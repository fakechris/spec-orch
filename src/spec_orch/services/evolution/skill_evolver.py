"""Skill Evolver — infer reusable builder-hook skills from telemetry tool traces."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from spec_orch.domain.models import (
    EvolutionChangeType,
    EvolutionOutcome,
    EvolutionProposal,
    EvolutionValidationMethod,
)
from spec_orch.services.evidence_analyzer import EvidenceAnalyzer
from spec_orch.services.io import atomic_write_text
from spec_orch.services.skill_format import (
    VALID_KINDS,
    SkillManifest,
    default_skills_dir,
    load_skills_from_dir,
    parse_skill_manifest,
    validate_skill_manifest,
)

logger = logging.getLogger(__name__)


def _coerce_skill_manifest(data: dict[str, Any]) -> SkillManifest | None:
    m, errs = parse_skill_manifest(data)
    if m is None:
        logger.debug("parse_skill_manifest failed: %s", errs)
    return m


def _version_is_newer(new: str, old: str) -> bool:
    """Compare semver-like version strings (best effort).

    Strips pre-release suffixes (e.g. ``-alpha``, ``-rc1``) before
    comparing numeric components so ``1.0.0-alpha > 0.9.0`` holds.
    """

    def _parts(v: str) -> tuple[int, ...]:
        try:
            numeric = v.split("-", 1)[0]  # strip pre-release suffix
            return tuple(int(x) for x in numeric.split("."))
        except (ValueError, AttributeError):
            return (0,)

    return _parts(new) > _parts(old)


_MAX_JSONL_LINES_PER_RUN = 4000
_MAX_SEQUENCE_LEN = 64
_MAX_RUNS_IN_PROMPT = 30
_MAX_SUMMARY_CHARS = 12000
_MAX_CONTEXT_SUMMARY_CHARS = 4000
_PROPOSAL_CONFIDENCE_THRESHOLD = 0.5

_SKILL_SYSTEM_PROMPT = """\
You are an evolution analyst for an AI coding-agent orchestrator (SpecOrch).

You receive tool-call / builder event traces from historical runs: ordered sequences
derived from telemetry (e.g. RPC methods, item types, or event kinds).

Identify **repeated compositions** — stable patterns such as:
read → search → edit → lint → test, or search → read → patch → verify.

For each distinct, reusable pattern, propose one declarative **SkillManifest**-style
object suitable for kind `builder_hook`:
- `id`: unique kebab-case id starting with `auto-skill-`
- `name`: short human-readable title
- `kind`: must be `builder_hook`
- `description`: what the skill encodes
- `triggers`: 2–6 short keywords or phrases that should suggest this skill
- `params`: must include `tool_sequence` (ordered list of tool/event labels matching
  the pattern) and `instructions` (how a builder should apply this skill)

