from __future__ import annotations

from pathlib import Path

from spec_orch.domain.models import GateVerdict, RunResult
from spec_orch.services.linear_client import LinearClient
from spec_orch.services.linear_intake import (
    LinearIntakeDocument,
    LinearIntakeState,
    render_linear_intake_description,
)


class LinearWriteBackService:
    def __init__(self, client: LinearClient) -> None:
        self._client = client

    def post_run_summary(self, *, linear_id: str, result: RunResult) -> None:
        body = self._build_comment(result)
        self._client.add_comment(linear_id, body)

    def post_intake_summary(
        self,
        *,
        linear_id: str,
        state: LinearIntakeState,
        intake: LinearIntakeDocument,
    ) -> None:
        self._client.add_comment(linear_id, self._build_intake_summary_comment(state, intake))

    def rewrite_issue_for_intake(
        self,
        *,
        linear_id: str,
        intake: LinearIntakeDocument,
    ) -> None:
        self._client.update_issue_description(
            linear_id,
            description=render_linear_intake_description(intake),
        )

    def update_state_on_merge(self, *, linear_id: str, target_state: str = "Done") -> None:
        self._client.update_issue_state(linear_id, target_state)

    def _build_comment(self, result: RunResult) -> str:
        gate = result.gate
        builder = result.builder
        lines = [
            "## SpecOrch Run Summary",
            "",
            f"**Issue**: {result.issue.issue_id} — {result.issue.title}",
            f"**Builder**: {builder.adapter} ({builder.agent})",
            f"**Builder succeeded**: {'yes' if builder.succeeded else 'no'}",
            "",
            "### Gate Verdict",
            "",
            f"**Mergeable**: {'yes' if gate.mergeable else 'no'}",
        ]
        if gate.failed_conditions:
            lines.append(f"**Blocked by**: {', '.join(gate.failed_conditions)}")
        else:
            lines.append("All conditions passed.")

        explain_path = result.explain
        if explain_path.exists():
            explain_text = explain_path.read_text().strip()
            if len(explain_text) > 2000:
                explain_text = explain_text[:2000] + "\n\n*(truncated)*"
            lines.extend(["", "### Explain Report", "", explain_text])

        return "\n".join(lines)

    def post_gate_update(
        self, *, linear_id: str, gate: GateVerdict, explain_path: Path | None = None
    ) -> None:
        lines = [
            "## Gate Re-evaluation",
            "",
            f"**Mergeable**: {'yes' if gate.mergeable else 'no'}",
        ]
        if gate.failed_conditions:
            lines.append(f"**Blocked by**: {', '.join(gate.failed_conditions)}")
        else:
            lines.append("All conditions passed.")

        if explain_path and explain_path.exists():
            explain_text = explain_path.read_text().strip()
            if len(explain_text) > 2000:
                explain_text = explain_text[:2000] + "\n\n*(truncated)*"
            lines.extend(["", "### Updated Explain", "", explain_text])

        self._client.add_comment(linear_id, "\n".join(lines))

    def _build_intake_summary_comment(
        self,
        state: LinearIntakeState,
        intake: LinearIntakeDocument,
    ) -> str:
        lines = [
            "## SpecOrch Intake Summary",
            "",
            f"**State**: `{state.value}`",
            "",
            "### Problem",
            "",
            intake.problem or "_pending_",
            "",
            "### Goal",
            "",
            intake.goal or "_pending_",
            "",
            "### Acceptance",
            "",
        ]
        for item in intake.acceptance.success_conditions:
            lines.append(f"- success: {item}")
        for item in intake.acceptance.verification_expectations:
            lines.append(f"- verify: {item}")
        for item in intake.acceptance.human_judgment_required:
            lines.append(f"- human: {item}")
        if not (
            intake.acceptance.success_conditions
            or intake.acceptance.verification_expectations
            or intake.acceptance.human_judgment_required
        ):
            lines.append("- pending")
        lines.extend(
            [
                "",
                "### Open Questions",
                "",
            ]
        )
        if intake.open_questions:
            lines.extend(f"- {item}" for item in intake.open_questions)
        else:
            lines.append("- none")
        lines.extend(
            [
                "",
                "### Current System Understanding",
                "",
                intake.current_system_understanding or "_pending_",
            ]
        )
        return "\n".join(lines)
