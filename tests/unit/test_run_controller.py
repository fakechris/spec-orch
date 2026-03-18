import json
from pathlib import Path

import pytest

from spec_orch.domain.models import (
    BuilderResult,
    Issue,
    IssueContext,
    RunState,
    validate_transition,
)
from spec_orch.services.run_controller import RunController


def test_run_controller_executes_local_fixture_issue(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-1.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-1",
                "title": "Build MVP runner",
                "summary": "Run one local fixture issue through the prototype pipeline.",
            }
        )
    )
    controller = RunController(repo_root=tmp_path)

    result = controller.run_issue("SPC-1")

    assert result.issue.issue_id == "SPC-1"
    assert result.workspace.exists()
    assert result.task_spec.exists()
    assert result.progress.exists()
    assert result.explain.exists()
    assert result.report.exists()
    assert result.gate.mergeable is False
    assert "builder" not in result.gate.failed_conditions
    assert "verification" not in result.gate.failed_conditions
    assert "review" in result.gate.failed_conditions
    assert "human_acceptance" in result.explain.read_text()
    assert '"adapter": "codex_exec"' in result.report.read_text()
    assert '"agent": "codex"' in result.report.read_text()
    telemetry_dir = result.workspace / "telemetry"
    assert telemetry_dir.exists()
    assert (telemetry_dir / "events.jsonl").exists()
    report_data = json.loads(result.report.read_text())
    assert report_data["run_id"]
    assert report_data["builder"]["metadata"]["run_id"] == report_data["run_id"]
    events = _read_events(telemetry_dir / "events.jsonl")
    assert any(event["event_type"] == "verification_started" for event in events)
    assert any(
        event["event_type"] == "verification_step_completed" and event["data"]["step"] == "lint"
        for event in events
    )
    assert any(
        event["event_type"] == "review_initialized" and event["data"]["verdict"] == "pending"
        for event in events
    )
    assert any(
        event["event_type"] == "gate_evaluated"
        and event["data"]["mergeable"] is False
        and "verification" not in event["data"]["failed_conditions"]
        for event in events
    )


def test_run_controller_keeps_builder_failure_when_executable_is_unavailable(
    tmp_path: Path,
) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-21.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-21",
                "title": "Unavailable builder",
                "summary": "Keep the builder failure when the executable is unavailable.",
                "builder_prompt": "Implement without fallback.",
                "verification_commands": {
                    "lint": ["{python}", "-c", "print('lint ok')"],
                    "typecheck": ["{python}", "-c", "print('type ok')"],
                    "test": ["{python}", "-c", "print('test ok')"],
                    "build": ["{python}", "-c", "print('build ok')"],
                },
            }
        )
    )

    controller = RunController(
        repo_root=tmp_path,
        codex_executable=str(tmp_path / "missing-codex"),
    )

    result = controller.run_issue("SPC-21")

    assert result.builder.succeeded is False
    assert result.builder.adapter == "codex_exec"
    assert result.builder.agent == "codex"
    assert result.builder.metadata["turn_contract_compliance"] == {
        "compliant": True,
        "first_action_seen": False,
        "first_action_method": None,
        "first_action_excerpt": None,
        "violations": [],
    }
    telemetry_dir = result.workspace / "telemetry"
    assert telemetry_dir.exists()
    assert (telemetry_dir / "events.jsonl").exists()
    report_data = json.loads(result.report.read_text())
    assert (
        report_data["builder"]["metadata"]["turn_contract_compliance"]
        == result.builder.metadata["turn_contract_compliance"]
    )
    explain_text = result.explain.read_text()
    assert "builder_contract_compliant=yes" in explain_text
    assert "builder_first_action_seen=no" in explain_text
    assert "builder_contract_violations=0" in explain_text
    events = _read_events(telemetry_dir / "events.jsonl")
    assert any(
        event["event_type"] == "builder_completed"
        and event["adapter"] == "codex_exec"
        and event["data"]["succeeded"] is False
        for event in events
    )
    assert any(
        event["event_type"] == "gate_evaluated"
        and event["data"]["mergeable"] is False
        and "builder" in event["data"]["failed_conditions"]
        for event in events
    )


