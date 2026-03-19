"""Plan Strategy Evolver — learn scoper hints from historical plan outcomes.

Analyzes which wave/packet decomposition strategies correlate with fewer
failures and deviations, then generates "scoper hints" that are injected
into the scoper's system prompt to improve future planning.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.services.evidence_analyzer import EvidenceAnalyzer

logger = logging.getLogger(__name__)

_HINTS_FILE = "scoper_hints.json"

_STRATEGY_SYSTEM_PROMPT = """\
You are a planning strategy analyst for an AI coding-agent orchestrator.

You receive historical data about how missions were decomposed into waves and
work packets, along with their outcomes (success/failure, deviations).

Your job is to identify patterns and produce actionable "scoper hints" — short
directives that the planning LLM should follow when decomposing future missions.

Good hints are specific and evidence-based:
- "Database migration files should be isolated in wave-0 to prevent cross-wave conflicts."
- "Test files that frequently deviate should have their own dedicated work packet."
- "Modules under src/auth/ have a 40% failure rate; allocate extra verification steps."

Bad hints are vague or generic:
- "Plan carefully." (too vague)
- "Make sure tests pass." (not a decomposition hint)

Respond with ONLY a JSON object:
{
  "hints": [
    {
      "hint_id": "short-kebab-id",
      "text": "the actionable hint text",
      "evidence": "brief description of the data that supports this hint",
      "confidence": "low|medium|high"
    }
  ],
  "analysis_summary": "brief paragraph summarizing what you observed"
}
"""


@dataclass
class ScoperHint:
    """A single scoper hint derived from historical plan analysis."""

    hint_id: str
    text: str
    evidence: str = ""
    confidence: str = "medium"
    created_at: str = ""
    is_active: bool = True


@dataclass
class HintSet:
    """Collection of scoper hints with metadata."""

    hints: list[ScoperHint] = field(default_factory=list)
    analysis_summary: str = ""
    generated_at: str = ""


class PlanStrategyEvolver:
    """Analyze historical plan outcomes and generate scoper hints."""

    def __init__(self, repo_root: Path, planner: Any | None = None) -> None:
        self._repo_root = repo_root
        self._planner = planner
        self._hints_path = repo_root / _HINTS_FILE

    def load_hints(self) -> HintSet:
        """Load current scoper hints from disk."""
        if not self._hints_path.exists():
            return HintSet()

        try:
            data = json.loads(self._hints_path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read hints at %s", self._hints_path)
            return HintSet()

        if not isinstance(data, dict):
            return HintSet()

        hints: list[ScoperHint] = []
        for item in data.get("hints", []):
            if not isinstance(item, dict):
                continue
            try:
                hints.append(
                    ScoperHint(
                        hint_id=item["hint_id"],
                        text=item["text"],
                        evidence=item.get("evidence", ""),
                        confidence=item.get("confidence", "medium"),
                        created_at=item.get("created_at", ""),
                        is_active=item.get("is_active", True),
                    )
                )
            except (KeyError, TypeError):
                logger.warning("Skipping malformed hint: %s", item)

        return HintSet(
            hints=hints,
            analysis_summary=data.get("analysis_summary", ""),
            generated_at=data.get("generated_at", ""),
        )

    def save_hints(self, hint_set: HintSet) -> None:
        """Persist scoper hints to disk."""
        data = {
            "hints": [asdict(h) for h in hint_set.hints],
            "analysis_summary": hint_set.analysis_summary,
            "generated_at": hint_set.generated_at,
        }
        self._hints_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def collect_plan_outcomes(self, last_n: int = 20) -> dict[str, Any]:
        """Gather historical plan outcome data for analysis."""
        analyzer = EvidenceAnalyzer(self._repo_root)
        run_dirs = analyzer.collect_run_dirs()[-last_n:]

        if not run_dirs:
            return {}

        outcomes: list[dict[str, Any]] = []
        for rd in run_dirs:
            run_id = rd.name
            report = analyzer.read_report(rd)
            if report is None:
                continue

            deviations = analyzer.read_deviations(rd)
            plan_data = report.get("metadata", {}).get("plan", [])

            outcome: dict[str, Any] = {
                "run_id": run_id,
                "succeeded": report.get("mergeable", report.get("succeeded", False)),
                "failed_conditions": report.get("failed_conditions", []),
                "deviation_count": len(deviations),
                "deviating_files": [d.get("file_path", "") for d in deviations],
            }

            verification = report.get("verification", {})
            if verification:
                outcome["verification_results"] = {
                    k: {"passed": v.get("exit_code", 1) == 0}
                    for k, v in verification.items()
                    if isinstance(v, dict)
                }

            if plan_data:
                outcome["plan_structure"] = plan_data

            outcomes.append(outcome)

        return {"total_runs": len(outcomes), "outcomes": outcomes}

    def _collect_failure_details(self, last_n: int = 20) -> list[dict[str, Any]]:
        """Collect detailed failure samples with packet/wave context."""
        analyzer = EvidenceAnalyzer(self._repo_root)
        run_dirs = analyzer.collect_run_dirs()[-last_n:]
        samples: list[dict[str, Any]] = []

        for rd in run_dirs:
            report = analyzer.read_report(rd)
            if report is None or report.get("mergeable", True):
                continue

            sample: dict[str, Any] = {
                "run_id": rd.name,
                "failed_conditions": report.get("failed_conditions", []),
            }

            deviations = analyzer.read_deviations(rd)
            if deviations:
                sample["deviating_files"] = [d.get("file_path", "") for d in deviations[:5]]
                sample["deviation_types"] = list(
                    {d.get("deviation_type", "") for d in deviations if d.get("deviation_type")}
                )

            plan_data = report.get("metadata", {}).get("plan", [])
            if plan_data:
                sample["plan_structure"] = plan_data

            verification = report.get("verification", {})
            sample["failed_checks"] = [
                k
                for k, v in verification.items()
                if isinstance(v, dict) and v.get("exit_code", 1) != 0
            ]

            samples.append(sample)
            if len(samples) >= 10:
                break

        return samples

    def analyze(self, last_n: int = 20, *, context: Any | None = None) -> HintSet | None:
        """Use an LLM to analyze plan outcomes and generate hints.

        Returns the new ``HintSet``, or ``None`` if analysis is not possible.
        """
        if self._planner is None:
            return None

        plan_data = self.collect_plan_outcomes(last_n=last_n)
        if not plan_data:
            return None

        evidence_analyzer = EvidenceAnalyzer(self._repo_root)
        summary = evidence_analyzer.analyze()
        evidence_ctx = ""
        if summary.total_runs > 0:
            evidence_ctx = evidence_analyzer.format_as_llm_context(summary)

        failure_details = self._collect_failure_details(last_n=last_n)

        user_msg = f"Historical plan outcomes:\n```json\n{json.dumps(plan_data, indent=2)}\n```\n\n"
        if failure_details:
            user_msg += (
                "Detailed failure samples (use these to identify specific "
                "packet/wave decomposition problems):\n"
                f"```json\n{json.dumps(failure_details, indent=2)}\n```\n\n"
            )
        if evidence_ctx:
            user_msg += f"Additional evidence context:\n{evidence_ctx}\n\n"
        if context is not None:
            user_msg += self._render_context_for_analysis(context)
        user_msg += "Analyze these outcomes and generate scoper hints."

        try:
            response = self._planner.brainstorm(
                conversation_history=[
                    {"role": "system", "content": _STRATEGY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                codebase_context="",
            )
        except Exception:
            logger.exception("LLM call failed during plan strategy analysis")
            return None

        return self._parse_response(response)

    def _parse_response(self, response: Any) -> HintSet | None:
        if not isinstance(response, str):
            logger.warning("Non-string LLM response: %s", type(response).__name__)
            return None

        text = response.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            logger.warning("Could not find JSON object in strategy response")
            return None

        try:
            obj = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from strategy response")
            return None

        if not isinstance(obj, dict):
            return None

        now = datetime.now(UTC).isoformat()
        hints: list[ScoperHint] = []
        for item in obj.get("hints", []):
            if not isinstance(item, dict) or "text" not in item:
                continue
            hints.append(
                ScoperHint(
                    hint_id=item.get("hint_id", f"hint-{len(hints)}"),
                    text=item["text"],
                    evidence=item.get("evidence", ""),
                    confidence=item.get("confidence", "medium"),
                    created_at=now,
                )
            )

        new_hint_set = HintSet(
            hints=hints,
            analysis_summary=obj.get("analysis_summary", ""),
            generated_at=now,
        )
        return self.merge_hints(new_hint_set)

    @staticmethod
    def _render_context_for_analysis(context: Any) -> str:
        parts: list[str] = []
        task = getattr(context, "task", None)
        execution = getattr(context, "execution", None)
        learning = getattr(context, "learning", None)

        if task and getattr(task, "constraints", []):
            parts.append("Constraints:\n" + "\n".join(f"- {c}" for c in task.constraints))
        if execution and getattr(execution, "deviation_slices", []):
            parts.append(
                "Deviation slices:\n"
                + json.dumps(execution.deviation_slices[:5], ensure_ascii=False, indent=2)
            )
        if learning and getattr(learning, "similar_failure_samples", []):
            lines = [
                f"- {s.get('key', '?')}: {s.get('content', '')[:180]}"
                for s in learning.similar_failure_samples[:3]
            ]
            parts.append("Failure samples:\n" + "\n".join(lines))

        if not parts:
            return ""
        return "ContextBundle evidence:\n" + "\n\n".join(parts) + "\n\n"

    def format_hints_for_prompt(self, hint_set: HintSet | None = None) -> str:
        """Format active hints as text for injection into scoper system prompt."""
        if hint_set is None:
            hint_set = self.load_hints()

        active = [h for h in hint_set.hints if h.is_active]
        if not active:
            return ""

        lines = ["<scoper_hints>"]
        for h in active:
            conf = f" [{h.confidence}]" if h.confidence else ""
            lines.append(f"- {h.text}{conf}")
        lines.append("</scoper_hints>")
        return "\n".join(lines)

    def merge_hints(self, new_hints: HintSet) -> HintSet:
        """Merge new hints into existing ones, avoiding duplicates by hint_id."""
        existing = self.load_hints()
        existing_ids = {h.hint_id for h in existing.hints}

        for h in new_hints.hints:
            if h.hint_id not in existing_ids:
                existing.hints.append(h)
                existing_ids.add(h.hint_id)

        existing.analysis_summary = new_hints.analysis_summary
        existing.generated_at = new_hints.generated_at
        self.save_hints(existing)
        return existing
