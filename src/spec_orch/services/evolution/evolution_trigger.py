"""Config-driven evolution trigger.

Reads ``[evolution]`` from spec-orch.toml and decides which evolvers to
invoke after each run.  Replaces ad-hoc manual invocations with a
deterministic, auditable lifecycle:
  observe → propose → (validate) → promote/reject
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.domain.models import Issue, IssueContext
from spec_orch.domain.protocols import LifecycleEvolver
from spec_orch.services.context_assembler import ContextAssembler
from spec_orch.services.evolution.evolution_policy import EvolutionPolicy
from spec_orch.services.evolution.promotion_registry import PromotionRegistry
from spec_orch.services.evolution.signal_bridge import build_evolution_signal_snapshot
from spec_orch.services.harness_synthesizer import HarnessSynthesizer, RuleValidator
from spec_orch.services.node_context_registry import get_node_context_spec

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EvolutionConfig:
    """Parsed ``[evolution]`` section of spec-orch.toml."""

    enabled: bool = True
    trigger_after_n_runs: int = 5
    auto_promote: bool = False
    prompt_evolver_enabled: bool = True
    plan_strategy_evolver_enabled: bool = True
    harness_synthesizer_enabled: bool = True
    harness_dry_run: bool = True
    policy_distiller_enabled: bool = False
    config_evolver_enabled: bool = True
    intent_evolver_enabled: bool = True
    gate_policy_evolver_enabled: bool = False
    flow_policy_evolver_enabled: bool = False
    skill_evolver_enabled: bool = False

    @classmethod
    def from_toml(cls, data: dict[str, Any]) -> EvolutionConfig:
        evo = data.get("evolution", {})
        return cls(
            enabled=evo.get("enabled", True),
            trigger_after_n_runs=evo.get("trigger_after_n_runs", 5),
            auto_promote=evo.get("auto_promote", False),
            prompt_evolver_enabled=evo.get("prompt_evolver", {}).get("enabled", True),
            plan_strategy_evolver_enabled=evo.get("plan_strategy_evolver", {}).get("enabled", True),
            harness_synthesizer_enabled=evo.get("harness_synthesizer", {}).get("enabled", True),
            harness_dry_run=evo.get("harness_synthesizer", {}).get("dry_run", True),
            policy_distiller_enabled=evo.get("policy_distiller", {}).get("enabled", False),
            config_evolver_enabled=evo.get("config_evolver", {}).get("enabled", True),
            intent_evolver_enabled=evo.get("intent_evolver", {}).get("enabled", True),
            gate_policy_evolver_enabled=evo.get("gate_policy_evolver", {}).get("enabled", False),
            flow_policy_evolver_enabled=evo.get("flow_policy_evolver", {}).get("enabled", False),
            skill_evolver_enabled=evo.get("skill_evolver", {}).get("enabled", False),
        )


@dataclass(slots=True)
class EvolutionResult:
    """Outcome of a single evolution cycle."""

    run_count: int = 0
    triggered: bool = False
    prompt_evolved: bool = False
    plan_hints_generated: bool = False
    harness_rules_proposed: int = 0
    policies_distilled: int = 0
    errors: list[str] = field(default_factory=list)
    timestamp: str = ""


class EvolutionTrigger:
    """Decides when and how to trigger evolution based on config."""

    def __init__(
        self,
        repo_root: Path,
        config: EvolutionConfig,
        planner: Any | None = None,
        latest_workspace: Path | None = None,
        policy: EvolutionPolicy | None = None,
    ):
        self._repo_root = repo_root
        self._config = config
        self._planner = planner
        self._latest_workspace = latest_workspace
        self._counter_path = repo_root / ".spec_orch_evolution" / "run_counter.json"
        self._context_assembler = ContextAssembler()
        self._policy = policy or EvolutionPolicy(global_min_runs=config.trigger_after_n_runs)
        self._promotion_registry = PromotionRegistry(repo_root)

    def _read_counter(self) -> int:
        if not self._counter_path.exists():
            return 0
        try:
            data = json.loads(self._counter_path.read_text())
            return int(data.get("count", 0))
        except json.JSONDecodeError:
            logger.warning(
                "Failed to decode run counter JSON at %s, resetting to 0",
                self._counter_path,
            )
            return 0
        except (ValueError, OSError):
            logger.warning(
                "Failed to read or parse run counter at %s, resetting to 0",
                self._counter_path,
            )
            return 0

    def _write_counter(self, count: int) -> None:
        from spec_orch.services.io import atomic_write_json

        atomic_write_json(
            self._counter_path,
            {"count": count, "updated_at": datetime.now(UTC).isoformat()},
        )

    def _lock_path(self) -> Path:
        return self._counter_path.with_suffix(".lock")

    def increment_and_check(self) -> bool:
        """Increment run counter and return True if evolution should trigger.

        Uses file locking to prevent lost-update races when multiple
        daemon workers run concurrently.
        """
        if not self._config.enabled:
            return False
        from spec_orch.services.io import file_lock

        with file_lock(self._lock_path()):
            count = self._read_counter() + 1
            self._write_counter(count)
            return count >= self._config.trigger_after_n_runs

    def reset_counter(self) -> None:
        from spec_orch.services.io import file_lock

        with file_lock(self._lock_path()):
            self._write_counter(0)

    def run_evolution_cycle(self, metrics: dict[str, float] | None = None) -> EvolutionResult:
        """Execute all enabled evolvers and return results.

        Uses EvolutionPolicy to determine which evolvers should run and in
        what order, based on configured trigger conditions and current metrics.
        """
        if not self._config.enabled:
            return EvolutionResult(timestamp=datetime.now(UTC).isoformat())

        if not self.increment_and_check():
            return EvolutionResult(
                run_count=self._read_counter(),
                timestamp=datetime.now(UTC).isoformat(),
            )

        run_count = self._read_counter()
        result = EvolutionResult(
            run_count=run_count,
            triggered=True,
            timestamp=datetime.now(UTC).isoformat(),
        )
        self.reset_counter()

        enabled_names = self._get_enabled_evolvers()
        ordered = self._policy.priority_order(enabled_names, metrics)

        for evolver_name in ordered:
            if not self._policy.should_trigger(
                evolver_name, run_count, metrics, skip_min_runs=True
            ):
                continue
            self._run_single_evolver(evolver_name, result)

        self._write_result(result)
        return result

    def _get_enabled_evolvers(self) -> list[str]:
        """Return list of evolver names that are enabled in config."""
        evolvers: list[str] = []
        if self._config.prompt_evolver_enabled:
            evolvers.append("prompt_evolver")
        if self._config.plan_strategy_evolver_enabled:
            evolvers.append("plan_strategy_evolver")
        if self._config.harness_synthesizer_enabled:
            evolvers.append("harness_synthesizer")
        if self._config.policy_distiller_enabled:
            evolvers.append("policy_distiller")
        if self._config.config_evolver_enabled:
            evolvers.append("config_evolver")
        if self._config.intent_evolver_enabled:
            evolvers.append("intent_evolver")
        if self._config.gate_policy_evolver_enabled:
            evolvers.append("gate_policy_evolver")
        if self._config.flow_policy_evolver_enabled:
            evolvers.append("flow_policy_evolver")
        if self._config.skill_evolver_enabled:
            evolvers.append("skill_evolver")
        return evolvers

    def _build_lifecycle_evolver(self, name: str) -> LifecycleEvolver | None:
        """Instantiate a lifecycle-conforming evolver by name, or ``None``."""
        try:
            if name == "prompt_evolver":
                from spec_orch.services.evolution.prompt_evolver import PromptEvolver

                return PromptEvolver(self._repo_root, planner=self._planner)
            if name == "plan_strategy_evolver":
                from spec_orch.services.evolution.plan_strategy_evolver import PlanStrategyEvolver

                return PlanStrategyEvolver(self._repo_root, planner=self._planner)
            if name == "config_evolver":
                from spec_orch.services.evolution.config_evolver import ConfigEvolver

                return ConfigEvolver(self._repo_root)
            if name == "intent_evolver":
                from spec_orch.services.evolution.intent_evolver import IntentEvolver

                return IntentEvolver(self._repo_root, planner=self._planner)
            if name == "gate_policy_evolver":
                from spec_orch.services.evolution.gate_policy_evolver import GatePolicyEvolver

                return GatePolicyEvolver(self._repo_root, planner=self._planner)
            if name == "flow_policy_evolver":
                from spec_orch.services.evolution.flow_policy_evolver import FlowPolicyEvolver

                return FlowPolicyEvolver(self._repo_root, planner=self._planner)
            if name == "skill_evolver":
                from spec_orch.services.evolution.skill_evolver import SkillEvolver

                return SkillEvolver(self._repo_root, planner=self._planner)
        except Exception:
            logger.warning("Failed to instantiate evolver %s", name, exc_info=True)
        return None

    def _run_single_evolver(self, name: str, result: EvolutionResult) -> None:
        """Dispatch to the appropriate evolver by name.

        Lifecycle-conforming evolvers go through observe → propose → validate
        → promote.  HarnessSynthesizer and PolicyDistiller use legacy handlers.
        """
        legacy_dispatch: dict[str, Any] = {
            "harness_synthesizer": self._run_harness_synthesizer,
            "policy_distiller": self._run_policy_distiller,
        }
        legacy = legacy_dispatch.get(name)
        if legacy:
            legacy(result)
            return

        evolver = self._build_lifecycle_evolver(name)
        if evolver is None:
            logger.warning("Unknown or unavailable evolver: %s", name)
            return
        self._run_lifecycle(evolver, result)

    def _run_lifecycle(self, evolver: LifecycleEvolver, result: EvolutionResult) -> None:
        """Execute the four-phase lifecycle for a single evolver."""
        name = evolver.EVOLVER_NAME
        context = self._assemble_evolver_context(name)
        signal_snapshot = build_evolution_signal_snapshot(context)
        signal_payload = signal_snapshot.to_dict()
        run_dirs = self._collect_run_dirs()
        try:
            evidence = evolver.observe(run_dirs, context=context)
            if not evidence:
                self._write_journal_entry(
                    evolver_name=name,
                    stage="observe",
                    payload={"evidence_count": 0, "skipped": True, **signal_payload},
                )
                logger.debug("%s: no evidence collected, skipping", name)
                return
            self._write_journal_entry(
                evolver_name=name,
                stage="observe",
                payload={"evidence_count": len(evidence), **signal_payload},
            )

            proposals = evolver.propose(evidence, context=context)
            if not proposals:
                self._write_journal_entry(
                    evolver_name=name,
                    stage="propose",
                    payload={"proposal_count": 0, "skipped": True, **signal_payload},
                )
                logger.debug("%s: no proposals generated", name)
                return
            self._write_journal_entry(
                evolver_name=name,
                stage="propose",
                payload={"proposal_count": len(proposals), **signal_payload},
            )

            promoted_any = False
            has_ab_testing = hasattr(evolver, "promote_variant")
            for proposal in proposals:
                outcome = evolver.validate(proposal)
                self._write_journal_entry(
                    evolver_name=name,
                    stage="validate",
                    payload={
                        "proposal_id": proposal.proposal_id,
                        "change_type": proposal.change_type.value,
                        "accepted": outcome.accepted,
                        "validation_method": outcome.validation_method.value,
                        "reason": outcome.reason,
                        "metrics": outcome.metrics,
                        **signal_payload,
                    },
                )
                if outcome.accepted:
                    if has_ab_testing and not self._config.auto_promote:
                        logger.info(
                            "%s: proposal %s accepted, variant saved as candidate "
                            "(auto_promote off, pending A/B validation)",
                            name,
                            proposal.proposal_id,
                        )
                        continue
                    gate = self._promotion_registry.evaluate_gate(
                        proposal,
                        reviewed_evidence_count=signal_snapshot.reviewed_evidence_count,
                        signal_origins=signal_snapshot.signal_origins,
                    )
                    if not gate.allowed:
                        self._write_journal_entry(
                            evolver_name=name,
                            stage="promote",
                            payload={
                                "proposal_id": proposal.proposal_id,
                                "promotion_blocked": True,
                                "reason": gate.reason,
                                "promotion_origin": gate.origin.value,
                                "reviewed_evidence_count": gate.reviewed_evidence_count,
                                "signal_origins": gate.signal_origins,
                            },
                        )
                        continue
                    ok = evolver.promote(proposal)
                    if ok:
                        promoted_any = True
                        promotion_record = self._promotion_registry.record_promotion(
                            proposal,
                            origin=gate.origin,
                            reviewed_evidence_count=gate.reviewed_evidence_count,
                            signal_origins=gate.signal_origins,
                        )
                        self._write_journal_entry(
                            evolver_name=name,
                            stage="promote",
                            payload={
                                "proposal_id": proposal.proposal_id,
                                "promoted": True,
                                "promotion_id": promotion_record.promotion_id,
                                "promotion_origin": gate.origin.value,
                                **signal_payload,
                            },
                        )
                        logger.info(
                            "%s: promoted proposal %s",
                            name,
                            proposal.proposal_id,
                        )

            self._update_result_flags(name, result, proposals, promoted_any)
        except Exception as exc:
            result.errors.append(f"{name}: {exc}")
            self._write_journal_entry(
                evolver_name=name,
                stage="error",
                payload={"error": str(exc)},
            )
            logger.warning("%s failed", name, exc_info=True)

    def _collect_run_dirs(self) -> list[Path]:
        """Gather recent run directories for evolver observation."""
        dirs: list[Path] = []
        for parent in (
            self._repo_root / ".spec_orch_runs",
            self._repo_root / ".worktrees",
        ):
            if parent.is_dir():
                dirs.extend(sorted(parent.iterdir())[-20:])
        return dirs

    @staticmethod
    def _update_result_flags(
        name: str,
        result: EvolutionResult,
        proposals: list[Any],
        promoted: bool,
    ) -> None:
        if name == "prompt_evolver" and proposals:
            result.prompt_evolved = True
        elif name == "plan_strategy_evolver" and proposals:
            result.plan_hints_generated = True

    def _run_harness_synthesizer(self, result: EvolutionResult) -> None:
        if self._planner is None:
            return
        try:
            synth = HarnessSynthesizer(self._repo_root, planner=self._planner)
            hs_context = self._assemble_evolver_context("harness_synthesizer")
            candidates = synth.synthesize(context=hs_context)
            if candidates:
                validator = RuleValidator(self._repo_root)
                accepted, _ = validator.validate(candidates)
                result.harness_rules_proposed = len(accepted)
                if accepted and not self._config.harness_dry_run:
                    contracts_path = self._repo_root / "compliance.contracts.yaml"
                    validator.apply(accepted, contracts_path)
        except Exception as exc:
            result.errors.append(f"HarnessSynthesizer: {exc}")
            logger.warning("HarnessSynthesizer failed", exc_info=True)

    def _run_policy_distiller(self, result: EvolutionResult) -> None:
        if self._planner is None:
            return
        try:
            from spec_orch.services.policy_distiller import PolicyDistiller

            pd = PolicyDistiller(self._repo_root, planner=self._planner)
            pd_context = self._assemble_evolver_context("policy_distiller")
            policy = pd.distill(context=pd_context)
            if policy:
                result.policies_distilled = 1
                logger.info("PolicyDistiller produced policy: %s", policy.policy_id)
        except Exception as exc:
            result.errors.append(f"PolicyDistiller: {exc}")
            logger.warning("PolicyDistiller failed", exc_info=True)

    def _load_latest_manifest(self) -> dict[str, str]:
        """Load artifacts dict from the latest workspace's manifest, if any."""
        if not self._latest_workspace:
            return {}
        for manifest_path in (
            self._latest_workspace / "run_artifact" / "manifest.json",
            self._latest_workspace / "artifact_manifest.json",
        ):
            if not manifest_path.exists():
                continue
            try:
                data = json.loads(manifest_path.read_text())
                artifacts: dict[str, str] = data.get("artifacts", {})
                return artifacts
            except (json.JSONDecodeError, OSError):
                logger.debug(
                    "Failed to load artifact manifest from %s", manifest_path, exc_info=True
                )
        return {}

    def _write_result(self, result: EvolutionResult) -> None:
        log_dir = self._repo_root / ".spec_orch_evolution"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "evolution_log.jsonl"
        entry = {
            "timestamp": result.timestamp,
            "triggered": result.triggered,
            "run_count": result.run_count,
            "prompt_evolved": result.prompt_evolved,
            "plan_hints_generated": result.plan_hints_generated,
            "harness_rules_proposed": result.harness_rules_proposed,
            "policies_distilled": result.policies_distilled,
            "errors": result.errors,
        }
        with log_path.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _write_journal_entry(
        self,
        *,
        evolver_name: str,
        stage: str,
        payload: dict[str, Any],
    ) -> None:
        log_dir = self._repo_root / ".spec_orch_evolution"
        log_dir.mkdir(parents=True, exist_ok=True)
        journal_path = log_dir / "evolution_journal.jsonl"
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "evolver_name": evolver_name,
            "stage": stage,
            **payload,
        }
        with journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

        try:
            from spec_orch.services.memory.service import get_memory_service

            summary = payload.get("reason") or payload.get("error") or ""
            get_memory_service(repo_root=self._repo_root).record_evolution_journal(
                evolver_name=evolver_name,
                stage=stage,
                summary=str(summary),
                metadata=entry,
            )
        except Exception:
            logger.debug("Failed to mirror evolution journal into memory", exc_info=True)

    def _assemble_evolver_context(self, node_name: str) -> Any | None:
        """Best-effort ContextBundle assembly for evolver nodes."""
        if self._latest_workspace is None:
            return None
        try:
            issue = self._build_issue_from_latest_workspace()
            memory = None
            try:
                from spec_orch.services.memory.service import get_memory_service

                memory = get_memory_service(repo_root=self._repo_root)
            except Exception:
                from spec_orch.services.event_bus import emit_fallback_safe

                emit_fallback_safe(
                    "EvolutionTrigger",
                    "memory_service",
                    "no_memory",
                    "MemoryService initialization failed for evolver",
                )
            return self._context_assembler.assemble(
                get_node_context_spec(node_name),
                issue,
                self._latest_workspace,
                memory=memory,
                repo_root=self._repo_root,
            )
        except Exception:
            logger.debug("Failed to assemble context for %s", node_name, exc_info=True)
            return None

    def _build_issue_from_latest_workspace(self) -> Issue:
        if self._latest_workspace is None:
            raise ValueError("latest workspace is required for evolver context assembly")
        issue_id = "evolver-context"
        title = "evolver context"
        summary = ""
        acceptance_criteria: list[str] = []
        constraints: list[str] = []

        spec_snapshot_path = self._latest_workspace / "spec_snapshot.json"
        if spec_snapshot_path.exists():
            with spec_snapshot_path.open("r", encoding="utf-8") as f:
                snap = json.load(f)
            issue_data = snap.get("issue", {})
            issue_id = issue_data.get("issue_id", issue_id)
            title = issue_data.get("title", title)
            summary = issue_data.get("summary") or issue_data.get("intent") or ""
            raw_ac = issue_data.get("acceptance_criteria", [])
            if isinstance(raw_ac, list):
                acceptance_criteria = [str(v) for v in raw_ac]
            raw_constraints = issue_data.get("context", {}).get("constraints", [])
            if isinstance(raw_constraints, list):
                constraints = [str(v) for v in raw_constraints]

        return Issue(
            issue_id=issue_id,
            title=title,
            summary=summary,
            context=IssueContext(constraints=constraints),
            acceptance_criteria=acceptance_criteria,
        )
