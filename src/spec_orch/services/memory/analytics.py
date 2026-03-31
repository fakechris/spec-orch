"""MemoryAnalytics — trend aggregation and structured learning views.

Extracted from MemoryService to keep the façade lean.  All methods
are stateless: they only read from the provider and return dicts.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from spec_orch.services.memory._utils import list_summaries_compat
from spec_orch.services.memory.types import MemoryLayer

if TYPE_CHECKING:
    from spec_orch.services.memory.protocol import MemoryProvider

logger = logging.getLogger(__name__)


class MemoryAnalytics:
    """Read-only analytics over a :class:`MemoryProvider`."""

    def __init__(self, provider: MemoryProvider) -> None:
        self._provider = provider

    def _list_summaries(self, **kwargs: Any) -> list[dict[str, Any]]:
        return list_summaries_compat(self._provider, **kwargs)

    def get_trend_summary(self, *, recent_days: int = 7) -> dict[str, Any]:
        """Aggregate run outcomes over *recent_days* into a trend dict."""
        from datetime import UTC, datetime, timedelta

        cutoff = (datetime.now(UTC) - timedelta(days=recent_days)).isoformat()
        summaries = self._list_summaries(
            layer=MemoryLayer.SEMANTIC.value,
            tags=["run-summary"],
            limit=10_000,
            created_after=cutoff,
        )
        total = 0
        succeeded = 0
        failed = 0
        failed_conditions: dict[str, int] = {}
        for s in summaries:
            entry = self._provider.get(s["key"])
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

    def get_active_run_signals(self, days: int = 7) -> dict[str, Any]:
        """Return recent run activity signals."""
        from datetime import UTC, datetime, timedelta

        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        summaries = self._list_summaries(
            layer=MemoryLayer.SEMANTIC.value,
            tags=["run-summary"],
            limit=10_000,
            created_after=cutoff,
        )
        recent_issues: list[str] = []
        recent_failures: list[str] = []
        total = 0
        succeeded = 0
        for s in summaries:
            entry = self._provider.get(s["key"])
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

    def get_failure_patterns(
        self, entity_id: str | None = None, top_k: int = 10
    ) -> list[dict[str, Any]]:
        """Return structured failure patterns from memory."""
        keys = self._provider.list_keys(
            layer=MemoryLayer.EPISODIC.value, tags=["issue-result"], limit=top_k * 3
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
        self, entity_id: str | None = None, top_k: int = 5
    ) -> list[dict[str, Any]]:
        """Return structured success recipes from run summaries."""
        keys = self._provider.list_keys(
            layer=MemoryLayer.SEMANTIC.value, tags=["run-summary"], limit=top_k * 5
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

    def get_reviewed_decision_failures(self, top_k: int = 5) -> list[dict[str, Any]]:
        """Return latest reviewed decision outcomes that ended negatively."""
        return self._decision_reviews_by_verdict(top_k=top_k, positive=False)

    def get_reviewed_decision_recipes(self, top_k: int = 5) -> list[dict[str, Any]]:
        """Return latest reviewed decision outcomes that ended positively."""
        return self._decision_reviews_by_verdict(top_k=top_k, positive=True)

    def get_reviewed_acceptance_findings(self, top_k: int = 5) -> list[dict[str, Any]]:
        """Return latest reviewed acceptance judgments, excluding queued findings."""
        keys = self._provider.list_keys(
            layer=MemoryLayer.EPISODIC.value,
            tags=["acceptance-judgment"],
            limit=top_k * 10,
        )
        items: list[dict[str, Any]] = []
        for key in keys:
            entry = self._provider.get(key)
            if entry is None:
                continue
            if entry.metadata.get("relation_type") == "superseded":
                continue
            if entry.metadata.get("provenance") != "reviewed":
                continue
            items.append(
                {
                    "key": entry.key,
                    "mission_id": entry.metadata.get("mission_id", ""),
                    "round_id": entry.metadata.get("round_id"),
                    "judgment_id": entry.metadata.get("judgment_id", ""),
                    "judgment_class": entry.metadata.get("judgment_class", ""),
                    "workflow_state": entry.metadata.get("workflow_state", ""),
                    "finding_id": entry.metadata.get("finding_id", ""),
                    "route": entry.metadata.get("route", ""),
                    "evidence_refs": list(entry.metadata.get("evidence_refs", []) or []),
                    "baseline_ref": entry.metadata.get("baseline_ref", ""),
                    "origin_step": entry.metadata.get("origin_step", ""),
                    "graph_profile": entry.metadata.get("graph_profile", ""),
                    "run_mode": entry.metadata.get("run_mode", ""),
                    "compare_overlay": bool(entry.metadata.get("compare_overlay", False)),
                    "promotion_test": entry.metadata.get("promotion_test", ""),
                    "dedupe_key": entry.metadata.get("dedupe_key", ""),
                    "summary": entry.content,
                    "provenance": entry.metadata.get("provenance", "unreviewed"),
                    "created_at": entry.created_at,
                }
            )
            if len(items) >= top_k:
                break
        return items

    def recall_latest_with_provenance(
        self,
        *,
        entity_scope: str,
        entity_id: str,
        layer: MemoryLayer | None = None,
        tags: list[str] | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Return latest-first recall results with explicit provenance."""
        from spec_orch.services.memory.types import MemoryQuery

        entries = self._provider.recall(
            MemoryQuery(
                layer=layer,
                tags=tags or [],
                top_k=top_k,
                entity_scope=entity_scope,
                entity_id=entity_id,
                exclude_relation_types=["superseded"],
            )
        )
        results: list[dict[str, Any]] = []
        for entry in entries:
            results.append(
                {
                    "key": entry.key,
                    "content": entry.content,
                    "tags": list(entry.tags),
                    "metadata": entry.metadata,
                    "provenance": entry.metadata.get("provenance", "unreviewed"),
                    "created_at": entry.created_at,
                    "updated_at": entry.updated_at,
                }
            )
        return results

    def _decision_reviews_by_verdict(self, *, top_k: int, positive: bool) -> list[dict[str, Any]]:
        keys = self._provider.list_keys(
            layer=MemoryLayer.EPISODIC.value,
            tags=["decision-review"],
            limit=top_k * 10,
        )
        positive_verdicts = {
            "approval_granted",
            "acceptance_candidate_promoted",
            "acceptance_candidate_reviewed",
            "continue",
        }
        items: list[dict[str, Any]] = []
        for key in keys:
            entry = self._provider.get(key)
            if entry is None:
                continue
            if entry.metadata.get("relation_type") == "superseded":
                continue
            verdict = str(entry.metadata.get("verdict", ""))
            verdict_is_positive = verdict in positive_verdicts
            if verdict_is_positive is not positive:
                continue
            items.append(
                {
                    "key": entry.key,
                    "record_id": entry.metadata.get("record_id", ""),
                    "review_id": entry.metadata.get("review_id", ""),
                    "point_key": entry.metadata.get("point_key", ""),
                    "owner": entry.metadata.get("owner", ""),
                    "selected_action": entry.metadata.get("selected_action", ""),
                    "verdict": verdict,
                    "summary": entry.content,
                    "provenance": entry.metadata.get("provenance", "reviewed"),
                    "created_at": entry.created_at,
                }
            )
            if len(items) >= top_k:
                break
        return items

    def get_project_profile(self, repo_root: Path | None = None) -> dict[str, Any]:
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
    def _fill_profile_from_config(profile: Any, repo_root: Path) -> None:
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