def test_review_and_accept_issue_recompute_gate_and_update_artifacts(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-5.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-5",
                "title": "Acceptance flow",
                "summary": "Turn a passing run into mergeable after acceptance.",
                "verification_commands": {
                    "lint": ["{python}", "-c", "print('lint ok')"],
                    "typecheck": ["{python}", "-c", "print('type ok')"],
                    "test": ["{python}", "-c", "print('test ok')"],
                    "build": ["{python}", "-c", "print('build ok')"],
                },
            }
        )
    )
    controller = RunController(repo_root=tmp_path)

    initial = controller.run_issue("SPC-5")
    reviewed = controller.review_issue(
        "SPC-5",
        verdict="pass",
        reviewed_by="claude",
    )
    accepted = controller.accept_issue("SPC-5", accepted_by="chris")

    assert initial.gate.mergeable is False
    assert reviewed.gate.mergeable is False
    assert reviewed.gate.failed_conditions == ["human_acceptance"]
    assert (reviewed.workspace / "review_report.json").exists()
    review_report = json.loads((reviewed.workspace / "review_report.json").read_text())
    assert (
        review_report["builder_turn_contract_compliance"]
        == initial.builder.metadata["turn_contract_compliance"]
    )
    assert '"reviewed_by": "claude"' in (reviewed.workspace / "report.json").read_text()
    assert "| review | pass |" in reviewed.explain.read_text()
    assert accepted.gate.mergeable is True
    assert accepted.gate.failed_conditions == []
    assert (accepted.workspace / "acceptance.json").exists()
    assert '"accepted_by": "chris"' in (accepted.workspace / "report.json").read_text()
    assert "| human_acceptance | accepted |" in accepted.explain.read_text()
    telemetry_dir = accepted.workspace / "telemetry"
    assert telemetry_dir.exists()
    events = _read_events(telemetry_dir / "events.jsonl")
    assert any(event["event_type"] == "review_completed" for event in events)
    assert any(event["event_type"] == "acceptance_recorded" for event in events)
    assert any(
        event["event_type"] == "gate_evaluated"
        and event["data"]["mergeable"] is True
        and event["data"]["failed_conditions"] == []
        for event in events
    )


def test_run_issue_closes_activity_logger_on_exception(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-ERR.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-ERR",
                "title": "Run logger cleanup",
                "summary": "Close the logger when verification fails.",
            }
        )
    )
    controller = RunController(repo_root=tmp_path)
    logger = _TrackingActivityLogger()

    controller._open_activity_logger = lambda _workspace: logger
    controller.verification_service.run = _raise_runtime_error

    with pytest.raises(RuntimeError, match="boom"):
        controller.run_issue("SPC-ERR")

    assert logger.entered is True
    assert logger.exited is True
    assert logger.closed is True


def test_rerun_issue_closes_activity_logger_on_exception(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-RERR.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-RERR",
                "title": "Rerun logger cleanup",
                "summary": "Close the logger when rerun verification fails.",
                "verification_commands": {
                    "lint": ["{python}", "-c", "print('lint ok')"],
                    "typecheck": ["{python}", "-c", "print('type ok')"],
                    "test": ["{python}", "-c", "print('test ok')"],
                    "build": ["{python}", "-c", "print('build ok')"],
                },
            }
        )
    )
    controller = RunController(repo_root=tmp_path)
    controller.builder_adapter = _PassingBuilderAdapter()
    controller.run_issue("SPC-RERR")
    logger = _TrackingActivityLogger()

    controller._open_activity_logger = lambda _workspace: logger
    controller.verification_service.run = _raise_runtime_error

    with pytest.raises(RuntimeError, match="boom"):
        controller.rerun_issue("SPC-RERR")

    assert logger.entered is True
    assert logger.exited is True
    assert logger.closed is True


