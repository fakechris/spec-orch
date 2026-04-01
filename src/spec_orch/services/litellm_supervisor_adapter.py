"""LiteLLM-backed supervisor adapter for mission round review."""

from __future__ import annotations

import json
import logging
import re
import signal
import time
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any, cast

from spec_orch.decision_core.records import build_round_review_decision_record
from spec_orch.decision_core.review_queue import write_round_decision_record
from spec_orch.domain.models import (
    ExecutionPlan,
    RoundAction,
    RoundArtifacts,
    RoundDecision,
    RoundSummary,
)
from spec_orch.runtime_chain.models import (
    ChainPhase,
    RuntimeChainEvent,
    RuntimeChainStatus,
    RuntimeSubjectKind,
)
from spec_orch.runtime_chain.store import append_chain_event, write_chain_status
from spec_orch.services.constitutions import (
    SUPERVISOR_CONSTITUTION,
    build_role_system_prompt,
)
from spec_orch.services.io import atomic_write_json, atomic_write_text
from spec_orch.services.litellm_profile import (
    ResolvedLiteLLMProfile,
    normalize_litellm_model,
    resolve_litellm_api_base,
    resolve_litellm_api_key,
)

logger = logging.getLogger(__name__)

_SUPERVISOR_SYSTEM_PROMPT = build_role_system_prompt(
    role_intro="You are Mission Supervisor for SpecOrch.",
    task_summary="Review one mission round and decide the next orchestration action.",
    constitution=SUPERVISOR_CONSTITUTION,
    response_contract="""\
Return two parts in this order:
1. A short markdown review
2. A JSON object in a ```json fenced block

The JSON must include:
- action: continue | retry | replan_remaining | ask_human | stop
- reason_code
- summary
- confidence
""",
)


class _SupervisorModelTimeout(TimeoutError):
    pass


def _with_signal_timeout(timeout_seconds: float):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if timeout_seconds <= 0:
                return func(*args, **kwargs)
            previous_handler = signal.getsignal(signal.SIGALRM)

            def _handle_timeout(_signum, _frame):
                raise _SupervisorModelTimeout(
                    f"Supervisor model call exceeded {timeout_seconds:.1f}s hard deadline"
                )

            signal.signal(signal.SIGALRM, _handle_timeout)
            signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
            try:
                return func(*args, **kwargs)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0.0)
                signal.signal(signal.SIGALRM, previous_handler)

        return wrapper

    return decorator


def _is_transient_litellm_error(exc: Exception) -> bool:
    if isinstance(exc, _SupervisorModelTimeout):
        return False
    if isinstance(exc, TimeoutError):
        return True
    message = str(exc).lower()
    transient_markers = (
        "overloaded_error",
        "rate limit",
        "rate_limit",
        "429",
        "529",
        "temporarily unavailable",
        "service unavailable",
        "server overloaded",
        "try again later",
    )
    fatal_markers = (
        "invalid x-api-key",
        "authentication_error",
        "unauthorized",
        "forbidden",
        "invalid api key",
        "missing_api_base",
    )
    if any(marker in message for marker in fatal_markers):
        return False
    return any(marker in message for marker in transient_markers)


