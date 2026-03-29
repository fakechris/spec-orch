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
        result = self._apply_campaign_defaults(result, campaign=campaign)
        return self._synthesize_exploratory_gap_candidates(
            result,
            artifacts=artifacts,
            campaign=campaign,
        )

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
        normalized_tested_routes = list(result.tested_routes)
        if not normalized_tested_routes and isinstance(browser_evidence, dict):
            normalized_tested_routes = [
                LiteLLMAcceptanceEvaluator._clean_text(route)
                for route in browser_evidence.get("tested_routes", [])
                if LiteLLMAcceptanceEvaluator._clean_text(route)
            ]
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
        normalized_artifacts = dict(result.artifacts) if isinstance(result.artifacts, dict) else {}
        for key in ("proof_split", "fresh_execution", "workflow_replay"):
            value = artifacts.get(key)
            if value is not None and key not in normalized_artifacts:
                normalized_artifacts[key] = value
        return replace(
            result,
            tested_routes=normalized_tested_routes,
            findings=findings,
            issue_proposals=issue_proposals,
            artifacts=normalized_artifacts,
        )

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
            acceptance_mode=campaign.mode.value,
            coverage_status=coverage_status,
            untested_expected_routes=untested_expected_routes,
            recommended_next_step=recommended_next_step,
            campaign=campaign,
        )

    @staticmethod
    def _synthesize_exploratory_gap_candidates(
        result: AcceptanceReviewResult,
        *,
        artifacts: dict[str, Any],
        campaign: AcceptanceCampaign | None,
    ) -> AcceptanceReviewResult:
        if campaign is None or campaign.mode.value != "exploratory":
            return result

        browser_evidence = artifacts.get("browser_evidence", {})
        if not isinstance(browser_evidence, dict):
            return result
        interactions = browser_evidence.get("interactions", {})
        if not isinstance(interactions, dict):
            return result

        transcript_route = next(
            (
                route
                for route in result.tested_routes
                if isinstance(route, str) and "tab=transcript" in route
            ),
            "",
        )
        if not transcript_route:
            return result
        route_interactions = interactions.get(transcript_route, [])
        if not isinstance(route_interactions, list) or not route_interactions:
            return result

        def _saw_success(target_fragment: str) -> bool:
            for entry in route_interactions:
                if not isinstance(entry, dict):
                    continue
                if entry.get("status") != "passed":
                    continue
                target = LiteLLMAcceptanceEvaluator._clean_text(entry.get("target"))
                if target_fragment in target:
                    return True
            return False

        saw_filter = _saw_success('data-automation-target="transcript-filter"')
        saw_packet = _saw_success('data-automation-target="packet-row"')
        saw_block = _saw_success('data-automation-target="transcript-block"')
        round_summary = artifacts.get("round_summary", {})
        retry_action = ""
        retry_reason_code = ""
        if isinstance(round_summary, dict):
            decision = round_summary.get("decision", {})
            if isinstance(decision, dict):
                retry_action = LiteLLMAcceptanceEvaluator._clean_text(decision.get("action"))
                retry_reason_code = LiteLLMAcceptanceEvaluator._clean_text(
                    decision.get("reason_code")
                )
        if (
            not saw_filter
            and not result.findings
            and not result.issue_proposals
            and "did not clear the critique threshold" not in result.summary.lower()
        ):
            summary = result.summary.rstrip()
            if summary:
                summary = (
                    f"{summary} Available exploratory evidence did not clear the critique "
                    "threshold because replay did not advance beyond transcript entry controls."
                )
            else:
                summary = (
                    "Available exploratory evidence did not clear the critique threshold because "
                    "replay did not advance beyond transcript entry controls."
                )
            recommended_next_step = result.recommended_next_step or (
                "Capture one deeper transcript interaction before promoting a UX critique."
            )
            return replace(
                result,
                summary=summary,
                recommended_next_step=recommended_next_step,
            )

        def _is_retry_backed_transcript_empty_state() -> bool:
            if retry_action != "retry" or not retry_reason_code:
                return False
            if not saw_filter or saw_packet or saw_block:
                return False
            return any(
                isinstance(entry, dict)
                and LiteLLMAcceptanceEvaluator._clean_text(entry.get("target"))
                == '[data-automation-target="packet-row"]'
                and LiteLLMAcceptanceEvaluator._clean_text(entry.get("status")) == "failed"
                for entry in route_interactions
            )

        if not saw_filter or (saw_packet and saw_block):
            return result

        def _is_low_signal_transcript_finding(finding: AcceptanceFinding) -> bool:
            summary = LiteLLMAcceptanceEvaluator._clean_text(finding.summary)
            return finding.route == transcript_route and summary.startswith(
                "Browser page error on "
            )

        def _is_low_signal_transcript_proposal(proposal: AcceptanceIssueProposal) -> bool:
            route = LiteLLMAcceptanceEvaluator._clean_text(proposal.route)
            title = LiteLLMAcceptanceEvaluator._clean_text(proposal.title)
            summary = LiteLLMAcceptanceEvaluator._clean_text(proposal.summary)
            expected = LiteLLMAcceptanceEvaluator._clean_text(proposal.expected)
            actual = LiteLLMAcceptanceEvaluator._clean_text(proposal.actual)
            critique_axis = LiteLLMAcceptanceEvaluator._clean_text(proposal.critique_axis)
            operator_task = LiteLLMAcceptanceEvaluator._clean_text(proposal.operator_task)
            why_it_matters = LiteLLMAcceptanceEvaluator._clean_text(proposal.why_it_matters)
            hold_reason = LiteLLMAcceptanceEvaluator._clean_text(proposal.hold_reason)
            repro_steps = [
                step
                for step in proposal.repro_steps
                if LiteLLMAcceptanceEvaluator._clean_text(step)
            ]
            if not route and not expected and not actual and not repro_steps:
                return True
            missing_critique_metadata = not any(
                [critique_axis, operator_task, why_it_matters, hold_reason]
            )
            return (
                route == transcript_route
                and missing_critique_metadata
                and (
                    (
                        title.startswith("Investigate browser page error on ")
                        and "browser page error" in f"{title} {summary}".lower()
                    )
                    or (
                        "transcript surface empty" in title.lower() and "browser" in summary.lower()
                    )
                )
            )

        def _is_low_signal_retry_backed_proposal(proposal: AcceptanceIssueProposal) -> bool:
            route = LiteLLMAcceptanceEvaluator._clean_text(proposal.route)
            title = LiteLLMAcceptanceEvaluator._clean_text(proposal.title).lower()
            summary = LiteLLMAcceptanceEvaluator._clean_text(proposal.summary).lower()
            critique_axis = LiteLLMAcceptanceEvaluator._clean_text(proposal.critique_axis)
            operator_task = LiteLLMAcceptanceEvaluator._clean_text(proposal.operator_task)
            why_it_matters = LiteLLMAcceptanceEvaluator._clean_text(proposal.why_it_matters)
            hold_reason = LiteLLMAcceptanceEvaluator._clean_text(proposal.hold_reason)
            missing_critique_metadata = not any(
                [critique_axis, operator_task, why_it_matters, hold_reason]
            )
            return (
                route == transcript_route
                and missing_critique_metadata
                and "empty state" in title
                and ("signal cause" in title or "operator" in title or "browser" in summary)
            )

        if _is_retry_backed_transcript_empty_state():
            low_signal_findings = all(
                _is_low_signal_transcript_finding(finding) for finding in result.findings
            )
            low_signal_proposals = all(
                _is_low_signal_retry_backed_proposal(proposal)
                or _is_low_signal_transcript_proposal(proposal)
                for proposal in result.issue_proposals
            )
            can_replace_existing = (not result.findings or low_signal_findings) and (
                not result.issue_proposals or low_signal_proposals
            )
            if can_replace_existing:
                finding = AcceptanceFinding(
                    severity="held",
                    summary="Transcript empty state hides the retry cause",
                    details=(
                        "Exploratory replay reached the transcript surface after a retry decision, "
                        f"but the empty state did not explain that round evidence is unavailable "
                        f"because the mission is currently marked {retry_reason_code}."
                    ),
                    expected=(
                        "When transcript evidence is unavailable because a round was retried, the "
                        "surface should explain the retry cause and point the operator to the next "
                        "review surface."
                    ),
                    actual=(
                        "The operator sees no packet rows and must infer from surrounding context "
                        "why transcript evidence is missing."
                    ),
                    route=transcript_route,
                    critique_axis="task_continuity",
                    operator_task=(
                        "understand why transcript evidence is unavailable and what to review next"
                    ),
                    why_it_matters=(
                        "Without the retry cause in the empty state, operators can mistake missing "
                        "evidence for a dashboard failure and lose review continuity."
                    ),
                )
                proposal = AcceptanceIssueProposal(
                    title="Explain retry-backed transcript empty states",
                    summary=(
                        "Exploratory acceptance indicates the transcript empty state should "
                        "explain "
                        f"that the round was retried for {retry_reason_code} and direct the "
                        "operator back to the relevant decision or acceptance context."
                    ),
                    severity="medium",
                    confidence=max(result.confidence, 0.82),
                    repro_steps=[
                        "Open the transcript tab for a mission with a retried round.",
                        "Try to determine why transcript evidence is unavailable from the "
                        "transcript surface alone.",
                    ],
                    expected=(
                        "The transcript empty state names the retry cause and suggests where the "
                        "operator should continue review."
                    ),
                    actual=(
                        "The surface only appears empty, so the operator must reconstruct the "
                        "retry reason from other panes."
                    ),
                    route=transcript_route,
                    critique_axis="task_continuity",
                    operator_task=(
                        "understand why transcript evidence is unavailable and what to review next"
                    ),
                    why_it_matters=(
                        "Operators should not have to reverse-engineer retry state before deciding "
                        "which surface to inspect next."
                    ),
                    hold_reason=(
                        "Exploratory UX critique should be reviewed before automatic filing."
                    ),
                )
                summary = (
                    "Operator navigation remains usable, but the transcript empty state does not "
                    f"explain that evidence is missing because round 1 was retried for "
                    f"{retry_reason_code}. A first-time operator can reach the surface but not "
                    "understand what happened or where to continue review."
                )
                recommended_next_step = result.recommended_next_step or (
                    "Hold the transcript continuity critique for operator review before "
                    "auto-filing."
                )
                return replace(
                    result,
                    status="warn",
                    summary=summary,
                    findings=[finding],
                    issue_proposals=[proposal],
                    recommended_next_step=recommended_next_step,
                )

        low_signal_findings = all(
            _is_low_signal_transcript_finding(finding) for finding in result.findings
        )
        low_signal_proposals = all(
            _is_low_signal_transcript_proposal(proposal) for proposal in result.issue_proposals
        )
        can_replace_existing = (not result.findings or low_signal_findings) and (
            not result.issue_proposals or low_signal_proposals
        )
        if not can_replace_existing:
            return result

        finding = AcceptanceFinding(
            severity="high",
            summary="Transcript evidence entry is hard to discover",
            details=(
                "Exploratory replay reached the transcript surface, but the operator path "
                "did not progress into packet-level transcript evidence within the bounded budget."
            ),
            expected=(
                "A first-time operator can discover how to open packet-level transcript evidence "
                "from the transcript tab without prior guidance."
            ),
            actual=(
                "Replay could use the transcript filter, but packet selection and transcript-block "
                "inspection did not both succeed."
            ),
            route=transcript_route,
            critique_axis="evidence_discoverability",
            operator_task="open packet-level transcript evidence",
            why_it_matters=(
                "Operators can stall before reaching the most important evidence for a mission."
            ),
        )
        proposal = AcceptanceIssueProposal(
            title="Clarify transcript packet selection entry point",
            summary=(
                "Exploratory acceptance indicates the transcript surface needs a clearer "
                "empty-state or packet-selection affordance so operators do not stall before "
                "reaching concrete evidence."
            ),
            severity="high",
            confidence=max(result.confidence, 0.82),
            repro_steps=[
                "Open the transcript tab for a mission.",
                "Attempt to move from the transcript surface into packet-level evidence.",
            ],
            expected=(
                "Packet selection and transcript evidence entry feel obvious without prior context."
            ),
            actual=(
                "The bounded exploratory pass reached transcript filters but did not reliably "
                "advance into packet-level evidence."
            ),
            route=transcript_route,
            critique_axis="evidence_discoverability",
            operator_task="open packet-level transcript evidence",
            why_it_matters=(
                "Operators should reach packet evidence without relying on prior dashboard context."
            ),
            hold_reason="Exploratory UX critique should be reviewed before automatic filing.",
        )
        summary = (
            "Navigation surfaces are functional, but transcript packet selection is not "
            "self-evident for a first-time operator. Exploratory replay reached transcript "
            "filters yet did not reliably progress into packet-level evidence within the bounded "
            "budget."
        )

        recommended_next_step = result.recommended_next_step or (
            "Hold the transcript discoverability critique for operator review before auto-filing."
        )

        return replace(
            result,
            status="warn",
            summary=summary,
            findings=[finding],
            issue_proposals=[proposal],
            recommended_next_step=recommended_next_step,
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
