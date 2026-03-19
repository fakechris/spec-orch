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
from spec_orch.services.context_assembler import ContextAssembler
from spec_orch.services.harness_synthesizer import HarnessSynthesizer, RuleValidator
from spec_orch.services.node_context_registry import get_node_context_spec
from spec_orch.services.plan_strategy_evolver import PlanStrategyEvolver
from spec_orch.services.prompt_evolver import PromptEvolver

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
        )


@dataclass(slots=True)
class EvolutionResult:
    """Outcome of a single evolution cycle."""

    run_count: int = 0
    triggered: bool = False
    prompt_evolved: bool = False
    plan_hints_generated: bool = False
    harness_rules_proposed: int = 0
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
    ):
        self._repo_root = repo_root
        self._config = config
        self._planner = planner
        self._latest_workspace = latest_workspace
        self._counter_path = repo_root / ".spec_orch_evolution" / "run_counter.json"
        self._context_assembler = ContextAssembler()

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
        self._counter_path.parent.mkdir(parents=True, exist_ok=True)
        self._counter_path.write_text(
            json.dumps({"count": count, "updated_at": datetime.now(UTC).isoformat()}) + "\n"
        )

    def increment_and_check(self) -> bool:
        """Increment run counter and return True if evolution should trigger."""
        if not self._config.enabled:
            return False
        count = self._read_counter() + 1
        self._write_counter(count)
        return count >= self._config.trigger_after_n_runs

    def reset_counter(self) -> None:
        self._write_counter(0)

    def run_evolution_cycle(self) -> EvolutionResult:
        """Execute all enabled evolvers and return results."""
        if not self._config.enabled:
            return EvolutionResult(timestamp=datetime.now(UTC).isoformat())

        if not self.increment_and_check():
            return EvolutionResult(
                run_count=self._read_counter(),
                timestamp=datetime.now(UTC).isoformat(),
            )

        result = EvolutionResult(
            run_count=self._read_counter(),
            triggered=True,
            timestamp=datetime.now(UTC).isoformat(),
        )
        self.reset_counter()

        if self._config.prompt_evolver_enabled and self._planner is not None:
            try:
                evolver = PromptEvolver(self._repo_root, planner=self._planner)
                variant = evolver.evolve(context=self._assemble_evolver_context("prompt_evolver"))
                if variant is not None:
                    result.prompt_evolved = True
                    if self._config.auto_promote:
                        evolver.auto_promote_if_ready()
            except Exception as exc:
                result.errors.append(f"PromptEvolver: {exc}")
                logger.warning("PromptEvolver failed", exc_info=True)

        if self._config.plan_strategy_evolver_enabled and self._planner is not None:
            try:
                pse = PlanStrategyEvolver(self._repo_root, planner=self._planner)
                hint_set = pse.analyze(
                    context=self._assemble_evolver_context("plan_strategy_evolver")
                )
                if hint_set is not None and hint_set.hints:
                    result.plan_hints_generated = True
            except Exception as exc:
                result.errors.append(f"PlanStrategyEvolver: {exc}")
                logger.warning("PlanStrategyEvolver failed", exc_info=True)

        if self._config.harness_synthesizer_enabled and self._planner is not None:
            try:
                synth = HarnessSynthesizer(self._repo_root, planner=self._planner)
                candidates = synth.synthesize()
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

        if self._config.config_evolver_enabled:
            try:
                from spec_orch.services.config_evolver import ConfigEvolver

                cev = ConfigEvolver(self._repo_root)
                cev_result = cev.evolve(context=self._assemble_evolver_context("config_evolver"))
                if cev_result and cev_result.suggestions:
                    logger.info(
                        "ConfigEvolver proposed %d suggestion(s)",
                        len(cev_result.suggestions),
                    )
            except Exception as exc:
                result.errors.append(f"ConfigEvolver: {exc}")
                logger.warning("ConfigEvolver failed", exc_info=True)

        self._write_result(result)
        return result

    def _load_latest_manifest(self) -> dict[str, str]:
        """Load artifacts dict from the latest workspace's manifest, if any."""
        if not self._latest_workspace:
            return {}
        manifest_path = self._latest_workspace / "artifact_manifest.json"
        if not manifest_path.exists():
            return {}
        try:
            data = json.loads(manifest_path.read_text())
            artifacts: dict[str, str] = data.get("artifacts", {})
            return artifacts
        except (json.JSONDecodeError, OSError):
            logger.debug("Failed to load artifact manifest from %s", manifest_path, exc_info=True)
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
            "errors": result.errors,
        }
        with log_path.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _assemble_evolver_context(self, node_name: str) -> Any | None:
        """Best-effort ContextBundle assembly for evolver nodes."""
        if self._latest_workspace is None:
            return None
        try:
            issue = self._build_issue_from_latest_workspace()
            return self._context_assembler.assemble(
                get_node_context_spec(node_name),
                issue,
                self._latest_workspace,
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
