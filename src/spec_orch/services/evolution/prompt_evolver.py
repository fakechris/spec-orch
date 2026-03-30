"""Prompt Evolver — versioned builder prompts with A/B testing.

Maintains a history of builder prompt variants and their observed success
rates across runs.  After every N runs the evolver can use an LLM to propose
improved prompt candidates, run them through an A/B framework, and
auto-promote the winning variant.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.domain.models import (
    EvolutionChangeType,
    EvolutionOutcome,
    EvolutionProposal,
    EvolutionValidationMethod,
)
from spec_orch.services.constitutions import EVOLVER_CONSTITUTION, build_role_system_prompt
from spec_orch.services.io import atomic_write_json

logger = logging.getLogger(__name__)

_PROMPT_HISTORY_FILE = "prompt_history.json"
_EVOLVE_SYSTEM_PROMPT = build_role_system_prompt(
    role_intro="You are a prompt-engineering specialist for an AI coding-agent orchestrator.",
    task_summary="""\
Given the current builder prompt and performance statistics from recent runs,
propose an improved prompt variant that addresses observed failure patterns.
""",
    constitution=EVOLVER_CONSTITUTION,
    response_contract="""\
Requirements:
- Keep the same general structure as the current prompt.
- Focus changes on areas that correlate with failures (e.g., narration issues,
  missing constraints, unclear instructions).
- The new prompt must still start with concrete action instructions.
- Explain your reasoning for each change in a brief rationale.

