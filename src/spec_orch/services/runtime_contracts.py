from __future__ import annotations

from pathlib import Path
from typing import Any

from spec_orch.domain.models import GateVerdict, VerificationDetail, VerificationSummary
from spec_orch.services.env_files import resolve_shared_repo_root
from spec_orch.services.path_sanitizer import resolve_repo_root, sanitize_value


def sanitize_runtime_payload(
    *,
    workspace: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    repo_root = resolve_repo_root(workspace)
    shared_root = resolve_shared_repo_root(repo_root)
    sanitized = sanitize_value(
        payload,
        repo_root=repo_root,
        shared_root=shared_root.resolve() if shared_root is not None else None,
    )
    return sanitized if isinstance(sanitized, dict) else {}


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


def build_telemetry_event_payload(
    *,
    workspace: Path,
    run_id: str,
    issue_id: str,
    component: str,
    event_type: str,
    severity: str,
    message: str,
    adapter: str | None = None,
    agent: str | None = None,
    data: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    payload = {
        "schema": "telemetry_event.v1",
        "timestamp": timestamp,
        "run_id": run_id,
        "issue_id": issue_id,
        "workspace": str(workspace),
        "component": component,
        "event_type": event_type,
        "severity": severity,
        "message": message,
        "adapter": adapter,
        "agent": agent,
        "data": data or {},
    }
    return sanitize_runtime_payload(workspace=workspace, payload=payload)
