"""ContextAssembler — builds a ContextBundle for any LLM node.

Reads artifacts from the workspace (via ArtifactManifest), pulls learning
history from MemoryService, and truncates each section to fit the node's
declared token budget.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from spec_orch.domain.context import (
    ContextBundle,
    ExecutionContext,
    LearningContext,
    NodeContextSpec,
    TaskContext,
)
from spec_orch.domain.models import (
    ArtifactManifest,
    GateVerdict,
    Issue,
    ReviewSummary,
    VerificationDetail,
    VerificationSummary,
)
from spec_orch.services.context_ranker import (
    ContextRanker,
    RankedSection,
    _detect_chars_per_token,
)

logger = logging.getLogger(__name__)


def _truncate(text: str, max_tokens: int) -> str:
    cpt = _detect_chars_per_token(text)
    limit = max_tokens * cpt
    if len(text) <= limit:
        return text
    suffix = "\n... [truncated]"
    return text[: limit - len(suffix)] + suffix


def _estimate_tokens(text: str) -> int:
    cpt = _detect_chars_per_token(text)
    return len(text) // cpt


class ContextAssembler:
    """Assembles a ContextBundle from workspace artifacts + memory."""

    def assemble(
        self,
        spec: NodeContextSpec,
        issue: Issue,
        workspace: Path,
        memory: Any | None = None,
        repo_root: Path | None = None,
    ) -> ContextBundle:
        manifest = self._load_manifest(workspace)
        budget = spec.max_tokens_budget
        oversized_budget = budget * 2

        task_ctx = self._build_task_context(
            issue, workspace, oversized_budget, spec.required_task_fields
        )
        exec_ctx = self._build_execution_context(
            workspace,
            manifest,
            oversized_budget,
            spec.required_execution_fields,
            exclude_framework_events=spec.exclude_framework_events,
        )
        learn_ctx = self._build_learning_context(
            repo_root or workspace, memory, oversized_budget, spec.required_learning_fields
        )

        sections = self._collect_ranked_sections(task_ctx, exec_ctx, learn_ctx)
        if sections:
            ranked = ContextRanker.allocate(sections, budget)
            self._apply_ranked_budget(task_ctx, exec_ctx, learn_ctx, ranked)

        return ContextBundle(task=task_ctx, execution=exec_ctx, learning=learn_ctx)

    @staticmethod
    def _collect_ranked_sections(
        task: TaskContext, exec_ctx: ExecutionContext, learn: LearningContext
    ) -> list[RankedSection]:
        from spec_orch.domain.context import CompactRetentionPriority as P

        sections: list[RankedSection] = []
        if task.spec_snapshot_text:
            sections.append(
                RankedSection(
                    "spec_snapshot_text",
                    task.spec_snapshot_text,
                    P.ARCHITECTURE_DECISIONS,
                )
            )
        if task.architecture_notes:
            sections.append(
                RankedSection(
                    "architecture_notes",
                    task.architecture_notes,
                    P.ARCHITECTURE_DECISIONS,
                )
            )
        if exec_ctx.file_tree:
            sections.append(
                RankedSection(
                    "file_tree",
                    exec_ctx.file_tree,
                    P.MODIFIED_FILES,
                )
            )
        if exec_ctx.git_diff:
            sections.append(
                RankedSection(
                    "git_diff",
                    exec_ctx.git_diff,
                    P.MODIFIED_FILES,
                )
            )
        if exec_ctx.builder_events_summary:
            sections.append(
                RankedSection(
                    "builder_events_summary",
                    exec_ctx.builder_events_summary,
                    P.TOOL_OUTPUT,
                )
            )
        return sections

    @staticmethod
    def _apply_ranked_budget(
        task: TaskContext,
        exec_ctx: ExecutionContext,
        learn: LearningContext,
        ranked: dict[str, str],
    ) -> None:
        if "spec_snapshot_text" in ranked:
            task.spec_snapshot_text = ranked["spec_snapshot_text"]
        if "architecture_notes" in ranked:
            task.architecture_notes = ranked["architecture_notes"]
        if "file_tree" in ranked:
            exec_ctx.file_tree = ranked["file_tree"]
        if "git_diff" in ranked:
            exec_ctx.git_diff = ranked["git_diff"]
        if "builder_events_summary" in ranked:
            exec_ctx.builder_events_summary = ranked["builder_events_summary"]

    @staticmethod
    def _load_manifest(workspace: Path) -> ArtifactManifest | None:
        candidates = [
            workspace / "run_artifact" / "manifest.json",
            workspace / "artifact_manifest.json",
        ]
        for manifest_path in candidates:
            if not manifest_path.exists():
                continue
            try:
                data = json.loads(manifest_path.read_text())
                return ArtifactManifest(
                    run_id=data.get("run_id", ""),
                    issue_id=data.get("issue_id", ""),
                    artifacts=data.get("artifacts", {}),
                    created_at=data.get("created_at", ""),
                )
            except (json.JSONDecodeError, KeyError):
                continue
        return None

    def _build_task_context(
        self,
        issue: Issue,
        workspace: Path,
        budget: int,
        required: list[str],
    ) -> TaskContext:
        spec_text = ""
        if not required or "spec_snapshot_text" in required:
            spec_path = workspace / "spec_snapshot.json"
            if spec_path.exists():
                try:
                    snap = json.loads(spec_path.read_text())
                    spec_text = snap.get("issue", {}).get("summary", "")
                except (json.JSONDecodeError, KeyError):
                    pass
            if not spec_text:
                task_spec_path = workspace / "task.spec.md"
                if task_spec_path.exists():
                    spec_text = task_spec_path.read_text()
            spec_text = _truncate(spec_text, budget // 2)

        return TaskContext(
            issue=issue,
            spec_snapshot_text=spec_text,
            acceptance_criteria=(
                list(issue.acceptance_criteria)
                if not required or "acceptance_criteria" in required
                else []
            ),
            constraints=(
                list(issue.context.constraints) if not required or "constraints" in required else []
            ),
            files_in_scope=(
                list(issue.context.files_to_read)
                if not required or "files_in_scope" in required
                else []
            ),
            files_out_of_scope=[],
            architecture_notes=(
                _truncate(issue.context.architecture_notes, budget // 4)
                if not required or "architecture_notes" in required
                else ""
            ),
        )

    @staticmethod
    def _filter_framework_events(raw: str) -> str:
        """Remove framework-internal events that LLM nodes should not see."""
        framework_topics = {
            "system",
            "conductor",
            "memory",
            "eval.sample",
            "tool.start",
            "tool.end",
        }
        lines = []
        for line in raw.splitlines():
            line_stripped = line.strip()
            if not line_stripped:
                continue
            try:
                obj = json.loads(line_stripped)
                topic = obj.get("topic", "")
                if topic in framework_topics:
                    continue
            except (json.JSONDecodeError, ValueError):
                pass
            lines.append(line)
        return "\n".join(lines)

    def _build_execution_context(
        self,
        workspace: Path,
        manifest: ArtifactManifest | None,
        budget: int,
        required: list[str],
        *,
        exclude_framework_events: bool = True,
    ) -> ExecutionContext:
        ctx = ExecutionContext()

        if "file_tree" in required:
            ctx.file_tree = _truncate(self._read_file_tree(workspace), budget // 4)

        if "git_diff" in required:
            ctx.git_diff = _truncate(self._read_git_diff(workspace), budget // 3)

        if manifest and "report" in manifest.artifacts:
            report_path = Path(manifest.artifacts["report"])
            if report_path.exists():
                try:
                    report = json.loads(report_path.read_text())
                    ctx.verification_results = self._parse_verification(report)
                    ctx.gate_report = self._parse_gate(report)
                except (json.JSONDecodeError, KeyError):
                    pass
        elif manifest and "live" in manifest.artifacts:
            live_path = Path(manifest.artifacts["live"])
            if live_path.exists():
                try:
                    live = json.loads(live_path.read_text())
                    if isinstance(live, dict):
                        ctx.verification_results = self._parse_verification(live)
                        ctx.gate_report = self._parse_gate(live)
                except (json.JSONDecodeError, KeyError):
                    pass

        if manifest and "builder_events" in manifest.artifacts:
            events_path = Path(manifest.artifacts["builder_events"])
            if events_path.exists():
                raw = events_path.read_text()
                if exclude_framework_events:
                    raw = self._filter_framework_events(raw)
                ctx.builder_events_summary = _truncate(raw, budget // 6)
        elif manifest and "events" in manifest.artifacts:
            events_path = Path(manifest.artifacts["events"])
            if events_path.exists():
                raw = events_path.read_text()
                if exclude_framework_events:
                    raw = self._filter_framework_events(raw)
                ctx.builder_events_summary = _truncate(raw, budget // 6)

        if manifest and "review_report" in manifest.artifacts:
            rr_path = Path(manifest.artifacts["review_report"])
            if rr_path.exists():
                try:
                    rdata = json.loads(rr_path.read_text())
                    ctx.review_summary = ReviewSummary(
                        verdict=rdata.get("verdict", "pending"),
                        reviewed_by=rdata.get("reviewed_by"),
                        report_path=rr_path,
                    )
                except (json.JSONDecodeError, KeyError):
                    pass

        if manifest and "deviations" in manifest.artifacts:
            dev_path = Path(manifest.artifacts["deviations"])
            if dev_path.exists():
                slices: list[dict[str, Any]] = []
                for line in dev_path.read_text().splitlines():
                    line = line.strip()
                    if line:
                        try:
                            slices.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                ctx.deviation_slices = slices

        return ctx

    def _build_learning_context(
        self,
        workspace: Path,
        memory: Any | None,
        budget: int,
        required: list[str],
    ) -> LearningContext:
        ctx = LearningContext()

        if memory is not None and "similar_failure_samples" in required:
            try:
                from spec_orch.services.memory.types import MemoryLayer, MemoryQuery

                entries = memory.recall(
                    MemoryQuery(
                        layer=MemoryLayer.EPISODIC,
                        tags=["issue-result"],
                        top_k=5,
                    )
                )
                samples: list[dict[str, Any]] = []
                for e in entries:
                    if e.metadata.get("succeeded") is False:
                        samples.append(
                            {
                                "key": e.key,
                                "content": _truncate(e.content, budget // 10),
                                "metadata": e.metadata,
                            }
                        )
                ctx.similar_failure_samples = samples
            except Exception:
                logger.debug("Failed to recall failure samples from memory", exc_info=True)

        if not required or "scoper_hints" in required:
            hints_path = workspace / "scoper_hints.json"
            if hints_path.exists():
                import contextlib

                with contextlib.suppress(json.JSONDecodeError, KeyError):
                    raw = json.loads(hints_path.read_text())
                    if isinstance(raw, dict):
                        ctx.scoper_hints = raw.get("hints", [])
                    elif isinstance(raw, list):
                        ctx.scoper_hints = raw

        if not required or "relevant_policies" in required:
            ctx.relevant_policies = self._load_relevant_policies(workspace)

        return ctx

    @staticmethod
    def _load_relevant_policies(repo_root: Path) -> list[str]:
        """Load policy IDs from the repo-level policies_index.json."""
        index_path = repo_root / "policies" / "policies_index.json"
        if not index_path.exists():
            return []
        try:
            raw = json.loads(index_path.read_text())
            if isinstance(raw, list):
                policies: list[str] = []
                for p in raw[:50]:
                    if isinstance(p, dict):
                        pid = p.get("policy_id")
                        if pid:
                            policies.append(str(pid))
                    elif isinstance(p, str):
                        policies.append(p)
                return policies
            if isinstance(raw, dict):
                return list(raw.keys())[:50]
        except (json.JSONDecodeError, OSError):
            logger.debug("Failed to load policies_index.json", exc_info=True)
        return []

    @staticmethod
    def _read_file_tree(workspace: Path, *, max_entries: int = 2000) -> str:
        try:
            lines: list[str] = []
            for p in sorted(workspace.rglob("*")):
                if ".git" in p.parts:
                    continue
                if p.is_file():
                    lines.append(str(p.relative_to(workspace)))
                    if len(lines) >= max_entries:
                        lines.append(f"... ({max_entries}+ files, truncated)")
                        break
            return "\n".join(lines)
        except OSError:
            return ""

    @staticmethod
    def _read_git_diff(workspace: Path) -> str:
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout
        except (subprocess.SubprocessError, FileNotFoundError):
            return ""

    @staticmethod
    def _parse_verification(report: dict[str, Any]) -> VerificationSummary | None:
        verification = report.get("verification")
        if not isinstance(verification, dict):
            return None
        details: dict[str, VerificationDetail] = {}
        for name, data in verification.items():
            if isinstance(data, dict):
                details[name] = VerificationDetail(
                    command=data.get("command", []),
                    exit_code=data.get("exit_code", -1),
                    stdout="",
                    stderr="",
                )
        if not details:
            return None
        summary = VerificationSummary(details=details)
        for name, detail in details.items():
            summary.set_step_passed(name, detail.exit_code == 0)
        return summary

    @staticmethod
    def _parse_gate(report: dict[str, Any]) -> GateVerdict | None:
        mergeable = report.get("mergeable")
        if mergeable is None:
            return None
        return GateVerdict(
            mergeable=bool(mergeable),
            failed_conditions=report.get("failed_conditions", []),
        )
