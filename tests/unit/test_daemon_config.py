"""Tests for DaemonConfig — validates api_type and config loading."""

from __future__ import annotations

from spec_orch.services.daemon import DaemonConfig
from spec_orch.services.round_orchestrator import RoundOrchestrator


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

    def test_supervisor_defaults(self) -> None:
        cfg = DaemonConfig({})
        assert cfg.supervisor_adapter is None
        assert cfg.supervisor_model is None
        assert cfg.supervisor_max_rounds == RoundOrchestrator.DEFAULT_MAX_ROUNDS
        assert cfg.supervisor_visual_evaluator_adapter is None
        assert cfg.supervisor_visual_evaluator_command == []

    def test_supervisor_custom_values(self) -> None:
        cfg = DaemonConfig(
            {
                "supervisor": {
                    "adapter": "litellm",
                    "model": "openai/gpt-4o",
                    "api_key_env": "SUP_KEY",
                    "api_base_env": "SUP_BASE",
                    "max_rounds": 9,
                    "visual_evaluator": {
                        "adapter": "command",
                        "command": ["{python}", "tools/visual_eval.py"],
                        "timeout_seconds": 45,
                    },
                }
            }
        )
        assert cfg.supervisor_adapter == "litellm"
        assert cfg.supervisor_model == "openai/gpt-4o"
        assert cfg.supervisor_api_key_env == "SUP_KEY"
        assert cfg.supervisor_api_base_env == "SUP_BASE"
        assert cfg.supervisor_max_rounds == 9
        assert cfg.supervisor_visual_evaluator_adapter == "command"
        assert cfg.supervisor_visual_evaluator_command == ["{python}", "tools/visual_eval.py"]
        assert cfg.supervisor_visual_evaluator_timeout_seconds == 45

    def test_acceptance_evaluator_defaults(self) -> None:
        cfg = DaemonConfig({})
        assert cfg.acceptance_evaluator_adapter is None
        assert cfg.acceptance_evaluator_model is None
        assert cfg.acceptance_evaluator_api_key_env is None
        assert cfg.acceptance_evaluator_api_base_env is None
        assert cfg.acceptance_auto_file_issues is False
        assert cfg.acceptance_min_confidence == 0.8
        assert cfg.acceptance_min_severity == "high"

    def test_acceptance_evaluator_custom_values(self) -> None:
        cfg = DaemonConfig(
            {
                "acceptance_evaluator": {
                    "adapter": "litellm",
                    "model": "minimax/MiniMax-M2.7-highspeed",
                    "api_key_env": "ACCEPT_KEY",
                    "api_base_env": "ACCEPT_BASE",
                    "auto_file_issues": True,
                    "min_confidence": 0.92,
                    "min_severity": "critical",
                }
            }
        )
        assert cfg.acceptance_evaluator_adapter == "litellm"
        assert cfg.acceptance_evaluator_model == "minimax/MiniMax-M2.7-highspeed"
        assert cfg.acceptance_evaluator_api_key_env == "ACCEPT_KEY"
        assert cfg.acceptance_evaluator_api_base_env == "ACCEPT_BASE"
        assert cfg.acceptance_auto_file_issues is True
        assert cfg.acceptance_min_confidence == 0.92
        assert cfg.acceptance_min_severity == "critical"
