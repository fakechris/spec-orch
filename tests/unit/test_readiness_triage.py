"""Tests for readiness triage: ReadinessChecker, daemon triage, reply detection."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from spec_orch.services.reaction_engine import ReactionDecision
from spec_orch.services.readiness_checker import ReadinessChecker, ReadinessResult

# ── ReadinessResult formatting ──


def test_readiness_result_format_comment_with_fields_and_questions() -> None:
    result = ReadinessResult(
        ready=False,
        missing_fields=["Goal", "Files in Scope"],
        questions=["What is the goal?", "Which files?"],
    )
    comment = result.format_comment()
    assert "Clarification Needed" in comment
    assert "Goal" in comment
    assert "Files in Scope" in comment
    assert "1. What is the goal?" in comment
    assert "2. Which files?" in comment


def test_readiness_result_format_comment_questions_only() -> None:
    result = ReadinessResult(
        ready=False,
        questions=["Is this a bug fix or feature?"],
    )
    comment = result.format_comment()
    assert "1. Is this a bug fix or feature?" in comment
    assert "Missing Fields" not in comment


# ── ReadinessChecker rule checks ──


def test_empty_description_fails() -> None:
    checker = ReadinessChecker()
    result = checker.check("")
    assert not result.ready
    assert "Goal" in result.missing_fields


def test_none_description_fails() -> None:
    checker = ReadinessChecker()
    result = checker.check(None)
    assert not result.ready


COMPLETE_DESCRIPTION = """\
## Goal

Implement the frobulator widget.

## Acceptance Criteria

- [ ] Frobulator renders correctly
- [ ] Tests pass

## Files in Scope

- `src/frobulator.py`
"""


def test_complete_description_passes() -> None:
    checker = ReadinessChecker()
    result = checker.check(COMPLETE_DESCRIPTION)
    assert result.ready
    assert result.missing_fields == []
    assert result.questions == []


def test_missing_goal_fails() -> None:
    desc = """\
## Acceptance Criteria

- [ ] Something works

## Files in Scope

- `src/foo.py`
"""
    checker = ReadinessChecker()
    result = checker.check(desc)
    assert not result.ready
    assert "Goal" in result.missing_fields


def test_missing_acceptance_criteria_fails() -> None:
    desc = """\
## Goal

Do something important.

## Files in Scope

- `src/foo.py`
"""
    checker = ReadinessChecker()
    result = checker.check(desc)
    assert not result.ready
    assert "Acceptance Criteria" in result.missing_fields


def test_missing_files_in_scope_fails() -> None:
    desc = """\
## Goal

Do something important.

## Acceptance Criteria

- [ ] It works
"""
    checker = ReadinessChecker()
    result = checker.check(desc)
    assert not result.ready
    assert "Files in Scope" in result.missing_fields


def test_empty_goal_section_fails() -> None:
    """Goal heading present but with no content should still fail."""
    desc = """\
## Goal

## Acceptance Criteria

- [ ] Something works

## Files in Scope

- `src/foo.py`
"""
    checker = ReadinessChecker()
    result = checker.check(desc)
    assert not result.ready
    assert "Goal" in result.missing_fields


def test_bullet_backtick_counts_as_files() -> None:
    """Backtick-quoted bullet items count as Files in Scope even without heading."""
    desc = """\
## Goal

Fix the widget.

## Acceptance Criteria

- [ ] Widget fixed

Some context about files:
- `src/widget.py`
"""
    checker = ReadinessChecker()
    result = checker.check(desc)
    assert result.ready


def test_checkbox_counts_as_acceptance() -> None:
    """Checkboxes anywhere count as acceptance criteria."""
    desc = """\
## Goal

Build it.

- [ ] Works correctly

## Files in Scope

