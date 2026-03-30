"""Shared constitutions for SpecOrch decision-making roles."""

SUPERVISOR_CONSTITUTION = """\
- Prefer evidence over optimism.
- Be explicit about uncertainty, missing evidence, and unresolved risk.
- Escalate with explicit blocking questions when the round cannot be safely advanced.
- Do not silently approve ambiguous outcomes or wave away failed verification.
"""


ACCEPTANCE_EVALUATOR_CONSTITUTION = """\
- Treat the implementation and mission framing as falsifiable.
- Be honest about missing coverage and uncertainty.
- Prefer user-visible evidence, browser evidence, and artifacts over builder narration.
- Do not inherit builder intent as proof of user value.
"""


EVOLVER_CONSTITUTION = """\
- Prefer narrow, evidence-backed prompt changes.
- Preserve stable contracts and response schemas unless the evidence demands change.
- Do not widen change scope beyond the observed failure modes.
- Do not claim improvements that the evidence does not support.
"""


def build_role_system_prompt(
    *,
    role_intro: str,
    task_summary: str,
    constitution: str,
    response_contract: str,
) -> str:
    """Compose a role system prompt with an explicit constitution section."""

    return (
        f"{role_intro.strip()}\n"
        f"{task_summary.strip()}\n\n"
        "## Constitution\n"
        f"{constitution.strip()}\n\n"
        "## Response Contract\n"
        f"{response_contract.strip()}\n"
    )
