from spec_orch.contract_core import (
    TaskContract,
    approve_spec_snapshot,
    create_initial_snapshot,
    generate_contract_from_issue,
    read_spec_snapshot,
    write_spec_snapshot,
)
from spec_orch.contract_core.contracts import TaskContract as CanonicalTaskContract
from spec_orch.domain.task_contract import TaskContract as LegacyTaskContract
from spec_orch.services.spec_snapshot_service import (
    read_spec_snapshot as legacy_read_spec_snapshot,
)


def test_contract_core_exports_canonical_contract_primitives() -> None:
    assert TaskContract is CanonicalTaskContract
    assert generate_contract_from_issue is not None
    assert create_initial_snapshot is not None
    assert write_spec_snapshot is not None
    assert read_spec_snapshot is not None
    assert approve_spec_snapshot is not None


def test_legacy_contract_shims_point_to_contract_core() -> None:
    assert LegacyTaskContract is CanonicalTaskContract
    assert legacy_read_spec_snapshot is read_spec_snapshot
