from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from spec_orch.services.memory.service import MemoryService, reset_memory_service


def test_gather_latest_approval_request_prefers_decision_core_intervention_queue(
    tmp_path: Path,
) -> None:
    from spec_orch.dashboard.approvals import _gather_latest_approval_request

    mission_id = "mission-approval"
    operator_dir = tmp_path / "docs" / "specs" / mission_id / "operator"
    operator_dir.mkdir(parents=True)
    (operator_dir / "interventions.jsonl").write_text(
        json.dumps(
            {
                "intervention_id": "int-1",
                "decision_record_id": "mission-approval-round-3-review",
                "point_key": "mission.round.review",
                "mission_id": mission_id,
                "round_id": 3,
                "summary": "Need operator approval before rollout.",
                "questions": ["Approve the rollout after visual QA review?"],
                "status": "open",
                "created_at": "2026-03-30T00:00:00+00:00",
                "review_route": f"/?mission={mission_id}&mode=missions&tab=approvals&round=3",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = _gather_latest_approval_request(tmp_path, mission_id)

    assert payload == {
        "round_id": 3,
        "timestamp": "2026-03-30T00:00:00+00:00",
        "summary": "Need operator approval before rollout.",
        "blocking_question": "Approve the rollout after visual QA review?",
        "decision_action": "ask_human",
        "review_route": f"/?mission={mission_id}&mode=missions&tab=approvals&round=3",
        "actions": [
            {
                "key": "approve",
                "label": "Approve",
                "message": "@approve Approve the rollout after visual QA review?",
            },
            {
                "key": "request_revision",
                "label": "Request revision",
                "message": "@request-revision Please revise this round before rollout.",
            },
            {
                "key": "ask_followup",
                "label": "Ask follow-up",
                "message": "@follow-up I need more detail before approving this round.",
            },
        ],
    }


def test_gather_latest_approval_request_ignores_responded_intervention(tmp_path: Path) -> None:
    from spec_orch.dashboard.approvals import _gather_latest_approval_request

    mission_id = "mission-approval-responded"
    operator_dir = tmp_path / "docs" / "specs" / mission_id / "operator"
    operator_dir.mkdir(parents=True)
    (operator_dir / "interventions.jsonl").write_text(
        json.dumps(
            {
                "intervention_id": "int-responded",
                "decision_record_id": "mission-approval-responded-round-3-review",
                "point_key": "mission.round.review",
                "mission_id": mission_id,
                "round_id": 3,
                "summary": "Need operator approval before rollout.",
                "questions": ["Approve this round?"],
                "status": "open",
                "created_at": "2026-03-30T00:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (operator_dir / "intervention_responses.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-03-30T00:05:00+00:00",
                "intervention_id": "int-responded",
                "decision_record_id": "mission-approval-responded-round-3-review",
                "action_key": "approve",
                "label": "Approve",
                "message": "@approve Approve this round.",
                "channel": "web-dashboard",
                "status": "applied",
                "effect": "approval_granted",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = _gather_latest_approval_request(tmp_path, mission_id)

    assert payload is None


def test_gather_latest_approval_request_ignores_stale_intervention_when_newer_round_exists(
    tmp_path: Path,
) -> None:
    from spec_orch.dashboard.approvals import _gather_latest_approval_request

    mission_id = "mission-approval-stale"
    specs_dir = tmp_path / "docs" / "specs" / mission_id
    operator_dir = specs_dir / "operator"
    rounds_dir = specs_dir / "rounds"
    operator_dir.mkdir(parents=True)
    (rounds_dir / "round-04").mkdir(parents=True)
    (rounds_dir / "round-05").mkdir(parents=True)

    (operator_dir / "interventions.jsonl").write_text(
        json.dumps(
            {
                "intervention_id": "int-stale",
                "decision_record_id": "mission-approval-stale-round-4-review",
                "point_key": "mission.round.review",
                "mission_id": mission_id,
                "round_id": 4,
                "summary": "Need operator approval before rollout.",
                "questions": ["Approve this round?"],
                "status": "open",
                "created_at": "2026-03-30T00:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (rounds_dir / "round-04" / "round_summary.json").write_text(
        json.dumps({"round_id": 4}),
        encoding="utf-8",
    )
    (rounds_dir / "round-05" / "round_summary.json").write_text(
        json.dumps({"round_id": 5}),
        encoding="utf-8",
    )

    payload = _gather_latest_approval_request(tmp_path, mission_id)

    assert payload is None


def test_record_approval_action_appends_decision_core_response_metadata(tmp_path: Path) -> None:
    import spec_orch.services.memory.service as mem_mod
    from spec_orch.dashboard.approvals import _record_approval_action
    from spec_orch.decision_core.review_queue import load_decision_reviews

    mission_id = "mission-approval"
    operator_dir = tmp_path / "docs" / "specs" / mission_id / "operator"
    operator_dir.mkdir(parents=True)
    (operator_dir / "interventions.jsonl").write_text(
        json.dumps(
            {
                "intervention_id": "int-1",
                "decision_record_id": "mission-approval-round-4-review",
                "point_key": "mission.round.review",
                "mission_id": mission_id,
                "round_id": 4,
                "summary": "Need operator approval before rollout.",
                "questions": ["Approve rollout after transcript review?"],
                "status": "open",
                "created_at": "2026-03-30T00:00:00+00:00",
                "review_route": f"/?mission={mission_id}&mode=missions&tab=approvals&round=4",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    reset_memory_service()
    svc = MemoryService(repo_root=tmp_path)
    mem_mod._instance = svc
    try:
        payload = _record_approval_action(
            tmp_path,
            mission_id,
            action_key="approve",
            label="Approve",
            message="@approve Approve rollout after transcript review?",
            channel="web-dashboard",
            status="applied",
        )
    finally:
        reset_memory_service()

    assert payload["effect"] == "approval_granted"
    history = [
        json.loads(line)
        for line in (operator_dir / "intervention_responses.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert history == [
        {
            "timestamp": payload["timestamp"],
            "intervention_id": "int-1",
            "decision_record_id": "mission-approval-round-4-review",
            "action_key": "approve",
            "label": "Approve",
            "message": "@approve Approve rollout after transcript review?",
            "channel": "web-dashboard",
            "status": "applied",
            "effect": "approval_granted",
        }
    ]
    reviews = load_decision_reviews(
        tmp_path, mission_id, record_id="mission-approval-round-4-review"
    )
    assert reviews == [
        {
            "review_id": f"mission-approval-round-4-review:approve:{payload['timestamp']}",
            "record_id": "mission-approval-round-4-review",
            "reviewer_kind": "human",
            "verdict": "approval_granted",
            "summary": "@approve Approve rollout after transcript review?",
            "recommended_authority": "human_required",
            "escalate_to_human": False,
            "reflection": "",
            "created_at": payload["timestamp"],
        }
    ]
    memory_keys = svc.list_keys(layer="episodic", tags=["decision-review"])
    assert memory_keys
    memory_entry = svc.get(memory_keys[0])
    assert memory_entry is not None
    assert memory_entry.metadata["mission_id"] == mission_id
    assert memory_entry.metadata["provenance"] == "reviewed"


def test_record_approval_action_normalizes_blank_decision_record_id(tmp_path: Path) -> None:
    from spec_orch.dashboard.approvals import _record_approval_action

    mission_id = "mission-approval-blank-record-id"
    operator_dir = tmp_path / "docs" / "specs" / mission_id / "operator"
    operator_dir.mkdir(parents=True)
    (operator_dir / "interventions.jsonl").write_text(
        json.dumps(
            {
                "intervention_id": "int-blank",
                "decision_record_id": "   ",
                "point_key": "mission.round.review",
                "mission_id": mission_id,
                "round_id": 4,
                "summary": "Need operator approval before rollout.",
                "questions": ["Approve rollout after transcript review?"],
                "status": "open",
                "created_at": "2026-03-30T00:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _record_approval_action(
        tmp_path,
        mission_id,
        action_key="approve",
        label="Approve",
        message="@approve Approve rollout after transcript review?",
        channel="web-dashboard",
        status="applied",
    )

    history = [
        json.loads(line)
        for line in (operator_dir / "intervention_responses.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert history[0]["decision_record_id"] is None
    assert not (operator_dir / "decision_reviews.jsonl").exists()


def test_record_approval_action_tolerates_decision_review_append_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import spec_orch.services.memory.service as mem_mod
    from spec_orch.dashboard import approvals as approvals_module

    mission_id = "mission-approval-review-failure"
    operator_dir = tmp_path / "docs" / "specs" / mission_id / "operator"
    operator_dir.mkdir(parents=True)
    (operator_dir / "interventions.jsonl").write_text(
        json.dumps(
            {
                "intervention_id": "int-failure",
                "decision_record_id": "mission-approval-review-failure-round-4-review",
                "point_key": "mission.round.review",
                "mission_id": mission_id,
                "round_id": 4,
                "summary": "Need operator approval before rollout.",
                "questions": ["Approve rollout after transcript review?"],
                "status": "open",
                "created_at": "2026-03-30T00:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def _raise_review_append(*args: object, **kwargs: object) -> dict[str, object]:
        raise OSError("disk full")

    monkeypatch.setattr(approvals_module, "append_decision_review", _raise_review_append)
    reset_memory_service()
    svc = MemoryService(repo_root=tmp_path)
    mem_mod._instance = svc

    try:
        with caplog.at_level(logging.WARNING):
            payload = approvals_module._record_approval_action(
                tmp_path,
                mission_id,
                action_key="approve",
                label="Approve",
                message="@approve Approve rollout after transcript review?",
                channel="web-dashboard",
                status="applied",
            )
    finally:
        reset_memory_service()

    assert payload["effect"] == "approval_granted"
    history = [
        json.loads(line)
        for line in (operator_dir / "intervention_responses.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert history == [
        {
            "timestamp": payload["timestamp"],
            "intervention_id": "int-failure",
            "decision_record_id": "mission-approval-review-failure-round-4-review",
            "action_key": "approve",
            "label": "Approve",
            "message": "@approve Approve rollout after transcript review?",
            "channel": "web-dashboard",
            "status": "applied",
            "effect": "approval_granted",
        }
    ]
    assert "decision review append failed" in caplog.text
    assert not (operator_dir / "decision_reviews.jsonl").exists()
    assert svc.list_keys(layer="episodic", tags=["decision-review"]) == []


def test_load_approval_history_prefers_decision_core_response_history(tmp_path: Path) -> None:
    from spec_orch.dashboard.approvals import _load_approval_history

    mission_id = "mission-approval-history"
    operator_dir = tmp_path / "docs" / "specs" / mission_id / "operator"
    operator_dir.mkdir(parents=True)
    (operator_dir / "intervention_responses.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-03-30T01:00:00+00:00",
                        "intervention_id": "int-2",
                        "decision_record_id": "mission-approval-history-round-2-review",
                        "action_key": "request_revision",
                        "label": "Request revision",
                        "message": "@request-revision Please revise this round before rollout.",
                        "channel": "web-dashboard",
                        "status": "applied",
                        "effect": "revision_requested",
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-30T02:00:00+00:00",
                        "intervention_id": "int-3",
                        "decision_record_id": "mission-approval-history-round-3-review",
                        "action_key": "approve",
                        "label": "Approve",
                        "message": "@approve Approve rollout after transcript review?",
                        "channel": "web-dashboard",
                        "status": "applied",
                        "effect": "approval_granted",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (operator_dir / "approval_actions.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-03-29T23:00:00+00:00",
                "action_key": "ask_followup",
                "label": "Ask follow-up",
                "message": "@follow-up Need more detail.",
                "channel": "web-dashboard",
                "status": "applied",
                "effect": "followup_requested",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    history = _load_approval_history(tmp_path, mission_id)

    assert history == [
        {
            "timestamp": "2026-03-30T02:00:00+00:00",
            "intervention_id": "int-3",
            "decision_record_id": "mission-approval-history-round-3-review",
            "action_key": "approve",
            "label": "Approve",
            "message": "@approve Approve rollout after transcript review?",
            "channel": "web-dashboard",
            "status": "applied",
            "effect": "approval_granted",
        },
        {
            "timestamp": "2026-03-30T01:00:00+00:00",
            "intervention_id": "int-2",
            "decision_record_id": "mission-approval-history-round-2-review",
            "action_key": "request_revision",
            "label": "Request revision",
            "message": "@request-revision Please revise this round before rollout.",
            "channel": "web-dashboard",
            "status": "applied",
            "effect": "revision_requested",
        },
    ]
