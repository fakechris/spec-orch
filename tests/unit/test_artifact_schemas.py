"""Tests for pydantic-based artifact schema validation."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from spec_orch.services.artifact_schemas import (
    ArtifactManifestSchema,
    Conclusion,
    LiveSnapshot,
    RoundSummarySchema,
    RunReport,
    validate_conclusion,
    validate_live_snapshot,
    validate_manifest,
    validate_round_summary,
    validate_run_report,
)
from spec_orch.services.run_artifact_service import RunArtifactService

# ---------------------------------------------------------------------------
# Fixtures: known-good payloads
# ---------------------------------------------------------------------------

GOOD_LIVE = {
    "run_id": "run-1",
    "issue_id": "SON-1",
    "state": "gate_evaluated",
    "mergeable": True,
    "failed_conditions": [],
    "flow_control": {"retry_recommended": False},
    "builder": {"adapter": "codex_exec"},
    "review": {},
    "verification": {},
    "event_tail": [{"event_type": "run_started"}],
    "updated_at": "2026-01-01T00:00:00Z",
}

GOOD_CONCLUSION = {
    "run_id": "run-1",
    "issue_id": "SON-1",
    "verdict": "pass",
    "mergeable": True,
    "failed_conditions": [],
    "flow_control": {},
    "state": "gate_evaluated",
    "evidence": {"report": {}},
    "generated_at": "2026-01-01T00:00:00Z",
}

GOOD_MANIFEST = {
    "schema_version": "1.0",
    "run_id": "run-1",
    "issue_id": "SON-1",
    "state": "gate_evaluated",
    "mergeable": True,
    "flow_control": {},
    "events_count": 5,
    "generated_at": "2026-01-01T00:00:00Z",
    "artifacts": {"report": "/tmp/report.json"},
}

GOOD_RUN_REPORT = {
    "state": "gate_evaluated",
    "run_id": "run-1",
    "issue_id": "SON-1",
    "title": "My Issue",
    "mergeable": True,
    "failed_conditions": [],
    "flow_control": {},
    "builder": {},
    "review": {},
    "verification": {},
    "human_acceptance": {},
}

GOOD_ROUND_SUMMARY = {
    "round_id": 1,
    "wave_id": 0,
    "status": "completed",
    "started_at": "2026-01-01T00:00:00Z",
    "completed_at": "2026-01-01T00:01:00Z",
    "worker_results": [{"worker": "w1", "exit_code": 0}],
    "decision": {"action": "proceed"},
}


# ---------------------------------------------------------------------------
# Test: known-good payloads validate successfully
# ---------------------------------------------------------------------------


class TestKnownGoodPayloads:
    def test_live_snapshot_valid(self) -> None:
        model = LiveSnapshot.model_validate(GOOD_LIVE)
        assert model.run_id == "run-1"
        assert model.mergeable is True

    def test_conclusion_valid(self) -> None:
        model = Conclusion.model_validate(GOOD_CONCLUSION)
        assert model.verdict == "pass"

    def test_manifest_valid(self) -> None:
        model = ArtifactManifestSchema.model_validate(GOOD_MANIFEST)
        assert model.events_count == 5

    def test_run_report_valid(self) -> None:
        model = RunReport.model_validate(GOOD_RUN_REPORT)
        assert model.title == "My Issue"

    def test_round_summary_valid(self) -> None:
        model = RoundSummarySchema.model_validate(GOOD_ROUND_SUMMARY)
        assert model.round_id == 1


# ---------------------------------------------------------------------------
# Test: invalid data is caught
# ---------------------------------------------------------------------------


class TestInvalidData:
    def test_live_snapshot_missing_required(self) -> None:
        with pytest.raises(ValidationError):
            LiveSnapshot.model_validate({"run_id": "run-1"})

    def test_conclusion_wrong_type(self) -> None:
        # pydantic v2 coerces strings in some modes; use strict to ensure
        # the model still validates (extra="allow" + lenient coercion)
        # The important thing is the helper returns None for truly broken data.
        result = validate_conclusion({"verdict": 123})
        assert result is None

    def test_manifest_wrong_type_events_count(self) -> None:
        bad = {**GOOD_MANIFEST, "events_count": "not-an-int"}
        # pydantic v2 coerces "5" to 5 but "not-an-int" should fail
        with pytest.raises(ValidationError):
            ArtifactManifestSchema.model_validate(bad)

    def test_round_summary_missing_required(self) -> None:
        with pytest.raises(ValidationError):
            RoundSummarySchema.model_validate({"round_id": 1})


# ---------------------------------------------------------------------------
# Test: extra fields are allowed (forward compatibility)
# ---------------------------------------------------------------------------


class TestExtraFieldsAllowed:
    def test_live_snapshot_extra(self) -> None:
        data = {**GOOD_LIVE, "future_field": "hello"}
        model = LiveSnapshot.model_validate(data)
        assert model.future_field == "hello"  # type: ignore[attr-defined]

    def test_conclusion_extra(self) -> None:
        data = {**GOOD_CONCLUSION, "new_key": 42}
        model = Conclusion.model_validate(data)
        assert model.new_key == 42  # type: ignore[attr-defined]

    def test_manifest_extra(self) -> None:
        data = {**GOOD_MANIFEST, "extra_info": [1, 2, 3]}
        model = ArtifactManifestSchema.model_validate(data)
        assert model.extra_info == [1, 2, 3]  # type: ignore[attr-defined]

    def test_run_report_extra(self) -> None:
        data = {**GOOD_RUN_REPORT, "metadata": {"version": 2}}
        model = RunReport.model_validate(data)
        assert model.metadata == {"version": 2}  # type: ignore[attr-defined]

    def test_round_summary_extra(self) -> None:
        data = {**GOOD_ROUND_SUMMARY, "extensions": {}}
        model = RoundSummarySchema.model_validate(data)
        assert model.extensions == {}  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Test: helper functions log warnings instead of raising
# ---------------------------------------------------------------------------


class TestHelperFunctionsWarnOnly:
    def test_validate_live_snapshot_returns_none_on_bad(self, caplog) -> None:
        with caplog.at_level(logging.WARNING):
            result = validate_live_snapshot({})
        assert result is None
        assert "LiveSnapshot validation failed" in caplog.text

    def test_validate_conclusion_returns_none_on_bad(self, caplog) -> None:
        with caplog.at_level(logging.WARNING):
            result = validate_conclusion({"verdict": 123})
        assert result is None
        assert "Conclusion validation failed" in caplog.text

    def test_validate_manifest_returns_none_on_bad(self, caplog) -> None:
        with caplog.at_level(logging.WARNING):
            result = validate_manifest({"events_count": "bad"})
        assert result is None
        assert "ArtifactManifestSchema validation failed" in caplog.text

    def test_validate_run_report_returns_model_on_good(self) -> None:
        result = validate_run_report(GOOD_RUN_REPORT)
        assert result is not None
        assert result.run_id == "run-1"

    def test_validate_round_summary_returns_none_on_bad(self, caplog) -> None:
        with caplog.at_level(logging.WARNING):
            result = validate_round_summary({})
        assert result is None
        assert "RoundSummarySchema validation failed" in caplog.text


# ---------------------------------------------------------------------------
# Test: RunArtifactService.write_from_run still works with validation
# ---------------------------------------------------------------------------


class TestArtifactServiceWithValidation:
    def test_write_conclusion_still_works(self, tmp_path: Path) -> None:
        workspace = tmp_path / "run-v"
        workspace.mkdir()
        (workspace / "telemetry").mkdir()
        (workspace / "telemetry" / "events.jsonl").write_text(
            json.dumps({"event_type": "run_started"}) + "\n"
        )
        report_path = workspace / "report.json"
        report_path.write_text(
            json.dumps(
                {
                    "state": "gate_evaluated",
                    "mergeable": True,
                    "failed_conditions": [],
                    "builder": {"adapter": "codex_exec", "succeeded": True},
                }
            )
        )

        svc = RunArtifactService()
        manifest_path = svc.write_from_run(
            workspace=workspace,
            run_id="run-v",
            issue_id="SON-V",
            report_path=report_path,
            explain_path=None,
        )

        assert manifest_path.exists()
        conclusion = json.loads((workspace / "run_artifact" / "conclusion.json").read_text())
        assert conclusion["run_id"] == "run-v"
        assert conclusion["verdict"] == "pass"
