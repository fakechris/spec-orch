from __future__ import annotations

import json
from pathlib import Path

from spec_orch.decision_core.models import DecisionAuthority, DecisionReview
from spec_orch.decision_core.review_queue import (
    append_decision_review,
    decision_review_history_path,
    load_decision_reviews,
)


def test_append_and_load_decision_reviews(tmp_path: Path) -> None:
    review = DecisionReview(
        review_id="rev-2",
        record_id="dec-2",
        reviewer_kind="self",
        verdict="revision_requested",
        summary="Need another pass.",
        recommended_authority=DecisionAuthority.HUMAN_REQUIRED,
        escalate_to_human=True,
        reflection="Self-review found unresolved risk.",
        created_at="2026-03-30T12:00:00+00:00",
    )

    payload = append_decision_review(tmp_path, "mission-1", review=review)

    assert payload["record_id"] == "dec-2"
    assert decision_review_history_path(tmp_path, "mission-1").exists()
    loaded = load_decision_reviews(tmp_path, "mission-1")
    assert loaded == [payload]


def test_load_decision_reviews_filters_by_record_id_and_sorts_latest_first(tmp_path: Path) -> None:
    path = decision_review_history_path(tmp_path, "mission-2")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "review_id": "rev-old",
                        "record_id": "dec-3",
                        "reviewer_kind": "human",
                        "verdict": "followup_requested",
                        "summary": "Need more detail.",
                        "recommended_authority": "human_required",
                        "escalate_to_human": True,
                        "reflection": "",
                        "created_at": "2026-03-30T10:00:00+00:00",
                    }
                ),
                json.dumps(
                    {
                        "review_id": "rev-new",
                        "record_id": "dec-3",
                        "reviewer_kind": "human",
                        "verdict": "approval_granted",
                        "summary": "Approved.",
                        "recommended_authority": "human_required",
                        "escalate_to_human": False,
                        "reflection": "",
                        "created_at": "2026-03-30T11:00:00+00:00",
                    }
                ),
                json.dumps(
                    {
                        "review_id": "rev-other",
                        "record_id": "dec-4",
                        "reviewer_kind": "self",
                        "verdict": "revision_requested",
                        "summary": "Different record.",
                        "recommended_authority": None,
                        "escalate_to_human": False,
                        "reflection": "",
                        "created_at": "2026-03-30T09:00:00+00:00",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = load_decision_reviews(tmp_path, "mission-2", record_id="dec-3")

    assert [item["review_id"] for item in loaded] == ["rev-new", "rev-old"]
