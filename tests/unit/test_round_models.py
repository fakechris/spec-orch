from __future__ import annotations

from spec_orch.domain.models import (
    MissionExecutionResult,
    PlanPatch,
    RoundAction,
    RoundArtifacts,
    RoundDecision,
    RoundStatus,
    RoundSummary,
    SessionOps,
    VisualEvaluationResult,
)


def test_round_decision_roundtrip_with_plan_patch() -> None:
    decision = RoundDecision(
        action=RoundAction.RETRY,
        reason_code="verification_failed",
        summary="Retry the backend worker with a narrowed patch.",
        confidence=0.82,
        affected_workers=["worker-backend"],
        artifacts={"review_memo": "docs/specs/m1/rounds/round-01/supervisor_review.md"},
        session_ops=SessionOps(
            reuse=["worker-backend"],
            spawn=["worker-migrations"],
            cancel=["worker-frontend"],
        ),
        plan_patch=PlanPatch(
            modified_packets={"pkt-2": {"builder_prompt": "Fix migration ordering."}},
            added_packets=[{"packet_id": "pkt-9", "title": "Repair seed data"}],
            removed_packet_ids=["pkt-5"],
            reason="Integration review found schema drift.",
        ),
        blocking_questions=["Should we drop support for the legacy seed path?"],
    )

    restored = RoundDecision.from_dict(decision.to_dict())

    assert restored.action is RoundAction.RETRY
    assert restored.reason_code == "verification_failed"
    assert restored.session_ops.spawn == ["worker-migrations"]
    assert restored.plan_patch is not None
    assert restored.plan_patch.modified_packets["pkt-2"]["builder_prompt"] == (
        "Fix migration ordering."
    )
    assert restored.blocking_questions == ["Should we drop support for the legacy seed path?"]


def test_round_summary_roundtrip_with_decision() -> None:
    summary = RoundSummary(
        round_id=2,
        wave_id=1,
        status=RoundStatus.DECIDED,
        worker_results=[{"packet_id": "pkt-1", "succeeded": True}],
        decision=RoundDecision(
            action=RoundAction.CONTINUE,
            summary="Wave looks good. Move forward.",
            confidence=0.93,
        ),
    )

    restored = RoundSummary.from_dict(summary.to_dict())

    assert restored.round_id == 2
    assert restored.wave_id == 1
    assert restored.status is RoundStatus.DECIDED
    assert restored.worker_results == [{"packet_id": "pkt-1", "succeeded": True}]
    assert restored.decision is not None
    assert restored.decision.action is RoundAction.CONTINUE
    assert restored.decision.summary == "Wave looks good. Move forward."


def test_round_decision_to_dict_omits_plan_patch_when_absent() -> None:
    decision = RoundDecision(
        action=RoundAction.STOP,
        summary="No more useful work remains.",
    )

    payload = decision.to_dict()

    assert payload["action"] == "stop"
    assert "plan_patch" not in payload


def test_visual_evaluation_result_roundtrip() -> None:
    result = VisualEvaluationResult(
        evaluator="stub",
        summary="Landing page hierarchy is clear.",
        confidence=0.84,
        findings=[
            {"severity": "advisory", "message": "CTA could use stronger contrast."},
        ],
        artifacts={
            "homepage": "docs/specs/m1/rounds/round-01/visual/homepage.png",
        },
    )

    restored = VisualEvaluationResult.from_dict(result.to_dict())

    assert restored.evaluator == "stub"
    assert restored.summary == "Landing page hierarchy is clear."
    assert restored.artifacts["homepage"].endswith("homepage.png")


def test_mission_execution_result_preserves_round_summary_and_markdown() -> None:
    result = MissionExecutionResult(
        mission_id="mission-1",
        completed=False,
        paused=True,
        summary_markdown="## Mission Execution\n\nPaused for review.",
        rounds=[
            RoundSummary(
                round_id=2,
                wave_id=1,
                status=RoundStatus.DECIDED,
                decision=RoundDecision(action=RoundAction.ASK_HUMAN, summary="Need approval."),
            )
        ],
        last_round_artifacts=RoundArtifacts(
            round_id=2,
            mission_id="mission-1",
        ),
        blocking_questions=["Approve migration direction?"],
    )

    assert result.mission_id == "mission-1"
    assert result.paused is True
    assert result.completed is False
    assert result.rounds[-1].decision is not None
    assert result.rounds[-1].decision.action is RoundAction.ASK_HUMAN
    assert result.blocking_questions == ["Approve migration direction?"]