- `src/main.py`
"""
    checker = ReadinessChecker()
    result = checker.check(desc)
    assert result.ready


# ── ReadinessChecker with LLM ──


def test_llm_check_ready() -> None:
    planner = MagicMock()
    planner.brainstorm.return_value = "READY"
    checker = ReadinessChecker(planner=planner)
    result = checker.check(COMPLETE_DESCRIPTION)
    assert result.ready
    planner.brainstorm.assert_called_once()
    call_kwargs = planner.brainstorm.call_args[1]
    assert "conversation_history" in call_kwargs


def test_llm_check_questions() -> None:
    planner = MagicMock()
    planner.brainstorm.return_value = (
        "1. What error handling is expected?\n2. Should this support concurrent access?"
    )
    checker = ReadinessChecker(planner=planner)
    result = checker.check(COMPLETE_DESCRIPTION)
    assert not result.ready
    assert len(result.questions) == 2
    assert "error handling" in result.questions[0]


def test_llm_check_exception_defaults_ready() -> None:
    planner = MagicMock()
    planner.brainstorm.side_effect = RuntimeError("API down")
    checker = ReadinessChecker(planner=planner)
    result = checker.check(COMPLETE_DESCRIPTION)
    assert result.ready


# ── DaemonConfig defaults ──


def test_daemon_config_defaults_no_require_labels() -> None:
    from spec_orch.services.daemon import DaemonConfig

    config = DaemonConfig({})
    assert config.require_labels == []
    assert "blocked" in config.exclude_labels
    assert "needs-clarification" in config.exclude_labels


def test_daemon_config_custom_labels() -> None:
    from spec_orch.services.daemon import DaemonConfig

    config = DaemonConfig(
        {
            "daemon": {
                "require_labels": ["agent-ready"],
                "exclude_labels": ["blocked"],
            }
        }
    )
    assert config.require_labels == ["agent-ready"]
    assert config.exclude_labels == ["blocked"]


# ── Daemon triage integration ──


def test_daemon_triage_skips_incomplete_issue(tmp_path: Path) -> None:
    from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon

    config = DaemonConfig({})
    daemon = SpecOrchDaemon(config=config, repo_root=tmp_path)

    from spec_orch.services.readiness_checker import ReadinessChecker

    daemon._readiness_checker = ReadinessChecker()
    daemon._triaged = set()

    client = MagicMock()
    raw_issue = {
        "identifier": "SON-99",
        "id": "uuid-99",
        "description": "Fix something",
    }

    result = daemon._triage_issue(client, raw_issue)
    assert result is False
    assert "SON-99" in daemon._triaged
    client.add_comment.assert_called_once()
    comment_body = client.add_comment.call_args[0][1]
    assert "Clarification Needed" in comment_body
    client.add_label.assert_called_once_with("uuid-99", "needs-clarification")


def test_daemon_triage_passes_complete_issue(tmp_path: Path) -> None:
    from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon

    config = DaemonConfig({})
    daemon = SpecOrchDaemon(config=config, repo_root=tmp_path)

    from spec_orch.services.readiness_checker import ReadinessChecker

    daemon._readiness_checker = ReadinessChecker()
    daemon._triaged = set()

    client = MagicMock()
    raw_issue = {
        "identifier": "SON-100",
        "id": "uuid-100",
        "description": COMPLETE_DESCRIPTION,
    }

    result = daemon._triage_issue(client, raw_issue)
    assert result is True
    client.add_comment.assert_not_called()
    client.add_label.assert_not_called()


def test_daemon_triage_context_assembly_error_falls_back_to_plain_check(tmp_path: Path) -> None:
    from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon

    config = DaemonConfig({})
    daemon = SpecOrchDaemon(config=config, repo_root=tmp_path)
    daemon._triaged = set()
    daemon._readiness_checker = MagicMock()
    daemon._readiness_checker.check.return_value = ReadinessResult(ready=True)
    daemon._context_assembler = MagicMock()
    daemon._context_assembler.assemble.side_effect = RuntimeError("boom")

    controller = MagicMock()
    controller.workspace_service.issue_workspace_path.return_value = tmp_path
    client = MagicMock()
    raw_issue = {
        "identifier": "SON-CTX",
        "id": "uuid-ctx",
        "description": COMPLETE_DESCRIPTION,
    }

    result = daemon._triage_issue(client, raw_issue, controller)
    assert result is True
    daemon._readiness_checker.check.assert_called_with(COMPLETE_DESCRIPTION)


def test_daemon_triage_skips_already_triaged_without_reposting(tmp_path: Path) -> None:
    from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon

    config = DaemonConfig({})
    daemon = SpecOrchDaemon(config=config, repo_root=tmp_path)

    from spec_orch.services.readiness_checker import ReadinessChecker

    daemon._readiness_checker = ReadinessChecker()
    daemon._triaged = {"SON-101"}

    client = MagicMock()
    raw_issue = {
        "identifier": "SON-101",
        "id": "uuid-101",
        "description": "",
    }

    result = daemon._triage_issue(client, raw_issue)
    assert result is False
    client.add_comment.assert_not_called()


# ── Reply detection ──


def test_check_clarification_replies_removes_label(tmp_path: Path) -> None:
    from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon

    config = DaemonConfig({"linear": {"team_key": "SON"}})
    daemon = SpecOrchDaemon(config=config, repo_root=tmp_path)
    daemon._triaged = {"SON-200"}

    client = MagicMock()
    client.list_issues.return_value = [
        {"identifier": "SON-200", "id": "uid-200"},
    ]
    client.list_comments.return_value = [
        {"body": "## SpecOrch: Clarification Needed\n\nSome questions...", "user": {"id": "bot"}},
        {"body": "Here is the answer to your questions.", "user": {"id": "human"}},
    ]

    daemon._check_clarification_replies(client)

    client.remove_label.assert_called_once_with("uid-200", "needs-clarification")
    assert "SON-200" not in daemon._triaged


def test_check_clarification_replies_no_reply_keeps_label(tmp_path: Path) -> None:
    from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon

    config = DaemonConfig({"linear": {"team_key": "SON"}})
    daemon = SpecOrchDaemon(config=config, repo_root=tmp_path)
    daemon._triaged = {"SON-201"}

    client = MagicMock()
    client.list_issues.return_value = [
        {"identifier": "SON-201", "id": "uid-201"},
    ]
    client.list_comments.return_value = [
        {"body": "## SpecOrch: Clarification Needed\n\nSome questions...", "user": {"id": "bot"}},
    ]

    daemon._check_clarification_replies(client)

    client.remove_label.assert_not_called()
    assert "SON-201" in daemon._triaged


def test_check_clarification_replies_handles_api_error(tmp_path: Path) -> None:
    from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon

    config = DaemonConfig({"linear": {"team_key": "SON"}})
    daemon = SpecOrchDaemon(config=config, repo_root=tmp_path)

    client = MagicMock()
    client.list_issues.side_effect = RuntimeError("API error")

    daemon._check_clarification_replies(client)


def test_daemon_run_reactions_auto_merge_once(tmp_path: Path) -> None:
    from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon

    daemon = SpecOrchDaemon(
        config=DaemonConfig({"linear": {"team_key": "SON"}}), repo_root=tmp_path
    )
    daemon._reaction_engine = MagicMock()
    daemon._reaction_engine.evaluate.return_value = [
        ReactionDecision(rule_name="approved-and-green", action="auto_merge", reason="ok")
    ]

    client = MagicMock()
    client.list_issues.return_value = [{"identifier": "SON-1", "id": "uid-1"}]
    gh = MagicMock()
    gh.get_pr_signal.return_value = {"review_decision": "APPROVED", "checks_passed": True}
    gh.merge_pr.return_value = True

    pr_meta = {"SON-1": {"number": 12, "sha": "abc123"}}
    daemon._run_reactions(client, gh, pr_meta)
    daemon._run_reactions(client, gh, pr_meta)

    gh.merge_pr.assert_called_once()
    client.update_issue_state.assert_called_once_with("uid-1", "Done")


def test_daemon_run_reactions_comment_once(tmp_path: Path) -> None:
    from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon

    daemon = SpecOrchDaemon(
        config=DaemonConfig({"linear": {"team_key": "SON"}}), repo_root=tmp_path
    )
    daemon._reaction_engine = MagicMock()
    daemon._reaction_engine.evaluate.return_value = [
        ReactionDecision(rule_name="ci-failed", action="comment_ci_failed", reason="ci")
    ]

    client = MagicMock()
    client.list_issues.return_value = [{"identifier": "SON-2", "id": "uid-2"}]
    gh = MagicMock()
    gh.get_pr_signal.return_value = {"checks_failed": True}

    pr_meta = {"SON-2": {"number": 21, "sha": "def456"}}
    daemon._run_reactions(client, gh, pr_meta)
    daemon._run_reactions(client, gh, pr_meta)

    assert client.add_comment.call_count == 1


def test_daemon_run_reactions_merge_method_from_params(tmp_path: Path) -> None:
    from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon

    daemon = SpecOrchDaemon(
        config=DaemonConfig({"linear": {"team_key": "SON"}}), repo_root=tmp_path
    )
    daemon._reaction_engine = MagicMock()
    daemon._reaction_engine.evaluate.return_value = [
        ReactionDecision(
            rule_name="approved-and-green",
            action="auto_merge",
            reason="ok",
            params={"merge_method": "merge"},
        )
    ]

    client = MagicMock()
    client.list_issues.return_value = [{"identifier": "SON-1", "id": "uid-1"}]
    gh = MagicMock()
    gh.get_pr_signal.return_value = {
        "review_decision": "APPROVED",
        "checks_passed": True,
        "mergeable": True,
    }
    gh.merge_pr.return_value = True

    pr_meta = {"SON-1": {"number": 12, "sha": "abc123"}}
    daemon._run_reactions(client, gh, pr_meta)

    gh.merge_pr.assert_called_once()
    assert gh.merge_pr.call_args.kwargs["method"] == "merge"


def test_daemon_run_reactions_requeue_ready(tmp_path: Path) -> None:
    from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon

    daemon = SpecOrchDaemon(
        config=DaemonConfig({"linear": {"team_key": "SON"}}), repo_root=tmp_path
    )
    daemon._reaction_engine = MagicMock()
    daemon._reaction_engine.evaluate.return_value = [
        ReactionDecision(rule_name="rq", action="requeue_ready", reason="r")
    ]

    client = MagicMock()
    client.list_issues.return_value = [{"identifier": "SON-9", "id": "uid-9"}]
    gh = MagicMock()
    gh.get_pr_signal.return_value = {"checks_failed": True}

    pr_meta = {"SON-9": {"number": 99, "sha": "abc123"}}
    daemon._run_reactions(client, gh, pr_meta)
    daemon._run_reactions(client, gh, pr_meta)

    client.update_issue_state.assert_called_once_with("uid-9", "Ready")


def test_daemon_run_reactions_writes_trace_jsonl(tmp_path: Path) -> None:
    from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon

    daemon = SpecOrchDaemon(
        config=DaemonConfig({"linear": {"team_key": "SON"}}), repo_root=tmp_path
    )
    daemon._reaction_engine = MagicMock()
    daemon._reaction_engine.evaluate.return_value = [
        ReactionDecision(rule_name="noop", action="noop", reason="n")
    ]

    client = MagicMock()
    gh = MagicMock()
    gh.get_pr_signal.return_value = {"checks_failed": True}

    pr_meta = {"SON-3": {"number": 7, "sha": "fff"}}
    daemon._run_reactions(client, gh, pr_meta)

    trace = tmp_path / ".spec_orch" / "reactions_trace.jsonl"
    assert trace.exists()
    lines = trace.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["action"] == "noop"
    assert rec["issue_id"] == "SON-3"
