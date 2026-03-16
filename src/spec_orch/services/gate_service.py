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

ALL_KNOWN_CONDITIONS = {
    "spec_exists",
    "spec_approved",
    "within_boundaries",
    "builder",
    "verification",
    "review",
    "preview",
    "human_acceptance",
    "findings",
    "compliance",
}


class GatePolicy:
    """Configurable gate policy with profile support.

    Profiles allow different condition sets for different contexts
    (e.g. ``daemon`` skips ``human_acceptance``, ``ci`` is stricter).
    """

    def __init__(
        self,
        *,
        required_conditions: set[str] | None = None,
        auto_merge: bool = False,
        auto_merge_conditions: set[str] | None = None,
        profiles: dict[str, dict[str, Any]] | None = None,
        raw: dict[str, Any] | None = None,
    ) -> None:
        self.required_conditions = required_conditions or DEFAULT_REQUIRED
        self.auto_merge = auto_merge
        self.auto_merge_conditions = auto_merge_conditions
        self.profiles = profiles or {}
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

        auto_merge_conds: set[str] | None = None
        am_raw = data.get("auto_merge_conditions")
        if isinstance(am_raw, list):
            auto_merge_conds = set(am_raw)

        profiles: dict[str, dict[str, Any]] = {}
        for pname, pcfg in data.get("profiles", {}).items():
            if isinstance(pcfg, dict):
                profiles[pname] = pcfg

        return cls(
            required_conditions=required,
            auto_merge=data.get("auto_merge", False),
            auto_merge_conditions=auto_merge_conds,
            profiles=profiles,
            raw=data,
        )

    @classmethod
    def default(cls) -> GatePolicy:
        return cls()

    def with_profile(self, profile_name: str) -> GatePolicy:
        """Return a new GatePolicy with profile overrides applied."""
        pcfg = self.profiles.get(profile_name)
        if not pcfg:
            return self

        new_required = set(self.required_conditions)
        for cond in pcfg.get("disable", []):
            new_required.discard(cond)
        for cond in pcfg.get("enable", []):
            if cond in ALL_KNOWN_CONDITIONS:
                new_required.add(cond)

        new_auto = pcfg.get("auto_merge", self.auto_merge)

        return GatePolicy(
            required_conditions=new_required,
            auto_merge=new_auto,
            auto_merge_conditions=self.auto_merge_conditions,
            profiles=self.profiles,
            raw=self.raw,
        )

    def available_profiles(self) -> list[str]:
        return sorted(self.profiles.keys())


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
        if "findings" in required and gate_input.review_meta.blocking_unresolved:
            failed_conditions.append("findings")
        if "compliance" in required and not gate_input.compliance_passed:
            failed_conditions.append("compliance")

        mergeable_internal = not failed_conditions

        promotion_required, promotion_target = self._check_promotion(gate_input)

        return GateVerdict(
            mergeable=mergeable_internal,
            failed_conditions=failed_conditions,
            mergeable_internal=mergeable_internal,
            mergeable_external=True,
            promotion_required=promotion_required,
            promotion_target=promotion_target,
        )

    _DOC_EXTENSIONS = frozenset({".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml"})

    def _check_promotion(self, gate_input: GateInput) -> tuple[bool, str | None]:
        """Detect if claimed flow is inconsistent with actual diff.

        Returns (promotion_required, promotion_target).  Does not affect
        mergeable — this is a signal for the caller (RunController) to act on.
        """
        claimed = gate_input.claimed_flow
        if not claimed or not gate_input.diff_stats:
            return False, None

        claimed_lower = claimed.lower()
        if claimed_lower == "full":
            return False, None

        has_code = any(ext not in self._DOC_EXTENSIONS for ext in gate_input.diff_stats)

        if not has_code:
            return False, None

        if claimed_lower == "hotfix":
            return True, "standard"
        if claimed_lower == "standard":
            return True, "full"

        return False, None

    def should_auto_merge(self, gate_input: GateInput) -> bool:
        """Check whether auto-merge should trigger.

        Returns True only when the policy allows auto-merge AND all
        auto-merge conditions (or all required conditions) pass.
        """
        if not self.policy.auto_merge:
            return False
        check_set = self.policy.auto_merge_conditions or self.policy.required_conditions
        temp_policy = GatePolicy(required_conditions=check_set)
        temp_svc = GateService(policy=temp_policy)
        verdict = temp_svc.evaluate(gate_input)
        return verdict.mergeable

    def describe_policy(self) -> str:
        lines = ["Gate Policy:"]
        conditions = self.policy.raw.get("conditions", {})
        if conditions:
            for name, cfg in conditions.items():
                req = "required" if cfg.get("required", True) else "optional"
                desc = cfg.get("description", "")
                status = "enabled" if name in self.policy.required_conditions else "disabled"
                lines.append(f"  {name}: [{req}] ({status}) {desc}")
        else:
            for cond in sorted(self.policy.required_conditions):
                lines.append(f"  {cond}: [required] (enabled)")
        lines.append(f"  auto_merge: {self.policy.auto_merge}")
        if self.policy.auto_merge_conditions:
            lines.append(
                f"  auto_merge_conditions: {', '.join(sorted(self.policy.auto_merge_conditions))}"
            )
        if self.policy.profiles:
            lines.append(f"  profiles: {', '.join(sorted(self.policy.profiles))}")
        return "\n".join(lines)

    def describe_as_dict(self) -> dict[str, Any]:
        """Machine-readable policy description."""
        conditions: dict[str, dict[str, Any]] = {}
        raw_conds = self.policy.raw.get("conditions", {})
        if raw_conds:
            for name, cfg in raw_conds.items():
                conditions[name] = {
                    "required": cfg.get("required", True),
                    "enabled": name in self.policy.required_conditions,
                    "description": cfg.get("description", ""),
                }
        else:
            for cond in sorted(self.policy.required_conditions):
                conditions[cond] = {"required": True, "enabled": True, "description": ""}
        return {
            "conditions": conditions,
            "auto_merge": self.policy.auto_merge,
            "auto_merge_conditions": sorted(self.policy.auto_merge_conditions)
            if self.policy.auto_merge_conditions
            else None,
            "profiles": list(self.policy.profiles.keys()),
        }
