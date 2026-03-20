"""Unit tests for skill format validation and loading (P4)."""

from __future__ import annotations

import json
from pathlib import Path

from spec_orch.services.skill_format import (
    SKILL_SCHEMA_VERSION,
    SkillManifest,
    load_skills_from_dir,
    parse_skill_manifest,
    validate_skill_manifest,
)


def test_validate_minimal_valid() -> None:
    issues = validate_skill_manifest({"id": "x", "name": "X", "kind": "gate_check"})
    assert issues == []


def test_validate_missing_required() -> None:
    issues = validate_skill_manifest({"id": "x"})
    assert any("name" in i for i in issues)
    assert any("kind" in i for i in issues)


def test_validate_unknown_kind() -> None:
    issues = validate_skill_manifest({"id": "x", "name": "X", "kind": "unknown_thing"})
    assert any("unknown kind" in i for i in issues)


def test_validate_bad_triggers_type() -> None:
    issues = validate_skill_manifest(
        {"id": "x", "name": "X", "kind": "custom", "triggers": "not_a_list"}
    )
    assert any("triggers must be a list" in i for i in issues)


def test_validate_bad_params_type() -> None:
    issues = validate_skill_manifest({"id": "x", "name": "X", "kind": "custom", "params": [1, 2]})
    assert any("params must be a mapping" in i for i in issues)


def test_parse_valid_manifest() -> None:
    data = {
        "id": "my-skill",
        "name": "My Skill",
        "kind": "evolver",
        "version": "1.0.0",
        "description": "Does cool stuff",
        "triggers": ["evolution"],
        "params": {"key": "val"},
    }
    m, errs = parse_skill_manifest(data)
    assert m is not None
    assert m.id == "my-skill"
    assert m.kind == "evolver"
    assert m.params == {"key": "val"}
    assert errs == []


def test_parse_missing_id_returns_none() -> None:
    m, errs = parse_skill_manifest({"name": "X", "kind": "custom"})
    assert m is None
    assert any("id" in e for e in errs)


def test_load_skills_from_dir_yaml(tmp_path: Path) -> None:
    d = tmp_path / "skills"
    d.mkdir()
    (d / "a.yaml").write_text("id: a\nname: A\nkind: gate_check\n")
    (d / "b.yml").write_text("id: b\nname: B\nkind: reaction\nparams:\n  merge_method: squash\n")
    manifests, warnings = load_skills_from_dir(d)
    assert len(manifests) == 2
    assert {m.id for m in manifests} == {"a", "b"}
    assert warnings == []


def test_load_skills_from_dir_json(tmp_path: Path) -> None:
    d = tmp_path / "skills"
    d.mkdir()
    (d / "c.json").write_text(json.dumps({"id": "c", "name": "C", "kind": "custom"}))
    manifests, warnings = load_skills_from_dir(d)
    assert len(manifests) == 1
    assert manifests[0].id == "c"


def test_load_skills_warns_on_bad_file(tmp_path: Path) -> None:
    d = tmp_path / "skills"
    d.mkdir()
    (d / "bad.yaml").write_text("{{{{invalid yaml")
    manifests, warnings = load_skills_from_dir(d)
    assert manifests == []
    assert any("parse error" in w for w in warnings)


def test_load_skills_warns_on_unknown_kind(tmp_path: Path) -> None:
    d = tmp_path / "skills"
    d.mkdir()
    (d / "unk.yaml").write_text("id: u\nname: U\nkind: banana\n")
    manifests, warnings = load_skills_from_dir(d)
    assert len(manifests) == 1
    assert any("unknown kind" in w for w in warnings)


def test_manifest_roundtrip() -> None:
    m = SkillManifest(
        id="rt",
        name="Roundtrip",
        kind="builder_hook",
        version="2.0.0",
        description="desc",
        triggers=["builder.output"],
        params={"a": 1},
    )
    d = m.to_dict()
    assert d["schema_version"] == SKILL_SCHEMA_VERSION
    assert d["id"] == "rt"
    assert d["params"]["a"] == 1


def test_load_empty_dir(tmp_path: Path) -> None:
    d = tmp_path / "no_skills"
    manifests, warnings = load_skills_from_dir(d)
    assert manifests == []
    assert warnings == []
