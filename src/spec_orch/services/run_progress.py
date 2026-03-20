"""RunProgressSnapshot — pipeline stage checkpointing for long-task continuity.

Writes a progress.json after each pipeline stage completes, allowing the
daemon to skip already-completed stages when retrying a failed run.

Inspired by Factory.ai Missions (milestone-based checkpointing) and
oh-my-openagent Sisyphus (todo enforcer / resume mechanism).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from spec_orch.services.io import atomic_write_json

logger = logging.getLogger(__name__)


@dataclass
class StageCheckpoint:
    """Record of a completed pipeline stage."""

    stage: str
    completed_at: float
    success: bool
    detail: str = ""


@dataclass
class RunProgressSnapshot:
    """Persistent progress state for a single run."""

    run_id: str
    issue_id: str
    stages: list[StageCheckpoint] = field(default_factory=list)
    current_stage: str = ""
    started_at: float = 0.0
    last_updated: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def mark_stage_complete(
        self,
        stage: str,
        success: bool = True,
        detail: str = "",
    ) -> None:
        self.stages.append(
            StageCheckpoint(
                stage=stage,
                completed_at=time.time(),
                success=success,
                detail=detail,
            )
        )
        self.last_updated = time.time()

    def mark_stage_start(self, stage: str) -> None:
        self.current_stage = stage
        self.last_updated = time.time()

    def completed_stage_names(self) -> set[str]:
        return {s.stage for s in self.stages if s.success}

    def is_stage_completed(self, stage: str) -> bool:
        return stage in self.completed_stage_names()

    def save(self, workspace: Path) -> Path:
        path = workspace / "progress.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        atomic_write_json(path, data)
        return path

    @classmethod
    def load(cls, workspace: Path) -> RunProgressSnapshot | None:
        path = workspace / "progress.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            stages = [StageCheckpoint(**s) for s in data.get("stages", [])]
            return cls(
                run_id=data.get("run_id", ""),
                issue_id=data.get("issue_id", ""),
                stages=stages,
                current_stage=data.get("current_stage", ""),
                started_at=data.get("started_at", 0.0),
                last_updated=data.get("last_updated", 0.0),
                metadata=data.get("metadata", {}),
            )
        except (json.JSONDecodeError, TypeError, KeyError):
            logger.warning("Failed to load progress from %s", path)
            return None

    @classmethod
    def create(cls, run_id: str, issue_id: str) -> RunProgressSnapshot:
        return cls(
            run_id=run_id,
            issue_id=issue_id,
            started_at=time.time(),
            last_updated=time.time(),
        )

    def is_stalled(self, timeout_seconds: float = 3600) -> bool:
        """Check if the run appears to be stalled."""
        if not self.current_stage:
            return False
        elapsed = time.time() - self.last_updated
        return elapsed > timeout_seconds
