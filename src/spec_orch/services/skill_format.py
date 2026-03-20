"""Skill format definition and validation (P4 — format only, no runtime).

A SpecOrch skill is a declarative YAML/JSON file that describes a reusable
capability: gate checks, evolver strategies, review lenses, builder hooks, etc.

This module defines the canonical schema, loads skill manifests from
`.spec_orch/skills/` or a configurable directory, and validates them.
It does NOT execute skills — that belongs to a future Skill Runtime.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

SKILL_SCHEMA_VERSION = "1.0"

VALID_KINDS = frozenset(
    {
        "gate_check",
        "evolver",
        "review_lens",
        "builder_hook",
        "readiness_rule",
        "reaction",
        "custom",
    }
)


@dataclass(slots=True)
class SkillManifest:
    """Parsed skill manifest."""

    id: str
    name: str
    kind: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    schema_version: str = SKILL_SCHEMA_VERSION
    triggers: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    source_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "triggers": self.triggers,
            "params": self.params,
        }


def validate_skill_manifest(data: dict[str, Any]) -> list[str]:
    """Validate a raw dict against skill manifest schema; return issues."""
    issues: list[str] = []
    for required in ("id", "name", "kind"):
        val = data.get(required)
        if not val or not isinstance(val, str) or not val.strip():
            issues.append(f"missing or empty required field: {required}")

    kind = str(data.get("kind", "")).strip()
    if kind and kind not in VALID_KINDS:
        issues.append(f"unknown kind {kind!r}; expected one of {sorted(VALID_KINDS)}")

    triggers = data.get("triggers")
    if triggers is not None and not isinstance(triggers, list):
        issues.append("triggers must be a list of strings")

    params = data.get("params")
    if params is not None and not isinstance(params, dict):
        issues.append("params must be a mapping")

    sv = data.get("schema_version", SKILL_SCHEMA_VERSION)
    if sv != SKILL_SCHEMA_VERSION:
        issues.append(f"unsupported schema_version {sv!r}; expected {SKILL_SCHEMA_VERSION!r}")

    return issues


def parse_skill_manifest(
    data: dict[str, Any], *, source_path: str = ""
) -> tuple[SkillManifest | None, list[str]]:
    """Parse and validate a skill manifest dict."""
    issues = validate_skill_manifest(data)
    if any("missing or empty required" in i for i in issues):
        return None, issues

    manifest = SkillManifest(
        id=str(data["id"]).strip(),
        name=str(data["name"]).strip(),
        kind=str(data["kind"]).strip(),
        version=str(data.get("version", "0.1.0")).strip(),
        description=str(data.get("description", "")).strip(),
        author=str(data.get("author", "")).strip(),
        schema_version=str(data.get("schema_version", SKILL_SCHEMA_VERSION)),
        triggers=_str_list(data.get("triggers", [])),
        params=dict(data.get("params", {})) if isinstance(data.get("params"), dict) else {},
        source_path=source_path,
    )
    return manifest, issues


def load_skills_from_dir(skills_dir: Path) -> tuple[list[SkillManifest], list[str]]:
    """Load all skill manifests from a directory (*.yaml / *.yml / *.json)."""
    manifests: list[SkillManifest] = []
    all_warnings: list[str] = []

    if not skills_dir.is_dir():
        return manifests, []

    import json

    for ext in ("*.yaml", "*.yml", "*.json"):
        for p in sorted(skills_dir.glob(ext)):
            try:
                raw_text = p.read_text(encoding="utf-8")
                if p.suffix == ".json":
                    data = json.loads(raw_text)
                else:
                    data = yaml.safe_load(raw_text) or {}
            except (yaml.YAMLError, json.JSONDecodeError, OSError) as exc:
                all_warnings.append(f"{p.name}: parse error — {exc}")
                continue

            if not isinstance(data, dict):
                all_warnings.append(f"{p.name}: root must be a mapping")
                continue

            m, errs = parse_skill_manifest(data, source_path=str(p))
            for e in errs:
                all_warnings.append(f"{p.name}: {e}")
            if m is not None:
                manifests.append(m)

    return manifests, all_warnings


def default_skills_dir(repo_root: Path) -> Path:
    return repo_root / ".spec_orch" / "skills"


def _str_list(val: Any) -> list[str]:
    if not isinstance(val, list):
        return []
    return [str(v) for v in val if v is not None]