class LiteLLMSupervisorAdapter:
    ADAPTER_NAME = "litellm"
    VALID_API_TYPES = ("anthropic", "openai")

    def __init__(
        self,
        *,
        repo_root: Path,
        model: str,
        api_type: str = "anthropic",
        api_key: str | None = None,
        api_base: str | None = None,
        temperature: float = 0.1,
        request_timeout_seconds: float = 120.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 1.0,
        model_chain: list[ResolvedLiteLLMProfile] | None = None,
        chat_completion: Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        if api_type not in self.VALID_API_TYPES:
            raise ValueError(f"api_type must be one of {self.VALID_API_TYPES}, got {api_type!r}")
        self.api_type = api_type
        self.model_chain = list(model_chain or [])
        if self.model_chain:
            primary = self.model_chain[0]
            self.model = primary.model
            self.api_key = primary.api_key or None
            self.api_base = primary.api_base or None
        else:
            self.model = normalize_litellm_model(model, api_type=api_type)
            self.api_key = resolve_litellm_api_key(api_key=api_key, api_type=api_type)
            self.api_base = resolve_litellm_api_base(api_base=api_base, api_type=api_type)
        self.temperature = temperature
        self.request_timeout_seconds = request_timeout_seconds
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self._chat_completion = chat_completion

    def review_round(
        self,
        *,
        round_artifacts: RoundArtifacts,
        plan: ExecutionPlan,
        round_history: list[RoundSummary],
        context: Any | None = None,
        chain_root: Path | None = None,
        chain_id: str | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> RoundDecision:
        self._emit_chain_status(
            chain_root=chain_root,
            chain_id=chain_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            subject_id=f"{round_artifacts.mission_id}:round-{round_artifacts.round_id}:supervisor",
            phase=ChainPhase.STARTED,
            status_reason="supervisor_review_started",
        )
        prompt = self._build_prompt(
            round_artifacts=round_artifacts,
            plan=plan,
            round_history=round_history,
            context=context,
        )
        try:
            raw_output = self._call_model(prompt)
            review_text, decision = self._parse_output(raw_output)
            review_text, decision = self._normalize_decision_against_round_contract(
                round_artifacts=round_artifacts,
                review_text=review_text,
                decision=decision,
            )
        except Exception as exc:
            logger.warning(
                "supervisor model call failed; using deterministic fallback",
                extra={
                    "mission_id": round_artifacts.mission_id,
                    "round_id": round_artifacts.round_id,
                },
                exc_info=True,
            )
            review_text, decision = self._fallback_for_model_error(
                exc, round_artifacts=round_artifacts
            )
            self._emit_chain_status(
                chain_root=chain_root,
                chain_id=chain_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                subject_id=(
                    f"{round_artifacts.mission_id}:round-{round_artifacts.round_id}:supervisor"
                ),
                phase=ChainPhase.DEGRADED,
                status_reason="supervisor_review_fallback",
            )

        round_dir = self._round_dir(round_artifacts.mission_id, round_artifacts.round_id)
        review_path = round_dir / "supervisor_review.md"
        decision_path = round_dir / "round_decision.json"
        atomic_write_text(review_path, review_text)
        atomic_write_json(decision_path, decision.to_dict())
        record = build_round_review_decision_record(
            mission_id=round_artifacts.mission_id,
            round_id=round_artifacts.round_id,
            owner="litellm_supervisor_adapter",
            decision=decision,
            context_artifacts=[
                str(review_path.relative_to(self.repo_root)),
                str(decision_path.relative_to(self.repo_root)),
            ],
        )
        write_round_decision_record(round_dir, record)
        try:
            from spec_orch.services.memory.service import get_memory_service

            memory = get_memory_service(repo_root=self.repo_root)
            memory.record_decision_record(
                record=record,
                mission_id=round_artifacts.mission_id,
                round_id=round_artifacts.round_id,
            )
        except Exception:
            logger.warning(
                "decision record memory write failed",
                extra={
                    "mission_id": round_artifacts.mission_id,
                    "round_id": round_artifacts.round_id,
                },
                exc_info=True,
            )
        if not (
            chain_root is not None and chain_id is not None and span_id is not None
        ) or decision.reason_code not in {
            "supervisor_timeout_all_mergeable",
            "supervisor_timeout_round_needs_retry",
            "supervisor_timeout",
        }:
            self._emit_chain_status(
                chain_root=chain_root,
                chain_id=chain_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                subject_id=(
                    f"{round_artifacts.mission_id}:round-{round_artifacts.round_id}:supervisor"
                ),
                phase=ChainPhase.COMPLETED,
                status_reason="supervisor_review_completed",
                artifact_refs={
                    "review_path": str(review_path),
                    "decision_path": str(decision_path),
                },
            )
        return decision

    def _emit_chain_status(
        self,
        *,
        chain_root: Path | None,
        chain_id: str | None,
        span_id: str | None,
        parent_span_id: str | None,
        subject_id: str,
        phase: ChainPhase,
        status_reason: str,
        artifact_refs: dict[str, str] | None = None,
    ) -> None:
        if chain_root is None or chain_id is None or span_id is None:
            return
        updated_at = datetime.now(UTC).isoformat()
        append_chain_event(
            chain_root,
            RuntimeChainEvent(
                chain_id=chain_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                subject_kind=RuntimeSubjectKind.SUPERVISOR,
                subject_id=subject_id,
                phase=phase,
                status_reason=status_reason,
                artifact_refs=artifact_refs or {},
                updated_at=updated_at,
            ),
        )
        write_chain_status(
            chain_root,
            RuntimeChainStatus(
                chain_id=chain_id,
                active_span_id=span_id,
                subject_kind=RuntimeSubjectKind.SUPERVISOR,
                subject_id=subject_id,
                phase=phase,
                status_reason=status_reason,
                artifact_refs=artifact_refs or {},
                updated_at=updated_at,
            ),
        )

    def _call_model(self, prompt: str) -> str:
        @_with_signal_timeout(self._hard_deadline_seconds())
        def _bounded_call() -> str:
            return self._call_model_unbounded(prompt)

        return cast(str, _bounded_call())

    def _hard_deadline_seconds(self) -> float:
        # Give the model call a narrow grace window beyond the nominal request timeout,
        # but keep the deadline meaningfully bounded for short test and recovery paths.
        grace_seconds = min(5.0, max(0.01, self.request_timeout_seconds * 0.1))
        return max(0.01, self.request_timeout_seconds + grace_seconds)

    def _call_model_unbounded(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": _SUPERVISOR_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        profiles = self.model_chain or [self._default_profile()]
        last_exc: Exception | None = None
        for profile in profiles:
            kwargs = {
                "model": profile.model,
                "messages": messages,
                "temperature": self.temperature,
                "timeout": self.request_timeout_seconds,
                "api_key": profile.api_key or None,
                "api_base": profile.api_base or None,
            }
            attempt = 0
            while True:
                try:
                    if self._chat_completion is not None:
                        response = self._chat_completion(**kwargs)
                        return self._extract_text(response)

                    try:
                        import litellm
                    except ImportError as exc:
                        raise ImportError(
                            "litellm is required for LiteLLMSupervisorAdapter. "
                            "Install with: pip install spec-orch[planner]"
                        ) from exc

                    response = litellm.completion(**kwargs)
                    return self._extract_text(response)
                except Exception as exc:
                    last_exc = exc
                    if attempt < self.max_retries and _is_transient_litellm_error(exc):
                        attempt += 1
                        if self.retry_backoff_seconds > 0:
                            time.sleep(self.retry_backoff_seconds * attempt)
                        continue
                    if not _is_transient_litellm_error(exc):
                        raise
                    break
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No supervisor model profile configured")

    def _default_profile(self) -> ResolvedLiteLLMProfile:
        return ResolvedLiteLLMProfile(
            model=self.model,
            api_type=self.api_type,
            api_key=self.api_key or "",
            api_base=self.api_base or "",
            api_key_env="",
            api_base_env="",
            slot="primary",
        )

    def _fallback_for_model_error(
        self,
        exc: Exception,
        *,
        round_artifacts: RoundArtifacts,
    ) -> tuple[str, RoundDecision]:
        message = str(exc).strip() or exc.__class__.__name__
        builder_reports = [
            report for report in round_artifacts.builder_reports if isinstance(report, dict)
        ]
        gate_verdicts = [
            verdict for verdict in round_artifacts.gate_verdicts if isinstance(verdict, dict)
        ]
        all_build_succeeded = bool(builder_reports) and all(
            bool(report.get("succeeded")) for report in builder_reports
        )
        all_mergeable = bool(gate_verdicts) and all(
            bool(verdict.get("mergeable")) for verdict in gate_verdicts
        )
        any_failed = any(not bool(report.get("succeeded")) for report in builder_reports) or any(
            not bool(verdict.get("mergeable")) for verdict in gate_verdicts
        )

        if (
            all_build_succeeded
            and all_mergeable
            and len(builder_reports) == len(gate_verdicts)
            and len(builder_reports) > 0
        ):
            decision = RoundDecision(
                action=RoundAction.CONTINUE,
                reason_code="supervisor_timeout_all_mergeable",
                summary=(
                    "Supervisor model call timed out; using deterministic continue fallback "
                    "because all packets succeeded and all gates are mergeable."
                ),
                confidence=0.2,
            )
        elif any_failed:
            decision = RoundDecision(
                action=RoundAction.RETRY,
                reason_code="supervisor_timeout_round_needs_retry",
                summary=(
                    "Supervisor model call timed out; using deterministic retry fallback "
                    "because at least one packet failed or is not mergeable."
                ),
                confidence=0.2,
            )
        else:
            decision = RoundDecision(
                action=RoundAction.ASK_HUMAN,
                reason_code="supervisor_timeout",
                summary=(
                    "Supervisor model call timed out; unable to derive a safe automatic "
                    "decision from round artifacts."
                ),
                confidence=0.0,
                blocking_questions=["Review the round artifacts and choose the next action."],
            )

        review = (
            "## Round Review Fallback\n\n"
            f"Supervisor model call failed: `{message}`.\n\n"
            f"Fallback decision: `{decision.action.value}` (`{decision.reason_code}`)."
        )
        return review, decision

    def _normalize_decision_against_round_contract(
        self,
        *,
        round_artifacts: RoundArtifacts,
        review_text: str,
        decision: RoundDecision,
    ) -> tuple[str, RoundDecision]:
        if decision.action is not RoundAction.ASK_HUMAN:
            return review_text, decision
        if decision.reason_code != "verification_gap_lint_typecheck_missing":
            return review_text, decision
        if self._round_contract_mentions_lint_or_typecheck(
            round_artifacts.mission_id, round_artifacts.round_id
        ):
            return review_text, decision
        if not self._all_builder_and_gate_reports_clear(round_artifacts):
            return review_text, decision

        normalized = RoundDecision(
            action=RoundAction.CONTINUE,
            reason_code="verification_gap_not_in_round_contract",
            summary=(
                "Supervisor flagged a lint/typecheck verification gap, but the round "
                "contract does not require those checks and all recorded builder/gate "
                "artifacts are clear. Continuing deterministically."
            ),
            confidence=0.25,
        )
        if review_text:
            review_text = (
                f"{review_text}\n\n"
                "### Deterministic Normalization\n\n"
                "- The round contract does not explicitly require lint or typecheck.\n"
                "- All recorded builder reports succeeded.\n"
                "- All recorded gate verdicts are mergeable.\n"
                "- The supervisor decision was normalized to avoid a false human block."
            )
        return review_text, normalized

    def _all_builder_and_gate_reports_clear(self, round_artifacts: RoundArtifacts) -> bool:
        builder_reports = [
            report for report in round_artifacts.builder_reports if isinstance(report, dict)
        ]
        gate_verdicts = [
            verdict for verdict in round_artifacts.gate_verdicts if isinstance(verdict, dict)
        ]
        return (
            bool(builder_reports)
            and bool(gate_verdicts)
            and all(bool(report.get("succeeded")) for report in builder_reports)
            and all(bool(verdict.get("mergeable")) for verdict in gate_verdicts)
        )

    def _round_contract_mentions_lint_or_typecheck(self, mission_id: str, round_id: int) -> bool:
        task_spec_path = self._round_dir(mission_id, round_id) / "task.spec.md"
        if not task_spec_path.exists():
            return False
        try:
            task_spec = task_spec_path.read_text(encoding="utf-8").lower()
        except OSError:
            return False
        return "lint" in task_spec or "typecheck" in task_spec

    def _build_prompt(
        self,
        *,
        round_artifacts: RoundArtifacts,
        plan: ExecutionPlan,
        round_history: list[RoundSummary],
        context: Any | None,
    ) -> str:
        payload = {
            "plan_id": plan.plan_id,
            "mission_id": plan.mission_id,
            "plan_overview": self._serialize_plan(plan),
            "round_artifacts": {
                "round_id": round_artifacts.round_id,
                "mission_id": round_artifacts.mission_id,
                "builder_reports": round_artifacts.builder_reports,
                "verification_outputs": round_artifacts.verification_outputs,
                "gate_verdicts": round_artifacts.gate_verdicts,
                "manifest_paths": round_artifacts.manifest_paths,
                "diff_summary": round_artifacts.diff_summary,
                "worker_session_ids": round_artifacts.worker_session_ids,
                "visual_evaluation": (
                    round_artifacts.visual_evaluation.to_dict()
                    if round_artifacts.visual_evaluation is not None
                    else None
                ),
            },
            "round_history": [summary.to_dict() for summary in round_history],
            "context": self._serialize_value(context),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _parse_output(self, raw_output: str) -> tuple[str, RoundDecision]:
        try:
            review_text, json_blob = self._split_review_and_json(raw_output)
            return review_text, RoundDecision.from_dict(json.loads(json_blob))
        except Exception:
            fallback = RoundDecision(
                action=RoundAction.ASK_HUMAN,
                reason_code="parse_error",
                summary="Supervisor output could not be parsed.",
                confidence=0.0,
                blocking_questions=["Review the supervisor output and decide the next action."],
            )
            return raw_output.strip() or "Supervisor output parsing failed.", fallback

    @staticmethod
    def _split_review_and_json(raw_output: str) -> tuple[str, str]:
        match = re.search(r"```json\s*(\{.*\})\s*```", raw_output, flags=re.DOTALL)
        if match:
            json_blob = match.group(1)
            review = raw_output[: match.start()].strip()
            return review, json_blob
        stripped = raw_output.strip()
        return "", stripped

    @staticmethod
    def _extract_text(response: Any) -> str:
        if isinstance(response, str):
            return response
        choices = getattr(response, "choices", None)
        if choices:
            message = getattr(choices[0], "message", None)
            if message is not None:
                content = getattr(message, "content", "")
                if isinstance(content, str):
                    return content
        raise ValueError("Unsupported chat completion response format")

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if value is None:
            return None
        if is_dataclass(value) and not isinstance(value, type):
            return asdict(value)
        if isinstance(value, dict):
            return {
                str(key): LiteLLMSupervisorAdapter._serialize_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [LiteLLMSupervisorAdapter._serialize_value(item) for item in value]
        if isinstance(value, tuple):
            return [LiteLLMSupervisorAdapter._serialize_value(item) for item in value]
        if isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    @staticmethod
    def _serialize_plan(plan: ExecutionPlan) -> list[dict[str, Any]]:
        return [
            {
                "wave_number": wave.wave_number,
                "description": wave.description,
                "packet_ids": [packet.packet_id for packet in wave.work_packets],
                "packet_titles": [packet.title for packet in wave.work_packets],
            }
            for wave in plan.waves
        ]

    def _round_dir(self, mission_id: str, round_id: int) -> Path:
        return self.repo_root / "docs" / "specs" / mission_id / "rounds" / f"round-{round_id:02d}"
