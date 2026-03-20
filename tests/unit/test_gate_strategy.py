"""Tests for gate strategy features: profiles, auto-merge, CLI helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from spec_orch.domain.models import (
    GateInput,
    GateVerdict,
    ReviewSummary,
    VerificationSummary,
)
from spec_orch.services.gate_service import (
    GatePolicy,
    GateService,
)


def _passing_input(**overrides: object) -> GateInput:
    defaults = dict(
        spec_exists=True,
        spec_approved=True,
        within_boundaries=True,
        builder_succeeded=True,
        verification=VerificationSummary(
            lint_passed=True,
            typecheck_passed=True,
            test_passed=True,
            build_passed=True,
        ),
        review=ReviewSummary(verdict="pass", reviewed_by="bot"),
        human_acceptance=True,
    )
    defaults.update(overrides)
    return GateInput(**defaults)  # type: ignore[arg-type]


# ── Profile tests ──


def test_profile_disables_condition() -> None:
    policy = GatePolicy(
        profiles={"daemon": {"disable": ["human_acceptance"], "auto_merge": True}},
    )
    daemon_policy = policy.with_profile("daemon")
    assert "human_acceptance" not in daemon_policy.required_conditions
    assert daemon_policy.auto_merge is True


def test_profile_enables_optional_condition() -> None:
    policy = GatePolicy(
        required_conditions={"builder"},
        profiles={"strict": {"enable": ["findings", "preview"]}},
    )
    strict = policy.with_profile("strict")
    assert "findings" in strict.required_conditions
    assert "preview" in strict.required_conditions
    assert "builder" in strict.required_conditions


def test_unknown_profile_returns_same_policy() -> None:
    policy = GatePolicy()
    same = policy.with_profile("nonexistent")
    assert same.required_conditions == policy.required_conditions
    assert same.auto_merge == policy.auto_merge


def test_available_profiles() -> None:
    policy = GatePolicy(profiles={"ci": {}, "daemon": {}, "strict": {}})
    assert policy.available_profiles() == ["ci", "daemon", "strict"]


# ── Auto-merge condition tests ──


def test_should_auto_merge_when_enabled_and_all_pass() -> None:
    policy = GatePolicy(
        required_conditions={"builder", "verification"},
        auto_merge=True,
    )
    svc = GateService(policy=policy)
    gate_input = _passing_input()
    assert svc.should_auto_merge(gate_input) is True


def test_should_not_auto_merge_when_disabled() -> None:
    policy = GatePolicy(
        required_conditions={"builder"},
        auto_merge=False,
    )
    svc = GateService(policy=policy)
    assert svc.should_auto_merge(_passing_input()) is False


def test_auto_merge_conditions_subset() -> None:
    """Auto-merge triggers even when some required conditions fail,
    as long as auto_merge_conditions all pass."""
    policy = GatePolicy(
        required_conditions={"builder", "verification", "human_acceptance"},
        auto_merge=True,
        auto_merge_conditions={"builder", "verification"},
    )
    svc = GateService(policy=policy)
    gate_input = _passing_input(human_acceptance=False)

    verdict = svc.evaluate(gate_input)
    assert not verdict.mergeable  # full gate fails

    assert svc.should_auto_merge(gate_input) is True  # auto-merge subset passes


def test_auto_merge_conditions_fail() -> None:
    policy = GatePolicy(
        required_conditions={"builder", "verification"},
        auto_merge=True,
        auto_merge_conditions={"builder", "verification"},
    )
    svc = GateService(policy=policy)
    gate_input = _passing_input(builder_succeeded=False)
    assert svc.should_auto_merge(gate_input) is False


# ── YAML loading with profiles and auto_merge_conditions ──


def test_from_yaml_with_profiles(tmp_path: Path) -> None:
    policy_file = tmp_path / "gate.policy.yaml"
    policy_file.write_text("""\
conditions:
  builder:
    required: true
  verification:
    required: true
  human_acceptance:
    required: true

auto_merge: false

auto_merge_conditions:
  - builder
  - verification

profiles:
  daemon:
    disable:
      - human_acceptance
    auto_merge: true
  ci:
    enable:
      - findings
    auto_merge: false
