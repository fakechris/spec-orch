"""Tests for the SkillEvolver — tool-sequence → SkillManifest discovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from spec_orch.domain.models import EvolutionChangeType, EvolutionProposal
from spec_orch.services.evolution.skill_evolver import (
    SkillEvolver,
    _dedupe_run,
    _event_tool_signature,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_telemetry(run_dir: Path, events: list[dict[str, Any]]) -> None:
    telem = run_dir / "telemetry"
    telem.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e) for e in events]
    (telem / "incoming_events.jsonl").write_text("\n".join(lines))


def _valid_skill_content() -> dict[str, Any]:
    return {
        "id": "auto-skill-lint-test",
        "name": "Lint then test",
        "kind": "builder_hook",
        "description": "Run linter before tests",
        "triggers": ["lint", "test"],
        "params": {
            "tool_sequence": ["lint", "test"],
            "instructions": "Always lint before running tests.",
        },
    }


# ---------------------------------------------------------------------------
# unit tests — _event_tool_signature
# ---------------------------------------------------------------------------


class TestEventToolSignature:
    def test_method_preferred(self) -> None:
        assert _event_tool_signature({"method": "git.diff", "type": "rpc"}) == "git.diff"

    def test_type_fallback(self) -> None:
        assert _event_tool_signature({"type": "file", "item": {"type": "read"}}) == "file/read"

    def test_kind_fallback(self) -> None:
        assert _event_tool_signature({"kind": "shell_exec"}) == "shell_exec"

    def test_empty(self) -> None:
        assert _event_tool_signature({}) is None


class TestDedupeRun:
    def test_removes_consecutive_dups(self) -> None:
        assert _dedupe_run(["a", "a", "b", "b", "a"]) == ["a", "b", "a"]

    def test_max_length(self) -> None:
        assert len(_dedupe_run(list(map(str, range(200))))) == 64


# ---------------------------------------------------------------------------
# observe / propose / validate / promote
# ---------------------------------------------------------------------------


class TestSkillEvolverObserve:
    def test_observe_with_telemetry(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-001"
        _make_telemetry(
            run_dir,
            [
                {"method": "file.read"},
                {"method": "file.write"},
                {"method": "shell.exec"},
            ],
        )
        evolver = SkillEvolver(tmp_path)
        evidence = evolver.observe([run_dir])
        assert len(evidence) == 1
        runs = evidence[0]["runs"]
        assert len(runs) == 1
        assert runs[0]["tool_sequence"] == ["file.read", "file.write", "shell.exec"]

    def test_observe_empty_dir(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-empty"
        run_dir.mkdir(parents=True)
        evolver = SkillEvolver(tmp_path)
        evidence = evolver.observe([run_dir])
        assert evidence == []


class TestSkillEvolverPropose:
    def test_propose_without_planner_returns_empty(self, tmp_path: Path) -> None:
        evolver = SkillEvolver(tmp_path, planner=None)
        assert evolver.propose([{"runs": [{"tool_sequence": ["a"]}]}]) == []

    def test_propose_parses_llm_response(self, tmp_path: Path) -> None:
        planner = MagicMock()
        planner.brainstorm.return_value = json.dumps(
            {
                "skills": [_valid_skill_content()],
                "analysis_summary": "found pattern",
            }
        )
        evolver = SkillEvolver(tmp_path, planner=planner)
        proposals = evolver.propose(
            [
                {
                    "runs": [{"run_id": "r1", "tool_sequence": ["lint", "test"]}],
                    "builder_events_summary": "",
                }
            ]
        )
        assert len(proposals) == 1
        assert proposals[0].evolver_name == "skill_evolver"
        assert proposals[0].content["id"] == "auto-skill-lint-test"


class TestSkillEvolverValidate:
    def test_valid_proposal_accepted(self, tmp_path: Path) -> None:
        evolver = SkillEvolver(tmp_path)
        proposal = EvolutionProposal(
            proposal_id="skill-auto-skill-lint-test",
            evolver_name="skill_evolver",
            change_type=EvolutionChangeType.HARNESS_RULE,
            content=_valid_skill_content(),
            confidence=0.7,
        )
        outcome = evolver.validate(proposal)
        assert outcome.accepted is True

    def test_duplicate_id_rejected(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".spec_orch" / "skills"
        skills_dir.mkdir(parents=True)
        import yaml

        (skills_dir / "auto-skill-lint-test.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": "1.0",
                    "id": "auto-skill-lint-test",
                    "name": "existing",
                    "kind": "builder_hook",
                }
            )
        )
        evolver = SkillEvolver(tmp_path)
        proposal = EvolutionProposal(
            proposal_id="skill-auto-skill-lint-test",
            evolver_name="skill_evolver",
            change_type=EvolutionChangeType.HARNESS_RULE,
            content=_valid_skill_content(),
            confidence=0.7,
        )
        outcome = evolver.validate(proposal)
        assert outcome.accepted is False
        assert "already exists" in outcome.reason

    def test_wrong_kind_rejected(self, tmp_path: Path) -> None:
        content = _valid_skill_content()
        content["kind"] = "custom"
        evolver = SkillEvolver(tmp_path)
        proposal = EvolutionProposal(
            proposal_id="x",
            evolver_name="skill_evolver",
            change_type=EvolutionChangeType.HARNESS_RULE,
            content=content,
            confidence=0.7,
        )
        outcome = evolver.validate(proposal)
        assert outcome.accepted is False

    def test_low_confidence_rejected(self, tmp_path: Path) -> None:
        evolver = SkillEvolver(tmp_path)
        proposal = EvolutionProposal(
            proposal_id="y",
            evolver_name="skill_evolver",
            change_type=EvolutionChangeType.HARNESS_RULE,
            content=_valid_skill_content(),
            confidence=0.3,
        )
        outcome = evolver.validate(proposal)
        assert outcome.accepted is False


class TestSkillEvolverPromote:
    def test_promote_writes_yaml(self, tmp_path: Path) -> None:
        evolver = SkillEvolver(tmp_path)
        proposal = EvolutionProposal(
            proposal_id="skill-auto-skill-lint-test",
            evolver_name="skill_evolver",
            change_type=EvolutionChangeType.HARNESS_RULE,
            content=_valid_skill_content(),
            confidence=0.7,
        )
        assert evolver.promote(proposal) is True
        skill_path = tmp_path / ".spec_orch" / "skills" / "auto-skill-lint-test.yaml"
        assert skill_path.exists()
        import yaml

        data = yaml.safe_load(skill_path.read_text())
        assert data["id"] == "auto-skill-lint-test"
        assert data["author"] == "skill_evolver"

    def test_promote_bad_id_rejected(self, tmp_path: Path) -> None:
        content = _valid_skill_content()
        content["id"] = "../../../etc/passwd"
        evolver = SkillEvolver(tmp_path)
        proposal = EvolutionProposal(
            proposal_id="z",
            evolver_name="skill_evolver",
            change_type=EvolutionChangeType.HARNESS_RULE,
            content=content,
            confidence=0.7,
        )
        assert evolver.promote(proposal) is False