def test_run_issue_persists_state_in_report(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-S1.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-S1",
                "title": "State tracking",
                "summary": "Verify state is persisted.",
            }
        )
    )
    controller = RunController(repo_root=tmp_path)
    result = controller.run_issue("SPC-S1")

    report_data = json.loads(result.report.read_text())
    assert report_data["state"] == "gate_evaluated"
    assert result.state == RunState.GATE_EVALUATED


def test_accept_issue_sets_accepted_state(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-S2.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-S2",
                "title": "Acceptance state",
                "summary": "Verify accept sets ACCEPTED state.",
                "verification_commands": {
                    "lint": ["{python}", "-c", "print('ok')"],
                    "typecheck": ["{python}", "-c", "print('ok')"],
                    "test": ["{python}", "-c", "print('ok')"],
                    "build": ["{python}", "-c", "print('ok')"],
                },
            }
        )
    )
    controller = RunController(repo_root=tmp_path)
    controller.run_issue("SPC-S2")
    controller.review_issue("SPC-S2", verdict="pass", reviewed_by="bot")
    accepted = controller.accept_issue("SPC-S2", accepted_by="chris")

    report_data = json.loads(accepted.report.read_text())
    assert report_data["state"] == "accepted"
    assert accepted.state == RunState.ACCEPTED


def test_get_state_returns_draft_for_unknown_issue(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-GHOST.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-GHOST",
                "title": "Ghost",
                "summary": "No run yet.",
            }
        )
    )
    controller = RunController(repo_root=tmp_path)
    assert controller.get_state("SPC-GHOST") == RunState.DRAFT


def test_get_state_returns_persisted_state(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-GS.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-GS",
                "title": "State read",
                "summary": "Check get_state after run.",
            }
        )
    )
    controller = RunController(repo_root=tmp_path)
    controller.run_issue("SPC-GS")
    assert controller.get_state("SPC-GS") == RunState.GATE_EVALUATED


def test_validate_transition_rejects_illegal_move() -> None:
    with pytest.raises(ValueError, match="Invalid state transition"):
        validate_transition(RunState.DRAFT, RunState.ACCEPTED)


def test_validate_transition_accepts_legal_move() -> None:
    validate_transition(RunState.DRAFT, RunState.BUILDING)
    validate_transition(RunState.GATE_EVALUATED, RunState.ACCEPTED)
    validate_transition(RunState.BUILDING, RunState.VERIFYING)


def _read_events(events_path: Path) -> list[dict]:
    return [json.loads(line) for line in events_path.read_text().splitlines()]


class _TrackingActivityLogger:
    def __init__(self) -> None:
        self.entered = False
        self.exited = False
        self.closed = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *exc: object) -> None:
        self.exited = True
        self.close()

    def log(self, _event: dict) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class _PassingBuilderAdapter:
    ADAPTER_NAME = "passing_builder"
    AGENT_NAME = "codex"

    def run(self, **_kwargs) -> BuilderResult:
        workspace = _kwargs.get("workspace", Path("."))
        return BuilderResult(
            succeeded=True,
            command=[],
            stdout="",
            stderr="",
            report_path=workspace / "builder_report.json",
            adapter=self.ADAPTER_NAME,
            agent=self.AGENT_NAME,
            metadata={},
        )


def _raise_runtime_error(**_kwargs):
    raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# Phase 0: SON-125 / SON-126 / SON-127 tests
# ---------------------------------------------------------------------------


def test_artifact_manifest_written_after_run(tmp_path: Path) -> None:
    """SON-127: artifact_manifest.json is written at end of each run."""
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-AM.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-AM",
                "title": "Test artifact manifest",
                "summary": "Verify manifest is written.",
            }
        )
    )
    controller = RunController(repo_root=tmp_path)
    result = controller.run_issue("SPC-AM")

    manifest_path = result.workspace / "artifact_manifest.json"
    assert manifest_path.exists(), "artifact_manifest.json should be written"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["issue_id"] == "SPC-AM"
    assert manifest["run_id"]
    assert "report" in manifest["artifacts"]
    assert "explain" in manifest["artifacts"]


