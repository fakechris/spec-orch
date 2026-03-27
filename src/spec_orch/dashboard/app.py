# ruff: noqa: E501

"""Lightweight web dashboard for spec-orch — pipeline status and execution results.

Start with:  spec-orch dashboard
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .approvals import (
    _record_approval_action as _approval_record_approval_action,
)
from .approvals import (
    _resolve_approval_action as _approval_resolve_approval_action,
)
from .missions import _gather_inbox as _missions_gather_inbox
from .missions import _gather_lifecycle_states as _missions_gather_lifecycle_states
from .missions import _gather_mission_detail as _missions_gather_mission_detail
from .missions import _gather_missions as _missions_gather_missions
from .transcript import _gather_packet_transcript as _transcript_gather_packet_transcript
from .transcript import (
    _gather_round_evidence_blocks as _transcript_gather_round_evidence_blocks,
)
from .transcript import _group_transcript_blocks as _transcript_group_transcript_blocks
from .transcript import _transcript_block_from_entry as _transcript_block_from_entry_impl

logger = logging.getLogger(__name__)


def _get_event_bus():
    try:
        from spec_orch.services.event_bus import get_event_bus

        return get_event_bus()
    except ImportError:
        return None


def _get_lifecycle_manager(repo_root: Path):
    try:
        from spec_orch.services.lifecycle_manager import MissionLifecycleManager

        return MissionLifecycleManager(repo_root)
    except ImportError:
        return None


def _get_conversation_service(repo_root: Path):
    try:
        from spec_orch.services.conversation_service import ConversationService

        return ConversationService(repo_root=repo_root)
    except Exception:
        return None


def _gather_packet_transcript(
    repo_root: Path,
    mission_id: str,
    packet_id: str,
) -> dict[str, Any] | None:
    telemetry_dir = (
        repo_root / "docs" / "specs" / mission_id / "workers" / packet_id / "telemetry"
    )
    activity_path = telemetry_dir / "activity.log"
    events_path = telemetry_dir / "events.jsonl"
    incoming_path = telemetry_dir / "incoming_events.jsonl"
    if not telemetry_dir.exists():
        return {
            "mission_id": mission_id,
            "packet_id": packet_id,
            "entries": [],
            "summary": {
                "entry_count": 0,
                "kind_counts": {},
                "block_counts": {},
                "latest_timestamp": None,
            },
            "milestones": [],
            "blocks": [],
            "telemetry": {
                "activity_log": None,
                "events": None,
                "incoming": None,
            },
        }

    entries: list[dict[str, Any]] = []
    milestones: list[dict[str, Any]] = []
    if activity_path.exists():
        for line in activity_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            ts, _, message = line.partition(" ")
            entries.append(
                {
                    "kind": "activity",
                    "timestamp": ts if message else "",
                    "message": message or line,
                    "raw": line,
                    "source_path": str(activity_path.relative_to(repo_root)),
                }
            )

    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            entries.append(
                {
                    "kind": "event",
                    "timestamp": payload.get("timestamp", ""),
                    "message": payload.get("message", payload.get("event_type", "event")),
                    "event_type": payload.get("event_type", ""),
                    "raw": payload,
                    "source_path": str(events_path.relative_to(repo_root)),
                }
            )
            event_type = payload.get("event_type", "")
            if isinstance(event_type, str) and event_type.startswith("mission_packet_"):
                milestones.append(
                    {
                        "timestamp": payload.get("timestamp", ""),
                        "event_type": event_type,
                        "message": payload.get("message", event_type),
                    }
                )

    if incoming_path.exists():
        for line in incoming_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            entries.append(
                {
                    "kind": "incoming",
                    "timestamp": payload.get("ts", payload.get("timestamp", "")),
                    "message": payload.get("excerpt", payload.get("message", payload.get("kind", ""))),
                    "event_type": payload.get("kind", ""),
                    "raw": payload,
                    "source_path": str(incoming_path.relative_to(repo_root)),
                }
            )

    entries.sort(key=lambda entry: (entry.get("timestamp", ""), entry.get("kind", "")))
    kind_counts: dict[str, int] = {}
    latest_timestamp: str | None = None
    for entry in entries:
        kind = str(entry.get("kind", "event"))
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        timestamp = entry.get("timestamp")
        if isinstance(timestamp, str) and timestamp:
            latest_timestamp = timestamp
    blocks = [_transcript_block_from_entry(entry) for entry in entries]
    blocks = _group_transcript_blocks(blocks)
    blocks.extend(_gather_round_evidence_blocks(repo_root, mission_id, packet_id))
    blocks.sort(key=lambda block: (block.get("timestamp", ""), block.get("block_type", "")))
    block_counts: dict[str, int] = {}
    for block in blocks:
        block_type = str(block.get("block_type", "event"))
        block_counts[block_type] = block_counts.get(block_type, 0) + 1

    return {
        "mission_id": mission_id,
        "packet_id": packet_id,
        "entries": entries,
        "summary": {
            "entry_count": len(entries),
            "kind_counts": kind_counts,
            "block_counts": block_counts,
            "latest_timestamp": latest_timestamp,
        },
        "milestones": milestones,
        "blocks": blocks,
        "telemetry": {
            "activity_log": str(activity_path.relative_to(repo_root)) if activity_path.exists() else None,
            "events": str(events_path.relative_to(repo_root)) if events_path.exists() else None,
            "incoming": str(incoming_path.relative_to(repo_root)) if incoming_path.exists() else None,
        },
    }


def _transcript_block_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    kind = str(entry.get("kind", "event"))
    event_type = str(entry.get("event_type", ""))
    message = str(entry.get("message", event_type or kind))
    raw = entry.get("raw")

    if kind == "activity":
        body = raw if isinstance(raw, str) else message
        return {
            "block_type": "activity",
            "timestamp": str(entry.get("timestamp", "")),
            "title": message,
            "body": body,
            "source_path": entry.get("source_path"),
        }

    if kind == "incoming":
        return {
            "block_type": "message",
            "timestamp": str(entry.get("timestamp", "")),
            "title": message,
            "body": event_type or kind,
            "source_path": entry.get("source_path"),
        }

    if event_type.startswith("mission_packet_"):
        return {
            "block_type": "milestone",
            "timestamp": str(entry.get("timestamp", "")),
            "title": message,
            "body": event_type,
            "source_path": entry.get("source_path"),
        }

    if "tool_call" in event_type:
        return {
            "block_type": "tool",
            "timestamp": str(entry.get("timestamp", "")),
            "title": message,
            "body": event_type,
            "source_path": entry.get("source_path"),
        }

    return {
        "block_type": "event",
        "timestamp": str(entry.get("timestamp", "")),
        "title": message,
        "body": event_type or kind,
        "source_path": entry.get("source_path"),
    }


def _group_transcript_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: list[dict[str, Any]] = []
    current_tool_burst: list[dict[str, Any]] = []

    def flush_tool_burst() -> None:
        nonlocal current_tool_burst
        if not current_tool_burst:
            return
        if len(current_tool_burst) == 1:
            grouped.extend(current_tool_burst)
        else:
            grouped.append(
                {
                    "block_type": "command_burst",
                    "timestamp": current_tool_burst[0].get("timestamp", ""),
                    "title": f"{len(current_tool_burst)} tool events",
                    "body": " • ".join(
                        str(item.get("title", item.get("body", "tool event")))
                        for item in current_tool_burst
                    ),
                    "source_path": current_tool_burst[0].get("source_path"),
                    "items": current_tool_burst,
                }
            )
        current_tool_burst = []

    for block in blocks:
        if block.get("block_type") == "tool":
            current_tool_burst.append(block)
            continue
        flush_tool_burst()
        grouped.append(block)

    flush_tool_burst()
    return grouped


def _gather_round_evidence_blocks(
    repo_root: Path,
    mission_id: str,
    packet_id: str,
) -> list[dict[str, Any]]:
    rounds_dir = repo_root / "docs" / "specs" / mission_id / "rounds"
    if not rounds_dir.exists():
        return []

    from spec_orch.domain.models import RoundSummary, VisualEvaluationResult

    blocks: list[dict[str, Any]] = []
    for round_dir in sorted(rounds_dir.glob("round-*")):
        summary_path = round_dir / "round_summary.json"
        if not summary_path.exists():
            continue
        try:
            summary = RoundSummary.from_dict(json.loads(summary_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not any(result.get("packet_id") == packet_id for result in summary.worker_results):
            continue

        timestamp = summary.completed_at or summary.started_at or ""
        if summary.decision is not None:
            blocks.append(
                {
                    "block_type": "supervisor",
                    "timestamp": timestamp,
                    "title": summary.decision.summary or "Supervisor decision",
                    "body": summary.decision.action.value,
                    "artifact_path": str((round_dir / "supervisor_review.md").relative_to(repo_root)),
                }
            )

        visual_path = round_dir / "visual_evaluation.json"
        if visual_path.exists():
            try:
                visual = VisualEvaluationResult.from_dict(
                    json.loads(visual_path.read_text(encoding="utf-8"))
                )
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            blocks.append(
                {
                    "block_type": "visual_finding",
                    "timestamp": timestamp,
                    "title": visual.summary or "Visual evaluation result",
                    "body": visual.evaluator,
                    "artifact_path": str(visual_path.relative_to(repo_root)),
                }
            )

    return blocks


_gather_packet_transcript = _transcript_gather_packet_transcript
_transcript_block_from_entry = _transcript_block_from_entry_impl
_group_transcript_blocks = _transcript_group_transcript_blocks
_gather_round_evidence_blocks = _transcript_gather_round_evidence_blocks
_gather_missions = _missions_gather_missions
_gather_inbox = _missions_gather_inbox
_gather_mission_detail = _missions_gather_mission_detail
_gather_lifecycle_states = _missions_gather_lifecycle_states
_record_approval_action = _approval_record_approval_action
_resolve_approval_action = _approval_resolve_approval_action


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
    for file_path, kind in (
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
            logger.debug("Skipping malformed %s: %s", kind, file_path)
    return None


def _control_overview(repo_root: Path) -> dict[str, Any]:
    """Aggregate overview for the Control Tower (P5)."""
    overview: dict[str, Any] = {
        "flywheel": {},
        "run_summary": {},
        "skills_count": 0,
        "reactions_count": 0,
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
        manifests, _ = load_skills_from_dir(skills_dir)
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
    """List loaded skill manifests for the Control Tower."""
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
    """Latest eval report for the Control Tower."""
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
    """Trigger a fresh eval run and return the report."""
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
    """Return loaded reaction rules for the Control Tower."""
    try:
        from spec_orch.services.reaction_engine import ReactionEngine

        engine = ReactionEngine(repo_root)
        rules = [
            {
                "name": r.name,
                "trigger": r.trigger,
                "action": r.action,
                "enabled": r.enabled,
                "params": r.params,
            }
            for r in engine.rules
        ]
        return {
            "rules": rules,
            "warnings": engine.load_warnings,
        }
    except Exception:
        return {"rules": [], "warnings": ["reaction engine unavailable"]}


def _control_degradation(repo_root: Path) -> dict[str, Any]:
    """Run degradation detection for the Control Tower."""
    try:
        from spec_orch.services.degradation_detector import DegradationDetector

        detector = DegradationDetector(repo_root)
        report = detector.detect()
        return report.to_dict()
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Degradation detection failed for Control Tower", exc_info=True
        )
        return {"degraded": False, "error": str(exc)}


def _gather_run_history(repo_root: Path) -> list[dict[str, Any]]:
    """Scan workspace directories for run reports."""
    runs: list[dict[str, Any]] = []
    for base in [repo_root / ".worktrees", repo_root / ".spec_orch_runs"]:
        if not base.exists():
            continue
        for ws in sorted(base.iterdir()):
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


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>spec-orch dashboard</title>
<link rel="stylesheet" href="/static/operator-console.css"/>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0f1117;--card:#1a1d27;--border:#2a2d3a;--text:#e1e4eb;--dim:#8b8fa3;
  --green:#22c55e;--amber:#f59e0b;--red:#ef4444;--blue:#3b82f6;--purple:#a855f7;
  --accent:#6366f1;--card-hover:#22253a;
  font-family:'Inter',system-ui,-apple-system,sans-serif;
}
body{background:var(--bg);color:var(--text);min-height:100vh;display:flex;flex-direction:column}

/* ---- header ---- */
.header{display:flex;align-items:center;gap:.75rem;padding:.75rem 1.5rem;
  border-bottom:1px solid var(--border);background:var(--card)}
.header h1{font-size:1.1rem;font-weight:700;display:flex;align-items:center;gap:.4rem}
.header h1 .tag{background:var(--accent);color:#fff;padding:.1rem .45rem;border-radius:4px;
  font-size:.65rem;font-weight:600;letter-spacing:.02em}
.header-spacer{flex:1}
.status-dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.status-dot.connected{background:var(--green);box-shadow:0 0 6px var(--green)}
.status-dot.disconnected{background:var(--red)}
.header-label{font-size:.75rem;color:var(--dim);margin-left:.25rem}
.btn{padding:.35rem .75rem;border:1px solid var(--border);border-radius:6px;
  background:var(--card);color:var(--text);cursor:pointer;font-size:.78rem;
  transition:all .15s}
.btn:hover{border-color:var(--accent);background:var(--card-hover)}
.btn-primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn-primary:hover{opacity:.9}
.btn-green{background:var(--green);border-color:var(--green);color:#fff}
.btn-green:hover{opacity:.9}
.btn-amber{background:var(--amber);border-color:var(--amber);color:#000}
.btn-amber:hover{opacity:.9}
.btn-red{background:rgba(239,68,68,.15);border-color:var(--red);color:var(--red)}
.btn-red:hover{background:rgba(239,68,68,.25)}
.btn-sm{padding:.2rem .5rem;font-size:.7rem}

/* ---- layout ---- */
.main-wrap{display:flex;flex:1;overflow:hidden}
.main-content{flex:1;overflow-y:auto;padding:1.25rem}
.sidebar{width:0;overflow:hidden;transition:width .25s ease;border-left:1px solid var(--border);
  display:flex;flex-direction:column;background:var(--card)}
.sidebar.open{width:380px}

/* ---- grid ---- */
.grid{display:grid;gap:1rem;grid-template-columns:repeat(auto-fill,minmax(460px,1fr))}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:1.25rem;
  transition:background .4s,border-color .3s}
.card.flash{border-color:var(--accent);background:var(--card-hover)}
.card-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:.75rem}
.card-title{font-size:.95rem;font-weight:600;word-break:break-word}
.badge{display:inline-block;padding:.1rem .5rem;border-radius:4px;font-size:.68rem;
  font-weight:600;text-transform:uppercase;letter-spacing:.03em}
.badge.approved{background:rgba(34,197,94,.15);color:var(--green)}
.badge.completed{background:rgba(168,85,247,.15);color:var(--purple)}
.badge.drafting{background:rgba(139,143,163,.15);color:var(--dim)}
.badge.in_progress,.badge.executing,.badge.promoting,.badge.planning,.badge.planned{
  background:rgba(59,130,246,.15);color:var(--blue)}
.badge.failed{background:rgba(239,68,68,.15);color:var(--red)}
.badge.all_done{background:rgba(245,158,11,.15);color:var(--amber)}
.badge.retrospecting,.badge.evolving{background:rgba(168,85,247,.15);color:var(--purple)}

/* ---- pipeline bar ---- */
.pipeline{display:flex;gap:2px;margin:.75rem 0;flex-wrap:wrap}
.stage{width:28px;height:8px;border-radius:2px;cursor:pointer;transition:transform .1s}
.stage:hover{transform:scaleY(1.8)}
.stage.done{background:var(--green)}
.stage.current{background:var(--amber);animation:pulse 1.5s infinite}
.stage.pending{background:var(--border)}
.stage.skipped{background:var(--border);opacity:.4}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
.progress-text{font-size:.75rem;color:var(--dim);margin-top:.25rem}

/* ---- issue progress ---- */
.issue-progress{margin:.5rem 0}
.issue-bar{height:6px;background:var(--border);border-radius:3px;overflow:hidden}
.issue-bar-fill{height:100%;background:var(--blue);border-radius:3px;transition:width .5s}
.issue-label{font-size:.72rem;color:var(--dim);margin-top:.2rem}

/* ---- waves ---- */
.waves{margin-top:.75rem}
.wave{border-left:2px solid var(--border);padding-left:.75rem;margin-bottom:.5rem}
.wave-label{font-size:.75rem;color:var(--dim);font-weight:600;margin-bottom:.25rem}
.packet{font-size:.8rem;padding:.15rem 0;display:flex;align-items:center;gap:.35rem}
.run-class{font-size:.65rem;padding:.05rem .3rem;border-radius:2px;
  background:rgba(99,102,241,.15);color:var(--accent)}
.linear-id{font-size:.65rem;color:var(--dim)}

/* ---- card meta / actions ---- */
.card-actions{display:flex;gap:.4rem;margin-top:.75rem;flex-wrap:wrap}
.meta{font-size:.75rem;color:var(--dim);margin-top:.5rem}
.error-banner{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);
  border-radius:4px;padding:.35rem .6rem;font-size:.75rem;color:var(--red);margin:.5rem 0}

/* ---- chat sidebar ---- */
.chat-header{display:flex;align-items:center;padding:.65rem .75rem;border-bottom:1px solid var(--border)}
.chat-header h3{font-size:.85rem;flex:1}
.chat-messages{flex:1;overflow-y:auto;padding:.75rem;display:flex;flex-direction:column;gap:.5rem}
.chat-msg{max-width:90%;padding:.45rem .65rem;border-radius:8px;font-size:.82rem;line-height:1.45;
  word-break:break-word}
.chat-msg.user{align-self:flex-end;background:var(--accent);color:#fff;border-bottom-right-radius:2px}
.chat-msg.bot{align-self:flex-start;background:var(--border);color:var(--text);border-bottom-left-radius:2px}
.chat-msg.system{align-self:center;background:transparent;color:var(--dim);font-size:.72rem;
  font-style:italic;text-align:center}
.chat-input-wrap{display:flex;padding:.5rem;border-top:1px solid var(--border);gap:.35rem}
.chat-input{flex:1;background:var(--bg);border:1px solid var(--border);border-radius:6px;
  padding:.45rem .6rem;color:var(--text);font-size:.82rem;outline:none}
.chat-input:focus{border-color:var(--accent)}
.chat-input::placeholder{color:var(--dim)}

/* ---- bottom bar ---- */
.bottom-bar{display:flex;align-items:center;gap:1.5rem;padding:.5rem 1.5rem;
  border-top:1px solid var(--border);background:var(--card);font-size:.75rem;color:var(--dim)}
.metric{display:flex;align-items:center;gap:.3rem}
.metric-value{color:var(--text);font-weight:600}
.metric-label{color:var(--dim)}

/* ---- empty state ---- */
.empty{text-align:center;padding:3rem;color:var(--dim)}

/* ---- tooltip ---- */
.tooltip{position:relative}
.tooltip:hover::after{content:attr(data-tip);position:absolute;bottom:calc(100% + 4px);
  left:50%;transform:translateX(-50%);background:#000;color:#fff;padding:.25rem .5rem;
  border-radius:4px;font-size:.7rem;white-space:nowrap;z-index:10}

/* ---- scrollbar ---- */
::-webkit-scrollbar{width:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--dim)}
</style>
</head>
<body>

<!-- ===== HEADER ===== -->
<div class="header">
  <h1>spec-orch <span class="tag">dashboard</span></h1>
  <div class="header-spacer"></div>
  <span class="status-dot disconnected" id="ws-dot"></span>
  <span class="header-label" id="ws-label">disconnected</span>
  <button class="btn" onclick="load()">Refresh</button>
  <button class="btn btn-primary" id="btn-new-mission" onclick="openNewMission()">+ New Mission</button>
</div>

<!-- ===== MAIN ===== -->
<div class="main-wrap">
  <div class="main-content" id="main">
    <div id="operator-shell" class="operator-shell">
      <aside class="operator-pane operator-nav">
        <div class="operator-nav-header">
          <h2>Mission Control</h2>
        </div>
        <div class="operator-nav-modes">
          <span class="operator-mode" id="inbox-attention-chip">Inbox</span>
          <span class="operator-mode">Missions</span>
          <span class="operator-mode">Approvals</span>
          <span class="operator-mode">Evidence</span>
        </div>
        <div id="inbox-list" class="mission-list"></div>
        <div id="mission-list" class="mission-list"></div>
      </aside>

      <section class="operator-pane operator-main">
        <div class="operator-main-header">
          <h2>Mission Detail</h2>
        </div>
        <div id="mission-detail-view" class="mission-detail-view">
          <div id="packet-transcript-view" class="transcript-list"></div>
        </div>
      </section>

      <aside class="operator-pane operator-context">
        <div class="operator-context-header">
          <h2>Context Rail</h2>
        </div>
        <div id="operator-context-rail" class="mission-detail-view operator-context-rail">
          <div id="transcript-inspector"></div>
        </div>
      </aside>
    </div>
  </div>

  <!-- ===== SIDEBAR CHAT ===== -->
  <div class="sidebar" id="sidebar">
    <div class="chat-header">
      <h3 id="chat-title">Discuss</h3>
      <button class="btn btn-sm" onclick="closeSidebar()">&times;</button>
    </div>
    <div class="chat-messages" id="chat-messages"></div>
    <div class="chat-input-wrap">
      <input class="chat-input" id="chat-input" placeholder="Type a message… (@freeze, @approve)"
             onkeydown="if(event.key==='Enter')sendChat()"/>
      <button class="btn btn-primary btn-sm" onclick="sendChat()">Send</button>
    </div>
  </div>
</div>

<!-- ===== EVOLUTION PANEL ===== -->
<div class="bottom-bar" id="bottom-bar" style="cursor:pointer" onclick="toggleEvoPanel()">
  <div class="metric"><span class="metric-label">Prompts:</span><span class="metric-value" id="m-prompts">—</span></div>
  <div class="metric"><span class="metric-label">Hints:</span><span class="metric-value" id="m-hints">—</span></div>
  <div class="metric"><span class="metric-label">Policies:</span><span class="metric-value" id="m-policies">—</span></div>
  <div class="metric"><span class="metric-label">Success:</span><span class="metric-value" id="m-success">—</span></div>
  <div class="metric"><span class="metric-label">Runs:</span><span class="metric-value" id="m-runs">—</span></div>
  <div style="flex:1"></div>
  <span style="font-size:.7rem;color:var(--dim)">▼ Evolution Details</span>
  <span id="event-log" style="font-size:.7rem;color:var(--dim);max-width:30%;overflow:hidden;
    text-overflow:ellipsis;white-space:nowrap;margin-left:.5rem"></span>
</div>
<div id="evo-panel" style="display:none;background:var(--card);border-top:1px solid var(--border);padding:1rem;max-height:50vh;overflow-y:auto">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
    <div>
      <h3 style="margin:0 0 .5rem;color:var(--accent);font-size:.9rem">Prompt Variants</h3>
      <div id="evo-variants" style="font-size:.8rem"></div>
    </div>
    <div>
      <h3 style="margin:0 0 .5rem;color:var(--accent);font-size:.9rem">Success Rate Trend</h3>
      <div id="evo-trend" style="height:80px;display:flex;align-items:flex-end;gap:2px"></div>
      <div id="evo-trend-labels" style="font-size:.65rem;color:var(--dim);margin-top:.25rem"></div>
    </div>
  </div>
</div>

<script>
/* ===== STATE ===== */
let missions = [];
let lifecycleStates = {};
let ws = null;
let wsRetryMs = 1000;
let chatThreadId = null;
let chatMessages = [];
let selectedMissionId = null;
let selectedMissionDetail = null;
let selectedPacketId = null;
let selectedPacketTranscript = null;
let selectedTranscriptFilter = 'all';
let selectedTranscriptBlockIndex = null;
let inboxSummary = {counts:{approvals:0, paused:0, failed:0, attention:0}, items:[]};

/* ===== DATA LOADING ===== */
async function load() {
  try {
    const [mRes, lcRes, inboxRes] = await Promise.all([
      fetch('/api/missions'),
      fetch('/api/lifecycle').catch(() => ({ok:false})),
      fetch('/api/inbox').catch(() => ({ok:false}))
    ]);
    missions = await mRes.json();
    if (lcRes.ok) {
      lifecycleStates = await lcRes.json();
    }
    if (inboxRes.ok) {
      inboxSummary = await inboxRes.json();
    }
    renderMissions();
    await ensureMissionSelection();
  } catch(e) {
    console.error('load failed', e);
  }
}

let evoPanelOpen = false;
function toggleEvoPanel() {
  evoPanelOpen = !evoPanelOpen;
  document.getElementById('evo-panel').style.display = evoPanelOpen ? 'block' : 'none';
}

async function loadEvolution() {
  try {
    const r = await fetch('/api/evolution');
    if (!r.ok) return;
    const d = await r.json();
    document.getElementById('m-prompts').textContent = d.prompt_variants ?? '—';
    document.getElementById('m-hints').textContent = d.scoper_hints ?? '—';
    document.getElementById('m-policies').textContent = d.policies ?? '—';
    document.getElementById('m-success').textContent = d.success_rate != null ? d.success_rate + '%' : '—';
    document.getElementById('m-runs').textContent = d.total_runs ?? '—';
    renderEvoVariants(d.variants || []);
    renderEvoTrend(d.run_trend || []);
  } catch(e) {}
}

function renderEvoVariants(variants) {
  const el = document.getElementById('evo-variants');
  if (!el) return;
  if (variants.length === 0) { el.innerHTML = '<span style="color:var(--dim)">No prompt variants yet</span>'; return; }
  el.innerHTML = variants.map(v => {
    const vid = escHtml(v.variant_id);
    const rat = escHtml(v.rationale || '');
    const badge = v.is_active ? '<span style="color:#4ade80;font-weight:bold">● active</span>' : v.is_candidate ? '<span style="color:#facc15">◎ candidate</span>' : '<span style="color:var(--dim)">○</span>';
    const pct = Number(v.success_rate) || 0;
    const bar = v.total_runs > 0 ? `<div style="display:inline-block;width:60px;height:8px;background:var(--border);border-radius:4px;overflow:hidden;vertical-align:middle"><div style="width:${pct}%;height:100%;background:${pct>=70?'#4ade80':pct>=40?'#facc15':'#f87171'}"></div></div>` : '';
    const ratSnip = rat.length > 50 ? rat.slice(0,50) + '…' : rat;
    return `<div style="padding:.25rem 0;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:.5rem">${badge} <strong>${vid}</strong> ${bar} <span>${pct}%</span> <span style="color:var(--dim)">(${Number(v.successful_runs)||0}/${Number(v.total_runs)||0})</span>${rat ? `<span style="color:var(--dim);font-size:.7rem;margin-left:auto" title="${rat}">${ratSnip}</span>` : ''}</div>`;
  }).join('');
}

function renderEvoTrend(trend) {
  const el = document.getElementById('evo-trend');
  const labels = document.getElementById('evo-trend-labels');
  if (!el) return;
  if (trend.length === 0) { el.innerHTML = '<span style="color:var(--dim);font-size:.8rem">No run data yet</span>'; return; }
  const maxH = 70;
  el.innerHTML = trend.map(t => {
    const h = Math.max(3, (t.cumulative_rate / 100) * maxH);
    const color = t.ok ? '#4ade80' : '#f87171';
    const runName = escHtml(t.run);
    return `<div title="${runName}: ${t.cumulative_rate}%" style="width:${Math.max(4, Math.floor(200/trend.length))}px;height:${h}px;background:${color};border-radius:2px 2px 0 0;transition:height .3s"></div>`;
  }).join('');
  if (labels && trend.length > 0) {
    const last = trend[trend.length - 1];
    labels.textContent = `${trend.length} runs | latest: ${last.cumulative_rate}% cumulative`;
  }
}

/* ===== RENDER ===== */
function phaseFor(m) {
  const lc = lifecycleStates[m.mission_id];
  return lc ? lc.phase : m.status;
}

function renderMissions() {
  const root = document.getElementById('mission-list');
  if (!missions.length) {
    selectedMissionId = null;
    selectedMissionDetail = null;
    selectedPacketId = null;
    root.innerHTML = '<div class="empty-panel">No missions found yet.</div>';
    renderMissionDetail(null);
    renderContextRail(null);
    return;
  }
  if (!selectedMissionId || !missions.some(m => m.mission_id === selectedMissionId)) {
    selectedMissionId = missions[0].mission_id;
  }
  root.innerHTML = missions.map(m => {
    const phase = phaseFor(m);
    const lc = lifecycleStates[m.mission_id];
    const pipelineText = `${m.pipeline_done}/${m.pipeline_total} stages complete`;
    const issueSummary = lc && phase === 'executing'
      ? `${(lc.completed_issues || []).length}/${(lc.issue_ids || []).length || 1} issues complete`
      : m.plan ? `${m.plan.packet_count} packets across ${m.plan.wave_count} waves` : 'Spec in progress';
    return `<button class="mission-list-item ${selectedMissionId === m.mission_id ? 'active' : ''}"
      id="card-${m.mission_id}" data-mid="${m.mission_id}" onclick="selectMission('${m.mission_id}')">
      <div class="mission-list-title">${escHtml(m.title)}</div>
      <div class="mission-list-meta">
        <span class="badge ${phase}">${phase}</span>
        <span>${pipelineText}</span>
      </div>
      <div class="mission-list-meta">
        <span>${escHtml(m.mission_id)}</span>
        <span>${escHtml(issueSummary)}</span>
      </div>
    </button>`;
  }).join('');
  renderInboxSummary();
}

function renderInboxSummary() {
  const chip = document.getElementById('inbox-attention-chip');
  const list = document.getElementById('inbox-list');
  if (!chip) return;
  const attention = inboxSummary?.counts?.attention || 0;
  chip.textContent = attention ? `Inbox ${attention}` : 'Inbox';
  chip.title = attention
    ? `${inboxSummary.counts.approvals || 0} approvals, ${inboxSummary.counts.paused || 0} paused, ${inboxSummary.counts.failed || 0} failed`
    : 'No operator attention items';
  if (!list) return;
  const items = inboxSummary?.items || [];
  if (!items.length) {
    list.innerHTML = '<div class="empty-panel">No approvals, paused missions, or failures.</div>';
    return;
  }
  list.innerHTML = items.map(item => `
    <button class="mission-list-item" type="button" onclick="selectMission('${item.mission_id}')">
      <div class="mission-list-title">${escHtml(item.title)}</div>
      <div class="mission-list-meta">
        <span class="badge ${escHtml(item.phase || item.kind || 'attention')}">${escHtml(item.kind)}</span>
        ${item.current_round ? `<span>Round ${escHtml(String(item.current_round))}</span>` : ''}
      </div>
      <div class="mission-list-meta">
        <span>${escHtml(item.summary || '')}</span>
      </div>
      ${item.latest_operator_action ? `
        <div class="mission-list-meta">
          <span class="detail-chip">${escHtml(item.latest_operator_action.label || item.latest_operator_action.action_key || 'Action')}</span>
          <span>${escHtml(item.latest_operator_action.effect || 'guidance_sent')}</span>
        </div>
      ` : ''}
    </button>
  `).join('');
}

async function ensureMissionSelection() {
  if (!selectedMissionId) return;
  await selectMission(selectedMissionId, {force:true});
}

async function selectMission(missionId, options = {}) {
  if (!options.force && missionId === selectedMissionId && selectedMissionDetail) {
    renderMissions();
    renderMissionDetail(selectedMissionDetail);
    renderContextRail(selectedMissionDetail);
    return;
  }
  selectedMissionId = missionId;
  renderMissions();
  renderMissionDetailLoading();
  renderContextRailLoading();
  try {
    const response = await fetch(`/api/missions/${missionId}/detail`);
    if (!response.ok) throw new Error(`Failed to load mission detail (${response.status})`);
    selectedMissionDetail = await response.json();
    selectedPacketId = selectedMissionDetail.packets?.[0]?.packet_id || null;
    selectedPacketTranscript = null;
    selectedTranscriptFilter = 'all';
    selectedTranscriptBlockIndex = null;
    renderMissionDetail(selectedMissionDetail);
    renderContextRail(selectedMissionDetail);
    await loadSelectedPacketTranscript();
  } catch (error) {
    console.error(error);
    selectedMissionDetail = null;
    selectedPacketTranscript = null;
    renderMissionDetailError(error);
    renderContextRailError(error);
  }
}

function renderMissionDetailLoading() {
  const view = document.getElementById('mission-detail-view');
  view.innerHTML = '<div class="empty-panel">Loading mission detail…</div>';
}

function renderContextRailLoading() {
  const rail = document.getElementById('operator-context-rail');
  rail.innerHTML = '<div class="empty-panel">Loading context…</div>';
}

function renderMissionDetailError(error) {
  const view = document.getElementById('mission-detail-view');
  view.innerHTML = `<div class="error-banner">${escHtml(error?.message || 'Failed to load mission detail')}</div>`;
}

function renderContextRailError(error) {
  const rail = document.getElementById('operator-context-rail');
  rail.innerHTML = `<div class="error-banner">${escHtml(error?.message || 'Failed to load context')}</div>`;
}

function renderMissionDetail(detail) {
  const view = document.getElementById('mission-detail-view');
  if (!detail) {
    view.innerHTML = '<div class="empty-panel">Select a mission to inspect its rounds, packets, and evidence.</div>';
    return;
  }

  const mission = detail.mission || {};
  const lifecycle = detail.lifecycle || {};
  const packets = detail.packets || [];
  const rounds = detail.rounds || [];
  const latestRound = rounds.length ? rounds[rounds.length - 1] : null;
  const currentPhase = lifecycle.phase || mission.status || 'unknown';
  const completedIssues = lifecycle.completed_issues || [];
  const issueIds = lifecycle.issue_ids || [];
  const metrics = [
    { label: 'Phase', value: currentPhase },
    { label: 'Round', value: detail.current_round || '—' },
    { label: 'Packets', value: packets.length || '—' },
    { label: 'Issues', value: issueIds.length ? `${completedIssues.length}/${issueIds.length}` : '—' },
  ];

  view.innerHTML = `
    <section class="mission-hero">
      <div class="mission-hero-copy">
        <div class="mission-kicker">Mission ${escHtml(mission.mission_id || '')}</div>
        <div class="mission-hero-title">${escHtml(mission.title || 'Untitled mission')}</div>
        <div class="mission-hero-subtitle">${escHtml(buildMissionSubtitle(detail))}</div>
      </div>
      <div class="mission-primary-actions">
        ${renderActionButtons(detail.actions || [], mission.mission_id || '')}
      </div>
    </section>
    <section class="mission-metrics">
      ${metrics.map(metric => `
        <div class="mission-metric">
          <div class="mission-metric-label">${escHtml(metric.label)}</div>
          <div class="mission-metric-value">${escHtml(String(metric.value))}</div>
        </div>
      `).join('')}
    </section>
    <section class="mission-tabs">
      <button class="mission-tab active" type="button">Overview</button>
      <button class="mission-tab" type="button" onclick="openDiscuss('${escHtml(mission.mission_id || '')}')">Discuss</button>
      <button class="mission-tab" type="button" onclick="load()">Refresh</button>
    </section>
    <section class="mission-workbench">
      <div class="mission-section">
        <h3>Packets</h3>
        <div class="packet-list">
          ${packets.length ? packets.map(packet => renderPacketRow(packet)).join('') : '<div class="empty-panel">No packets scoped yet.</div>'}
        </div>
      </div>
      <div class="mission-section">
        <h3>Latest Round</h3>
        ${latestRound ? renderLatestRound(latestRound) : '<div class="empty-panel">No round evidence yet.</div>'}
      </div>
    </section>
    <section class="mission-section">
      <div class="section-heading">
        <h3>Transcript</h3>
        <div id="transcript-filter-bar" class="transcript-filter-bar"></div>
      </div>
      <div id="packet-transcript-view" class="transcript-list">${renderTranscriptPreview()}</div>
    </section>
    <section class="mission-workbench">
      <div class="mission-section">
        <h3>Acceptance Criteria</h3>
        ${renderSimpleList(mission.acceptance_criteria, 'No acceptance criteria recorded yet.')}
      </div>
      <div class="mission-section">
        <h3>Constraints</h3>
        ${renderSimpleList(mission.constraints, 'No constraints recorded yet.')}
      </div>
    </section>
  `;
}

function renderContextRail(detail) {
  const rail = document.getElementById('operator-context-rail');
  if (!detail) {
    rail.innerHTML = '<div class="empty-panel">Mission context will appear here.</div>';
    return;
  }
  const mission = detail.mission || {};
  const rounds = detail.rounds || [];
  const latestRound = rounds.length ? rounds[rounds.length - 1] : null;
  const approvalRequest = detail.approval_request || null;
  const approvalHistory = detail.approval_history || [];
  const packet = (detail.packets || []).find(item => item.packet_id === selectedPacketId) || detail.packets?.[0];
  rail.innerHTML = `
    <div class="mission-section">
      <h3>Interventions</h3>
      <div class="context-list">
        <div class="context-card">
          <div class="context-title">Available actions</div>
          <div class="context-meta">${(detail.actions || []).join(' • ') || 'No actions'}</div>
        </div>
        <div class="context-card">
          <div class="context-title">Current packet</div>
          <div class="context-meta">${packet ? escHtml(packet.title) : 'No packet selected'}</div>
        </div>
      </div>
    </div>
    <div class="mission-section">
      <h3>Approval workspace</h3>
      <div class="context-list">
        ${approvalRequest ? renderApprovalWorkspace(approvalRequest, approvalHistory, mission.mission_id || '') : '<div class="empty-panel">No active approval request.</div>'}
      </div>
    </div>
    <div class="mission-section">
      <h3>Artifacts</h3>
      <div class="artifact-list">
        ${renderArtifactLinks(detail.artifacts || {})}
      </div>
    </div>
    <div class="mission-section">
      <h3>Round evidence</h3>
      <div class="context-list">
        ${latestRound ? renderRoundContext(latestRound) : '<div class="empty-panel">Waiting for first round evidence.</div>'}
      </div>
    </div>
    <div class="mission-section">
      <h3>Transcript inspector</h3>
      <div id="transcript-inspector" class="context-list">
        ${renderTranscriptInspector()}
      </div>
    </div>
    <div class="mission-section">
      <h3>Spec</h3>
      <div class="context-list">
        <div class="context-card">
          <div class="context-title">${escHtml(mission.spec_path || 'No spec path')}</div>
          <div class="context-meta">Mission source of truth</div>
        </div>
      </div>
    </div>
  `;
}

function renderApprovalWorkspace(approvalRequest, approvalHistory, missionId) {
  const latestAction = approvalHistory && approvalHistory.length ? approvalHistory[0] : null;
  return `
    <div class="context-card">
      <div class="context-title">${escHtml(approvalRequest.summary || 'Approval required')}</div>
      <div class="context-meta">
        <span>Round ${escHtml(String(approvalRequest.round_id || '—'))}</span>
        <span>${escHtml(approvalRequest.decision_action || 'ask_human')}</span>
        <span>${escHtml(approvalRequest.timestamp || '—')}</span>
      </div>
    </div>
    ${latestAction ? `
      <div class="context-card">
        <div class="context-title">Latest operator decision</div>
        <div class="context-meta">
          <span class="detail-chip">${escHtml(latestAction.label || latestAction.action_key || 'Action')}</span>
          <span class="detail-chip">${escHtml(latestAction.effect || 'guidance_sent')}</span>
          <span>${escHtml(latestAction.timestamp || '—')}</span>
        </div>
        <div class="transcript-entry-body">${escHtml(latestAction.message || '')}</div>
      </div>
    ` : ''}
    <div class="context-card">
      <div class="context-title">Blocking question</div>
      <div class="transcript-entry-body">${escHtml(approvalRequest.blocking_question || 'No blocking question recorded.')}</div>
    </div>
    <div class="context-card">
      <div class="context-title">Operator actions</div>
      <div class="context-meta">
        ${(approvalRequest.actions || []).map(action => `
          <button
            class="btn ${action.key === 'approve' ? 'btn-primary' : ''} btn-sm"
            type="button"
            onclick="triggerApprovalAction('${missionId}', '${escHtml(action.key || '')}')"
          >${escHtml(action.label || action.key || 'Action')}</button>
        `).join('')}
        <button
          class="btn btn-sm"
          type="button"
          onclick="openDiscussPreset('${missionId}', '${escHtml((approvalRequest.actions || [])[0]?.message || '')}')"
        >Open discuss</button>
        <button class="btn btn-sm" type="button" onclick="load()">Refresh state</button>
      </div>
    </div>
    <div class="context-card">
      <div class="context-title">Recent operator actions</div>
      ${
        approvalHistory && approvalHistory.length
          ? `<div class="context-list">
              ${approvalHistory.slice(0, 3).map(item => `
                <div class="context-card">
                  <div class="context-title">${escHtml(item.label || item.action_key || 'Action')}</div>
                  <div class="context-meta">
                    <span>${escHtml(item.timestamp || '—')}</span>
                    <span>${escHtml(item.channel || 'web-dashboard')}</span>
                    <span class="detail-chip">${escHtml(item.status || 'sent')}</span>
                    <span class="detail-chip">${escHtml(item.effect || 'guidance_sent')}</span>
                  </div>
                  <div class="transcript-entry-body">${escHtml(item.message || '')}</div>
                </div>
              `).join('')}
            </div>`
          : '<div class="empty-panel">No operator actions recorded yet.</div>'
      }
    </div>
  `;
}

function renderActionButtons(actions, missionId) {
  return actions.map(action => {
    if (action === 'approve') {
      return `<button class="btn btn-green btn-sm" onclick="approveGo('${missionId}')">Approve</button>`;
    }
    if (action === 'retry' || action === 'rerun') {
      return `<button class="btn btn-red btn-sm" onclick="retryMission('${missionId}')">${action}</button>`;
    }
    if (action === 'resume') {
      return `<button class="btn btn-sm" onclick="openDiscuss('${missionId}')">Resume</button>`;
    }
    if (action === 'inject_guidance') {
      return `<button class="btn btn-primary btn-sm" onclick="openDiscuss('${missionId}')">Inject guidance</button>`;
    }
    return `<button class="btn btn-sm" type="button">${escHtml(action)}</button>`;
  }).join('');
}

function renderPacketRow(packet) {
  const inScope = (packet.files_in_scope || []).slice(0, 2).join(', ');
  const isSelected = packet.packet_id === selectedPacketId;
  return `
    <button class="packet-row ${isSelected ? 'active' : ''}" type="button" onclick="selectPacket('${packet.packet_id}')">
      <div class="packet-row-header">
        <div class="packet-row-title">${escHtml(packet.title)}</div>
        <span class="run-class">${escHtml(packet.run_class || 'packet')}</span>
      </div>
      <div class="packet-row-meta">
        <span>${escHtml(packet.packet_id)}</span>
        <span>Wave ${escHtml(String(packet.wave_id ?? '—'))}</span>
        ${packet.linear_issue_id ? `<span>${escHtml(packet.linear_issue_id)}</span>` : ''}
      </div>
      <div class="packet-row-meta">
        <span>${escHtml(inScope || 'No scoped files')}</span>
      </div>
    </button>
  `;
}

function renderLatestRound(round) {
  const decision = round.decision || {};
  const succeeded = (round.worker_results || []).filter(result => result.succeeded).length;
  const total = (round.worker_results || []).length;
  return `
    <div class="context-card">
      <div class="context-title">${escHtml(decision.summary || 'No supervisor decision summary')}</div>
      <div class="context-meta">
        <span>Action ${escHtml(decision.action || '—')}</span>
        <span>Confidence ${decision.confidence != null ? escHtml(String(decision.confidence)) : '—'}</span>
        <span>Workers ${succeeded}/${total}</span>
      </div>
    </div>
    <div class="context-list">
      ${(round.worker_results || []).map(result => `
        <div class="context-card">
          <div class="context-title">${escHtml(result.title || result.packet_id || 'worker')}</div>
          <div class="context-meta">
            <span>${escHtml(result.packet_id || '—')}</span>
            <span>${result.succeeded ? 'succeeded' : 'failed'}</span>
            ${result.report_path ? `<span>${escHtml(result.report_path)}</span>` : ''}
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

function renderSimpleList(items, emptyText) {
  if (!items || !items.length) {
    return `<div class="empty-panel">${escHtml(emptyText)}</div>`;
  }
  return `<div class="context-list">${items.map(item => `
    <div class="context-card">
      <div class="context-title">${escHtml(item)}</div>
    </div>
  `).join('')}</div>`;
}

function renderArtifactLinks(artifacts) {
  const entries = Object.entries(artifacts).filter(([, value]) => Boolean(value));
  if (!entries.length) {
    return '<div class="empty-panel">No artifact paths available.</div>';
  }
  return entries.map(([key, value]) => `
    <div class="context-card">
      <div class="context-title">${escHtml(key)}</div>
      <div class="context-meta"><span class="artifact-link">${escHtml(String(value))}</span></div>
    </div>
  `).join('');
}

function renderRoundContext(round) {
  const paths = round.paths || {};
  const decision = round.decision || {};
  return `
    <div class="context-card">
      <div class="context-title">${escHtml(decision.reason_code || 'round decision')}</div>
      <div class="context-meta">
        <span>Round ${escHtml(String(round.round_id || '—'))}</span>
        <span>${escHtml(round.status || 'unknown')}</span>
      </div>
    </div>
    ${Object.entries(paths).filter(([, value]) => Boolean(value)).map(([key, value]) => `
      <div class="context-card">
        <div class="context-title">${escHtml(key)}</div>
        <div class="context-meta">${escHtml(String(value))}</div>
      </div>
    `).join('')}
  `;
}

function buildMissionSubtitle(detail) {
  const mission = detail.mission || {};
  const rounds = detail.rounds || [];
  const lifecycle = detail.lifecycle || {};
  const paused = lifecycle.round_orchestrator_state?.paused;
  const stateText = paused ? 'Paused for human input.' : 'Supervisor loop active.';
  const criterionCount = (mission.acceptance_criteria || []).length;
  return `${stateText} ${criterionCount} acceptance criteria, ${rounds.length} recorded rounds, and ${(detail.packets || []).length} scoped packets.`;
}

async function selectPacket(packetId) {
  selectedPacketId = packetId;
  selectedPacketTranscript = null;
  selectedTranscriptBlockIndex = null;
  renderMissionDetail(selectedMissionDetail);
  renderContextRail(selectedMissionDetail);
  await loadSelectedPacketTranscript();
}

async function loadSelectedPacketTranscript() {
  if (!selectedMissionId || !selectedPacketId) {
    selectedPacketTranscript = null;
    renderTranscriptContainer();
    return;
  }
  selectedPacketTranscript = {loading: true, entries: []};
  renderTranscriptContainer();
  try {
    const response = await fetch(`/api/missions/${selectedMissionId}/packets/${selectedPacketId}/transcript`);
    if (!response.ok) {
      selectedPacketTranscript = {error: 'No transcript available for this packet yet.', entries: []};
      renderTranscriptContainer();
      renderContextRail(selectedMissionDetail);
      return;
    }
    selectedPacketTranscript = await response.json();
    const blocks = selectedPacketTranscript.blocks || [];
    selectedTranscriptBlockIndex = blocks.length ? blocks.length - 1 : null;
  } catch (error) {
    selectedPacketTranscript = {error: error?.message || 'Failed to load transcript.', entries: []};
  }
  renderTranscriptContainer();
  renderContextRail(selectedMissionDetail);
}

function renderTranscriptContainer() {
  renderTranscriptFilters();
  const container = document.getElementById('packet-transcript-view');
  if (!container) return;
  container.innerHTML = renderTranscriptPreview();
}

function selectTranscriptBlock(index) {
  selectedTranscriptBlockIndex = index;
  renderTranscriptContainer();
  renderContextRail(selectedMissionDetail);
}

function renderTranscriptFilters() {
  const root = document.getElementById('transcript-filter-bar');
  if (!root) return;
  const counts = selectedPacketTranscript?.summary?.block_counts || {};
  const filters = [{key: 'all', label: 'All'}].concat(
    Object.entries(counts)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([key, value]) => ({key, label: `${key} (${value})`}))
  );
  root.innerHTML = filters.map(filter => `
    <button
      class="mission-tab ${selectedTranscriptFilter === filter.key ? 'active' : ''}"
      type="button"
      onclick="selectTranscriptFilter('${escHtml(filter.key)}')"
    >${escHtml(filter.label)}</button>
  `).join('');
}

function selectTranscriptFilter(filterKey) {
  selectedTranscriptFilter = filterKey || 'all';
  renderTranscriptContainer();
}

function renderTranscriptPreview() {
  if (!selectedPacketId) {
    return '<div class="empty-panel">Select a packet to inspect its transcript.</div>';
  }
  if (!selectedPacketTranscript || selectedPacketTranscript.loading) {
    return '<div class="empty-panel">Loading transcript…</div>';
  }
  if (selectedPacketTranscript.error) {
    return `<div class="empty-panel">${escHtml(selectedPacketTranscript.error)}</div>`;
  }
  const entries = selectedPacketTranscript.entries || [];
  const blocks = selectedPacketTranscript.blocks || [];
  if (!entries.length && !blocks.length) {
    return '<div class="empty-panel">No transcript events have been recorded yet.</div>';
  }
  const summary = selectedPacketTranscript.summary || {};
  const milestones = selectedPacketTranscript.milestones || [];
  const visibleBlocks = selectedTranscriptFilter === 'all'
    ? blocks
    : blocks.filter(block => (block.block_type || 'event') === selectedTranscriptFilter);
  const summaryMeta = [
    `${summary.entry_count || 0} events`,
    ...(summary.latest_timestamp ? [summary.latest_timestamp] : []),
    ...Object.entries(summary.kind_counts || {}).map(([kind, count]) => `${kind} ${count}`),
  ];
  return `
    <div class="context-card">
      <div class="context-title">Packet timeline</div>
      <div class="context-meta">${summaryMeta.map(item => `<span>${escHtml(String(item))}</span>`).join('')}</div>
      ${milestones.length ? `<div class="context-meta">${milestones.map(item => `<span class="run-class">${escHtml(item.event_type || 'milestone')}</span>`).join('')}</div>` : ''}
    </div>
    ${(visibleBlocks.length ? visibleBlocks.slice(-8).map(block => {
      const blockIndex = blocks.indexOf(block);
      const active = blockIndex === selectedTranscriptBlockIndex;
      return `
    <button type="button" class="transcript-entry ${escHtml(block.block_type || 'event')} ${active ? 'active' : ''}" onclick="selectTranscriptBlock(${blockIndex})">
      <div class="transcript-entry-header">
        <div class="context-title">${escHtml(block.title || 'event')}</div>
        <span class="run-class">${escHtml(block.block_type || 'event')}</span>
      </div>
      <div class="transcript-entry-meta">
        <span>${escHtml(block.timestamp || '—')}</span>
        ${block.body ? `<span>${escHtml(block.body)}</span>` : ''}
      </div>
      ${block.body ? `<div class="transcript-entry-body">${escHtml(block.body)}</div>` : ''}
    </button>
  `;
    }).join('') : (blocks.length
    ? '<div class="empty-panel">No transcript blocks match the current filter.</div>'
    : entries.slice(-8).map(entry => `
    <div class="transcript-entry ${escHtml(entry.kind || '')}">
      <div class="transcript-entry-header">
        <div class="context-title">${escHtml(entry.message || entry.event_type || entry.kind || 'event')}</div>
        <span class="run-class">${escHtml(entry.kind || 'event')}</span>
      </div>
      <div class="transcript-entry-meta">
        <span>${escHtml(entry.timestamp || '—')}</span>
        ${entry.event_type ? `<span>${escHtml(entry.event_type)}</span>` : ''}
      </div>
      ${renderTranscriptBody(entry)}
    </div>
  `).join('')))}
  `;
}

function renderTranscriptInspector() {
  if (!selectedPacketId) {
    return '<div class="empty-panel">Select a packet to inspect transcript evidence.</div>';
  }
  if (!selectedPacketTranscript || selectedPacketTranscript.loading) {
    return '<div class="empty-panel">Loading transcript evidence…</div>';
  }
  if (selectedPacketTranscript.error) {
    return `<div class="empty-panel">${escHtml(selectedPacketTranscript.error)}</div>`;
  }
  const blocks = selectedPacketTranscript.blocks || [];
  if (!blocks.length || selectedTranscriptBlockIndex == null || !blocks[selectedTranscriptBlockIndex]) {
    return '<div class="empty-panel">Select a transcript block to inspect its evidence.</div>';
  }
  const block = blocks[selectedTranscriptBlockIndex];
  const links = [block.artifact_path, block.source_path].filter(Boolean);
  const burstItems = Array.isArray(block.items) ? block.items : [];
  return `
    <div class="context-card">
      <div class="context-title">${escHtml(block.title || 'Transcript evidence')}</div>
      <div class="context-meta">
        <span>${escHtml(block.block_type || 'event')}</span>
        <span>${escHtml(block.timestamp || '—')}</span>
      </div>
      ${block.body ? `<div class="transcript-entry-body">${escHtml(block.body)}</div>` : ''}
    </div>
    ${renderTranscriptDetails(block.details)}
    ${burstItems.length ? `
      <div class="context-card">
        <div class="context-title">Burst items</div>
        <div class="context-list">
          ${burstItems.map(item => `
            <div class="context-card">
              <div class="context-title">${escHtml(item.title || item.block_type || 'tool')}</div>
              <div class="context-meta">
                <span>${escHtml(item.block_type || 'tool')}</span>
                <span>${escHtml(item.timestamp || '—')}</span>
              </div>
              ${item.body ? `<div class="transcript-entry-body">${escHtml(item.body)}</div>` : ''}
            </div>
          `).join('')}
        </div>
      </div>
    ` : ''}
    ${links.length ? links.map(path => `
      <div class="context-card">
        <div class="context-title">Linked evidence</div>
        <div class="context-meta"><span class="artifact-link">${escHtml(String(path))}</span></div>
      </div>
    `).join('') : '<div class="empty-panel">No linked evidence path for this block.</div>'}
  `;
}

function renderTranscriptDetails(details) {
  if (!details || typeof details !== 'object') {
    return '';
  }
  const entries = Object.entries(details);
  const artifactRows = [];
  const findingRows = [];
  const genericRows = [];

  for (const [key, value] of entries) {
    if (key === 'artifacts' && value && typeof value === 'object' && !Array.isArray(value)) {
      for (const [artifactKey, artifactValue] of Object.entries(value)) {
        artifactRows.push(`
          <div class="detail-row">
            <div class="detail-key">${escHtml(artifactKey)}</div>
            <div class="detail-value artifact-link">${escHtml(String(artifactValue))}</div>
          </div>
        `);
      }
      continue;
    }

    if (key === 'findings' && Array.isArray(value)) {
      for (const finding of value) {
        findingRows.push(`
          <div class="context-card detail-finding">
            <div class="context-title">${escHtml(String(finding?.severity || 'finding'))}</div>
            <div class="transcript-entry-body">${escHtml(String(finding?.message || ''))}</div>
          </div>
        `);
      }
      continue;
    }

    genericRows.push(`
      <div class="detail-row">
        <div class="detail-key">${escHtml(key)}</div>
        <div class="detail-value">${renderDetailValue(value)}</div>
      </div>
    `);
  }

  return `
    <div class="context-card">
      <div class="context-title">Structured details</div>
      ${genericRows.length ? `<div class="detail-grid">${genericRows.join('')}</div>` : '<div class="empty-panel">No structured fields.</div>'}
      ${findingRows.length ? `<div class="context-list detail-section"><div class="context-title">Findings</div>${findingRows.join('')}</div>` : ''}
      ${artifactRows.length ? `<div class="detail-grid detail-section">${artifactRows.join('')}</div>` : ''}
    </div>
  `;
}

function renderDetailValue(value) {
  if (Array.isArray(value)) {
    if (!value.length) return '<span class="detail-empty">—</span>';
    return value.map(item => `<span class="detail-chip">${escHtml(String(item))}</span>`).join('');
  }
  if (value && typeof value === 'object') {
    return `<span class="detail-json">${escHtml(JSON.stringify(value))}</span>`;
  }
  if (value === null || value === undefined || value === '') {
    return '<span class="detail-empty">—</span>';
  }
  return escHtml(String(value));
}

function renderTranscriptBody(entry) {
  if (!entry.raw) return '';
  const body = typeof entry.raw === 'string' ? entry.raw : JSON.stringify(entry.raw, null, 2);
  return `<div class="transcript-entry-body">${escHtml(body)}</div>`;
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

/* ===== ACTIONS ===== */
async function approveGo(mid) {
  const btn = event.target;
  btn.disabled = true; btn.textContent = 'Starting…';
  try {
    const r = await fetch(`/api/missions/${mid}/approve`, {method:'POST'});
    const d = await r.json();
    if (!r.ok) alert(d.error || 'Failed');
    await load();
  } catch(e) { alert('Error: ' + e.message); }
  finally { btn.disabled = false; btn.textContent = 'Approve & Go'; }
}

async function retryMission(mid) {
  const btn = event.target;
  btn.disabled = true; btn.textContent = 'Retrying…';
  try {
    const r = await fetch(`/api/missions/${mid}/retry`, {method:'POST'});
    const d = await r.json();
    if (!r.ok) alert(d.error || 'Failed');
    await load();
  } catch(e) { alert('Error: ' + e.message); }
  finally { btn.disabled = false; btn.textContent = 'Retry'; }
}

async function triggerApprovalAction(missionId, actionKey) {
  try {
    const response = await fetch(`/api/missions/${missionId}/approval-action`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action_key: actionKey}),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || 'Approval action failed');
    }
    openDiscussPreset(missionId, data.message || '');
    addSystemMsg(`Sent ${actionKey} guidance for ${missionId}`);
    await load();
  } catch (error) {
    alert('Error: ' + (error?.message || 'Approval action failed'));
  }
}

/* ===== CHAT / DISCUSS ===== */
function openSidebar() {
  document.getElementById('sidebar').classList.add('open');
}
function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
}

function openNewMission() {
  chatThreadId = 'web-' + crypto.randomUUID().slice(0,8);
  chatMessages = [];
  renderChat();
  document.getElementById('chat-title').textContent = 'New Mission';
  openSidebar();
  addSystemMsg('Start describing your feature. Use @freeze to create a spec, @approve to approve.');
}

function openDiscuss(missionId) {
  chatThreadId = 'discuss-' + missionId;
  chatMessages = [];
  renderChat();
  document.getElementById('chat-title').textContent = 'Discuss: ' + missionId.slice(0,12);
  openSidebar();
  addSystemMsg('Discussing mission ' + missionId);
}

function openDiscussPreset(missionId, presetMessage) {
  openDiscuss(missionId);
  const input = document.getElementById('chat-input');
  if (input) {
    input.value = presetMessage || '';
    input.focus();
  }
}

function addSystemMsg(text) {
  chatMessages.push({role:'system', text});
  renderChat();
}

function renderChat() {
  const el = document.getElementById('chat-messages');
  el.innerHTML = chatMessages.map(m =>
    `<div class="chat-msg ${m.role}">${escHtml(m.text)}</div>`
  ).join('');
  el.scrollTop = el.scrollHeight;
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text || !chatThreadId) return;
  input.value = '';

  chatMessages.push({role:'user', text});
  renderChat();

  try {
    const r = await fetch('/api/discuss', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({thread_id: chatThreadId, message: text})
    });
    const d = await r.json();
    const reply = d.reply || d.error || 'No response';
    chatMessages.push({role:'bot', text: reply});
    renderChat();

    if (reply.toLowerCase().includes('frozen') || reply.toLowerCase().includes('spec frozen')) {
      addSystemMsg('Spec frozen. Refreshing missions…');
      closeSidebar();
      await load();
    }
  } catch(e) {
    chatMessages.push({role:'bot', text: 'Error: ' + e.message});
    renderChat();
  }
}

/* ===== WEBSOCKET ===== */
function connectWs() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws`);

  ws.onopen = () => {
    wsRetryMs = 1000;
    document.getElementById('ws-dot').className = 'status-dot connected';
    document.getElementById('ws-label').textContent = 'live';
  };

  ws.onmessage = (ev) => {
    try {
      const evt = JSON.parse(ev.data);
      handleEvent(evt);
    } catch(e) {}
  };

  ws.onclose = () => {
    document.getElementById('ws-dot').className = 'status-dot disconnected';
    document.getElementById('ws-label').textContent = 'disconnected';
    setTimeout(() => { wsRetryMs = Math.min(wsRetryMs * 2, 30000); connectWs(); }, wsRetryMs);
  };

  ws.onerror = () => { ws.close(); };
}

function handleEvent(evt) {
  const logEl = document.getElementById('event-log');
  logEl.textContent = `${evt.topic}: ${JSON.stringify(evt.payload).slice(0,80)}`;

  if (evt.topic === 'mission.state' || evt.topic === 'issue.state') {
    const mid = evt.payload.mission_id;
    if (mid) {
      const card = document.getElementById('card-' + mid);
      if (card) {
        card.classList.add('flash');
        setTimeout(() => card.classList.remove('flash'), 1500);
      }
      if (evt.payload.mission_id) {
        loadSingleMission(mid);
      }
    }
    load();
  }
}

async function loadSingleMission(mid) {
  try {
    const r = await fetch(`/api/missions/${mid}`);
    if (!r.ok) return;
    const m = await r.json();
    const idx = missions.findIndex(x => x.mission_id === mid);
    if (idx >= 0) missions[idx] = m;
    if (idx < 0) missions.push(m);
    const lcr = await fetch('/api/lifecycle').catch(() => ({ok:false}));
    if (lcr.ok) lifecycleStates = await lcr.json();
    renderMissions();
    if (selectedMissionId === mid) {
      await selectMission(mid, {force:true});
    }
  } catch(e) {}
}

/* ===== INIT ===== */
load();
loadEvolution();
connectWs();
setInterval(load, 15000);
setInterval(loadEvolution, 30000);
</script>
<script src="/static/operator-console.js" defer></script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# FastAPI application factory
# ---------------------------------------------------------------------------


def _legacy_create_app(repo_root: Path | None = None) -> Any:
    """Create the FastAPI app. Requires ``pip install fastapi uvicorn``."""
    from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
    from fastapi.staticfiles import StaticFiles

    root = repo_root or Path(".")
    app = FastAPI(title="spec-orch dashboard")
    static_dir = Path(__file__).resolve().parent.parent / "dashboard_assets" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="dashboard-static")

    # ---- pages ----

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return DASHBOARD_HTML

    @app.get("/favicon.ico")
    async def favicon() -> PlainTextResponse:
        return PlainTextResponse("", status_code=204)

    # ---- existing read endpoints ----

    @app.get("/api/missions")
    async def api_missions() -> JSONResponse:
        return JSONResponse(_gather_missions(root))

    @app.get("/api/inbox")
    async def api_inbox() -> JSONResponse:
        return JSONResponse(_gather_inbox(root))

    @app.get("/api/missions/{mission_id}")
    async def api_mission(mission_id: str) -> JSONResponse:
        missions = _gather_missions(root)
        for m in missions:
            if m["mission_id"] == mission_id:
                return JSONResponse(m)
        return JSONResponse({"error": "not found"}, status_code=404)

    @app.get("/api/missions/{mission_id}/detail")
    async def api_mission_detail(mission_id: str) -> JSONResponse:
        detail = _gather_mission_detail(root, mission_id)
        if detail is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(detail)

    @app.get("/api/missions/{mission_id}/packets/{packet_id}/transcript")
    async def api_packet_transcript(mission_id: str, packet_id: str) -> JSONResponse:
        transcript = _gather_packet_transcript(root, mission_id, packet_id)
        return JSONResponse(transcript)

    @app.get("/api/missions/{mission_id}/spec")
    async def api_mission_spec(mission_id: str) -> PlainTextResponse:
        content = _get_spec_content(root, mission_id)
        if content is None:
            return PlainTextResponse("not found", status_code=404)
        return PlainTextResponse(content)

    @app.get("/api/runs")
    async def api_runs() -> JSONResponse:
        return JSONResponse(_gather_run_history(root))

    @app.get("/api/health")
    async def api_health() -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "repo_root": str(root),
                "missions": len(_gather_missions(root)),
            }
        )

    @app.get("/api/events")
    async def api_events(
        issue_id: str | None = None,
        run_id: str | None = None,
        topic: str | None = None,
        limit: int = 100,
    ) -> JSONResponse:
        bus = _get_event_bus()
        if bus is None:
            return JSONResponse([])
        parsed_topic = None
        if topic:
            try:
                from spec_orch.services.event_bus import EventTopic

                parsed_topic = EventTopic(topic)
            except ValueError:
                parsed_topic = None
        events = bus.query_history(
            topic=parsed_topic,
            issue_id=issue_id,
            run_id=run_id,
            limit=limit,
        )
        return JSONResponse(
            [
                {
                    "topic": ev.topic.value if hasattr(ev.topic, "value") else str(ev.topic),
                    "payload": ev.payload,
                    "timestamp": ev.timestamp,
                    "source": ev.source,
                }
                for ev in events
            ]
        )

    # ---- lifecycle & evolution endpoints ----

    @app.get("/api/lifecycle")
    async def api_lifecycle() -> JSONResponse:
        return JSONResponse(_gather_lifecycle_states(root))

    @app.get("/api/evolution")
    async def api_evolution() -> JSONResponse:
        return JSONResponse(_gather_evolution_metrics(root))

    # ---- control tower endpoints (P5) ----

    @app.get("/api/control/overview")
    async def api_control_overview() -> JSONResponse:
        return JSONResponse(_control_overview(root))

    @app.get("/api/control/skills")
    async def api_control_skills() -> JSONResponse:
        return JSONResponse(_control_skills(root))

    @app.get("/api/control/eval")
    async def api_control_eval() -> JSONResponse:
        return JSONResponse(_control_eval(root))

    @app.post("/api/control/eval/run")
    async def api_control_eval_run() -> JSONResponse:
        return JSONResponse(_control_eval_trigger(root))

    @app.get("/api/control/reactions")
    async def api_control_reactions() -> JSONResponse:
        return JSONResponse(_control_reactions(root))

    @app.get("/api/control/degradation")
    async def api_control_degradation() -> JSONResponse:
        return JSONResponse(_control_degradation(root))

    # ---- action endpoints ----

    @app.post("/api/missions/{mission_id}/approve")
    async def api_approve(mission_id: str) -> JSONResponse:
        mgr = _get_lifecycle_manager(root)
        if mgr is None:
            return JSONResponse({"error": "Lifecycle manager unavailable"}, status_code=503)
        try:
            mgr.begin_tracking(mission_id)
            state = mgr.auto_advance(mission_id)
            return JSONResponse({"ok": True, "phase": state.phase.value if state else "unknown"})
        except Exception:
            logger.exception("approve failed for %s", mission_id)
            return JSONResponse({"error": "Mission approval failed"}, status_code=500)

    @app.post("/api/missions/{mission_id}/retry")
    async def api_retry(mission_id: str) -> JSONResponse:
        mgr = _get_lifecycle_manager(root)
        if mgr is None:
            return JSONResponse({"error": "Lifecycle manager unavailable"}, status_code=503)
        try:
            mgr.retry(mission_id)
            state = mgr.auto_advance(mission_id)
            return JSONResponse({"ok": True, "phase": state.phase.value if state else "unknown"})
        except Exception:
            logger.exception("retry failed for %s", mission_id)
            return JSONResponse({"error": "Mission retry failed"}, status_code=500)

    @app.post("/api/discuss")
    async def api_discuss(
        thread_id: str = Body(...),
        message: str = Body(...),
    ) -> JSONResponse:
        svc = _get_conversation_service(root)
        if svc is None:
            return JSONResponse({"error": "Conversation service unavailable"}, status_code=503)
        try:
            from spec_orch.domain.models import ConversationMessage

            msg = ConversationMessage(
                message_id=f"web-{uuid.uuid4().hex[:8]}",
                thread_id=thread_id,
                sender="user",
                content=message,
                timestamp=datetime.now(UTC).isoformat(),
                channel="web-dashboard",
            )
            reply = svc.handle_message(msg)
            return JSONResponse({"reply": reply or ""})
        except Exception:
            logger.exception("discuss failed")
            return JSONResponse({"error": "Discussion request failed"}, status_code=500)

    @app.post("/api/btw")
    async def api_btw(
        issue_id: str = Body(...),
        message: str = Body(...),
    ) -> JSONResponse:
        mgr = _get_lifecycle_manager(root)
        if mgr is None:
            return JSONResponse({"error": "Lifecycle manager unavailable"}, status_code=503)
        try:
            ok = mgr.inject_btw(issue_id, message, channel="web-dashboard")
            return JSONResponse({"ok": ok})
        except Exception:
            logger.exception("btw injection failed")
            return JSONResponse({"error": "BTW injection failed"}, status_code=500)

    # ---- websocket ----
    # Registered via add_api_websocket_route for maximum compatibility
    # with starlette/uvicorn version combinations (avoids 403 in some versions).

    async def _ws_handler(websocket: WebSocket) -> None:
        await websocket.accept()
        bus = _get_event_bus()
        if bus is None:
            await websocket.send_json(
                {
                    "topic": "system",
                    "payload": {"message": "EventBus unavailable"},
                    "timestamp": 0,
                    "source": "dashboard",
                }
            )
            await websocket.close()
            return

        queue = bus.create_async_queue()
        try:
            while True:
                event = await queue.get()
                await websocket.send_json(
                    {
                        "topic": event.topic.value
                        if hasattr(event.topic, "value")
                        else str(event.topic),
                        "payload": event.payload,
                        "timestamp": event.timestamp,
                        "source": event.source,
                    }
                )
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("Error in websocket endpoint")
        finally:
            bus.remove_async_queue(queue)

    # `from __future__ import annotations` turns nested function annotations into
    # strings. FastAPI can't resolve the local `WebSocket` symbol from the
    # function's globals, so it misclassifies `websocket` as a query param and
    # rejects the handshake with 403. Patch the concrete type back in before
    # route registration.
    _ws_handler.__annotations__["websocket"] = WebSocket
    app.add_api_websocket_route("/ws", _ws_handler)

    return app


def create_app(repo_root: Path | None = None) -> Any:
    """Create the FastAPI app. Requires ``pip install fastapi uvicorn``."""
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    from .routes import register_routes

    root = repo_root or Path(".")
    app = FastAPI(title="spec-orch dashboard")
    static_dir = Path(__file__).resolve().parent.parent / "dashboard_assets" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="dashboard-static")
    register_routes(app, root)
    return app
