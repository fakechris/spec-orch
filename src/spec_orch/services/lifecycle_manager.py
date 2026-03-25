"""Mission lifecycle state machine.

Manages the full lifecycle of a Mission from approval through
planning, promotion, execution, retrospective, and evolution.
"""

from __future__ import annotations

import enum
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.domain.models import Issue, IssueContext
from spec_orch.services.context_assembler import ContextAssembler
from spec_orch.services.event_bus import EventBus, get_event_bus
from spec_orch.services.io import atomic_write_json
from spec_orch.services.node_context_registry import get_node_context_spec

logger = logging.getLogger(__name__)


class MissionPhase(enum.StrEnum):
    APPROVED = "approved"
    PLANNING = "planning"
    PLANNED = "planned"
    PROMOTING = "promoting"
    EXECUTING = "executing"
    ALL_DONE = "all_done"
    RETROSPECTING = "retrospecting"
    EVOLVING = "evolving"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class MissionState:
    mission_id: str
    phase: MissionPhase
    issue_ids: list[str] = field(default_factory=list)
    completed_issues: list[str] = field(default_factory=list)
    error: str | None = None
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    current_round: int = 0
    round_orchestrator_state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["phase"] = self.phase.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MissionState:
        data = dict(data)
        data["phase"] = MissionPhase(data["phase"])
        return cls(**data)