def test_flow_transition_writes_to_memory(tmp_path: Path) -> None:
    """SON-126: record_flow_transition stores event in MemoryService."""
    from spec_orch.domain.models import FlowTransitionEvent
    from spec_orch.services.memory.service import MemoryService, reset_memory_service
    from spec_orch.services.memory.types import MemoryLayer, MemoryQuery

    reset_memory_service()
    svc = MemoryService(repo_root=tmp_path)

    import spec_orch.services.memory.service as mem_mod

    mem_mod._instance = svc

    try:
        from spec_orch.services.run_controller import record_flow_transition

        event = FlowTransitionEvent(
            from_flow="standard",
            to_flow="full",
            trigger="promotion_required",
            timestamp="2026-03-17T00:00:00Z",
            issue_id="TEST-1",
            run_id="run-abc",
        )
        record_flow_transition(event)

        results = svc.recall(MemoryQuery(layer=MemoryLayer.EPISODIC, tags=["flow-promotion"]))
        assert len(results) >= 1
        entry = results[0]
        assert entry.metadata["from_flow"] == "standard"
        assert entry.metadata["to_flow"] == "full"
        assert entry.metadata["issue_id"] == "TEST-1"
    finally:
        reset_memory_service()


def test_chat_completion_method_exists_on_planner() -> None:
    """SON-125: LiteLLMPlannerAdapter exposes chat_completion method."""
    from spec_orch.services.litellm_planner_adapter import LiteLLMPlannerAdapter

    adapter = LiteLLMPlannerAdapter(api_key="fake-key")
    assert hasattr(adapter, "chat_completion")
    assert callable(adapter.chat_completion)


def test_intent_evolver_uses_chat_completion(tmp_path: Path) -> None:
    """SON-125: IntentEvolver calls chat_completion, not invoke."""
    from spec_orch.services.intent_evolver import IntentEvolver

    class FakePlanner:
        called_method: str = ""

        def chat_completion(self, *, system_prompt: str, user_prompt: str) -> str:
            self.called_method = "chat_completion"
            return json.dumps(
                {
                    "variant_id": "v1",
                    "prompt_text": "improved prompt",
                    "rationale": "test",
                    "target_improvements": [],
                }
            )

    planner = FakePlanner()
    evolver = IntentEvolver(repo_root=tmp_path, planner=planner)
    evolver.MIN_ENTRIES_FOR_EVOLVE = 0

    evo_dir = tmp_path / ".spec_orch_evolution"
    evo_dir.mkdir(parents=True, exist_ok=True)
    history_path = evo_dir / "classifier_prompt_history.json"
    history_path.write_text(
        json.dumps(
            [
                {
                    "variant_id": "v0",
                    "prompt_text": "classify intent",
                    "is_active": True,
                    "total_runs": 20,
                    "successful_runs": 15,
                }
            ]
        )
    )

    class FakeMemory:
        def recall(self, query):
            from spec_orch.services.memory.types import MemoryEntry, MemoryLayer

            return [
                MemoryEntry(
                    key="test",
                    content="test",
                    layer=MemoryLayer.EPISODIC,
                    metadata={"intent_category": "feature"},
                )
                for _ in range(15)
            ]

    import spec_orch.services.intent_evolver as ie_mod

    orig_recall = ie_mod.IntentEvolver.recall_intent_logs

    def patched_recall(self):
        return [{"intent_category": "feature"} for _ in range(15)]

    ie_mod.IntentEvolver.recall_intent_logs = patched_recall

    try:
        result = evolver.evolve()
        assert planner.called_method == "chat_completion"
        assert result is not None
        assert result.variant_id == "v1"
    finally:
        ie_mod.IntentEvolver.recall_intent_logs = orig_recall


# ─── Phase 1: Context Contract tests ─────────────────────────────────────────


