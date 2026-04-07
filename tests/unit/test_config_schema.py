"""Tests for pydantic-based config schema validation."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from spec_orch.services.config_schema import (
    AcceptanceEvaluatorConfig,
    BuilderConfig,
    DaemonBehaviorConfig,
    LinearConfig,
    PlannerConfig,
    SpecOrchConfig,
    SupervisorConfig,
    validate_config,
)

# ---------------------------------------------------------------------------
# SpecOrchConfig — dict-based
# ---------------------------------------------------------------------------


class TestSpecOrchConfigFromDict:
    def test_empty_dict_uses_all_defaults(self) -> None:
        cfg = SpecOrchConfig.from_dict({})
        assert cfg.linear.team_key == "SPC"
        assert cfg.builder.adapter == "codex_exec"
        assert cfg.daemon.max_concurrent == 1
        assert cfg.supervisor.max_rounds == 20

    def test_partial_override(self) -> None:
        cfg = SpecOrchConfig.from_dict({"linear": {"team_key": "ABC"}})
        assert cfg.linear.team_key == "ABC"
        # Other linear defaults still hold
        assert cfg.linear.poll_interval_seconds == 60

    def test_full_valid_config(self) -> None:
        raw = {
            "linear": {"token_env": "MY_TOKEN", "team_key": "XYZ", "poll_interval_seconds": 30},
            "builder": {"adapter": "acpx", "model": "gpt-4"},
            "reviewer": {"adapter": "llm"},
            "planner": {"model": "claude-3", "api_type": "openai"},
            "supervisor": {
                "adapter": "litellm",
                "max_rounds": 10,
                "visual_evaluator": {
                    "adapter": "command",
                    "command": ["python", "eval.py"],
                    "timeout_seconds": 60,
                },
            },
            "acceptance_evaluator": {
                "adapter": "litellm",
                "min_confidence": 0.9,
                "auto_file_issues": True,
            },
            "daemon": {"max_concurrent": 4, "consume_state": "Todo"},
        }
        cfg = SpecOrchConfig.from_dict(raw)
        assert cfg.linear.token_env == "MY_TOKEN"
        assert cfg.builder.model == "gpt-4"
        assert cfg.supervisor.visual_evaluator.adapter == "command"
        assert cfg.supervisor.visual_evaluator.command == ["python", "eval.py"]
        assert cfg.acceptance_evaluator.min_confidence == 0.9
        assert cfg.daemon.max_concurrent == 4


class TestMissingOptionalFieldsUseDefaults:
    def test_linear_defaults(self) -> None:
        cfg = LinearConfig()
        assert cfg.token_env == "SPEC_ORCH_LINEAR_TOKEN"
        assert cfg.team_key == "SPC"
        assert cfg.poll_interval_seconds == 60

    def test_builder_defaults(self) -> None:
        cfg = BuilderConfig()
        assert cfg.adapter == "codex_exec"
        assert cfg.executable is None
        assert cfg.codex_executable == "codex"
        assert cfg.timeout_seconds == 1800

    def test_planner_defaults(self) -> None:
        cfg = PlannerConfig()
        assert cfg.model is None
        assert cfg.api_type == "anthropic"
        assert cfg.api_key_env is None

    def test_supervisor_defaults(self) -> None:
        cfg = SupervisorConfig()
        assert cfg.adapter is None
        assert cfg.max_rounds == 20
        assert cfg.visual_evaluator.adapter is None
        assert cfg.visual_evaluator.command == []
        assert cfg.visual_evaluator.timeout_seconds == 300

    def test_acceptance_defaults(self) -> None:
        cfg = AcceptanceEvaluatorConfig()
        assert cfg.auto_file_issues is False
        assert cfg.min_confidence == 0.8
        assert cfg.min_severity == "high"

    def test_daemon_behavior_defaults(self) -> None:
        cfg = DaemonBehaviorConfig()
        assert cfg.max_concurrent == 1
        assert cfg.exclude_labels == ["blocked", "needs-clarification"]
        assert cfg.hotfix_labels == ["hotfix", "urgent", "P0"]
        assert cfg.max_retries == 3


class TestInvalidTypesRaiseClearErrors:
    def test_invalid_poll_interval_type(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            LinearConfig(poll_interval_seconds="not_a_number")  # type: ignore[arg-type]
        errors = exc_info.value.errors()
        assert any("poll_interval_seconds" in str(e["loc"]) for e in errors)

    def test_invalid_max_rounds_type(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            SupervisorConfig(max_rounds="twelve")  # type: ignore[arg-type]
        errors = exc_info.value.errors()
        assert any("max_rounds" in str(e["loc"]) for e in errors)

    def test_invalid_min_confidence_type(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            AcceptanceEvaluatorConfig(min_confidence="high")  # type: ignore[arg-type]
        errors = exc_info.value.errors()
        assert any("min_confidence" in str(e["loc"]) for e in errors)

    def test_invalid_nested_type_via_top_level(self) -> None:
        with pytest.raises(ValidationError):
            SpecOrchConfig.from_dict({"linear": {"poll_interval_seconds": "bad"}})


class TestUnknownSectionsAllowed:
    """Forward compatibility: unknown TOML sections must not cause errors."""

    def test_unknown_top_level_section(self) -> None:
        cfg = SpecOrchConfig.from_dict({"future_feature": {"enabled": True}})
        assert cfg.linear.team_key == "SPC"  # defaults still work

    def test_unknown_key_in_subsection(self) -> None:
        cfg = SpecOrchConfig.from_dict({"linear": {"new_field": 42}})
        assert cfg.linear.team_key == "SPC"

    def test_unknown_keys_preserved_in_model_dump(self) -> None:
        cfg = SpecOrchConfig.from_dict({"custom": {"x": 1}})
        dumped = cfg.model_dump()
        assert dumped["custom"] == {"x": 1}


# ---------------------------------------------------------------------------
# from_toml — parse real TOML content
# ---------------------------------------------------------------------------


class TestFromToml:
    def test_round_trip_toml(self, tmp_path: Path) -> None:
        toml_content = textwrap.dedent("""\
            [linear]
            team_key = "TEST"
            poll_interval_seconds = 30

            [builder]
            adapter = "acpx"

            [daemon]
            max_concurrent = 2
            consume_state = "Todo"
        """)
        toml_file = tmp_path / "spec-orch.toml"
        toml_file.write_text(toml_content)

        cfg = SpecOrchConfig.from_toml(toml_file)
        assert cfg.linear.team_key == "TEST"
        assert cfg.linear.poll_interval_seconds == 30
        assert cfg.builder.adapter == "acpx"
        assert cfg.daemon.max_concurrent == 2

    def test_real_toml_format_with_extra_sections(self, tmp_path: Path) -> None:
        toml_content = textwrap.dedent("""\
            [issue]
            source = "linear"

            [linear]
            token_env = "MY_TOKEN"
            team_key = "SON"

            [verification]
            lint = ["{python}", "-m", "ruff", "check", "src/"]

            [builder]
            adapter = "acpx"

            [evolution]
            enabled = true
        """)
        toml_file = tmp_path / "spec-orch.toml"
        toml_file.write_text(toml_content)

        cfg = SpecOrchConfig.from_toml(toml_file)
        assert cfg.linear.team_key == "SON"
        assert cfg.builder.adapter == "acpx"
        # Unknown sections preserved
        dumped = cfg.model_dump()
        assert dumped["issue"] == {"source": "linear"}


# ---------------------------------------------------------------------------
# validate_config helper
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_valid_config_returns_empty(self, tmp_path: Path) -> None:
        toml_file = tmp_path / "spec-orch.toml"
        toml_file.write_text("[linear]\nteam_key = 'OK'\n")
        assert validate_config(toml_file) == []

    def test_missing_file_returns_error(self, tmp_path: Path) -> None:
        errors = validate_config(tmp_path / "nonexistent.toml")
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_invalid_toml_syntax_returns_error(self, tmp_path: Path) -> None:
        toml_file = tmp_path / "bad.toml"
        toml_file.write_text("this is not valid toml {{{")
        errors = validate_config(toml_file)
        assert len(errors) == 1
        assert "TOML parse error" in errors[0]

    def test_invalid_type_returns_field_errors(self, tmp_path: Path) -> None:
        toml_file = tmp_path / "bad-type.toml"
        toml_file.write_text("[linear]\npoll_interval_seconds = 'slow'\n")
        errors = validate_config(toml_file)
        assert len(errors) >= 1
        assert any("poll_interval_seconds" in e for e in errors)
