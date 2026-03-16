"""Pre-defined FlowGraph instances for each FlowType.

These graphs mirror the step tables in docs/architecture/change-management-policy.md.
"""

from __future__ import annotations

from spec_orch.domain.models import FlowGraph, FlowStep, FlowType, RunState

# ---------------------------------------------------------------------------
# Full Flow (New Features, Architecture Changes)
# ---------------------------------------------------------------------------

FULL_GRAPH = FlowGraph(
    flow_type=FlowType.FULL,
    steps=(
        FlowStep(id="create_issue"),
        FlowStep(id="discuss"),
        FlowStep(id="freeze_spec", run_state=RunState.SPEC_DRAFTING),
        FlowStep(id="mission_approve", run_state=RunState.SPEC_APPROVED),
        FlowStep(id="generate_plan"),
        FlowStep(id="promote_issues"),
        FlowStep(id="generate_contracts"),
        FlowStep(
            id="execute",
            run_state=RunState.BUILDING,
            skippable_if=("doc_only",),
        ),
        FlowStep(id="verify", run_state=RunState.VERIFYING),
        FlowStep(id="gate", run_state=RunState.GATE_EVALUATED),
        FlowStep(id="create_pr"),
        FlowStep(id="pr_review", run_state=RunState.REVIEW_PENDING),
        FlowStep(id="merge", run_state=RunState.MERGED),
        FlowStep(id="retrospective"),
    ),
    transitions={
        "create_issue": ("discuss",),
        "discuss": ("freeze_spec",),
        "freeze_spec": ("mission_approve",),
        "mission_approve": ("generate_plan",),
        "generate_plan": ("promote_issues",),
        "promote_issues": ("generate_contracts",),
        "generate_contracts": ("execute",),
        "execute": ("verify",),
        "verify": ("gate",),
        "gate": ("create_pr",),
        "create_pr": ("pr_review",),
        "pr_review": ("merge",),
        "merge": ("retrospective",),
        "retrospective": (),
    },
    backtrack={
        "gate": {
            "recoverable": "execute",
            "needs_redesign": "freeze_spec",
        },
    },
)

# ---------------------------------------------------------------------------
# Standard Flow (Bug Fixes, Small Improvements)
# ---------------------------------------------------------------------------

STANDARD_GRAPH = FlowGraph(
    flow_type=FlowType.STANDARD,
    steps=(
        FlowStep(id="create_issue"),
        FlowStep(id="create_branch"),
        FlowStep(id="implement", run_state=RunState.BUILDING),
        FlowStep(
            id="verify",
            run_state=RunState.VERIFYING,
            skippable_if=("doc_only",),
        ),
        FlowStep(id="gate", run_state=RunState.GATE_EVALUATED),
        FlowStep(id="create_pr"),
        FlowStep(id="pr_review", run_state=RunState.REVIEW_PENDING),
        FlowStep(id="merge", run_state=RunState.MERGED),
    ),
    transitions={
        "create_issue": ("create_branch",),
        "create_branch": ("implement",),
        "implement": ("verify",),
        "verify": ("gate",),
        "gate": ("create_pr",),
        "create_pr": ("pr_review",),
        "pr_review": ("merge",),
        "merge": (),
    },
    backtrack={
        "gate": {
            "recoverable": "implement",
        },
    },
)

# ---------------------------------------------------------------------------
# Hotfix Flow (Production Blockers, Security Issues)
# ---------------------------------------------------------------------------

HOTFIX_GRAPH = FlowGraph(
    flow_type=FlowType.HOTFIX,
    steps=(
        FlowStep(id="create_issue"),
        FlowStep(id="create_branch"),
        FlowStep(id="implement", run_state=RunState.BUILDING),
        FlowStep(id="verify", run_state=RunState.VERIFYING),
        FlowStep(id="gate", run_state=RunState.GATE_EVALUATED),
        FlowStep(id="create_pr"),
        FlowStep(
            id="pre_merge_review",
            run_state=RunState.REVIEW_PENDING,
            skippable_if=("urgent",),
        ),
        FlowStep(id="merge", run_state=RunState.MERGED),
        FlowStep(id="post_merge_review"),
    ),
    transitions={
        "create_issue": ("create_branch",),
        "create_branch": ("implement",),
        "implement": ("verify",),
        "verify": ("gate",),
        "gate": ("create_pr",),
        "create_pr": ("pre_merge_review",),
        "pre_merge_review": ("merge",),
        "merge": ("post_merge_review",),
        "post_merge_review": (),
    },
    backtrack={
        "gate": {
            "recoverable": "implement",
        },
    },
)
