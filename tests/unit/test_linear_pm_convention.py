"""Tests for Linear PM convention: label filtering, parent exclusion, daemon rules."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spec_orch.domain.models import (
    ExecutionPlan,
    PlanStatus,
    RunState,
    Wave,
    WorkPacket,
)
from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon
from spec_orch.services.linear_client import LinearClient
from spec_orch.services.promotion_service import PromotionService
from spec_orch.services.readiness_checker import ReadinessChecker

_COMPLETE_DESC = """\
## Goal

Implement the widget.

## Acceptance Criteria

- [ ] Widget works

## Files in Scope

- `src/widget.py`
"""


# ── LinearClient: filter_labels ─────────────────────────────────


@pytest.fixture()
def mock_httpx():
    with patch("spec_orch.services.linear_client.httpx") as mock:
        mock_client = MagicMock()
        mock.Client.return_value = mock_client
        yield mock_client


def _make_client(mock_httpx: MagicMock) -> LinearClient:
    with patch.dict("os.environ", {"SPEC_ORCH_LINEAR_TOKEN": "test-token"}):
        return LinearClient()


class TestLinearClientFiltering:
    def test_filter_labels_generates_correct_query(self, mock_httpx: MagicMock) -> None:
        client = _make_client(mock_httpx)
        mock_httpx.post.return_value = MagicMock(
            json=lambda: {"data": {"issues": {"nodes": []}}},
            raise_for_status=MagicMock(),
        )
        client.list_issues(team_key="SON", filter_labels=["agent-ready"])
        query = mock_httpx.post.call_args[1]["json"]["query"]
        assert "agent-ready" in query
        assert "some" in query

    def test_exclude_labels_generates_correct_query(self, mock_httpx: MagicMock) -> None:
        client = _make_client(mock_httpx)
        mock_httpx.post.return_value = MagicMock(
            json=lambda: {"data": {"issues": {"nodes": []}}},
            raise_for_status=MagicMock(),
        )
        client.list_issues(team_key="SON", exclude_labels=["blocked"])
        query = mock_httpx.post.call_args[1]["json"]["query"]
        assert "blocked" in query
        assert "nin" in query

    def test_exclude_parents_filters_out_issues_with_children(
        self, mock_httpx: MagicMock,
    ) -> None:
        client = _make_client(mock_httpx)
        mock_httpx.post.return_value = MagicMock(
            json=lambda: {
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "1", "identifier": "SON-1", "title": "Epic",
                                "children": {"nodes": [{"id": "child-1"}]},
                            },
                            {
                                "id": "2", "identifier": "SON-2", "title": "Task",
                                "children": {"nodes": []},
                            },
                        ]
                    }
                }
            },
            raise_for_status=MagicMock(),
        )
        issues = client.list_issues(team_key="SON", exclude_parents=True)
        assert len(issues) == 1
        assert issues[0]["identifier"] == "SON-2"

    def test_exclude_parents_false_keeps_all(self, mock_httpx: MagicMock) -> None:
        client = _make_client(mock_httpx)
        mock_httpx.post.return_value = MagicMock(
            json=lambda: {
                "data": {
                    "issues": {
                        "nodes": [
                            {"id": "1", "identifier": "SON-1"},
                            {"id": "2", "identifier": "SON-2"},
                        ]
                    }
                }
            },
            raise_for_status=MagicMock(),
        )
        issues = client.list_issues(team_key="SON", exclude_parents=False)
        assert len(issues) == 2

    def test_combined_filters(self, mock_httpx: MagicMock) -> None:
        client = _make_client(mock_httpx)
        mock_httpx.post.return_value = MagicMock(
            json=lambda: {"data": {"issues": {"nodes": []}}},
            raise_for_status=MagicMock(),
        )
        client.list_issues(
            team_key="SON",
            filter_state="Ready",
            filter_labels=["agent-ready"],
            exclude_labels=["blocked"],
            exclude_parents=True,
        )
        query = mock_httpx.post.call_args[1]["json"]["query"]
        assert "Ready" in str(mock_httpx.post.call_args)
        assert "agent-ready" in query
        assert "blocked" in query
        assert "children" in query


# ── DaemonConfig: new fields ────────────────────────────────────


class TestDaemonConfigConvention:
    def test_defaults(self) -> None:
        cfg = DaemonConfig({})
        assert cfg.consume_state == "Ready"
        assert cfg.require_labels == []
        assert "blocked" in cfg.exclude_labels
        assert "needs-clarification" in cfg.exclude_labels
        assert cfg.skip_parents is True

    def test_custom_values(self) -> None:
        cfg = DaemonConfig({
            "daemon": {
                "consume_state": "Todo",
                "require_labels": ["custom-ready"],
                "exclude_labels": ["wontfix"],
                "skip_parents": False,
            },
        })
        assert cfg.consume_state == "Todo"
        assert cfg.require_labels == ["custom-ready"]
        assert cfg.exclude_labels == ["wontfix"]
        assert cfg.skip_parents is False

    def test_from_toml(self, tmp_path: Path) -> None:
        toml_file = tmp_path / "spec-orch.toml"
        toml_file.write_text(
            '[daemon]\n'
            'consume_state = "Ready"\n'
            'require_labels = ["agent-ready"]\n'
            'exclude_labels = ["blocked"]\n'
            'skip_parents = true\n'
        )
        cfg = DaemonConfig.from_toml(toml_file)
        assert cfg.consume_state == "Ready"
        assert cfg.require_labels == ["agent-ready"]
        assert cfg.skip_parents is True


# ── Daemon: execution qualification ─────────────────────────────


class TestDaemonExecutionQualification:
    def test_polls_with_convention_filters(self, tmp_path: Path) -> None:
        cfg = DaemonConfig({
            "daemon": {
                "lockfile_dir": str(tmp_path / "locks"),
                "consume_state": "Ready",
                "require_labels": ["agent-ready"],
                "exclude_labels": ["blocked"],
                "skip_parents": True,
            },
        })
        daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
        daemon._write_back = MagicMock()
        daemon._readiness_checker = ReadinessChecker()

        mock_client = MagicMock()
        mock_client.list_issues.return_value = []
        mock_controller = MagicMock()

        daemon._poll_and_run(mock_client, mock_controller)

        mock_client.list_issues.assert_called_once()
        call_kwargs = mock_client.list_issues.call_args[1]
        assert call_kwargs["filter_state"] == "Ready"
        assert call_kwargs["filter_labels"] == ["agent-ready"]
        assert call_kwargs["exclude_labels"] == ["blocked"]
        assert call_kwargs["exclude_parents"] is True

    def test_moves_to_in_progress_on_claim(self, tmp_path: Path) -> None:
        cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
        daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
        daemon._write_back = MagicMock()
        daemon._readiness_checker = ReadinessChecker()

        mock_client = MagicMock()
        mock_client.list_issues.return_value = [
            {"id": "uuid-1", "identifier": "SON-99", "description": _COMPLETE_DESC},
        ]

        mock_gate = MagicMock()
        mock_gate.mergeable = True
        mock_gate.failed_conditions = []
        mock_result = MagicMock()
        mock_result.gate = mock_gate
        mock_result.state = RunState.ACCEPTED

        mock_controller = MagicMock()
        mock_controller.advance_to_completion.return_value = mock_result

        daemon._poll_and_run(mock_client, mock_controller)

        mock_client.update_issue_state.assert_any_call("uuid-1", "In Progress")

    def test_moves_to_in_review_after_pr(self, tmp_path: Path) -> None:
        cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
        daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
        daemon._write_back = MagicMock()
        daemon._readiness_checker = ReadinessChecker()

        mock_client = MagicMock()
        mock_client.list_issues.return_value = [
            {"id": "uuid-2", "identifier": "SON-100", "description": _COMPLETE_DESC},
        ]

        mock_gate = MagicMock()
        mock_gate.mergeable = True
        mock_gate.failed_conditions = []
        mock_result = MagicMock()
        mock_result.gate = mock_gate
        mock_result.state = RunState.GATE_EVALUATED
        mock_result.issue.title = "Test"
        mock_result.issue.issue_id = "SON-100"
        mock_result.workspace = tmp_path

        mock_controller = MagicMock()
        mock_controller.advance_to_completion.return_value = mock_result

        with patch("spec_orch.services.github_pr_service.GitHubPRService") as MockGH:
            mock_gh = MockGH.return_value
            mock_gh.create_pr.return_value = "https://github.com/pr/1"

            daemon._poll_and_run(mock_client, mock_controller)

        mock_client.update_issue_state.assert_any_call("uuid-2", "In Review")

    def test_auto_create_pr_returns_bool(self, tmp_path: Path) -> None:
        cfg = DaemonConfig({})
        daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

        mock_result = MagicMock()
        mock_result.state = RunState.ACCEPTED
        assert daemon._auto_create_pr("X", mock_result) is False

        mock_result.state = RunState.GATE_EVALUATED
        mock_result.gate.mergeable = True
        mock_result.gate.failed_conditions = []
        mock_result.issue.title = "T"
        mock_result.workspace = tmp_path

        with patch("spec_orch.services.github_pr_service.GitHubPRService") as MockGH:
            mock_gh = MockGH.return_value
            mock_gh.create_pr.return_value = "https://github.com/pr/2"
            assert daemon._auto_create_pr("Y", mock_result) is True


# ── PromotionService: labels and template ───────────────────────


class TestPromotionServiceConvention:
    def test_promote_to_linear_adds_labels(self) -> None:
        wp = WorkPacket(
            packet_id="wp-1", title="Task",
            builder_prompt="Do it", acceptance_criteria=["Done"],
        )
        plan = ExecutionPlan(
            plan_id="p-1", mission_id="test",
            waves=[Wave(wave_number=0, description="W0", work_packets=[wp])],
        )

        mock_client = MagicMock()
        mock_client.create_issue.return_value = {"id": "uid-1", "identifier": "SON-99"}
        mock_client._resolve_label_id.return_value = "label-uuid"
        mock_client.list_issues.return_value = []

        svc = PromotionService(linear_client=mock_client)
        result = svc.promote(plan, team_key="SON")

        assert result.status == PlanStatus.EXECUTING
        mock_client.query.assert_called()
        update_call = mock_client.query.call_args
        assert "labelIds" in str(update_call)

    def test_issue_description_includes_template_sections(self) -> None:
        wp = WorkPacket(
            packet_id="wp-1", title="Add auth",
            builder_prompt="Implement JWT auth",
            acceptance_criteria=["Login works", "Token valid"],
            files_in_scope=["src/auth.py"],
            verification_commands={"test": ["pytest", "-x"]},
        )
        wave = Wave(wave_number=0, description="Scaffold", work_packets=[wp])

        desc = PromotionService._build_issue_description(wp, "auth-mission", wave)

        assert "## Goal" in desc
        assert "## Non-Goals" in desc
        assert "## Acceptance Criteria" in desc
        assert "- [ ] Login works" in desc
        assert "## Files in Scope" in desc
        assert "`src/auth.py`" in desc
        assert "## Test Requirements" in desc
        assert "pytest" in desc
        assert "## Merge Constraints" in desc

    def test_issue_description_default_test_requirements(self) -> None:
        wp = WorkPacket(packet_id="wp-1", title="Fix bug", builder_prompt="Fix it")
        wave = Wave(wave_number=0, description="Fixes", work_packets=[wp])

        desc = PromotionService._build_issue_description(wp, "bug-fix", wave)
        assert "All existing tests must pass" in desc
