"""Tests for FlowRouter (R1+R4: hybrid routing)."""

from __future__ import annotations

import json

from spec_orch.domain.models import FlowType, Issue, IssueContext
from spec_orch.flow_engine.flow_router import FlowRouter, FlowRoutingDecision


def _make_issue(
    *,
    labels: list[str] | None = None,
    run_class: str | None = None,
    title: str = "Test issue",
    summary: str = "A test issue",
) -> Issue:
    return Issue(
        issue_id="TEST-1",
        title=title,
        summary=summary,
        labels=labels or [],
        run_class=run_class,
        context=IssueContext(),
    )


class TestFlowRouterRuleOnly:
    def test_static_rule_resolves_hotfix(self) -> None:
        router = FlowRouter(use_llm_routing=False)
        decision = router.route(_make_issue(labels=["hotfix"]))
        assert decision.recommended_flow == FlowType.HOTFIX
        assert decision.source == "rule"
        assert decision.confidence == 1.0

    def test_static_rule_resolves_feature(self) -> None:
        router = FlowRouter(use_llm_routing=False)
        decision = router.route(_make_issue(run_class="feature"))
        assert decision.recommended_flow == FlowType.FULL
        assert decision.source == "rule"

    def test_fallback_to_standard_when_no_match(self) -> None:
        router = FlowRouter(use_llm_routing=False)
        decision = router.route(_make_issue())
        assert decision.recommended_flow == FlowType.STANDARD
        assert decision.source == "fallback"
        assert decision.confidence == 0.5

    def test_bug_label_resolves_to_standard(self) -> None:
        router = FlowRouter(use_llm_routing=False)
        decision = router.route(_make_issue(run_class="bug"))
        assert decision.recommended_flow == FlowType.STANDARD


class TestFlowRoutingDecision:
    def test_to_event_payload(self) -> None:
        router = FlowRouter()
        decision = FlowRoutingDecision(
            recommended_flow=FlowType.FULL,
            confidence=0.95,
            reasoning="Complex feature",
            source="llm",
            complexity_signals={"estimated_files": 10, "cross_module": True},
        )
        payload = router.to_event_payload(decision)
        assert payload["recommended_flow"] == "full"
        assert payload["confidence"] == 0.95
        assert payload["source"] == "llm"


class TestLLMResponseParsing:
    def test_parse_valid_response(self) -> None:
        raw = json.dumps(
            {
                "recommended_flow": "full",
                "confidence": 0.92,
                "reasoning": "Architecture change detected",
                "complexity_signals": {"estimated_files": 15, "cross_module": True},
            }
        )
        decision = FlowRouter._parse_llm_response(raw)
        assert decision.recommended_flow == FlowType.FULL
        assert decision.confidence == 0.92
        assert decision.source == "llm"

    def test_parse_with_markdown_fences(self) -> None:
        raw = '```json\n{"recommended_flow": "hotfix", "confidence": 0.99, "reasoning": "urgent"}\n```'
        decision = FlowRouter._parse_llm_response(raw)
        assert decision.recommended_flow == FlowType.HOTFIX

    def test_parse_unknown_flow_defaults_to_standard(self) -> None:
        raw = json.dumps({"recommended_flow": "unknown", "confidence": 0.5})
        decision = FlowRouter._parse_llm_response(raw)
        assert decision.recommended_flow == FlowType.STANDARD

    def test_parse_non_json_returns_fallback(self) -> None:
        decision = FlowRouter._parse_llm_response("This is not JSON at all")
        assert decision.recommended_flow == FlowType.STANDARD
        assert decision.source == "fallback"
        assert decision.confidence == 0.0

    def test_parse_non_dict_json_returns_fallback(self) -> None:
        decision = FlowRouter._parse_llm_response('["a", "b"]')
        assert decision.recommended_flow == FlowType.STANDARD
        assert decision.source == "fallback"
        assert decision.confidence == 0.0

    def test_parse_json_null_returns_fallback(self) -> None:
        decision = FlowRouter._parse_llm_response("null")
        assert decision.recommended_flow == FlowType.STANDARD
        assert decision.source == "fallback"
