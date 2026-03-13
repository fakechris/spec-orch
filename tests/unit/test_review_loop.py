"""Tests for daemon review-loop and merge-readiness features."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon
from spec_orch.services.readiness_checker import ReadinessChecker


def _make_daemon(tmp_path: Path) -> SpecOrchDaemon:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._write_back = MagicMock()
    daemon._readiness_checker = ReadinessChecker()
    return daemon


def test_pr_commits_persisted(tmp_path: Path) -> None:
    daemon = _make_daemon(tmp_path)
    daemon._pr_commits["SPC-99"] = "abc123"
    daemon._save_state()

    daemon2 = _make_daemon(tmp_path)
    assert daemon2._pr_commits.get("SPC-99") == "abc123"


def test_check_review_updates_detects_new_commit(tmp_path: Path) -> None:
    daemon = _make_daemon(tmp_path)
    daemon._processed.add("SPC-50")
    daemon._pr_commits["SPC-50"] = "old_sha_1234"

    client = MagicMock()
    client.list_issues.return_value = [
        {"identifier": "SPC-50", "id": "uid-50"},
    ]

    mock_prs = [
        {
            "number": 10,
            "title": "[SpecOrch] SPC-50: some feature",
            "headRefName": "feat/spc-50",
            "headRefOid": "new_sha_5678",
        },
    ]

    with patch(
        "spec_orch.services.github_pr_service.GitHubPRService.list_open_prs",
        return_value=mock_prs,
    ):
        daemon._check_review_updates(client)

    assert "SPC-50" not in daemon._processed
    assert daemon._pr_commits["SPC-50"] == "new_sha_5678"
    client.update_issue_state.assert_called_once_with("uid-50", "Ready")


def test_check_review_updates_skips_same_commit(tmp_path: Path) -> None:
    daemon = _make_daemon(tmp_path)
    daemon._processed.add("SPC-51")
    daemon._pr_commits["SPC-51"] = "same_sha"

    client = MagicMock()

    mock_prs = [
        {
            "number": 11,
            "title": "[SpecOrch] SPC-51: no change",
            "headRefName": "feat/spc-51",
            "headRefOid": "same_sha",
        },
    ]

    with patch(
        "spec_orch.services.github_pr_service.GitHubPRService.list_open_prs",
        return_value=mock_prs,
    ):
        daemon._check_review_updates(client)

    assert "SPC-51" in daemon._processed
    client.update_issue_state.assert_not_called()


def test_check_review_updates_no_pr_commits(tmp_path: Path) -> None:
    """Early exit when no PRs have been tracked."""
    daemon = _make_daemon(tmp_path)
    client = MagicMock()
    daemon._check_review_updates(client)
    client.list_issues.assert_not_called()


def test_check_review_updates_no_substring_false_match(tmp_path: Path) -> None:
    """SPC-5 must NOT match a PR titled '[SpecOrch] SPC-50: ...'."""
    daemon = _make_daemon(tmp_path)
    daemon._processed.add("SPC-5")
    daemon._pr_commits["SPC-5"] = "old_sha"

    client = MagicMock()

    mock_prs = [
        {
            "number": 12,
            "title": "[SpecOrch] SPC-50: unrelated feature",
            "headRefName": "feat/spc-50",
            "headRefOid": "new_sha",
        },
    ]

    with patch(
        "spec_orch.services.github_pr_service.GitHubPRService.list_open_prs",
        return_value=mock_prs,
    ):
        daemon._check_review_updates(client)

    assert "SPC-5" in daemon._processed
    client.update_issue_state.assert_not_called()


def test_check_mergeable_fetch_failure(tmp_path: Path) -> None:
    from spec_orch.services.github_pr_service import GitHubPRService

    svc = GitHubPRService()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="network error")
        result = svc.check_mergeable(tmp_path, branch="feat/x")
        assert result["mergeable"] is False
        assert "git fetch failed" in result["conflicting_files"]


def test_github_pr_list_open_prs(tmp_path: Path) -> None:
    from spec_orch.services.github_pr_service import GitHubPRService

    svc = GitHubPRService()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"number":1,"title":"[SpecOrch] SPC-1","headRefName":"feat/spc-1","headRefOid":"abc"}]',
        )
        result = svc.list_open_prs(tmp_path)
        assert len(result) == 1
        assert result[0]["headRefOid"] == "abc"


def test_github_pr_auto_rebase_success(tmp_path: Path) -> None:
    from spec_orch.services.github_pr_service import GitHubPRService

    svc = GitHubPRService()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert svc.auto_rebase(tmp_path) is True
        assert mock_run.call_count == 3  # fetch + rebase + push


def test_github_pr_auto_rebase_conflict(tmp_path: Path) -> None:
    from spec_orch.services.github_pr_service import GitHubPRService

    svc = GitHubPRService()
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:  # rebase fails
            return MagicMock(returncode=1)
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=side_effect):
        assert svc.auto_rebase(tmp_path) is False
