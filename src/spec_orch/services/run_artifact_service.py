from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.runtime_core.writers import write_issue_execution_payloads
from spec_orch.services.io import atomic_write_json


class RunArtifactService:
    """Write unified run artifacts under workspace/run_artifact/."""

    def artifact_dir(self, workspace: Path) -> Path:
        path = workspace / "run_artifact"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_from_run(
        self,
        *,
        workspace: Path,
        run_id: str,
        issue_id: str,
        report_path: Path,
        explain_path: Path | None = None,
    ) -> Path:
        artifact_dir = self.artifact_dir(workspace)
        report = self._load_json(report_path)
        events = self._load_events(workspace)

        (artifact_dir / "events.jsonl").write_text(
            "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events),
            encoding="utf-8",
        )

        live = self._build_live_snapshot(
            run_id=run_id, issue_id=issue_id, report=report, events=events
        )

        conclusion = self._build_conclusion(
            run_id=run_id,
            issue_id=issue_id,
            report=report,
            explain_path=explain_path,
        )

        retro = self._build_retro(report=report)
        self._write_json(artifact_dir / "retro.json", retro)

        manifest = self._build_manifest(
            run_id=run_id,
            issue_id=issue_id,
            report=report,
            events_count=len(events),
            artifact_dir=artifact_dir,
        )
        written = write_issue_execution_payloads(
            workspace,
            live=live,
            conclusion=conclusion,
            manifest=manifest,
        )
        return written["manifest"]

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _load_events(workspace: Path) -> list[dict[str, Any]]:
        events_path = workspace / "telemetry" / "events.jsonl"
        if not events_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for line in events_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                entries.append(obj)
        return entries

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        atomic_write_json(path, payload)

    @staticmethod
    def _build_manifest(
        *,
        run_id: str,
        issue_id: str,
        report: dict[str, Any],
        events_count: int,
        artifact_dir: Path,
    ) -> dict[str, Any]:
        workspace = artifact_dir.parent
        artifacts: dict[str, str] = {
            "events": str(artifact_dir / "events.jsonl"),
            "live": str(artifact_dir / "live.json"),
            "retro": str(artifact_dir / "retro.json"),
            "conclusion": str(artifact_dir / "conclusion.json"),
            # Compatibility aliases used by existing context consumers.
            "report": str(artifact_dir / "live.json"),
            "builder_events": str(artifact_dir / "events.jsonl"),
        }
        review_report = workspace / "review_report.json"
        if review_report.exists():
            artifacts["review_report"] = str(review_report)
        deviations = workspace / "deviations.jsonl"
        if deviations.exists():
            artifacts["deviations"] = str(deviations)

        return {
            "schema_version": "1.0",
            "run_id": run_id,
            "issue_id": issue_id,
            "state": report.get("state", "unknown"),
            "mergeable": bool(report.get("mergeable", False)),
            "events_count": events_count,
            "generated_at": datetime.now(UTC).isoformat(),
            "artifacts": artifacts,
        }

    @staticmethod
    def _build_live_snapshot(
        *,
        run_id: str,
        issue_id: str,
        report: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "issue_id": issue_id,
            "state": report.get("state", "unknown"),
            "mergeable": bool(report.get("mergeable", False)),
            "failed_conditions": report.get("failed_conditions", []),
            "builder": report.get("builder", {}),
            "review": report.get("review", {}),
            "verification": report.get("verification", {}),
            "event_tail": events[-20:],
            "updated_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _build_conclusion(
        *,
        run_id: str,
        issue_id: str,
        report: dict[str, Any],
        explain_path: Path | None,
    ) -> dict[str, Any]:
        verdict = "pass" if report.get("mergeable", False) else "fail"
        return {
            "run_id": run_id,
            "issue_id": issue_id,
            "verdict": verdict,
            "mergeable": bool(report.get("mergeable", False)),
            "failed_conditions": report.get("failed_conditions", []),
            "state": report.get("state", "unknown"),
            "evidence": {
                "report": report,
                "explain_path": str(explain_path) if explain_path is not None else "",
            },
            "generated_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _build_retro(*, report: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary": "auto-generated retrospective placeholder",
            "mergeable": bool(report.get("mergeable", False)),
            "failed_conditions": report.get("failed_conditions", []),
            "improvements": [],
            "generated_at": datetime.now(UTC).isoformat(),
        }
