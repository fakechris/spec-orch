from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from spec_orch.runtime_core.readers import read_issue_execution_attempt

logger = logging.getLogger(__name__)


def _gather_evolution_metrics(repo_root: Path) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "prompt_variants": 0,
        "scoper_hints": 0,
        "policies": 0,
        "success_rate": 0.0,
        "total_runs": 0,
        "successful_runs": 0,
        "variants": [],
        "hint_categories": {},
        "run_trend": [],
    }
    try:
        evo_dir = repo_root / ".spec_orch_runs" / "evolution"
        if evo_dir.exists():
            prompts_dir = evo_dir / "prompts"
            if prompts_dir.exists():
                metrics["prompt_variants"] = len(list(prompts_dir.glob("*.md")))
            hints_path = evo_dir / "scoper_hints.json"
            if hints_path.exists():
                hints = json.loads(hints_path.read_text())
                metrics["scoper_hints"] = (
                    len(hints) if isinstance(hints, list) else len(hints.keys())
                )
                if isinstance(hints, dict):
                    metrics["hint_categories"] = {
                        k: len(v) if isinstance(v, list) else 1 for k, v in hints.items()
                    }
            policies_path = evo_dir / "policies.json"
            if policies_path.exists():
                policies = json.loads(policies_path.read_text())
                metrics["policies"] = (
                    len(policies) if isinstance(policies, list) else len(policies.keys())
                )

        _load_prompt_variant_metrics(repo_root, metrics)
        _load_run_trend(repo_root, metrics)
    except Exception:
        logger.warning("Failed to gather evolution metrics", exc_info=True)
    return metrics


def _load_prompt_variant_metrics(repo_root: Path, metrics: dict[str, Any]) -> None:
    try:
        from spec_orch.services.prompt_evolver import PromptEvolver

        evolver = PromptEvolver(repo_root)
        history = evolver.load_history()
        variants = []
        for v in history:
            variants.append(
                {
                    "variant_id": v.variant_id,
                    "total_runs": v.total_runs,
                    "successful_runs": v.successful_runs,
                    "success_rate": round(v.success_rate * 100, 1),
                    "is_active": v.is_active,
                    "is_candidate": v.is_candidate,
                    "rationale": v.rationale[:120] if v.rationale else "",
                    "created_at": v.created_at,
                }
            )
        metrics["variants"] = variants
        if variants:
            metrics["prompt_variants"] = len(variants)
    except ImportError:
        pass


def _load_run_trend(repo_root: Path, metrics: dict[str, Any]) -> None:
    runs_dir = repo_root / ".spec_orch_runs"
    if not runs_dir.exists():
        return
    total = 0
    success = 0
    trend: list[dict[str, Any]] = []
    for run_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        data = _read_run_summary(run_dir)
        if data is None:
            continue
        total += 1
        ok = data.get("state") == "merged" or data.get("mergeable")
        if ok:
            success += 1
        trend.append(
            {
                "run": run_dir.name,
                "ok": bool(ok),
                "cumulative_rate": round(success / total * 100, 1),
            }
        )
    metrics["total_runs"] = total
    metrics["successful_runs"] = success
    if total > 0:
        metrics["success_rate"] = round(success / total * 100, 1)
    metrics["run_trend"] = trend[-30:]


def _read_run_summary(run_dir: Path) -> dict[str, Any] | None:
    normalized = read_issue_execution_attempt(run_dir)
    if normalized is not None:
        gate = normalized.outcome.gate or {}
        return {
            "run_id": normalized.attempt_id,
            "issue_id": normalized.unit_id,
            "state": gate.get("state", "unknown"),
            "mergeable": gate.get("mergeable", False),
            "failed_conditions": gate.get("failed_conditions", []),
            "builder": normalized.outcome.build or {},
        }

    for file_path, _kind in (
        (run_dir / "run_artifact" / "conclusion.json", "conclusion"),
        (run_dir / "report.json", "report"),
    ):
        if not file_path.exists():
            continue
        try:
            data = json.loads(file_path.read_text())
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            logger.debug("Skipping malformed run summary: %s", file_path)
    return None


