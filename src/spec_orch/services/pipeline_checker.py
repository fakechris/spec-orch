"""EODF Pipeline Checker — enforces the canonical pipeline stage sequence.

The full EODF closed-loop pipeline is:

  discuss → freeze → approve → plan → promote → run → gate → pr → review → merge → retro

Each stage has a detection function that inspects the repo to determine
whether that stage has been completed for a given mission.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class PipelineStage:
    key: str
    label: str
    command_hint: str
    status: Literal["done", "current", "pending", "skipped"]


PIPELINE_STAGES = [
    ("discuss", "Discuss / Brainstorm", "spec-orch discuss"),
    ("freeze", "Freeze → Spec + Mission", "@spec-orch freeze"),
    ("approve", "Mission Approve", "spec-orch mission approve <id>"),
    ("plan", "Generate Execution Plan", "spec-orch plan <id>"),
    ("promote", "Promote → Linear Issues", "spec-orch promote <id>"),
    ("run", "Execute Work Packets", "spec-orch run <issue>"),
    ("gate", "Quality Gate", "spec-orch gate <issue>"),
    ("pr", "Create Pull Request", "spec-orch create-pr <issue>"),
    ("review", "PR Review", "(automated / manual)"),
    ("merge", "Merge PR", "gh pr merge"),
    ("retro", "Retrospective", "spec-orch retro <id>"),
]


def check_pipeline(mission_id: str, repo_root: Path) -> list[PipelineStage]:
    """Return the pipeline stage list with status for a given mission."""
    specs_dir = repo_root / "docs" / "specs" / mission_id
    mission_path = specs_dir / "mission.json"
    spec_path = specs_dir / "spec.md"
    plan_path = specs_dir / "plan.json"

    mission_data: dict = {}
    if mission_path.exists():
        mission_data = json.loads(mission_path.read_text())

    plan_data: dict = {}
    if plan_path.exists():
        plan_data = json.loads(plan_path.read_text())

    has_spec = spec_path.exists() and spec_path.stat().st_size > 0
    has_mission = bool(mission_data)
    is_approved = mission_data.get("approved_at") is not None
    has_plan = bool(plan_data.get("waves"))
    has_linear_issues = _plan_has_linear_issues(plan_data)
    plan_status = plan_data.get("status", "")

    is_completed = mission_data.get("completed_at") is not None
    has_retro = (specs_dir / "retro.md").exists()

    stage_done: dict[str, bool] = {
        "discuss": has_spec,
        "freeze": has_spec and has_mission,
        "approve": is_approved,
        "plan": has_plan,
        "promote": has_linear_issues,
        "run": plan_status in ("executing", "completed"),
        "gate": is_completed,
        "pr": is_completed,
        "review": is_completed,
        "merge": is_completed,
        "retro": has_retro,
    }

    stages: list[PipelineStage] = []
    found_current = False
    for key, label, hint in PIPELINE_STAGES:
        if stage_done[key]:
            status: Literal["done", "current", "pending", "skipped"] = "done"
        elif not found_current:
            status = "current"
            found_current = True
        else:
            status = "pending"
        stages.append(PipelineStage(key=key, label=label, command_hint=hint, status=status))

    return stages


def next_step(mission_id: str, repo_root: Path) -> PipelineStage | None:
    """Return the next uncompleted pipeline stage, or None if all done."""
    for stage in check_pipeline(mission_id, repo_root):
        if stage.status == "current":
            return stage
    return None


def format_pipeline(stages: list[PipelineStage]) -> str:
    """Format pipeline stages for terminal display."""
    lines: list[str] = []
    icons = {"done": "✓", "current": "→", "pending": "·", "skipped": "○"}
    for s in stages:
        icon = icons[s.status]
        suffix = f"  ({s.command_hint})" if s.status == "current" else ""
        lines.append(f"  [{icon}] {s.label}{suffix}")
    return "\n".join(lines)


def _plan_has_linear_issues(plan_data: dict) -> bool:
    for wave in plan_data.get("waves", []):
        for packet in wave.get("work_packets", []):
            lid = packet.get("linear_issue_id")
            if lid and not lid.startswith("LOCAL-"):
                return True
    return False
