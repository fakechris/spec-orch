"""Factory functions to create adapters from spec-orch.toml configuration."""

from __future__ import annotations

import logging
import shlex
from pathlib import Path
from typing import Any

from spec_orch.domain.protocols import BuilderAdapter, IssueSource, ReviewAdapter
from spec_orch.services.litellm_profile import resolve_role_litellm_settings

logger = logging.getLogger(__name__)

_BUILDER_REGISTRY: dict[str, type] = {}
_REVIEWER_REGISTRY: dict[str, type] = {}
_ISSUE_SOURCE_REGISTRY: dict[str, type] = {}


def register_builder(name: str, cls: type) -> None:
    _BUILDER_REGISTRY[name] = cls


def register_reviewer(name: str, cls: type) -> None:
    _REVIEWER_REGISTRY[name] = cls


def register_issue_source(name: str, cls: type) -> None:
    _ISSUE_SOURCE_REGISTRY[name] = cls


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
        from spec_orch.services.builders.codex_exec_builder_adapter import CodexExecBuilderAdapter

        executable = cfg.get("executable") or cfg.get("codex_executable", "codex")
        timeout = cfg.get("timeout_seconds", 1800)
        return CodexExecBuilderAdapter(
            executable=executable, absolute_timeout_seconds=float(timeout)
        )

    elif adapter_name == "opencode":
        from spec_orch.services.builders.opencode_builder_adapter import OpenCodeBuilderAdapter

        return OpenCodeBuilderAdapter(
            executable=cfg.get("executable", "opencode"),
            model=cfg.get("model"),
            absolute_timeout_seconds=float(cfg.get("timeout_seconds", 1800)),
        )

    elif adapter_name == "droid":
        from spec_orch.services.builders.droid_builder_adapter import DroidBuilderAdapter

        return DroidBuilderAdapter(
            executable=cfg.get("executable", "droid"),
            model=cfg.get("model"),
            absolute_timeout_seconds=float(cfg.get("timeout_seconds", 1800)),
        )

    elif adapter_name == "claude_code":
        from spec_orch.services.builders.claude_code_builder_adapter import ClaudeCodeBuilderAdapter

        return ClaudeCodeBuilderAdapter(
            executable=cfg.get("executable", "claude"),
            model=cfg.get("model"),
            absolute_timeout_seconds=float(cfg.get("timeout_seconds", 1800)),
        )

    elif adapter_name == "acpx" or adapter_name.startswith("acpx_"):
        from spec_orch.services.builders.acpx_builder_adapter import AcpxBuilderAdapter

        agent = cfg.get("agent")
        if not agent and adapter_name.startswith("acpx_"):
            agent = adapter_name[len("acpx_") :]
        agent = agent or "opencode"

        return AcpxBuilderAdapter(
            agent=agent,
            model=cfg.get("model"),
            session_name=cfg.get("session_name"),
            permissions=cfg.get("permissions", "full-auto"),
            executable=cfg.get("executable", "npx"),
            acpx_package=cfg.get("acpx_package", "acpx"),
            absolute_timeout_seconds=float(cfg.get("timeout_seconds", 1800)),
        )

    elif adapter_name in _BUILDER_REGISTRY:
        builder_cfg = {k: v for k, v in cfg.items() if k != "adapter"}
        instance: BuilderAdapter = _BUILDER_REGISTRY[adapter_name](**builder_cfg)
        return instance

    raise ValueError(
        f"Unknown builder adapter: {adapter_name!r}. "
        "Supported: codex_exec, opencode, droid, claude_code, acpx, acpx_<agent>"
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

    elif adapter_name == "llm":
        from spec_orch.services.llm_review_adapter import LLMReviewAdapter

        settings = resolve_role_litellm_settings(
            raw,
            section_name="reviewer",
            default_model=str(cfg.get("model", "")),
            default_api_type=str(cfg.get("api_type", "anthropic")),
        )

        return LLMReviewAdapter(
            model=str(settings["model"]) or None,
            api_key=str(settings["api_key"]) or None,
            api_base=str(settings["api_base"]) or None,
            temperature=float(cfg.get("temperature", 0.2)),
            max_diff_chars=int(cfg.get("max_diff_chars", 60_000)),
            max_spec_chars=int(cfg.get("max_spec_chars", 10_000)),
            model_chain=settings["model_chain"],
        )

    elif adapter_name in _REVIEWER_REGISTRY:
        reviewer_cfg = {k: v for k, v in cfg.items() if k != "adapter"}
        rev_instance: ReviewAdapter = _REVIEWER_REGISTRY[adapter_name](**reviewer_cfg)
        return rev_instance

    raise ValueError(f"Unknown reviewer adapter: {adapter_name!r}. Supported: local, llm")


def load_verification_commands(
    repo_root: Path, *, toml_override: dict[str, Any] | None = None
) -> dict[str, list[str]]:
    """Load verification commands from spec-orch.toml [verification] section.

    Returns an empty dict when no [verification] section is present.
    All keys in the section are treated as verification step names,
    supporting arbitrary steps beyond the standard lint/typecheck/test/build.
    """
    raw = toml_override or _load_toml(repo_root)
    cfg = raw.get("verification")
    if cfg is None:
        return {}
    commands: dict[str, list[str]] = {}
    for step_name, cmd in cfg.items():
        if cmd is not None:
            if isinstance(cmd, str):
                commands[step_name] = shlex.split(cmd)
            elif isinstance(cmd, list):
                commands[step_name] = [str(c) for c in cmd]
    return commands


def create_issue_source(
    repo_root: Path,
    *,
    toml_override: dict[str, Any] | None = None,
    source_override: str | None = None,
) -> IssueSource:
    """Create an IssueSource from spec-orch.toml [issue] section.

    Args:
        repo_root: Project root directory.
        toml_override: Pre-loaded TOML config (optional).
        source_override: Explicit source name, overrides [issue].source.
    """
    raw = toml_override or _load_toml(repo_root)
    issue_cfg = raw.get("issue", {})
    source_name = source_override or issue_cfg.get("source", "fixture")
    verify_cmds = load_verification_commands(repo_root, toml_override=raw)

    if source_name == "linear":
        from spec_orch.services.linear_client import LinearClient
        from spec_orch.services.linear_issue_source import LinearIssueSource

        client = LinearClient()
        return LinearIssueSource(
            client=client,
            default_verification_commands=verify_cmds,
        )

    elif source_name == "fixture":
        from spec_orch.services.fixture_issue_source import FixtureIssueSource

        return FixtureIssueSource(
            repo_root=repo_root,
            default_verification_commands=verify_cmds,
        )

    elif source_name in _ISSUE_SOURCE_REGISTRY:
        src_cfg = {k: v for k, v in issue_cfg.items() if k != "source"}
        src_cfg["verification_commands"] = verify_cmds
        instance: IssueSource = _ISSUE_SOURCE_REGISTRY[source_name](**src_cfg)
        return instance

    raise ValueError(f"Unknown issue source: {source_name!r}. Supported: fixture, linear")
