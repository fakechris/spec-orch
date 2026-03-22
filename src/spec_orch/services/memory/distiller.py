"""MemoryDistiller — compaction and distillation of episodic memory.

Extracted from MemoryService.  Handles expired-episode grouping,
LLM-based (or fallback) summarisation, and soft-delete of stale entries.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from spec_orch.services.memory.types import MemoryEntry, MemoryLayer

if TYPE_CHECKING:
    from spec_orch.services.memory.protocol import MemoryProvider

logger = logging.getLogger(__name__)


class MemoryDistiller:
    """Compaction and distillation logic over a :class:`MemoryProvider`.

    Requires store / get / forget access to the provider.
    """

    def __init__(self, provider: MemoryProvider) -> None:
        self._provider = provider

    def _list_summaries(self, **kwargs: Any) -> list[dict[str, Any]]:
        if hasattr(self._provider, "list_summaries"):
            result: list[dict[str, Any]] = self._provider.list_summaries(**kwargs)  # type: ignore[union-attr]
            return result
        keys = self._provider.list_keys(
            layer=kwargs.get("layer"), tags=kwargs.get("tags"), limit=kwargs.get("limit", 100)
        )
        return [
            {"key": k, "layer": kwargs.get("layer", ""), "tags": [], "created_at": ""} for k in keys
        ]

    def compact(
        self,
        *,
        max_age_days: int = 30,
        summarize: bool = True,
        planner_config: dict[str, Any] | None = None,
    ) -> dict[str, int]:
        """Mark expired episodic entries as superseded, optionally distilling first."""
        from datetime import UTC, datetime, timedelta

        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)

        summaries = self._list_summaries(layer=MemoryLayer.EPISODIC.value, limit=100_000)
        expired_keys: list[str] = []
        retained = 0
        for s in summaries:
            created = s.get("created_at", "")
            try:
                entry_dt = datetime.fromisoformat(created)
            except (ValueError, TypeError):
                retained += 1
                continue
            if entry_dt < cutoff:
                expired_keys.append(s["key"])
            else:
                retained += 1

        distilled = 0
        if summarize and expired_keys:
            distilled = self._distill_expired_episodes(expired_keys, planner_config)

        soft_deleted = 0
        for key in expired_keys:
            entry = self._provider.get(key)
            if entry is None:
                continue
            if entry.metadata.get("relation_type") == "superseded":
                continue
            entry.metadata["relation_type"] = "superseded"
            self._provider.store(entry)
            soft_deleted += 1

        if soft_deleted > 0 or distilled > 0:
            logger.info(
                "Memory compact: soft-deleted %d expired entries, "
                "distilled %d summaries, retained %d",
                soft_deleted,
                distilled,
                retained,
            )
        return {"removed": soft_deleted, "retained": retained, "distilled": distilled}

    def _distill_expired_episodes(
        self,
        expired_keys: list[str],
        planner_config: dict[str, Any] | None = None,
    ) -> int:
        """Group expired episodes by issue_id and distill each group."""
        groups: dict[str, list[MemoryEntry]] = {}
        ungrouped: list[MemoryEntry] = []
        for key in expired_keys:
            entry = self._provider.get(key)
            if entry is None:
                continue
            issue_id = entry.metadata.get("issue_id")
            if issue_id:
                groups.setdefault(str(issue_id), []).append(entry)
            else:
                ungrouped.append(entry)

        distilled = 0
        for issue_id, entries in groups.items():
            if len(entries) < 2:
                continue
            summary_text = self._summarize_episode_group(entries, planner_config)
            if summary_text:
                tags_union = sorted({t for e in entries for t in e.tags})
                ts = int(time.time())
                self._provider.store(
                    MemoryEntry(
                        key=f"distilled-{issue_id}-{ts}",
                        content=summary_text,
                        layer=MemoryLayer.SEMANTIC,
                        tags=["distilled", "auto-consolidated", f"issue:{issue_id}"],
                        metadata={
                            "issue_id": issue_id,
                            "source_count": len(entries),
                            "source_tags": tags_union,
                            "entity_scope": "issue",
                            "entity_id": issue_id,
                            "relation_type": "derive",
                        },
                    )
                )
                distilled += 1

        if len(ungrouped) >= 3:
            summary_text = self._summarize_episode_group(ungrouped, planner_config)
            if summary_text:
                self._provider.store(
                    MemoryEntry(
                        key=f"distilled-misc-{int(time.time())}",
                        content=summary_text,
                        layer=MemoryLayer.SEMANTIC,
                        tags=["distilled", "auto-consolidated", "misc"],
                        metadata={"source_count": len(ungrouped)},
                    )
                )
                distilled += 1

        return distilled

    @staticmethod
    def _summarize_episode_group(
        entries: list[MemoryEntry],
        planner_config: dict[str, Any] | None = None,
    ) -> str:
        """Produce a summary via LLM or concatenation fallback."""
        combined = "\n\n---\n\n".join(
            f"[{e.key}] ({', '.join(e.tags)})\n{e.content}" for e in entries
        )

        try:
            import litellm  # type: ignore[import-untyped,import-not-found]

            cfg = planner_config or {}
            model = cfg.get("model", "anthropic/claude-sonnet-4-20250514")
            api_type = cfg.get("api_type", "anthropic")
            if "/" not in model:
                model = f"{api_type}/{model}"

            kwargs: dict[str, Any] = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a memory consolidation assistant. "
                            "Distill the following episodic memory entries into a concise "
                            "SEMANTIC summary that preserves key learnings, failure patterns, "
                            "and actionable insights. Be specific about what happened and why. "
                            "Output plain text, no JSON wrapper."
                        ),
                    },
                    {"role": "user", "content": combined},
                ],
                "temperature": 0.2,
            }
            if cfg.get("api_key"):
                kwargs["api_key"] = cfg["api_key"]
            elif cfg.get("api_key_env"):
                import os

                kwargs["api_key"] = os.environ.get(cfg["api_key_env"])
            if cfg.get("api_base"):
                kwargs["api_base"] = cfg["api_base"]
            elif cfg.get("api_base_env"):
                import os

                kwargs["api_base"] = os.environ.get(cfg["api_base_env"])

            response = litellm.completion(**kwargs)
            choices = getattr(response, "choices", None) or []
            if choices:
                message = getattr(choices[0], "message", None)
                content = (getattr(message, "content", None) or "") if message else ""
                if content.strip():
                    return content.strip()
        except ImportError:
            logger.debug("litellm not available; using concatenation fallback for distillation")
        except Exception:
            logger.warning("LLM distillation failed; using concatenation fallback", exc_info=True)

        lines = [f"- [{e.key}]: {e.content[:200]}" for e in entries[:20]]
        return f"Consolidated {len(entries)} episodes:\n" + "\n".join(lines)

    def soft_delete_stale_entries(self, *, max_age_days: int = 90) -> int:
        """Mark old episodic entries as superseded instead of hard-deleting."""
        from datetime import UTC, datetime, timedelta

        cutoff = (datetime.now(UTC) - timedelta(days=max_age_days)).isoformat()
        summaries = self._list_summaries(layer=MemoryLayer.EPISODIC.value, limit=100_000)
        marked = 0
        for s in summaries:
            updated = s.get("updated_at", "")
            if not updated or updated >= cutoff:
                continue
            entry = self._provider.get(s["key"])
            if entry is None:
                continue
            if entry.metadata.get("relation_type") == "superseded":
                continue
            entry.metadata["relation_type"] = "superseded"
            self._provider.store(entry)
            marked += 1
        if marked > 0:
            logger.info("Soft-deleted %d stale episodic entries", marked)
        return marked
