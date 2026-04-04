from __future__ import annotations

from spec_orch.services.path_sanitizer import sanitize_text_artifact_tree


def test_sanitize_text_artifact_tree_rewrites_absolute_paths(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    mission_root = repo_root / "docs/specs/mission-1"
    repo_root.joinpath(".git").mkdir(parents=True)
    text_file = mission_root / "operator/runtime_chain/chain_events.jsonl"
    png_file = mission_root / "rounds/round-01/visual/root.png"
    text_file.parent.mkdir(parents=True, exist_ok=True)
    png_file.parent.mkdir(parents=True, exist_ok=True)

    text_file.write_text(
        "\n".join(
            [
                str(repo_root / "docs/specs/mission-1/rounds/round-01"),
                "/Users/chris/tmp/raw-proof.json",
                "see `/Users/chris/workspace/spec-orch/.venv-py313/bin/python`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    png_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    changed = sanitize_text_artifact_tree(mission_root, repo_root=repo_root)

    assert text_file in changed
    assert png_file not in changed
    sanitized = text_file.read_text(encoding="utf-8")
    assert "/Users/chris/" not in sanitized
    assert "docs/specs/mission-1/rounds/round-01" in sanitized
    assert "<external-path>/tmp/raw-proof.json" in sanitized
    assert "<external-path>/.venv-py313/bin/python" in sanitized
