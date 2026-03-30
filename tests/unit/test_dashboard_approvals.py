from __future__ import annotations

import json
from pathlib import Path


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


def test_record_approval_action_appends_decision_core_response_metadata(tmp_path: Path) -> None:
    from spec_orch.dashboard.approvals import _record_approval_action

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

    payload = _record_approval_action(
        tmp_path,
        mission_id,
        action_key="approve",
        label="Approve",
        message="@approve Approve rollout after transcript review?",
        channel="web-dashboard",
        status="applied",
    )

    assert payload["effect"] == "approval_granted"
    history = [
        json.loads(line)
        for line in (operator_dir / "intervention_responses.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
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
