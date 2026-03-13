import json
from pathlib import Path

from spec_orch.domain.models import Finding, GateInput, ReviewMeta
from spec_orch.services.finding_store import (
    append_finding,
    append_findings,
    bump_review_epoch,
    fingerprint_from,
    load_findings,
    load_review_meta,
    resolve_finding,
)
from spec_orch.services.gate_service import GateService


def _make_finding(
    *,
    fid: str = "f1",
    severity: str = "blocking",
    scope: str = "in_spec",
    resolved: bool = False,
) -> Finding:
    return Finding(
        id=fid,
        source="test",
        severity=severity,
        confidence=0.9,
        scope=scope,
        fingerprint=fingerprint_from("test", f"desc-{fid}"),
        description=f"Description for {fid}",
        resolved=resolved,
    )


def test_append_and_load_findings(tmp_path: Path) -> None:
    f1 = _make_finding(fid="f1")
    f2 = _make_finding(fid="f2", severity="advisory")
    append_finding(tmp_path, f1)
    append_finding(tmp_path, f2)

    loaded = load_findings(tmp_path)
    assert len(loaded) == 2
    assert loaded[0].id == "f1"
    assert loaded[0].severity == "blocking"
    assert loaded[1].id == "f2"
    assert loaded[1].severity == "advisory"


def test_append_findings_batch(tmp_path: Path) -> None:
    findings = [_make_finding(fid=f"f{i}") for i in range(5)]
    append_findings(tmp_path, findings)
    assert len(load_findings(tmp_path)) == 5


def test_load_findings_returns_empty_if_absent(tmp_path: Path) -> None:
    assert load_findings(tmp_path) == []


def test_resolve_finding(tmp_path: Path) -> None:
    f1 = _make_finding(fid="f1")
    append_finding(tmp_path, f1)
    assert not load_findings(tmp_path)[0].resolved

    assert resolve_finding(tmp_path, "f1") is True
    assert load_findings(tmp_path)[0].resolved is True


def test_resolve_finding_missing_id(tmp_path: Path) -> None:
    f1 = _make_finding(fid="f1")
    append_finding(tmp_path, f1)
    assert resolve_finding(tmp_path, "nonexistent") is False


def test_bump_review_epoch(tmp_path: Path) -> None:
    assert bump_review_epoch(tmp_path) == 1
    assert bump_review_epoch(tmp_path) == 2
    assert bump_review_epoch(tmp_path) == 3

    epoch_data = json.loads((tmp_path / "review_epoch.json").read_text())
    assert epoch_data["review_epoch"] == 3
    assert epoch_data["autofix_budget"] == 3


def test_load_review_meta(tmp_path: Path) -> None:
    f1 = _make_finding(fid="f1")
    f2 = _make_finding(fid="f2", severity="advisory")
    append_findings(tmp_path, [f1, f2])
    bump_review_epoch(tmp_path)

    meta = load_review_meta(tmp_path)
    assert meta.review_epoch == 1
    assert meta.autofix_budget == 3
    assert len(meta.findings) == 2
    assert len(meta.blocking_unresolved) == 1
    assert not meta.budget_exhausted


def test_review_meta_blocking_unresolved() -> None:
    meta = ReviewMeta(
        findings=[
            _make_finding(fid="f1", severity="blocking", scope="in_spec"),
            _make_finding(fid="f2", severity="blocking", scope="out_of_spec"),
            _make_finding(fid="f3", severity="advisory", scope="in_spec"),
            _make_finding(fid="f4", severity="blocking", scope="in_spec", resolved=True),
        ]
    )
    unresolved = meta.blocking_unresolved
    assert len(unresolved) == 1
    assert unresolved[0].id == "f1"


def test_review_meta_budget_exhausted() -> None:
    meta = ReviewMeta(review_epoch=3, autofix_budget=3)
    assert meta.budget_exhausted

    meta2 = ReviewMeta(review_epoch=2, autofix_budget=3)
    assert not meta2.budget_exhausted


def test_review_meta_deduplication() -> None:
    fp = fingerprint_from("test", "same issue")
    meta = ReviewMeta(
        findings=[
            Finding(
                id="f1",
                source="test",
                severity="blocking",
                confidence=0.9,
                scope="in_spec",
                fingerprint=fp,
                description="same issue",
            ),
            Finding(
                id="f2",
                source="test",
                severity="blocking",
                confidence=0.8,
                scope="in_spec",
                fingerprint=fp,
                description="same issue",
            ),
        ]
    )
    deduped = meta.deduplicated_findings()
    assert len(deduped) == 1
    assert deduped[0].id == "f1"


def test_fingerprint_stable() -> None:
    fp1 = fingerprint_from("gemini", "path traversal", "src/a.py", 10)
    fp2 = fingerprint_from("gemini", "path traversal", "src/a.py", 10)
    fp3 = fingerprint_from("gemini", "path traversal", "src/b.py", 10)
    assert fp1 == fp2
    assert fp1 != fp3


def test_gate_blocks_on_unresolved_findings() -> None:
    from spec_orch.services.gate_service import GatePolicy

    policy = GatePolicy(
        required_conditions={"findings", "human_acceptance"},
    )
    svc = GateService(policy=policy)

    meta_with_blocking = ReviewMeta(
        findings=[
            _make_finding(fid="f1", severity="blocking", scope="in_spec"),
        ]
    )
    verdict = svc.evaluate(
        GateInput(
            human_acceptance=True,
            review_meta=meta_with_blocking,
        )
    )
    assert not verdict.mergeable
    assert "findings" in verdict.failed_conditions

    meta_resolved = ReviewMeta(
        findings=[
            _make_finding(fid="f1", severity="blocking", scope="in_spec", resolved=True),
        ]
    )
    verdict2 = svc.evaluate(
        GateInput(
            human_acceptance=True,
            review_meta=meta_resolved,
        )
    )
    assert "findings" not in verdict2.failed_conditions
