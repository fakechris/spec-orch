"""LiteLLM-backed acceptance evaluator."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from spec_orch.domain.models import (
    AcceptanceFinding,
    AcceptanceReviewResult,
    BuilderResult,
    WorkPacket,
)

_ACCEPTANCE_SYSTEM_PROMPT = """\
You are the independent Acceptance Evaluator for SpecOrch.
Judge whether the mission output actually meets the intended result.

Return two parts in this order:
1. A short markdown acceptance review
2. A JSON object in a ```json fenced block

The JSON must include:
- status: pass | warn | fail
- summary
- confidence
- evaluator
- tested_routes
- findings
- issue_proposals
- artifacts
"""


class LiteLLMAcceptanceEvaluator:
    ADAPTER_NAME = "litellm_acceptance"

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

    def evaluate_acceptance(
        self,
        *,
        mission_id: str,
        round_id: int,
        round_dir: Path,
        worker_results: list[tuple[WorkPacket, BuilderResult]],
        artifacts: dict[str, Any],
        repo_root: Path,
    ) -> AcceptanceReviewResult:
        prompt = self._build_prompt(
            mission_id=mission_id,
            round_id=round_id,
            round_dir=round_dir,
            worker_results=worker_results,
            artifacts=artifacts,
            repo_root=repo_root,
        )
        raw_output = self._call_model(prompt)
        _, result = self._parse_output(raw_output)
        return result

    def _call_model(self, prompt: str) -> str:
        if self._chat_completion is not None:
            response = self._chat_completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": _ACCEPTANCE_SYSTEM_PROMPT},
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
                "litellm is required for LiteLLMAcceptanceEvaluator. "
                "Install with: pip install spec-orch[planner]"
            ) from exc

        response = litellm.completion(
            model=self.model,
            messages=[
                {"role": "system", "content": _ACCEPTANCE_SYSTEM_PROMPT},
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
        mission_id: str,
        round_id: int,
        round_dir: Path,
        worker_results: list[tuple[WorkPacket, BuilderResult]],
        artifacts: dict[str, Any],
        repo_root: Path,
    ) -> str:
        payload = {
            "mission_id": mission_id,
            "round_id": round_id,
            "round_dir": str(round_dir),
            "repo_root": str(repo_root),
            "worker_results": [
                {
                    "packet_id": packet.packet_id,
                    "title": packet.title,
                    "succeeded": result.succeeded,
                    "report_path": str(result.report_path),
                    "adapter": result.adapter,
                    "agent": result.agent,
                }
                for packet, result in worker_results
            ],
            "artifacts": artifacts,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _parse_output(self, raw_output: str) -> tuple[str, AcceptanceReviewResult]:
        try:
            review_text, json_blob = self._split_review_and_json(raw_output)
            return review_text, AcceptanceReviewResult.from_dict(json.loads(json_blob))
        except Exception:
            fallback = AcceptanceReviewResult(
                status="warn",
                summary="Acceptance evaluator output could not be parsed.",
                confidence=0.0,
                evaluator=self.ADAPTER_NAME,
                findings=[
                    AcceptanceFinding(
                        severity="error",
                        summary="Acceptance evaluator output could not be parsed.",
                    )
                ],
            )
            return raw_output.strip() or "Acceptance evaluator parsing failed.", fallback

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