def _control_overview(repo_root: Path) -> dict[str, Any]:
    overview: dict[str, Any] = {
        "flywheel": {},
        "run_summary": {},
        "skills_count": 0,
        "reactions_count": 0,
        "execution_substrate": {
            "summary": {
                "active_work_count": 0,
                "agent_count": 0,
                "runtime_count": 0,
                "running_count": 0,
                "queued_count": 0,
                "degraded_count": 0,
                "intervention_needed_count": 0,
            },
            "active_work": [],
            "agents": [],
            "runtimes": [],
            "queue": [],
            "interventions": [],
            "execution_sessions": [],
            "execution_events": [],
            "resource_budgets": [],
            "pressure_signals": [],
            "admission_decisions": [],
        },
    }
    try:
        from spec_orch.services.eval_runner import EvalRunner

        runner = EvalRunner(repo_root)
        report = runner.evaluate()
        overview["run_summary"] = {
            "total": report.total,
            "passed": report.passed,
            "failed": report.failed,
            "pass_rate": round(report.pass_rate * 100, 1),
        }
    except Exception:
        logger.debug("Control tower: eval runner unavailable", exc_info=True)

    try:
        from spec_orch.services.skill_format import default_skills_dir, load_skills_from_dir

        skills_dir = default_skills_dir(repo_root)
        manifests, _warnings = load_skills_from_dir(skills_dir)
        overview["skills_count"] = len(manifests)
    except Exception:
        logger.debug("Control tower: skill loader unavailable", exc_info=True)

    reactions_path = repo_root / ".spec_orch" / "reactions.yaml"
    if reactions_path.exists():
        try:
            import yaml

            raw = yaml.safe_load(reactions_path.read_text()) or {}
            items = raw.get("reactions", [])
            overview["reactions_count"] = len(items) if isinstance(items, list) else 0
        except Exception:
            pass

    try:
        from spec_orch.services.execution_substrate import build_execution_substrate_snapshot

        overview["execution_substrate"] = build_execution_substrate_snapshot(repo_root)
    except Exception:
        logger.debug("Control tower: execution substrate unavailable", exc_info=True)

    overview["flywheel"] = {
        "P0_context_contract": "done",
        "P1_unified_artifact": "done",
        "P2_reaction_engine": "done",
        "P4_skill_format": "done",
        "P5_control_tower": "active",
        "P6_harness_evals": "done",
    }
    return overview


def _control_skills(repo_root: Path) -> dict[str, Any]:
    try:
        from spec_orch.services.skill_format import default_skills_dir, load_skills_from_dir

        skills_dir = default_skills_dir(repo_root)
        manifests, warnings = load_skills_from_dir(skills_dir)
        return {
            "skills": [m.to_dict() for m in manifests],
            "warnings": warnings,
        }
    except Exception:
        return {"skills": [], "warnings": ["skill_format module unavailable"]}


def _control_eval(repo_root: Path) -> dict[str, Any]:
    eval_path = repo_root / "eval_report.json"
    if eval_path.exists():
        try:
            data: dict[str, Any] = json.loads(eval_path.read_text())
            return data
        except (json.JSONDecodeError, OSError):
            pass
    try:
        from spec_orch.services.eval_runner import EvalRunner

        runner = EvalRunner(repo_root)
        return runner.evaluate().to_dict()
    except Exception:
        return {"total": 0, "error": "eval runner unavailable"}


def _control_eval_trigger(repo_root: Path) -> dict[str, Any]:
    try:
        from spec_orch.services.eval_runner import EvalRunner

        runner = EvalRunner(repo_root)
        report = runner.evaluate()
        out = repo_root / "eval_report.json"
        runner.write_report(report, out)
        return {"triggered": True, "report": report.to_dict()}
    except Exception as exc:
        return {"triggered": False, "error": str(exc)}


