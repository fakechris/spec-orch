"""ContextAssembler — builds a ContextBundle for any LLM node.

Reads artifacts from the workspace (via ArtifactManifest), pulls learning
history from MemoryService, and truncates each section to fit the node's
declared token budget.
"""

from __future__ import annotations

import json
import logging
import re
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
from spec_orch.services.context.context_ranker import (
    ContextRanker,
    RankedSection,
    _detect_chars_per_token,
)
from spec_orch.services.skill_format import SkillManifest

logger = logging.getLogger(__name__)

_MAX_MATCHED_SKILLS = 10


def _truncate(text: str, max_tokens: int) -> str:
    cpt = _detect_chars_per_token(text)
    limit = max_tokens * cpt
    if len(text) <= limit:
        return text
    suffix = "\n... [truncated]"
    if limit <= len(suffix) + 10:
        return text[: max(limit, 0)]
    return text[: limit - len(suffix)] + suffix


def _estimate_tokens(text: str) -> int:
    cpt = _detect_chars_per_token(text)
    return len(text) // cpt


def _skill_to_context(m: SkillManifest) -> dict[str, Any]:
    d: dict[str, Any] = {"id": m.id, "name": m.name, "description": m.description}
    instructions = m.params.get("instructions")
    if instructions:
        d["instructions"] = instructions
    tool_sequence = m.params.get("tool_sequence")
    if tool_sequence:
        d["tool_sequence"] = tool_sequence
    return d


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
            repo_root or workspace,
            memory,
            oversized_budget,
            spec.required_learning_fields,
            issue_title=issue.title,
            issue_summary=issue.summary,
        )

        contexts: dict[str, Any] = {
            "task": task_ctx,
            "execution": exec_ctx,
            "learning": learn_ctx,
        }
        sections = self._collect_ranked_sections(contexts)
        if sections:
            ranked = ContextRanker.allocate(sections, budget)
            self._apply_ranked_budget(contexts, ranked)

        return ContextBundle(task=task_ctx, execution=exec_ctx, learning=learn_ctx)

    _SECTION_DEFS: list[tuple[str, str, int]] = []

    @staticmethod
    def _section_definitions() -> list[tuple[str, str, int]]:
        from spec_orch.domain.context import CompactRetentionPriority as P

        return [
            ("spec_snapshot_text", "task", P.ARCHITECTURE_DECISIONS),
            ("architecture_notes", "task", P.ARCHITECTURE_DECISIONS),
            ("file_tree", "execution", P.MODIFIED_FILES),
            ("git_diff", "execution", P.MODIFIED_FILES),
            ("builder_events_summary", "execution", P.TOOL_OUTPUT),
        ]

    @classmethod
    def _collect_ranked_sections(
        cls,
        contexts: dict[str, Any],
    ) -> list[RankedSection]:
        from spec_orch.domain.context import CompactRetentionPriority as P

        sections: list[RankedSection] = []
        for name, ctx_key, priority in cls._section_definitions():
            content = getattr(contexts.get(ctx_key), name, None)
            if content:
                sections.append(RankedSection(name, content, priority))

        learn = contexts.get("learning")
        if learn is not None:
            cls._add_learning_sections(learn, sections, P)
        return sections

    @staticmethod
    def _add_learning_sections(
        learn: Any,
        sections: list[RankedSection],
        priorities: Any,
    ) -> None:
        """Serialize learning-context list/dict fields for ranked allocation."""
        hints = getattr(learn, "scoper_hints", None)
        if hints:
            text = json.dumps(hints, ensure_ascii=False, indent=1)
            sections.append(RankedSection("scoper_hints", text, priorities.UNRESOLVED_TODOS))

        skills = getattr(learn, "matched_skills", None)
        if skills:
            text = json.dumps(skills, ensure_ascii=False, indent=1)
            sections.append(RankedSection("matched_skills", text, priorities.UNRESOLVED_TODOS))

        samples = getattr(learn, "similar_failure_samples", None)
        if samples:
            text = json.dumps(samples, ensure_ascii=False, indent=1)
            sections.append(RankedSection("similar_failure_samples", text, priorities.TOOL_OUTPUT))

        procedures = getattr(learn, "relevant_procedures", None)
        if procedures:
            text = json.dumps(procedures, ensure_ascii=False, indent=1)
            sections.append(RankedSection("relevant_procedures", text, priorities.TOOL_OUTPUT))

        trend = getattr(learn, "success_trend", None)
        if trend:
            text = json.dumps(trend, ensure_ascii=False, indent=1)
            sections.append(RankedSection("success_trend", text, priorities.TOOL_OUTPUT))

        profile = getattr(learn, "project_profile", None)
        if profile:
            text = json.dumps(profile, ensure_ascii=False, indent=1)
            sections.append(RankedSection("project_profile", text, priorities.MODIFIED_FILES))

        fp = getattr(learn, "failure_patterns", None)
        if fp:
            text = json.dumps(fp, ensure_ascii=False, indent=1)
            sections.append(RankedSection("failure_patterns", text, priorities.VERIFICATION_STATE))

        sr = getattr(learn, "success_recipes", None)
        if sr:
            text = json.dumps(sr, ensure_ascii=False, indent=1)
            sections.append(RankedSection("success_recipes", text, priorities.TOOL_OUTPUT))

        signals = getattr(learn, "active_run_signals", None)
        if signals:
            text = json.dumps(signals, ensure_ascii=False, indent=1)
            sections.append(RankedSection("active_run_signals", text, priorities.TOOL_OUTPUT))

    _LEARNING_LIST_FIELDS = frozenset(
        {
            "scoper_hints",
            "matched_skills",
            "similar_failure_samples",
            "relevant_procedures",
            "failure_patterns",
            "success_recipes",
        }
    )
    _LEARNING_DICT_FIELDS = frozenset({"success_trend", "project_profile", "active_run_signals"})

    @classmethod
    def _apply_ranked_budget(
        cls,
        contexts: dict[str, Any],
        ranked: dict[str, str],
    ) -> None:
        for name, ctx_key, _ in cls._section_definitions():
            if name in ranked:
                setattr(contexts[ctx_key], name, ranked[name])

        learn = contexts.get("learning")
        if learn is None:
            return
        for name in cls._LEARNING_LIST_FIELDS:
            if name not in ranked:
                continue
            text = ranked[name]
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    setattr(learn, name, parsed)
            except (json.JSONDecodeError, TypeError):
                original = getattr(learn, name, [])
                if not isinstance(original, list) or not original:
                    setattr(learn, name, [])
                    continue
                budget_chars = len(text)
                trimmed = cls._trim_list_to_budget(original, budget_chars)
                setattr(learn, name, trimmed)
                logger.debug(
                    "ContextRanker truncated %s: %d→%d items to fit budget",
                    name,
                    len(original),
                    len(trimmed),
                )
        for name in cls._LEARNING_DICT_FIELDS:
            if name not in ranked:
                continue
            text = ranked[name]
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    setattr(learn, name, parsed)
                else:
                    setattr(learn, name, {})
            except (json.JSONDecodeError, TypeError):
                setattr(learn, name, {})
                logger.debug(
                    "ContextRanker non-JSON dict for %s; empty dict fallback",
                    name,
                )

    @staticmethod
    def _trim_list_to_budget(items: list[Any], budget_chars: int) -> list[Any]:
        """Remove items from the end until serialized JSON fits budget."""
        for end in range(len(items), 0, -1):
            candidate = json.dumps(items[:end], ensure_ascii=False, indent=1)
            if len(candidate) <= budget_chars:
                return items[:end]
        return []

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
                if not isinstance(data, dict):
                    logger.warning("Manifest %s is not a JSON object", manifest_path)
                    continue
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
                    if isinstance(report, dict):
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
                    if isinstance(rdata, dict):
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
        *,
        issue_title: str = "",
        issue_summary: str = "",
    ) -> LearningContext:
        ctx = LearningContext()

        if memory is not None and "similar_failure_samples" in required:
            try:
                from spec_orch.services.memory.types import MemoryLayer, MemoryQuery

                query_text = " ".join(filter(None, [issue_title, issue_summary]))
                entries = memory.recall(
                    MemoryQuery(
                        text=query_text,
                        layer=MemoryLayer.EPISODIC,
                        tags=["issue-result"],
                        top_k=10,
                    )
                )
                samples: list[dict[str, Any]] = []
                for e in entries:
                    if e.metadata.get("relation_type") == "superseded":
                        continue
                    if e.metadata.get("succeeded") is False:
                        samples.append(
                            {
                                "key": e.key,
                                "content": _truncate(e.content, budget // 10),
                                "metadata": e.metadata,
                            }
                        )
                        if len(samples) >= 5:
                            break
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

        if not required or "matched_skills" in required:
            ctx.matched_skills = self._build_skill_context(workspace, issue_title, issue_summary)

        if memory is not None and (not required or "relevant_procedures" in required):
            try:
                from spec_orch.services.memory.types import MemoryLayer, MemoryQuery

                query_text = " ".join(filter(None, [issue_title, issue_summary]))
                proc_entries = memory.recall(
                    MemoryQuery(
                        text=query_text,
                        layer=MemoryLayer.PROCEDURAL,
                        top_k=5,
                    )
                )
                ctx.relevant_procedures = [
                    {
                        "key": e.key,
                        "content": _truncate(e.content, budget // 10),
                        "tags": e.tags,
                    }
                    for e in proc_entries
                ]
            except Exception:
                logger.debug("Failed to recall procedures from memory", exc_info=True)

        if memory is not None and (not required or "success_trend" in required):
            try:
                if hasattr(memory, "get_trend_summary"):
                    ctx.success_trend = memory.get_trend_summary()
            except Exception:
                logger.debug("Failed to build success trend", exc_info=True)

        if memory is not None and (not required or "project_profile" in required):
            try:
                if hasattr(memory, "get_project_profile"):
                    ctx.project_profile = memory.get_project_profile()
            except Exception:
                logger.debug("Failed to build project profile", exc_info=True)

        if memory is not None and (not required or "failure_patterns" in required):
            try:
                if hasattr(memory, "get_failure_patterns"):
                    ctx.failure_patterns = memory.get_failure_patterns()
            except Exception:
                logger.debug("Failed to build failure patterns", exc_info=True)

        if memory is not None and (not required or "success_recipes" in required):
            try:
                if hasattr(memory, "get_success_recipes"):
                    ctx.success_recipes = memory.get_success_recipes()
            except Exception:
                logger.debug("Failed to build success recipes", exc_info=True)

        if memory is not None and (not required or "active_run_signals" in required):
            try:
                if hasattr(memory, "get_active_run_signals"):
                    ctx.active_run_signals = memory.get_active_run_signals()
            except Exception:
                logger.debug("Failed to build active run signals", exc_info=True)

        return ctx

    @staticmethod
    def _build_skill_context(
        repo_root: Path,
        issue_title: str,
        issue_summary: str,
    ) -> list[dict[str, Any]]:
        from spec_orch.services.skill_format import default_skills_dir, load_skills_from_dir

        skills_dir = default_skills_dir(repo_root)
        manifests, _ = load_skills_from_dir(skills_dir)
        if not manifests:
            return []

        search_text = f"{issue_title} {issue_summary}".lower()
        matched: list[dict[str, Any]] = []
        for m in manifests:
            if not m.triggers:
                continue
            alts = "|".join(re.escape(t.lower()) for t in m.triggers)
            pattern = r"(?<!\w)(" + alts + r")(?!\w)"
            if re.search(pattern, search_text):
                matched.append(_skill_to_context(m))
        return matched[:_MAX_MATCHED_SKILLS]

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
