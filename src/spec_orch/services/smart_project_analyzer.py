"""LLM-driven project analysis for spec-orch init.

Reads the project's file tree and configuration files, then asks an LLM
to determine the optimal verification commands and toolchain.  Falls back
to rule-based detection (``project_detector.detect_project``) when no
LLM API key is available or the call fails.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
from pathlib import Path
from typing import Any

from spec_orch.services.project_detector import (
    ProjectProfile,
    _detect_base_branch,
    _detect_framework,
    detect_project,
)

logger = logging.getLogger(__name__)

_ANALYZE_SYSTEM_PROMPT = """\
You are a build-system expert.  Given a project's file tree and the content
of key configuration files, determine the best verification commands.

Return a JSON object with these keys:
- "languages": list of detected languages (e.g. ["python", "typescript"])
- "framework": primary framework or null (e.g. "nextjs", "fastapi", null)
- "verification": object mapping step names to command arrays.
  Standard steps are "lint", "typecheck", "test", "build", but you MAY
  add extras like "security_scan", "e2e", "format_check" if the project
  clearly uses them.  Use the project's OWN scripts/tasks when available
  (e.g. "npm run lint" over raw "npx eslint ."; "make test" over raw
  "pytest").  Use {python} as a placeholder for the Python interpreter.
- "notes": short free-text explanation of your choices (1-3 sentences)

Respond ONLY with the JSON object. No markdown fences.\
"""

_CONFIG_FILES_TO_READ = [
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "Makefile",
    "Justfile",
    "Taskfile.yml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    ".github/workflows/ci.yml",
    ".github/workflows/ci.yaml",
    ".github/workflows/test.yml",
    ".github/workflows/test.yaml",
    "tox.ini",
    ".pre-commit-config.yaml",
    "biome.json",
    ".eslintrc.json",
    ".eslintrc.js",
    "tsconfig.json",
]

_MAX_FILE_CHARS = 3000
_MAX_TREE_DEPTH = 2


def _gather_context(root: Path) -> str:
    """Collect file tree + key config file contents for LLM analysis."""
    parts: list[str] = []

    parts.append("## File Tree (depth 2)\n")
    parts.append(_file_tree(root, max_depth=_MAX_TREE_DEPTH))

    parts.append("\n## Configuration Files\n")
    for rel in _CONFIG_FILES_TO_READ:
        fpath = root / rel
        if fpath.exists() and fpath.is_file():
            try:
                content = fpath.read_text(errors="replace")
                if len(content) > _MAX_FILE_CHARS:
                    content = content[:_MAX_FILE_CHARS] + "\n... [truncated]"
                parts.append(f"### {rel}\n```\n{content}\n```\n")
            except Exception:
                logger.debug("Could not read config file %s", rel, exc_info=True)

    return "\n".join(parts)


def _file_tree(root: Path, max_depth: int = 2) -> str:
    """Generate a compact file tree string."""
    lines: list[str] = []
    _walk_tree(root, root, 0, max_depth, lines)
    return "\n".join(lines[:200])


def _walk_tree(
    base: Path, current: Path, depth: int, max_depth: int, lines: list[str]
) -> None:
    if depth > max_depth:
        return
    skip_dirs = {
        ".git", "node_modules", "__pycache__", ".venv", "venv",
        ".tox", ".mypy_cache", ".ruff_cache", "dist", "build",
        ".worktrees", ".spec_orch_runs", ".spec_orch_evolution",
    }
    try:
        entries = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name))
    except PermissionError:
        return
    for entry in entries:
        if entry.name in skip_dirs:
            continue
        rel = entry.relative_to(base)
        prefix = "  " * depth
        if entry.is_dir():
            lines.append(f"{prefix}{rel}/")
            _walk_tree(base, entry, depth + 1, max_depth, lines)
        else:
            lines.append(f"{prefix}{rel}")


def analyze_project_with_llm(
    root: Path,
    *,
    model: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
) -> ProjectProfile | None:
    """Use an LLM to analyze the project and generate a ProjectProfile.

    Returns None if the LLM is unavailable or the call fails, allowing
    the caller to fall back to rule-based detection.
    """
    try:
        import litellm
    except ImportError:
        logger.info("litellm not installed; falling back to rule-based detection")
        return None

    resolved_key = api_key or os.environ.get("SPEC_ORCH_LLM_API_KEY")
    if not resolved_key:
        logger.info("No LLM API key available; falling back to rule-based detection")
        return None

    context = _gather_context(root)
    _default_model = "anthropic/claude-sonnet-4-20250514"
    resolved_model = model or os.environ.get("SPEC_ORCH_INIT_MODEL", _default_model)
    resolved_base = api_base or os.environ.get("SPEC_ORCH_LLM_API_BASE")

    kwargs: dict[str, Any] = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": _ANALYZE_SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ],
        "temperature": 0.1,
        "api_key": resolved_key,
    }
    if resolved_base:
        kwargs["api_base"] = resolved_base

    try:
        response = litellm.completion(**kwargs)
        choices = getattr(response, "choices", None) or []
        if not choices:
            logger.warning("LLM returned empty response")
            return None
        message = getattr(choices[0], "message", None)
        content = (getattr(message, "content", None) or "") if message else ""
        if not content:
            logger.warning("LLM returned empty content")
            return None

        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]

        parsed: dict[str, Any] = json.loads(content)
        return _parse_llm_result(parsed, root)

    except json.JSONDecodeError:
        logger.warning("LLM response was not valid JSON: %s", content[:200])
        return None
    except Exception:
        logger.warning("LLM project analysis failed", exc_info=True)
        return None


def _parse_llm_result(data: dict[str, Any], root: Path) -> ProjectProfile:
    """Convert the LLM JSON response into a ProjectProfile."""
    languages = data.get("languages", [])
    language = languages[0] if languages else "unknown"

    framework = data.get("framework")
    if not framework:
        framework = _detect_framework(root)

    verification: dict[str, list[str]] = {}
    raw_verify = data.get("verification", {})
    for step_name, cmd in raw_verify.items():
        if isinstance(cmd, list):
            verification[step_name] = [str(c) for c in cmd]
        elif isinstance(cmd, str):
            verification[step_name] = shlex.split(cmd)

    notes = data.get("notes", "")
    if len(languages) > 1:
        notes = f"Multi-language project: {', '.join(languages)}. {notes}"

    return ProjectProfile(
        language=language,
        framework=framework,
        verification=verification,
        extra_notes=notes,
        base_branch=_detect_base_branch(root),
    )


def smart_detect_project(
    root: Path,
    *,
    offline: bool = False,
    model: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
) -> tuple[ProjectProfile, str]:
    """Detect project type, preferring LLM analysis over rules.

    Returns (profile, method) where method is "llm" or "rules".
    """
    if not offline:
        profile = analyze_project_with_llm(
            root, model=model, api_key=api_key, api_base=api_base
        )
        if profile is not None:
            return profile, "llm"

    return detect_project(root), "rules"
