from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_visual_eval_tool_prints_usage_without_arguments() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(repo_root / "tools" / "visual_eval.py")],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "usage: visual_eval.py <input_json> <output_json>" in result.stderr


def test_visual_eval_tool_returns_non_zero_on_error(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.json"
    input_path.write_text("{}", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "tools" / "visual_eval.py"),
            str(input_path),
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "visual evaluation failed:" in result.stderr
    assert not output_path.exists()
