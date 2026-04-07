"""Pydantic v2 schema for spec-orch.toml configuration.

Provides validated, typed configuration models that mirror the TOML structure.
All models use ``extra = "allow"`` for forward compatibility — unknown keys
are preserved rather than rejected.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Sub-section models
# ---------------------------------------------------------------------------


class LinearConfig(BaseModel):
    model_config = {"extra": "allow"}

    token_env: str = "SPEC_ORCH_LINEAR_TOKEN"
    team_key: str = "SPC"
    poll_interval_seconds: int = 60
    issue_filter: str = "assigned_to_me"


class BuilderConfig(BaseModel):
    model_config = {"extra": "allow"}

    adapter: str = "codex_exec"
    executable: str | None = None
    codex_executable: str = "codex"
    agent: str | None = None
    model: str | None = None
    timeout_seconds: int = 1800
    permissions: str = "full-auto"


class ReviewerConfig(BaseModel):
    model_config = {"extra": "allow"}

    adapter: str = "local"


class PlannerConfig(BaseModel):
    model_config = {"extra": "allow"}

    model: str | None = None
    api_type: str = "anthropic"
    api_key_env: str | None = None
    api_base_env: str | None = None
    token_command: str | None = None


class VisualEvaluatorConfig(BaseModel):
    model_config = {"extra": "allow"}

    adapter: str | None = None
    command: list[str] = Field(default_factory=list)
    timeout_seconds: int = 300


class SupervisorConfig(BaseModel):
    model_config = {"extra": "allow"}

    adapter: str | None = None
    model: str | None = None
    api_type: str = "anthropic"
    api_key_env: str | None = None
    api_base_env: str | None = None
    max_rounds: int = 20
    visual_evaluator: VisualEvaluatorConfig = Field(default_factory=VisualEvaluatorConfig)


class AcceptanceEvaluatorConfig(BaseModel):
    model_config = {"extra": "allow"}

    adapter: str | None = None
    model: str | None = None
    api_type: str = "anthropic"
    api_key_env: str | None = None
    api_base_env: str | None = None
    auto_file_issues: bool = False
    min_confidence: float = 0.8
    min_severity: str = "high"


class GithubConfig(BaseModel):
    model_config = {"extra": "allow"}

    base_branch: str = "main"


class DaemonBehaviorConfig(BaseModel):
    model_config = {"extra": "allow"}

    max_concurrent: int = 1
    live_mission_workers: bool = False
    lockfile_dir: str = ".spec_orch_locks/"
    consume_state: str = "Ready"
    require_labels: list[str] = Field(default_factory=list)
    exclude_labels: list[str] = Field(default_factory=lambda: ["blocked", "needs-clarification"])
    skip_parents: bool = True
    max_retries: int = 3
    retry_base_delay_seconds: int = 60
    hotfix_labels: list[str] = Field(default_factory=lambda: ["hotfix", "urgent", "P0"])
    drain_batch_size: int = 5


class SpecSectionConfig(BaseModel):
    model_config = {"extra": "allow"}

    require_approval: bool = True


# ---------------------------------------------------------------------------
# Top-level config
# ---------------------------------------------------------------------------


class SpecOrchConfig(BaseModel):
    """Top-level validated configuration for spec-orch.toml."""

    model_config = {"extra": "allow"}

    linear: LinearConfig = Field(default_factory=LinearConfig)
    builder: BuilderConfig = Field(default_factory=BuilderConfig)
    reviewer: ReviewerConfig = Field(default_factory=ReviewerConfig)
    planner: PlannerConfig = Field(default_factory=PlannerConfig)
    supervisor: SupervisorConfig = Field(default_factory=SupervisorConfig)
    acceptance_evaluator: AcceptanceEvaluatorConfig = Field(
        default_factory=AcceptanceEvaluatorConfig
    )
    github: GithubConfig = Field(default_factory=GithubConfig)
    daemon: DaemonBehaviorConfig = Field(default_factory=DaemonBehaviorConfig)
    spec: SpecSectionConfig = Field(default_factory=SpecSectionConfig)

    @classmethod
    def from_toml(cls, path: Path) -> SpecOrchConfig:
        """Load and validate a spec-orch.toml file."""
        import tomllib

        with open(path, "rb") as f:
            raw = tomllib.load(f)
        return cls.model_validate(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> SpecOrchConfig:
        """Validate a raw dict (e.g. already-parsed TOML)."""
        return cls.model_validate(raw)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def validate_config(path: Path) -> list[str]:
    """Return a list of validation error strings (empty means valid).

    Designed as a CLI-friendly entrypoint: callers can print the list or
    check ``len(errors) == 0``.
    """
    import tomllib

    errors: list[str] = []
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except FileNotFoundError:
        return [f"Config file not found: {path}"]
    except tomllib.TOMLDecodeError as exc:
        return [f"TOML parse error: {exc}"]

    try:
        SpecOrchConfig.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        # Pydantic ValidationError has a nice `.errors()` method
        from pydantic import ValidationError

        if isinstance(exc, ValidationError):
            for err in exc.errors():
                loc = " -> ".join(str(p) for p in err["loc"])
                errors.append(f"{loc}: {err['msg']}")
        else:
            errors.append(str(exc))

    return errors
