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
from spec_orch.domain.models import Issue, IssueContext, ReviewSummary
from spec_orch.services.context_assembler import ContextAssembler
from spec_orch.services.node_context_registry import get_node_context_spec

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
        max_diff_chars: int = 60_000,
        max_spec_chars: int = 10_000,
    ) -> None:
        self.model = model or "anthropic/claude-sonnet-4-20250514"
        self._api_key = api_key or os.environ.get("SPEC_ORCH_LLM_API_KEY")
        self.api_base = api_base or os.environ.get("SPEC_ORCH_LLM_API_BASE")
        self.temperature = temperature
        self.max_diff_chars = max_diff_chars
        self.max_spec_chars = max_spec_chars
        self._context_assembler = ContextAssembler()

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

        context_bundle = self._build_context_bundle(issue_id=issue_id, workspace=workspace)
        extra_context = (
            self._render_context_bundle(context_bundle)
            if context_bundle is not None
            else self._collect_extra_context(workspace)
        )
        llm_result = self._call_llm(diff, spec, issue_id, extra_context=extra_context)
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
            if len(diff) > self.max_diff_chars:
                diff = diff[: self.max_diff_chars] + "\n... [truncated]"
            return diff
        except (subprocess.SubprocessError, FileNotFoundError):
            return ""

    def _get_spec(self, workspace: Path) -> str:
        spec_path = workspace / "task.spec.md"
        if not spec_path.exists():
            return ""
        text = spec_path.read_text()
        if len(text) > self.max_spec_chars:
            text = text[: self.max_spec_chars] + "\n... [truncated]"
        return text

    @staticmethod
    def _collect_extra_context(workspace: Path) -> str:
        """Gather verification, gate, and acceptance criteria for richer review."""
        parts: list[str] = []

        report_path = workspace / "report.json"
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text())
                verification = report.get("verification", {})
                if verification:
                    lines = []
                    for name, detail in verification.items():
                        if isinstance(detail, dict):
                            status = "pass" if detail.get("exit_code") == 0 else "FAIL"
                            lines.append(f"  - {name}: {status}")
                    if lines:
                        parts.append("## Verification Results (previous run)\n" + "\n".join(lines))

                failed = report.get("failed_conditions", [])
                mergeable = report.get("mergeable", False)
                if failed or not mergeable:
                    parts.append(
                        f"## Gate Status (previous run)\n"
                        f"mergeable={mergeable}, failed_conditions={failed}"
                    )
            except (json.JSONDecodeError, KeyError):
                pass

        for manifest_path in (
            workspace / "run_artifact" / "manifest.json",
            workspace / "artifact_manifest.json",
        ):
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text())
                    parts.append(f"## Run ID\n{manifest.get('run_id', 'unknown')}")
                    break
                except (json.JSONDecodeError, KeyError):
                    continue

        spec_snap_path = workspace / "spec_snapshot.json"
        if spec_snap_path.exists():
            try:
                snap = json.loads(spec_snap_path.read_text())
                criteria = snap.get("issue", {}).get("acceptance_criteria", [])
                if criteria:
                    items = "\n".join(f"- {c}" for c in criteria)
                    parts.append(f"## Acceptance Criteria\n{items}")
            except (json.JSONDecodeError, KeyError):
                pass

        return "\n\n".join(parts)

    def _build_context_bundle(self, *, issue_id: str, workspace: Path) -> Any | None:
        """Build ContextBundle for llm reviewer; fallback to legacy context on errors."""
        issue = self._issue_from_workspace(issue_id=issue_id, workspace=workspace)
        try:
            return self._context_assembler.assemble(
                get_node_context_spec("llm_reviewer"),
                issue,
                workspace,
            )
        except Exception:
            logger.debug("Failed to assemble review ContextBundle", exc_info=True)
            return None

    @staticmethod
    def _issue_from_workspace(*, issue_id: str, workspace: Path) -> Issue:
        summary = ""
        acceptance_criteria: list[str] = []
        constraints: list[str] = []
        title = issue_id

        spec_snap_path = workspace / "spec_snapshot.json"
        if spec_snap_path.exists():
            try:
                snap = json.loads(spec_snap_path.read_text())
                issue_data = snap.get("issue", {})
                title = issue_data.get("title", title) or title
                summary = issue_data.get("summary") or issue_data.get("intent") or ""
                criteria = issue_data.get("acceptance_criteria", [])
                if isinstance(criteria, list):
                    acceptance_criteria = [str(c) for c in criteria]
                cts = issue_data.get("context", {}).get("constraints", [])
                if isinstance(cts, list):
                    constraints = [str(c) for c in cts]
            except (json.JSONDecodeError, KeyError):
                pass

        return Issue(
            issue_id=issue_id,
            title=title,
            summary=summary,
            context=IssueContext(constraints=constraints),
            acceptance_criteria=acceptance_criteria,
        )

    @staticmethod
    def _render_context_bundle(context_bundle: Any) -> str:
        """Render ContextBundle into review prompt-friendly markdown."""
        parts: list[str] = []
        task = getattr(context_bundle, "task", None)
        execution = getattr(context_bundle, "execution", None)
        learning = getattr(context_bundle, "learning", None)

        if task:
            if getattr(task, "acceptance_criteria", []):
                lines = "\n".join(f"- {c}" for c in task.acceptance_criteria)
                parts.append(f"## Acceptance Criteria\n{lines}")
            if getattr(task, "constraints", []):
                lines = "\n".join(f"- {c}" for c in task.constraints)
                parts.append(f"## Constraints\n{lines}")

        if execution:
            vr = getattr(execution, "verification_results", None)
            if vr:
                verification_lines: list[str] = []
                details = getattr(vr, "details", {})
                for name, detail in details.items():
                    exit_code = getattr(detail, "exit_code", -1)
                    status = "pass" if exit_code == 0 else "FAIL"
                    verification_lines.append(f"  - {name}: {status}")
                if verification_lines:
                    parts.append(
                        "## Verification Results (previous run)\n" + "\n".join(verification_lines)
                    )

            gate = getattr(execution, "gate_report", None)
            if gate is not None:
                mergeable = getattr(gate, "mergeable", False)
                failed_conditions = getattr(gate, "failed_conditions", [])
                parts.append(
                    "## Gate Status (previous run)\n"
                    f"mergeable={mergeable}, failed_conditions={failed_conditions}"
                )

        if learning and getattr(learning, "similar_failure_samples", []):
            failure_lines: list[str] = []
            for s in learning.similar_failure_samples[:3]:
                failure_lines.append(f"- {s.get('key', '?')}: {s.get('content', '')[:200]}")
            if failure_lines:
                parts.append("## Recent Failure Samples\n" + "\n".join(failure_lines))

        return "\n\n".join(parts)

    def _call_llm(
        self, diff: str, spec: str, issue_id: str, *, extra_context: str = ""
    ) -> dict[str, Any]:
        try:
            import litellm
        except ImportError:
            logger.warning("litellm not installed; falling back to 'uncertain' verdict")
            return {"verdict": "uncertain", "summary": "LLM not available", "issues": []}

        user_msg = f"## Issue: {issue_id}\n\n"
        if spec:
            user_msg += f"## Spec\n\n{spec}\n\n"
        if extra_context:
            user_msg += f"{extra_context}\n\n"
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
