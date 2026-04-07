from __future__ import annotations

import json as _json
import os
import re
import signal
import sqlite3
import subprocess as _subprocess
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast

from spec_orch.domain.models import Issue, IssueContext, RunResult, RunState
from spec_orch.domain.protocols import PlannerAdapter
from spec_orch.services.admission_governor import AdmissionGovernor
from spec_orch.services.builders.adapter_factory import create_builder, create_reviewer
from spec_orch.services.conflict_resolver import ConflictResolver
from spec_orch.services.context.context_assembler import ContextAssembler
from spec_orch.services.context.node_context_registry import get_node_context_spec
from spec_orch.services.daemon_executor import DaemonExecutor
from spec_orch.services.daemon_issue_dispatcher import DaemonIssueDispatcher
from spec_orch.services.daemon_mission_executor import DaemonMissionExecutor
from spec_orch.services.daemon_mission_tick_handler import DaemonMissionTickHandler
from spec_orch.services.daemon_reaction_processor import DaemonReactionProcessor
from spec_orch.services.daemon_single_issue_executor import DaemonSingleIssueExecutor
from spec_orch.services.daemon_state_store import DaemonStateStore
from spec_orch.services.event_bus import Event, EventTopic
from spec_orch.services.github_pr_service import GitHubPRService
from spec_orch.services.io import atomic_write_json
from spec_orch.services.linear_client import LinearClient
from spec_orch.services.linear_issue_source import LinearIssueSource
from spec_orch.services.linear_write_back import LinearWriteBackService
from spec_orch.services.litellm_profile import resolve_role_litellm_settings
from spec_orch.services.mission_execution_service import MissionExecutionService
from spec_orch.services.reaction_engine import (
    ReactionDecision,
    ReactionEngine,
)
from spec_orch.services.run_controller import RunController

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_PR_ISSUE_ID_RE = re.compile(r"\[SpecOrch\]\s+([A-Za-z0-9_-]+):")


class _DaemonSharedState:
    """Mutable state shared between the daemon and its collaborators.

    Using a dedicated container avoids stale references when tests replace
    attributes like ``daemon._triaged = new_set``.
    """

    __slots__ = (
        "processed",
        "triaged",
        "pr_commits",
        "retry_counts",
        "retry_at",
        "dead_letter",
        "in_progress",
        "reaction_marks",
    )

    def __init__(
        self,
        *,
        processed: set[str],
        triaged: set[str],
        pr_commits: dict[str, str],
        retry_counts: dict[str, int],
        retry_at: dict[str, float],
        dead_letter: set[str],
        in_progress: set[str],
        reaction_marks: set[str],
    ) -> None:
        self.processed = processed
        self.triaged = triaged
        self.pr_commits = pr_commits
        self.retry_counts = retry_counts
        self.retry_at = retry_at
        self.dead_letter = dead_letter
        self.in_progress = in_progress
        self.reaction_marks = reaction_marks


class DaemonConfig:
    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw
        linear = raw.get("linear", {})
        self.linear_token_env: str = linear.get("token_env", "SPEC_ORCH_LINEAR_TOKEN")
        self.team_key: str = linear.get("team_key", "SPC")
        self.poll_interval_seconds: int = linear.get("poll_interval_seconds", 60)
        self.issue_filter: str = linear.get("issue_filter", "assigned_to_me")

        builder = raw.get("builder", {})
        self.builder_adapter: str = builder.get("adapter", "codex_exec")
        self.codex_executable: str = builder.get("executable") or builder.get(
            "codex_executable", "codex"
        )

        reviewer = raw.get("reviewer", {})
        self.reviewer_adapter: str = reviewer.get("adapter", "local")

        planner = raw.get("planner", {})
        self.planner_model: str | None = planner.get("model")
        self.planner_api_type: str = planner.get("api_type", "anthropic")
        self.planner_api_key_env: str | None = planner.get("api_key_env")
        self.planner_api_base_env: str | None = planner.get("api_base_env")
        self.planner_token_command: str | None = planner.get("token_command")

        supervisor = raw.get("supervisor", {})
        self.supervisor_adapter: str | None = supervisor.get("adapter")
        self.supervisor_model: str | None = supervisor.get("model")
        self.supervisor_api_type: str = supervisor.get("api_type", "anthropic")
        self.supervisor_api_key_env: str | None = supervisor.get("api_key_env")
        self.supervisor_api_base_env: str | None = supervisor.get("api_base_env")
        self.supervisor_max_rounds: int = supervisor.get("max_rounds", 20)
        visual_evaluator = supervisor.get("visual_evaluator", {})
        self.supervisor_visual_evaluator_adapter: str | None = visual_evaluator.get("adapter")
        self.supervisor_visual_evaluator_command: list[str] = list(
            visual_evaluator.get("command", [])
        )
        self.supervisor_visual_evaluator_timeout_seconds: int = visual_evaluator.get(
            "timeout_seconds", 300
        )

        acceptance = raw.get("acceptance_evaluator", {})
        self.acceptance_evaluator_adapter: str | None = acceptance.get("adapter")
        self.acceptance_evaluator_model: str | None = acceptance.get("model")
        self.acceptance_evaluator_api_type: str = acceptance.get("api_type", "anthropic")
        self.acceptance_evaluator_api_key_env: str | None = acceptance.get("api_key_env")
        self.acceptance_evaluator_api_base_env: str | None = acceptance.get("api_base_env")
        self.acceptance_auto_file_issues: bool = acceptance.get("auto_file_issues", False)
        self.acceptance_min_confidence: float = float(acceptance.get("min_confidence", 0.8))
        self.acceptance_min_severity: str = str(acceptance.get("min_severity", "high"))

        github = raw.get("github", {})
        self.base_branch: str = github.get("base_branch", "main")

        daemon = raw.get("daemon", {})
        self.max_concurrent: int = daemon.get("max_concurrent", 1)
        self.live_mission_workers: bool = daemon.get("live_mission_workers", False)
        self.lockfile_dir: str = daemon.get("lockfile_dir", ".spec_orch_locks/")
        self.consume_state: str = daemon.get("consume_state", "Ready")
        self.require_labels: list[str] = daemon.get("require_labels", [])
        self.exclude_labels: list[str] = daemon.get(
            "exclude_labels",
            ["blocked", "needs-clarification"],
        )
        self.skip_parents: bool = daemon.get("skip_parents", True)
        self.max_retries: int = daemon.get("max_retries", 3)
        self.retry_base_delay: int = daemon.get("retry_base_delay_seconds", 60)
        self.hotfix_labels: list[str] = daemon.get("hotfix_labels", ["hotfix", "urgent", "P0"])

        spec = raw.get("spec", {})
        self.require_spec_approval: bool = spec.get("require_approval", True)

    @classmethod
    def from_toml(cls, path: Path) -> DaemonConfig:
        import tomllib

        with open(path, "rb") as f:
            raw = tomllib.load(f)
        return cls(raw)


