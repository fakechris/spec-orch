"""FlowEngine — query interface for workflow graphs."""

from __future__ import annotations

from spec_orch.domain.models import FlowGraph, FlowType
from spec_orch.flow_engine.graphs import FULL_GRAPH, HOTFIX_GRAPH, STANDARD_GRAPH

_GRAPHS: dict[FlowType, FlowGraph] = {
    FlowType.FULL: FULL_GRAPH,
    FlowType.STANDARD: STANDARD_GRAPH,
    FlowType.HOTFIX: HOTFIX_GRAPH,
}


class FlowEngine:
    """Stateless query interface over pre-defined FlowGraphs."""

    def __init__(self, graphs: dict[FlowType, FlowGraph] | None = None) -> None:
        self._graphs = graphs or dict(_GRAPHS)

    def get_graph(self, flow_type: FlowType) -> FlowGraph:
        try:
            return self._graphs[flow_type]
        except KeyError:
            raise ValueError(f"Unknown flow type: {flow_type!r}") from None

    def get_next_steps(self, flow_type: FlowType, step_id: str) -> list[str]:
        graph = self.get_graph(flow_type)
        return list(graph.transitions.get(step_id, ()))

    def get_backtrack_target(
        self,
        flow_type: FlowType,
        step_id: str,
        reason: str,
    ) -> str | None:
        graph = self.get_graph(flow_type)
        step_bt = graph.backtrack.get(step_id, {})
        return step_bt.get(reason)

    def is_skippable(
        self,
        flow_type: FlowType,
        step_id: str,
        active_conditions: set[str],
    ) -> bool:
        """Check if a step can be skipped given the active conditions."""
        graph = self.get_graph(flow_type)
        step = graph.get_step(step_id)
        if step is None:
            return False
        return bool(step.skippable_if and not active_conditions.isdisjoint(step.skippable_if))
