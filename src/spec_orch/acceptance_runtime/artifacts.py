"""Artifact persistence for bounded acceptance graph runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from spec_orch.acceptance_runtime.graph_models import AcceptanceGraphRun, AcceptanceStepResult
from spec_orch.services.io import atomic_write_json, atomic_write_text


def graph_run_root(base_dir: Path) -> Path:
    return Path(base_dir) / "acceptance_graph_runs"


def graph_run_dir(base_dir: Path, run_id: str) -> Path:
    return graph_run_root(base_dir) / run_id


def write_graph_run(run_dir: Path, run: AcceptanceGraphRun) -> dict[str, Any]:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = run.to_dict()
    atomic_write_json(run_dir / "graph_run.json", payload)
    return payload


def write_step_artifact(run_dir: Path, index: int, result: AcceptanceStepResult) -> dict[str, str]:
    steps_dir = Path(run_dir) / "steps"
    steps_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{index:02d}-{result.step_key}"
    json_path = steps_dir / f"{base_name}.json"
    atomic_write_json(json_path, result.to_dict())

    markdown_path = ""
    if result.review_markdown:
        markdown_file = steps_dir / f"{base_name}.md"
        atomic_write_text(markdown_file, result.review_markdown.rstrip() + "\n")
        markdown_path = str(markdown_file)

    return {
        "json_path": str(json_path),
        "markdown_path": markdown_path,
    }
