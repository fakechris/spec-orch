"""Factory functions to create adapters from spec-orch.toml configuration."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from spec_orch.domain.protocols import BuilderAdapter, ReviewAdapter

logger = logging.getLogger(__name__)

_BUILDER_REGISTRY: dict[str, type] = {}
_REVIEWER_REGISTRY: dict[str, type] = {}


def register_builder(name: str, cls: type) -> None:
    _BUILDER_REGISTRY[name] = cls


def register_reviewer(name: str, cls: type) -> None:
    _REVIEWER_REGISTRY[name] = cls


def _load_toml(repo_root: Path) -> dict[str, Any]:
    config_path = repo_root / "spec-orch.toml"
    if not config_path.exists():
        return {}
    try:
        import tomllib

        with config_path.open("rb") as f:
            return tomllib.load(f)
    except Exception:
        logger.warning("Failed to parse spec-orch.toml", exc_info=True)
        return {}


def create_builder(
    repo_root: Path, *, toml_override: dict[str, Any] | None = None
) -> BuilderAdapter:
    """Create a BuilderAdapter from spec-orch.toml [builder] section."""
    raw = toml_override or _load_toml(repo_root)
    cfg = raw.get("builder", {})
    adapter_name = cfg.get("adapter", "codex_exec")

    if adapter_name == "codex_exec":
        from spec_orch.services.codex_exec_builder_adapter import CodexExecBuilderAdapter

        executable = cfg.get("executable") or cfg.get("codex_executable", "codex")
        timeout = cfg.get("timeout_seconds", 1800)
        return CodexExecBuilderAdapter(
            executable=executable, absolute_timeout_seconds=float(timeout)
        )

    if adapter_name == "opencode":
        from spec_orch.services.opencode_builder_adapter import OpenCodeBuilderAdapter

        return OpenCodeBuilderAdapter(
            executable=cfg.get("executable", "opencode"),
            model=cfg.get("model"),
            absolute_timeout_seconds=float(cfg.get("timeout_seconds", 1800)),
        )

    if adapter_name == "droid":
        from spec_orch.services.droid_builder_adapter import DroidBuilderAdapter

        return DroidBuilderAdapter(
            executable=cfg.get("executable", "droid"),
            model=cfg.get("model"),
            absolute_timeout_seconds=float(cfg.get("timeout_seconds", 1800)),
        )

    if adapter_name == "claude_code":
        from spec_orch.services.claude_code_builder_adapter import ClaudeCodeBuilderAdapter

        return ClaudeCodeBuilderAdapter(
            executable=cfg.get("executable", "claude"),
            model=cfg.get("model"),
            absolute_timeout_seconds=float(cfg.get("timeout_seconds", 1800)),
        )

    if adapter_name in _BUILDER_REGISTRY:
        instance: BuilderAdapter = _BUILDER_REGISTRY[adapter_name](**cfg)
        return instance

    raise ValueError(
        f"Unknown builder adapter: {adapter_name!r}. "
        "Supported: codex_exec, opencode, droid, claude_code"
    )


def create_reviewer(
    repo_root: Path, *, toml_override: dict[str, Any] | None = None
) -> ReviewAdapter:
    """Create a ReviewAdapter from spec-orch.toml [reviewer] section."""
    raw = toml_override or _load_toml(repo_root)
    cfg = raw.get("reviewer", {})
    adapter_name = cfg.get("adapter", "local")

    if adapter_name == "local":
        from spec_orch.services.review_adapter import LocalReviewAdapter

        return LocalReviewAdapter()

    if adapter_name == "llm":
        from spec_orch.services.llm_review_adapter import LLMReviewAdapter

        model = cfg.get("model")
        api_key = None
        if env := cfg.get("api_key_env"):
            api_key = os.environ.get(env)
        api_base = None
        if env := cfg.get("api_base_env"):
            api_base = os.environ.get(env)

        return LLMReviewAdapter(model=model, api_key=api_key, api_base=api_base)

    if adapter_name in _REVIEWER_REGISTRY:
        rev_instance: ReviewAdapter = _REVIEWER_REGISTRY[adapter_name](**cfg)
        return rev_instance

    raise ValueError(f"Unknown reviewer adapter: {adapter_name!r}. Supported: local, llm")
