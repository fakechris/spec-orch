"""Tests for DaemonConfig — validates api_type and config loading."""

from __future__ import annotations

from spec_orch.services.daemon import DaemonConfig


class TestDaemonConfig:
    def test_default_api_type(self) -> None:
        cfg = DaemonConfig({})
        assert cfg.planner_api_type == "anthropic"

    def test_custom_api_type(self) -> None:
        cfg = DaemonConfig({"planner": {"api_type": "openai", "model": "gpt-4"}})
        assert cfg.planner_api_type == "openai"
        assert cfg.planner_model == "gpt-4"

    def test_defaults(self) -> None:
        cfg = DaemonConfig({})
        assert cfg.team_key == "SPC"
        assert cfg.poll_interval_seconds == 60
        assert cfg.codex_executable == "codex"
        assert cfg.max_concurrent == 1
        assert cfg.planner_model is None
