"""One-shot migration helpers for importing existing implicit memory.

Each ``import_*`` function reads from the legacy storage location and
writes :class:`MemoryEntry` objects into the provider.  They are
idempotent — re-running silently upserts.
"""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path
from typing import Any

from spec_orch.services.memory.protocol import MemoryProvider
from spec_orch.services.memory.types import MemoryEntry, MemoryLayer

logger = logging.getLogger(__name__)


def import_prompt_history(provider: MemoryProvider, repo_root: Path) -> int:
    """Import ``prompt_history.json`` into *procedural* memory.

    Returns the number of entries imported.
    """
    path = repo_root / "prompt_history.json"
    if not path.exists():
        logger.info("No prompt_history.json found, skipping")
        return 0

    try:
        variants: list[dict[str, Any]] = json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cannot read prompt_history.json: %s", exc)
        return 0

    count = 0
    for v in variants:
        vid = v.get("variant_id", f"unknown-{count}")
        entry = MemoryEntry(
            key=f"prompt-variant-{vid}",
            content=v.get("prompt_text", ""),
            layer=MemoryLayer.PROCEDURAL,
            tags=["prompt-variant", *(["active"] if v.get("is_active") else [])],
            metadata={
                "variant_id": vid,
                "rationale": v.get("rationale", ""),
                "total_runs": v.get("total_runs", 0),
                "successful_runs": v.get("successful_runs", 0),
                "success_rate": v.get("successful_runs", 0) / max(v.get("total_runs", 1), 1) * 100,
                "is_active": v.get("is_active", False),
                "is_candidate": v.get("is_candidate", False),
                "source": "prompt_evolver",
            },
            created_at=v.get("created_at", ""),
        )
        provider.store(entry)
        count += 1

    logger.info("Imported %d prompt variants into procedural memory", count)
    return count


def import_scoper_hints(provider: MemoryProvider, repo_root: Path) -> int:
    """Import ``scoper_hints.json`` into *semantic* memory.

    Returns the number of hints imported.
    """
    path = repo_root / "scoper_hints.json"
    if not path.exists():
        logger.info("No scoper_hints.json found, skipping")
        return 0

    try:
        data: dict[str, Any] = json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cannot read scoper_hints.json: %s", exc)
        return 0

    hints = data.get("hints", [])
    count = 0
    for h in hints:
        hid = h.get("hint_id", f"hint-{count}")
        entry = MemoryEntry(
            key=f"scoper-hint-{hid}",
            content=h.get("text", ""),
            layer=MemoryLayer.SEMANTIC,
            tags=["scoper-hint", *(["active"] if h.get("is_active") else ["inactive"])],
            metadata={
                "hint_id": hid,
                "evidence": h.get("evidence", ""),
                "confidence": h.get("confidence", "medium"),
                "is_active": h.get("is_active", True),
                "source": "plan_strategy_evolver",
            },
            created_at=h.get("created_at", ""),
        )
        provider.store(entry)
        count += 1

    if data.get("analysis_summary"):
        provider.store(
            MemoryEntry(
                key="scoper-analysis-summary",
                content=data["analysis_summary"],
                layer=MemoryLayer.SEMANTIC,
                tags=["scoper-hint", "summary"],
                metadata={
                    "source": "plan_strategy_evolver",
                    "generated_at": data.get("generated_at", ""),
                },
            )
        )
        count += 1

    logger.info("Imported %d scoper hints into semantic memory", count)
    return count


