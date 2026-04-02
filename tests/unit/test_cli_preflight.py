from __future__ import annotations

from pathlib import Path


def _write_config(path: Path) -> None:
    path.write_text(
        """
[llm]
default_model_chain = "default_reasoning"

[models.minimax_reasoning]
model = "MiniMax-M2.7-highspeed"
api_type = "anthropic"
api_key_env = "MINIMAX_API_KEY"
api_base_env = "MINIMAX_ANTHROPIC_BASE_URL"

[model_chains.default_reasoning]
primary = "minimax_reasoning"

[planner]
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_run_preflight_accepts_slot_env_default_model_chain(
    tmp_path: Path, monkeypatch
) -> None:
    from spec_orch.cli._helpers import _run_preflight

    _write_config(tmp_path / "spec-orch.toml")
    monkeypatch.delenv("SPEC_ORCH_LLM_API_KEY", raising=False)
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")

    report = _run_preflight(tmp_path)

    checks = {entry["name"]: entry for entry in report["checks"]}
    assert checks["planner_model"]["status"] == "pass"
    assert checks["planner_auth"]["status"] == "pass"
    assert "run" in report["ready"]
    assert "plan" in report["ready"]
    assert "discuss" in report["ready"]


def test_run_preflight_marks_planner_not_ready_without_usable_chain_credentials(
    tmp_path: Path, monkeypatch
) -> None:
    from spec_orch.cli._helpers import _run_preflight

    _write_config(tmp_path / "spec-orch.toml")
    monkeypatch.delenv("SPEC_ORCH_LLM_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_CN_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    report = _run_preflight(tmp_path)

    checks = {entry["name"]: entry for entry in report["checks"]}
    assert checks["planner_model"]["status"] == "pass"
    assert checks["planner_auth"]["status"] == "fail"
    assert "MINIMAX_API_KEY" in checks["planner_auth"]["fix"]
    assert "run" in report["not_ready"]
    assert "plan" in report["not_ready"]
    assert "discuss" in report["not_ready"]
