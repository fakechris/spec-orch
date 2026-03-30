from __future__ import annotations

from spec_orch.runtime_core.writers import write_issue_execution_payloads
from spec_orch.services.execution_semantics_writer import (
    write_issue_execution_payloads as shim_write_issue_execution_payloads,
)


def test_service_writer_is_runtime_core_shim() -> None:
    assert shim_write_issue_execution_payloads is write_issue_execution_payloads
