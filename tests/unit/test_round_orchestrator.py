from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spec_orch.acceptance_core.models import (
    AcceptanceJudgment,
    AcceptanceJudgmentClass,
    AcceptanceRunMode,
    AcceptanceWorkflowState,
    CandidateFinding,
)
from spec_orch.domain.models import (
    AcceptanceIssueProposal,
    AcceptanceMode,
    AcceptanceReviewResult,
    BuilderResult,
    ExecutionPlan,
    PlanPatch,
    RoundAction,
    RoundDecision,
    RoundStatus,
    RoundSummary,
    VisualEvaluationResult,
    Wave,
    WorkPacket,
)
from spec_orch.runtime_chain.store import read_chain_events, read_chain_status
from spec_orch.services.memory.service import MemoryService, reset_memory_service


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


def _make_single_wave_plan() -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="plan-ctx",
        mission_id="mission-ctx",
        waves=[
            Wave(
                wave_number=0,
                description="Wave ctx",
                work_packets=[
                    WorkPacket(
                        packet_id="pkt-ctx",
                        title="Task ctx",
                        builder_prompt="Do task ctx",
                        files_in_scope=["src/a.py", "src/b.py"],
                        acceptance_criteria=["packet done"],
                    )
                ],
            )
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
    assert len(builder.prompts) == 2
    assert "## Task" in builder.prompts[0]
    assert "Do task 1" in builder.prompts[0]
    assert "## Task" in builder.prompts[1]
    assert "Do task 2" in builder.prompts[1]
    assert (tmp_path / "docs/specs/mission-1/rounds/round-01/round_summary.json").exists()
    chain_root = tmp_path / "docs/specs/mission-1/operator/runtime_chain"
    chain_status = read_chain_status(chain_root)
    chain_events = read_chain_events(chain_root)
    assert chain_status is not None
    assert chain_status.subject_kind.value == "mission"
    assert chain_events
    assert chain_events[0].subject_kind.value == "mission"
    assert any(
        event.subject_kind.value == "round" and event.subject_id == "round-01"
        for event in chain_events
    )
    assert any(
        event.subject_kind.value == "packet" and event.subject_id == "pkt-1"
        for event in chain_events
    )


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
    intervention_history = [
        json.loads(line)
        for line in (tmp_path / "docs" / "specs" / "mission-1" / "operator" / "interventions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert intervention_history == [
        {
            "intervention_id": "mission-1-round-1-approval",
            "decision_record_id": "mission-1-round-1-review",
            "point_key": "mission.round.review",
            "mission_id": "mission-1",
            "round_id": 1,
            "summary": "Need a human decision.",
            "questions": ["Should packet 2 be dropped?"],
            "status": "open",
            "created_at": intervention_history[0]["created_at"],
            "review_route": "/?mission=mission-1&mode=missions&tab=approvals&round=1",
        }
    ]


def test_run_supervised_uses_unique_packet_spans_per_round(tmp_path: Path) -> None:
    from spec_orch.services.round_orchestrator import RoundOrchestrator
    from spec_orch.services.workers.in_memory_worker_handle_factory import (
        InMemoryWorkerHandleFactory,
    )
    from spec_orch.services.workers.oneshot_worker_handle import OneShotWorkerHandle

    plan = ExecutionPlan(
        plan_id="plan-repeat",
        mission_id="mission-repeat",
        waves=[
            Wave(
                wave_number=0,
                description="Wave 0",
                work_packets=[
                    WorkPacket(packet_id="pkt-repeat", title="Task 1", builder_prompt="Do task 1")
                ],
            ),
            Wave(
                wave_number=1,
                description="Wave 1",
                work_packets=[
                    WorkPacket(packet_id="pkt-repeat", title="Task 2", builder_prompt="Do task 2")
                ],
            ),
        ],
    )

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
            return RoundDecision(action=RoundAction.CONTINUE, summary="Continue")

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

    result = orchestrator.run_supervised(mission_id="mission-repeat", plan=plan)

    assert result.completed is True
    chain_root = tmp_path / "docs/specs/mission-repeat/operator/runtime_chain"
    packet_started_events = [
        event
        for event in read_chain_events(chain_root)
        if event.subject_kind.value == "packet" and event.phase.value == "started"
    ]
    assert len(packet_started_events) == 2
    assert {event.subject_id for event in packet_started_events} == {"pkt-repeat"}
    assert len({event.span_id for event in packet_started_events}) == 2


def test_run_supervised_enriches_supervisor_context_and_persists_visual_eval(
    tmp_path: Path,
) -> None:
    from spec_orch.services.mission_service import MissionService
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

        def __init__(self) -> None:
            self.round_artifacts = None
            self.context = None

        def review_round(
            self, *, round_artifacts, plan, round_history, context=None
        ) -> RoundDecision:
            self.round_artifacts = round_artifacts
            self.context = context
            return RoundDecision(action=RoundAction.STOP, summary="Done")

    class StubAssembler:
        def __init__(self) -> None:
            self.issue = None
            self.workspace = None

        def assemble(self, spec, issue, workspace, memory=None, repo_root=None):
            self.issue = issue
            self.workspace = workspace
            return {"node": spec.node_name, "constraints": issue.context.constraints}

    class StubVisualEvaluator:
        ADAPTER_NAME = "stub_visual"

        def evaluate_round(
            self,
            *,
            mission_id: str,
            round_id: int,
            wave,
            worker_results,
            repo_root: Path,
            round_dir: Path,
        ) -> VisualEvaluationResult | None:
            return VisualEvaluationResult(
                evaluator="stub_visual",
                summary="UI looks correct.",
                confidence=0.82,
                findings=[{"severity": "low", "summary": "Minor spacing issue."}],
                artifacts={"screenshot": str(round_dir / "screenshot.png")},
            )

    mission_service = MissionService(tmp_path)
    mission = mission_service.create_mission(
        "Mission ctx",
        mission_id="mission-ctx",
        acceptance_criteria=["mission done"],
        constraints=["stay within API"],
    )
    spec_path = tmp_path / mission.spec_path
    spec_path.write_text("# Mission ctx\n\n## Intent\n\nShip the feature.\n")

    builder = StubBuilderAdapter()
    supervisor = StubSupervisor()
    assembler = StubAssembler()
    factory = InMemoryWorkerHandleFactory(
        creator=lambda session_id, workspace: OneShotWorkerHandle(
            session_id=session_id,
            builder_adapter=builder,
        )
    )
    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=supervisor,
        worker_factory=factory,
        context_assembler=assembler,
        visual_evaluator=StubVisualEvaluator(),
    )

    result = orchestrator.run_supervised(mission_id="mission-ctx", plan=_make_single_wave_plan())

    assert result.completed is True
    assert supervisor.round_artifacts is not None
    assert supervisor.round_artifacts.visual_evaluation is not None
    assert supervisor.round_artifacts.visual_evaluation.summary == "UI looks correct."
    assert assembler.issue is not None
    assert assembler.issue.acceptance_criteria == ["mission done", "packet done"]
    assert assembler.issue.context.constraints == ["stay within API"]
    assert sorted(assembler.issue.context.files_to_read) == ["src/a.py", "src/b.py"]
    assert supervisor.context["mission"]["mission_id"] == "mission-ctx"
    assert supervisor.context["wave"]["packet_ids"] == ["pkt-ctx"]
    assert (
        (tmp_path / "docs/specs/mission-ctx/rounds/round-01/task.spec.md")
        .read_text(encoding="utf-8")
        .startswith("# Mission ctx")
    )
    visual_path = tmp_path / "docs/specs/mission-ctx/rounds/round-01/visual_evaluation.json"
    assert visual_path.exists()


def test_run_supervised_treats_visual_evaluator_failure_as_non_fatal(tmp_path: Path) -> None:
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

        def __init__(self) -> None:
            self.visual_evaluation = "unset"

        def review_round(
            self, *, round_artifacts, plan, round_history, context=None
        ) -> RoundDecision:
            self.visual_evaluation = round_artifacts.visual_evaluation
            return RoundDecision(action=RoundAction.STOP, summary="Done")

    class StubAssembler:
        def assemble(self, spec, issue, workspace, memory=None, repo_root=None):
            return {}

    class FailingVisualEvaluator:
        ADAPTER_NAME = "failing_visual"

        def evaluate_round(
            self,
            *,
            mission_id: str,
            round_id: int,
            wave,
            worker_results,
            repo_root: Path,
            round_dir: Path,
        ) -> VisualEvaluationResult | None:
            raise RuntimeError("browser exploded")

    supervisor = StubSupervisor()
    factory = InMemoryWorkerHandleFactory(
        creator=lambda session_id, workspace: OneShotWorkerHandle(
            session_id=session_id,
            builder_adapter=StubBuilderAdapter(),
        )
    )
    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=supervisor,
        worker_factory=factory,
        context_assembler=StubAssembler(),
        visual_evaluator=FailingVisualEvaluator(),
    )

    result = orchestrator.run_supervised(mission_id="mission-1", plan=_make_single_wave_plan())

    assert result.completed is True
    assert supervisor.visual_evaluation is None
    visual_path = tmp_path / "docs/specs/mission-1/rounds/round-01/visual_evaluation.json"
    assert not visual_path.exists()


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