class MissionLifecycleManager:
    """Drives Mission through the full lifecycle.

    Human decision points:
    - APPROVED: user must explicitly approve spec
    - PLANNED: optionally review plan before promote

    All other transitions are automatic.
    """

    STATE_FILE = "lifecycle_state.json"

    def __init__(
        self,
        repo_root: Path,
        event_bus: EventBus | None = None,
        round_orchestrator: Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self._bus = event_bus or get_event_bus()
        self._round_orchestrator = round_orchestrator
        self._states: dict[str, MissionState] = {}
        self._context_assembler = ContextAssembler()
        self._memory: Any | None = None
        self._load_state()

    def _get_memory(self) -> Any | None:
        if self._memory is not None:
            return self._memory
        try:
            from spec_orch.services.memory.service import get_memory_service

            self._memory = get_memory_service(repo_root=self.repo_root)
        except Exception:
            from spec_orch.services.event_bus import emit_fallback_safe

            emit_fallback_safe(
                "LifecycleManager",
                "memory_service",
                "no_memory",
                "MemoryService initialization failed",
            )
        return self._memory

    def _state_path(self) -> Path:
        d = self.repo_root / ".spec_orch_runs"
        d.mkdir(parents=True, exist_ok=True)
        return d / self.STATE_FILE

    def _load_state(self) -> None:
        path = self._state_path()
        if path.exists():
            try:
                data = json.loads(path.read_text())
                for mid, sd in data.items():
                    self._states[mid] = MissionState.from_dict(sd)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                logger.warning("Failed to load lifecycle state, starting fresh")

    def _save_state(self) -> None:
        path = self._state_path()
        data = {mid: ms.to_dict() for mid, ms in self._states.items()}
        atomic_write_json(path, data)

    def get_state(self, mission_id: str) -> MissionState | None:
        return self._states.get(mission_id)

    def all_states(self) -> dict[str, MissionState]:
        return dict(self._states)

    def _transition(self, mission_id: str, new_phase: MissionPhase, **extra: Any) -> MissionState:
        state = self._states.get(mission_id)
        old_phase = state.phase.value if state else "none"

        if state is None:
            state = MissionState(mission_id=mission_id, phase=new_phase)
            self._states[mission_id] = state
        else:
            state.phase = new_phase
            state.updated_at = datetime.now(UTC).isoformat()

        if "error" in extra:
            state.error = extra.pop("error")
        else:
            state.error = None

        self._save_state()
        self._bus.emit_mission_state(mission_id, old_phase, new_phase.value, **extra)
        logger.info("Mission %s: %s → %s", mission_id, old_phase, new_phase.value)
        return state

    def begin_tracking(self, mission_id: str) -> MissionState:
        """Start tracking an approved mission."""
        return self._transition(mission_id, MissionPhase.APPROVED)

    def start_planning(self, mission_id: str) -> MissionState:
        return self._transition(mission_id, MissionPhase.PLANNING)

    def plan_complete(self, mission_id: str, issue_ids: list[str] | None = None) -> MissionState:
        state = self._transition(mission_id, MissionPhase.PLANNED)
        if issue_ids:
            state.issue_ids = issue_ids
            self._save_state()
        return state

    def start_promoting(self, mission_id: str) -> MissionState:
        return self._transition(mission_id, MissionPhase.PROMOTING)

    def promotion_complete(self, mission_id: str, issue_ids: list[str]) -> MissionState:
        state = self._transition(mission_id, MissionPhase.EXECUTING)
        state.issue_ids = issue_ids
        state.completed_issues = []
        state.current_round = 0
        state.round_orchestrator_state = {}
        self._save_state()
        return state

    def mark_issue_done(self, mission_id: str, issue_id: str) -> MissionState | None:
        """Record an issue completion. Transitions to ALL_DONE if all done."""
        state = self._states.get(mission_id)
        if state is None or state.phase != MissionPhase.EXECUTING:
            return state

        if issue_id not in state.completed_issues:
            state.completed_issues.append(issue_id)
            state.updated_at = datetime.now(UTC).isoformat()
            self._save_state()

            self._bus.emit_issue_state(
                issue_id,
                "done",
                mission_id=mission_id,
                progress=f"{len(state.completed_issues)}/{len(state.issue_ids)}",
            )

        if set(state.completed_issues) >= set(state.issue_ids) and state.issue_ids:
            return self._transition(mission_id, MissionPhase.ALL_DONE)

        return state

    def start_retrospective(self, mission_id: str) -> MissionState:
        return self._transition(mission_id, MissionPhase.RETROSPECTING)

    def start_evolution(self, mission_id: str) -> MissionState:
        return self._transition(mission_id, MissionPhase.EVOLVING)

    def mark_completed(self, mission_id: str) -> MissionState:
        return self._transition(mission_id, MissionPhase.COMPLETED)

    def mark_failed(self, mission_id: str, error: str) -> MissionState:
        return self._transition(mission_id, MissionPhase.FAILED, error=error)

    def retry(self, mission_id: str) -> MissionState:
        """Reset a mission to APPROVED so it can be re-advanced."""
        return self._transition(mission_id, MissionPhase.APPROVED)

    def auto_advance(self, mission_id: str) -> MissionState | None:
        """Attempt to advance a mission through automated phases.

        Called by the daemon on each tick. Only transitions that don't
        require human approval are executed here.
        """
        state = self._states.get(mission_id)
        if state is None:
            return None

        if state.phase == MissionPhase.APPROVED:
            return self._do_plan(mission_id)
        if state.phase == MissionPhase.PLANNED:
            return self._do_promote(mission_id)
        if state.phase == MissionPhase.EXECUTING:
            if state.round_orchestrator_state.get("paused"):
                return state
            return self._do_execute(mission_id)
        if state.phase == MissionPhase.ALL_DONE:
            return self._do_retro_and_evolve(mission_id)
        return state

    def _do_plan(self, mission_id: str) -> MissionState:
        self.start_planning(mission_id)
        try:
            plan_result = self._run_plan(mission_id)
            issue_ids = [
                wp.get("title", f"packet-{i}")
                for w in plan_result.get("waves", [])
                for i, wp in enumerate(w.get("work_packets", []))
            ]
            return self.plan_complete(mission_id, issue_ids)
        except Exception as exc:
            logger.exception("Planning failed for %s", mission_id)
            return self.mark_failed(mission_id, f"Planning failed: {exc}")

    def _do_promote(self, mission_id: str) -> MissionState:
        self.start_promoting(mission_id)
        try:
            issue_ids = self._run_promote(mission_id)
            return self.promotion_complete(mission_id, issue_ids)
        except Exception as exc:
            logger.exception("Promotion failed for %s", mission_id)
            return self.mark_failed(mission_id, f"Promotion failed: {exc}")

    def _do_execute(self, mission_id: str) -> MissionState:
        state = self._states[mission_id]
        if self._round_orchestrator is None:
            return state
        if state.round_orchestrator_state.get("paused"):
            return state

        from spec_orch.services.parallel_run_controller import ParallelRunController

        try:
            plan = ParallelRunController.load_plan(mission_id, self.repo_root)
            result = self._round_orchestrator.run_supervised(
                mission_id=mission_id,
                plan=plan,
                initial_round=state.current_round,
            )
            if result.rounds:
                state.current_round = result.rounds[-1].round_id
            if result.paused:
                blocking_questions: list[str] = []
                if result.last_decision is not None:
                    blocking_questions = list(result.last_decision.blocking_questions)
                state.round_orchestrator_state = {
                    "paused": True,
                    "blocking_questions": blocking_questions,
                }
                self._save_state()
                return state
            state.round_orchestrator_state = {}
            self._save_state()
            if result.completed:
                return self._transition(mission_id, MissionPhase.ALL_DONE)
            if result.max_rounds_hit:
                return self.mark_failed(mission_id, "max_rounds_exhausted")
            return state
        except Exception as exc:
            logger.exception("Execution failed for %s", mission_id)
            return self.mark_failed(mission_id, f"Execution failed: {exc}")

    def _do_retro_and_evolve(self, mission_id: str) -> MissionState:
        try:
            self.start_retrospective(mission_id)
            self._run_retrospective(mission_id)
            self.start_evolution(mission_id)
            self._run_evolution(mission_id)
            return self.mark_completed(mission_id)
        except Exception as exc:
            logger.exception("Retro/evolution failed for %s", mission_id)
            return self.mark_failed(mission_id, f"Retro/evolution failed: {exc}")

    def _run_plan(self, mission_id: str) -> dict[str, Any]:
        """Execute planning via the Scoper LLM."""
        from spec_orch.services.mission_service import MissionService
        from spec_orch.services.scoper_adapter import LiteLLMScoperAdapter

        ms = MissionService(self.repo_root)
        mission = ms.get_mission(mission_id)
        spec_path = self.repo_root / mission.spec_path
        spec_text = spec_path.read_text() if spec_path.exists() else ""

        cfg = self._load_planner_config()
        if cfg is None:
            raise RuntimeError("No planner configured — cannot auto-plan")

        evidence_ctx = self._gather_evidence()
        scoper = LiteLLMScoperAdapter(
            model=cfg["model"],
            api_type=cfg.get("api_type", "anthropic"),
            api_key=cfg.get("api_key"),
            api_base=cfg.get("api_base"),
            token_command=cfg.get("token_command"),
            evidence_context=evidence_ctx,
        )
        plan = scoper.scope(
            mission=mission,
            codebase_context={"spec_content": spec_text, "file_tree": ""},
            context=self._context_assembler.assemble(
                get_node_context_spec("scoper"),
                Issue(
                    issue_id=mission.mission_id,
                    title=mission.title,
                    summary=spec_text,
                    context=IssueContext(
                        files_to_read=[],
                        constraints=list(mission.constraints),
                    ),
                    acceptance_criteria=list(mission.acceptance_criteria),
                ),
                self.repo_root,
                memory=self._get_memory(),
            ),
        )
        plan_dir = self.repo_root / "docs" / "specs" / mission_id
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plan_dir / "plan.json"
        plan_dict = asdict(plan)
        atomic_write_json(plan_path, plan_dict, default=str)
        return plan_dict

    def _run_promote(self, mission_id: str) -> list[str]:
        """Create Linear issues from plan."""
        from spec_orch.services.promotion_service import (
            PromotionService,
            load_plan,
        )

        plan_path = self.repo_root / "docs" / "specs" / mission_id / "plan.json"
        plan = load_plan(plan_path)
        svc = PromotionService()
        promoted = svc.promote(plan)
        return [
            wp.linear_issue_id or wp.title for wave in promoted.waves for wp in wave.work_packets
        ]

    def _run_retrospective(self, mission_id: str) -> None:
        logger.info("Running retrospective for %s", mission_id)

    def _run_evolution(self, mission_id: str) -> None:
        logger.info("Running evolution for %s", mission_id)
        try:
            from spec_orch.services.evidence_analyzer import EvidenceAnalyzer

            analyzer = EvidenceAnalyzer(self.repo_root)
            summary = analyzer.analyze()
            logger.info(
                "Evidence summary for %s: %d runs analyzed",
                mission_id,
                summary.total_runs,
            )
        except Exception:
            logger.warning("Evidence analysis skipped", exc_info=True)

    def _load_planner_config(self) -> dict[str, Any] | None:
        config_path = self.repo_root / "spec-orch.toml"
        if not config_path.exists():
            return None
        try:
            import os
            import tomllib

            with config_path.open("rb") as f:
                raw = tomllib.load(f)
            cfg: dict[str, Any] = raw.get("planner", {})
            if not cfg.get("model"):
                return None
            if env := cfg.get("api_key_env"):
                cfg["api_key"] = os.environ.get(env)
            if env := cfg.get("api_base_env"):
                cfg["api_base"] = os.environ.get(env)
            return cfg
        except Exception:
            logger.exception("Failed to load planner config")
            return None

    def _gather_evidence(self) -> str | None:
        try:
            from spec_orch.services.evidence_analyzer import EvidenceAnalyzer

            analyzer = EvidenceAnalyzer(self.repo_root)
            summary = analyzer.analyze()
            return analyzer.format_as_llm_context(summary)
        except Exception:
            logger.exception("Failed to gather evidence")
            return None

    def inject_btw(self, issue_id: str, message: str, channel: str) -> bool:
        """Inject /btw context into a running issue.

        Writes to btw_context.md in the issue's run directory so the
        builder prompt picks it up on next retry.
        """
        for state in self._states.values():
            if (
                state.phase == MissionPhase.EXECUTING
                and issue_id in state.issue_ids
                and issue_id not in state.completed_issues
            ):
                btw_dir = self.repo_root / ".spec_orch_runs" / issue_id
                btw_dir.mkdir(parents=True, exist_ok=True)
                btw_path = btw_dir / "btw_context.md"
                timestamp = datetime.now(UTC).isoformat()
                with open(btw_path, "a") as f:
                    f.write(f"\n## /btw [{channel}] {timestamp}\n\n{message}\n")
                if state.round_orchestrator_state.get("paused"):
                    state.round_orchestrator_state = {}
                    self._save_state()
                self._bus.emit_btw(issue_id, message, channel)
                logger.info(
                    "BTW injected for %s from %s: %s",
                    issue_id,
                    channel,
                    message[:80],
                )
                return True
        return False