class SpecOrchDaemon:
    STATE_FILE = "daemon_state.json"
    PROCESS_LOCK_LEASE_SECONDS = 120
    ISSUE_CLAIM_LEASE_SECONDS = 300

    def __init__(
        self,
        *,
        config: DaemonConfig,
        repo_root: Path,
        live_mission_workers: bool = False,
    ) -> None:
        self.config = config
        self.repo_root = repo_root
        self._live_mission_workers = live_mission_workers or config.live_mission_workers
        self._running = True
        self._readiness_checker: Any = None
        self._context_assembler = ContextAssembler()
        self._lockdir = repo_root / config.lockfile_dir
        self._lockdir.mkdir(parents=True, exist_ok=True)
        self._state_store = DaemonStateStore(self._lockdir)
        self._state_path = self._lockdir / self.STATE_FILE
        saved = self._load_state()
        self._shared_state = _DaemonSharedState(
            processed=set(saved.get("processed", [])),
            triaged=set(saved.get("triaged", [])),
            pr_commits=dict(saved.get("pr_commits", {})),
            retry_counts=dict(saved.get("retry_counts", {})),
            retry_at={
                str(key): float(value)
                for key, value in dict(saved.get("retry_at", {})).items()
                if str(key).strip()
            },
            dead_letter=set(saved.get("dead_letter", [])),
            in_progress=set(saved.get("in_progress", [])),
            reaction_marks=set(saved.get("reaction_marks", [])),
        )
        self._last_poll: str = saved.get("last_poll", "")
        self._state_lock = threading.Lock()
        self._process_lock_owner = f"{os.getpid()}:{id(self)}"
        self._reaction_engine = ReactionEngine(repo_root)
        self._admission_governor = AdmissionGovernor(
            repo_root,
            max_concurrent=self.config.max_concurrent,
        )
        self._daemon_executor = DaemonExecutor()
        self._single_issue_executor = DaemonSingleIssueExecutor()
        self._mission_executor = DaemonMissionExecutor()
        self._executor_pool = ThreadPoolExecutor(
            max_workers=max(1, self.config.max_concurrent),
            thread_name_prefix="daemon-exec",
        )
        from spec_orch.services.event_bus import get_event_bus

        self._event_bus = get_event_bus()
        self._round_orchestrator = self._build_round_orchestrator()
        self._mission_execution_service: MissionExecutionService | None = None

        from spec_orch.services.lifecycle_manager import MissionLifecycleManager
        from spec_orch.services.memory.service import get_memory_service

        self._memory_service = get_memory_service(repo_root=repo_root)
        self._memory_service.subscribe_to_event_bus()

        self._lifecycle_manager = MissionLifecycleManager(
            repo_root=repo_root,
            event_bus=self._event_bus,
            round_orchestrator=self._round_orchestrator,
            mission_execution_service=self._get_mission_execution_service(),
            codex_bin=self.config.codex_executable,
            memory_service=self._memory_service,
        )

        # -- Collaborators (decomposed from monolithic daemon) --
        self._issue_dispatcher = DaemonIssueDispatcher(
            config=config,
            state_store=self._state_store,
            admission_governor=self._admission_governor,
            daemon_executor=self._daemon_executor,
            executor_pool=self._executor_pool,
            state_lock=self._state_lock,
            shared_state=self._shared_state,
            host=self,
            process_lock_owner=self._process_lock_owner,
        )

        self._reaction_processor = DaemonReactionProcessor(
            config=config,
            repo_root=repo_root,
            reaction_engine=self._reaction_engine,
            event_bus=self._event_bus,
            state_lock=self._state_lock,
            shared_state=self._shared_state,
            host=self,
        )

        self._mission_tick_handler = DaemonMissionTickHandler(
            repo_root=repo_root,
            lifecycle_manager=self._lifecycle_manager,
        )

    # -- Properties delegating to _shared_state for test compatibility --
    # Tests that use ``__new__`` bypass __init__ and set these directly on the
    # instance dict.  The property getters fall back to ``__dict__`` so that
    # both normal construction and test shortcuts work.

    @property
    def _processed(self) -> set[str]:
        ss = self.__dict__.get("_shared_state")
        return ss.processed if ss is not None else self.__dict__.get("_processed_fallback", set())  # type: ignore[no-any-return]

    @_processed.setter
    def _processed(self, value: set[str]) -> None:
        ss = self.__dict__.get("_shared_state")
        if ss is not None:
            ss.processed = value
        else:
            self.__dict__["_processed_fallback"] = value

    @property
    def _triaged(self) -> set[str]:
        ss = self.__dict__.get("_shared_state")
        return ss.triaged if ss is not None else self.__dict__.get("_triaged_fallback", set())  # type: ignore[no-any-return]

    @_triaged.setter
    def _triaged(self, value: set[str]) -> None:
        ss = self.__dict__.get("_shared_state")
        if ss is not None:
            ss.triaged = value
        else:
            self.__dict__["_triaged_fallback"] = value

    @property
    def _pr_commits(self) -> dict[str, str]:
        ss = self.__dict__.get("_shared_state")
        return ss.pr_commits if ss is not None else self.__dict__.get("_pr_commits_fallback", {})  # type: ignore[no-any-return]

    @_pr_commits.setter
    def _pr_commits(self, value: dict[str, str]) -> None:
        ss = self.__dict__.get("_shared_state")
        if ss is not None:
            ss.pr_commits = value
        else:
            self.__dict__["_pr_commits_fallback"] = value

    @property
    def _retry_counts(self) -> dict[str, int]:
        ss = self.__dict__.get("_shared_state")
        if ss is not None:
            return ss.retry_counts  # type: ignore[no-any-return]
        return self.__dict__.get("_retry_counts_fallback", {})  # type: ignore[no-any-return]

    @_retry_counts.setter
    def _retry_counts(self, value: dict[str, int]) -> None:
        ss = self.__dict__.get("_shared_state")
        if ss is not None:
            ss.retry_counts = value
        else:
            self.__dict__["_retry_counts_fallback"] = value

    @property
    def _retry_at(self) -> dict[str, float]:
        ss = self.__dict__.get("_shared_state")
        return ss.retry_at if ss is not None else self.__dict__.get("_retry_at_fallback", {})  # type: ignore[no-any-return]

    @_retry_at.setter
    def _retry_at(self, value: dict[str, float]) -> None:
        ss = self.__dict__.get("_shared_state")
        if ss is not None:
            ss.retry_at = value
        else:
            self.__dict__["_retry_at_fallback"] = value

    @property
    def _dead_letter(self) -> set[str]:
        ss = self.__dict__.get("_shared_state")
        if ss is not None:
            return ss.dead_letter  # type: ignore[no-any-return]
        return self.__dict__.get("_dead_letter_fallback", set())  # type: ignore[no-any-return]

    @_dead_letter.setter
    def _dead_letter(self, value: set[str]) -> None:
        ss = self.__dict__.get("_shared_state")
        if ss is not None:
            ss.dead_letter = value
        else:
            self.__dict__["_dead_letter_fallback"] = value

    @property
    def _in_progress(self) -> set[str]:
        ss = self.__dict__.get("_shared_state")
        if ss is not None:
            return ss.in_progress  # type: ignore[no-any-return]
        return self.__dict__.get("_in_progress_fallback", set())  # type: ignore[no-any-return]

    @_in_progress.setter
    def _in_progress(self, value: set[str]) -> None:
        ss = self.__dict__.get("_shared_state")
        if ss is not None:
            ss.in_progress = value
        else:
            self.__dict__["_in_progress_fallback"] = value

    @property
    def _reaction_marks(self) -> set[str]:
        ss = self.__dict__.get("_shared_state")
        if ss is not None:
            return ss.reaction_marks  # type: ignore[no-any-return]
        return self.__dict__.get("_reaction_marks_fallback", set())  # type: ignore[no-any-return]

    @_reaction_marks.setter
    def _reaction_marks(self, value: set[str]) -> None:
        ss = self.__dict__.get("_shared_state")
        if ss is not None:
            ss.reaction_marks = value
        else:
            self.__dict__["_reaction_marks_fallback"] = value

    HEARTBEAT_FILE = "daemon_heartbeat.json"

    def _get_mission_execution_service(self) -> MissionExecutionService:
        # Tests sometimes inject a stub directly on this attribute.
        if self._mission_execution_service is not None and not isinstance(
            self._mission_execution_service, MissionExecutionService
        ):
            return self._mission_execution_service
        current_orchestrator = getattr(
            self._mission_execution_service,
            "round_orchestrator",
            self._round_orchestrator,
        )
        if (
            self._mission_execution_service is None
            or current_orchestrator is not self._round_orchestrator
        ):
            self._mission_execution_service = MissionExecutionService(
                repo_root=self.repo_root,
                round_orchestrator=self._round_orchestrator,
                codex_bin=self.config.codex_executable,
            )
        return self._mission_execution_service

    def _load_state(self) -> dict[str, Any]:
        try:
            return self._state_store.load_snapshot()
        except Exception as exc:
            print(f"[daemon] failed to load state: {exc}")
            if self._state_path.exists():
                try:
                    return cast(dict[str, Any], _json.loads(self._state_path.read_text()))
                except (_json.JSONDecodeError, OSError) as legacy_exc:
                    print(f"[daemon] failed to load legacy state: {legacy_exc}")
        return {}

    def _save_state(self) -> None:
        self._last_poll = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._state_lock:
            data = {
                "processed": sorted(set(self._processed)),
                "triaged": sorted(set(self._triaged)),
                "pr_commits": dict(self._pr_commits),
                "retry_counts": dict(self._retry_counts),
                "retry_at": dict(self._retry_at),
                "dead_letter": sorted(set(self._dead_letter)),
                "in_progress": sorted(set(self._in_progress)),
                "reaction_marks": sorted(set(self._reaction_marks)),
                "last_poll": self._last_poll,
            }
        try:
            self._state_store.save_snapshot(data)
        except OSError as exc:
            print(f"[daemon] failed to save state: {exc}")
        except Exception as exc:
            print(f"[daemon] failed to save sqlite state: {exc}")

    def _acquire_process_lock(self) -> None:
        acquired = self._state_store.acquire_daemon_lock(
            owner=self._process_lock_owner,
            pid=os.getpid(),
            lease_seconds=self.PROCESS_LOCK_LEASE_SECONDS,
        )
        if not acquired:
            raise RuntimeError("another spec-orch daemon instance already holds the process lock")

    def _renew_process_lock(self) -> None:
        self._state_store.renew_daemon_lock(
            owner=self._process_lock_owner,
            pid=os.getpid(),
            lease_seconds=self.PROCESS_LOCK_LEASE_SECONDS,
        )

    def _release_process_lock(self) -> None:
        self._state_store.release_daemon_lock(owner=self._process_lock_owner)

    def run(self) -> None:
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        client = LinearClient(token_env=self.config.linear_token_env)
        issue_source = LinearIssueSource(client=client)
        builder = create_builder(self.repo_root, toml_override=self.config._raw)
        reviewer = create_reviewer(self.repo_root, toml_override=self.config._raw)
        self._builder = builder
        self._write_back = LinearWriteBackService(client=client)

        planner = self._build_planner()

        from spec_orch.services.evidence_analyzer import EvidenceAnalyzer

        self._evidence_analyzer = EvidenceAnalyzer(self.repo_root)

        from spec_orch.services.readiness_checker import ReadinessChecker

        self._readiness_checker = ReadinessChecker(
            planner=planner,
            evidence_context=self._get_evidence_context(),
        )

        controller = RunController(
            repo_root=self.repo_root,
            builder_adapter=builder,
            issue_source=issue_source,
            planner_adapter=planner,
            review_adapter=reviewer,
            require_spec_approval=self.config.require_spec_approval,
        )

        interval = self.config.poll_interval_seconds
        print(f"[daemon] started, polling {self.config.team_key} every {interval}s")
        if self.config.reviewer_adapter == "local":
            print(
                "[daemon] WARNING: using 'local' reviewer (JSON-only, no automated review). "
                'Set [reviewer] adapter = "llm" in spec-orch.toml for LLM-based review.'
            )
        if planner:
            print(f"[daemon] planner: {planner.ADAPTER_NAME}")
        if self._dead_letter:
            print(f"[daemon] dead letter queue: {sorted(self._dead_letter)}")

        self._consecutive_loop_errors = 0
        self._acquire_process_lock()
        self._write_heartbeat(status="starting")
        self.resume_in_progress(controller)

        try:
            while self._running:
                try:
                    self._reap_completed_futures()
                    self._tick_missions()
                    self._check_clarification_replies(client)
                    self._check_review_updates(client)
                    self._poll_and_run(client, controller)
                    self._save_state()
                    self._renew_process_lock()
                    self._write_heartbeat(status="healthy")
                    self._consecutive_loop_errors = 0
                except Exception as exc:
                    self._consecutive_loop_errors += 1
                    self._emit_error_event(
                        "daemon.loop_error",
                        str(exc),
                        transient=self._consecutive_loop_errors < 5,
                    )
                    print(f"[daemon] loop error ({self._consecutive_loop_errors}): {exc}")
                    self._write_heartbeat(
                        status="degraded",
                        error=str(exc),
                    )
                    if self._consecutive_loop_errors >= 10:
                        print("[daemon] 10 consecutive loop errors — exiting")
                        break
                self._sleep(self.config.poll_interval_seconds)
        finally:
            self._executor_pool.shutdown(wait=True)
            self._reap_completed_futures()
            self._save_state()
            self._release_process_lock()
            self._write_heartbeat(status="stopped")
            client.close()
            print("[daemon] stopped")

    def _build_planner(self) -> PlannerAdapter | None:
        """Build a PlannerAdapter from config.

        Token resolution is deferred to the adapter's ``api_key`` property so
        that ``token_command`` tokens are refreshed on every ``plan()`` call,
        not just once at daemon startup.
        """
        planner_settings = resolve_role_litellm_settings(
            self.config._raw,
            section_name="planner",
            default_model=self.config.planner_model or "",
            default_api_type=self.config.planner_api_type,
        )
        if not planner_settings.get("model"):
            return None
        model_chain = planner_settings["model_chain"]
        api_key = planner_settings["api_key"] or None
        api_base = planner_settings["api_base"] or None

        try:
            from spec_orch.services.litellm_planner_adapter import (
                LiteLLMPlannerAdapter,
            )

            return LiteLLMPlannerAdapter(
                model=str(planner_settings["model"]),
                api_type=str(planner_settings["api_type"]),
                api_key=api_key,
                api_base=api_base,
                token_command=self.config.planner_token_command,
                model_chain=model_chain,
            )
        except ImportError:
            print("[daemon] litellm not installed, planner disabled")
            return None

    def _build_round_orchestrator(self) -> Any | None:
        supervisor_settings = resolve_role_litellm_settings(
            self.config._raw,
            section_name="supervisor",
            default_model=self.config.supervisor_model or "",
            default_api_type=self.config.supervisor_api_type,
        )
        if not supervisor_settings.get("model"):
            return None
        supervisor_chain = supervisor_settings["model_chain"]
        api_key = supervisor_settings["api_key"] or None
        api_base = supervisor_settings["api_base"] or None

        if self.config.supervisor_adapter not in (None, "litellm"):
            raise ValueError(f"Unsupported supervisor adapter: {self.config.supervisor_adapter!r}")

        from spec_orch.domain.protocols import WorkerHandleFactory
        from spec_orch.services.acceptance.linear_filing import LinearAcceptanceFiler
        from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
            LiteLLMAcceptanceEvaluator,
        )
        from spec_orch.services.litellm_supervisor_adapter import LiteLLMSupervisorAdapter
        from spec_orch.services.round_orchestrator import RoundOrchestrator
        from spec_orch.services.visual.command_visual_evaluator import CommandVisualEvaluator
        from spec_orch.services.visual.noop_visual_evaluator import NoopVisualEvaluator
        from spec_orch.services.workers.acpx_worker_handle_factory import AcpxWorkerHandleFactory
        from spec_orch.services.workers.in_memory_worker_handle_factory import (
            InMemoryWorkerHandleFactory,
        )
        from spec_orch.services.workers.oneshot_worker_handle import OneShotWorkerHandle

        supervisor = LiteLLMSupervisorAdapter(
            repo_root=self.repo_root,
            model=str(supervisor_settings["model"]),
            api_type=str(supervisor_settings["api_type"]),
            api_key=api_key,
            api_base=api_base,
            model_chain=supervisor_chain,
        )

        builder_cfg = self.config._raw.get("builder", {})
        adapter_name = builder_cfg.get("adapter", "codex_exec")
        worker_factory: WorkerHandleFactory
        if adapter_name == "acpx" or str(adapter_name).startswith("acpx_"):
            agent = builder_cfg.get("agent")
            if not agent and str(adapter_name).startswith("acpx_"):
                agent = str(adapter_name)[len("acpx_") :]
            agent = agent or "opencode"
            worker_factory = AcpxWorkerHandleFactory(
                agent=agent,
                model=builder_cfg.get("model"),
                permissions=builder_cfg.get("permissions", "full-auto"),
                executable=builder_cfg.get("executable", "npx"),
                acpx_package=builder_cfg.get("acpx_package", "acpx"),
                absolute_timeout_seconds=float(builder_cfg.get("timeout_seconds", 1800)),
                startup_timeout_seconds=float(builder_cfg.get("startup_timeout_seconds", 30)),
                idle_progress_timeout_seconds=float(
                    builder_cfg.get("idle_progress_timeout_seconds", 60)
                ),
                completion_quiet_period_seconds=float(
                    builder_cfg.get("completion_quiet_period_seconds", 2)
                ),
                max_retries=int(builder_cfg.get("max_retries", 1)),
                max_turns_per_session=int(builder_cfg.get("max_turns_per_session", 10)),
                max_session_age_seconds=float(builder_cfg.get("max_session_age_seconds", 1800)),
            )
        else:
            worker_factory = InMemoryWorkerHandleFactory(
                creator=lambda session_id, workspace: OneShotWorkerHandle(
                    session_id=session_id,
                    builder_adapter=create_builder(
                        self.repo_root,
                        toml_override=self.config._raw,
                    ),
                )
            )

        visual_evaluator: Any | None = None
        if self.config.supervisor_visual_evaluator_adapter == "noop":
            visual_evaluator = NoopVisualEvaluator()
        elif self.config.supervisor_visual_evaluator_adapter == "command":
            if not self.config.supervisor_visual_evaluator_command:
                raise ValueError("supervisor.visual_evaluator.command must not be empty")
            visual_evaluator = CommandVisualEvaluator(
                command=self.config.supervisor_visual_evaluator_command,
                timeout_seconds=self.config.supervisor_visual_evaluator_timeout_seconds,
            )
        elif self.config.supervisor_visual_evaluator_adapter not in (None, ""):
            raise ValueError(
                "Unsupported visual evaluator adapter: "
                f"{self.config.supervisor_visual_evaluator_adapter!r}"
            )

        acceptance_settings = resolve_role_litellm_settings(
            self.config._raw,
            section_name="acceptance_evaluator",
            default_model=self.config.acceptance_evaluator_model or "",
            default_api_type=self.config.acceptance_evaluator_api_type,
        )
        acceptance_chain = acceptance_settings["model_chain"]
        acceptance_api_key = acceptance_settings["api_key"] or None
        acceptance_api_base = acceptance_settings["api_base"] or None

        acceptance_evaluator: Any | None = None
        if acceptance_settings["model"]:
            if self.config.acceptance_evaluator_adapter not in (None, "litellm"):
                raise ValueError(
                    "Unsupported acceptance evaluator adapter: "
                    f"{self.config.acceptance_evaluator_adapter!r}"
                )
            acceptance_evaluator = LiteLLMAcceptanceEvaluator(
                repo_root=self.repo_root,
                model=str(acceptance_settings["model"]),
                api_type=str(acceptance_settings["api_type"]),
                api_key=acceptance_api_key,
                api_base=acceptance_api_base,
                model_chain=acceptance_chain,
            )

        acceptance_filer: Any | None = None
        if acceptance_evaluator is not None and self.config.acceptance_auto_file_issues:
            acceptance_filer = LinearAcceptanceFiler(
                client=LinearClient(token_env=self.config.linear_token_env),
                team_key=self.config.team_key,
                min_confidence=self.config.acceptance_min_confidence,
                min_severity=self.config.acceptance_min_severity,
            )

        return RoundOrchestrator(
            repo_root=self.repo_root,
            supervisor=supervisor,
            worker_factory=worker_factory,
            context_assembler=ContextAssembler(),
            visual_evaluator=visual_evaluator,
            acceptance_evaluator=acceptance_evaluator,
            acceptance_filer=acceptance_filer,
            event_bus=self._event_bus,
            max_rounds=self.config.supervisor_max_rounds,
            live_stream=sys.stderr if self._live_mission_workers else None,
            gate_policy=self._load_gate_policy(),
        )

    def _tick_missions(self) -> None:
        """Advance mission lifecycles on each daemon tick."""
        self._mission_tick_handler.tick()

    def _find_mission_for_issue(self, issue_id: str) -> str | None:
        """Return the mission_id that owns *issue_id*, if any."""
        return self._mission_tick_handler.find_mission_for_issue(issue_id)

    def handle_btw(self, issue_id: str, message: str, channel: str) -> bool:
        """Inject /btw context into a running issue via the lifecycle manager."""
        return self._mission_tick_handler.handle_btw(issue_id, message, channel)

    def _poll_and_run(self, client: LinearClient, controller: RunController) -> None:
        self._issue_dispatcher.poll_and_dispatch(client, controller)

    def _poll_and_enqueue(self, client: LinearClient, controller: RunController) -> None:
        self._issue_dispatcher._poll_and_enqueue(client, controller)

    def _enqueue_execution_intent(
        self,
        *,
        issue_id: str,
        raw_issue: dict[str, Any],
        is_hotfix: bool,
    ) -> None:
        self._issue_dispatcher._enqueue_execution_intent(
            issue_id=issue_id,
            raw_issue=raw_issue,
            is_hotfix=is_hotfix,
        )

    def _drain_execution_queue(self, client: LinearClient, controller: RunController) -> None:
        self._issue_dispatcher._drain_execution_queue(client, controller)

    def _reap_completed_futures(self) -> None:
        self._issue_dispatcher.reap_completed_futures()

    @property
    def _execution_futures(self) -> dict[str, Future[None]]:  # type: ignore[override]
        dispatcher = self.__dict__.get("_issue_dispatcher")
        if dispatcher is not None:
            return dispatcher._execution_futures  # type: ignore[no-any-return]
        return self.__dict__.get("__execution_futures_fallback", {})  # type: ignore[no-any-return]

    @_execution_futures.setter
    def _execution_futures(self, value: dict[str, Future[None]]) -> None:
        dispatcher = self.__dict__.get("_issue_dispatcher")
        if dispatcher is not None:
            dispatcher._execution_futures = value
        else:
            self.__dict__["__execution_futures_fallback"] = value

    @staticmethod
    def _sanitize_id(raw_id: str) -> str:
        """Strip path-traversal characters from a mission/issue ID."""
        return re.sub(r"[/\\.\s]+", "-", raw_id).strip("-")

    def _detect_mission(
        self,
        issue_id: str,
        raw_issue: dict[str, Any],
    ) -> str | None:
        """Check if the issue references a mission plan.json.

        Returns the mission_id if a plan.json exists, else None.
        """
        desc = raw_issue.get("description", "") or ""
        specs_dir = self.repo_root / "docs" / "specs"

        mission_match = re.search(r"mission[:\s]+(\S+)", desc, re.IGNORECASE)
        if mission_match:
            mid = self._sanitize_id(mission_match.group(1))
            if (specs_dir / mid / "plan.json").exists():
                return mid

        if re.search(r"plan\.json", desc, re.IGNORECASE):
            safe_id = self._sanitize_id(issue_id)
            if (specs_dir / safe_id / "plan.json").exists():
                return safe_id

        safe_id = self._sanitize_id(issue_id)
        if (specs_dir / safe_id / "plan.json").exists():
            return safe_id
        return None

    def _execute_single(
        self,
        issue_id: str,
        raw_issue: dict[str, Any],
        client: LinearClient,
        controller: RunController,
        *,
        is_hotfix: bool = False,
    ) -> None:
        """Execute a single issue through the standard pipeline."""
        self._single_issue_executor.execute(
            host=self,
            issue_id=issue_id,
            raw_issue=raw_issue,
            client=client,
            controller=controller,
            is_hotfix=is_hotfix,
        )

    def _execute_mission(
        self,
        issue_id: str,
        mission_id: str,
        raw_issue: dict[str, Any],
        client: LinearClient,
    ) -> None:
        """Execute a mission-level plan with parallel wave execution."""
        self._mission_executor.execute(
            host=self,
            issue_id=issue_id,
            mission_id=mission_id,
            raw_issue=raw_issue,
            client=client,
        )

    def _sync_linear_mirror_for_mission(
        self,
        *,
        client: LinearClient,
        raw_issue: dict[str, Any],
        mission_id: str,
    ) -> None:
        linear_uid = str(raw_issue.get("id", "")).strip()
        if not linear_uid:
            return
        try:
            issue = client.query(
                """
                query($id: String!) {
                  issue(id: $id) { description }
                }
                """,
                {"id": linear_uid},
            ).get("issue")
            current_description = (
                str(issue.get("description") or "") if isinstance(issue, dict) else ""
            )
            self._write_back.sync_issue_mirror_from_mission(
                repo_root=self.repo_root,
                mission_id=mission_id,
                linear_id=linear_uid,
                current_description=current_description,
            )
        except Exception as exc:
            print(f"[daemon] {mission_id}: mirror sync failed: {exc}")

    def _auto_create_pr(
        self,
        issue_id: str,
        result: RunResult,
    ) -> bool:
        """Automatically create a GitHub PR when gate is evaluated.

        When the gate policy's daemon profile allows auto-merge and
        all auto-merge conditions pass, the PR is created as non-draft
        and auto-merge is enabled.

        Returns True if a PR was successfully created.
        """
        if result.state != RunState.GATE_EVALUATED:
            return False
        try:
            gate_policy = self._load_gate_policy()
            should_auto = gate_policy.auto_merge and result.gate.mergeable

            workspace = result.workspace
            gh_svc = GitHubPRService()

            branch = gh_svc._current_branch(workspace)
            if branch and branch != self.config.base_branch:
                check = gh_svc.check_mergeable(
                    workspace,
                    branch=branch,
                    base=self.config.base_branch,
                )
                if not check["mergeable"]:
                    print(f"[daemon] {issue_id}: conflicts detected, attempting rebase")
                    rebased = gh_svc.auto_rebase(
                        workspace,
                        base=self.config.base_branch,
                    )
                    if rebased:
                        print(f"[daemon] {issue_id}: rebase succeeded")
                    else:
                        print(f"[daemon] {issue_id}: rebase failed, attempting AI resolution")
                        resolver = ConflictResolver(
                            builder_adapter=getattr(self, "_builder", None),
                            linear_client=getattr(self._write_back, "_client", None),
                        )
                        conflict_files = cast(list[str], check["conflicting_files"])
                        cr = resolver.resolve(
                            issue=result.issue,
                            workspace=workspace,
                            conflicting_files=conflict_files,
                            base=self.config.base_branch,
                        )
                        if cr.resolved:
                            print(f"[daemon] {issue_id}: conflict resolved via {cr.method}")
                        else:
                            print(
                                f"[daemon] {issue_id}: conflict resolution failed "
                                f"({cr.method}), PR will be created with conflicts"
                            )

            title = f"[SpecOrch] {issue_id}: {result.issue.title}"
            flow = result.gate.flow_control
            body_lines = [
                f"## SpecOrch: {issue_id}",
                "",
                f"**Mergeable**: {'yes' if result.gate.mergeable else 'no'}",
            ]
            if result.gate.failed_conditions:
                body_lines.append(f"**Blocked**: {', '.join(result.gate.failed_conditions)}")
            if flow.retry_recommended:
                body_lines.append("**Retry recommended**: yes")
            if flow.escalation_required:
                body_lines.append("**Escalation required**: yes")
            if flow.promotion_required:
                body_lines.append(f"**Promotion signal**: {flow.promotion_target or 'required'}")
            if flow.demotion_suggested:
                body_lines.append(f"**Demotion signal**: {flow.demotion_target or 'suggested'}")
            if flow.backtrack_reason:
                body_lines.append(f"**Backtrack reason**: {flow.backtrack_reason}")
            body_lines.extend(["", f"Closes {issue_id}"])

            pr_url = gh_svc.create_pr(
                workspace=workspace,
                title=title,
                body="\n".join(body_lines),
                base=self.config.base_branch,
                draft=not should_auto,
            )
            if pr_url:
                print(f"[daemon] PR created: {pr_url}")
                gh_svc.set_gate_status(workspace=workspace, gate=result.gate)
                head_sha = gh_svc._head_sha(workspace)
                if head_sha:
                    self._pr_commits[issue_id] = head_sha

                if should_auto:
                    merged = gh_svc.merge_pr(workspace, method="squash")
                    if merged:
                        print(f"[daemon] auto-merged PR for {issue_id}")
                    else:
                        print("[daemon] auto-merge requested (waiting for checks)")
                return True
            print(f"[daemon] could not create PR for {issue_id}")
            return False
        except (RuntimeError, OSError, FileNotFoundError) as exc:
            print(f"[daemon] auto-PR failed for {issue_id}: {exc}")
            return False

    def _load_gate_policy(self) -> Any:
        """Load gate policy with daemon profile applied."""
        return self._load_gate_policy_for("daemon")

    def _load_gate_policy_for(self, profile: str) -> Any:
        """Load gate policy with the specified profile applied."""
        from spec_orch.services.gate_service import GatePolicy

        policy_path = self.repo_root / "gate.policy.yaml"
        if policy_path.exists():
            base_policy = GatePolicy.from_yaml(policy_path)
        else:
            base_policy = GatePolicy.default()
        return base_policy.with_profile(profile)

    def _triage_issue(
        self,
        client: LinearClient,
        raw_issue: dict[str, Any],
        controller: RunController | None = None,
    ) -> bool:
        """Check issue readiness before execution.

        Returns True if the issue is ready to execute, False if it
        needs clarification (comment posted, label applied).
        """
        issue_id = raw_issue.get("identifier", "")
        linear_uid = raw_issue.get("id", "")
        description = raw_issue.get("description", "") or ""

        if controller is None:
            result = self._readiness_checker.check(description)
        else:
            try:
                issue = self._build_triage_issue(raw_issue)
                raw_workspace = controller.workspace_service.issue_workspace_path(issue.issue_id)
                workspace = raw_workspace if isinstance(raw_workspace, Path) else self.repo_root
                context = self._context_assembler.assemble(
                    get_node_context_spec("readiness_checker"),
                    issue,
                    workspace,
                    memory=self._memory_service,
                    repo_root=self.repo_root,
                )
                result = self._readiness_checker.check(description, context=context)
            except Exception as exc:
                print(f"[daemon] {issue_id}: triage context assembly failed: {exc}")
                result = self._readiness_checker.check(description)
        if result.ready:
            return True

        if issue_id in self._triaged:
            return False

        print(f"[daemon] {issue_id}: needs clarification ({result.missing_fields})")

        if linear_uid:
            try:
                comment = result.format_comment()
                client.add_comment(linear_uid, comment)
                print(f"[daemon] {issue_id}: posted clarification request")
            except Exception as exc:
                print(f"[daemon] {issue_id}: comment failed: {exc}")

            try:
                client.add_label(linear_uid, "needs-clarification")
            except Exception as exc:
                print(f"[daemon] {issue_id}: add label failed: {exc}")

        self._triaged.add(issue_id)
        return False

    @staticmethod
    def _build_triage_issue(raw_issue: dict[str, Any]) -> Issue:
        issue_id = raw_issue.get("identifier", "") or "unknown"
        title = raw_issue.get("title", issue_id) or issue_id
        summary = raw_issue.get("description", "") or ""
        return Issue(
            issue_id=issue_id,
            title=title,
            summary=summary,
            context=IssueContext(),
            acceptance_criteria=[],
        )

    def _check_clarification_replies(self, client: LinearClient) -> None:
        self._reaction_processor.check_clarification_replies(client)

    def _check_review_updates(self, client: LinearClient) -> None:
        self._reaction_processor.check_review_updates(client)

    def _run_reactions(
        self,
        client: LinearClient,
        gh: GitHubPRService,
        pr_meta_by_issue: dict[str, dict[str, Any]],
    ) -> None:
        self._reaction_processor._run_reactions(client, gh, pr_meta_by_issue)

    def _reaction_template_context(
        self,
        *,
        issue_id: str,
        pr_number: int,
        sha: str,
        signal: dict[str, Any],
    ) -> dict[str, Any]:
        return self._reaction_processor._reaction_template_context(
            issue_id=issue_id,
            pr_number=pr_number,
            sha=sha,
            signal=signal,
        )

    def _append_reaction_trace(self, record: dict[str, Any]) -> None:
        self._reaction_processor._append_reaction_trace(record)

    def _apply_reaction_decision(
        self,
        client: LinearClient,
        gh: GitHubPRService,
        *,
        issue_id: str,
        pr_number: int,
        decision: ReactionDecision,
        tpl_ctx: dict[str, Any],
    ) -> bool:
        return self._reaction_processor._apply_reaction_decision(
            client,
            gh,
            issue_id=issue_id,
            pr_number=pr_number,
            decision=decision,
            tpl_ctx=tpl_ctx,
        )

    def _requeue_issue_to_consume_state(self, client: LinearClient, issue_id: str) -> bool:
        return self._reaction_processor._requeue_issue_to_consume_state(client, issue_id)

    def _mark_issue_done_if_in_review(self, client: LinearClient, issue_id: str) -> None:
        self._reaction_processor._mark_issue_done_if_in_review(client, issue_id)

    def _comment_reaction(
        self,
        client: LinearClient,
        issue_id: str,
        decision: ReactionDecision,
        tpl_ctx: dict[str, Any],
    ) -> bool:
        return self._reaction_processor._comment_reaction(client, issue_id, decision, tpl_ctx)

    def _is_locked(self, issue_id: str) -> bool:
        dispatcher = self.__dict__.get("_issue_dispatcher")
        if dispatcher is not None:
            return bool(dispatcher._is_locked(issue_id))
        return self._state_store.issue_is_claimed(issue_id)

    def _claim(self, issue_id: str) -> None:
        dispatcher = self.__dict__.get("_issue_dispatcher")
        if dispatcher is not None:
            dispatcher._claim(issue_id)
            return
        claimed = self._state_store.try_claim_issue(
            issue_id,
            owner=self._process_lock_owner,
            lease_seconds=self.ISSUE_CLAIM_LEASE_SECONDS,
        )
        if not claimed:
            raise RuntimeError(f"issue already claimed: {issue_id}")

    def _release(self, issue_id: str) -> None:
        dispatcher = self.__dict__.get("_issue_dispatcher")
        if dispatcher is not None:
            dispatcher._release(issue_id)
            return
        self._state_store.release_issue_claim(issue_id)

    def _sleep(self, seconds: int) -> None:
        for _ in range(seconds):
            if not self._running:
                break
            time.sleep(1)

    def _get_evidence_context(self) -> str | None:
        """Build LLM context from historical evidence, refreshed each call."""
        try:
            summary = self._evidence_analyzer.analyze()
            if summary.total_runs > 0:
                return self._evidence_analyzer.format_as_llm_context(summary)
        except (OSError, ValueError) as exc:
            print(f"[daemon] evidence analysis skipped: {exc}")
        return None

    def _write_heartbeat(
        self,
        *,
        status: str = "healthy",
        error: str = "",
    ) -> None:
        """Write a heartbeat file for external health monitoring."""
        heartbeat_path = self._lockdir / self.HEARTBEAT_FILE
        data = {
            "status": status,
            "pid": os.getpid(),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "epoch": time.time(),
            "processed_count": len(self._processed),
            "in_progress": sorted(self._in_progress),
            "dead_letter_count": len(self._dead_letter),
            "consecutive_errors": getattr(self, "_consecutive_loop_errors", 0),
        }
        if error:
            data["last_error"] = error[:500]
        import contextlib

        with contextlib.suppress(OSError):
            atomic_write_json(heartbeat_path, data)

    def _emit_error_event(
        self,
        kind: str,
        message: str,
        *,
        issue_id: str = "",
        transient: bool = True,
    ) -> None:
        """Publish a structured error event to the EventBus."""
        import contextlib

        with contextlib.suppress(Exception):
            self._event_bus.publish(
                Event(
                    topic=EventTopic.SYSTEM,
                    payload={
                        "kind": kind,
                        "message": message[:500],
                        "issue_id": issue_id,
                        "transient": transient,
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    },
                )
            )

    # ---- Dead letter queue management ----

    def get_dead_letter_issues(self) -> list[str]:
        """Return the current dead letter queue."""
        return sorted(self._dead_letter)

    def retry_dead_letter(self, issue_id: str) -> bool:
        """Move an issue out of the dead letter queue for retry."""
        with self._state_lock:
            if issue_id not in self._dead_letter:
                return False
            self._dead_letter.discard(issue_id)
            self._processed.discard(issue_id)
            self._retry_counts.pop(issue_id, None)
            self._retry_at.pop(issue_id, None)
        self._release(issue_id)
        self._save_state()
        print(f"[daemon] {issue_id} removed from dead letter queue for retry")
        return True

    def clear_dead_letter(self) -> int:
        """Clear all issues from the dead letter queue. Returns count removed."""
        with self._state_lock:
            count = len(self._dead_letter)
            ids_to_release = list(self._dead_letter)
            for issue_id in ids_to_release:
                self._retry_at.pop(issue_id, None)
            self._dead_letter.clear()
        for issue_id in ids_to_release:
            self._release(issue_id)
        self._save_state()
        return count

    @classmethod
    def read_heartbeat(
        cls, repo_root: Path, lockfile_dir: str = ".spec_orch_locks/"
    ) -> dict[str, Any]:
        """Read the heartbeat file (static — can be called without a running daemon)."""
        heartbeat_path = repo_root / lockfile_dir / cls.HEARTBEAT_FILE
        if not heartbeat_path.exists():
            return {"status": "not_running"}
        try:
            data = _json.loads(heartbeat_path.read_text())
            if isinstance(data, dict):
                age = time.time() - data.get("epoch", 0)
                data["age_seconds"] = round(age, 1)
                if data.get("status") == "healthy" and age > 300:
                    data["status"] = "stale"
                return data
            return {"status": "unknown"}
        except (_json.JSONDecodeError, OSError):
            return {"status": "unknown"}

    @classmethod
    def read_state(cls, repo_root: Path, lockfile_dir: str = ".spec_orch_locks/") -> dict[str, Any]:
        """Read the daemon state file (static — can be called without a running daemon)."""
        try:
            lockdir = repo_root / lockfile_dir
            db_path = lockdir / DaemonStateStore.DB_NAME
            if db_path.exists():
                conn = sqlite3.connect(str(db_path), check_same_thread=False)
                try:
                    store = DaemonStateStore.__new__(DaemonStateStore)
                    store._lockdir = lockdir
                    store._db_path = db_path
                    store._db = conn
                    return store.load_snapshot()
                finally:
                    conn.close()
            legacy_path = lockdir / DaemonStateStore.LEGACY_STATE_FILE
            if legacy_path.exists():
                data = _json.loads(legacy_path.read_text())
                if isinstance(data, dict):
                    return data
            return {}
        except Exception:
            return {}

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        print(f"\n[daemon] received signal {signum}, shutting down gracefully...")
        self._running = False

    def _write_back_result(
        self,
        raw_issue: dict[str, Any],
        result: RunResult,
    ) -> None:
        """Post a run summary back to Linear as a comment and move to Done."""
        import httpx

        linear_id = raw_issue.get("id", "")
        if not linear_id or not hasattr(self, "_write_back"):
            return
        try:
            self._write_back.post_run_summary(linear_id=linear_id, result=result)
            print(f"[daemon] wrote summary to Linear for {result.issue.issue_id}")
        except (httpx.HTTPError, RuntimeError, OSError) as exc:
            print(f"[daemon] write-back failed: {exc}")

        if result.gate.mergeable:
            try:
                client: LinearClient = self._write_back._client  # type: ignore[attr-defined]
                client.update_issue_state(linear_id, "Done")
                print(f"[daemon] moved {result.issue.issue_id} to Done")
            except Exception as exc:
                print(f"[daemon] state update failed: {exc}")

    def _is_hotfix(self, raw_issue: dict[str, Any]) -> bool:
        """Check if an issue has hotfix labels -- skip triage if so."""
        return self._issue_dispatcher._is_hotfix(raw_issue)

    def _should_backoff(self, issue_id: str) -> bool:
        """Check if the issue is in a retry backoff period."""
        return self._issue_dispatcher._should_backoff(issue_id)

    def _record_failure(
        self,
        issue_id: str,
        error_msg: str,
        client: Any,
        linear_uid: str,
    ) -> None:
        """Record an issue failure, increment retry counter, move to dead letter if max exceeded."""
        with self._state_lock:
            count = self._retry_counts.get(issue_id, 0) + 1
            self._retry_counts[issue_id] = count
        self._emit_error_event(
            "daemon.issue_failed",
            error_msg,
            issue_id=issue_id,
            transient=count < self.config.max_retries,
        )

        if count >= self.config.max_retries:
            print(
                f"[daemon] {issue_id}: max retries ({self.config.max_retries}) "
                "exceeded → dead letter"
            )
            with self._state_lock:
                self._dead_letter.add(issue_id)
                self._retry_counts.pop(issue_id, None)
                self._retry_at.pop(issue_id, None)
            if linear_uid:
                try:
                    client.add_comment(
                        linear_uid,
                        f"## SpecOrch: Moved to Dead Letter\n\n"
                        f"This issue failed {count} times and has been removed from "
                        f"the automatic execution pool.\n\n"
                        f"**Last error**: `{error_msg[:500]}`\n\n"
                        f"_To retry, remove the `dead-letter` label and move back to Ready._",
                    )
                    client.add_label(linear_uid, "dead-letter")
                except Exception as exc:
                    print(f"[daemon] {issue_id}: dead letter notification failed: {exc}")
        else:
            delay = self.config.retry_base_delay * (2 ** (count - 1))
            retry_at = time.time() + delay
            with self._state_lock:
                self._retry_at[issue_id] = retry_at
            print(
                f"[daemon] {issue_id}: attempt {count}/{self.config.max_retries}, retry in {delay}s"
            )

    def resume_in_progress(self, controller: RunController) -> None:
        """Resume issues that were in_progress when the daemon last stopped.

        Before blindly re-executing, check if a run_artifact already exists
        with a terminal state — if so, skip the re-execution.
        """
        if not self._in_progress:
            return
        print(f"[daemon] resuming {len(self._in_progress)} in-progress issues")
        for issue_id in list(self._in_progress):
            if self._run_already_completed(issue_id, controller):
                print(f"[daemon] {issue_id}: already completed (found terminal artifact)")
                self._in_progress.discard(issue_id)
                self._processed.add(issue_id)
                continue
            try:
                result = controller.advance_to_completion(issue_id)
                print(f"[daemon] resumed {issue_id}: state={result.state.value}")
                self._in_progress.discard(issue_id)
                self._processed.add(issue_id)
            except Exception as exc:
                print(f"[daemon] resume {issue_id} failed: {exc}")
                self._emit_error_event("daemon.resume_failed", str(exc), issue_id=issue_id)
                self._in_progress.discard(issue_id)

    def _run_already_completed(self, issue_id: str, controller: RunController) -> bool:
        """Check if a run has already reached a terminal state via artifacts."""
        try:
            ws = controller.workspace_service.issue_workspace_path(issue_id)
        except Exception:
            return False
        conclusion = ws / "run_artifact" / "conclusion.json"
        if not conclusion.exists():
            return False
        try:
            data = _json.loads(conclusion.read_text())
            if not isinstance(data, dict):
                return False
            state = data.get("state", "")
            return state in ("merged", "gate_evaluated", "reviewed", "completed")
        except (_json.JSONDecodeError, OSError):
            return False

    def _notify(self, issue_id: str, mergeable: bool) -> None:
        status = "mergeable=true" if mergeable else "mergeable=false"
        sys.stdout.write("\a")
        sys.stdout.flush()

        if not _SAFE_ID_RE.match(issue_id):
            return

        import contextlib

        with contextlib.suppress(FileNotFoundError):
            _subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display notification "{status}" with title "SpecOrch: {issue_id} completed"',
                ],
                check=False,
                capture_output=True,
            )