def test_context_bundle_dataclass_fields() -> None:
    """SON-128: ContextBundle exposes task/execution/learning."""
    from spec_orch.domain.context import (
        ContextBundle,
        ExecutionContext,
        LearningContext,
        TaskContext,
    )

    issue = Issue(issue_id="CTX-1", title="t", summary="s", context=IssueContext())
    bundle = ContextBundle(
        task=TaskContext(issue=issue),
        execution=ExecutionContext(),
        learning=LearningContext(),
    )
    assert bundle.task.issue.issue_id == "CTX-1"
    assert bundle.execution.git_diff == ""
    assert bundle.learning.similar_failure_samples == []


def test_node_context_spec_defaults() -> None:
    """SON-128: NodeContextSpec carries node-level budget & field lists."""
    from spec_orch.domain.context import NodeContextSpec

    spec = NodeContextSpec(
        node_name="builder",
        required_task_fields=["issue", "spec_snapshot_text"],
        required_execution_fields=["file_tree"],
        max_tokens_budget=4000,
    )
    assert spec.node_name == "builder"
    assert spec.max_tokens_budget == 4000
    assert "issue" in spec.required_task_fields


def test_context_assembler_builds_bundle(tmp_path: Path) -> None:
    """SON-129: ContextAssembler returns a valid ContextBundle."""
    from spec_orch.domain.context import NodeContextSpec
    from spec_orch.services.context_assembler import ContextAssembler

    issue = Issue(
        issue_id="CTX-2",
        title="Assembler test",
        summary="Test assembler builds bundle.",
        context=IssueContext(
            constraints=["no-sudo"],
            files_to_read=["src/main.py"],
        ),
        acceptance_criteria=["Passes lint"],
    )
    spec = NodeContextSpec(
        node_name="builder",
        required_task_fields=["issue", "spec_snapshot_text", "constraints", "acceptance_criteria"],
        required_execution_fields=["file_tree"],
        max_tokens_budget=6000,
    )
    assembler = ContextAssembler()
    bundle = assembler.assemble(spec=spec, issue=issue, workspace=tmp_path)

    assert bundle.task.issue.issue_id == "CTX-2"
    assert "no-sudo" in bundle.task.constraints
    assert "Passes lint" in bundle.task.acceptance_criteria


def test_render_builder_envelope_includes_acceptance_criteria(tmp_path: Path) -> None:
    """SON-130: Builder envelope contains structured acceptance criteria."""
    from spec_orch.services.run_controller import RunController

    issue = Issue(
        issue_id="ENV-1",
        title="Envelope test",
        summary="Check envelope rendering.",
        context=IssueContext(constraints=["no-secrets"]),
        acceptance_criteria=["All tests pass", "No regressions"],
        verification_commands={"lint": ["ruff", "check", "."]},
    )
    rendered = RunController._render_builder_envelope(issue, tmp_path)
    assert "## Acceptance Criteria" in rendered
    assert "All tests pass" in rendered
    assert "## Constraints" in rendered
    assert "no-secrets" in rendered
    assert "## Verification Commands" in rendered
    assert "ruff" in rendered


def test_render_builder_envelope_includes_spec(tmp_path: Path) -> None:
    """SON-130: Builder envelope includes task.spec.md when present."""
    from spec_orch.services.run_controller import RunController

    spec_path = tmp_path / "task.spec.md"
    spec_path.write_text("# My Spec\nDo the thing.\n")

    issue = Issue(issue_id="ENV-2", title="t", summary="s", context=IssueContext())
    rendered = RunController._render_builder_envelope(issue, tmp_path)
    assert "## Spec" in rendered
    assert "Do the thing." in rendered


