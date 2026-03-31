"""Contract core seams for snapshots, contracts, and future import normalization."""

from spec_orch.contract_core.contracts import (
    TaskContract,
    assess_risk_level,
    generate_contract_from_issue,
)
from spec_orch.contract_core.decisions import (
    add_snapshot_question,
    answer_snapshot_question,
    question_status_rows,
)
from spec_orch.contract_core.snapshots import (
    approve_spec_snapshot,
    auto_approve_spec_snapshot,
    create_initial_snapshot,
    read_spec_snapshot,
    write_spec_snapshot,
)

__all__ = [
    "TaskContract",
    "assess_risk_level",
    "generate_contract_from_issue",
    "add_snapshot_question",
    "answer_snapshot_question",
    "question_status_rows",
    "approve_spec_snapshot",
    "auto_approve_spec_snapshot",
    "create_initial_snapshot",
    "read_spec_snapshot",
    "write_spec_snapshot",
]
