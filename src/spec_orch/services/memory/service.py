"""MemoryService — singleton façade for the memory subsystem.

Wraps a :class:`MemoryProvider` and hooks into the :class:`EventBus`
to automatically capture mission lifecycle events into episodic memory.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from spec_orch.services.memory.fs_provider import FileSystemMemoryProvider
from spec_orch.services.memory.protocol import MemoryProvider
from spec_orch.services.memory.types import MemoryEntry, MemoryLayer, MemoryQuery

logger = logging.getLogger(__name__)

_DEFAULT_MEMORY_DIR = ".spec_orch_memory"

_instance: MemoryService | None = None


class MemoryService:
    """High-level façade over a pluggable :class:`MemoryProvider`.

    Also subscribes to the ``EventBus`` so that mission/issue state
    changes are transparently recorded in episodic memory.
    """

    def __init__(
        self,
        provider: MemoryProvider | None = None,
        *,
        repo_root: Path | None = None,
        qdrant_config: dict[str, Any] | None = None,
        derivation_mode: str = "sync",
    ) -> None:
        if provider is not None:
            self._provider = provider
        else:
            root = (repo_root or Path.cwd()) / _DEFAULT_MEMORY_DIR
            self._provider = _build_provider(root, qdrant_config)
        self._derivation_mode = derivation_mode
        self._derivation_queue: Any = None
        self._derivation_worker: Any = None

    @property
    def provider(self) -> MemoryProvider:
        return self._provider

    @property
    def derivation_mode(self) -> str:
        return self._derivation_mode

    def _ensure_derivation_queue(self) -> Any:
        """Lazily create the derivation queue and worker."""
        if self._derivation_queue is not None:
            return self._derivation_queue
        from spec_orch.services.memory.derivation import (
            DerivationQueue,
            DerivationWorker,
        )

        if hasattr(self._provider, "_root"):
            db_path = self._provider._root / "_derivation.db"
        else:
            db_path = Path.cwd() / _DEFAULT_MEMORY_DIR / "_derivation.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._derivation_queue = DerivationQueue(db_path)
        self._derivation_worker = DerivationWorker(self._derivation_queue)
        self._register_derivation_handlers()
        return self._derivation_queue

    def _register_derivation_handlers(self) -> None:
        """Register standard derivation task handlers."""
        if self._derivation_worker is None:
            return

        def _handle_compact(payload: dict[str, Any]) -> None:
            self.compact(
                max_age_days=payload.get("max_age_days", 30),
                summarize=payload.get("summarize", True),
                planner_config=payload.get("planner_config"),
            )

        def _handle_profile_refresh(payload: dict[str, Any]) -> None:
            repo_root = Path(payload["repo_root"]) if payload.get("repo_root") else None
            self.get_project_profile(repo_root=repo_root)

        def _handle_stale_cleanup(payload: dict[str, Any]) -> None:
            self._soft_delete_stale_entries(max_age_days=payload.get("max_age_days", 90))

        def _handle_recipe_extraction(payload: dict[str, Any]) -> None:
            entity_id = payload.get("entity_id")
            self.get_success_recipes(entity_id=entity_id, top_k=10)

        self._derivation_worker.register("compact", _handle_compact)
        self._derivation_worker.register("profile-refresh", _handle_profile_refresh)
        self._derivation_worker.register("stale-cleanup", _handle_stale_cleanup)
        self._derivation_worker.register("recipe-extraction", _handle_recipe_extraction)

    # -- delegated CRUD ------------------------------------------------------

    def store(self, entry: MemoryEntry) -> str:
        key = self._provider.store(entry)
        self._emit("memory.stored", {"key": key, "layer": entry.layer.value})
        return key

    def recall(self, query: MemoryQuery) -> list[MemoryEntry]:
        results = self._provider.recall(query)
        self._emit("memory.recalled", {"query_text": query.text, "count": len(results)})
        return results

    def forget(self, key: str) -> bool:
        removed = self._provider.forget(key)
        if removed:
            self._emit("memory.forgotten", {"key": key})
        return removed

    def get(self, key: str) -> MemoryEntry | None:
        return self._provider.get(key)

    def list_keys(
        self,
        *,
        layer: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[str]:
        return self._provider.list_keys(layer=layer, tags=tags, limit=limit)

    def list_summaries(
        self,
        *,
        layer: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return index-only summaries (no file I/O per entry)."""
        if hasattr(self._provider, "list_summaries"):
            result: list[dict[str, Any]] = self._provider.list_summaries(
                layer=layer, tags=tags, limit=limit
            )  # type: ignore[union-attr]
            return result
        keys = self._provider.list_keys(layer=layer, tags=tags, limit=limit)
        results: list[dict[str, Any]] = []
        for k in keys:
            entry = self._provider.get(k)
            results.append(
                {
                    "key": k,
                    "layer": layer or "",
                    "tags": [],
                    "created_at": entry.created_at if entry else "",
                }
            )
        return results

    def enqueue_derivation(self, task_type: str, payload: dict[str, Any] | None = None) -> str:
        """Enqueue a background derivation task."""
        q = self._ensure_derivation_queue()
        result: str = q.enqueue(task_type, payload)
        return result

    def process_derivations(self, batch_size: int = 5) -> int:
        """Process pending derivation tasks. Returns count processed."""
        self._ensure_derivation_queue()
        if self._derivation_worker is None:
            return 0
        result: int = self._derivation_worker.process_batch(batch_size)
        return result

    def schedule_post_run_derivations(
        self,
        *,
        issue_id: str,
        run_id: str,
        repo_root: Path | None = None,
    ) -> list[str]:
        """Schedule standard post-run derivation tasks.

        In sync mode, executes inline. In async mode, enqueues for later.
        """
        task_ids: list[str] = []
        if self._derivation_mode == "async":
            task_ids.append(
                self.enqueue_derivation("compact", {"max_age_days": 30, "summarize": True})
            )
            task_ids.append(
                self.enqueue_derivation(
                    "profile-refresh",
                    {"repo_root": str(repo_root) if repo_root else ""},
                )
            )
            task_ids.append(self.enqueue_derivation("recipe-extraction", {"entity_id": issue_id}))
        else:
            self.compact(max_age_days=30, summarize=True)
            if repo_root:
                self.get_project_profile(repo_root=repo_root)
        return task_ids

    def _soft_delete_stale_entries(self, *, max_age_days: int = 90) -> int:
        """Mark old episodic entries as superseded instead of hard-deleting."""
        from datetime import UTC, datetime, timedelta

        cutoff = (datetime.now(UTC) - timedelta(days=max_age_days)).isoformat()
        summaries = self.list_summaries(layer=MemoryLayer.EPISODIC.value, limit=100_000)
        marked = 0
        for s in summaries:
            updated = s.get("updated_at", "")
            if not updated or updated >= cutoff:
                continue
            entry = self.get(s["key"])
            if entry is None:
                continue
            if entry.metadata.get("relation_type") == "superseded":
                continue
            entry.metadata["relation_type"] = "superseded"
            self.store(entry)
            marked += 1
        if marked > 0:
            logger.info("Soft-deleted %d stale episodic entries", marked)
        return marked

    def compact(
        self,
        *,
        max_age_days: int = 30,
        summarize: bool = True,
        planner_config: dict[str, Any] | None = None,
    ) -> dict[str, int]:
        """Remove expired episodic entries, optionally distilling them first.

        When *summarize* is ``True`` (default) and a planner LLM is
        configured, expired episodes are grouped by ``issue_id`` and
        distilled into SEMANTIC summaries before deletion.  If no LLM
        is available, a simple concatenation fallback is used.
        """
        from datetime import UTC, datetime, timedelta

        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)

        summaries = self.list_summaries(layer=MemoryLayer.EPISODIC.value, limit=100_000)
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

        removed = 0
        for key in expired_keys:
            if self.forget(key):
                removed += 1

        if removed > 0 or distilled > 0:
            logger.info(
                "Memory compact: removed %d expired entries, distilled %d summaries, retained %d",
                removed,
                distilled,
                retained,
            )
        return {"removed": removed, "retained": retained, "distilled": distilled}

    def _distill_expired_episodes(
        self,
        expired_keys: list[str],
        planner_config: dict[str, Any] | None = None,
    ) -> int:
        """Group expired episodes by issue_id and distill each group."""
        groups: dict[str, list[MemoryEntry]] = {}
        ungrouped: list[MemoryEntry] = []
        for key in expired_keys:
            entry = self.get(key)
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
                self.store(
                    MemoryEntry(
                        key=f"distilled-{issue_id}",
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
                self.store(
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
        """Produce a summary for a group of related episodic entries.

        Uses LLM via litellm when available, otherwise falls back to
        simple concatenation with truncation.
        """
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

    def consolidate_run(
        self,
        *,
        run_id: str,
        issue_id: str,
        succeeded: bool,
        failed_conditions: list[str] | None = None,
        key_learnings: str = "",
        builder_adapter: str | None = None,
        verification_passed: bool | None = None,
    ) -> str | None:
        """Store a run outcome summary in semantic memory for cross-run learning."""
        outcome = "succeeded" if succeeded else "failed"
        content = f"Run {run_id} for {issue_id}: {outcome}"
        if builder_adapter:
            content += f"\nBuilder: {builder_adapter}"
        if verification_passed is not None:
            content += f"\nVerification: {'passed' if verification_passed else 'failed'}"
        if key_learnings:
            content += f"\n{key_learnings}"

        meta: dict[str, Any] = {
            "run_id": run_id,
            "issue_id": issue_id,
            "succeeded": succeeded,
            "failed_conditions": failed_conditions or [],
            "entity_scope": "issue",
            "entity_id": issue_id,
            "relation_type": "summarize",
            "source_run_id": run_id,
        }
        if builder_adapter:
            meta["builder_adapter"] = builder_adapter
        if verification_passed is not None:
            meta["verification_passed"] = verification_passed

        entry = MemoryEntry(
            key=f"run-summary-{run_id}",
            content=content,
            layer=MemoryLayer.SEMANTIC,
            tags=["run-summary", "auto-consolidated"],
            metadata=meta,
        )
        return self.store(entry)

    def record_builder_telemetry(
        self,
        *,
        run_id: str,
        issue_id: str,
        tool_sequence: list[str],
        lines_scanned: int = 0,
        source_path: str = "",
    ) -> str | None:
        """Store builder tool-call telemetry in episodic memory."""
        if not tool_sequence:
            return None
        content = (
            f"Builder telemetry for run {run_id} (issue {issue_id}):\n"
            f"Tool sequence ({len(tool_sequence)} calls): " + " → ".join(tool_sequence[:50])
        )
        entry = MemoryEntry(
            key=f"builder-telemetry-{run_id}",
            content=content,
            layer=MemoryLayer.EPISODIC,
            tags=["builder-telemetry", f"issue:{issue_id}", f"run:{run_id}"],
            metadata={
                "run_id": run_id,
                "issue_id": issue_id,
                "tool_sequence": tool_sequence[:100],
                "tool_count": len(tool_sequence),
                "lines_scanned": lines_scanned,
                "source_path": source_path,
                "entity_scope": "issue",
                "entity_id": issue_id,
                "relation_type": "observed",
                "source_run_id": run_id,
            },
        )
        return self.store(entry)

    def record_acceptance(
        self,
        *,
        issue_id: str,
        accepted_by: str,
        run_id: str = "",
    ) -> str:
        """Store human acceptance feedback in episodic memory."""
        content = f"Issue {issue_id} accepted by {accepted_by}." + (
            f" Run: {run_id}" if run_id else ""
        )
        entry = MemoryEntry(
            key=f"acceptance-{issue_id}",
            content=content,
            layer=MemoryLayer.EPISODIC,
            tags=["acceptance", f"issue:{issue_id}", "human-feedback"],
            metadata={
                "issue_id": issue_id,
                "accepted_by": accepted_by,
                "run_id": run_id,
                "entity_scope": "issue",
                "entity_id": issue_id,
                "relation_type": "observed",
                "source_run_id": run_id,
            },
        )
        return self.store(entry)

    def recall_latest(
        self,
        *,
        entity_scope: str,
        entity_id: str,
        layer: str | None = None,
        tags: list[str] | None = None,
        top_k: int = 5,
    ) -> list[MemoryEntry]:
        """Recall the most recent entries for a given entity, excluding superseded ones."""
        if hasattr(self._provider, "_filtered_keys"):
            keys = self._provider._filtered_keys(
                layer=layer,
                tags=tags,
                limit=top_k,
                entity_scope=entity_scope,
                entity_id=entity_id,
                exclude_relation_types=["superseded"],
            )
        else:
            keys = self._provider.list_keys(layer=layer, tags=tags, limit=top_k * 3)

        results: list[MemoryEntry] = []
        for key in keys:
            entry = self._provider.get(key)
            if entry is None:
                continue
            meta = entry.metadata
            if meta.get("entity_scope") != entity_scope:
                continue
            if meta.get("entity_id") != entity_id:
                continue
            if meta.get("relation_type") == "superseded":
                continue
            results.append(entry)
            if len(results) >= top_k:
                break
        return results

    def get_failure_patterns(
        self,
        entity_id: str | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Return structured failure patterns from memory."""
        keys = self._provider.list_keys(
            layer=MemoryLayer.EPISODIC.value,
            tags=["issue-result"],
            limit=top_k * 3,
        )
        patterns: list[dict[str, Any]] = []
        for key in keys:
            entry = self._provider.get(key)
            if entry is None:
                continue
            if entry.metadata.get("relation_type") == "superseded":
                continue
            if entry.metadata.get("succeeded") is not False:
                continue
            if entity_id and entry.metadata.get("entity_id") != entity_id:
                continue
            patterns.append(
                {
                    "key": entry.key,
                    "issue_id": entry.metadata.get("issue_id", ""),
                    "failed_conditions": entry.metadata.get("failed_conditions", []),
                    "content": entry.content[:500],
                    "created_at": entry.created_at,
                }
            )
            if len(patterns) >= top_k:
                break
        return patterns

    def get_success_recipes(
        self,
        entity_id: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Return structured success recipes from run summaries."""
        keys = self._provider.list_keys(
            layer=MemoryLayer.SEMANTIC.value,
            tags=["run-summary"],
            limit=top_k * 5,
        )
        recipes: list[dict[str, Any]] = []
        for key in keys:
            entry = self._provider.get(key)
            if entry is None:
                continue
            if entry.metadata.get("relation_type") == "superseded":
                continue
            if not entry.metadata.get("succeeded"):
                continue
            if entity_id and entry.metadata.get("entity_id") != entity_id:
                continue
            recipes.append(
                {
                    "key": entry.key,
                    "issue_id": entry.metadata.get("issue_id", ""),
                    "builder_adapter": entry.metadata.get("builder_adapter", ""),
                    "content": entry.content[:500],
                    "created_at": entry.created_at,
                }
            )
            if len(recipes) >= top_k:
                break
        return recipes

    def get_project_profile(
        self,
        repo_root: Path | None = None,
    ) -> dict[str, Any]:
        """Build a project profile from memory + config fallback."""
        from spec_orch.domain.context import ProjectProfile

        profile = ProjectProfile()

        trend = self.get_trend_summary()
        profile.recent_success_rate = trend.get("success_rate")
        profile.recent_period_days = trend.get("period_days", 7)
        top_failures = trend.get("top_failure_reasons", {})
        profile.high_freq_failure_conditions = list(top_failures.keys())[:5]

        failure_patterns = self.get_failure_patterns(top_k=10)
        seen: set[str] = set()
        for fp in failure_patterns:
            for cond in fp.get("failed_conditions", []):
                if cond not in seen:
                    seen.add(cond)
                    profile.common_failures.append(cond)

        if repo_root:
            self._fill_profile_from_config(profile, repo_root)

        return {
            "tech_stack": profile.tech_stack,
            "common_failures": profile.common_failures[:10],
            "verification_commands": profile.verification_commands,
            "architecture_constraints": profile.architecture_constraints,
            "recent_success_rate": profile.recent_success_rate,
            "recent_period_days": profile.recent_period_days,
            "high_freq_failure_conditions": profile.high_freq_failure_conditions,
            "active_skills": profile.active_skills,
        }

    @staticmethod
    def _fill_profile_from_config(
        profile: Any,
        repo_root: Path,
    ) -> None:
        """Populate static profile fields from spec-orch.toml."""
        import tomllib

        toml_path = repo_root / "spec-orch.toml"
        if not toml_path.exists():
            return
        try:
            with toml_path.open("rb") as f:
                raw = tomllib.load(f)
        except Exception:
            return
        proj = raw.get("project", {})
        if proj.get("type"):
            profile.tech_stack = [proj["type"]]
        verification = raw.get("verification", {})
        steps = verification.get("steps", {})
        for step_name, step_cfg in steps.items():
            if isinstance(step_cfg, dict) and step_cfg.get("command"):
                profile.verification_commands.append(f"{step_name}: {step_cfg['command']}")

    def get_active_run_signals(
        self,
        days: int = 7,
    ) -> dict[str, Any]:
        """Return recent run activity signals."""
        from datetime import UTC, datetime, timedelta

        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        summaries = self.list_summaries(
            layer=MemoryLayer.SEMANTIC.value,
            tags=["run-summary"],
            limit=100_000,
        )
        recent_issues: list[str] = []
        recent_failures: list[str] = []
        total = 0
        succeeded = 0
        for s in summaries:
            if s.get("created_at", "") < cutoff:
                continue
            entry = self.get(s["key"])
            if entry is None:
                continue
            total += 1
            issue_id = entry.metadata.get("issue_id", "")
            if entry.metadata.get("succeeded"):
                succeeded += 1
            else:
                if issue_id and issue_id not in recent_failures:
                    recent_failures.append(issue_id)
            if issue_id and issue_id not in recent_issues:
                recent_issues.append(issue_id)
        return {
            "period_days": days,
            "total_runs": total,
            "succeeded": succeeded,
            "recent_issues": recent_issues[:20],
            "recent_failure_issues": recent_failures[:10],
        }

    def get_trend_summary(self, *, recent_days: int = 7) -> dict[str, Any]:
        """Aggregate run outcomes over recent_days into a trend dict."""
        from datetime import UTC, datetime, timedelta

        cutoff = (datetime.now(UTC) - timedelta(days=recent_days)).isoformat()
        summaries = self.list_summaries(
            layer=MemoryLayer.SEMANTIC.value, tags=["run-summary"], limit=100_000
        )
        total = 0
        succeeded = 0
        failed = 0
        failed_conditions: dict[str, int] = {}
        for s in summaries:
            created = s.get("created_at", "")
            if created < cutoff:
                continue
            entry = self.get(s["key"])
            if entry is None:
                continue
            total += 1
            if entry.metadata.get("succeeded"):
                succeeded += 1
            else:
                failed += 1
                for cond in entry.metadata.get("failed_conditions", []):
                    failed_conditions[cond] = failed_conditions.get(cond, 0) + 1

        return {
            "period_days": recent_days,
            "total_runs": total,
            "succeeded": succeeded,
            "failed": failed,
            "success_rate": round(succeeded / total, 2) if total > 0 else 0.0,
            "top_failure_reasons": dict(
                sorted(failed_conditions.items(), key=lambda x: x[1], reverse=True)[:5]
            ),
        }

    # -- lifecycle event capture ---------------------------------------------

    def record_mission_event(
        self,
        mission_id: str,
        phase: str,
        *,
        detail: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Write a mission lifecycle event to episodic memory."""
        content = f"# Mission {mission_id} — {phase}"
        if detail:
            content += f"\n\n{detail}"
        entry = MemoryEntry(
            key=f"mission-event-{mission_id}-{phase}",
            content=content,
            layer=MemoryLayer.EPISODIC,
            tags=["mission-event", f"mission:{mission_id}", phase],
            metadata={
                "mission_id": mission_id,
                "phase": phase,
                "entity_scope": "mission",
                "entity_id": mission_id,
                "relation_type": "observed",
                **(metadata or {}),
            },
        )
        return self.store(entry)

    def record_issue_completion(
        self,
        issue_id: str,
        *,
        succeeded: bool,
        summary: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Write an issue completion event to episodic memory."""
        status = "succeeded" if succeeded else "failed"
        content = f"# Issue {issue_id} — {status}"
        if summary:
            content += f"\n\n{summary}"
        entry = MemoryEntry(
            key=f"issue-result-{issue_id}",
            content=content,
            layer=MemoryLayer.EPISODIC,
            tags=["issue-result", f"issue:{issue_id}", status],
            metadata={
                "issue_id": issue_id,
                "succeeded": succeeded,
                "entity_scope": "issue",
                "entity_id": issue_id,
                "relation_type": "observed",
                **(metadata or {}),
            },
        )
        return self.store(entry)

    # -- EventBus integration ------------------------------------------------

    def subscribe_to_event_bus(self) -> None:
        """Wire up automatic memory capture from EventBus events."""
        try:
            from spec_orch.services.event_bus import EventTopic, get_event_bus

            bus = get_event_bus()
            bus.subscribe(self._on_mission_state, EventTopic.MISSION_STATE)
            bus.subscribe(self._on_issue_state, EventTopic.ISSUE_STATE)
            bus.subscribe(self._on_conductor, EventTopic.CONDUCTOR)
            bus.subscribe(self._on_gate_result, EventTopic.GATE_RESULT)
            logger.info("MemoryService subscribed to EventBus")
        except ImportError:
            logger.debug("EventBus not available, skipping subscription")

    def _on_mission_state(self, event: Any) -> None:
        payload = event.payload if hasattr(event, "payload") else event
        mission_id = payload.get("mission_id", "unknown")
        new_state = payload.get("new_state", "unknown")
        old_state = payload.get("old_state", "")
        detail = f"Transition: {old_state} → {new_state}" if old_state else ""
        self.record_mission_event(mission_id, new_state, detail=detail, metadata=payload)

    def _on_issue_state(self, event: Any) -> None:
        payload = event.payload if hasattr(event, "payload") else event
        issue_id = payload.get("issue_id", "unknown")
        state = payload.get("state", "unknown")
        succeeded = state in ("accepted", "merged")
        if state in ("accepted", "merged", "failed"):
            self.record_issue_completion(issue_id, succeeded=succeeded, metadata=payload)

    def _on_conductor(self, event: Any) -> None:
        payload = event.payload if hasattr(event, "payload") else event
        action = payload.get("action", "")
        thread_id = payload.get("thread_id", "unknown")

        if action == "fork":
            self.store(
                MemoryEntry(
                    key=f"conductor-fork-{thread_id}-{payload.get('linear_issue_id', '')}",
                    content=f"Fork: {payload.get('title', '')}",
                    layer=MemoryLayer.EPISODIC,
                    tags=["conductor-fork", f"thread:{thread_id}"],
                    metadata=payload,
                )
            )
        else:
            intent_cat = payload.get("intent_category", "")
            self.store(
                MemoryEntry(
                    key=f"intent-classified-{thread_id}-{payload.get('message_id', '')}",
                    content=payload.get("summary", ""),
                    layer=MemoryLayer.EPISODIC,
                    tags=["intent-classified", f"thread:{thread_id}", f"intent:{intent_cat}"],
                    metadata=payload,
                )
            )

    def _on_gate_result(self, event: Any) -> None:
        payload = event.payload if hasattr(event, "payload") else event
        issue_id = payload.get("issue_id", "unknown")
        passed = payload.get("passed", False)
        self.store(
            MemoryEntry(
                key=f"gate-verdict-{issue_id}-{int(time.time() * 1000)}",
                content=f"Gate {'passed' if passed else 'failed'}",
                layer=MemoryLayer.EPISODIC,
                tags=[
                    "gate-verdict",
                    f"issue:{issue_id}",
                    "gate-passed" if passed else "gate-failed",
                ],
                metadata=payload,
            )
        )

    # -- EventBus emit helper ------------------------------------------------

    @staticmethod
    def _emit(topic_str: str, payload: dict[str, Any]) -> None:
        try:
            from spec_orch.services.event_bus import Event, EventTopic, get_event_bus

            bus = get_event_bus()
            topic = EventTopic.MEMORY
            bus.publish(
                Event(topic=topic, payload={"sub": topic_str, **payload}, source="memory_service")
            )
        except ImportError:
            pass


def _build_provider(
    root: Path,
    qdrant_config: dict[str, Any] | None,
) -> MemoryProvider:
    """Select the best available MemoryProvider based on config."""
    if qdrant_config:
        try:
            from spec_orch.services.memory.vector_provider import (
                VectorEnhancedProvider,
            )

            return VectorEnhancedProvider(root, qdrant_config=qdrant_config)
        except Exception:
            logger.warning(
                "VectorEnhancedProvider unavailable; falling back to FileSystemMemoryProvider",
                exc_info=True,
            )
    return FileSystemMemoryProvider(root)


def _load_qdrant_config(repo_root: Path) -> dict[str, Any] | None:
    """Read ``[memory.qdrant]`` from spec-orch.toml if present."""
    import tomllib

    toml_path = repo_root / "spec-orch.toml"
    if not toml_path.exists():
        return None
    try:
        with toml_path.open("rb") as f:
            raw = tomllib.load(f)
    except Exception:
        return None
    mem_cfg = raw.get("memory", {})
    if not isinstance(mem_cfg, dict):
        return None
    provider = mem_cfg.get("provider", "")
    if provider not in ("filesystem_qdrant", "vector_enhanced"):
        return None
    return mem_cfg.get("qdrant") if isinstance(mem_cfg.get("qdrant"), dict) else None


def _load_derivation_mode(repo_root: Path) -> str:
    """Read ``[memory].derivation_mode`` from spec-orch.toml if present."""
    import tomllib

    toml_path = repo_root / "spec-orch.toml"
    if not toml_path.exists():
        return "sync"
    try:
        with toml_path.open("rb") as f:
            raw = tomllib.load(f)
    except Exception:
        return "sync"
    mem_cfg = raw.get("memory", {})
    mode = mem_cfg.get("derivation_mode", "sync") if isinstance(mem_cfg, dict) else "sync"
    return mode if mode in ("sync", "async") else "sync"


def get_memory_service(repo_root: Path | None = None) -> MemoryService:
    """Return the global ``MemoryService`` singleton, creating it if needed."""
    global _instance  # noqa: PLW0603
    if _instance is None:
        root = repo_root or Path.cwd()
        qdrant_config = _load_qdrant_config(root)
        derivation_mode = _load_derivation_mode(root)
        _instance = MemoryService(
            repo_root=root,
            qdrant_config=qdrant_config,
            derivation_mode=derivation_mode,
        )
    return _instance


def reset_memory_service() -> None:
    """Reset the singleton (for testing)."""
    global _instance  # noqa: PLW0603
    _instance = None
