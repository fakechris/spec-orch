"""Tests for memory migration helpers."""

import json
from pathlib import Path

import pytest

from spec_orch.services.memory.fs_provider import FileSystemMemoryProvider
from spec_orch.services.memory.migration import (
    import_all,
    import_policies,
    import_prompt_history,
    import_run_reports,
    import_scoper_hints,
)
from spec_orch.services.memory.types import MemoryLayer


@pytest.fixture()
def provider(tmp_path: Path) -> FileSystemMemoryProvider:
    return FileSystemMemoryProvider(tmp_path / "memory")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


class TestImportPromptHistory:
    def test_no_file(self, provider, repo):
        assert import_prompt_history(provider, repo) == 0

    def test_imports_variants(self, provider, repo):
        data = [
            {
                "variant_id": "v0",
                "prompt_text": "Build this feature",
                "created_at": "2026-01-01T00:00:00Z",
                "rationale": "baseline",
                "total_runs": 10,
                "successful_runs": 8,
                "is_active": True,
                "is_candidate": False,
            },
            {
                "variant_id": "v1",
                "prompt_text": "Build it better",
                "total_runs": 5,
                "successful_runs": 4,
                "is_active": False,
                "is_candidate": True,
            },
        ]
        (repo / "prompt_history.json").write_text(json.dumps(data))
        count = import_prompt_history(provider, repo)
        assert count == 2

        entry = provider.get("prompt-variant-v0")
        assert entry is not None
        assert entry.layer == MemoryLayer.PROCEDURAL
        assert "active" in entry.tags
        assert entry.metadata["is_active"] is True

    def test_idempotent(self, provider, repo):
        data = [{"variant_id": "v0", "prompt_text": "text"}]
        (repo / "prompt_history.json").write_text(json.dumps(data))
        import_prompt_history(provider, repo)
        import_prompt_history(provider, repo)
        keys = provider.list_keys(layer="procedural")
        assert len(keys) == 1


class TestImportScoperHints:
    def test_imports_hints(self, provider, repo):
        data = {
            "hints": [
                {
                    "hint_id": "h1",
                    "text": "Focus on error handling",
                    "confidence": "high",
                    "is_active": True,
                }
            ],
            "analysis_summary": "Overall good quality",
            "generated_at": "2026-03-01T00:00:00Z",
        }
        (repo / "scoper_hints.json").write_text(json.dumps(data))
        count = import_scoper_hints(provider, repo)
        assert count == 2  # 1 hint + 1 summary

        entry = provider.get("scoper-hint-h1")
        assert entry is not None
        assert entry.layer == MemoryLayer.SEMANTIC
        assert "active" in entry.tags

        summary = provider.get("scoper-analysis-summary")
        assert summary is not None
        assert "Overall good quality" in summary.content


class TestImportRunReports:
    def test_imports_reports(self, provider, repo):
        run_dir = repo / ".spec_orch_runs" / "SON-50"
        run_dir.mkdir(parents=True)
        report = {
            "state": "gate_evaluated",
            "issue_id": "SON-50",
            "run_id": "run-1",
            "mergeable": True,
            "builder": {"succeeded": True, "adapter": "codex_exec"},
            "verification": {"lint": {"exit_code": 0}, "test": {"exit_code": 0}},
            "review": {"verdict": "approved"},
        }
        (run_dir / "report.json").write_text(json.dumps(report))
        count = import_run_reports(provider, repo)
        assert count == 1

        entry = provider.get("run-report-SON-50-run-1")
        assert entry is not None
        assert entry.layer == MemoryLayer.EPISODIC
        assert "succeeded" in entry.tags

    def test_imports_deviations(self, provider, repo):
        run_dir = repo / ".spec_orch_runs" / "SON-51"
        run_dir.mkdir(parents=True)
        (run_dir / "report.json").write_text(
            json.dumps({"issue_id": "SON-51", "run_id": "r2", "mergeable": False})
        )
        (run_dir / "deviations.jsonl").write_text(
            '{"severity": "medium", "description": "Wrong import"}\n'
        )
        count = import_run_reports(provider, repo)
        assert count == 1
        entry = provider.get("run-report-SON-51-r2")
        assert entry is not None
        assert "failed" in entry.tags
        assert entry.metadata["deviation_count"] == 1

    def test_imports_unified_artifacts_without_legacy_report(self, provider, repo):
        run_dir = repo / ".spec_orch_runs" / "SON-52"
        (run_dir / "run_artifact").mkdir(parents=True)
        (run_dir / "run_artifact" / "conclusion.json").write_text(
            json.dumps(
                {
                    "issue_id": "SON-52",
                    "run_id": "r3",
                    "state": "gate_evaluated",
                    "mergeable": True,
                    "failed_conditions": [],
                }
            )
        )
        (run_dir / "run_artifact" / "live.json").write_text(
            json.dumps(
                {
                    "builder": {"succeeded": True, "adapter": "codex_exec"},
                    "verification": {"lint": {"exit_code": 0}},
                    "review": {"verdict": "pass"},
                }
            )
        )

        count = import_run_reports(provider, repo)
        assert count == 1
        entry = provider.get("run-report-SON-52-r3")
        assert entry is not None
        assert "succeeded" in entry.tags
        assert entry.metadata["builder_adapter"] == "codex_exec"
        assert entry.metadata["review_verdict"] == "pass"
        assert entry.metadata["source_path"].endswith("run_artifact/conclusion.json")


class TestImportPolicies:
    def test_imports_policies(self, provider, repo):
        policies = [
            {
                "policy_id": "pol-1",
                "name": "Auto-fix lint",
                "description": "Runs ruff fix automatically",
                "trigger_patterns": ["lint_failure"],
                "is_active": True,
            }
        ]
        (repo / "policies_index.json").write_text(json.dumps(policies))
        (repo / "policies").mkdir()
        (repo / "policies" / "pol-1.py").write_text("print('fix')")

        count = import_policies(provider, repo)
        assert count == 1

        entry = provider.get("policy-pol-1")
        assert entry is not None
        assert entry.layer == MemoryLayer.PROCEDURAL
        assert "print('fix')" in entry.content


class TestImportAll:
    def test_returns_counts(self, provider, repo):
        (repo / "prompt_history.json").write_text("[]")
        (repo / "scoper_hints.json").write_text('{"hints": []}')
        counts = import_all(provider, repo)
        assert "prompt_variants" in counts
        assert "scoper_hints" in counts
        assert "run_reports" in counts
        assert "policies" in counts
