from pathlib import Path
from typing import Any

from spec_orch.domain.models import Issue
from spec_orch.services.builders.codex_exec_builder_adapter import CodexExecBuilderAdapter


def test_codex_adapter_can_handle() -> None:
    adapter = CodexExecBuilderAdapter()
    issue = Issue(issue_id="T-1", title="Test", summary="s")
    assert adapter.can_handle(issue) is True


def test_codex_adapter_collect_artifacts(tmp_path: Path) -> None:
    adapter = CodexExecBuilderAdapter()
    (tmp_path / "builder_report.json").write_text("{}")
    telem = tmp_path / "telemetry"
    telem.mkdir()
    (telem / "incoming_events.jsonl").write_text("")

    artifacts = adapter.collect_artifacts(tmp_path)
    names = [a.name for a in artifacts]
    assert "builder_report.json" in names
    assert "incoming_events.jsonl" in names


def test_codex_adapter_map_events() -> None:
    adapter = CodexExecBuilderAdapter()
    raw_events: list[dict[str, Any]] = [
        {
            "type": "item.started",
            "item": {"type": "command_execution", "command": "ls"},
            "timestamp": "2026-03-11T00:00:00Z",
        },
        {
            "type": "item.completed",
            "item": {"type": "command_execution", "command": "ls", "exit_code": 0},
            "timestamp": "2026-03-11T00:00:01Z",
        },
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "Done."},
            "timestamp": "2026-03-11T00:00:02Z",
        },
        {
            "type": "item.completed",
            "item": {"type": "file_change", "file": "src/a.py"},
            "timestamp": "2026-03-11T00:00:03Z",
        },
        {
            "type": "turn.completed",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "timestamp": "2026-03-11T00:00:04Z",
        },
        {
            "type": "turn.failed",
            "timestamp": "2026-03-11T00:00:05Z",
        },
    ]
    mapped = adapter.map_events(raw_events)
    assert len(mapped) == 6
    assert mapped[0].kind == "command_start"
    assert mapped[0].text == "ls"
    assert mapped[1].kind == "command_end"
    assert mapped[1].exit_code == 0
    assert mapped[2].kind == "message"
    assert mapped[2].text == "Done."
    assert mapped[3].kind == "file_change"
    assert mapped[3].file_path == "src/a.py"
    assert mapped[4].kind == "turn_end"
    assert mapped[5].kind == "error"


def test_gate_verdict_dual_mergeability() -> None:
    from spec_orch.domain.models import GateInput
    from spec_orch.services.gate_service import GateService

    svc = GateService()
    verdict = svc.evaluate(
        GateInput(
            spec_exists=True,
            spec_approved=True,
            within_boundaries=True,
            builder_succeeded=True,
            human_acceptance=True,
        )
    )
    assert verdict.mergeable_internal is not None
    assert verdict.mergeable_external is True
    assert verdict.mergeable == verdict.mergeable_internal
