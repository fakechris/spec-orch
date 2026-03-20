"""Tests for degradation detector."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from spec_orch.services.degradation_detector import DegradationDetector


def _write_runs(tmp_path: Path, count: int, mergeable_fn: Callable[[int], bool]) -> None:
    """Create count run directories with conclusion.json."""
    runs = tmp_path / ".spec_orch_runs"
    for i in range(count):
        rd = runs / f"issue-{i:03d}" / "run_artifact"
        rd.mkdir(parents=True)
        (rd / "conclusion.json").write_text(
            json.dumps(
                {
                    "run_id": f"r{i}",
                    "issue_id": f"issue-{i:03d}",
                    "mergeable": mergeable_fn(i),
                    "verdict": "pass" if mergeable_fn(i) else "fail",
                }
            )
        )


def test_no_degradation_stable(tmp_path: Path) -> None:
    _write_runs(tmp_path, 30, lambda _: True)
    d = DegradationDetector(tmp_path, recent_window=5, baseline_window=20)
    report = d.detect()
    assert not report.degraded
    assert report.signals == []


def test_degradation_detected(tmp_path: Path) -> None:
    def mergeable(i: int) -> bool:
        return i < 20

    _write_runs(tmp_path, 25, mergeable)
    d = DegradationDetector(tmp_path, recent_window=5, baseline_window=15, threshold=0.10)
    report = d.detect()
    assert report.degraded
    pass_signal = [s for s in report.signals if s.metric == "pass_rate"]
    assert len(pass_signal) == 1
    assert pass_signal[0].delta < 0


def test_not_enough_runs(tmp_path: Path) -> None:
    _write_runs(tmp_path, 3, lambda _: True)
    d = DegradationDetector(tmp_path, recent_window=5)
    report = d.detect()
    assert not report.degraded
    assert report.recent_runs == 0


def test_write_report(tmp_path: Path) -> None:
    _write_runs(tmp_path, 20, lambda i: i < 15)
    d = DegradationDetector(tmp_path, recent_window=5, baseline_window=10)
    report = d.detect()
    out = tmp_path / "degradation.json"
    d.write_report(report, out)
    assert out.exists()
    data = json.loads(out.read_text())
    assert "degraded" in data
    assert "signals" in data


def test_high_severity_on_large_drop(tmp_path: Path) -> None:
    def mergeable(i: int) -> bool:
        return i < 10

    _write_runs(tmp_path, 20, mergeable)
    d = DegradationDetector(tmp_path, recent_window=5, baseline_window=10, threshold=0.10)
    report = d.detect()
    assert report.degraded
    high = [s for s in report.signals if s.severity == "high"]
    assert len(high) >= 1
