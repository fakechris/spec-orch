from __future__ import annotations

import os
from pathlib import Path


def test_find_dotenv_path_prefers_local_worktree_env_over_shared_root(tmp_path: Path) -> None:
    from spec_orch.services.env_files import find_dotenv_path

    shared_root = tmp_path / "shared"
    worktree = tmp_path / "worktrees" / "feature"
    shared_root.mkdir(parents=True)
    worktree.mkdir(parents=True)
    (shared_root / ".env").write_text("SPEC_ORCH_LLM_API_KEY=shared\n", encoding="utf-8")
    (worktree / ".env").write_text("SPEC_ORCH_LLM_API_KEY=local\n", encoding="utf-8")

    env_path = find_dotenv_path(worktree, git_common_dir=shared_root / ".git")

    assert env_path == (worktree / ".env").resolve()


def test_find_dotenv_path_falls_back_to_shared_repo_root(tmp_path: Path) -> None:
    from spec_orch.services.env_files import find_dotenv_path

    shared_root = tmp_path / "shared"
    worktree = tmp_path / "worktrees" / "feature"
    shared_root.mkdir(parents=True)
    worktree.mkdir(parents=True)
    (shared_root / ".env").write_text("SPEC_ORCH_LLM_API_KEY=shared\n", encoding="utf-8")

    env_path = find_dotenv_path(worktree, git_common_dir=shared_root / ".git")

    assert env_path == (shared_root / ".env").resolve()


def test_load_dotenv_bridges_shared_legacy_llm_envs_into_minimax(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from spec_orch.services.env_files import load_dotenv

    shared_root = tmp_path / "shared"
    worktree = tmp_path / "worktrees" / "feature"
    shared_root.mkdir(parents=True)
    worktree.mkdir(parents=True)
    (shared_root / ".env").write_text(
        "\n".join(
            [
                "SPEC_ORCH_LLM_API_KEY=shared-key",
                "SPEC_ORCH_LLM_API_BASE=https://api.minimaxi.com/anthropic",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("SPEC_ORCH_LLM_API_KEY", raising=False)
    monkeypatch.delenv("SPEC_ORCH_LLM_API_BASE", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_ANTHROPIC_BASE_URL", raising=False)

    env_path = load_dotenv(worktree, git_common_dir=shared_root / ".git")

    assert env_path == (shared_root / ".env").resolve()
    assert os.environ["SPEC_ORCH_LLM_API_KEY"] == "shared-key"
    assert os.environ["SPEC_ORCH_LLM_API_BASE"] == "https://api.minimaxi.com/anthropic"
    assert os.environ["MINIMAX_API_KEY"] == "shared-key"
    assert os.environ["MINIMAX_ANTHROPIC_BASE_URL"] == "https://api.minimaxi.com/anthropic"