def test_run_supervised_persists_acceptance_review_and_files_issue(tmp_path: Path) -> None:
    import spec_orch.services.memory.service as mem_mod
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
            return RoundDecision(action=RoundAction.STOP, summary="Done")

    class StubAssembler:
        def assemble(self, spec, issue, workspace, memory=None, repo_root=None):
            return {}

    class StubAcceptanceEvaluator:
        ADAPTER_NAME = "stub_acceptance"

        def evaluate_acceptance(
            self,
            *,
            mission_id: str,
            round_id: int,
            round_dir: Path,
            worker_results,
            artifacts,
            repo_root: Path,
            campaign=None,
        ) -> AcceptanceReviewResult | None:
            return AcceptanceReviewResult(
                status="fail",
                summary="Acceptance failed.",
                confidence=0.93,
                evaluator="stub_acceptance",
                issue_proposals=[
                    AcceptanceIssueProposal(
                        title="Fix acceptance regression",
                        summary="Regression detected by acceptance evaluator.",
                        severity="high",
                        confidence=0.93,
                    )
                ],
            )

    class StubAcceptanceFiler:
        def apply(self, result: AcceptanceReviewResult, *, mission_id: str, round_id: int):
            proposals = [
                replace(p, linear_issue_id="SON-321", filing_status="filed")
                for p in result.issue_proposals
            ]
            return replace(result, issue_proposals=proposals)

    factory = InMemoryWorkerHandleFactory(
        creator=lambda session_id, workspace: OneShotWorkerHandle(
            session_id=session_id,
            builder_adapter=StubBuilderAdapter(),
        )
    )
    reset_memory_service()
    svc = MemoryService(repo_root=tmp_path)
    mem_mod._instance = svc
    try:
        orchestrator = RoundOrchestrator(
            repo_root=tmp_path,
            supervisor=StubSupervisor(),
            worker_factory=factory,
            context_assembler=StubAssembler(),
            acceptance_evaluator=StubAcceptanceEvaluator(),
            acceptance_filer=StubAcceptanceFiler(),
        )

        result = orchestrator.run_supervised(mission_id="mission-1", plan=_make_single_wave_plan())
    finally:
        reset_memory_service()

    assert result.completed is True
    review_path = tmp_path / "docs/specs/mission-1/rounds/round-01/acceptance_review.json"
    assert review_path.exists()
    payload = review_path.read_text(encoding="utf-8")
    assert "SON-321" in payload
    memory_entry = svc.get("acceptance-judgment-mission-1-round-1-proposal:0")
    assert memory_entry is not None
    assert memory_entry.metadata["mission_id"] == "mission-1"
    assert memory_entry.metadata["provenance"] == "reviewed"


def test_run_supervised_passes_browser_evidence_to_acceptance_evaluator(
    tmp_path: Path, monkeypatch
) -> None:
    import spec_orch.services.acceptance_pipeline as acceptance_pipeline_module
    from spec_orch.domain.models import AcceptanceMode
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
            return RoundDecision(action=RoundAction.STOP, summary="Done")

    class StubAssembler:
        def assemble(self, spec, issue, workspace, memory=None, repo_root=None):
            return {}

    captured_artifacts: dict[str, object] = {}
    captured_campaign: dict[str, object] = {}

    class StubAcceptanceEvaluator:
        ADAPTER_NAME = "stub_acceptance"

        def evaluate_acceptance(
            self,
            *,
            mission_id: str,
            round_id: int,
            round_dir: Path,
            worker_results,
            artifacts,
            repo_root: Path,
            campaign=None,
        ) -> AcceptanceReviewResult | None:
            captured_artifacts.update(artifacts)
            captured_campaign["value"] = campaign
            return AcceptanceReviewResult(
                status="pass",
                summary="Acceptance passed.",
                confidence=0.9,
                evaluator="stub_acceptance",
            )

    monkeypatch.setenv("SPEC_ORCH_VISUAL_EVAL_URL", "http://127.0.0.1:4173")
    monkeypatch.setenv("SPEC_ORCH_VISUAL_EVAL_PATHS", "/,/settings")
    monkeypatch.setattr(
        acceptance_pipeline_module,
        "collect_playwright_browser_evidence",
        lambda **kwargs: {
            "tested_routes": ["/", "/settings"],
            "interactions": {"/settings": [{"action": "click_text", "status": "passed"}]},
            "screenshots": {"/": "rounds/round-01/visual/root.png"},
            "console_errors": [],
            "page_errors": [],
            "artifact_paths": {"round_dir": str(kwargs["round_dir"])},
        },
    )

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
        acceptance_evaluator=StubAcceptanceEvaluator(),
    )

    result = orchestrator.run_supervised(mission_id="mission-1", plan=_make_single_wave_plan())

    assert result.completed is True
    assert captured_artifacts["browser_evidence"] == {
        "tested_routes": ["/", "/settings"],
        "interactions": {"/settings": [{"action": "click_text", "status": "passed"}]},
        "screenshots": {"/": "rounds/round-01/visual/root.png"},
        "console_errors": [],
        "page_errors": [],
        "artifact_paths": {"round_dir": str(tmp_path / "docs/specs/mission-1/rounds/round-01")},
    }
    assert captured_campaign["value"] is not None
    assert captured_campaign["value"].mode is AcceptanceMode.FEATURE_SCOPED
    assert captured_campaign["value"].primary_routes == ["/", "/settings"]
    assert captured_campaign["value"].min_primary_routes == 2
    assert captured_campaign["value"].related_route_budget == 1
    assert captured_campaign["value"].interaction_budget == "tight"
    assert captured_campaign["value"].required_interactions == ["verify declared feature flow"]
    assert captured_campaign["value"].related_routes == [
        "/?mission=mission-1&mode=missions&tab=transcript&round=1"
    ]
    assert captured_campaign["value"].interaction_plans == {}


def test_run_supervised_records_acceptance_graph_trace_artifacts(tmp_path: Path) -> None:
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
            return RoundDecision(action=RoundAction.STOP, summary="Done")

    class StubAssembler:
        def assemble(self, spec, issue, workspace, memory=None, repo_root=None):
            return {}

    class StubAcceptanceEvaluator:
        ADAPTER_NAME = "stub_acceptance"

        def invoke_acceptance_graph_step(self, *, system_prompt: str, user_prompt: str) -> str:
            payload = json.loads(user_prompt.split("\n", 3)[-1])
            step_key = payload["step_key"]
            next_transition = {
                "contract_brief": "route_replay",
                "route_replay": "assert_contract",
                "assert_contract": "summarize_judgment",
                "summarize_judgment": "",
            }[step_key]
            return json.dumps(
                {
                    "decision": "continue" if next_transition else "complete",
                    "outputs": {f"{step_key}_artifact": "ok"},
                    "next_transition": next_transition,
                    "warnings": [],
                    "review_markdown": f"## {step_key}",
                }
            )

        def evaluate_acceptance(
            self,
            *,
            mission_id: str,
            round_id: int,
            round_dir: Path,
            worker_results,
            artifacts,
            repo_root: Path,
            campaign=None,
        ) -> AcceptanceReviewResult | None:
            assert artifacts["graph_run"].endswith("graph_run.json")
            assert artifacts["graph_profile"] == "verify_contract_graph"
            assert len(artifacts["step_artifacts"]) == 4
            return AcceptanceReviewResult(
                status="pass",
                summary="Acceptance graph completed.",
                confidence=0.8,
                evaluator="stub_acceptance",
                tested_routes=["/"],
                findings=[],
                issue_proposals=[],
                artifacts=dict(artifacts),
            )

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
        acceptance_evaluator=StubAcceptanceEvaluator(),
    )

    result = orchestrator.run_supervised(mission_id="mission-1", plan=_make_single_wave_plan())

    assert result.completed is True
    review_path = tmp_path / "docs/specs/mission-1/rounds/round-01/acceptance_review.json"
    payload = json.loads(review_path.read_text(encoding="utf-8"))
    assert payload["artifacts"]["graph_run"].endswith("graph_run.json")
    assert payload["artifacts"]["graph_profile"] == "verify_contract_graph"
    assert len(payload["artifacts"]["step_artifacts"]) == 4
    chain_events = read_chain_events(tmp_path / "docs/specs/mission-1/operator/runtime_chain")
    phases = [(event.span_id, event.phase.value, event.status_reason) for event in chain_events]
    round_completed_index = phases.index(
        next(item for item in phases if item[2] == "round_completed")
    )
    acceptance_graph_completed_index = phases.index(
        next(item for item in phases if item[2] == "acceptance_graph_completed")
    )
    assert round_completed_index > acceptance_graph_completed_index
    observability_root = (
        tmp_path / "docs/specs/mission-1/operator/observability/round-01-acceptance-graph"
    )
    live_summary = json.loads(
        (observability_root / "live_summary.json").read_text(encoding="utf-8")
    )
    assert live_summary["phase"] == "completed"
    assert live_summary["budget"]["planned_steps"] == 4


def test_run_supervised_continues_when_acceptance_graph_trace_fails(tmp_path: Path) -> None:
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
            return RoundDecision(action=RoundAction.STOP, summary="Done")

    class StubAssembler:
        def assemble(self, spec, issue, workspace, memory=None, repo_root=None):
            return {}

    class StubAcceptanceEvaluator:
        ADAPTER_NAME = "stub_acceptance"

        def invoke_acceptance_graph_step(self, *, system_prompt: str, user_prompt: str) -> str:
            raise ValueError("step output contained an unbalanced JSON object")

        def evaluate_acceptance(
            self,
            *,
            mission_id: str,
            round_id: int,
            round_dir: Path,
            worker_results,
            artifacts,
            repo_root: Path,
            campaign=None,
        ) -> AcceptanceReviewResult | None:
            assert "graph_run" not in artifacts
            assert (
                artifacts["graph_trace_error"] == "step output contained an unbalanced JSON object"
            )
            return AcceptanceReviewResult(
                status="warn",
                summary="Acceptance graph degraded gracefully.",
                confidence=0.6,
                evaluator="stub_acceptance",
                tested_routes=["/"],
                findings=[],
                issue_proposals=[],
                artifacts=dict(artifacts),
            )

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
        acceptance_evaluator=StubAcceptanceEvaluator(),
    )

    result = orchestrator.run_supervised(mission_id="mission-1", plan=_make_single_wave_plan())

    assert result.completed is True
    review_path = tmp_path / "docs/specs/mission-1/rounds/round-01/acceptance_review.json"
    payload = json.loads(review_path.read_text(encoding="utf-8"))
    assert payload["summary"] == "Acceptance graph degraded gracefully."
    assert (
        payload["artifacts"]["graph_trace_error"]
        == "step output contained an unbalanced JSON object"
    )