def test_llm_review_adapter_collect_extra_context(tmp_path: Path) -> None:
    """SON-131: LLMReviewAdapter collects verification+gate+criteria context."""
    from spec_orch.services.llm_review_adapter import LLMReviewAdapter

    report = {
        "verification": {
            "lint": {"command": ["ruff", "check"], "exit_code": 0},
            "test": {"command": ["pytest"], "exit_code": 1},
        },
        "mergeable": False,
        "failed_conditions": ["test_failure"],
    }
    (tmp_path / "report.json").write_text(json.dumps(report))

    snap = {"issue": {"acceptance_criteria": ["All tests pass"]}}
    (tmp_path / "spec_snapshot.json").write_text(json.dumps(snap))

    extra = LLMReviewAdapter._collect_extra_context(tmp_path)
    assert "Verification Results (previous run)" in extra
    assert "lint: pass" in extra
    assert "test: FAIL" in extra
    assert "Gate Status (previous run)" in extra
    assert "Acceptance Criteria" in extra
    assert "All tests pass" in extra


def test_prompt_evolver_collects_failure_samples(tmp_path: Path) -> None:
    """SON-133: PromptEvolver collects failure samples bucketed by task type."""
    from spec_orch.services.prompt_evolver import PromptEvolver

    runs_dir = tmp_path / ".spec_orch_runs"
    run_dir = runs_dir / "run-fail-01"
    run_dir.mkdir(parents=True)
    (run_dir / "report.json").write_text(
        json.dumps(
            {
                "mergeable": False,
                "failed_conditions": ["test_failure"],
                "metadata": {"run_class": "feature", "builder_adapter": "opencode"},
                "verification": {
                    "lint": {"exit_code": 0},
                    "test": {"exit_code": 1},
                },
            }
        )
    )
    telem_dir = run_dir / "telemetry"
    telem_dir.mkdir()
    (telem_dir / "incoming_events.jsonl").write_text(
        json.dumps({"text": "Error: test_auth failed"}) + "\n"
    )

    evolver = PromptEvolver(repo_root=tmp_path)
    samples = evolver._collect_failure_samples()
    assert len(samples) == 1
    assert samples[0]["task_type"] == "feature"
    assert samples[0]["adapter"] == "opencode"
    assert "test" in samples[0]["failed_checks"]
    assert len(samples[0]["builder_tail"]) >= 1


def test_plan_strategy_evolver_collects_failure_details(tmp_path: Path) -> None:
    """SON-134: PlanStrategyEvolver collects detailed failure samples."""
    from spec_orch.services.plan_strategy_evolver import PlanStrategyEvolver

    runs_dir = tmp_path / ".spec_orch_runs"
    run_dir = runs_dir / "run-plan-fail"
    run_dir.mkdir(parents=True)
    (run_dir / "report.json").write_text(
        json.dumps(
            {
                "mergeable": False,
                "failed_conditions": ["lint"],
                "metadata": {"plan": [{"wave": 0, "packets": ["setup"]}]},
                "verification": {"lint": {"exit_code": 1}},
            }
        )
    )
    devs = [json.dumps({"file_path": "src/bad.py", "deviation_type": "out_of_scope"})]
    (run_dir / "deviations.jsonl").write_text("\n".join(devs))

    evolver = PlanStrategyEvolver(repo_root=tmp_path)
    details = evolver._collect_failure_details()
    assert len(details) == 1
    assert "src/bad.py" in details[0]["deviating_files"]
    assert "out_of_scope" in details[0]["deviation_types"]
    assert details[0]["plan_structure"] == [{"wave": 0, "packets": ["setup"]}]


def test_evolution_config_from_toml() -> None:
    """SON-135: EvolutionConfig parses [evolution] section from TOML data."""
    from spec_orch.services.evolution_trigger import EvolutionConfig

    toml_data = {
        "evolution": {
            "enabled": True,
            "trigger_after_n_runs": 10,
            "auto_promote": True,
            "prompt_evolver": {"enabled": False},
            "harness_synthesizer": {"enabled": True, "dry_run": False},
        }
    }
    cfg = EvolutionConfig.from_toml(toml_data)
    assert cfg.enabled is True
    assert cfg.trigger_after_n_runs == 10
    assert cfg.auto_promote is True
    assert cfg.prompt_evolver_enabled is False
    assert cfg.harness_dry_run is False


