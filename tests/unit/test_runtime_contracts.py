from __future__ import annotations

from pathlib import Path

from spec_orch.domain.models import GateVerdict, VerificationDetail, VerificationSummary
from spec_orch.services.runtime_contracts import (
    build_gate_event_payload,
    build_gate_verdict_payload,
    build_telemetry_event_payload,
    build_verification_event_payload,
    build_verification_output_payload,
    sanitize_runtime_payload,
)


def test_build_verification_output_payload_uses_tri_state_outcomes(tmp_path: Path) -> None:
    verification = VerificationSummary(
        details={
            "lint": VerificationDetail(
                command=["ruff", "check"],
                exit_code=0,
                stdout="ok",
                stderr="",
            ),
            "build": VerificationDetail(
                command=[],
                exit_code=0,
                stdout="",
                stderr="not configured — skipped",
            ),
        }
    )
    verification.set_step_passed("lint", True)
    verification.set_step_outcome("build", "skipped")

    payload = build_verification_output_payload(
        packet_id="pkt-1",
        workspace=tmp_path / "pkt-1",
        verification=verification,
    )

    assert payload["schema"] == "verification_output.v1"
    assert payload["outcomes"] == {"lint": "pass", "build": "skipped"}
    assert payload["all_passed"] is False


def test_build_gate_payloads_use_shared_contract_shape() -> None:
    gate = GateVerdict(mergeable=False, failed_conditions=["verification", "scope"])
    scope = {
        "allowed_files": ["src/a.py"],
        "realized_files": ["src/a.py", "src/b.py"],
        "out_of_scope_files": ["src/b.py"],
        "all_in_scope": False,
    }

    verdict_payload = build_gate_verdict_payload(packet_id="pkt-1", gate=gate, scope=scope)
    event_payload = build_gate_event_payload(gate)

    assert verdict_payload["schema"] == "gate_verdict.v1"
    assert verdict_payload["failed_conditions"] == ["verification", "scope"]
    assert verdict_payload["flow_control"]["backtrack_reason"] == gate.flow_control.backtrack_reason
    assert verdict_payload["scope"]["all_in_scope"] is False
    assert event_payload["schema"] == "gate_event.v1"
    assert event_payload["mergeable"] is False
    assert event_payload["flow_control"]["promotion_required"] is False


def test_build_verification_event_payload_preserves_step_outcome() -> None:
    detail = VerificationDetail(
        command=[],
        exit_code=0,
        stdout="",
        stderr="not configured — skipped",
    )

    payload = build_verification_event_payload(
        step_name="build",
        detail=detail,
        outcome="skipped",
    )

    assert payload["schema"] == "verification_event.v1"
    assert payload["step"] == "build"
    assert payload["outcome"] == "skipped"


def test_sanitize_runtime_payload_rewrites_nested_paths_and_keys(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    payload = sanitize_runtime_payload(
        workspace=workspace,
        payload={
            str(workspace / "artifacts/report.json"): {
                "proof": str(workspace / "artifacts/proof.json"),
                "external": "/Users/chris/tmp/raw-proof.json",
            }
        },
    )

    assert payload == {
        "artifacts/report.json": {
            "proof": "artifacts/proof.json",
            "external": "<external-path>/tmp/raw-proof.json",
        }
    }


def test_build_telemetry_event_payload_uses_shared_sanitization(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    payload = build_telemetry_event_payload(
        workspace=workspace,
        run_id="run-1",
        issue_id="SPC-1",
        component="verification",
        event_type="verification_step_completed",
        severity="warning",
        message="Verification step completed",
        adapter="test-adapter",
        agent="test-agent",
        data={
            "artifact": str(workspace / "artifacts/report.json"),
            "external": "/Users/chris/tmp/raw-proof.json",
        },
    )

    assert payload["schema"] == "telemetry_event.v1"
    assert payload["workspace"] == "."
    assert payload["data"]["artifact"] == "artifacts/report.json"
    assert payload["data"]["external"] == "<external-path>/tmp/raw-proof.json"
