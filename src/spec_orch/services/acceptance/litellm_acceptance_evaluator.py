"""LiteLLM-backed acceptance evaluator."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from spec_orch.domain.models import (
    AcceptanceCampaign,
    AcceptanceFinding,
    AcceptanceReviewResult,
    BuilderResult,
    WorkPacket,
)
from spec_orch.services.acceptance.prompt_composer import compose_acceptance_prompt
from spec_orch.services.litellm_profile import (
    normalize_litellm_model,
    resolve_litellm_api_base,
    resolve_litellm_api_key,
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
    VALID_API_TYPES = ("anthropic", "openai")

    def __init__(
        self,
        *,
        repo_root: Path,
        model: str,
        api_type: str = "anthropic",
        api_key: str | None = None,
        api_base: str | None = None,
        temperature: float = 0.1,
        chat_completion: Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        if api_type not in self.VALID_API_TYPES:
            raise ValueError(f"api_type must be one of {self.VALID_API_TYPES}, got {api_type!r}")
        self.api_type = api_type
        self.model = normalize_litellm_model(model, api_type=api_type)
        self.api_key = resolve_litellm_api_key(api_key=api_key, api_type=api_type)
        self.api_base = resolve_litellm_api_base(api_base=api_base, api_type=api_type)
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
        campaign: AcceptanceCampaign | None = None,
    ) -> AcceptanceReviewResult:
        prompt = compose_acceptance_prompt(
            mission_id=mission_id,
            round_id=round_id,
            round_dir=round_dir,
            worker_results=worker_results,
            artifacts=artifacts,
            repo_root=repo_root,
            campaign=campaign,
        )
        raw_output = self._call_model(prompt)
        _, result = self._parse_output(raw_output)
        return self._apply_campaign_defaults(result, campaign=campaign)

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

    def _parse_output(self, raw_output: str) -> tuple[str, AcceptanceReviewResult]:
        try:
            review_text, json_blob = self._split_review_and_json(raw_output)
            payload = json.loads(json_blob)
            if not isinstance(payload, dict) or not payload.get("status"):
                raise ValueError("Acceptance evaluator JSON payload missing required status")
            return review_text, AcceptanceReviewResult.from_dict(payload)
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
    def _apply_campaign_defaults(
        result: AcceptanceReviewResult,
        *,
        campaign: AcceptanceCampaign | None,
    ) -> AcceptanceReviewResult:
        if campaign is None:
            return result

        tested_routes = list(result.tested_routes)
        expected_routes = list(dict.fromkeys(campaign.primary_routes + campaign.related_routes))
        if result.coverage_status:
            coverage_status = result.coverage_status
        elif not expected_routes:
            coverage_status = "unscoped"
        elif all(route in tested_routes for route in expected_routes):
            coverage_status = "complete"
        elif any(route in tested_routes for route in expected_routes):
            coverage_status = "partial"
        else:
            coverage_status = "missing"

        untested_expected_routes = (
            list(result.untested_expected_routes)
            if result.untested_expected_routes
            else [route for route in expected_routes if route not in tested_routes]
        )
        recommended_next_step = result.recommended_next_step
        if not recommended_next_step and untested_expected_routes:
            recommended_next_step = "Expand route coverage before filing lower-confidence findings."

        return replace(
            result,
            acceptance_mode=result.acceptance_mode or campaign.mode.value,
            coverage_status=coverage_status,
            untested_expected_routes=untested_expected_routes,
            recommended_next_step=recommended_next_step,
            campaign=result.campaign or campaign,
        )

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