def test_evolution_trigger_counter(tmp_path: Path) -> None:
    """SON-135: EvolutionTrigger increments counter and triggers at threshold."""
    from spec_orch.services.evolution_trigger import EvolutionConfig, EvolutionTrigger

    cfg = EvolutionConfig(enabled=True, trigger_after_n_runs=3)
    trigger = EvolutionTrigger(repo_root=tmp_path, config=cfg)

    assert trigger.increment_and_check() is False  # count=1
    assert trigger.increment_and_check() is False  # count=2
    assert trigger.increment_and_check() is True  # count=3, threshold met

    trigger.reset_counter()
    assert trigger._read_counter() == 0


def test_evolution_trigger_disabled(tmp_path: Path) -> None:
    """SON-135: Disabled evolution never triggers."""
    from spec_orch.services.evolution_trigger import EvolutionConfig, EvolutionTrigger

    cfg = EvolutionConfig(enabled=False)
    trigger = EvolutionTrigger(repo_root=tmp_path, config=cfg)
    result = trigger.run_evolution_cycle()
    assert result.triggered is False


def test_harness_synthesizer_collect_failure_samples(tmp_path: Path) -> None:
    """SON-132: HarnessSynthesizer collects raw builder event samples."""
    from spec_orch.services.harness_synthesizer import HarnessSynthesizer

    runs_dir = tmp_path / ".spec_orch_runs"
    run_dir = runs_dir / "run-001"
    run_dir.mkdir(parents=True)
    (run_dir / "report.json").write_text(
        json.dumps({"mergeable": False, "failed_conditions": ["bad"]})
    )
    telem_dir = run_dir / "telemetry"
    telem_dir.mkdir()
    events = [
        json.dumps({"text": "sudo rm -rf / executed"}),
        json.dumps({"text": "normal operation"}),
    ]
    (telem_dir / "incoming_events.jsonl").write_text("\n".join(events))

    synth = HarnessSynthesizer(repo_root=tmp_path)
    samples = synth._collect_failure_samples(["run-001"])
    assert "sudo" in samples
    assert "run-001" in samples


# ── Phase 13 tests: Full context integration ──────────────────────────


def test_readiness_checker_accepts_context_bundle() -> None:
    """SON-137: ReadinessChecker.check() accepts an optional ContextBundle."""
    from spec_orch.services.readiness_checker import ReadinessChecker

    checker = ReadinessChecker()
    result = checker.check(
        "## Goal\nDo stuff\n## Acceptance Criteria\n- [ ] done\n## Files\n- `src/a.py`",
        context=None,
    )
    assert result.ready is True


def test_readiness_checker_uses_context_in_prompt() -> None:
    """SON-137: When ContextBundle is provided, LLM prompt includes its data."""
    from unittest.mock import MagicMock

    from spec_orch.domain.context import (
        ContextBundle,
        ExecutionContext,
        LearningContext,
        TaskContext,
    )
    from spec_orch.services.readiness_checker import ReadinessChecker

    mock_planner = MagicMock()
    mock_planner.brainstorm.return_value = "READY"

    issue = Issue(issue_id="RC-1", title="t", summary="s", context=IssueContext())
    bundle = ContextBundle(
        task=TaskContext(
            issue=issue,
            constraints=["no-sudo"],
            acceptance_criteria=["All tests pass"],
        ),
        execution=ExecutionContext(file_tree="src/main.py\nsrc/utils.py"),
        learning=LearningContext(
            similar_failure_samples=[{"key": "run-fail-1", "content": "import error"}]
        ),
    )

    checker = ReadinessChecker(planner=mock_planner)
    result = checker.check(
        "## Goal\nDo stuff\n## Acceptance Criteria\n- [ ] done\n## Files\n- `src/a.py`",
        context=bundle,
    )
    assert result.ready is True
    call_args = mock_planner.brainstorm.call_args
    prompt = call_args.kwargs["conversation_history"][0]["content"]
    assert "no-sudo" in prompt
    assert "All tests pass" in prompt
    assert "src/main.py" in prompt
    assert "run-fail-1" in prompt


