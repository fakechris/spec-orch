"""Configurable compliance engine with YAML-defined contracts.

Extends the core ComplianceEngine with declarative contract definitions
loaded from compliance.contracts.yaml.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from spec_orch.domain.models import BuilderEvent


@dataclass(slots=True)
class ComplianceContract:
    """A single compliance contract definition."""

    id: str
    name: str
    description: str = ""
    severity: str = "warning"
    builtin: bool = False
    patterns: list[str] = field(default_factory=list)
    check_fields: list[str] = field(default_factory=lambda: ["text"])


@dataclass(slots=True)
class ContractResult:
    """Evaluation result for a single contract."""

    contract_id: str
    contract_name: str
    severity: str
    passed: bool
    violations: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ComplianceReport:
    """Full compliance evaluation report."""

    results: list[ContractResult] = field(default_factory=list)

    @property
    def compliant(self) -> bool:
        return all(r.passed for r in self.results if r.severity == "error")

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if not r.passed and r.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.results if not r.passed and r.severity == "warning")

    def to_dict(self) -> dict[str, Any]:
        return {
            "compliant": self.compliant,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "results": [
                {
                    "contract_id": r.contract_id,
                    "contract_name": r.contract_name,
                    "severity": r.severity,
                    "passed": r.passed,
                    "violations": r.violations,
                }
                for r in self.results
            ],
        }

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> ComplianceReport:
        data = json.loads(path.read_text())
        results = [
            ContractResult(
                contract_id=r["contract_id"],
                contract_name=r["contract_name"],
                severity=r["severity"],
                passed=r["passed"],
                violations=r.get("violations", []),
            )
            for r in data.get("results", [])
        ]
        return cls(results=results)


def load_contracts(path: Path) -> list[ComplianceContract]:
    """Load contract definitions from a YAML file."""
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text())
    if not raw or "contracts" not in raw:
        return []
    contracts: list[ComplianceContract] = []
    for entry in raw["contracts"]:
        contracts.append(ComplianceContract(
            id=entry["id"],
            name=entry["name"],
            description=entry.get("description", ""),
            severity=entry.get("severity", "warning"),
            builtin=entry.get("builtin", False),
            patterns=entry.get("patterns", []),
            check_fields=entry.get("check_fields", ["text"]),
        ))
    return contracts


class ConfigurableComplianceEngine:
    """Evaluate builder events against YAML-configured contracts."""

    def __init__(self, contracts: list[ComplianceContract] | None = None) -> None:
        self._contracts = contracts or []

    @classmethod
    def from_yaml(cls, path: Path) -> ConfigurableComplianceEngine:
        return cls(contracts=load_contracts(path))

    def evaluate(self, events: list[BuilderEvent]) -> ComplianceReport:
        results: list[ContractResult] = []
        for contract in self._contracts:
            if contract.builtin:
                result = self._evaluate_builtin(contract, events)
            else:
                result = self._evaluate_pattern(contract, events)
            results.append(result)
        return ComplianceReport(results=results)

    def _evaluate_builtin(
        self, contract: ComplianceContract, events: list[BuilderEvent],
    ) -> ContractResult:
        if contract.id == "pre-action-narration":
            from spec_orch.domain.compliance import pre_action_narration_rule

            violations = pre_action_narration_rule(events)
            return ContractResult(
                contract_id=contract.id,
                contract_name=contract.name,
                severity=contract.severity,
                passed=len(violations) == 0,
                violations=violations,
            )
        return ContractResult(
            contract_id=contract.id,
            contract_name=contract.name,
            severity=contract.severity,
            passed=True,
        )

    def _evaluate_pattern(
        self, contract: ComplianceContract, events: list[BuilderEvent],
    ) -> ContractResult:
        compiled = [re.compile(p) for p in contract.patterns]
        violations: list[dict[str, Any]] = []

        for evt in events:
            for fld in contract.check_fields:
                value = getattr(evt, fld, "") or ""
                if not value:
                    continue
                for pat in compiled:
                    if pat.search(value):
                        violations.append({
                            "timestamp": evt.timestamp,
                            "kind": evt.kind,
                            "field": fld,
                            "match": pat.pattern,
                            "excerpt": value[:200],
                        })

        return ContractResult(
            contract_id=contract.id,
            contract_name=contract.name,
            severity=contract.severity,
            passed=len(violations) == 0,
            violations=violations,
        )
