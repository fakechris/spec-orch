"""FlowRouter — hybrid rule + LLM routing for flow type selection.

When use_llm_routing is enabled and the static FlowMapper cannot resolve
a definitive flow type, the FlowRouter calls an LLM to evaluate:
  1. Issue complexity (files involved, cross-module, architecture changes)
  2. Historical success rates per flow type (from EvidenceAnalyzer)
  3. Recommended FlowType with confidence + reasoning

Low-confidence results (< threshold) fall back to the static mapper default.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

from spec_orch.domain.models import FlowType, Issue
from spec_orch.flow_engine.mapper import FlowMapper
from spec_orch.services.evidence_analyzer import EvidenceAnalyzer

logger = logging.getLogger(__name__)

_ROUTING_PROMPT = """\
You are a flow routing assistant for a software development pipeline.
Given an issue and historical evidence, recommend the best workflow tier:

- **full**: Feature/architecture changes. Full plan-scope-build-verify-review-gate.
- **standard**: For bug fixes, improvements, documentation. Streamlined build → verify → gate.
- **hotfix**: For urgent/security fixes. Minimal overhead, fast path.

Analyze the issue and evidence, then respond with a JSON object:
{
  "recommended_flow": "full" | "standard" | "hotfix",
  "confidence": 0.0-1.0,
  "reasoning": "one sentence explanation",
  "complexity_signals": {
    "estimated_files": <int>,
    "cross_module": <bool>,
    "architecture_change": <bool>
  }
}
Respond ONLY with the JSON object.\
"""


@dataclass(frozen=True)
class FlowRoutingDecision:
    """Result of a flow routing evaluation."""

    recommended_flow: FlowType
    confidence: float
    reasoning: str
    source: str  # "rule" | "llm" | "fallback"
    complexity_signals: dict[str, Any] | None = None


class FlowRouter:
    """Hybrid router: static rules first, LLM analysis on ambiguous cases."""

    def __init__(
        self,
        *,
        mapper: FlowMapper | None = None,
        evidence_analyzer: EvidenceAnalyzer | None = None,
        llm_model: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        confidence_threshold: float = 0.7,
        use_llm_routing: bool = False,
    ) -> None:
        self._mapper = mapper or FlowMapper()
        self._evidence = evidence_analyzer
        self._llm_model = llm_model or "anthropic/claude-sonnet-4-20250514"
        self._api_key = api_key
        self._api_base = api_base
        self._confidence_threshold = confidence_threshold
        self._use_llm_routing = use_llm_routing

    def route(self, issue: Issue) -> FlowRoutingDecision:
        """Determine optimal flow type for an issue."""
        rule_result = self._mapper.resolve_flow_type(
            issue.run_class,
            labels=issue.labels,
        )

        if rule_result is not None and not self._use_llm_routing:
            return FlowRoutingDecision(
                recommended_flow=rule_result,
                confidence=1.0,
                reasoning=f"Static rule: labels={issue.labels}, run_class={issue.run_class}",
                source="rule",
            )

        if self._use_llm_routing:
            try:
                llm_decision = self._route_via_llm(issue)
                if llm_decision.confidence >= self._confidence_threshold:
                    return llm_decision
                logger.info(
                    "LLM routing confidence %.2f < %.2f, falling back to rule",
                    llm_decision.confidence,
                    self._confidence_threshold,
                )
            except Exception:
                logger.warning("LLM routing failed, falling back to rule", exc_info=True)

        fallback_flow = rule_result or FlowType.STANDARD
        return FlowRoutingDecision(
            recommended_flow=fallback_flow,
            confidence=0.5,
            reasoning="Fallback to default (no confident routing available)",
            source="fallback",
        )

    def _route_via_llm(self, issue: Issue) -> FlowRoutingDecision:
        """Call LLM to evaluate issue complexity and recommend flow."""
        import litellm

        history = self._get_history_context()
        user_message = self._build_routing_prompt(issue, history)

        kwargs: dict[str, Any] = {
            "model": self._llm_model,
            "messages": [
                {"role": "system", "content": _ROUTING_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.1,
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._api_base:
            kwargs["api_base"] = self._api_base

        response = litellm.completion(**kwargs)
        if not response.choices:
            raise ValueError("LLM returned empty choices")
        raw = response.choices[0].message.content or "{}"
        return self._parse_llm_response(raw)

    def _get_history_context(self) -> str:
        if self._evidence is None:
            return "No historical data available."
        summary = self._evidence.analyze()
        return self._evidence.format_summary(summary)

    @staticmethod
    def _build_routing_prompt(issue: Issue, history: str) -> str:
        parts = [
            f"## Issue\n- Title: {issue.title}\n- Summary: {issue.summary}",
            f"- Labels: {', '.join(issue.labels) if issue.labels else 'none'}",
            f"- Run class: {issue.run_class or 'unset'}",
        ]
        if issue.acceptance_criteria:
            parts.append(f"- Acceptance criteria: {len(issue.acceptance_criteria)} items")
        if issue.context.constraints:
            parts.append(f"- Constraints: {len(issue.context.constraints)} items")
        if issue.context.files_to_read:
            parts.append(f"- Files mentioned: {', '.join(issue.context.files_to_read[:10])}")
        parts.append(f"\n## Historical Evidence\n{history}")
        return "\n".join(parts)

    @staticmethod
    def _parse_llm_response(raw: str) -> FlowRoutingDecision:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("LLM routing response is not valid JSON: %s", cleaned[:200])
            from spec_orch.services.event_bus import emit_fallback_safe

            emit_fallback_safe(
                "FlowRouter",
                "llm_json_parse",
                "default_standard",
                "LLM returned non-JSON response",
            )
            return FlowRoutingDecision(
                recommended_flow=FlowType.STANDARD,
                confidence=0.0,
                reasoning="LLM response was not valid JSON",
                source="fallback",
            )

        if not isinstance(data, dict):
            logger.warning("LLM routing response is not a JSON object: %s", type(data).__name__)
            from spec_orch.services.event_bus import emit_fallback_safe

            emit_fallback_safe(
                "FlowRouter",
                "llm_json_schema",
                "default_standard",
                f"Expected JSON object, got {type(data).__name__}",
            )
            return FlowRoutingDecision(
                recommended_flow=FlowType.STANDARD,
                confidence=0.0,
                reasoning="LLM response was not a JSON object",
                source="fallback",
            )

        flow_str = data.get("recommended_flow", "standard")
        try:
            flow = FlowType(flow_str)
        except ValueError:
            logger.warning("LLM returned unknown flow type %r, defaulting to standard", flow_str)
            flow = FlowType.STANDARD
        return FlowRoutingDecision(
            recommended_flow=flow,
            confidence=float(data.get("confidence", 0.5)),
            reasoning=data.get("reasoning", ""),
            source="llm",
            complexity_signals=data.get("complexity_signals"),
        )

    def to_event_payload(self, decision: FlowRoutingDecision) -> dict[str, Any]:
        """Serialize a routing decision for EventBus audit."""
        return asdict(decision)
