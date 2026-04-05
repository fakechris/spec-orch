from __future__ import annotations

from pathlib import Path
from typing import Any

from spec_orch.domain.models import GateVerdict, VerificationDetail, VerificationSummary


def build_verification_output_payload(
    *,
    packet_id: str,
    workspace: Path,
    verification: VerificationSummary,
    producer_role: str = "verifier",
) -> dict[str, Any]:
    return {
        "schema": "verification_output.v1",
        "packet_id": packet_id,
        "producer_role": producer_role,
        "workspace": str(workspace),
        "all_passed": verification.all_passed,
        "step_results": dict(verification.step_results),
        "outcomes": {step: verification.get_step_outcome(step) for step in verification.details},
        "details": {
            step: {
                "command": detail.command,
                "exit_code": detail.exit_code,
                "stdout": detail.stdout,
                "stderr": detail.stderr,
            }
            for step, detail in verification.details.items()
        },
    }


def build_gate_verdict_payload(
    *,
    packet_id: str,
    gate: GateVerdict,
    scope: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "gate_verdict.v1",
        "packet_id": packet_id,
        "mergeable": gate.mergeable and bool(scope.get("all_in_scope", False)),
        "failed_conditions": list(gate.failed_conditions),
        "scope": scope,
    }


def build_verification_event_payload(
    *,
    step_name: str,
    detail: VerificationDetail,
    outcome: str,
) -> dict[str, Any]:
    return {
        "schema": "verification_event.v1",
        "step": step_name,
        "outcome": outcome,
        "exit_code": detail.exit_code,
        "command": detail.command,
    }


def build_gate_event_payload(gate: GateVerdict) -> dict[str, Any]:
    return {
        "schema": "gate_event.v1",
        "mergeable": gate.mergeable,
        "failed_conditions": list(gate.failed_conditions),
    }
