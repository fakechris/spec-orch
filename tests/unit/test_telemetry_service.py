from __future__ import annotations

import json
from pathlib import Path

from spec_orch.services.telemetry_service import TelemetryService


def test_telemetry_service_writes_sanitized_contract_payload(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    service = TelemetryService()

    events_path = service.log_event(
        workspace=workspace,
        run_id="run-1",
        issue_id="SPC-1",
        component="verification",
        event_type="verification_completed",
        severity="info",
        message="Completed verification steps.",
        data={
            "artifact": str(workspace / "artifacts/report.json"),
            str(workspace / "artifacts/proof.json"): "proof",
        },
    )

    payload = json.loads(events_path.read_text(encoding="utf-8").splitlines()[0])

    assert payload["schema"] == "telemetry_event.v1"
    assert payload["workspace"] == "."
    assert payload["data"]["artifact"] == "artifacts/report.json"
    assert payload["data"]["artifacts/proof.json"] == "proof"
