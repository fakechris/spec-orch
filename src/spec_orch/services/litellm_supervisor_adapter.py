"""LiteLLM-backed supervisor adapter for mission round review."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from spec_orch.domain.models import (
    ExecutionPlan,
    RoundAction,
    RoundArtifacts,
    RoundDecision,
    RoundSummary,
)
from spec_orch.services.io import atomic_write_json, atomic_write_text

_SUPERVISOR_SYSTEM_PROMPT = """\
You are Mission Supervisor for SpecOrch.
Review one mission round and decide the next orchestration action.

Return two parts in this order:
1. A short markdown review
2. A JSON object in a ```json fenced block

The JSON must include:
- action: continue | retry | replan_remaining | ask_human | stop
- reason_code
- summary
- confidence
"""


class LiteLLMSupervisorAdapter:
    ADAPTER_NAME = "litellm"

    def __init__(
        self,
        *,
        repo_root: Path,
        model: str,
        api_key: str | None = None,
        api_base: str | None = None,
        temperature: float = 0.1,
        chat_completion: Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.model = model
        self.api_key = api_key or os.environ.get("SPEC_ORCH_LLM_API_KEY")
        self.api_base = api_base or os.environ.get("SPEC_ORCH_LLM_API_BASE")
        self.temperature = temperature
        self._chat_completion = chat_completion

    def review_round(
        self,
        *,
        round_artifacts: RoundArtifacts,
        plan: ExecutionPlan,
        round_history: list[RoundSummary],
        context: Any | None = None,
    ) -> RoundDecision:
        prompt = self._build_prompt(
            round_artifacts=round_artifacts,
            plan=plan,
            round_history=round_history,
            context=context,
        )
        raw_output = self._call_model(prompt)
        review_text, decision = self._parse_output(raw_output)

        round_dir = self._round_dir(round_artifacts.mission_id, round_artifacts.round_id)
        atomic_write_text(round_dir / "supervisor_review.md", review_text)
        atomic_write_json(round_dir / "round_decision.json", decision.to_dict())
        return decision

    def _call_model(self, prompt: str) -> str:
        if self._chat_completion is not None:
            response = self._chat_completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SUPERVISOR_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                api_key=self.api_key,
                api_base=self.api_base,
            )
            return self._extract_text(response)

        try:
            import litellm
        except ImportError as exc:
            raise ImportError(
                "litellm is required for LiteLLMSupervisorAdapter. "
                "Install with: pip install spec-orch[planner]"
            ) from exc

        response = litellm.completion(
            model=self.model,
            messages=[
                {"role": "system", "content": _SUPERVISOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
            api_key=self.api_key,
            api_base=self.api_base,
        )
        return self._extract_text(response)

    def _build_prompt(
        self,
        *,
        round_artifacts: RoundArtifacts,
        plan: ExecutionPlan,
        round_history: list[RoundSummary],
        context: Any | None,
    ) -> str:
        payload = {
            "plan_id": plan.plan_id,
            "mission_id": plan.mission_id,
            "round_artifacts": {
                "round_id": round_artifacts.round_id,
                "mission_id": round_artifacts.mission_id,
                "builder_reports": round_artifacts.builder_reports,
                "verification_outputs": round_artifacts.verification_outputs,
                "gate_verdicts": round_artifacts.gate_verdicts,
                "manifest_paths": round_artifacts.manifest_paths,
                "diff_summary": round_artifacts.diff_summary,
                "worker_session_ids": round_artifacts.worker_session_ids,
            },
            "round_history": [summary.to_dict() for summary in round_history],
            "context": context,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _parse_output(self, raw_output: str) -> tuple[str, RoundDecision]:
        try:
            review_text, json_blob = self._split_review_and_json(raw_output)
            return review_text, RoundDecision.from_dict(json.loads(json_blob))
        except Exception:
            fallback = RoundDecision(
                action=RoundAction.ASK_HUMAN,
                reason_code="parse_error",
                summary="Supervisor output could not be parsed.",
                confidence=0.0,
                blocking_questions=["Review the supervisor output and decide the next action."],
            )
            return raw_output.strip() or "Supervisor output parsing failed.", fallback

    @staticmethod
    def _split_review_and_json(raw_output: str) -> tuple[str, str]:
        match = re.search(r"```json\s*(\{.*\})\s*```", raw_output, flags=re.DOTALL)
        if match:
            json_blob = match.group(1)
            review = raw_output[: match.start()].strip()
            return review, json_blob
        stripped = raw_output.strip()
        return "", stripped

    @staticmethod
    def _extract_text(response: Any) -> str:
        if isinstance(response, str):
            return response
        choices = getattr(response, "choices", None)
        if choices:
            message = getattr(choices[0], "message", None)
            if message is not None:
                content = getattr(message, "content", "")
                if isinstance(content, str):
                    return content
        raise ValueError("Unsupported chat completion response format")

    def _round_dir(self, mission_id: str, round_id: int) -> Path:
        return self.repo_root / "docs" / "specs" / mission_id / "rounds" / f"round-{round_id:02d}"