""")
    policy = GatePolicy.from_yaml(policy_file)

    assert policy.auto_merge is False
    assert policy.auto_merge_conditions == {"builder", "verification"}
    assert "daemon" in policy.profiles
    assert "ci" in policy.profiles

    daemon = policy.with_profile("daemon")
    assert "human_acceptance" not in daemon.required_conditions
    assert daemon.auto_merge is True

    ci = policy.with_profile("ci")
    assert "findings" in ci.required_conditions
    assert ci.auto_merge is False


# ── describe_as_dict ──


def test_describe_as_dict() -> None:
    policy = GatePolicy(
        required_conditions={"builder", "verification"},
        auto_merge=True,
        auto_merge_conditions={"builder"},
        profiles={"ci": {}},
    )
    svc = GateService(policy=policy)
    d = svc.describe_as_dict()
    assert d["auto_merge"] is True
    assert d["auto_merge_conditions"] == ["builder"]
    assert "ci" in d["profiles"]


# ── GateVerdict model ──


def test_gate_verdict_fields() -> None:
    v = GateVerdict(
        mergeable=False,
        failed_conditions=["builder"],
        mergeable_internal=False,
        mergeable_external=True,
    )
    assert not v.mergeable
    assert v.failed_conditions == ["builder"]


# ── CLI helper: _build_gate_input_from_report ──


def test_build_gate_input_from_report() -> None:
    from spec_orch.cli._helpers import _build_gate_input_from_report

    data = {
        "builder": {"succeeded": True},
        "review": {"verdict": "pass", "reviewed_by": "coderabbit"},
        "verification": {
            "lint": {"command": ["ruff"], "exit_code": 0},
            "typecheck": {"command": ["mypy"], "exit_code": 0},
            "test": {"command": ["pytest"], "exit_code": 0},
            "build": {"command": ["python", "-m", "build"], "exit_code": 0},
        },
        "human_acceptance": {"accepted": True},
    }
    gate_input = _build_gate_input_from_report(data)
    assert gate_input.builder_succeeded is True
    assert gate_input.verification.all_passed is True
    assert gate_input.review.verdict == "pass"
    assert gate_input.human_acceptance is True


def test_build_gate_input_from_empty_report() -> None:
    from spec_orch.cli._helpers import _build_gate_input_from_report

    gate_input = _build_gate_input_from_report({})
    assert gate_input.builder_succeeded is False
    assert gate_input.verification.all_passed is True
    assert gate_input.review.verdict == "pending"
    assert gate_input.human_acceptance is False


# ── Daemon gate policy loading ──


def test_daemon_loads_daemon_profile(tmp_path: Path) -> None:
    from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon

    config = DaemonConfig({})
    daemon = SpecOrchDaemon(config=config, repo_root=tmp_path)

    policy_file = tmp_path / "gate.policy.yaml"
    policy_file.write_text("""\
conditions:
  builder:
    required: true
  human_acceptance:
    required: true
auto_merge: false
profiles:
  daemon:
    disable:
      - human_acceptance
    auto_merge: true
""")
    loaded = daemon._load_gate_policy()
    assert loaded.auto_merge is True
    assert "human_acceptance" not in loaded.required_conditions


# ── GitHubPRService merge/ready ──


def test_github_pr_service_merge_pr_calls_gh(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import subprocess

    calls: list[list[str]] = []

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if "pr" in cmd and "view" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="42\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run)

    from spec_orch.services.github_pr_service import GitHubPRService

    svc = GitHubPRService()
    result = svc.merge_pr(tmp_path, method="squash")
    assert result is True

    merge_cmd = [c for c in calls if "merge" in c]
    assert len(merge_cmd) == 1
    assert "--squash" in merge_cmd[0]
    assert "--auto" in merge_cmd[0]


def test_github_pr_service_mark_ready(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import subprocess

    calls: list[list[str]] = []

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run)

    from spec_orch.services.github_pr_service import GitHubPRService

    svc = GitHubPRService()
    result = svc.mark_ready(tmp_path, pr_number=42)
    assert result is True
    ready_cmd = [c for c in calls if "ready" in c]
    assert len(ready_cmd) == 1
    assert "42" in ready_cmd[0]
