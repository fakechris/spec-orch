from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock

from spec_orch.services.workspace_service import WorkspaceService


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_prepare_issue_workspace_recovers_from_missing_registered_worktree(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init", "-b", "main")
    _git(repo_root, "config", "user.name", "SpecOrch")
    _git(repo_root, "config", "user.email", "spec-orch@example.com")
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "init")

    service = WorkspaceService(repo_root=repo_root)

    workspace = service.prepare_issue_workspace("SPC-1")
    assert workspace.exists()

    backup = repo_root / ".worktrees" / "SPC-1.bak"
    workspace.rename(backup)
    assert not workspace.exists()

    recovered = service.prepare_issue_workspace("SPC-1")

    assert recovered == workspace
    assert recovered.exists()
    assert (recovered / ".git").exists()


def test_prepare_issue_workspace_falls_back_to_scoped_branch_when_issue_branch_in_use(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init", "-b", "main")
    _git(repo_root, "config", "user.name", "SpecOrch")
    _git(repo_root, "config", "user.email", "spec-orch@example.com")
    (repo_root / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "init")

    primary_service = WorkspaceService(repo_root=repo_root)
    primary_workspace = primary_service.prepare_issue_workspace("SPC-1")
    assert primary_workspace.exists()

    sibling_root = tmp_path / "repo-sibling"
    _git(repo_root, "worktree", "add", str(sibling_root), "-b", "sibling-main", "HEAD")

    sibling_service = WorkspaceService(repo_root=sibling_root)
    sibling_workspace = sibling_service.prepare_issue_workspace("SPC-1")

    assert sibling_workspace.exists()
    branch_name = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=sibling_workspace,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert branch_name.startswith("issue/spc-1-")


def test_prepare_issue_workspace_uses_scoped_branch_when_branch_known_checked_out_elsewhere(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    service = WorkspaceService(repo_root=repo_root)
    run_git = Mock()

    monkeypatch.setattr(service, "_is_git_repository", lambda: True)
    monkeypatch.setattr(service, "_prune_worktrees", lambda: None)
    monkeypatch.setattr(service, "_run_git", run_git)
    monkeypatch.setattr(service, "_branch_exists", lambda name: name == "issue/spc-1")
    monkeypatch.setattr(
        service,
        "_branch_checked_out_elsewhere",
        lambda branch_name: branch_name == "issue/spc-1",
        raising=False,
    )

    workspace = service.prepare_issue_workspace("SPC-1")

    assert workspace == repo_root / ".worktrees" / "SPC-1"
    assert run_git.call_args_list == [
        (("branch", service._scoped_issue_branch_name("SPC-1"), "issue/spc-1"),),
        (("worktree", "add", str(workspace), service._scoped_issue_branch_name("SPC-1")),),
    ]
