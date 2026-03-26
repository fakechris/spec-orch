from __future__ import annotations

import json
import sys
from pathlib import Path

from spec_orch.domain.models import BuilderResult, Wave, WorkPacket


def test_command_visual_evaluator_runs_external_command_and_parses_output(tmp_path: Path) -> None:
    from spec_orch.services.visual.command_visual_evaluator import CommandVisualEvaluator

    script = """
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text())
pathlib.Path(sys.argv[2]).write_text(
    json.dumps(
        {
            "evaluator": "command",
            "summary": f"checked {payload['mission_id']} round {payload['round_id']}",
            "confidence": 0.75,
            "findings": [{"severity": "low", "summary": payload["wave"]["description"]}],
            "artifacts": {"input_json": sys.argv[1]},
        }
    )
)
""".strip()
    evaluator = CommandVisualEvaluator(
        command=[sys.executable, "-c", script, "{input_json}", "{output_json}"],
    )
    workspace = tmp_path / "worker"
    workspace.mkdir()

    result = evaluator.evaluate_round(
        mission_id="mission-cmd",
        round_id=4,
        wave=Wave(
            wave_number=2,
            description="Visual regression sweep",
            work_packets=[WorkPacket(packet_id="pkt-1", title="Task 1")],
        ),
        worker_results=[
            (
                WorkPacket(packet_id="pkt-1", title="Task 1"),
                BuilderResult(
                    succeeded=True,
                    command=["stub"],
                    stdout="ok",
                    stderr="",
                    report_path=workspace / "builder_report.json",
                    adapter="stub",
                    agent="stub",
                ),
            )
        ],
        repo_root=tmp_path,
        round_dir=tmp_path / "round-04",
    )

    assert result is not None
    assert result.evaluator == "command"
    assert result.summary == "checked mission-cmd round 4"
    assert result.findings == [{"severity": "low", "summary": "Visual regression sweep"}]
    input_json = tmp_path / "round-04" / "visual" / "input.json"
    output_json = tmp_path / "round-04" / "visual" / "output.json"
    assert input_json.exists()
    assert output_json.exists()
    payload = json.loads(input_json.read_text(encoding="utf-8"))
    assert payload["wave"]["packet_ids"] == ["pkt-1"]


def test_command_visual_evaluator_degrades_to_error_result_on_command_failure(
    tmp_path: Path,
) -> None:
    from spec_orch.services.visual.command_visual_evaluator import CommandVisualEvaluator

    evaluator = CommandVisualEvaluator(
        command=[sys.executable, "-c", "import sys; sys.exit(7)"],
    )

    result = evaluator.evaluate_round(
        mission_id="mission-fail",
        round_id=1,
        wave=Wave(wave_number=0, description="Failing eval", work_packets=[]),
        worker_results=[],
        repo_root=tmp_path,
        round_dir=tmp_path / "round-01",
    )

    assert result is not None
    assert result.evaluator == "command"
    assert result.confidence == 0.0
    assert result.findings[0]["severity"] == "error"
    assert "exit code 7" in result.findings[0]["summary"]