def _control_reactions(repo_root: Path) -> dict[str, Any]:
    try:
        from spec_orch.services.reaction_engine import ReactionEngine

        engine = ReactionEngine(repo_root)
        rules = [
            {
                "name": rule.name,
                "trigger": rule.trigger,
                "action": rule.action,
                "enabled": rule.enabled,
                "params": rule.params,
            }
            for rule in engine.rules
        ]
        return {
            "rules": rules,
            "warnings": engine.load_warnings,
        }
    except Exception:
        return {"rules": [], "warnings": ["reaction engine unavailable"]}


def _control_degradation(repo_root: Path) -> dict[str, Any]:
    try:
        from spec_orch.services.degradation_detector import DegradationDetector

        detector = DegradationDetector(repo_root)
        report = detector.detect()
        return report.to_dict()
    except Exception as exc:
        logger.warning("Degradation detection failed for Control Tower", exc_info=True)
        return {"degraded": False, "error": str(exc)}


def _gather_run_history(repo_root: Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for base in [repo_root / ".worktrees", repo_root / ".spec_orch_runs"]:
        if not base.exists():
            continue
        for ws in sorted(base.iterdir()):
            normalized = read_issue_execution_attempt(ws)
            if normalized is not None:
                gate = normalized.outcome.gate or {}
                builder = normalized.outcome.build or {}
                runs.append(
                    {
                        "issue_id": normalized.unit_id,
                        "title": ws.name,
                        "state": gate.get("state", "unknown"),
                        "mergeable": gate.get("mergeable", False),
                        "failed_conditions": gate.get("failed_conditions", []),
                        "builder_adapter": builder.get("adapter", "")
                        if isinstance(builder, dict)
                        else "",
                        "builder_succeeded": builder.get("succeeded", False)
                        if isinstance(builder, dict)
                        else False,
                    }
                )
                continue

            report = ws / "report.json"
            conclusion = ws / "run_artifact" / "conclusion.json"
            try:
                report_data: dict[str, Any] = {}
                if report.exists():
                    maybe_report = json.loads(report.read_text())
                    if isinstance(maybe_report, dict):
                        report_data = maybe_report
                if conclusion.exists():
                    cdata = json.loads(conclusion.read_text())
                    if not isinstance(cdata, dict):
                        cdata = {}
                    data = {
                        "issue_id": cdata.get("issue_id", ws.name),
                        "title": report_data.get("title", ws.name),
                        "state": cdata.get("state", "unknown"),
                        "mergeable": cdata.get("mergeable", False),
                        "failed_conditions": cdata.get("failed_conditions", []),
                        "builder": report_data.get("builder", {}),
                    }
                elif report.exists():
                    data = report_data
                else:
                    continue
                runs.append(
                    {
                        "issue_id": data.get("issue_id", ws.name),
                        "title": data.get("title", ws.name),
                        "state": data.get("state", "unknown"),
                        "mergeable": data.get("mergeable", False),
                        "failed_conditions": data.get("failed_conditions", []),
                        "builder_adapter": data.get("builder", {}).get("adapter", ""),
                        "builder_succeeded": data.get("builder", {}).get("succeeded", False),
                    }
                )
            except (json.JSONDecodeError, OSError):
                continue
    return runs


def _get_spec_content(repo_root: Path, mission_id: str) -> str | None:
    spec_path = repo_root / "docs" / "specs" / mission_id / "spec.md"
    if spec_path.exists():
        return spec_path.read_text()
    return None


__all__ = [
    "_control_degradation",
    "_control_eval",
    "_control_eval_trigger",
    "_control_overview",
    "_control_reactions",
    "_control_skills",
    "_gather_evolution_metrics",
    "_gather_run_history",
    "_get_spec_content",
]