def import_run_reports(provider: MemoryProvider, repo_root: Path) -> int:
    """Import ``report.json`` files from run directories into *episodic* memory.

    Returns the number of reports imported.
    """
    count = 0
    for run_parent in (".spec_orch_runs", ".worktrees"):
        parent = repo_root / run_parent
        if not parent.is_dir():
            continue
        for run_dir in sorted(parent.iterdir()):
            if not run_dir.is_dir():
                continue
            report_path = run_dir / "report.json"
            if not report_path.exists():
                continue
            try:
                report: dict[str, Any] = json.loads(report_path.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            issue_id = report.get("issue_id", run_dir.name)
            run_id = report.get("run_id", run_dir.name)
            succeeded = report.get("mergeable", False)

            # Build a human-readable summary
            lines = [f"# Run report: {issue_id}"]
            lines.append(f"\n**State**: {report.get('state', 'unknown')}")
            lines.append(f"**Mergeable**: {succeeded}")

            builder = report.get("builder", {})
            if builder:
                lines.append(f"\n## Builder\n- Succeeded: {builder.get('succeeded')}")
                lines.append(f"- Adapter: {builder.get('adapter', 'unknown')}")

            verification = report.get("verification", {})
            if verification:
                lines.append("\n## Verification")
                for step, detail in verification.items():
                    exit_code = detail.get("exit_code", "?") if isinstance(detail, dict) else "?"
                    lines.append(f"- {step}: exit_code={exit_code}")

            review = report.get("review", {})
            if review:
                lines.append(f"\n## Review\n- Verdict: {review.get('verdict', 'unknown')}")

            # Also import deviations if present
            dev_path = run_dir / "deviations.jsonl"
            deviations: list[dict[str, Any]] = []
            if dev_path.exists():
                try:
                    for line in dev_path.read_text("utf-8").splitlines():
                        line = line.strip()
                        if line:
                            deviations.append(json.loads(line))
                except (json.JSONDecodeError, OSError):
                    pass
                if deviations:
                    lines.append(f"\n## Deviations ({len(deviations)})")
                    for d in deviations[:10]:
                        lines.append(f"- [{d.get('severity', '?')}] {d.get('description', '')}")

            entry = MemoryEntry(
                key=f"run-report-{issue_id}-{run_id}",
                content="\n".join(lines),
                layer=MemoryLayer.EPISODIC,
                tags=[
                    "run-report",
                    "succeeded" if succeeded else "failed",
                    f"issue:{issue_id}",
                ],
                metadata={
                    "issue_id": issue_id,
                    "run_id": run_id,
                    "state": report.get("state", ""),
                    "mergeable": succeeded,
                    "builder_adapter": builder.get("adapter", "") if builder else "",
                    "review_verdict": review.get("verdict", "") if review else "",
                    "deviation_count": len(deviations),
                    "source": "evidence_analyzer",
                    "source_path": str(report_path),
                },
            )
            provider.store(entry)
            count += 1

    logger.info("Imported %d run reports into episodic memory", count)
    return count


def import_policies(provider: MemoryProvider, repo_root: Path) -> int:
    """Import ``policies_index.json`` into *procedural* memory.

    Returns the number of policies imported.
    """
    path = repo_root / "policies_index.json"
    if not path.exists():
        logger.info("No policies_index.json found, skipping")
        return 0

    try:
        policies: list[dict[str, Any]] = json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cannot read policies_index.json: %s", exc)
        return 0

    count = 0
    for p in policies:
        pid = p.get("policy_id", f"policy-{count}")
        script_path = repo_root / "policies" / f"{pid}.py"
        script_content = ""
        if script_path.exists():
            with contextlib.suppress(OSError):
                script_content = script_path.read_text("utf-8")

        content_lines = [
            f"# Policy: {p.get('name', pid)}",
            f"\n{p.get('description', '')}",
            f"\n**Trigger patterns**: {', '.join(p.get('trigger_patterns', []))}",
        ]
        if script_content:
            content_lines.append(f"\n## Script\n```python\n{script_content}\n```")

        entry = MemoryEntry(
            key=f"policy-{pid}",
            content="\n".join(content_lines),
            layer=MemoryLayer.PROCEDURAL,
            tags=["policy", *(["active"] if p.get("is_active") else ["inactive"])],
            metadata={
                "policy_id": pid,
                "name": p.get("name", ""),
                "trigger_patterns": p.get("trigger_patterns", []),
                "total_executions": p.get("total_executions", 0),
                "successful_executions": p.get("successful_executions", 0),
                "is_active": p.get("is_active", True),
                "source": "policy_distiller",
            },
            created_at=p.get("created_at", ""),
        )
        provider.store(entry)
        count += 1

    logger.info("Imported %d policies into procedural memory", count)
    return count


def import_all(provider: MemoryProvider, repo_root: Path) -> dict[str, int]:
    """Run all migration importers and return counts by category."""
    return {
        "prompt_variants": import_prompt_history(provider, repo_root),
        "scoper_hints": import_scoper_hints(provider, repo_root),
        "run_reports": import_run_reports(provider, repo_root),
        "policies": import_policies(provider, repo_root),
    }
