"""Tests for RunController flow engine integration (Phase 4+5 of Change 01)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from spec_orch.domain.models import FlowType, GateVerdict, Issue
from spec_orch.flow_engine.engine import FlowEngine
from spec_orch.flow_engine.mapper import FlowMapper
from spec_orch.services.run_controller import RunController, record_flow_transition

# ── T4.1: RunController accepts FlowEngine/FlowMapper injection ──


class TestRunControllerInjection:
    def test_default_engine_and_mapper(self, tmp_path: Path):
        rc = RunController(repo_root=tmp_path)
        assert isinstance(rc.flow_engine, FlowEngine)
        assert isinstance(rc.flow_mapper, FlowMapper)

    def test_custom_engine(self, tmp_path: Path):
        custom = FlowEngine()
        rc = RunController(repo_root=tmp_path, flow_engine=custom)
        assert rc.flow_engine is custom

    def test_custom_mapper(self, tmp_path: Path):
        custom = FlowMapper()
        rc = RunController(repo_root=tmp_path, flow_mapper=custom)
        assert rc.flow_mapper is custom


# ── T4.2: _resolve_flow ──


class TestResolveFlow:
    def test_default_is_standard(self, tmp_path: Path):
        rc = RunController(repo_root=tmp_path)
        issue = Issue(issue_id="TEST-1", title="test", summary="", run_class=None)
        assert rc._resolve_flow(issue) is FlowType.STANDARD

    def test_feature_resolves_to_full(self, tmp_path: Path):
        rc = RunController(repo_root=tmp_path)
        issue = Issue(issue_id="TEST-1", title="test", summary="", run_class="feature")
        assert rc._resolve_flow(issue) is FlowType.FULL

    def test_bug_resolves_to_standard(self, tmp_path: Path):
        rc = RunController(repo_root=tmp_path)
        issue = Issue(issue_id="TEST-1", title="test", summary="", run_class="bug")
        assert rc._resolve_flow(issue) is FlowType.STANDARD


# ── T4.3: run_issue accepts flow_type parameter ──


class TestRunIssueFlowType:
    def test_run_issue_signature_accepts_flow_type(self, tmp_path: Path):
        """Verify run_issue accepts flow_type kwarg without error at signature level."""
        import inspect

        sig = inspect.signature(RunController.run_issue)
        assert "flow_type" in sig.parameters
        param = sig.parameters["flow_type"]
        assert param.default is None


# ── T4.5/T4.6/T4.7: _handle_gate_flow_signals ──


class TestHandleGateFlowSignals:
    def _make_rc(self, tmp_path: Path) -> RunController:
        return RunController(repo_root=tmp_path)

    def test_promotion_records_event(self, tmp_path: Path):
        rc = self._make_rc(tmp_path)
        gate = GateVerdict(
            mergeable=True,
            failed_conditions=[],
            promotion_required=True,
            promotion_target="full",
        )
        with patch("spec_orch.services.run_controller.record_flow_transition") as mock_record:
            rc._handle_gate_flow_signals(
                gate=gate,
                resolved_flow=FlowType.STANDARD,
                issue_id="TEST-1",
                run_id="run-001",
                workspace=tmp_path,
            )
            mock_record.assert_called_once()
            evt = mock_record.call_args[0][0]
            assert evt.from_flow == "standard"
            assert evt.to_flow == "full"
            assert evt.trigger == "promotion_required"

    def test_promotion_invalid_target_no_crash(self, tmp_path: Path):
        rc = self._make_rc(tmp_path)
        gate = GateVerdict(
            mergeable=True,
            failed_conditions=[],
            promotion_required=True,
            promotion_target="nonexistent",
        )
        with patch("spec_orch.services.run_controller.record_flow_transition") as mock_record:
            rc._handle_gate_flow_signals(
                gate=gate,
                resolved_flow=FlowType.STANDARD,
                issue_id="TEST-1",
                run_id="run-001",
                workspace=tmp_path,
            )
            mock_record.assert_not_called()

    def test_promotion_same_or_lower_ignored(self, tmp_path: Path):
        rc = self._make_rc(tmp_path)
        gate = GateVerdict(
            mergeable=True,
            failed_conditions=[],
            promotion_required=True,
            promotion_target="standard",
        )
        with patch("spec_orch.services.run_controller.record_flow_transition") as mock_record:
            rc._handle_gate_flow_signals(
                gate=gate,
                resolved_flow=FlowType.FULL,
                issue_id="TEST-1",
                run_id="run-001",
                workspace=tmp_path,
            )
            mock_record.assert_not_called()

    def test_no_promotion_normal_flow(self, tmp_path: Path):
        rc = self._make_rc(tmp_path)
        gate = GateVerdict(
            mergeable=True,
            failed_conditions=[],
            promotion_required=False,
        )
        with patch("spec_orch.services.run_controller.record_flow_transition") as mock_record:
            rc._handle_gate_flow_signals(
                gate=gate,
                resolved_flow=FlowType.STANDARD,
                issue_id="TEST-1",
                run_id="run-001",
                workspace=tmp_path,
            )
            mock_record.assert_not_called()

    def test_demotion_records_event(self, tmp_path: Path):
        rc = self._make_rc(tmp_path)
        gate = GateVerdict(
            mergeable=True,
            failed_conditions=[],
            demotion_suggested=True,
            demotion_target="standard",
        )
        with patch("spec_orch.services.run_controller.record_flow_transition") as mock_record:
            rc._handle_gate_flow_signals(
                gate=gate,
                resolved_flow=FlowType.FULL,
                issue_id="TEST-1",
                run_id="run-001",
                workspace=tmp_path,
            )
            mock_record.assert_called_once()
            evt = mock_record.call_args[0][0]
            assert evt.trigger == "demotion_suggested"

    def test_backtrack_logs_reason(self, tmp_path: Path):
        rc = self._make_rc(tmp_path)
        gate = GateVerdict(
            mergeable=False,
            failed_conditions=["builder"],
            backtrack_reason="recoverable",
        )
        rc._handle_gate_flow_signals(
            gate=gate,
            resolved_flow=FlowType.FULL,
            issue_id="TEST-1",
            run_id="run-001",
            workspace=tmp_path,
        )


# ── T5.1: record_flow_transition stub ──


class TestRecordFlowTransition:
    def test_stub_does_not_raise(self):
        from spec_orch.domain.models import FlowTransitionEvent

        evt = FlowTransitionEvent(
            from_flow="standard",
            to_flow="full",
            trigger="test",
            timestamp="2026-01-01T00:00:00Z",
        )
        record_flow_transition(evt)
