"""Legacy shim for spec snapshot helpers now owned by contract_core."""

from spec_orch.contract_core.snapshots import (
    approve_spec_snapshot,
    auto_approve_spec_snapshot,
    create_initial_snapshot,
    read_spec_snapshot,
    write_spec_snapshot,
)

__all__ = [
    "approve_spec_snapshot",
    "auto_approve_spec_snapshot",
    "create_initial_snapshot",
    "read_spec_snapshot",
    "write_spec_snapshot",
]