def test_run_supervised_appends_fixture_graduation_from_repeated_reviewed_candidate(
    tmp_path: Path,
) -> None:
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
            return RoundDecision(action=RoundAction.STOP, summary="Done")

    class StubAssembler:
        def assemble(self, spec, issue, workspace, memory=None, repo_root=None):
            return {}

    class StubAcceptanceEvaluator:
        ADAPTER_NAME = "stub_acceptance"

        def invoke_acceptance_graph_step(self, *, system_prompt: str, user_prompt: str) -> str:
            payload = json.loads(user_prompt.split("\n", 3)[-1])
            step_key = payload["step_key"]
            next_transition = {
                "contract_brief": "route_replay",
                "route_replay": "assert_contract",
                "assert_contract": "summarize_judgment",
                "surface_scan": "guided_probe",
                "guided_probe": "candidate_review",
                "candidate_review": "summarize_judgment",
                "summarize_judgment": "",
            }[step_key]
            return json.dumps(
                {
                    "decision": "continue" if next_transition else "complete",
                    "outputs": {f"{step_key}_artifact": "ok"},
                    "next_transition": next_transition,
                    "warnings": [],
                    "review_markdown": f"## {step_key}",
                }
            )

        def evaluate_acceptance(
            self,
            *,
            mission_id: str,
            round_id: int,
            round_dir: Path,
            worker_results,
            artifacts,
            repo_root: Path,
            campaign=None,
        ) -> AcceptanceReviewResult | None:
            return AcceptanceReviewResult(
                status="warn",
                summary="Repeated transcript orientation issue still reproduces.",
                confidence=0.91,
                evaluator="stub_acceptance",
                acceptance_mode="exploratory",
                coverage_status="complete",
                findings=[],
                issue_proposals=[
                    AcceptanceIssueProposal(
                        title="Transcript orientation issue",
                        summary="Transcript route needs stronger orientation.",
                        severity="medium",
                        route="/?mission=mission-1&mode=missions&tab=transcript",
                        confidence=0.72,
                        hold_reason="Needs repeated confirmation before filing.",
                        why_it_matters="Operators may miss the main evidence path.",
                        critique_axis="surface_orientation",
                        operator_task="trace_transcript_route",
                        artifact_paths={
                            "acceptance_review": "docs/specs/mission-1/rounds/round-01/acceptance_review.json"
                        },
                        filing_status="filed",
                        linear_issue_id="SON-999",
                    )
                ],
                artifacts=dict(artifacts),
            )

    reset_memory_service()
    svc = MemoryService(repo_root=tmp_path)
    svc.record_acceptance_judgments(
        mission_id="mission-1",
        round_id=0,
        judgments=[
            AcceptanceJudgment(
                judgment_id="proposal:older-1",
                judgment_class=AcceptanceJudgmentClass.CANDIDATE_FINDING,
                run_mode=AcceptanceRunMode.EXPLORE,
                workflow_state=AcceptanceWorkflowState.REVIEWED,
                summary="Transcript route needs stronger orientation.",
                candidate=CandidateFinding(
                    finding_id="candidate:older-1",
                    claim="Transcript route needs stronger orientation.",
                    route="/?mission=mission-1&mode=missions&tab=transcript",
                    baseline_ref="fixture:dashboard-transcript-regression",
                    origin_step="candidate_review",
                    graph_profile="tuned_exploratory_graph",
                    run_mode="explore",
                    compare_overlay=True,
                    promotion_test="Replay transcript route with orientation breadcrumbs visible.",
                    recommended_next_step="Promote to fixture candidate when repeated.",
                    dedupe_key="dashboard:transcript-orientation",
                ),
            ),
            AcceptanceJudgment(
                judgment_id="proposal:older-2",
                judgment_class=AcceptanceJudgmentClass.CANDIDATE_FINDING,
                run_mode=AcceptanceRunMode.EXPLORE,
                workflow_state=AcceptanceWorkflowState.REVIEWED,
                summary="Transcript route needs stronger orientation.",
                candidate=CandidateFinding(
                    finding_id="candidate:older-2",
                    claim="Transcript route needs stronger orientation.",
                    route="/?mission=mission-1&mode=missions&tab=transcript",
                    baseline_ref="fixture:dashboard-transcript-regression",
                    origin_step="candidate_review",
                    graph_profile="tuned_exploratory_graph",
                    run_mode="explore",
                    compare_overlay=True,
                    promotion_test="Replay transcript route with orientation breadcrumbs visible.",
                    recommended_next_step="Promote to fixture candidate when repeated.",
                    dedupe_key="dashboard:transcript-orientation",
                ),
            ),
        ],
    )

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
        acceptance_evaluator=StubAcceptanceEvaluator(),
    )

    try:
        with patch("spec_orch.services.memory.service._instance", svc):
            result = orchestrator.run_supervised(
                mission_id="mission-1",
                plan=_make_single_wave_plan(),
            )
    finally:
        reset_memory_service()

    assert result.completed is True
    graduations_path = tmp_path / "docs/specs/mission-1/operator/fixture_graduations.jsonl"
    rows = [
        json.loads(line)
        for line in graduations_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    assert rows[0]["stage"] == "fixture_candidate"
    assert rows[0]["dedupe_key"] == "/?mission=mission-1&mode=missions&tab=transcript"
    assert rows[0]["repeat_count"] == 3
    assert rows[0]["graph_profile"] == "verify_contract_graph"
    assert rows[0]["graph_run"].endswith("graph_run.json")
    assert len(rows[0]["step_artifacts"]) == 4
    assert rows[0]["graph_transitions"][-1] == "assert_contract->summarize_judgment"
    seed_dir = tmp_path / "docs/specs/mission-1/operator/fixture_candidates"
    seeds = sorted(seed_dir.glob("*.json"))
    assert len(seeds) == 1
    seed_payload = json.loads(seeds[0].read_text(encoding="utf-8"))
    assert seed_payload["event"]["judgment_id"] == "proposal:0"
    assert (
        seed_payload["expected"]["field_expectations"]["graph_profile"] == "verify_contract_graph"
    )
    assert seed_payload["expected"]["step_artifacts"][0].endswith("01-contract_brief.json")


def test_build_acceptance_campaign_sets_mode_specific_coverage_budgets(
    tmp_path: Path, monkeypatch
) -> None:
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    mission_dir = tmp_path / "docs/specs/mission-1"
    mission_dir.mkdir(parents=True)
    (mission_dir / "mission.json").write_text(
        json.dumps(
            {
                "mission_id": "mission-1",
                "title": "Mission 1",
                "acceptance_criteria": ["launcher works", "mission visible"],
                "constraints": [],
                "approved": True,
            }
        ),
        encoding="utf-8",
    )

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=None,
        worker_factory=None,
        context_assembler=None,
    )
    artifacts = {
        "review_routes": {
            "overview": "/?mission=mission-1&tab=overview",
            "transcript": "/?mission=mission-1&tab=transcript",
            "approvals": "/?mission=mission-1&tab=approvals",
            "visual_qa": "/?mission=mission-1&tab=visual",
            "judgment": "/?mission=mission-1&tab=judgment",
            "costs": "/?mission=mission-1&tab=costs",
        },
    }

    monkeypatch.setenv("SPEC_ORCH_ACCEPTANCE_MODE", AcceptanceMode.IMPACT_SWEEP.value)
    impact = orchestrator._build_acceptance_campaign(mission_id="mission-1", artifacts=artifacts)
    assert impact.primary_routes == ["/"]
    assert impact.min_primary_routes == 1
    assert impact.related_route_budget == 3
    assert impact.related_routes == [
        "/?mission=mission-1&tab=transcript",
        "/?mission=mission-1&tab=visual",
        "/?mission=mission-1&tab=costs",
    ]
    assert impact.interaction_budget == "moderate"
    assert impact.required_interactions == [
        "verify declared feature flow",
        "sweep adjacent mission surfaces",
    ]
    assert impact.interaction_plans["/?mission=mission-1&tab=transcript"][0].target == "Visual QA"
    assert impact.interaction_plans["/?mission=mission-1&tab=transcript"][-1].target == "Transcript"

    monkeypatch.setenv("SPEC_ORCH_ACCEPTANCE_MODE", AcceptanceMode.WORKFLOW.value)
    workflow = orchestrator._build_acceptance_campaign(mission_id="mission-1", artifacts=artifacts)
    assert workflow.primary_routes == [
        "/",
        "/?mission=mission-1&mode=missions&tab=overview",
    ]
    assert workflow.related_route_budget == 5
    assert workflow.related_routes == [
        "/?mission=mission-1&tab=transcript",
        "/?mission=mission-1&tab=approvals",
        "/?mission=mission-1&tab=judgment",
        "/?mission=mission-1&tab=visual",
        "/?mission=mission-1&tab=costs",
    ]
    assert workflow.interaction_budget == "moderate"
    assert workflow.required_interactions == [
        "open launcher",
        "switch across operator modes",
        "select the mission",
        "open the core mission detail tabs",
        "confirm workflow surfaces stay reachable end-to-end",
    ]
    assert workflow.filing_policy == "auto_file_broken_flows_only"
    assert workflow.interaction_plans["/"][0].action == "click_selector"
    assert workflow.interaction_plans["/"][0].target == '[data-automation-target="open-launcher"]'
    assert (
        workflow.interaction_plans["/"][1].target
        == '[data-automation-target="launcher-action"][data-launcher-action="refresh-readiness"]'
    )
    assert (
        workflow.interaction_plans["/"][2].target
        == '[data-automation-target="launcher-action"][data-launcher-action="refresh-readiness"].is-complete'
    )
    assert (
        workflow.interaction_plans["/"][3].target
        == '[data-automation-target="operator-mode"][data-mode-key="missions"]'
    )
    assert (
        workflow.interaction_plans["/"][4].target
        == '[data-automation-target="operator-mode"][data-mode-key="missions"][data-active="true"]'
    )
    assert (
        workflow.interaction_plans["/"][5].target
        == '[data-automation-target="operator-mode"][data-mode-key="approvals"]'
    )
    assert (
        workflow.interaction_plans["/"][6].target
        == '[data-automation-target="operator-mode"][data-mode-key="approvals"][data-active="true"]'
    )
    assert (
        workflow.interaction_plans["/"][7].target
        == '[data-automation-target="operator-mode"][data-mode-key="evidence"]'
    )
    assert (
        workflow.interaction_plans["/"][8].target
        == '[data-automation-target="operator-mode"][data-mode-key="evidence"][data-active="true"]'
    )
    assert (
        workflow.interaction_plans["/"][9].target
        == '[data-automation-target="operator-mode"][data-mode-key="inbox"]'
    )
    assert (
        workflow.interaction_plans["/"][10].target
        == '[data-automation-target="operator-mode"][data-mode-key="inbox"][data-active="true"]'
    )
    assert (
        workflow.interaction_plans["/"][11].target
        == '[data-automation-target="operator-mode"][data-mode-key="missions"]'
    )
    assert (
        workflow.interaction_plans["/"][12].target
        == '[data-automation-target="operator-mode"][data-mode-key="missions"][data-active="true"]'
    )
    assert (
        workflow.interaction_plans["/"][13].target
        == '[data-automation-target="mission-card"][data-mission-id="mission-1"]'
    )
    assert (
        workflow.interaction_plans["/"][14].target
        == '[data-automation-target="mission-detail-ready"][data-mission-id="mission-1"]'
    )
    assert (
        workflow.interaction_plans["/?mission=mission-1&mode=missions&tab=overview"][0].target
        == '[data-automation-target="mission-tab"][data-tab-key="transcript"]'
    )
    assert (
        workflow.interaction_plans["/?mission=mission-1&mode=missions&tab=overview"][2].target
        == '[data-automation-target="mission-tab"][data-tab-key="approvals"]'
    )
    assert (
        workflow.interaction_plans["/?mission=mission-1&mode=missions&tab=overview"][4].target
        == '[data-automation-target="mission-tab"][data-tab-key="visual-qa"]'
    )
    assert (
        workflow.interaction_plans["/?mission=mission-1&mode=missions&tab=overview"][6].target
        == '[data-automation-target="mission-tab"][data-tab-key="judgment"]'
    )
    assert (
        workflow.interaction_plans["/?mission=mission-1&mode=missions&tab=overview"][7].target
        == '[data-automation-target="mission-tab"][data-tab-key="judgment"][data-active="true"]'
    )
    assert (
        workflow.interaction_plans["/?mission=mission-1&mode=missions&tab=overview"][8].target
        == '[data-automation-target="mission-tab"][data-tab-key="costs"]'
    )
    assert (
        workflow.interaction_plans["/?mission=mission-1&mode=missions&tab=overview"][10].target
        == '[data-automation-target="mission-tab"][data-tab-key="overview"]'
    )
    assert (
        workflow.interaction_plans["/?mission=mission-1&mode=missions&tab=overview"][-1].target
        == '[data-automation-target="mission-tab"][data-tab-key="overview"][data-active="true"]'
    )
    assert workflow.coverage_expectations[-11:] == [
        "launcher panel can be opened from the header",
        "needs attention mode can be selected from mission control",
        "missions mode can be selected from mission control",
        "decision queue mode can be selected from mission control",
        "deep evidence mode can be selected from mission control",
        "the target mission can be selected from the mission list",
        "the transcript tab can be opened from mission detail",
        "the approvals surface exposes actionable operator controls when present",
        "the visual QA tab can be opened from mission detail",
        "the judgment tab can be opened from mission detail",
        "the costs tab can be opened from mission detail",
    ]

    monkeypatch.setenv("SPEC_ORCH_ACCEPTANCE_MODE", AcceptanceMode.EXPLORATORY.value)
    exploratory = orchestrator._build_acceptance_campaign(
        mission_id="mission-1", artifacts=artifacts
    )
    assert exploratory.primary_routes == [
        "/",
        "/?mission=mission-1&tab=overview",
    ]
    assert exploratory.seed_routes == [
        "/",
        "/?mission=mission-1&tab=overview",
    ]
    assert exploratory.min_primary_routes == 2
    assert exploratory.related_route_budget == 4
    assert exploratory.related_routes == [
        "/?mission=mission-1&tab=transcript",
        "/?mission=mission-1&tab=judgment",
        "/?mission=mission-1&tab=costs",
        "/?mission=mission-1&tab=visual",
    ]
    assert exploratory.allowed_expansions == [
        "/?mission=mission-1&tab=transcript",
        "/?mission=mission-1&tab=judgment",
        "/?mission=mission-1&tab=costs",
        "/?mission=mission-1&tab=visual",
    ]
    assert exploratory.interaction_budget == "wide"
    assert exploratory.evidence_budget == "bounded"
    assert exploratory.required_interactions == [
        "complete the intended operator task",
        "switch into adjacent surfaces when the task suggests it",
    ]
    assert exploratory.coverage_expectations == [
        "operator can establish launcher context",
        "operator can inspect mission detail from the overview surface",
        "operator can expand into adjacent mission surfaces",
        "operator can inspect at least one deeper evidence surface",
    ]
    assert exploratory.critique_focus == [
        "information architecture confusion",
        "ambiguous terminology",
        "discoverability gaps",
        "context switching friction",
    ]
    assert exploratory.stop_conditions == [
        "stop when the route budget is exhausted",
        "stop when no adjacent surface adds new operator evidence",
        "stop after confirming a materially broken flow",
    ]
    assert (
        exploratory.interaction_plans["/"][0].target == '[data-automation-target="open-launcher"]'
    )
    assert (
        exploratory.interaction_plans["/?mission=mission-1&tab=overview"][0].target
        == '[data-automation-target="mission-detail-ready"][data-mission-id="mission-1"]'
    )
    assert (
        exploratory.interaction_plans["/?mission=mission-1&tab=overview"][1].target
        == '[data-automation-target="mission-tab"][data-tab-key="transcript"]'
    )
    assert (
        exploratory.interaction_plans["/?mission=mission-1&tab=transcript"][0].target
        == '[data-automation-target="mission-detail-ready"][data-mission-id="mission-1"]'
    )
    assert (
        exploratory.interaction_plans["/?mission=mission-1&tab=transcript"][1].target
        == '[data-automation-target="transcript-filter"][data-filter-key="all"]'
    )
    assert exploratory.interaction_plans["/?mission=mission-1&tab=transcript"][1].timeout_ms == 4000
    assert (
        exploratory.interaction_plans["/?mission=mission-1&tab=transcript"][3].target
        == '[data-automation-target="transcript-filter"][data-filter-key="all"][data-active="true"]'
    )
    assert (
        exploratory.interaction_plans["/?mission=mission-1&tab=transcript"][4].target
        == '[data-automation-target="transcript-block"]'
    )
    assert (
        exploratory.interaction_plans["/?mission=mission-1&tab=transcript"][5].target
        == '[data-automation-target="transcript-block"][data-active="true"]'
    )
    assert (
        exploratory.interaction_plans["/?mission=mission-1&tab=transcript"][6].target
        == '[data-automation-target="transcript-inspector"]'
    )
    assert exploratory.interaction_plans["/?mission=mission-1&tab=transcript"][6].timeout_ms == 4000
    assert (
        exploratory.interaction_plans["/?mission=mission-1&tab=judgment"][0].target
        == '[data-automation-target="internal-route"][data-route-label="Open raw acceptance artifact"]'
    )
    assert exploratory.interaction_plans["/?mission=mission-1&tab=judgment"][0].timeout_ms == 1500
    assert (
        exploratory.interaction_plans["/?mission=mission-1&tab=visual"][0].target
        == '[data-automation-target="internal-route"][data-route-label="Open visual review"]'
    )
    assert exploratory.interaction_plans["/?mission=mission-1&tab=visual"][0].timeout_ms == 1500


def test_build_acceptance_campaign_honors_explicit_mode_override(
    tmp_path: Path, monkeypatch
) -> None:
    from spec_orch.domain.models import AcceptanceMode
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    mission_dir = tmp_path / "docs/specs/mission-1"
    mission_dir.mkdir(parents=True)
    (mission_dir / "mission.json").write_text(
        json.dumps(
            {
                "mission_id": "mission-1",
                "title": "Mission 1",
                "acceptance_criteria": ["launcher works"],
                "constraints": [],
                "approved": True,
            }
        ),
        encoding="utf-8",
    )

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=None,
        worker_factory=None,
        context_assembler=None,
    )
    artifacts = {
        "review_routes": {
            "overview": "/?mission=mission-1&tab=overview",
            "transcript": "/?mission=mission-1&tab=transcript",
            "acceptance": "/?mission=mission-1&tab=acceptance",
            "costs": "/?mission=mission-1&tab=costs",
        },
    }

    monkeypatch.delenv("SPEC_ORCH_ACCEPTANCE_MODE", raising=False)

    campaign = orchestrator._build_acceptance_campaign(
        mission_id="mission-1",
        artifacts=artifacts,
        mode_override=AcceptanceMode.EXPLORATORY,
    )

    assert campaign.mode is AcceptanceMode.EXPLORATORY
    assert campaign.seed_routes == ["/", "/?mission=mission-1&tab=overview"]
    assert campaign.critique_focus == [
        "information architecture confusion",
        "ambiguous terminology",
        "discoverability gaps",
        "context switching friction",
    ]
    assert (
        campaign.interaction_plans["/?mission=mission-1&tab=costs"][0].target
        == '[data-automation-target="internal-route"][data-route-label="Open cost review"]'
    )


def test_build_acceptance_campaign_uses_default_dashboard_review_routes_for_exploratory(
    tmp_path: Path, monkeypatch
) -> None:
    from spec_orch.domain.models import AcceptanceMode
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    mission_dir = tmp_path / "docs/specs/mission-2"
    mission_dir.mkdir(parents=True)
    (mission_dir / "mission.json").write_text(
        json.dumps(
            {
                "mission_id": "mission-2",
                "title": "Mission 2",
                "acceptance_criteria": ["dashboard is usable"],
                "constraints": [],
                "approved": True,
            }
        ),
        encoding="utf-8",
    )

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=None,
        worker_factory=None,
        context_assembler=None,
    )
    monkeypatch.delenv("SPEC_ORCH_ACCEPTANCE_MODE", raising=False)

    campaign = orchestrator._build_acceptance_campaign(
        mission_id="mission-2",
        artifacts={},
        mode_override=AcceptanceMode.EXPLORATORY,
    )

    assert campaign.primary_routes == [
        "/",
        "/?mission=mission-2&mode=missions&tab=overview",
    ]
    assert campaign.related_routes == [
        "/?mission=mission-2&mode=missions&tab=transcript",
        "/?mission=mission-2&mode=missions&tab=judgment",
        "/?mission=mission-2&mode=missions&tab=costs",
        "/?mission=mission-2&mode=missions&tab=visual",
    ]


def test_build_acceptance_campaign_escapes_mission_id_for_workflow_css_selector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    mission_id = 'mission"with\\quotes'
    mission_dir = tmp_path / "docs" / "specs" / mission_id
    mission_dir.mkdir(parents=True)
    (mission_dir / "mission.json").write_text(
        json.dumps(
            {
                "id": mission_id,
                "title": "Mission 1",
                "acceptance_criteria": [],
                "constraints": [],
                "approved": True,
            }
        ),
        encoding="utf-8",
    )

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=None,
        worker_factory=None,
        context_assembler=None,
    )
    monkeypatch.setenv("SPEC_ORCH_ACCEPTANCE_MODE", AcceptanceMode.WORKFLOW.value)

    campaign = orchestrator._build_acceptance_campaign(
        mission_id=mission_id,
        artifacts={"review_routes": {}},
    )

    assert (
        campaign.interaction_plans["/"][13].target
        == '[data-automation-target="mission-card"][data-mission-id="mission\\"with\\\\quotes"]'
    )


def test_build_acceptance_campaign_workflow_allows_single_env_primary_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    mission_dir = tmp_path / "docs" / "specs" / "mission-1"
    mission_dir.mkdir(parents=True)
    (mission_dir / "mission.json").write_text(
        json.dumps(
            {
                "id": "mission-1",
                "title": "Mission 1",
                "acceptance_criteria": [],
                "constraints": [],
                "approved": True,
            }
        ),
        encoding="utf-8",
    )

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=None,
        worker_factory=None,
        context_assembler=None,
    )
    monkeypatch.setenv("SPEC_ORCH_ACCEPTANCE_MODE", AcceptanceMode.WORKFLOW.value)
    monkeypatch.setenv("SPEC_ORCH_VISUAL_EVAL_PATHS", "/")

    campaign = orchestrator._build_acceptance_campaign(
        mission_id="mission-1",
        artifacts={"review_routes": {}},
    )

    assert campaign.primary_routes == ["/"]
    assert campaign.min_primary_routes == 1


def test_workflow_launcher_mutation_campaign_can_raise_approve_plan_wait_timeout() -> None:
    from spec_orch.domain.models import AcceptanceCampaign, AcceptanceInteractionStep

    campaign = AcceptanceCampaign(
        mode=AcceptanceMode.WORKFLOW,
        goal="Verify launcher mutation flow can create a draft and plan locally.",
        primary_routes=["/"],
        interaction_plans={
            "/": [
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="launcher-action"][data-launcher-action="approve-plan"]',
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="launcher-status"][data-tone="success"]',
                    timeout_ms=90000,
                ),
            ]
        },
    )

    restored = AcceptanceCampaign.from_dict(campaign.to_dict())

    assert restored.interaction_plans["/"][1].timeout_ms == 90000


def test_build_acceptance_campaign_uses_visual_eval_paths_env_for_primary_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    mission_dir = tmp_path / "docs" / "specs" / "mission-1"
    mission_dir.mkdir(parents=True)
    (mission_dir / "mission.json").write_text(
        json.dumps(
            {
                "id": "mission-1",
                "title": "Mission 1",
                "acceptance_criteria": ["launcher works"],
                "constraints": [],
                "approved": True,
            }
        ),
        encoding="utf-8",
    )

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=None,
        worker_factory=None,
        context_assembler=None,
    )

    monkeypatch.setenv("SPEC_ORCH_ACCEPTANCE_MODE", AcceptanceMode.IMPACT_SWEEP.value)
    monkeypatch.setenv("SPEC_ORCH_VISUAL_EVAL_PATHS", "/,/launcher")

    campaign = orchestrator._build_acceptance_campaign(
        mission_id="mission-1",
        artifacts={"review_routes": {}},
    )

    assert campaign.primary_routes == ["/", "/launcher"]


def test_run_supervised_persists_round_before_acceptance_side_effects(tmp_path: Path) -> None:
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
            return RoundDecision(action=RoundAction.STOP, summary="Done")

    class StubAssembler:
        def assemble(self, spec, issue, workspace, memory=None, repo_root=None):
            return {}

    class StubAcceptanceEvaluator:
        ADAPTER_NAME = "stub_acceptance"

        def evaluate_acceptance(
            self,
            *,
            mission_id: str,
            round_id: int,
            round_dir: Path,
            worker_results,
            artifacts,
            repo_root: Path,
            campaign=None,
        ) -> AcceptanceReviewResult | None:
            return AcceptanceReviewResult(
                status="warn",
                summary="Acceptance warning.",
                confidence=0.5,
                evaluator="stub_acceptance",
            )

    class InspectingAcceptanceFiler:
        def apply(self, result: AcceptanceReviewResult, *, mission_id: str, round_id: int):
            summary_path = (
                tmp_path
                / "docs"
                / "specs"
                / mission_id
                / "rounds"
                / f"round-{round_id:02d}"
                / "round_summary.json"
            )
            assert summary_path.exists(), "round summary should exist before acceptance filing"
            return result

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
        acceptance_evaluator=StubAcceptanceEvaluator(),
        acceptance_filer=InspectingAcceptanceFiler(),
    )

    result = orchestrator.run_supervised(mission_id="mission-1", plan=_make_single_wave_plan())

    assert result.completed is True


def test_run_supervised_records_acceptance_filing_failure_without_failing_round(
    tmp_path: Path,
) -> None:
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
            return RoundDecision(action=RoundAction.STOP, summary="Done")

    class StubAssembler:
        def assemble(self, spec, issue, workspace, memory=None, repo_root=None):
            return {}

    class StubAcceptanceEvaluator:
        ADAPTER_NAME = "stub_acceptance"

        def evaluate_acceptance(
            self,
            *,
            mission_id: str,
            round_id: int,
            round_dir: Path,
            worker_results,
            artifacts,
            repo_root: Path,
            campaign=None,
        ) -> AcceptanceReviewResult | None:
            return AcceptanceReviewResult(
                status="fail",
                summary="Acceptance failed.",
                confidence=0.95,
                evaluator="stub_acceptance",
                issue_proposals=[
                    AcceptanceIssueProposal(
                        title="Fix regression",
                        summary="Regression detected.",
                        severity="high",
                        confidence=0.95,
                    )
                ],
            )

    class FailingAcceptanceFiler:
        def apply(self, result: AcceptanceReviewResult, *, mission_id: str, round_id: int):
            raise RuntimeError("filing exploded")

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
        acceptance_evaluator=StubAcceptanceEvaluator(),
        acceptance_filer=FailingAcceptanceFiler(),
    )

    result = orchestrator.run_supervised(mission_id="mission-1", plan=_make_single_wave_plan())

    assert result.completed is True
    review_path = tmp_path / "docs/specs/mission-1/rounds/round-01/acceptance_review.json"
    assert review_path.exists()
    payload = review_path.read_text(encoding="utf-8")
    assert "filing exploded" in payload


def test_run_supervised_writes_packet_telemetry_and_activity_log(tmp_path: Path) -> None:
    from spec_orch.services.round_orchestrator import RoundOrchestrator
    from spec_orch.services.workers.in_memory_worker_handle_factory import (
        InMemoryWorkerHandleFactory,
    )
    from spec_orch.services.workers.oneshot_worker_handle import OneShotWorkerHandle

    class StubBuilderAdapter:
        ADAPTER_NAME = "stub"
        AGENT_NAME = "stub"

        def run(self, *, issue, workspace: Path, run_id=None, event_logger=None) -> BuilderResult:
            assert event_logger is not None
            event_logger(
                {
                    "event_type": "item.completed",
                    "message": "worker applied patch",
                    "component": "builder",
                    "adapter": "stub",
                    "agent": "stub",
                    "data": {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "worker applied patch"},
                    },
                }
            )
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
            return RoundDecision(action=RoundAction.STOP, summary="Stop after one round.")

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

    assert result.completed is True
    packet_workspace = tmp_path / "docs/specs/mission-1/workers/pkt-1"
    telemetry_dir = packet_workspace / "telemetry"
    events_path = telemetry_dir / "events.jsonl"
    activity_log_path = telemetry_dir / "activity.log"
    assert events_path.exists()
    assert activity_log_path.exists()
    events = [line for line in events_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(events) >= 3
    assert any("mission_packet_started" in line for line in events)
    assert any("item.completed" in line for line in events)
    assert any("mission_packet_completed" in line for line in events)
    activity_text = activity_log_path.read_text(encoding="utf-8")
    assert "worker applied patch" in activity_text
    assert "Completed packet pkt-1" in activity_text


def test_run_supervised_emits_terminal_failure_event_when_worker_raises(tmp_path: Path) -> None:
    from spec_orch.services.round_orchestrator import RoundOrchestrator
    from spec_orch.services.workers.in_memory_worker_handle_factory import (
        InMemoryWorkerHandleFactory,
    )
    from spec_orch.services.workers.oneshot_worker_handle import OneShotWorkerHandle

    class StubBuilderAdapter:
        ADAPTER_NAME = "stub"
        AGENT_NAME = "stub"

        def run(self, *, issue, workspace: Path, run_id=None, event_logger=None) -> BuilderResult:
            raise RuntimeError("worker exploded")

    class StubSupervisor:
        ADAPTER_NAME = "stub"

        def review_round(
            self, *, round_artifacts, plan, round_history, context=None
        ) -> RoundDecision:
            return RoundDecision(action=RoundAction.STOP, summary="unreachable")

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
    packet_workspace = tmp_path / "docs/specs/mission-1/workers/pkt-1"
    telemetry_dir = packet_workspace / "telemetry"
    events_path = telemetry_dir / "events.jsonl"
    activity_log_path = telemetry_dir / "activity.log"
    assert events_path.exists()
    assert activity_log_path.exists()
    events = [line for line in events_path.read_text(encoding="utf-8").splitlines() if line]
    assert any("mission_packet_started" in line for line in events)
    assert any("mission_packet_completed" in line for line in events)
    assert any("worker exploded" in line for line in events)
    activity_text = activity_log_path.read_text(encoding="utf-8")
    assert "Failed packet pkt-1" in activity_text
    assert "worker exploded" in activity_text


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
    assert len(builder.prompts) == 1
    assert "## Task" in builder.prompts[0]
    assert "Do task 2" in builder.prompts[0]


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
    assert len(builder.prompts) == 2
    assert "## Task" in builder.prompts[0]
    assert "Do task 1" in builder.prompts[0]
    assert "## Task" in builder.prompts[1]
    assert "Retarget remaining work." in builder.prompts[1]
    assert "Do task 1 again, but differently" in builder.prompts[1]


def test_run_supervised_worker_prompt_uses_builder_envelope(tmp_path: Path) -> None:
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
                return RoundDecision(action=RoundAction.RETRY, summary="Retry with migration note.")
            return RoundDecision(action=RoundAction.STOP, summary="done")

    class StubAssembler:
        def assemble(self, spec, issue, workspace, memory=None, repo_root=None):
            return {}

    plan = ExecutionPlan(
        plan_id="plan-1",
        mission_id="mission-1",
        waves=[
            Wave(
                wave_number=0,
                description="Wave 0",
                work_packets=[
                    WorkPacket(
                        packet_id="pkt-1",
                        title="Task 1",
                        builder_prompt="Implement migration fix",
                        files_in_scope=["src/migrate.py", "tests/test_migrate.py"],
                        acceptance_criteria=["migration passes", "tests cover rollback"],
                        verification_commands={
                            "lint": ["python", "-m", "ruff", "check", "src/"],
                            "test": ["python", "-m", "pytest", "-q"],
                        },
                    )
                ],
            )
        ],
    )

    packet_workspace = tmp_path / "docs" / "specs" / "mission-1" / "workers" / "pkt-1"
    packet_workspace.mkdir(parents=True, exist_ok=True)
    (packet_workspace / "src").mkdir(parents=True, exist_ok=True)
    (packet_workspace / "tests").mkdir(parents=True, exist_ok=True)
    (packet_workspace / "src" / "migrate.py").write_text("print('ok')\n", encoding="utf-8")
    (packet_workspace / "tests" / "test_migrate.py").write_text(
        "def test_stub():\n    assert True\n",
        encoding="utf-8",
    )
    (packet_workspace / "btw_context.md").write_text(
        "Focus on preserving backward compatibility.",
        encoding="utf-8",
    )
    (packet_workspace / "task.spec.md").write_text(
        "Spec details for the migration packet.",
        encoding="utf-8",
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
        max_rounds=2,
    )

    result = orchestrator.run_supervised(mission_id="mission-1", plan=plan)

    assert result.completed is True
    assert len(builder.prompts) == 2
    initial_prompt = builder.prompts[0]
    followup_prompt = builder.prompts[1]
    assert "## Task" in initial_prompt
    assert "Implement migration fix" in initial_prompt
    assert "## Acceptance Criteria" in initial_prompt
    assert "migration passes" in initial_prompt
    assert "## Files to Read" in initial_prompt
    assert "src/migrate.py" in initial_prompt
    assert "## Verification Commands" in initial_prompt
    assert "ruff check" in initial_prompt
    assert "## Spec" in initial_prompt
    assert "Spec details for the migration packet." in initial_prompt
    assert "## Additional Context (injected via /btw)" in initial_prompt
    assert "Focus on preserving backward compatibility." in initial_prompt
    assert "Retry with migration note." in followup_prompt


def test_run_supervised_replays_plan_patch_on_resume(tmp_path: Path) -> None:
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
            return RoundDecision(action=RoundAction.STOP, summary="Stop after resume.")

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
            decision=RoundDecision(
                action=RoundAction.REPLAN_REMAINING,
                summary="Replan current wave.",
                plan_patch=PlanPatch(
                    modified_packets={
                        "pkt-1": {"builder_prompt": "Do task 1 with replayed plan patch"}
                    }
                ),
            ),
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

    assert result.completed is True
    assert [round_.round_id for round_ in result.rounds] == [1, 2]
    assert [round_.wave_id for round_ in result.rounds] == [0, 0]
    assert len(builder.prompts) == 1
    assert "## Task" in builder.prompts[0]
    assert "Do task 1 with replayed plan patch" in builder.prompts[0]


def test_build_worker_prompt_moves_missing_output_targets_out_of_files_to_read(
    tmp_path: Path,
) -> None:
    from spec_orch.domain.models import WorkPacket
    from spec_orch.services.round_orchestrator import RoundOrchestrator
    from spec_orch.services.workers.in_memory_worker_handle_factory import (
        InMemoryWorkerHandleFactory,
    )
    from spec_orch.services.workers.oneshot_worker_handle import OneShotWorkerHandle

    class StubSupervisor:
        pass

    class StubAssembler:
        pass

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=StubSupervisor(),
        worker_factory=InMemoryWorkerHandleFactory(
            creator=lambda session_id, workspace: OneShotWorkerHandle(
                session_id=session_id,
                builder_adapter=MagicMock(),
            )
        ),
        context_assembler=StubAssembler(),
        max_rounds=1,
    )

    workspace = tmp_path / "docs" / "specs" / "mission-1" / "workers" / "pkt-new"
    workspace.mkdir(parents=True, exist_ok=True)
    packet = WorkPacket(
        packet_id="pkt-new",
        title="Scaffold mission types",
        builder_prompt="Create src/contracts/mission_types.ts with minimal interfaces.",
        files_in_scope=["src/contracts/mission_types.ts"],
        acceptance_criteria=["File exists"],
    )

    prompt = orchestrator._build_worker_prompt(
        mission_id="mission-1",
        packet=packet,
        workspace=workspace,
        decision=None,
    )

    assert "## Target Files" in prompt
    assert "src/contracts/mission_types.ts" in prompt
    assert "## Files to Read" not in prompt


def test_run_supervised_applies_plan_patch_during_retry(tmp_path: Path) -> None:
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
                    action=RoundAction.RETRY,
                    summary="Retry with narrowed packet brief.",
                    plan_patch=PlanPatch(
                        modified_packets={
                            "pkt-1": {"builder_prompt": "Retry migration with narrowed scope"}
                        }
                    ),
                )
            return RoundDecision(action=RoundAction.STOP, summary="done")

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
        max_rounds=2,
    )

    result = orchestrator.run_supervised(mission_id="mission-1", plan=_make_plan())

    assert result.completed is True
    assert len(builder.prompts) == 2
    assert "Do task 1" in builder.prompts[0]
    assert "Retry migration with narrowed scope" in builder.prompts[1]


def test_build_acceptance_artifacts_splits_fresh_and_replay_proof(tmp_path: Path) -> None:
    from spec_orch.domain.models import RoundArtifacts, RoundSummary
    from spec_orch.services.mission_service import MissionService
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    mission = MissionService(tmp_path).create_mission("Fresh Mission", mission_id="fresh-mission")
    operator_dir = tmp_path / "docs" / "specs" / mission.mission_id / "operator"
    operator_dir.mkdir(parents=True, exist_ok=True)
    (operator_dir / "mission_bootstrap.json").write_text(
        json.dumps({"mission_id": mission.mission_id, "fresh": True}) + "\n",
        encoding="utf-8",
    )
    (operator_dir / "launch.json").write_text(
        json.dumps({"mission_id": mission.mission_id, "state": "launched"}) + "\n",
        encoding="utf-8",
    )
    (operator_dir / "daemon_run.json").write_text(
        json.dumps({"mission_id": mission.mission_id, "state": "picked_up"}) + "\n",
        encoding="utf-8",
    )

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=None,
        worker_factory=None,
        context_assembler=None,
    )
    payload = orchestrator._build_acceptance_artifacts(
        mission_id=mission.mission_id,
        round_id=3,
        artifacts=RoundArtifacts(
            round_id=3,
            mission_id=mission.mission_id,
            builder_reports=[{"packet_id": "pkt-1", "succeeded": True}],
            worker_session_ids=["worker-1"],
        ),
        summary=RoundSummary(round_id=3, wave_id=0, status=RoundStatus.REVIEWING),
    )

    assert payload["fresh_execution"]["proof_type"] == "fresh_execution"
    assert payload["fresh_execution"]["mission_bootstrap"]["fresh"] is True
    assert payload["fresh_execution"]["launch"]["state"] == "launched"
    assert payload["fresh_execution"]["daemon_run"]["state"] == "picked_up"
    assert payload["fresh_execution"]["fresh_round_path"].endswith("round-03")
    assert payload["fresh_execution"]["builder_execution_summary"]["builder_reports"] == [
        {"packet_id": "pkt-1", "succeeded": True}
    ]
    assert payload["workflow_replay"]["proof_type"] == "workflow_replay"
    assert payload["workflow_replay"]["review_routes"]["overview"].endswith("tab=overview")
    assert payload["proof_split"]["fresh_execution"]["proof_type"] == "fresh_execution"
    assert payload["proof_split"]["workflow_replay"]["proof_type"] == "workflow_replay"


def test_build_acceptance_artifacts_normalizes_nested_launch_state(tmp_path: Path) -> None:
    from spec_orch.domain.models import RoundArtifacts, RoundSummary
    from spec_orch.services.mission_service import MissionService
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    mission = MissionService(tmp_path).create_mission("Fresh Mission", mission_id="fresh-mission")
    operator_dir = tmp_path / "docs" / "specs" / mission.mission_id / "operator"
    operator_dir.mkdir(parents=True, exist_ok=True)
    (operator_dir / "mission_bootstrap.json").write_text(
        json.dumps({"mission_id": mission.mission_id, "fresh": True}) + "\n",
        encoding="utf-8",
    )
    (operator_dir / "launch.json").write_text(
        json.dumps(
            {
                "runner": {"status": "running"},
                "last_launch": {"state": {"mission_id": mission.mission_id, "phase": "executing"}},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (operator_dir / "daemon_run.json").write_text(
        json.dumps({"mission_id": mission.mission_id, "state": "picked_up"}) + "\n",
        encoding="utf-8",
    )

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=None,
        worker_factory=None,
        context_assembler=None,
    )
    payload = orchestrator._build_acceptance_artifacts(
        mission_id=mission.mission_id,
        round_id=3,
        artifacts=RoundArtifacts(
            round_id=3,
            mission_id=mission.mission_id,
            builder_reports=[{"packet_id": "pkt-1", "succeeded": True}],
            worker_session_ids=["worker-1"],
        ),
        summary=RoundSummary(round_id=3, wave_id=0, status=RoundStatus.REVIEWING),
    )

    assert payload["fresh_execution"]["launch"]["runner"]["status"] == "running"
    assert payload["fresh_execution"]["launch"]["state"]["phase"] == "executing"
    assert payload["fresh_execution"]["launch"]["state"]["mission_id"] == mission.mission_id


def test_run_acceptance_evaluation_delegates_to_acceptance_pipeline(tmp_path: Path) -> None:
    from spec_orch.domain.models import RoundArtifacts, RoundSummary
    from spec_orch.services.mission_service import MissionService
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    mission = MissionService(tmp_path).create_mission("Mission 1", mission_id="mission-1")
    round_dir = tmp_path / "docs" / "specs" / mission.mission_id / "rounds" / "round-01"
    round_dir.mkdir(parents=True, exist_ok=True)
    chain_root = tmp_path / "docs" / "specs" / mission.mission_id / "operator" / "runtime_chain"
    chain_root.mkdir(parents=True, exist_ok=True)

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=None,
        worker_factory=None,
        context_assembler=None,
        acceptance_evaluator=MagicMock(),
    )
    expected = AcceptanceReviewResult(
        status="pass",
        summary="delegated",
        confidence=0.8,
        evaluator="stub",
    )

    with patch.object(orchestrator._acceptance_pipeline, "run", return_value=expected) as mocked:
        result = orchestrator._run_acceptance_evaluation(
            mission_id=mission.mission_id,
            round_id=1,
            round_dir=round_dir,
            worker_results=[],
            artifacts=RoundArtifacts(round_id=1, mission_id=mission.mission_id),
            summary=RoundSummary(round_id=1, wave_id=0, status=RoundStatus.REVIEWING),
            chain_root=chain_root,
            chain_id="chain-1",
            round_span_id="round-01",
        )

    assert result is expected
    mocked.assert_called_once()


def test_build_fresh_acpx_post_run_campaign_substitutes_interaction_plan_keys(
    tmp_path: Path,
) -> None:
    from spec_orch.services.round_orchestrator import build_fresh_acpx_post_run_campaign

    campaign = build_fresh_acpx_post_run_campaign(tmp_path, "fresh-mission-123")

    assert "/?mission=fresh-mission-123&mode=missions&tab=overview" in campaign.interaction_plans
    assert not any("{mission_id}" in route for route in campaign.interaction_plans)


def test_collect_artifacts_records_verification_gate_and_manifest_paths(tmp_path: Path) -> None:
    from spec_orch.domain.models import BuilderResult, Wave, WorkPacket
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=None,
        worker_factory=None,
        context_assembler=None,
    )
    packet = WorkPacket(
        packet_id="pkt-1",
        title="Scaffold contract",
        files_in_scope=["src/contracts/mission_types.ts"],
        verification_commands={
            "scaffold_exists": [
                "{python}",
                "-c",
                "from pathlib import Path; raise SystemExit(0 if Path('src/contracts/mission_types.ts').exists() else 1)",
            ]
        },
    )
    workspace = orchestrator._packet_workspace("mission-1", packet)
    (workspace / "src" / "contracts").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "contracts" / "mission_types.ts").write_text(
        "export interface MissionType {}\n",
        encoding="utf-8",
    )
    report_path = workspace / "builder_report.json"
    report_path.write_text("{}", encoding="utf-8")
    artifacts = orchestrator._collect_artifacts(
        mission_id="mission-1",
        round_id=1,
        wave=Wave(wave_number=0, work_packets=[packet]),
        worker_results=[
            (
                packet,
                BuilderResult(
                    succeeded=True,
                    command=["builder"],
                    stdout="ok",
                    stderr="",
                    report_path=report_path,
                    adapter="stub",
                    agent="stub",
                ),
            )
        ],
        round_dir=tmp_path / "docs" / "specs" / "mission-1" / "rounds" / "round-01",
    )

    assert artifacts.verification_outputs
    assert artifacts.verification_outputs[0]["packet_id"] == "pkt-1"
    assert artifacts.verification_outputs[0]["all_passed"] is True
    assert artifacts.verification_outputs[0]["producer_role"] == "verifier"
    assert artifacts.builder_reports[0]["producer_role"] == "implementer"
    assert artifacts.gate_verdicts
    assert artifacts.gate_verdicts[0]["packet_id"] == "pkt-1"
    assert artifacts.gate_verdicts[0]["mergeable"] is True
    assert artifacts.gate_verdicts[0]["scope"]["all_in_scope"] is True
    assert artifacts.gate_verdicts[0]["scope"]["out_of_scope_files"] == []
    assert str(report_path) in artifacts.manifest_paths
    assert any(path.endswith("src/contracts/mission_types.ts") for path in artifacts.manifest_paths)


def test_persist_round_delegates_normalized_supervision_payload_write(tmp_path: Path) -> None:
    from spec_orch.domain.models import (
        RoundAction,
        RoundDecision,
        RoundStatus,
        RoundSummary,
        SessionOps,
    )
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=None,
        worker_factory=None,
        context_assembler=None,
    )
    round_dir = tmp_path / "docs" / "specs" / "mission-1" / "rounds" / "round-01"
    summary = RoundSummary(round_id=1, wave_id=0, status=RoundStatus.DECIDED)
    summary.decision = RoundDecision(
        action=RoundAction.ASK_HUMAN,
        summary="Need approval.",
        reason_code="needs_review",
        confidence=0.7,
        session_ops=SessionOps(reuse=[], spawn=[], cancel=[]),
        blocking_questions=["Approve?"],
    )

    delegated: dict[str, object] = {}

    def fake_write_round_supervision_payloads(
        round_dir_arg: Path,
        *,
        summary: dict,
        decision: dict | None,
    ) -> dict[str, Path]:
        delegated["round_dir"] = round_dir_arg
        delegated["summary"] = summary
        delegated["decision"] = decision
        round_dir_arg.mkdir(parents=True, exist_ok=True)
        summary_path = round_dir_arg / "round_summary.json"
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        written = {"summary": summary_path}
        if decision is not None:
            decision_path = round_dir_arg / "round_decision.json"
            decision_path.write_text(json.dumps(decision), encoding="utf-8")
            written["decision"] = decision_path
        return written

    with patch(
        "spec_orch.services.round_orchestrator.write_round_supervision_payloads",
        fake_write_round_supervision_payloads,
    ):
        orchestrator._persist_round(round_dir, summary)

    assert delegated["round_dir"] == round_dir
    assert isinstance(delegated["summary"], dict)
    assert isinstance(delegated["decision"], dict)


def test_collect_artifacts_marks_out_of_scope_workspace_files_as_non_mergeable(
    tmp_path: Path,
) -> None:
    from spec_orch.domain.models import BuilderResult, Wave, WorkPacket
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=None,
        worker_factory=None,
        context_assembler=None,
    )
    packet = WorkPacket(
        packet_id="pkt-1",
        title="Scaffold contract",
        files_in_scope=["src/contracts/mission_types.ts"],
        verification_commands={
            "scaffold_exists": [
                "{python}",
                "-c",
                "from pathlib import Path; raise SystemExit(0 if Path('src/contracts/mission_types.ts').exists() else 1)",
            ]
        },
    )
    workspace = orchestrator._packet_workspace("mission-1", packet)
    (workspace / "src" / "contracts").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "contracts" / "mission_types.ts").write_text(
        "export interface MissionType {}\n",
        encoding="utf-8",
    )
    (workspace / "src" / "contracts" / "rogue_types.ts").write_text(
        "export interface RogueType {}\n",
        encoding="utf-8",
    )
    report_path = workspace / "builder_report.json"
    report_path.write_text("{}", encoding="utf-8")

    artifacts = orchestrator._collect_artifacts(
        mission_id="mission-1",
        round_id=1,
        wave=Wave(wave_number=0, work_packets=[packet]),
        worker_results=[
            (
                packet,
                BuilderResult(
                    succeeded=True,
                    command=["builder"],
                    stdout="ok",
                    stderr="",
                    report_path=report_path,
                    adapter="stub",
                    agent="stub",
                ),
            )
        ],
        round_dir=tmp_path / "docs" / "specs" / "mission-1" / "rounds" / "round-01",
    )

    assert artifacts.gate_verdicts[0]["mergeable"] is False
    assert "scope" in artifacts.gate_verdicts[0]["failed_conditions"]
    assert artifacts.gate_verdicts[0]["scope"]["all_in_scope"] is False
    assert artifacts.gate_verdicts[0]["scope"]["out_of_scope_files"] == [
        "src/contracts/rogue_types.ts"
    ]


def test_collect_artifacts_ignores_harness_telemetry_for_scope_proof(
    tmp_path: Path,
) -> None:
    from spec_orch.domain.models import BuilderResult, Wave, WorkPacket
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=None,
        worker_factory=None,
        context_assembler=None,
    )
    packet = WorkPacket(
        packet_id="pkt-1",
        title="Scaffold contract",
        files_in_scope=["src/contracts/mission_types.ts"],
        verification_commands={
            "scaffold_exists": [
                "{python}",
                "-c",
                "from pathlib import Path; raise SystemExit(0 if Path('src/contracts/mission_types.ts').exists() else 1)",
            ]
        },
    )
    workspace = orchestrator._packet_workspace("mission-1", packet)
    (workspace / "src" / "contracts").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "contracts" / "mission_types.ts").write_text(
        "export interface MissionType {}\n",
        encoding="utf-8",
    )
    telemetry_dir = workspace / "telemetry"
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    (telemetry_dir / "events.jsonl").write_text("{}\n", encoding="utf-8")
    (telemetry_dir / "incoming_events.jsonl").write_text("{}\n", encoding="utf-8")
    (telemetry_dir / "activity.log").write_text("[10:00] started\n", encoding="utf-8")
    (workspace / "btw_context.md").write_text("Use the latest packet context.\n", encoding="utf-8")
    (workspace / "task.spec.md").write_text("# Task Spec\n", encoding="utf-8")
    report_path = workspace / "builder_report.json"
    report_path.write_text("{}", encoding="utf-8")

    artifacts = orchestrator._collect_artifacts(
        mission_id="mission-1",
        round_id=1,
        wave=Wave(wave_number=0, work_packets=[packet]),
        worker_results=[
            (
                packet,
                BuilderResult(
                    succeeded=True,
                    command=["builder"],
                    stdout="ok",
                    stderr="",
                    report_path=report_path,
                    adapter="stub",
                    agent="stub",
                ),
            )
        ],
        round_dir=tmp_path / "docs" / "specs" / "mission-1" / "rounds" / "round-01",
    )

    assert artifacts.gate_verdicts[0]["mergeable"] is True
    assert artifacts.gate_verdicts[0]["scope"]["all_in_scope"] is True
    assert artifacts.gate_verdicts[0]["scope"]["out_of_scope_files"] == []


def test_collect_artifacts_prefers_builder_report_files_changed_for_scope_proof(
    tmp_path: Path,
) -> None:
    from spec_orch.domain.models import BuilderResult, Wave, WorkPacket
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=None,
        worker_factory=None,
        context_assembler=None,
    )
    packet = WorkPacket(
        packet_id="pkt-1",
        title="Scaffold contracts",
        files_in_scope=["src/contracts/mission_types.ts", "src/contracts/artifact_types.ts"],
        verification_commands={
            "scaffold_exists": [
                "{python}",
                "-c",
                "from pathlib import Path; raise SystemExit(0 if Path('src/contracts/mission_types.ts').exists() else 1)",
            ]
        },
    )
    workspace = orchestrator._packet_workspace("mission-1", packet)
    (workspace / "src" / "contracts").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "contracts" / "mission_types.ts").write_text(
        "export interface MissionType {}\n",
        encoding="utf-8",
    )
    (workspace / "src" / "contracts" / "artifact_types.ts").write_text(
        "export interface ArtifactType {}\n",
        encoding="utf-8",
    )
    (workspace / "node_modules" / "left-pad").mkdir(parents=True, exist_ok=True)
    (workspace / "node_modules" / "left-pad" / "index.js").write_text(
        "module.exports = () => '';",
        encoding="utf-8",
    )
    (workspace / "tsconfig.json").write_text("{}", encoding="utf-8")
    report_path = workspace / "builder_report.json"
    report_path.write_text(
        json.dumps(
            {
                "files_changed": [
                    str(workspace / "src" / "contracts" / "mission_types.ts"),
                    str(workspace / "src" / "contracts" / "artifact_types.ts"),
                ]
            }
        ),
        encoding="utf-8",
    )

    artifacts = orchestrator._collect_artifacts(
        mission_id="mission-1",
        round_id=1,
        wave=Wave(wave_number=0, work_packets=[packet]),
        worker_results=[
            (
                packet,
                BuilderResult(
                    succeeded=True,
                    command=["builder"],
                    stdout="ok",
                    stderr="",
                    report_path=report_path,
                    adapter="stub",
                    agent="stub",
                ),
            )
        ],
        round_dir=tmp_path / "docs" / "specs" / "mission-1" / "rounds" / "round-01",
    )

    assert artifacts.gate_verdicts[0]["mergeable"] is True
    assert artifacts.gate_verdicts[0]["scope"]["realized_files"] == [
        "src/contracts/mission_types.ts",
        "src/contracts/artifact_types.ts",
    ]
    assert artifacts.gate_verdicts[0]["scope"]["out_of_scope_files"] == []


def test_collect_artifacts_ignores_transient_verification_support_files(
    tmp_path: Path,
) -> None:
    from spec_orch.domain.models import BuilderResult, Wave, WorkPacket
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=None,
        worker_factory=None,
        context_assembler=None,
    )
    packet = WorkPacket(
        packet_id="pkt-verify",
        title="Scaffold and verify contracts",
        files_in_scope=["src/contracts/mission_types.ts", "src/contracts/artifact_types.ts"],
        builder_prompt=("Create the contract files, then run lint and typecheck to verify them."),
        verification_commands={
            "scaffold_exists": [
                "{python}",
                "-c",
                "from pathlib import Path; raise SystemExit(0 if Path('src/contracts/mission_types.ts').exists() else 1)",
            ],
            "typescript_typecheck": ["tsc", "--noEmit", "src/contracts/mission_types.ts"],
            "typescript_lint_smoke": ["eslint", "src/contracts/mission_types.ts"],
        },
    )
    workspace = orchestrator._packet_workspace("mission-1", packet)
    (workspace / "src" / "contracts").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "contracts" / "mission_types.ts").write_text(
        "export interface MissionType {}\n",
        encoding="utf-8",
    )
    (workspace / "src" / "contracts" / "artifact_types.ts").write_text(
        "export interface ArtifactType {}\n",
        encoding="utf-8",
    )
    report_path = workspace / "builder_report.json"
    report_path.write_text(
        json.dumps(
            {
                "files_changed": [
                    str(workspace / "src" / "contracts" / "mission_types.ts"),
                    str(workspace / "src" / "contracts" / "artifact_types.ts"),
                    str(workspace / "tsconfig.json"),
                    str(workspace / "eslint.config.js"),
                    str(workspace / "eslint.config.mjs"),
                    str(workspace / "import_smoke.ts"),
                ]
            }
        ),
        encoding="utf-8",
    )

    artifacts = orchestrator._collect_artifacts(
        mission_id="mission-1",
        round_id=1,
        wave=Wave(wave_number=0, work_packets=[packet]),
        worker_results=[
            (
                packet,
                BuilderResult(
                    succeeded=True,
                    command=["builder"],
                    stdout="ok",
                    stderr="",
                    report_path=report_path,
                    adapter="stub",
                    agent="stub",
                ),
            )
        ],
        round_dir=tmp_path / "docs" / "specs" / "mission-1" / "rounds" / "round-01",
    )

    assert artifacts.gate_verdicts[0]["scope"]["out_of_scope_files"] == []
    assert "scope" not in artifacts.gate_verdicts[0]["failed_conditions"]


def test_build_packet_scope_proof_preserves_empty_files_changed_without_workspace_scan(
    tmp_path: Path,
) -> None:
    from spec_orch.domain.models import WorkPacket
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=None,
        worker_factory=None,
        context_assembler=None,
    )
    packet = WorkPacket(
        packet_id="pkt-empty",
        title="Scaffold and verify contracts",
        files_in_scope=["src/contracts/mission_types.ts"],
        builder_prompt="Create the contract file only.",
        verification_commands={
            "typescript_typecheck": ["tsc", "--noEmit", "src/contracts/mission_types.ts"]
        },
    )
    workspace = orchestrator._packet_workspace("mission-empty", packet)
    (workspace / "src" / "contracts").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "contracts" / "mission_types.ts").write_text(
        "export interface MissionType {}\n",
        encoding="utf-8",
    )
    (workspace / "outside.txt").write_text("noise\n", encoding="utf-8")
    report_path = workspace / "builder_report.json"
    report_path.write_text(json.dumps({"files_changed": []}), encoding="utf-8")

    scope = orchestrator._build_packet_scope_proof(
        workspace=workspace,
        packet=packet,
        report_path=report_path,
    )

    assert scope["realized_files"] == []
    assert scope["out_of_scope_files"] == []


def test_build_packet_scope_proof_ignores_directory_entries_from_builder_report(
    tmp_path: Path,
) -> None:
    from spec_orch.domain.models import WorkPacket
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=None,
        worker_factory=None,
        context_assembler=None,
    )
    packet = WorkPacket(
        packet_id="pkt-directories",
        title="Scaffold artifact types",
        files_in_scope=["src/contracts/artifact_types.ts"],
        builder_prompt="Create the artifact_types contract only.",
    )
    workspace = orchestrator._packet_workspace("mission-directories", packet)
    (workspace / "src" / "contracts").mkdir(parents=True, exist_ok=True)
    artifact_path = workspace / "src" / "contracts" / "artifact_types.ts"
    artifact_path.write_text("export interface ArtifactType {}\n", encoding="utf-8")
    report_path = workspace / "builder_report.json"
    report_path.write_text(
        json.dumps(
            {
                "files_changed": [
                    str(workspace),
                    str(workspace / "src"),
                    str(artifact_path),
                ]
            }
        ),
        encoding="utf-8",
    )

    scope = orchestrator._build_packet_scope_proof(
        workspace=workspace,
        packet=packet,
        report_path=report_path,
    )

    assert scope["realized_files"] == ["src/contracts/artifact_types.ts"]
    assert scope["out_of_scope_files"] == []
    assert scope["all_in_scope"] is True


def test_transient_verification_support_file_uses_verification_commands(tmp_path: Path) -> None:
    from spec_orch.domain.models import WorkPacket
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=None,
        worker_factory=None,
        context_assembler=None,
    )
    packet = WorkPacket(
        packet_id="pkt-support",
        title="Plain scaffold title",
        files_in_scope=["src/contracts/mission_types.ts"],
        builder_prompt="Create the contract file.",
        acceptance_criteria=["Contract compiles cleanly."],
        verification_commands={
            "typescript_typecheck": ["tsc", "--noEmit", "src/contracts/mission_types.ts"],
            "typescript_lint_smoke": ["eslint", "src/contracts/mission_types.ts"],
        },
    )

    assert orchestrator._is_transient_verification_support_file(packet, "import_smoke.ts") is True
    assert orchestrator._is_transient_verification_support_file(packet, "eslint.config.mjs") is True
    assert (
        orchestrator._is_transient_verification_support_file(
            packet, "src/contracts/mission_types.ts"
        )
        is False
    )
