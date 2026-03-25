from __future__ import annotations

from pathlib import Path

from spec_orch.domain.models import (
    BuilderResult,
    ExecutionPlan,
    PlanPatch,
    RoundAction,
    RoundDecision,
    RoundStatus,
    RoundSummary,
    Wave,
    WorkPacket,
)


def _make_plan() -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="plan-1",
        mission_id="mission-1",
        waves=[
            Wave(
                wave_number=0,
                description="Wave 0",
                work_packets=[
                    WorkPacket(packet_id="pkt-1", title="Task 1", builder_prompt="Do task 1")
                ],
            ),
            Wave(
                wave_number=1,
                description="Wave 1",
                work_packets=[
                    WorkPacket(packet_id="pkt-2", title="Task 2", builder_prompt="Do task 2")
                ],
            ),
        ],
    )


def test_run_supervised_continues_to_next_wave_until_complete(tmp_path: Path) -> None:
    from spec_orch.services.round_orchestrator import RoundOrchestrator
    from spec_orch.services.workers.in_memory_worker_handle_factory import (
        InMemoryWorkerHandleFactory,
    )
    from spec_orch.services.workers.oneshot_worker_handle import OneShotWorkerHandle

    class StubBuilderAdapter:
        ADAPTER_NAME = "stub"
        AGENT_NAME = "stub"

        def __init__(self) -> None:
            self.prompts: list[str] = []

        def run(self, *, issue, workspace: Path, run_id=None, event_logger=None) -> BuilderResult:
            self.prompts.append(issue.builder_prompt or "")
            return BuilderResult(
                succeeded=True,
                command=["stub"],
                stdout="ok",
                stderr="",
                report_path=workspace / "builder_report.json",
                adapter="stub",
                agent="stub",
            )

    class StubSupervisor:
        ADAPTER_NAME = "stub"

        def review_round(
            self, *, round_artifacts, plan, round_history, context=None
        ) -> RoundDecision:
            return RoundDecision(action=RoundAction.CONTINUE, summary="Continue")

    class StubAssembler:
        def assemble(self, spec, issue, workspace, memory=None, repo_root=None):
            return {"node": spec.node_name, "issue_id": issue.issue_id}

    builder = StubBuilderAdapter()
    factory = InMemoryWorkerHandleFactory(
        creator=lambda session_id, workspace: OneShotWorkerHandle(
            session_id=session_id,
            builder_adapter=builder,
        )
    )
    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=StubSupervisor(),
        worker_factory=factory,
        context_assembler=StubAssembler(),
    )

    result = orchestrator.run_supervised(mission_id="mission-1", plan=_make_plan())

    assert result.completed is True
    assert result.paused is False
    assert len(result.rounds) == 2
    assert [round_.wave_id for round_ in result.rounds] == [0, 1]
    assert builder.prompts == ["Do task 1", "Do task 2"]
    assert (tmp_path / "docs/specs/mission-1/rounds/round-01/round_summary.json").exists()


def test_run_supervised_pauses_on_ask_human(tmp_path: Path) -> None:
    from spec_orch.services.round_orchestrator import RoundOrchestrator
    from spec_orch.services.workers.in_memory_worker_handle_factory import (
        InMemoryWorkerHandleFactory,
    )
    from spec_orch.services.workers.oneshot_worker_handle import OneShotWorkerHandle

    class StubBuilderAdapter:
        ADAPTER_NAME = "stub"
        AGENT_NAME = "stub"

        def run(self, *, issue, workspace: Path, run_id=None, event_logger=None) -> BuilderResult:
            return BuilderResult(
                succeeded=True,
                command=["stub"],
                stdout="ok",
                stderr="",
                report_path=workspace / "builder_report.json",
                adapter="stub",
                agent="stub",
            )

    class StubSupervisor:
        ADAPTER_NAME = "stub"

        def review_round(
            self, *, round_artifacts, plan, round_history, context=None
        ) -> RoundDecision:
            return RoundDecision(
                action=RoundAction.ASK_HUMAN,
                summary="Need a human decision.",
                blocking_questions=["Should packet 2 be dropped?"],
            )

    class StubAssembler:
        def assemble(self, spec, issue, workspace, memory=None, repo_root=None):
            return {}

    factory = InMemoryWorkerHandleFactory(
        creator=lambda session_id, workspace: OneShotWorkerHandle(
            session_id=session_id,
            builder_adapter=StubBuilderAdapter(),
        )
    )
    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=StubSupervisor(),
        worker_factory=factory,
        context_assembler=StubAssembler(),
    )

    result = orchestrator.run_supervised(mission_id="mission-1", plan=_make_plan())

    assert result.completed is False
    assert result.paused is True
    assert len(result.rounds) == 1
    assert result.last_decision is not None
    assert result.last_decision.action is RoundAction.ASK_HUMAN


def test_run_supervised_retries_same_wave_when_decision_is_retry(tmp_path: Path) -> None:
    from spec_orch.services.round_orchestrator import RoundOrchestrator
    from spec_orch.services.workers.in_memory_worker_handle_factory import (
        InMemoryWorkerHandleFactory,
    )
    from spec_orch.services.workers.oneshot_worker_handle import OneShotWorkerHandle

    class StubBuilderAdapter:
        ADAPTER_NAME = "stub"
        AGENT_NAME = "stub"

        def __init__(self) -> None:
            self.prompts: list[str] = []

        def run(self, *, issue, workspace: Path, run_id=None, event_logger=None) -> BuilderResult:
            self.prompts.append(issue.builder_prompt or "")
            return BuilderResult(
                succeeded=True,
                command=["stub"],
                stdout="ok",
                stderr="",
                report_path=workspace / "builder_report.json",
                adapter="stub",
                agent="stub",
            )

    class StubSupervisor:
        ADAPTER_NAME = "stub"

        def __init__(self) -> None:
            self.calls = 0

        def review_round(
            self, *, round_artifacts, plan, round_history, context=None
        ) -> RoundDecision:
            self.calls += 1
            if self.calls == 1:
                return RoundDecision(action=RoundAction.RETRY, summary="Retry same wave.")
            return RoundDecision(action=RoundAction.STOP, summary="Stop after retry.")

    class StubAssembler:
        def assemble(self, spec, issue, workspace, memory=None, repo_root=None):
            return {"history": len(workspace.parts)}

    builder = StubBuilderAdapter()
    factory = InMemoryWorkerHandleFactory(
        creator=lambda session_id, workspace: OneShotWorkerHandle(
            session_id=session_id,
            builder_adapter=builder,
        )
    )
    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=StubSupervisor(),
        worker_factory=factory,
        context_assembler=StubAssembler(),
        max_rounds=3,
    )

    result = orchestrator.run_supervised(mission_id="mission-1", plan=_make_plan())

    assert result.completed is True
    assert len(result.rounds) == 2
    assert [round_.wave_id for round_ in result.rounds] == [0, 0]
    assert result.rounds[-1].decision is not None
    assert result.rounds[-1].decision.action is RoundAction.STOP


def test_run_supervised_resumes_from_persisted_history(tmp_path: Path) -> None:
    from spec_orch.services.io import atomic_write_json
    from spec_orch.services.round_orchestrator import RoundOrchestrator
    from spec_orch.services.workers.in_memory_worker_handle_factory import (
        InMemoryWorkerHandleFactory,
    )
    from spec_orch.services.workers.oneshot_worker_handle import OneShotWorkerHandle

    class StubBuilderAdapter:
        ADAPTER_NAME = "stub"
        AGENT_NAME = "stub"

        def __init__(self) -> None:
            self.prompts: list[str] = []

        def run(self, *, issue, workspace: Path, run_id=None, event_logger=None) -> BuilderResult:
            self.prompts.append(issue.builder_prompt or "")
            return BuilderResult(
                succeeded=True,
                command=["stub"],
                stdout="ok",
                stderr="",
                report_path=workspace / "builder_report.json",
                adapter="stub",
                agent="stub",
            )

    class StubSupervisor:
        ADAPTER_NAME = "stub"

        def review_round(
            self, *, round_artifacts, plan, round_history, context=None
        ) -> RoundDecision:
            return RoundDecision(action=RoundAction.STOP, summary="Stop on resumed wave.")

    class StubAssembler:
        def assemble(self, spec, issue, workspace, memory=None, repo_root=None):
            return {}

    rounds_dir = tmp_path / "docs" / "specs" / "mission-1" / "rounds" / "round-01"
    rounds_dir.mkdir(parents=True)
    atomic_write_json(
        rounds_dir / "round_summary.json",
        RoundSummary(
            round_id=1,
            wave_id=0,
            status=RoundStatus.DECIDED,
            decision=RoundDecision(action=RoundAction.CONTINUE, summary="Move to wave 1."),
        ).to_dict(),
    )

    builder = StubBuilderAdapter()
    factory = InMemoryWorkerHandleFactory(
        creator=lambda session_id, workspace: OneShotWorkerHandle(
            session_id=session_id,
            builder_adapter=builder,
        )
    )
    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=StubSupervisor(),
        worker_factory=factory,
        context_assembler=StubAssembler(),
    )

    result = orchestrator.run_supervised(
        mission_id="mission-1",
        plan=_make_plan(),
        initial_round=1,
    )

    assert [round_.round_id for round_ in result.rounds] == [1, 2]
    assert [round_.wave_id for round_ in result.rounds] == [0, 1]
    assert builder.prompts == ["Do task 2"]


def test_run_supervised_replans_remaining_packets(tmp_path: Path) -> None:
    from spec_orch.services.round_orchestrator import RoundOrchestrator
    from spec_orch.services.workers.in_memory_worker_handle_factory import (
        InMemoryWorkerHandleFactory,
    )
    from spec_orch.services.workers.oneshot_worker_handle import OneShotWorkerHandle

    class StubBuilderAdapter:
        ADAPTER_NAME = "stub"
        AGENT_NAME = "stub"

        def __init__(self) -> None:
            self.prompts: list[str] = []

        def run(self, *, issue, workspace: Path, run_id=None, event_logger=None) -> BuilderResult:
            self.prompts.append(issue.builder_prompt or "")
            return BuilderResult(
                succeeded=True,
                command=["stub"],
                stdout="ok",
                stderr="",
                report_path=workspace / "builder_report.json",
                adapter="stub",
                agent="stub",
            )

    class StubSupervisor:
        ADAPTER_NAME = "stub"

        def __init__(self) -> None:
            self.calls = 0

        def review_round(
            self, *, round_artifacts, plan, round_history, context=None
        ) -> RoundDecision:
            self.calls += 1
            if self.calls == 1:
                return RoundDecision(
                    action=RoundAction.REPLAN_REMAINING,
                    summary="Retarget remaining work.",
                    plan_patch=PlanPatch(
                        modified_packets={
                            "pkt-1": {"builder_prompt": "Do task 1 again, but differently"}
                        }
                    ),
                )
            return RoundDecision(action=RoundAction.STOP, summary="Done replanning.")

    class StubAssembler:
        def assemble(self, spec, issue, workspace, memory=None, repo_root=None):
            return {}

    builder = StubBuilderAdapter()
    factory = InMemoryWorkerHandleFactory(
        creator=lambda session_id, workspace: OneShotWorkerHandle(
            session_id=session_id,
            builder_adapter=builder,
        )
    )
    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=StubSupervisor(),
        worker_factory=factory,
        context_assembler=StubAssembler(),
        max_rounds=3,
    )

    result = orchestrator.run_supervised(mission_id="mission-1", plan=_make_plan())

    assert result.completed is True
    assert [round_.wave_id for round_ in result.rounds] == [0, 0]
    assert builder.prompts == [
        "Do task 1",
        "Retarget remaining work.\n\nUpdated packet brief:\nDo task 1 again, but differently",
    ]
