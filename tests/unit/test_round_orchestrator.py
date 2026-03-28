from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

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
    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=StubSupervisor(),
        worker_factory=factory,
        context_assembler=StubAssembler(),
        acceptance_evaluator=StubAcceptanceEvaluator(),
        acceptance_filer=StubAcceptanceFiler(),
    )

    result = orchestrator.run_supervised(mission_id="mission-1", plan=_make_single_wave_plan())

    assert result.completed is True
    review_path = tmp_path / "docs/specs/mission-1/rounds/round-01/acceptance_review.json"
    assert review_path.exists()
    payload = review_path.read_text(encoding="utf-8")
    assert "SON-321" in payload


def test_run_supervised_passes_browser_evidence_to_acceptance_evaluator(
    tmp_path: Path, monkeypatch
) -> None:
    import spec_orch.services.round_orchestrator as round_orchestrator_module
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
        round_orchestrator_module,
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
            "transcript": "/?mission=mission-1&tab=transcript",
            "visual_qa": "/?mission=mission-1&tab=visual",
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

    monkeypatch.setenv("SPEC_ORCH_ACCEPTANCE_MODE", AcceptanceMode.EXPLORATORY.value)
    exploratory = orchestrator._build_acceptance_campaign(
        mission_id="mission-1", artifacts=artifacts
    )
    assert exploratory.min_primary_routes == 1
    assert exploratory.related_route_budget == 5
    assert exploratory.interaction_budget == "wide"
    assert exploratory.required_interactions == [
        "complete the intended operator task",
        "switch into adjacent surfaces when the task suggests it",
    ]
    assert exploratory.interaction_plans["/?mission=mission-1&tab=costs"][0].target == "Transcript"
    assert exploratory.interaction_plans["/?mission=mission-1&tab=costs"][-1].target == "Costs"


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
