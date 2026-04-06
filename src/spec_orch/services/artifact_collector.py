from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spec_orch.domain.models import (
    BuilderResult,
    GateInput,
    GateVerdict,
    Issue,
    IssueContext,
    ReviewSummary,
    RoundArtifacts,
    Wave,
    WorkPacket,
)
from spec_orch.services.gate_service import GatePolicy, GateService
from spec_orch.services.runtime_contracts import (
    build_gate_verdict_payload,
    build_verification_output_payload,
)
from spec_orch.services.verification_service import VerificationService


class ArtifactCollector:
    """Collects post-wave builder, verification, gate, and manifest artifacts."""

    def __init__(self, *, repo_root: Path, gate_policy: GatePolicy | None = None) -> None:
        self.repo_root = Path(repo_root)
        if gate_policy is not None:
            self._gate_policy = gate_policy
        else:
            policy_path = self.repo_root / "gate.policy.yaml"
            self._gate_policy = (
                GatePolicy.from_yaml(policy_path) if policy_path.exists() else GatePolicy.default()
            )

    def collect(
        self,
        *,
        host: Any,
        mission_id: str,
        round_id: int,
        wave: Wave,
        worker_results: list[tuple[WorkPacket, BuilderResult]],
        round_dir: Path,
    ) -> RoundArtifacts:
        visual_evaluation = host._run_visual_evaluation(
            mission_id=mission_id,
            round_id=round_id,
            wave=wave,
            worker_results=worker_results,
            round_dir=round_dir,
        )
        verification_outputs: list[dict[str, Any]] = []
        gate_verdicts: list[dict[str, Any]] = []
        manifest_paths: list[str] = []
        verification_service = VerificationService()
        gate_service = GateService(policy=self._gate_policy)

        for packet, result in worker_results:
            workspace = host._packet_workspace(mission_id, packet)
            if result.report_path.exists():
                manifest_paths.append(str(result.report_path))
            for file_path in packet.files_in_scope:
                scoped_path = workspace / file_path
                if scoped_path.exists():
                    manifest_paths.append(str(scoped_path))
            if not packet.verification_commands:
                continue

            verification = verification_service.run(
                issue=Issue(
                    issue_id=packet.packet_id,
                    title=packet.title,
                    summary=packet.title,
                    verification_commands=dict(packet.verification_commands),
                    context=IssueContext(),
                    acceptance_criteria=list(packet.acceptance_criteria),
                ),
                workspace=workspace,
            )
            verification_outputs.append(
                build_verification_output_payload(
                    packet_id=packet.packet_id,
                    workspace=workspace,
                    verification=verification,
                )
            )
            scope_proof = self.build_packet_scope_proof(
                workspace=workspace,
                packet=packet,
                report_path=result.report_path,
            )
            gate = gate_service.evaluate(
                GateInput(
                    builder_succeeded=result.succeeded,
                    verification=verification,
                    review=ReviewSummary(verdict="not_applicable"),
                )
            )
            failed_conditions = list(gate.failed_conditions)
            if not scope_proof["all_in_scope"] and "scope" not in failed_conditions:
                failed_conditions.append("scope")
            gate_verdicts.append(
                build_gate_verdict_payload(
                    packet_id=packet.packet_id,
                    gate=GateVerdict(
                        mergeable=gate.mergeable,
                        failed_conditions=failed_conditions,
                    ),
                    scope=scope_proof,
                )
            )

        return RoundArtifacts(
            round_id=round_id,
            mission_id=mission_id,
            builder_reports=[
                {
                    "packet_id": packet.packet_id,
                    "succeeded": result.succeeded,
                    "producer_role": "implementer",
                    "adapter": result.adapter,
                    "agent": result.agent,
                    "report_path": str(result.report_path),
                }
                for packet, result in worker_results
            ],
            verification_outputs=verification_outputs,
            gate_verdicts=gate_verdicts,
            manifest_paths=host._unique_preserve_order(manifest_paths),
            worker_session_ids=[
                f"mission-{mission_id}-{packet.packet_id}" for packet, _ in worker_results
            ],
            visual_evaluation=visual_evaluation,
        )

    def build_packet_scope_proof(
        self,
        *,
        workspace: Path,
        packet: WorkPacket,
        report_path: Path,
    ) -> dict[str, Any]:
        allowed = [str(path).strip() for path in packet.files_in_scope if str(path).strip()]
        allowed_set = set(allowed)
        excluded_paths = {report_path.resolve()}
        excluded_prefixes = ("telemetry/",)
        excluded_filenames = {"btw_context.md", "task.spec.md"}
        realized_files = self.load_realized_files_from_report(
            workspace=workspace,
            packet=packet,
            report_path=report_path,
        )
        if realized_files is None:
            realized_files = []
            for path in workspace.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    resolved = path.resolve()
                except OSError:
                    resolved = path
                if resolved in excluded_paths:
                    continue
                relative_path = path.relative_to(workspace).as_posix()
                if (
                    relative_path.startswith(excluded_prefixes)
                    or relative_path in excluded_filenames
                    or self.is_transient_verification_support_file(packet, relative_path)
                ):
                    continue
                realized_files.append(relative_path)
            realized_files = self._unique_preserve_order(realized_files)
        out_of_scope_files = [
            path
            for path in realized_files
            if path not in allowed_set
            and not self.is_transient_verification_support_file(packet, path)
        ]
        return {
            "allowed_files": allowed,
            "realized_files": realized_files,
            "out_of_scope_files": out_of_scope_files,
            "all_in_scope": not out_of_scope_files,
        }

    def load_realized_files_from_report(
        self,
        *,
        workspace: Path,
        packet: WorkPacket,
        report_path: Path,
    ) -> list[str] | None:
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        files_changed = payload.get("files_changed")
        if files_changed is None:
            return None
        if not isinstance(files_changed, list):
            return None
        realized_files: list[str] = []
        for raw_path in files_changed:
            text = str(raw_path).strip()
            if not text:
                continue
            path = Path(text)
            try:
                resolved = path.resolve() if path.is_absolute() else (workspace / path).resolve()
            except OSError:
                resolved = workspace / path if not path.is_absolute() else path
            try:
                relative_path = resolved.relative_to(workspace.resolve()).as_posix()
            except ValueError:
                continue
            if resolved.exists() and resolved.is_dir():
                continue
            if self.is_transient_verification_support_file(packet, relative_path):
                continue
            realized_files.append(relative_path)
        return self._unique_preserve_order(realized_files)

    def is_transient_verification_support_file(
        self, packet: WorkPacket, relative_path: str
    ) -> bool:
        verification_language = " ".join(
            " ".join(command) if isinstance(command, list) else str(command)
            for command in packet.verification_commands.values()
        ).lower()
        if not any(
            token in verification_language
            for token in ("lint", "typecheck", "type check", "eslint", "compile", "tsc")
        ):
            return False
        filename = Path(relative_path).name
        return filename in {
            "tsconfig.json",
            "eslint.config.js",
            "eslint.config.mjs",
            "eslint.config.cjs",
            ".eslintrc.js",
            ".eslintrc.json",
            "import_smoke.ts",
            "package.json",
            "package-lock.json",
            "pnpm-lock.yaml",
        }

    @staticmethod
    def _unique_preserve_order(items: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered
