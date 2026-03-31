from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from spec_orch.cli import app


def _make_fixture(tmp_path: Path, issue_id: str = "E7-CONTRACT-1") -> Path:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    fixture = {
        "issue_id": issue_id,
        "title": "Contract CLI Test",
        "summary": "Exercise contract surface commands.",
        "builder_prompt": "Implement the feature safely.",
        "acceptance_criteria": ["Tests pass"],
        "verification_commands": {"test": ["pytest", "tests/"]},
        "context": {
            "files_to_read": ["src/main.py"],
            "architecture_notes": "",
            "constraints": ["Do not touch auth"],
        },
    }
    path = fixtures_dir / f"{issue_id}.json"
    path.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
    return tmp_path


def test_contract_generate_outputs_yaml(tmp_path: Path) -> None:
    repo = _make_fixture(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["contract", "generate", "E7-CONTRACT-1", "--repo-root", str(repo)],
    )

    assert result.exit_code == 0
    data = yaml.safe_load(result.stdout)
    assert data["issue_id"] == "E7-CONTRACT-1"
    assert data["intent"] == "Implement the feature safely."


def test_contract_validate_accepts_valid_yaml(tmp_path: Path) -> None:
    contract_path = tmp_path / "contract.yaml"
    contract_path.write_text(
        yaml.dump(
            {
                "contract_id": "contract-1",
                "issue_id": "E7-CONTRACT-1",
                "intent": "Ship safely",
                "risk_level": "medium",
                "completion_criteria": ["Tests pass"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["contract", "validate", str(contract_path)])

    assert result.exit_code == 0
    assert "is valid" in result.stdout


def test_contract_assess_risk_reads_issue_from_fixture(tmp_path: Path) -> None:
    repo = _make_fixture(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["contract", "assess-risk", "E7-CONTRACT-1", "--repo-root", str(repo)],
    )

    assert result.exit_code == 0
    assert "risk_level=" in result.stdout
