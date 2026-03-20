"""Tests for KnowledgeDistiller (R5)."""

from __future__ import annotations

import json
from pathlib import Path

from spec_orch.services.knowledge_distiller import KnowledgeDistiller


def test_distill_empty_repo(tmp_path: Path) -> None:
    distiller = KnowledgeDistiller(tmp_path)
    content = distiller.distill()
    assert "spec-orch Knowledge Base" in content
    assert "Auto-generated" in content


def test_write_creates_file(tmp_path: Path) -> None:
    distiller = KnowledgeDistiller(tmp_path)
    path = distiller.write()
    assert path.exists()
    assert path.name == "knowledge.md"
    text = path.read_text(encoding="utf-8")
    assert "Knowledge Base" in text


def test_distill_scoper_hints(tmp_path: Path) -> None:
    hints = {"hints": [{"text": "Prefer interfaces over classes", "confidence": 0.9}]}
    (tmp_path / "scoper_hints.json").write_text(json.dumps(hints))
    distiller = KnowledgeDistiller(tmp_path)
    content = distiller.distill()
    assert "Scoper Hints" in content
    assert "Prefer interfaces over classes" in content


def test_distill_prompt_history(tmp_path: Path) -> None:
    data = {
        "variants": [{"variant_id": "v1", "success_rate": 0.85}],
        "active_variant": "v1",
    }
    (tmp_path / "prompt_history.json").write_text(json.dumps(data))
    distiller = KnowledgeDistiller(tmp_path)
    content = distiller.distill()
    assert "Builder Prompt Variants" in content
    assert "v1" in content


def test_distill_evolution_log(tmp_path: Path) -> None:
    evo_dir = tmp_path / ".spec_orch_evolution"
    evo_dir.mkdir(parents=True)
    entry = {"timestamp": "2026-03-18T10:00:00Z", "evolvers_triggered": ["prompt", "gate"]}
    (evo_dir / "evolution_log.jsonl").write_text(json.dumps(entry) + "\n")
    distiller = KnowledgeDistiller(tmp_path)
    content = distiller.distill()
    assert "Evolution History" in content
    assert "prompt, gate" in content


def test_distill_policies(tmp_path: Path) -> None:
    data = [{"policy_id": "no-secrets", "description": "No API keys in code"}]
    (tmp_path / "policies_index.json").write_text(json.dumps(data))
    distiller = KnowledgeDistiller(tmp_path)
    content = distiller.distill()
    assert "Distilled Policies" in content
    assert "no-secrets" in content


def test_custom_output_path(tmp_path: Path) -> None:
    distiller = KnowledgeDistiller(tmp_path)
    custom = tmp_path / "custom" / "output.md"
    path = distiller.write(output_path=custom)
    assert path == custom
    assert custom.exists()