Respond with ONLY a JSON object:
{
  "variant_id": "v<next_number>",
  "prompt_text": "the full improved prompt",
  "rationale": "brief explanation of what changed and why",
  "target_improvements": ["list of expected improvements"]
}
""",
)


@dataclass
class PromptVariant:
    """A single builder prompt variant with performance tracking."""

    variant_id: str
    prompt_text: str
    created_at: str = ""
    rationale: str = ""
    total_runs: int = 0
    successful_runs: int = 0
    is_active: bool = False
    is_candidate: bool = False
    target_improvements: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return self.successful_runs / self.total_runs


@dataclass
class ABTestResult:
    """Result of comparing two prompt variants."""

    winner_id: str
    loser_id: str
    winner_success_rate: float
    loser_success_rate: float
    winner_runs: int
    loser_runs: int
    confidence: str  # "low" | "medium" | "high"


class PromptEvolver:
    """Manages versioned builder prompts and A/B testing."""

    EVOLVER_NAME: str = "prompt_evolver"
    MIN_RUNS_FOR_COMPARISON = 5

    def __init__(self, repo_root: Path, planner: Any | None = None) -> None:
        self._repo_root = repo_root
        self._planner = planner
        self._history_path = repo_root / _PROMPT_HISTORY_FILE

    def load_history(self) -> list[PromptVariant]:
        """Load prompt variant history from disk."""
        if not self._history_path.exists():
            return []

        try:
            data = json.loads(self._history_path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read prompt history at %s", self._history_path)
            return []

        if not isinstance(data, list):
            return []

        variants: list[PromptVariant] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                variants.append(
                    PromptVariant(
                        variant_id=item["variant_id"],
                        prompt_text=item["prompt_text"],
                        created_at=item.get("created_at", ""),
                        rationale=item.get("rationale", ""),
                        total_runs=item.get("total_runs", 0),
                        successful_runs=item.get("successful_runs", 0),
                        is_active=item.get("is_active", False),
                        is_candidate=item.get("is_candidate", False),
                        target_improvements=item.get("target_improvements", []),
                    )
                )
            except (KeyError, TypeError):
                logger.warning("Skipping malformed prompt variant: %s", item)
        return variants

    def save_history(self, variants: list[PromptVariant]) -> None:
        """Persist prompt variant history to disk."""
        data = [asdict(v) for v in variants]
        atomic_write_json(self._history_path, data)

    def get_active_prompt(self) -> PromptVariant | None:
        """Return the currently active prompt variant."""
        for v in self.load_history():
            if v.is_active:
                return v
        return None

    def initialize_from_current(self, prompt_text: str) -> PromptVariant:
        """Bootstrap history with the current builder prompt as v0."""
        history = self.load_history()
        for v in history:
            if v.variant_id == "v0":
                return v

        v0 = PromptVariant(
            variant_id="v0",
            prompt_text=prompt_text,
            created_at=datetime.now(UTC).isoformat(),
            rationale="Initial builder prompt (baseline).",
            is_active=True,
        )
        history.append(v0)
        self.save_history(history)
        return v0

    def record_run(self, variant_id: str, succeeded: bool) -> None:
        """Record a run outcome for a prompt variant."""
        history = self.load_history()
        for v in history:
            if v.variant_id == variant_id:
                v.total_runs += 1
                if succeeded:
                    v.successful_runs += 1
                self.save_history(history)
                return
        logger.warning("Variant %s not found in history", variant_id)

    def _collect_failure_samples(self, max_samples: int = 10) -> list[dict[str, Any]]:
        """Collect recent failure samples bucketed by task type and failure mode."""
        try:
            from spec_orch.services.evidence_analyzer import EvidenceAnalyzer
        except ImportError:
            return []

        analyzer = EvidenceAnalyzer(self._repo_root)
        run_dirs = analyzer.collect_run_dirs()[-20:]
        samples: list[dict[str, Any]] = []

        for rd in run_dirs:
            report = analyzer.read_report(rd)
            if report is None or report.get("mergeable", True):
                continue

            sample: dict[str, Any] = {
                "run_id": rd.name,
                "failed_conditions": report.get("failed_conditions", []),
            }

            metadata = report.get("metadata", {})
            sample["task_type"] = metadata.get("run_class", "unknown")
            sample["adapter"] = metadata.get("builder_adapter", "unknown")

            verification = report.get("verification", {})
            failed_checks = [
                k
                for k, v in verification.items()
                if isinstance(v, dict) and v.get("exit_code", 1) != 0
            ]
            sample["failed_checks"] = failed_checks

            events_path = rd / "telemetry" / "incoming_events.jsonl"
            if not events_path.exists():
                events_path = rd / "builder_events.jsonl"
            if events_path.exists():
                excerpts: list[str] = []
                try:
                    for line in events_path.read_text().splitlines()[-5:]:
                        line = line.strip()
                        if line:
                            try:
                                obj = json.loads(line)
                                text = obj.get("text") or obj.get("excerpt") or ""
                                if text:
                                    excerpts.append(text[:200])
                            except json.JSONDecodeError:
                                continue
                except OSError:
                    pass
                sample["builder_tail"] = excerpts

            samples.append(sample)
            if len(samples) >= max_samples:
                break

        return samples

    def evolve(self, *, context: Any | None = None) -> PromptVariant | None:
        """Use an LLM to propose an improved prompt variant.

        Returns the new candidate variant, or ``None`` if evolution is not
        possible (no planner, no active prompt, or LLM call fails).
        """
        if self._planner is None:
            return None

        history = self.load_history()
        active = None
        for v in history:
            if v.is_active:
                active = v
                break

        if active is None:
            return None

        stats = {
            "active_variant": active.variant_id,
            "success_rate": f"{active.success_rate:.1%}",
            "total_runs": active.total_runs,
            "history": [
                {
                    "variant_id": v.variant_id,
                    "success_rate": f"{v.success_rate:.1%}",
                    "total_runs": v.total_runs,
                    "rationale": v.rationale,
                }
                for v in history
            ],
        }

        failure_samples = self._collect_failure_samples()

        user_msg = (
            "Current active builder prompt:\n"
            f"```\n{active.prompt_text}\n```\n\n"
            "Performance statistics:\n"
            f"```json\n{json.dumps(stats, indent=2)}\n```\n\n"
        )
        if context is not None:
            user_msg += self._render_context_for_prompt(context)
        if failure_samples:
            user_msg += (
                "Recent failure samples (use these to target specific failure patterns):\n"
                f"```json\n{json.dumps(failure_samples, indent=2)}\n```\n\n"
            )
        user_msg += "Propose an improved prompt variant."

        try:
            response = self._planner.brainstorm(
                conversation_history=[
                    {"role": "system", "content": _EVOLVE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                codebase_context="",
            )
        except Exception:
            logger.exception("LLM call failed during prompt evolution")
            return None

        return self._parse_evolve_response(response, history)

    @staticmethod
    def _render_context_for_prompt(context: Any) -> str:
        parts: list[str] = []
        task = getattr(context, "task", None)
        execution = getattr(context, "execution", None)
        learning = getattr(context, "learning", None)

        if task and getattr(task, "constraints", []):
            constraint_lines = "\n".join(f"- {c}" for c in task.constraints)
            parts.append(f"Known constraints:\n{constraint_lines}")
        if execution and getattr(execution, "deviation_slices", []):
            parts.append(
                "Recent deviation slices:\n"
                + json.dumps(execution.deviation_slices[:5], ensure_ascii=False, indent=2)
            )
        if learning and getattr(learning, "similar_failure_samples", []):
            failure_lines: list[str] = [
                f"- {s.get('key', '?')}: {s.get('content', '')[:180]}"
                for s in learning.similar_failure_samples[:3]
            ]
            parts.append("Similar failures:\n" + "\n".join(failure_lines))
        if learning and getattr(learning, "reviewed_decision_failures", []):
            failure_lines = [
                f"- {s.get('record_id', '?')}: {s.get('summary', '')[:180]}"
                for s in learning.reviewed_decision_failures[:3]
            ]
            parts.append("Reviewed decision failures:\n" + "\n".join(failure_lines))
        if learning and getattr(learning, "reviewed_decision_recipes", []):
            recipe_lines = [
                f"- {s.get('record_id', '?')}: {s.get('summary', '')[:180]}"
                for s in learning.reviewed_decision_recipes[:3]
            ]
            parts.append("Reviewed decision recipes:\n" + "\n".join(recipe_lines))
        if learning and getattr(learning, "reviewed_acceptance_findings", []):
            finding_lines = [
                f"- {s.get('finding_id', '?')}: {s.get('summary', '')[:180]}"
                for s in learning.reviewed_acceptance_findings[:3]
            ]
            parts.append("Reviewed acceptance findings:\n" + "\n".join(finding_lines))

        if not parts:
            return ""
        return "ContextBundle evidence:\n" + "\n\n".join(parts) + "\n\n"

    def _parse_evolve_response(
        self, response: Any, history: list[PromptVariant]
    ) -> PromptVariant | None:
        if not isinstance(response, str):
            logger.warning("Non-string LLM response: %s", type(response).__name__)
            return None

        text = response.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            logger.warning("Could not find JSON object in evolve response")
            return None

        try:
            obj = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from evolve response")
            return None

        if not isinstance(obj, dict) or "prompt_text" not in obj:
            return None

        next_num = len(history)
        variant_id = obj.get("variant_id", f"v{next_num}")

        existing_ids = {v.variant_id for v in history}
        if variant_id in existing_ids:
            variant_id = f"v{next_num}"

        new_variant = PromptVariant(
            variant_id=variant_id,
            prompt_text=obj["prompt_text"],
            created_at=datetime.now(UTC).isoformat(),
            rationale=obj.get("rationale", ""),
            is_candidate=True,
            target_improvements=obj.get("target_improvements", []),
        )

        history.append(new_variant)
        self.save_history(history)
        return new_variant

    def compare_variants(self, variant_a_id: str, variant_b_id: str) -> ABTestResult | None:
        """Compare two variants' performance and determine the winner."""
        history = self.load_history()
        va = vb = None
        for v in history:
            if v.variant_id == variant_a_id:
                va = v
            elif v.variant_id == variant_b_id:
                vb = v

        if va is None or vb is None:
            return None

        if va.total_runs < self.MIN_RUNS_FOR_COMPARISON:
            return None
        if vb.total_runs < self.MIN_RUNS_FOR_COMPARISON:
            return None

        total_runs = va.total_runs + vb.total_runs
        if total_runs < 20:
            confidence = "low"
        elif total_runs < 50:
            confidence = "medium"
        else:
            confidence = "high"

        if va.success_rate >= vb.success_rate:
            winner, loser = va, vb
        else:
            winner, loser = vb, va

        return ABTestResult(
            winner_id=winner.variant_id,
            loser_id=loser.variant_id,
            winner_success_rate=winner.success_rate,
            loser_success_rate=loser.success_rate,
            winner_runs=winner.total_runs,
            loser_runs=loser.total_runs,
            confidence=confidence,
        )

    def promote_variant(self, variant_id: str) -> bool:
        """Promote a variant to active, deactivating the current active."""
        history = self.load_history()
        target = None
        for v in history:
            if v.variant_id == variant_id:
                target = v

        if target is None:
            return False

        for v in history:
            v.is_active = v.variant_id == variant_id
            if v.variant_id == variant_id:
                v.is_candidate = False

        self.save_history(history)
        return True

    def auto_promote_if_ready(self) -> ABTestResult | None:
        """If a candidate has enough runs, compare with active and auto-promote.

        Returns the ABTestResult if promotion happened, else ``None``.
        """
        history = self.load_history()
        active = None
        candidate = None
        for v in history:
            if v.is_active:
                active = v
            if v.is_candidate and v.total_runs >= self.MIN_RUNS_FOR_COMPARISON:
                candidate = v

        if active is None or candidate is None:
            return None

        result = self.compare_variants(active.variant_id, candidate.variant_id)
        if result is None:
            return None

        if result.winner_id == candidate.variant_id:
            self.promote_variant(candidate.variant_id)
            logger.info(
                "Auto-promoted %s (%.1f%%) over %s (%.1f%%)",
                candidate.variant_id,
                candidate.success_rate * 100,
                active.variant_id,
                active.success_rate * 100,
            )

        return result

    # ------------------------------------------------------------------
    # LifecycleEvolver protocol
    # ------------------------------------------------------------------

    def observe(
        self,
        run_dirs: list[Path],
        *,
        context: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Collect evidence from recent run directories."""
        return self._collect_failure_samples()

    def propose(
        self,
        evidence: list[dict[str, Any]],
        *,
        context: Any | None = None,
    ) -> list[EvolutionProposal]:
        """Generate prompt variant proposals from evidence."""
        variant = self.evolve(context=context)
        if variant is None:
            return []
        return [
            EvolutionProposal(
                proposal_id=f"prompt-{uuid.uuid4().hex[:8]}",
                evolver_name=self.EVOLVER_NAME,
                change_type=EvolutionChangeType.PROMPT_VARIANT,
                content={
                    "variant_id": variant.variant_id,
                    "prompt_text": variant.prompt_text,
                    "rationale": variant.rationale,
                },
                evidence=evidence,
                confidence=0.5,
            )
        ]

    def validate(self, proposal: EvolutionProposal) -> EvolutionOutcome:
        """Rule-based validation: accept if confidence >= 0.5."""
        accepted = proposal.confidence >= 0.5
        return EvolutionOutcome(
            proposal_id=proposal.proposal_id,
            accepted=accepted,
            validation_method=EvolutionValidationMethod.RULE_VALIDATOR,
            metrics={"confidence": proposal.confidence},
            reason="confidence >= 0.5" if accepted else "confidence < 0.5",
        )

    def promote(self, proposal: EvolutionProposal) -> bool:
        """Apply a validated proposal by promoting the variant."""
        variant_id = proposal.content.get("variant_id", "")
        return self.promote_variant(variant_id)
