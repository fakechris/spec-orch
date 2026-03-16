"""Service for managing Missions — the contract layer above issues.

Missions live as structured JSON metadata alongside canonical spec markdown
in ``docs/specs/<mission_id>/``.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from spec_orch.domain.models import Mission, MissionStatus

if TYPE_CHECKING:
    from spec_orch.spec_import.models import SpecStructure

_MISSION_META = "mission.json"
_SPECS_DIR = "docs/specs"


class MissionService:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root)
        self.specs_dir = self.repo_root / _SPECS_DIR

    def create_mission(
        self,
        title: str,
        *,
        mission_id: str | None = None,
        acceptance_criteria: list[str] | None = None,
        constraints: list[str] | None = None,
    ) -> Mission:
        if mission_id is None:
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            date = datetime.now(UTC).strftime("%Y-%m")
            mission_id = f"{date}-{slug}"

        mission_dir = self.specs_dir / mission_id
        mission_dir.mkdir(parents=True, exist_ok=True)

        spec_path = mission_dir / "spec.md"
        if not spec_path.exists():
            spec_path.write_text(
                f"# {title}\n\n"
                "## Goal\n\n<!-- describe the user value -->\n\n"
                "## Scope\n\n<!-- what's in and out -->\n\n"
                "## Acceptance Criteria\n\n"
                + "".join(f"- {c}\n" for c in (acceptance_criteria or []))
                + "\n## Constraints\n\n"
                + "".join(f"- {c}\n" for c in (constraints or []))
                + "\n## Interface Contracts\n\n<!-- frozen APIs / schemas -->\n"
            )

        mission = Mission(
            mission_id=mission_id,
            title=title,
            spec_path=str(spec_path.relative_to(self.repo_root)),
            acceptance_criteria=acceptance_criteria or [],
            constraints=constraints or [],
        )
        self._write_meta(mission_dir, mission)
        return mission

    def create_mission_from_structure(
        self,
        title: str,
        spec_structure: SpecStructure,
        *,
        mission_id: str | None = None,
    ) -> Mission:
        """Create a mission from a parsed SpecStructure."""
        mission = self.create_mission(
            title,
            mission_id=mission_id,
            acceptance_criteria=spec_structure.acceptance_criteria or None,
            constraints=spec_structure.constraints or None,
        )
        spec_text = spec_structure.to_markdown(title)
        spec_path = self.specs_dir / mission.mission_id / "spec.md"
        spec_path.write_text(spec_text)
        return mission

    def approve_mission(self, mission_id: str) -> Mission:
        mission = self.get_mission(mission_id)
        mission.status = MissionStatus.APPROVED
        mission.approved_at = datetime.now(UTC).isoformat()
        mission_dir = self.specs_dir / mission_id
        self._write_meta(mission_dir, mission)
        return mission

    def get_mission(self, mission_id: str) -> Mission:
        mission_dir = self.specs_dir / mission_id
        meta_path = mission_dir / _MISSION_META
        if not meta_path.exists():
            raise FileNotFoundError(f"Mission not found: {mission_id}")
        data = json.loads(meta_path.read_text())
        if "status" in data and isinstance(data["status"], str):
            data["status"] = MissionStatus(data["status"])
        return Mission(**data)

    def list_missions(self) -> list[Mission]:
        if not self.specs_dir.exists():
            return []
        missions = []
        for meta_path in sorted(self.specs_dir.glob(f"*/{_MISSION_META}")):
            data = json.loads(meta_path.read_text())
            if "status" in data and isinstance(data["status"], str):
                data["status"] = MissionStatus(data["status"])
            missions.append(Mission(**data))
        return missions

    def update_status(self, mission_id: str, status: MissionStatus) -> Mission:
        mission = self.get_mission(mission_id)
        mission.status = status
        if status == MissionStatus.COMPLETED:
            mission.completed_at = datetime.now(UTC).isoformat()
        mission_dir = self.specs_dir / mission_id
        self._write_meta(mission_dir, mission)
        return mission

    @staticmethod
    def _write_meta(mission_dir: Path, mission: Mission) -> None:
        meta_path = mission_dir / _MISSION_META
        meta_path.write_text(
            json.dumps(
                {
                    "mission_id": mission.mission_id,
                    "title": mission.title,
                    "status": mission.status.value,
                    "spec_path": mission.spec_path,
                    "acceptance_criteria": mission.acceptance_criteria,
                    "constraints": mission.constraints,
                    "interface_contracts": mission.interface_contracts,
                    "created_at": mission.created_at,
                    "approved_at": mission.approved_at,
                    "completed_at": mission.completed_at,
                },
                indent=2,
            )
            + "\n"
        )
