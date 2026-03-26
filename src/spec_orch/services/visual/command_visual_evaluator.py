from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from spec_orch.domain.models import BuilderResult, VisualEvaluationResult, Wave, WorkPacket
from spec_orch.services.io import atomic_write_json, atomic_write_text


class CommandVisualEvaluator:
    """Runs an external command that returns a visual evaluation JSON payload."""

    ADAPTER_NAME = "command"

    def __init__(
        self,
        *,
        command: list[str],
        timeout_seconds: int = 300,
    ) -> None:
        self.command = list(command)
        self.timeout_seconds = timeout_seconds

    def evaluate_round(
        self,
        *,
        mission_id: str,
        round_id: int,
        wave: Wave,
        worker_results: list[tuple[WorkPacket, BuilderResult]],
        repo_root: Path,
        round_dir: Path,
    ) -> VisualEvaluationResult | None:
        visual_dir = round_dir / "visual"
        visual_dir.mkdir(parents=True, exist_ok=True)
        input_json = visual_dir / "input.json"
        output_json = visual_dir / "output.json"
        stdout_log = visual_dir / "command.stdout.log"
        stderr_log = visual_dir / "command.stderr.log"

        payload = self._build_payload(
            mission_id=mission_id,
            round_id=round_id,
            wave=wave,
            worker_results=worker_results,
            round_dir=round_dir,
        )
        atomic_write_json(input_json, payload)
        command = [
            self._resolve_token(
                token,
                mission_id=mission_id,
                round_id=round_id,
                repo_root=repo_root,
                round_dir=round_dir,
                input_json=input_json,
                output_json=output_json,
            )
            for token in self.command
        ]

        try:
            result = subprocess.run(
                command,
                cwd=repo_root,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            return self._error_result(
                f"visual evaluator command failed to start: {exc}",
                input_json=input_json,
                output_json=output_json,
                stdout_log=stdout_log,
                stderr_log=stderr_log,
            )

        atomic_write_text(stdout_log, result.stdout)
        atomic_write_text(stderr_log, result.stderr)

        if result.returncode != 0:
            return self._error_result(
                f"visual evaluator exited with exit code {result.returncode}",
                input_json=input_json,
                output_json=output_json,
                stdout_log=stdout_log,
                stderr_log=stderr_log,
            )

        raw_output = (
            output_json.read_text(encoding="utf-8")
            if output_json.exists()
            else result.stdout.strip()
        )
        if not raw_output:
            return self._error_result(
                "visual evaluator produced no JSON output",
                input_json=input_json,
                output_json=output_json,
                stdout_log=stdout_log,
                stderr_log=stderr_log,
            )

        try:
            parsed = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            return self._error_result(
                f"visual evaluator returned invalid JSON: {exc}",
                input_json=input_json,
                output_json=output_json,
                stdout_log=stdout_log,
                stderr_log=stderr_log,
            )
        if not isinstance(parsed, dict):
            return self._error_result(
                "visual evaluator output must be a JSON object",
                input_json=input_json,
                output_json=output_json,
                stdout_log=stdout_log,
                stderr_log=stderr_log,
            )

        artifacts = dict(parsed.get("artifacts", {}))
        artifacts.setdefault("input_json", str(input_json))
        artifacts.setdefault("output_json", str(output_json))
        artifacts.setdefault("stdout_log", str(stdout_log))
        artifacts.setdefault("stderr_log", str(stderr_log))
        parsed["artifacts"] = artifacts
        parsed.setdefault("evaluator", self.ADAPTER_NAME)
        return VisualEvaluationResult.from_dict(parsed)

    def _error_result(
        self,
        summary: str,
        *,
        input_json: Path,
        output_json: Path,
        stdout_log: Path,
        stderr_log: Path,
    ) -> VisualEvaluationResult:
        return VisualEvaluationResult(
            evaluator=self.ADAPTER_NAME,
            summary=summary,
            confidence=0.0,
            findings=[{"severity": "error", "summary": summary}],
            artifacts={
                "input_json": str(input_json),
                "output_json": str(output_json),
                "stdout_log": str(stdout_log),
                "stderr_log": str(stderr_log),
            },
        )

    @staticmethod
    def _resolve_token(
        token: str,
        *,
        mission_id: str,
        round_id: int,
        repo_root: Path,
        round_dir: Path,
        input_json: Path,
        output_json: Path,
    ) -> str:
        replacements = {
            "{python}": sys.executable,
            "{mission_id}": mission_id,
            "{round_id}": str(round_id),
            "{repo_root}": str(repo_root),
            "{round_dir}": str(round_dir),
            "{input_json}": str(input_json),
            "{output_json}": str(output_json),
        }
        resolved = token
        for placeholder, value in replacements.items():
            resolved = resolved.replace(placeholder, value)
        return resolved

    @staticmethod
    def _build_payload(
        *,
        mission_id: str,
        round_id: int,
        wave: Wave,
        worker_results: list[tuple[WorkPacket, BuilderResult]],
        round_dir: Path,
    ) -> dict[str, Any]:
        return {
            "mission_id": mission_id,
            "round_id": round_id,
            "round_dir": str(round_dir),
            "wave": {
                "wave_number": wave.wave_number,
                "description": wave.description,
                "packet_ids": [packet.packet_id for packet in wave.work_packets],
            },
            "worker_results": [
                {
                    "packet_id": packet.packet_id,
                    "title": packet.title,
                    "succeeded": result.succeeded,
                    "report_path": str(result.report_path),
                    "adapter": result.adapter,
                    "agent": result.agent,
                }
                for packet, result in worker_results
            ],
        }
