from __future__ import annotations

import re
from pathlib import Path

from spec_orch.services.plan_parser import PlanData

_PATH_IN_BACKTICKS_RE = re.compile(r"`([^`\n]+)`")


def generate_fixture(
    plan: PlanData,
    issue_id: str,
    *,
    repo_root: Path | None = None,
) -> dict:
    from spec_orch.services.adapter_factory import load_verification_commands

    verify = load_verification_commands(repo_root) if repo_root is not None else {}

    return {
        "issue_id": issue_id,
        "title": plan.title,
        "summary": plan.summary,
        "builder_prompt": generate_builder_prompt(plan),
        "verification_commands": verify,
        "acceptance_criteria": plan.acceptance_criteria,
        "context": {
            "files_to_read": plan.files_to_read,
            "architecture_notes": plan.architecture_notes,
            "constraints": plan.constraints,
        },
    }


def generate_builder_prompt(plan: PlanData) -> str:
    instructions = [_instruction_from_change(change) for change in plan.file_changes]
    numbered = [
        f"{index}. {instruction}" for index, instruction in enumerate(instructions, start=1)
    ]
    next_index = len(numbered) + 1
    numbered.append(f"{next_index}. Run ruff check src/ and fix any lint errors.")
    numbered.append(f"{next_index + 1}. Run pytest tests/ -q to make sure nothing is broken.")
    return "\n".join(numbered)


def _instruction_from_change(change: str) -> str:
    path = _extract_path(change)
    if path is None:
        return change

    if re.search(r"\b(new|create)\b", change, re.IGNORECASE):
        remainder = _remainder_after_path(change, path)
        return f"Create `{path}`{f' {remainder}' if remainder else ''}"

    if re.search(r"\b(modify|update)\b", change, re.IGNORECASE):
        remainder = _remainder_after_path(change, path)
        remainder = re.sub(r"^(to)\s+", "", remainder, flags=re.IGNORECASE)
        return f"In `{path}`, {remainder}".rstrip()

    return change


def _extract_path(change: str) -> str | None:
    match = _PATH_IN_BACKTICKS_RE.search(change)
    if match is None:
        return None
    return match.group(1)


def _remainder_after_path(change: str, path: str) -> str:
    _, _, remainder = change.partition(f"`{path}`")
    return remainder.lstrip(" ,:;-").strip()
