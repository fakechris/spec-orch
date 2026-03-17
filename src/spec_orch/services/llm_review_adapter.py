"""LLM-driven ReviewAdapter using litellm.

Reads the workspace diff + spec and asks an LLM to produce a code review.
Requires the ``planner`` extra: ``pip install spec-orch[planner]``.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.domain.compliance import default_turn_contract_compliance
from spec_orch.domain.models import ReviewSummary

logger = logging.getLogger(__name__)

_REVIEW_SYSTEM_PROMPT = """\
You are a senior code reviewer for the SpecOrch project.
You will receive a git diff and the issue spec. Your job is to:
1. Assess whether the changes correctly implement the spec.
2. Identify bugs, logic errors, missing edge cases, or regressions.
3. Return a JSON object with:
   - "verdict": "pass" | "changes_requested" | "uncertain"
   - "summary": a 1-3 sentence summary of your review
   - "issues": a list of objects with "severity" ("high"|"medium"|"low"),
     "file", "line" (optional), and "description"

Respond ONLY with the JSON object. No markdown fences, no extra text.\
"""

_MAX_DIFF_CHARS = 60_000
_MAX_SPEC_CHARS = 10_000


class LLMReviewAdapter:
    ADAPTER_NAME = "llm"
    VALID_VERDICTS = {"pass", "changes_requested", "uncertain"}

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        temperature: float = 0.2,
    ) -> None:
        self.model = model or "anthropic/claude-sonnet-4-20250514"
        self._api_key = api_key or os.environ.get("SPEC_ORCH_LLM_API_KEY")
        self.api_base = api_base or os.environ.get("SPEC_ORCH_LLM_API_BASE")
        self.temperature = temperature

    def initialize(
        self,
        *,
        issue_id: str,
        workspace: Path,
        builder_turn_contract_compliance: dict[str, Any] | None = None,
    ) -> ReviewSummary:
        diff = self._get_diff(workspace)
        spec = self._get_spec(workspace)

        if not diff.strip():
            summary = ReviewSummary(verdict="pass", reviewed_by="llm-reviewer")
            self._write_report(
                issue_id=issue_id,
                summary=summary,
                workspace=workspace,
                llm_response={"verdict": "pass", "summary": "No changes to review.", "issues": []},
                builder_turn_contract_compliance=builder_turn_contract_compliance,
            )
            return summary

        llm_result = self._call_llm(diff, spec, issue_id)
        verdict = llm_result.get("verdict", "uncertain")
        if verdict not in ("pass", "changes_requested", "uncertain"):
            verdict = "uncertain"

        summary = ReviewSummary(
            verdict=verdict,
            reviewed_by="llm-reviewer",
            report_path=workspace / "review_report.json",
        )
        self._write_report(
            issue_id=issue_id,
            summary=summary,
            workspace=workspace,
            llm_response=llm_result,
            builder_turn_contract_compliance=builder_turn_contract_compliance,
        )
        return summary

    def review(
        self,
        *,
        issue_id: str,
        workspace: Path,
        verdict: str,
        reviewed_by: str,
        builder_turn_contract_compliance: dict[str, Any] | None = None,
    ) -> ReviewSummary:
        if verdict not in self.VALID_VERDICTS:
            raise ValueError(f"invalid review verdict: {verdict}")
        summary = ReviewSummary(
            verdict=verdict,
            reviewed_by=reviewed_by,
            report_path=workspace / "review_report.json",
        )
        self._write_report(
            issue_id=issue_id,
            summary=summary,
            workspace=workspace,
            llm_response=None,
            builder_turn_contract_compliance=builder_turn_contract_compliance,
        )
        return summary

    def _get_diff(self, workspace: Path) -> str:
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=30,
            )
            diff = result.stdout
            if len(diff) > _MAX_DIFF_CHARS:
                diff = diff[:_MAX_DIFF_CHARS] + "\n... [truncated]"
            return diff
        except (subprocess.SubprocessError, FileNotFoundError):
            return ""

    def _get_spec(self, workspace: Path) -> str:
        spec_path = workspace / "task.spec.md"
        if not spec_path.exists():
            return ""
        text = spec_path.read_text()
        if len(text) > _MAX_SPEC_CHARS:
            text = text[:_MAX_SPEC_CHARS] + "\n... [truncated]"
        return text

    def _call_llm(self, diff: str, spec: str, issue_id: str) -> dict[str, Any]:
        try:
            import litellm
        except ImportError:
            logger.warning("litellm not installed; falling back to 'uncertain' verdict")
            return {"verdict": "uncertain", "summary": "LLM not available", "issues": []}

        user_msg = f"## Issue: {issue_id}\n\n"
        if spec:
            user_msg += f"## Spec\n\n{spec}\n\n"
        user_msg += f"## Diff\n\n```diff\n{diff}\n```"

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "temperature": self.temperature,
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base

        try:
            response = litellm.completion(**kwargs)
            choices = getattr(response, "choices", None) or []
            if not choices:
                return {"verdict": "uncertain", "summary": "Empty LLM response", "issues": []}
            message = getattr(choices[0], "message", None)
            content = (getattr(message, "content", None) or "") if message else ""
            if not content:
                return {"verdict": "uncertain", "summary": "Empty LLM content", "issues": []}
            parsed: dict[str, Any] = json.loads(content)
            return parsed
        except json.JSONDecodeError:
            logger.warning("LLM review response was not valid JSON")
            return {"verdict": "uncertain", "summary": content[:500], "issues": []}
        except Exception:
            logger.warning("LLM review call failed", exc_info=True)
            return {"verdict": "uncertain", "summary": "LLM call failed", "issues": []}

    def _write_report(
        self,
        *,
        issue_id: str,
        summary: ReviewSummary,
        workspace: Path,
        llm_response: dict[str, Any] | None,
        builder_turn_contract_compliance: dict[str, Any] | None,
    ) -> None:
        report_path = workspace / "review_report.json"
        summary.report_path = report_path
        report_path.write_text(
            json.dumps(
                {
                    "issue_id": issue_id,
                    "verdict": summary.verdict,
                    "reviewed_by": summary.reviewed_by,
                    "reviewed_at": datetime.now(UTC).isoformat(),
                    "llm_review": llm_response,
                    "builder_turn_contract_compliance": (
                        builder_turn_contract_compliance or default_turn_contract_compliance()
                    ),
                },
                indent=2,
            )
            + "\n"
        )
