"""GitHubReviewAdapter — pulls PR review comments via ``gh`` and maps to Findings."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from uuid import uuid4

from spec_orch.domain.models import Finding, ReviewMeta, ReviewSummary
from spec_orch.services.finding_store import append_finding, fingerprint_from


class GitHubReviewAdapter:
    """Fetches PR review comments and maps them to structured Findings.

    Supports reviews from CodeRabbit, Gemini, Devin, and human reviewers.
    """

    BOT_SEVERITY_PATTERNS: list[tuple[str, str]] = [
        (r"\[blocking\]", "blocking"),
        (r"\[critical\]", "blocking"),
        (r"\[major\]", "blocking"),
        (r"\[minor\]", "advisory"),
        (r"\[nit\]", "advisory"),
        (r"\[nitpick\]", "advisory"),
        (r"\[suggestion\]", "advisory"),
    ]

    def __init__(self, *, gh_executable: str = "gh") -> None:
        self._gh = gh_executable

    def fetch_pr_reviews(
        self, *, workspace: Path, pr_number: int | None = None,
    ) -> list[dict]:
        """Fetch all review comments for a PR."""
        pr = pr_number or self._detect_pr(workspace)
        if not pr:
            return []

        result = subprocess.run(
            [self._gh, "api", f"repos/{{owner}}/{{repo}}/pulls/{pr}/reviews"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        reviews = json.loads(result.stdout) if result.returncode == 0 else []

        result2 = subprocess.run(
            [self._gh, "api", f"repos/{{owner}}/{{repo}}/pulls/{pr}/comments"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        comments = json.loads(result2.stdout) if result2.returncode == 0 else []

        return reviews + comments

    def reviews_to_findings(
        self, reviews: list[dict], *, workspace: Path,
    ) -> list[Finding]:
        """Map raw review data to structured Finding objects."""
        findings: list[Finding] = []
        for item in reviews:
            body = item.get("body", "") or ""
            if not body.strip():
                continue

            user = item.get("user", {}).get("login", "unknown")
            source = self._classify_source(user)
            file_path = item.get("path")
            line = item.get("line") or item.get("original_line")

            severity = self._infer_severity(body, source, item)
            fp = fingerprint_from(source, body[:200], file_path, line)

            finding = Finding(
                id=f"f-{uuid4().hex[:8]}",
                source=source,
                severity=severity,
                confidence=0.8 if source != "human" else 1.0,
                scope="in_spec",
                fingerprint=fp,
                description=body[:500],
                file_path=file_path,
                line=line,
            )
            findings.append(finding)

        return findings

    def auto_review(
        self, *, workspace: Path, pr_number: int | None = None,
    ) -> tuple[ReviewSummary, ReviewMeta]:
        """Full auto-review: fetch → findings → verdict."""
        raw = self.fetch_pr_reviews(workspace=workspace, pr_number=pr_number)
        findings = self.reviews_to_findings(raw, workspace=workspace)

        for f in findings:
            append_finding(workspace, f)

        meta = ReviewMeta(findings=findings)
        blocking = meta.blocking_unresolved

        if not findings:
            verdict = "pass"
            reviewer = "auto:no-reviews"
        elif blocking:
            verdict = "changes_requested"
            reviewer = f"auto:{len(blocking)}-blocking"
        else:
            verdict = "pass"
            reviewer = f"auto:{len(findings)}-advisory-only"

        summary = ReviewSummary(
            verdict=verdict,
            reviewed_by=reviewer,
            report_path=workspace / "review_report.json",
        )
        return summary, meta

    def _detect_pr(self, workspace: Path) -> int | None:
        result = subprocess.run(
            [self._gh, "pr", "view", "--json", "number"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        try:
            return int(json.loads(result.stdout)["number"])
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    @staticmethod
    def _classify_source(username: str) -> str:
        lowered = username.lower()
        if "coderabbit" in lowered:
            return "coderabbit"
        if "devin" in lowered:
            return "devin"
        if "gemini" in lowered or "google" in lowered:
            return "gemini"
        if lowered in ("github-actions[bot]", "dependabot[bot]"):
            return "bot"
        return "human"

    def _infer_severity(
        self, body: str, source: str, raw: dict,
    ) -> str:
        lowered = body.lower()
        for pattern, sev in self.BOT_SEVERITY_PATTERNS:
            if re.search(pattern, lowered):
                return sev

        state = raw.get("state", "").upper()
        if state == "CHANGES_REQUESTED":
            return "blocking"
        if state == "APPROVED":
            return "advisory"

        if source in ("coderabbit", "devin", "gemini"):
            if any(w in lowered for w in ("bug", "error", "crash", "security", "vulnerability")):
                return "blocking"
            return "advisory"

        return "advisory"
