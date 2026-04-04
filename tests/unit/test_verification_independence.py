from __future__ import annotations

from pathlib import Path

from spec_orch.domain.models import AcceptanceReviewResult


def test_collect_browser_evidence_marks_verifier_origin(tmp_path: Path) -> None:
    from spec_orch.services.acceptance.browser_evidence import collect_browser_evidence
    from spec_orch.services.visual.playwright_visual_eval import PageSnapshot

    round_dir = tmp_path / "round-01"
    screenshot = round_dir / "visual" / "home.png"
    screenshot.parent.mkdir(parents=True)
    screenshot.write_text("png", encoding="utf-8")

    payload = collect_browser_evidence(
        mission_id="mission-1",
        round_id=1,
        round_dir=round_dir,
        snapshots=[
            PageSnapshot(
                path="/",
                title="Home",
                url="http://127.0.0.1:8420/",
                screenshot_path=screenshot,
                console_errors=[],
                page_errors=[],
                interaction_log=[],
            )
        ],
    )

    assert payload["producer_role"] == "verifier"
    assert payload["verification_origin"] == "browser_verifier"


def test_evidence_bundle_reports_mixed_verification_provenance() -> None:
    from spec_orch.services.operator_semantics import evidence_bundle_from_acceptance_review

    review = AcceptanceReviewResult(
        status="warn",
        summary="Acceptance review consumed both verifier and builder artifacts.",
        confidence=0.8,
        evaluator="acceptance_llm",
        artifacts={
            "acceptance_review": "docs/specs/mission-1/rounds/round-01/acceptance_review.json",
            "builder_report": "docs/specs/mission-1/rounds/round-01/builder_report.json",
            "step_artifacts": [
                "docs/specs/mission-1/rounds/round-01/acceptance_graph_runs/agr-1/steps/01-route_inventory.json"
            ],
        },
    )

    bundle = evidence_bundle_from_acceptance_review(
        review,
        workspace_id="mission-1",
        round_id=1,
        artifact_path="docs/specs/mission-1/rounds/round-01/acceptance_review.json",
    ).to_dict()

    assert bundle["verification_origin"] == "independent_verifier"
    assert bundle["independence_status"] == "mixed"
    assert bundle["verifier_artifact_count"] == 2
    assert bundle["implementer_artifact_count"] == 1
    assert [item["producer_role"] for item in bundle["artifact_refs"]] == [
        "verifier",
        "implementer",
    ]
