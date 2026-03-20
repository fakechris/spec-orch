"""Tests for Epic H: Multi-Agent hallucination guard."""

from __future__ import annotations

import json
from pathlib import Path

from spec_orch.services.llm_review_adapter import LLMReviewAdapter


class TestVerifyOutcomes:
    def test_workspace_is_git_repo_check(self, tmp_path: Path) -> None:
        checks = LLMReviewAdapter.verify_outcomes(tmp_path)
        git_check = next(c for c in checks if c["name"] == "workspace_is_git_repo")
        assert not git_check["passed"]

        (tmp_path / ".git").mkdir()
        checks2 = LLMReviewAdapter.verify_outcomes(tmp_path)
        git_check2 = next(c for c in checks2 if c["name"] == "workspace_is_git_repo")
        assert git_check2["passed"]

    def test_mergeable_consistency_check(self, tmp_path: Path) -> None:
        artifact_dir = tmp_path / "run_artifact"
        artifact_dir.mkdir()
        (artifact_dir / "conclusion.json").write_text(json.dumps({"mergeable": True}))
        (tmp_path / "report.json").write_text(json.dumps({"mergeable": False}))
        checks = LLMReviewAdapter.verify_outcomes(tmp_path)
        consistency = next(c for c in checks if c["name"] == "mergeable_consistency")
        assert not consistency["passed"]
        assert "True" in consistency["detail"]
        assert "False" in consistency["detail"]

    def test_verification_all_pass(self, tmp_path: Path) -> None:
        (tmp_path / "report.json").write_text(
            json.dumps(
                {
                    "verification": {
                        "test": {"exit_code": 0},
                        "lint": {"exit_code": 0},
                    }
                }
            )
        )
        checks = LLMReviewAdapter.verify_outcomes(tmp_path)
        vcheck = next(c for c in checks if c["name"] == "verification_all_pass")
        assert vcheck["passed"]

    def test_verification_has_failure(self, tmp_path: Path) -> None:
        (tmp_path / "report.json").write_text(
            json.dumps(
                {
                    "verification": {
                        "test": {"exit_code": 1},
                        "lint": {"exit_code": 0},
                    }
                }
            )
        )
        checks = LLMReviewAdapter.verify_outcomes(tmp_path)
        vcheck = next(c for c in checks if c["name"] == "verification_all_pass")
        assert not vcheck["passed"]
