from __future__ import annotations

from pathlib import Path
from typing import Any

from spec_orch.domain.models import GateInput, GateVerdict

DEFAULT_REQUIRED = {
    "spec_exists",
    "spec_approved",
    "within_boundaries",
    "builder",
    "verification",
    "review",
    "human_acceptance",
}


class GatePolicy:
    def __init__(
        self,
        *,
        required_conditions: set[str] | None = None,
        auto_merge: bool = False,
        raw: dict[str, Any] | None = None,
    ) -> None:
        self.required_conditions = required_conditions or DEFAULT_REQUIRED
        self.auto_merge = auto_merge
        self.raw = raw or {}

    @classmethod
    def from_yaml(cls, path: Path) -> GatePolicy:
        import yaml

        with open(path) as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
        conditions = data.get("conditions", {})
        required = {
            name
            for name, cfg in conditions.items()
            if isinstance(cfg, dict) and cfg.get("required", True)
        }
        return cls(
            required_conditions=required,
            auto_merge=data.get("auto_merge", False),
            raw=data,
        )

    @classmethod
    def default(cls) -> GatePolicy:
        return cls()


class GateService:
    def __init__(self, policy: GatePolicy | None = None) -> None:
        self.policy = policy or GatePolicy.default()

    def evaluate(self, gate_input: GateInput) -> GateVerdict:
        failed_conditions: list[str] = []
        required = self.policy.required_conditions

        if "spec_exists" in required and not gate_input.spec_exists:
            failed_conditions.append("spec_exists")
        if "spec_approved" in required and not gate_input.spec_approved:
            failed_conditions.append("spec_approved")
        if "within_boundaries" in required and not gate_input.within_boundaries:
            failed_conditions.append("within_boundaries")
        if "builder" in required and not gate_input.builder_succeeded:
            failed_conditions.append("builder")
        if "verification" in required and not gate_input.verification.all_passed:
            failed_conditions.append("verification")
        if "review" in required and gate_input.review.verdict != "pass":
            failed_conditions.append("review")
        if "preview" in required and gate_input.preview_required and not gate_input.preview_passed:
            failed_conditions.append("preview")
        if "human_acceptance" in required and not gate_input.human_acceptance:
            failed_conditions.append("human_acceptance")

        return GateVerdict(
            mergeable=not failed_conditions,
            failed_conditions=failed_conditions,
        )

    def describe_policy(self) -> str:
        lines = ["Gate Policy:"]
        conditions = self.policy.raw.get("conditions", {})
        if conditions:
            for name, cfg in conditions.items():
                req = "required" if cfg.get("required", True) else "optional"
                desc = cfg.get("description", "")
                lines.append(f"  {name}: [{req}] {desc}")
        else:
            for cond in sorted(self.policy.required_conditions):
                lines.append(f"  {cond}: [required]")
        lines.append(f"  auto_merge: {self.policy.auto_merge}")
        return "\n".join(lines)
