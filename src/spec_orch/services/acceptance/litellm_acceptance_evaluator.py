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
    AcceptanceIssueProposal,
    AcceptanceReviewResult,
    BuilderResult,
    WorkPacket,
)
from spec_orch.services.acceptance.prompt_composer import compose_acceptance_prompt
from spec_orch.services.constitutions import (
    ACCEPTANCE_EVALUATOR_CONSTITUTION,
    build_role_system_prompt,
)
from spec_orch.services.litellm_profile import (
    normalize_litellm_model,
    resolve_litellm_api_base,
    resolve_litellm_api_key,
)

_ACCEPTANCE_SYSTEM_PROMPT = build_role_system_prompt(
    role_intro="You are the independent Acceptance Evaluator for SpecOrch.",
    task_summary="Judge whether the mission output actually meets the intended result.",
    constitution=ACCEPTANCE_EVALUATOR_CONSTITUTION,
    response_contract="""\
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
""",
)


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
        result = self._normalize_result(result, artifacts=artifacts)
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
    def _normalize_result(
        result: AcceptanceReviewResult,
        *,
        artifacts: dict[str, Any],
    ) -> AcceptanceReviewResult:
        browser_evidence = artifacts.get("browser_evidence", {})
        page_errors_by_route = LiteLLMAcceptanceEvaluator._page_errors_by_route(browser_evidence)
        fallback_route = LiteLLMAcceptanceEvaluator._fallback_route(result, browser_evidence)

        findings: list[AcceptanceFinding] = []
        for finding in result.findings:
            normalized_finding = LiteLLMAcceptanceEvaluator._normalize_finding(
                finding,
                fallback_route=fallback_route,
                page_errors_by_route=page_errors_by_route,
            )
            if normalized_finding is not None:
                findings.append(normalized_finding)
        issue_proposals: list[AcceptanceIssueProposal] = []
        for proposal in result.issue_proposals:
            normalized_proposal = LiteLLMAcceptanceEvaluator._normalize_issue_proposal(
                proposal,
                fallback_route=fallback_route,
                page_errors_by_route=page_errors_by_route,
            )
            if normalized_proposal is not None:
                issue_proposals.append(normalized_proposal)
        return replace(result, findings=findings, issue_proposals=issue_proposals)

    @staticmethod
    def _page_errors_by_route(browser_evidence: Any) -> dict[str, list[str]]:
        if not isinstance(browser_evidence, dict):
            return {}
        grouped: dict[str, list[str]] = {}
        for entry in browser_evidence.get("page_errors", []):
            if not isinstance(entry, dict):
                continue
            route = str(entry.get("path", "")).strip()
            message = str(entry.get("message", "")).strip()
            if not route or not message:
                continue
            grouped.setdefault(route, []).append(message)
        return grouped

    @staticmethod
    def _fallback_route(result: AcceptanceReviewResult, browser_evidence: Any) -> str:
        routes: list[str] = []
        for route in result.tested_routes:
            cleaned = LiteLLMAcceptanceEvaluator._clean_text(route)
            if cleaned and cleaned not in routes:
                routes.append(cleaned)
        if isinstance(browser_evidence, dict):
            for route in browser_evidence.get("tested_routes", []):
                cleaned = LiteLLMAcceptanceEvaluator._clean_text(route)
                if cleaned and cleaned not in routes:
                    routes.append(cleaned)
        return routes[0] if len(routes) == 1 else ""

    @staticmethod
    def _clean_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _normalize_finding(
        finding: AcceptanceFinding,
        *,
        fallback_route: str,
        page_errors_by_route: dict[str, list[str]],
    ) -> AcceptanceFinding | None:
        route = LiteLLMAcceptanceEvaluator._clean_text(finding.route) or fallback_route
        page_error = LiteLLMAcceptanceEvaluator._page_error_message(route, page_errors_by_route)
        summary = LiteLLMAcceptanceEvaluator._clean_text(finding.summary)
        details = LiteLLMAcceptanceEvaluator._clean_text(finding.details)
        expected = LiteLLMAcceptanceEvaluator._clean_text(finding.expected)
        actual = LiteLLMAcceptanceEvaluator._clean_text(finding.actual)
        has_supporting_signal = any(
            [
                page_error,
                summary,
                details,
                expected,
                actual,
                bool(finding.artifact_paths),
            ]
        )

        if not has_supporting_signal:
            return None

        if page_error:
            summary = summary or f"Browser page error on {route or 'tested route'}"
            expected = expected or "Route should render without browser page errors."
            actual = actual or f"Page error observed: {page_error}"
            details = details or f"Browser evidence recorded a page error on {route}: {page_error}"
        else:
            summary = summary or f"Acceptance finding on {route or 'tested route'}"
            details = details or actual or expected or summary

        return replace(
            finding,
            summary=summary,
            details=details,
            expected=expected,
            actual=actual,
            route=route,
        )

    @staticmethod
    def _normalize_issue_proposal(
        proposal: AcceptanceIssueProposal,
        *,
        fallback_route: str,
        page_errors_by_route: dict[str, list[str]],
    ) -> AcceptanceIssueProposal | None:
        route = LiteLLMAcceptanceEvaluator._clean_text(proposal.route) or fallback_route
        page_error = LiteLLMAcceptanceEvaluator._page_error_message(route, page_errors_by_route)
        title = LiteLLMAcceptanceEvaluator._clean_text(proposal.title)
        summary = LiteLLMAcceptanceEvaluator._clean_text(proposal.summary)
        expected = LiteLLMAcceptanceEvaluator._clean_text(proposal.expected)
        actual = LiteLLMAcceptanceEvaluator._clean_text(proposal.actual)
        has_supporting_signal = any(
            [
                page_error,
                title,
                summary,
                expected,
                actual,
                bool(proposal.repro_steps),
                bool(proposal.artifact_paths),
            ]
        )

        if not has_supporting_signal:
            return None

        if page_error:
            title = title or f"Investigate browser page error on {route or 'tested route'}"
            summary = summary or f"Browser evidence recorded a page error on {route}: {page_error}."
            expected = expected or "Route should render without browser page errors."
            actual = actual or f"Page error observed: {page_error}"
        else:
            title = title or f"Investigate acceptance issue on {route or 'tested route'}"
            summary = summary or actual or expected or title

        return replace(
            proposal,
            title=title,
            summary=summary,
            expected=expected,
            actual=actual,
            route=route,
        )

    @staticmethod
    def _page_error_message(route: str, page_errors_by_route: dict[str, list[str]]) -> str:
        errors = page_errors_by_route.get(route, [])
        return errors[0] if errors else ""

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