Respond with ONLY a JSON object:
{
  "skills": [
    {
      "id": "auto-skill-example",
      "name": "descriptive name",
      "kind": "builder_hook",
      "description": "what this skill does",
      "triggers": ["keyword1", "keyword2"],
      "params": {
        "tool_sequence": ["tool1", "tool2", "tool3"],
        "instructions": "how to apply this skill"
      },
      "confidence": "low|medium|high"
    }
  ],
  "analysis_summary": "brief paragraph of what you observed"
}
"""


def _event_tool_signature(ev: dict[str, Any]) -> str | None:
    method = ev.get("method")
    if isinstance(method, str) and method.strip():
        return method.strip()
    etype = ev.get("type", "")
    item = ev.get("item") if isinstance(ev.get("item"), dict) else {}
    itype = item.get("type", "") if isinstance(item, dict) else ""
    parts = [p for p in (str(etype).strip(), str(itype).strip()) if p]
    if parts:
        return "/".join(parts)
    kind = ev.get("kind")
    if isinstance(kind, str) and kind.strip():
        return kind.strip()
    return None


def _dedupe_run(seq: list[str]) -> list[str]:
    out: list[str] = []
    for s in seq:
        if not out or out[-1] != s:
            out.append(s)
    return out[:_MAX_SEQUENCE_LEN]


def _read_incoming_sequences(run_dir: Path) -> tuple[list[str], int, str]:
    """Return (deduplicated tool sequence, lines scanned, actual path used)."""
    path = run_dir / "telemetry" / "incoming_events.jsonl"
    if not path.exists():
        alt = run_dir / "builder_events.jsonl"
        path = alt if alt.exists() else path
    if not path.exists():
        return [], 0, str(path)

    seq: list[str] = []
    lines_read = 0
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read telemetry %s: %s", path, exc)
        return [], 0, str(path)

    for line in text.splitlines():
        if lines_read >= _MAX_JSONL_LINES_PER_RUN:
            break
        line = line.strip()
        if not line:
            continue
        lines_read += 1
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        sig = _event_tool_signature(obj)
        if sig:
            seq.append(sig)

    return _dedupe_run(seq), lines_read, str(path)


def _builder_summary_from_context(context: Any | None) -> str:
    if context is None:
        return ""
    execution = getattr(context, "execution", None)
    if execution is None:
        return ""
    raw = getattr(execution, "builder_events_summary", "") or ""
    return raw if isinstance(raw, str) else ""


class SkillEvolver:
    """Discover builder tool-sequence patterns and propose SkillManifest YAML files."""

    EVOLVER_NAME: str = "skill_evolver"

    def __init__(self, repo_root: Path, planner: Any | None = None) -> None:
        self._repo_root = repo_root
        self._planner = planner

    def observe(
        self,
        run_dirs: list[Path],
        *,
        context: Any | None = None,
    ) -> list[dict[str, Any]]:
        runs_out: list[dict[str, Any]] = []
        for rd in run_dirs:
            if not rd.is_dir():
                continue
            seq, line_count, actual_path = _read_incoming_sequences(rd)
            if not seq and line_count == 0:
                continue
            runs_out.append(
                {
                    "run_id": rd.name,
                    "telemetry_path": actual_path,
                    "lines_scanned": line_count,
                    "tool_sequence": seq,
                }
            )

        summary = _builder_summary_from_context(context)
        payload: dict[str, Any] = {
            "runs": runs_out[-_MAX_RUNS_IN_PROMPT:],
            "builder_events_summary": summary[:_MAX_SUMMARY_CHARS] if summary else "",
        }

        if not payload["runs"] and not (payload["builder_events_summary"] or "").strip():
            return []

        analyzer = EvidenceAnalyzer(self._repo_root)
        ev_summary = analyzer.analyze()
        if ev_summary.total_runs > 0:
            payload["evidence_digest"] = {
                "total_runs": ev_summary.total_runs,
                "success_rate": round(ev_summary.success_rate, 4),
            }

        semantic_summaries = self._recall_semantic_run_summaries()
        if semantic_summaries:
            payload["run_outcome_summaries"] = semantic_summaries

        return [payload]

    def _recall_semantic_run_summaries(self) -> list[dict[str, Any]]:
        """Pull structured run outcomes from MemoryService semantic layer."""
        try:
            from spec_orch.services.memory.service import get_memory_service
            from spec_orch.services.memory.types import MemoryLayer, MemoryQuery

            memory = get_memory_service(repo_root=self._repo_root)
            entries = memory.recall(
                MemoryQuery(
                    layer=MemoryLayer.SEMANTIC,
                    tags=["run-summary"],
                    top_k=20,
                )
            )
            return [
                {
                    "run_id": e.metadata.get("run_id", ""),
                    "issue_id": e.metadata.get("issue_id", ""),
                    "succeeded": e.metadata.get("succeeded"),
                    "failed_conditions": e.metadata.get("failed_conditions", []),
                    "summary": e.content,
                }
                for e in entries
                if e.metadata
            ]
        except Exception:
            logger.debug("Could not recall semantic run summaries", exc_info=True)
            return []

    def propose(
        self,
        evidence: list[dict[str, Any]],
        *,
        context: Any | None = None,
    ) -> list[EvolutionProposal]:
        if self._planner is None:
            return []
        if not evidence:
            return []

        block = evidence[0]
        runs = block.get("runs") or []
        if not runs and not (block.get("builder_events_summary") or "").strip():
            return []

        user_parts = [
            "Observed builder telemetry aggregates:\n```json\n",
            json.dumps(block, indent=2, ensure_ascii=False),
            "\n```\n\n",
        ]
        ctx_extra = self._render_context_for_analysis(context)
        if ctx_extra:
            user_parts.append(ctx_extra)
        user_parts.append(
            "Identify recurring tool-call compositions and emit skill proposals "
            "as specified in the system instructions."
        )
        user_msg = "".join(user_parts)

        try:
            response = self._planner.brainstorm(
                conversation_history=[
                    {"role": "system", "content": _SKILL_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                codebase_context="",
            )
        except Exception:
            logger.exception("LLM call failed during skill_evolver.propose")
            return []

        parsed = self._parse_response(response)
        if not parsed:
            return []

        skills_raw, _analysis = parsed
        proposals: list[EvolutionProposal] = []
        now = datetime.now(UTC).isoformat()
        for i, sk in enumerate(skills_raw):
            sid = str(sk.get("id", f"auto-skill-{i}")).strip()
            conf_key = str(sk.get("confidence", "medium")).lower()
            conf = {"high": 0.9, "medium": 0.6, "low": 0.3}.get(conf_key, 0.5)
            proposals.append(
                EvolutionProposal(
                    proposal_id=f"skill-{sid}",
                    evolver_name=self.EVOLVER_NAME,
                    change_type=EvolutionChangeType.HARNESS_RULE,
                    content=dict(sk),
                    evidence=list(evidence),
                    confidence=conf,
                    created_at=now,
                )
            )
        return proposals

    def _parse_response(self, response: Any) -> tuple[list[dict[str, Any]], str] | None:
        if not isinstance(response, str):
            logger.warning("Non-string LLM response: %s", type(response).__name__)
            return None

        text = response.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            logger.warning("Could not find JSON object in skill_evolver response")
            return None

        try:
            obj = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from skill_evolver response")
            return None

        if not isinstance(obj, dict):
            return None

        skills: list[dict[str, Any]] = []
        for item in obj.get("skills", []):
            if isinstance(item, dict):
                skills.append(item)

        return skills, str(obj.get("analysis_summary", ""))

    def validate(self, proposal: EvolutionProposal) -> EvolutionOutcome:
        skills_dir = default_skills_dir(self._repo_root)
        existing, _warn = load_skills_from_dir(skills_dir)
        existing_by_id = {m.id: m for m in existing}

        content = proposal.content
        if not isinstance(content, dict):
            return EvolutionOutcome(
                proposal_id=proposal.proposal_id,
                accepted=False,
                validation_method=EvolutionValidationMethod.RULE_VALIDATOR,
                reason="proposal content is not an object",
            )

        pid = str(content.get("id", "")).strip()
        prev = existing_by_id.get(pid)
        if prev is not None:
            new_ver = str(content.get("version", "0.1.0")).strip()
            if not _version_is_newer(new_ver, prev.version):
                return EvolutionOutcome(
                    proposal_id=proposal.proposal_id,
                    accepted=False,
                    validation_method=EvolutionValidationMethod.RULE_VALIDATOR,
                    reason=(f"skill {pid!r} v{new_ver} is not newer than existing v{prev.version}"),
                )

        manifest_dict = self._content_to_manifest_dict(content)
        kind_early = str(content.get("kind", "")).strip()
        if kind_early and kind_early not in VALID_KINDS:
            return EvolutionOutcome(
                proposal_id=proposal.proposal_id,
                accepted=False,
                validation_method=EvolutionValidationMethod.RULE_VALIDATOR,
                reason=f"unknown kind {kind_early!r}",
            )

        issues = validate_skill_manifest(manifest_dict)
        if issues:
            return EvolutionOutcome(
                proposal_id=proposal.proposal_id,
                accepted=False,
                validation_method=EvolutionValidationMethod.RULE_VALIDATOR,
                reason="; ".join(issues[:5]),
            )

        coerced = _coerce_skill_manifest(manifest_dict)
        if coerced is None:
            return EvolutionOutcome(
                proposal_id=proposal.proposal_id,
                accepted=False,
                validation_method=EvolutionValidationMethod.RULE_VALIDATOR,
                reason="skill manifest failed parse_skill_manifest",
            )

        params = content.get("params")
        if not isinstance(params, dict):
            return EvolutionOutcome(
                proposal_id=proposal.proposal_id,
                accepted=False,
                validation_method=EvolutionValidationMethod.RULE_VALIDATOR,
                reason="params must be a mapping",
            )

        ts = params.get("tool_sequence")
        if not isinstance(ts, list) or not ts:
            return EvolutionOutcome(
                proposal_id=proposal.proposal_id,
                accepted=False,
                validation_method=EvolutionValidationMethod.RULE_VALIDATOR,
                reason="params.tool_sequence must be a non-empty list",
            )
        if not all(isinstance(x, str) and x.strip() for x in ts):
            return EvolutionOutcome(
                proposal_id=proposal.proposal_id,
                accepted=False,
                validation_method=EvolutionValidationMethod.RULE_VALIDATOR,
                reason="params.tool_sequence must be non-empty strings",
            )

        instr = params.get("instructions", "")
        if not isinstance(instr, str) or not instr.strip():
            return EvolutionOutcome(
                proposal_id=proposal.proposal_id,
                accepted=False,
                validation_method=EvolutionValidationMethod.RULE_VALIDATOR,
                reason="params.instructions must be a non-empty string",
            )

        kind = str(content.get("kind", "")).strip()
        if kind != "builder_hook":
            return EvolutionOutcome(
                proposal_id=proposal.proposal_id,
                accepted=False,
                validation_method=EvolutionValidationMethod.RULE_VALIDATOR,
                reason=f"kind must be builder_hook, got {kind!r}",
            )

        ground_truth = self._query_ground_truth(coerced.triggers)
        effective_confidence = self._blend_confidence(proposal.confidence, ground_truth)

        accepted = effective_confidence >= _PROPOSAL_CONFIDENCE_THRESHOLD
        metrics = {
            "confidence": proposal.confidence,
            "effective_confidence": effective_confidence,
            "tool_sequence_len": float(len(ts)),
            "trigger_count": float(len(coerced.triggers)),
        }
        if ground_truth is not None:
            metrics["ground_truth_success_rate"] = ground_truth

        reason = ""
        if not accepted:
            reason = (
                f"effective confidence {effective_confidence:.2f} "
                f"below threshold ({_PROPOSAL_CONFIDENCE_THRESHOLD})"
            )
        return EvolutionOutcome(
            proposal_id=proposal.proposal_id,
            accepted=accepted,
            validation_method=EvolutionValidationMethod.RULE_VALIDATOR,
            metrics=metrics,
            reason=reason,
        )

    def _query_ground_truth(self, triggers: list[str]) -> float | None:
        """Query semantic memory for historical success rate of related runs."""
        try:
            from spec_orch.services.memory.service import get_memory_service
            from spec_orch.services.memory.types import MemoryLayer, MemoryQuery

            memory = get_memory_service(repo_root=self._repo_root)
            entries = memory.recall(
                MemoryQuery(
                    layer=MemoryLayer.SEMANTIC,
                    tags=["run-summary"],
                    top_k=50,
                )
            )
            if len(entries) < 3:
                return None
            succeeded = sum(1 for e in entries if e.metadata.get("succeeded") is True)
            return succeeded / len(entries)
        except Exception:
            logger.debug("Could not query ground truth", exc_info=True)
            return None

    @staticmethod
    def _blend_confidence(llm_confidence: float, ground_truth: float | None) -> float:
        """Blend LLM-reported confidence with empirical success rate.

        When ground truth is available (>= 3 runs), weight it 40%.
        """
        if ground_truth is None:
            return llm_confidence
        return 0.6 * llm_confidence + 0.4 * ground_truth

    @staticmethod
    def _content_to_manifest_dict(content: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "id": content.get("id", ""),
            "name": content.get("name", ""),
            "kind": content.get("kind", ""),
            "version": content.get("version", "0.1.0"),
            "description": content.get("description", ""),
            "author": content.get("author", "") or "skill_evolver",
            "triggers": content.get("triggers", []),
            "params": content.get("params", {}),
        }

    def promote(self, proposal: EvolutionProposal) -> bool:
        content = proposal.content
        if not isinstance(content, dict):
            return False

        manifest_dict = self._content_to_manifest_dict(content)
        manifest_dict["author"] = str(manifest_dict.get("author") or "skill_evolver")

        parsed = _coerce_skill_manifest(manifest_dict)
        if parsed is None:
            logger.warning("promote: could not parse skill manifest")
            return False

        sid = parsed.id.strip()
        if not sid or not re.match(r"^[\w.-]+$", sid):
            logger.warning("promote: unsafe or empty skill id %r", sid)
            return False

        skills_dir = default_skills_dir(self._repo_root)
        skills_dir.mkdir(parents=True, exist_ok=True)
        out_path = skills_dir / f"{sid}.yaml"

        is_update = out_path.exists()

        yaml_body = yaml.safe_dump(
            parsed.to_dict(),
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
        try:
            atomic_write_text(out_path, yaml_body)
        except OSError:
            logger.exception("Failed to write skill YAML to %s", out_path)
            return False

        action = "Updated" if is_update else "Wrote"
        logger.info("%s skill manifest %s v%s at %s", action, sid, parsed.version, out_path)
        return True

    @staticmethod
    def _render_context_for_analysis(context: Any | None) -> str:
        if context is None:
            return ""
        parts: list[str] = []
        task = getattr(context, "task", None)
        execution = getattr(context, "execution", None)

        if task and getattr(task, "constraints", []):
            parts.append("Constraints:\n" + "\n".join(f"- {c}" for c in task.constraints))
        if execution:
            bes = getattr(execution, "builder_events_summary", "") or ""
            if isinstance(bes, str) and bes.strip():
                parts.append(
                    "Current run builder_events_summary (truncated):\n"
                    + bes[:_MAX_CONTEXT_SUMMARY_CHARS]
                    + ("\n…" if len(bes) > _MAX_CONTEXT_SUMMARY_CHARS else "")
                )

        if not parts:
            return ""
        return "ContextBundle (extra):\n" + "\n\n".join(parts) + "\n\n"
