#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from spec_orch.services.visual.playwright_visual_eval import (
    parse_request,
    run_playwright_visual_evaluation,
)


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if len(args) != 2:
        print("usage: visual_eval.py <input_json> <output_json>", file=sys.stderr)
        return 2

    input_json = Path(args[0])
    output_json = Path(args[1])
    try:
        request = parse_request(input_json)
        result = run_playwright_visual_evaluation(request)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
        return 0
    except Exception as exc:
        print(f"visual evaluation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
