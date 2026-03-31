"""Legacy shim for task contract primitives now owned by contract_core."""

from spec_orch.contract_core.contracts import (
    TaskContract,
    assess_risk_level,
    generate_contract_from_issue,
)

__all__ = ["TaskContract", "assess_risk_level", "generate_contract_from_issue"]
