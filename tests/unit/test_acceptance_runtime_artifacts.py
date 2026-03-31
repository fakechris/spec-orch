from __future__ import annotations

import json

from spec_orch.acceptance_core.routing import AcceptanceGraphProfile


def test_write_graph_run_persists_canonical_graph_run_payload(tmp_path) -> None:
    from spec_orch.acceptance_runtime.artifacts import graph_run_dir, write_graph_run
    from spec_orch.acceptance_runtime.graph_models import AcceptanceGraphRun

    run = AcceptanceGraphRun(
        run_id="agr-1",
        mission_id="mission-1",
        round_id=2,
        graph_profile=AcceptanceGraphProfile.TUNED_EXPLORATORY,
        step_keys=["surface_scan", "guided_probe", "candidate_review", "summarize_judgment"],
        compare_overlay=False,
    )

    run_dir = graph_run_dir(tmp_path, run.run_id)
    payload = write_graph_run(run_dir, run)

    assert payload["run_id"] == "agr-1"
    persisted = json.loads((run_dir / "graph_run.json").read_text(encoding="utf-8"))
    assert persisted["graph_profile"] == "tuned_exploratory_graph"
    assert persisted["step_keys"][-1] == "summarize_judgment"


def test_write_step_artifact_persists_json_and_markdown(tmp_path) -> None:
    from spec_orch.acceptance_runtime.artifacts import graph_run_dir, write_step_artifact
    from spec_orch.acceptance_runtime.graph_models import AcceptanceStepResult

    run_dir = graph_run_dir(tmp_path, "agr-2")
    result = AcceptanceStepResult(
        step_key="candidate_review",
        decision="emit_candidate",
        outputs={"candidate_ids": ["cf-1"]},
        next_transition="summarize_judgment",
        warnings=["requires_compare"],
        review_markdown="## Candidate Review\n- Promote cf-1",
    )

    artifact = write_step_artifact(run_dir, 3, result)

    assert artifact["json_path"].endswith("steps/03-candidate_review.json")
    assert artifact["markdown_path"].endswith("steps/03-candidate_review.md")
    persisted = json.loads((run_dir / "steps" / "03-candidate_review.json").read_text("utf-8"))
    assert persisted["decision"] == "emit_candidate"
    assert persisted["warnings"] == ["requires_compare"]
