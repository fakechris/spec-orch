"""Tests for GitHubReviewAdapter — review comment mapping to Findings."""

from __future__ import annotations

from pathlib import Path

import pytest

from spec_orch.services.github_review_adapter import GitHubReviewAdapter


@pytest.fixture()
def adapter() -> GitHubReviewAdapter:
    return GitHubReviewAdapter()


class TestClassifySource:
    def test_coderabbit(self, adapter: GitHubReviewAdapter) -> None:
        assert adapter._classify_source("coderabbitai[bot]") == "coderabbit"

    def test_devin(self, adapter: GitHubReviewAdapter) -> None:
        assert adapter._classify_source("devin-ai[bot]") == "devin"

    def test_gemini(self, adapter: GitHubReviewAdapter) -> None:
        assert adapter._classify_source("gemini-code-review") == "gemini"

    def test_human(self, adapter: GitHubReviewAdapter) -> None:
        assert adapter._classify_source("fakechris") == "human"


class TestInferSeverity:
    def test_blocking_tag(self, adapter: GitHubReviewAdapter) -> None:
        assert adapter._infer_severity("[blocking] Fix this", "coderabbit", {}) == "blocking"

    def test_nit_tag(self, adapter: GitHubReviewAdapter) -> None:
        assert adapter._infer_severity("[nit] minor style", "coderabbit", {}) == "advisory"

    def test_changes_requested_state(self, adapter: GitHubReviewAdapter) -> None:
        assert adapter._infer_severity("Fix bugs", "human", {"state": "CHANGES_REQUESTED"}) == "blocking"

    def test_approved_state(self, adapter: GitHubReviewAdapter) -> None:
        assert adapter._infer_severity("LGTM", "human", {"state": "APPROVED"}) == "advisory"

    def test_bot_bug_keyword(self, adapter: GitHubReviewAdapter) -> None:
        assert adapter._infer_severity("This has a bug in the loop", "coderabbit", {}) == "blocking"

    def test_bot_default(self, adapter: GitHubReviewAdapter) -> None:
        assert adapter._infer_severity("Consider renaming", "devin", {}) == "advisory"


class TestReviewsToFindings:
    def test_basic_mapping(self, adapter: GitHubReviewAdapter, tmp_path: Path) -> None:
        reviews = [
            {
                "body": "[nit] rename this variable",
                "user": {"login": "coderabbitai[bot]"},
                "path": "src/foo.py",
                "line": 42,
            },
            {
                "body": "[blocking] security vulnerability in auth",
                "user": {"login": "gemini-review"},
                "path": "src/auth.py",
                "line": 10,
            },
        ]
        findings = adapter.reviews_to_findings(reviews, workspace=tmp_path)
        assert len(findings) == 2
        assert findings[0].severity == "advisory"
        assert findings[0].source == "coderabbit"
        assert findings[1].severity == "blocking"
        assert findings[1].source == "gemini"

    def test_empty_body_skipped(self, adapter: GitHubReviewAdapter, tmp_path: Path) -> None:
        reviews = [{"body": "", "user": {"login": "bot"}}]
        assert adapter.reviews_to_findings(reviews, workspace=tmp_path) == []

    def test_no_reviews_pass(self, adapter: GitHubReviewAdapter, tmp_path: Path) -> None:
        summary, meta = adapter.auto_review(workspace=tmp_path)
        assert summary.verdict == "pass"
        assert meta.findings == []
