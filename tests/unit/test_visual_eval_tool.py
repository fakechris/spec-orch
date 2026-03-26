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