def test_planner_plan_accepts_context() -> None:
    """SON-138: LiteLLMPlannerAdapter.plan() accepts optional context parameter."""
    from spec_orch.services.litellm_planner_adapter import LiteLLMPlannerAdapter

    adapter = LiteLLMPlannerAdapter()
    msg = adapter._build_user_message(
        Issue(issue_id="P-1", title="t", summary="s", context=IssueContext()),
        None,
        context=None,
    )
    assert "Untrusted Issue Payload" in msg


def test_planner_renders_context_block() -> None:
    """SON-138: _render_context_block produces readable sections from ContextBundle."""
    from spec_orch.domain.context import ContextBundle, ExecutionContext, TaskContext
    from spec_orch.services.litellm_planner_adapter import LiteLLMPlannerAdapter

    issue = Issue(issue_id="P-2", title="t", summary="s", context=IssueContext())
    bundle = ContextBundle(
        task=TaskContext(
            issue=issue,
            spec_snapshot_text="Build a widget",
            constraints=["no-external-deps"],
        ),
        execution=ExecutionContext(file_tree="src/widget.py"),
    )
    parts = LiteLLMPlannerAdapter._render_context_block(bundle)
    combined = "\n".join(parts)
    assert "Build a widget" in combined
    assert "no-external-deps" in combined
    assert "src/widget.py" in combined


def test_scoper_accepts_context_parameter() -> None:
    """SON-139: LiteLLMScoperAdapter.scope() accepts optional context parameter."""
    import inspect

    from spec_orch.services.scoper_adapter import LiteLLMScoperAdapter

    sig = inspect.signature(LiteLLMScoperAdapter.scope)
    assert "context" in sig.parameters


def test_intent_classifier_accepts_context() -> None:
    """SON-140: classify_intent accepts optional context parameter."""
    from spec_orch.services.conductor.intent_classifier import classify_intent

    result = classify_intent("fix the bug", context=None)
    assert result.category is not None


def test_evolution_trigger_loads_manifest(tmp_path: Path) -> None:
    """SON-141: EvolutionTrigger._load_latest_manifest reads artifact manifest."""
    from spec_orch.services.evolution_trigger import EvolutionConfig, EvolutionTrigger

    ws = tmp_path / "workspace"
    ws.mkdir()
    manifest = {
        "run_id": "run-1",
        "issue_id": "I-1",
        "artifacts": {"report": "/tmp/r.json", "builder_events": "/tmp/e.jsonl"},
    }
    (ws / "artifact_manifest.json").write_text(json.dumps(manifest))

    cfg = EvolutionConfig(enabled=True)
    trigger = EvolutionTrigger(repo_root=tmp_path, config=cfg, latest_workspace=ws)
    loaded = trigger._load_latest_manifest()
    assert loaded["report"] == "/tmp/r.json"
    assert loaded["builder_events"] == "/tmp/e.jsonl"


def test_evolution_trigger_without_manifest(tmp_path: Path) -> None:
    """SON-141: Missing manifest returns empty dict."""
    from spec_orch.services.evolution_trigger import EvolutionConfig, EvolutionTrigger

    cfg = EvolutionConfig(enabled=True)
    trigger = EvolutionTrigger(repo_root=tmp_path, config=cfg, latest_workspace=tmp_path)
    assert trigger._load_latest_manifest() == {}


def test_finalize_run_triggers_evolution(tmp_path: Path) -> None:
    """SON-142: _finalize_run calls _maybe_trigger_evolution."""
    from unittest.mock import patch

    controller = RunController(repo_root=tmp_path)
    with patch.object(controller, "_maybe_trigger_evolution") as mock_evo:
        fixtures_dir = tmp_path / "fixtures" / "issues"
        fixtures_dir.mkdir(parents=True)
        (fixtures_dir / "EVO-1.json").write_text(
            json.dumps(
                {
                    "issue_id": "EVO-1",
                    "title": "Test evolution trigger",
                    "summary": "Test that evolution is called after finalize.",
                }
            )
        )
        controller.run_issue("EVO-1")
        mock_evo.assert_called_once()
