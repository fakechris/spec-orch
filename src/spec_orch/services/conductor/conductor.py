"""Conductor Agent — progressive formalization layer.

Sits between the user and the structured pipeline.  In *explore* mode
it lets users chat freely; when it detects actionable intent it proposes
formalizing the conversation into an Issue/Epic (*crystallize*); on
approval it hands off to the existing lifecycle pipeline (*execute*).

The Conductor never executes code itself — it only manages the
conversation-to-structure bridge.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from spec_orch.domain.models import ConversationMessage, ConversationThread, Issue, IssueContext
from spec_orch.services.conductor.intent_classifier import classify_intent
from spec_orch.services.conductor.types import (
    ACTIONABLE_INTENTS,
    ConductorState,
    ConversationMode,
    DMAStage,
    ForkResult,
    FormalizationProposal,
    IntentCategory,
    IntentSignal,
    InterceptAction,
    InterceptResult,
)
from spec_orch.services.context_assembler import ContextAssembler
from spec_orch.services.node_context_registry import get_node_context_spec

logger = logging.getLogger(__name__)

_STATE_DIR = ".spec_orch_conductor"
_CRYSTALLIZE_THRESHOLD = 3
APPROVE_RE_PATTERN = r"@?spec[_-]?orch\s+approve"
_DRIFT_JACCARD_THRESHOLD = 0.15
_FORK_DEBOUNCE_SECONDS = 60
_FORK_EXCERPT_MESSAGES = 5
_FORK_EXCERPT_CHARS = 100
_INTERCEPT_DEBOUNCE_SECONDS = 60


class Conductor:
    """Progressive formalization engine for conversations.

    Wraps around the existing ``ConversationService`` and adds:

    * Per-message intent classification
    * Automatic crystallization proposals when actionable intent
      accumulates
    * ``@spec-orch approve`` to formalize a proposal into an Issue
    * Memory integration for recording decisions
    """

    def __init__(
        self,
        *,
        repo_root: Path,
        planner: Any | None = None,
        linear_client: Any | None = None,
        event_bus: Any | None = None,
        fork_team_key: str = "",
    ) -> None:
        self._repo_root = Path(repo_root)
        self._planner = planner
        self._linear_client = linear_client
        self._event_bus = event_bus
        self._fork_team_key = (
            fork_team_key
            or os.environ.get("SPEC_ORCH_FORK_TEAM", "")
            or os.environ.get("SPEC_ORCH_LINEAR_TEAM", "SON")
        )
        self._fork_enabled = os.environ.get("SPEC_ORCH_FORK_ENABLED", "true").lower() != "false"
        self._intercept_enabled = (
            os.environ.get("SPEC_ORCH_INTERCEPT_ENABLED", "true").lower() != "false"
        )
        raw_stages = os.environ.get("SPEC_ORCH_INTERCEPT_STAGES", "")
        self._intercept_stages: set[str] = (
            {s.strip() for s in raw_stages.split(",") if s.strip()} if raw_stages else set()
        )
        self._state_dir = self._repo_root / _STATE_DIR
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._states: dict[str, ConductorState] = {}
        self._fork_timestamps: dict[str, float] = {}
        self._intercept_cache: dict[str, float] = {}
        self._context_assembler = ContextAssembler()

    def intercept(
        self,
        stage: DMAStage,
        user_input: str,
        context: dict[str, Any] | None = None,
    ) -> InterceptResult:
        """Intercept a DMA lifecycle stage with user input.

        Returns an InterceptResult with an action that the caller (e.g.
        RunController) should honour.  When intercept is disabled, the
        stage is filtered out, or the input was already processed within
        the debounce window, the method returns ``action="continue"``
        without invoking the classifier.
        """
        _noop = InterceptResult(
            intent_signal=IntentSignal(
                category=IntentCategory.EXPLORATION,
                confidence=0.0,
            ),
            action="continue",
        )

        if not self._intercept_enabled:
            return _noop

        if self._intercept_stages and stage.value not in self._intercept_stages:
            return _noop

        if not user_input or not user_input.strip():
            return _noop

        input_hash = self._signal_hash(
            IntentSignal(
                category=IntentCategory.EXPLORATION,
                confidence=0.0,
                summary=user_input,
            ),
        )
        now = time.time()
        last_ts = self._intercept_cache.get(input_hash, 0.0)
        if now - last_ts < _INTERCEPT_DEBOUNCE_SECONDS:
            return _noop
        self._intercept_cache[input_hash] = now

        try:
            assembled_context = self._assemble_intent_context(context or {})
            signal = classify_intent(
                user_input,
                conversation_history=(context or {}).get("history", []),
                planner=self._planner,
                context=assembled_context,
            )
        except Exception:
            logger.warning("intercept: classify_intent failed, degrading to continue")
            return _noop

        action = self._intent_to_action(signal, stage)
        metadata: dict[str, Any] = {"stage": stage.value}

        if action == "fork":
            thread_id = (context or {}).get("thread_id", "intercept")
            state = self._get_or_create_state(thread_id)
            fork_result = self._maybe_fork(state, signal, None)
            if fork_result.forked:
                metadata["fork_result"] = {
                    "forked": fork_result.forked,
                    "linear_issue_id": fork_result.linear_issue_id,
                    "title": fork_result.title,
                    "error": fork_result.error,
                }

        return InterceptResult(
            intent_signal=signal,
            action=action,
            metadata=metadata,
        )

    @staticmethod
    def _intent_to_action(
        signal: IntentSignal,
        stage: DMAStage,
    ) -> InterceptAction:
        """Map an IntentSignal to an intercept action."""
        if signal.category == IntentCategory.DRIFT:
            if stage in {DMAStage.BUILD, DMAStage.VERIFY}:
                return "pause"
            return "fork"
        if signal.is_actionable():
            if stage in {DMAStage.GATE, DMAStage.REVIEW}:
                return "fork"
            return "redirect"
        return "continue"

    def process_message(
        self,
        msg: ConversationMessage,
        thread: ConversationThread,
    ) -> ConductorResponse:
        """Analyse a message and decide how the Conductor should respond.

        Returns a ``ConductorResponse`` telling the caller what to do:
        pass-through to brainstorm, present a proposal, or execute.
        """
        state = self._get_or_create_state(msg.thread_id)

        if re.search(APPROVE_RE_PATTERN, msg.content, re.IGNORECASE):
            return self._handle_approve(state, thread)

        # Classify intent
        history = self._build_history(thread)
        signal = classify_intent(
            msg.content,
            conversation_history=history,
            planner=self._planner,
            context=self._assemble_intent_context(msg.metadata),
        )
        state.intent_history.append(signal)

        # Detect drift
        is_drift = self._detect_drift(state, signal)
        if is_drift:
            signal = IntentSignal(
                category=IntentCategory.DRIFT,
                confidence=signal.confidence,
                summary=signal.summary,
                reasoning="Topic drift detected",
            )
            state.intent_history[-1] = signal

        # Fork on drift (R1.1)
        if is_drift and signal.summary:
            self._maybe_fork(state, signal, thread)

        # Update topic anchor if we have a clear signal
        if signal.summary and signal.confidence >= 0.5:
            state.topic_anchors = state.topic_anchors[-4:] + [signal.summary]

        # Decide whether to propose formalization
        if state.mode == ConversationMode.EXPLORE:
            proposal = self._maybe_propose(state, signal)
            if proposal is not None:
                state.pending_proposal = proposal
                state.mode = ConversationMode.CRYSTALLIZE
                self._persist_state(state)
                return ConductorResponse(
                    action="propose",
                    proposal=proposal,
                    intent=signal,
                    conductor_message=proposal.format_for_user(),
                )

        # Fork on new actionable intent during CRYSTALLIZE/EXECUTE (R1.2)
        if (
            not is_drift
            and state.mode in {ConversationMode.CRYSTALLIZE, ConversationMode.EXECUTE}
            and signal.is_actionable()
        ):
            self._maybe_fork(state, signal, thread)

        # Record to memory
        self._record_to_memory(state, signal, msg)
        self._persist_state(state)

        return ConductorResponse(
            action="passthrough",
            intent=signal,
        )

    def get_state(self, thread_id: str) -> ConductorState | None:
        if thread_id in self._states:
            return self._states[thread_id]
        path = self._state_dir / f"{thread_id}.json"
        if path.exists():
            state = self._load_state(path)
            self._states[thread_id] = state
            return state
        return None

    # -- internal logic ------------------------------------------------------

    def _handle_approve(
        self,
        state: ConductorState,
        thread: ConversationThread,
    ) -> ConductorResponse:
        """User approved a formalization proposal."""
        proposal = state.pending_proposal
        if proposal is None:
            return ConductorResponse(
                action="passthrough",
                conductor_message="Nothing to approve — no pending proposal.",
            )

        state.mode = ConversationMode.EXECUTE
        state.pending_proposal = None

        issue_desc = self._create_formalized_work(state, proposal, thread)
        self._persist_state(state)

        return ConductorResponse(
            action="formalized",
            proposal=proposal,
            conductor_message=issue_desc,
        )

    def _create_formalized_work(
        self,
        state: ConductorState,
        proposal: FormalizationProposal,
        thread: ConversationThread,
    ) -> str:
        """Create an Issue/Epic from the approved proposal.

        Uses MissionService for epic-level work or returns a structured
        description for direct issue creation.
        """
        if proposal.proposal_type == "epic":
            try:
                from spec_orch.services.mission_service import MissionService

                svc = MissionService(self._repo_root)
                mission = svc.create_mission(proposal.title)
                state.formalized_issues.append(mission.mission_id)
                spec_path = self._repo_root / mission.spec_path
                existing = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
                if existing.strip():
                    spec_path.write_text(
                        existing.rstrip() + f"\n\n## Description\n\n{proposal.description}\n",
                        encoding="utf-8",
                    )
                else:
                    spec_path.write_text(
                        f"# {proposal.title}\n\n{proposal.description}\n",
                        encoding="utf-8",
                    )
                return (
                    f"Epic created as Mission **{mission.mission_id}**.\n"
                    f"Spec: `{mission.spec_path}`\n"
                    f"Run `spec-orch mission approve {mission.mission_id}` to start planning."
                )
            except (ImportError, OSError, ValueError) as exc:
                logger.warning("Failed to create mission, falling back: %s", exc)

        issue_id = f"conductor-{uuid.uuid4().hex[:8]}"
        state.formalized_issues.append(issue_id)
        return (
            f"Formalized as **{proposal.proposal_type}**: {proposal.title}\n\n"
            f"{proposal.description}\n\n"
            f"Create this in Linear or run the lifecycle pipeline to proceed."
        )

    def _maybe_propose(
        self,
        state: ConductorState,
        current: IntentSignal,
    ) -> FormalizationProposal | None:
        """Decide whether to propose formalizing the conversation."""
        if not current.is_actionable():
            return None

        recent = state.intent_history[-_CRYSTALLIZE_THRESHOLD:]
        actionable_count = sum(1 for s in recent if s.category in ACTIONABLE_INTENTS)

        # Need either high confidence on a single signal or accumulation
        if current.confidence < 0.7 and actionable_count < 2:
            return None

        return self._build_proposal(state, current)

    def _build_proposal(
        self,
        state: ConductorState,
        trigger: IntentSignal,
    ) -> FormalizationProposal:
        """Construct a formalization proposal from accumulated signals."""
        actionable = [s for s in state.intent_history if s.category in ACTIONABLE_INTENTS]
        summaries = [s.summary for s in actionable if s.summary]
        description = "\n".join(f"- {s}" for s in summaries) if summaries else trigger.summary

        if trigger.category == IntentCategory.FEATURE and len(actionable) >= 3:
            proposal_type = "epic"
        elif trigger.category == IntentCategory.QUICK_FIX:
            proposal_type = "quick_fix"
        else:
            proposal_type = "issue"

        title = trigger.suggested_title or trigger.summary[:60] or "Untitled"

        return FormalizationProposal(
            proposal_type=proposal_type,
            title=title,
            description=description,
            intent_category=trigger.category,
            confidence=trigger.confidence,
        )

    # -- fork logic -----------------------------------------------------------

    def _maybe_fork(
        self,
        state: ConductorState,
        signal: IntentSignal,
        thread: ConversationThread | None,
    ) -> ForkResult:
        """Attempt to fork a new Issue for a divergent or new actionable intent.

        Side-effect only — does not modify state.mode or pending_proposal (R4.1).
        """
        if not self._fork_enabled:
            return ForkResult(forked=False)

        signal_hash = self._signal_hash(signal)

        # Dedup: same intent within debounce window (S7.1)
        if signal_hash in state.forked_intent_ids:
            return ForkResult(forked=False)
        now = time.monotonic()
        last_fork_time = self._fork_timestamps.get(state.thread_id, 0.0)
        if now - last_fork_time < _FORK_DEBOUNCE_SECONDS and state.forked_intent_ids:
            return ForkResult(forked=False)

        title = (
            signal.suggested_title
            or (signal.summary[:60] if signal.summary else "")
            or "Forked from conversation"
        )
        description = self._build_fork_description(state, signal, thread)

        issue_id = ""
        error = ""

        # Try Linear creation (R6.3: skip if no client)
        if self._linear_client is not None:
            issue_id, error = self._create_linear_fork_issue(title, description)

        if not issue_id:
            self._write_local_fork_fallback(state, title, description, signal)

        state.forked_intent_ids.append(signal_hash)
        self._fork_timestamps[state.thread_id] = now

        result = ForkResult(forked=True, linear_issue_id=issue_id, title=title, error=error)

        self._emit_fork_event(state, signal, result)
        self._record_fork_to_memory(state, signal, result)

        return result

    @staticmethod
    def _signal_hash(signal: IntentSignal) -> str:
        raw = f"{signal.category.value}:{signal.summary}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _assemble_intent_context(self, metadata: dict[str, Any] | None) -> Any | None:
        """Best-effort ContextAssembler integration for intent classification."""
        if not metadata:
            return None
        issue_id = str(metadata.get("issue_id", "")).strip()
        if not issue_id:
            return None
        workspace_path = metadata.get("workspace")
        workspace = Path(workspace_path) if isinstance(workspace_path, str) else self._repo_root
        issue = Issue(
            issue_id=issue_id,
            title=str(metadata.get("issue_title", issue_id)),
            summary=str(metadata.get("issue_summary", "")),
            context=IssueContext(
                constraints=list(metadata.get("constraints", []))
                if isinstance(metadata.get("constraints"), list)
                else []
            ),
            acceptance_criteria=list(metadata.get("acceptance_criteria", []))
            if isinstance(metadata.get("acceptance_criteria"), list)
            else [],
        )
        try:
            return self._context_assembler.assemble(
                get_node_context_spec("intent_classifier"),
                issue,
                workspace,
                repo_root=self._repo_root,
            )
        except Exception:
            logger.debug("Failed to assemble intent context", exc_info=True)
            return None

    def _build_fork_description(
        self,
        state: ConductorState,
        signal: IntentSignal,
        thread: ConversationThread | None,
    ) -> str:
        lines = [
            f"Source: thread:{state.thread_id}",
            "",
            f"**Original intent**: {signal.category.value} — {signal.summary}",
            "",
            "**Conversation excerpt**:",
        ]
        if thread is not None:
            recent = thread.messages[-_FORK_EXCERPT_MESSAGES:]
            for m in recent:
                truncated = m.content[:_FORK_EXCERPT_CHARS]
                if len(m.content) > _FORK_EXCERPT_CHARS:
                    truncated += "…"
                lines.append(f"- [{m.sender}] {truncated}")
        else:
            lines.append("- (no conversation thread available)")
        return "\n".join(lines)

    def _create_linear_fork_issue(self, title: str, description: str) -> tuple[str, str]:
        """Call LinearClient.create_issue with retry on 429. Returns (issue_id, error)."""
        assert self._linear_client is not None  # caller guards
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                issue = self._linear_client.create_issue(
                    team_key=self._fork_team_key,
                    title=title,
                    description=description,
                )
                return issue.get("identifier", ""), ""
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                exc_str = str(exc).lower()
                is_rate_limit = (
                    status == 429
                    or "429" in exc_str
                    or "rate limit" in exc_str
                    or "too many requests" in exc_str
                )
                if is_rate_limit and attempt < max_retries:
                    time.sleep(2**attempt)
                    continue
                logger.warning("Fork Linear issue creation failed: %s", exc)
                return "", str(exc)
        return "", "max retries exceeded"

    def _write_local_fork_fallback(
        self,
        state: ConductorState,
        title: str,
        description: str,
        signal: IntentSignal,
    ) -> None:
        """Write fork to local JSONL as a sync queue (R6.2 fallback)."""
        forks_dir = self._state_dir
        forks_dir.mkdir(parents=True, exist_ok=True)
        forks_path = forks_dir / "forks.jsonl"
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "thread_id": state.thread_id,
            "title": title,
            "description": description,
            "intent_category": signal.category.value,
            "intent_summary": signal.summary,
        }
        with forks_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _emit_fork_event(
        self,
        state: ConductorState,
        signal: IntentSignal,
        result: ForkResult,
    ) -> None:
        if self._event_bus is None:
            return
        try:
            from spec_orch.services.event_bus import Event, EventTopic

            self._event_bus.publish(
                Event(
                    topic=EventTopic.CONDUCTOR,
                    payload={
                        "action": "fork",
                        "thread_id": state.thread_id,
                        "linear_issue_id": result.linear_issue_id,
                        "intent_category": signal.category.value,
                        "intent_summary": signal.summary,
                        "title": result.title,
                        "error": result.error,
                    },
                    source="conductor.fork",
                )
            )
        except Exception:
            logger.debug("Failed to emit fork event", exc_info=True)

    def _record_fork_to_memory(
        self,
        state: ConductorState,
        signal: IntentSignal,
        result: ForkResult,
    ) -> None:
        try:
            from spec_orch.services.memory.service import get_memory_service
            from spec_orch.services.memory.types import MemoryEntry, MemoryLayer

            svc = get_memory_service(repo_root=self._repo_root)
            tags = [
                "conductor-fork",
                f"thread:{state.thread_id}",
            ]
            if result.linear_issue_id:
                tags.append(f"linear:{result.linear_issue_id}")

            svc.store(
                MemoryEntry(
                    key=f"conductor-fork-{state.thread_id}-{self._signal_hash(signal)}",
                    content=f"Forked: {result.title}",
                    layer=MemoryLayer.EPISODIC,
                    tags=tags,
                    metadata={
                        "action": "fork",
                        "intent_category": signal.category.value,
                        "intent_summary": signal.summary,
                        "linear_issue_id": result.linear_issue_id,
                        "thread_id": state.thread_id,
                    },
                )
            )
        except (ImportError, Exception):
            logger.debug("Failed to record fork to memory", exc_info=True)

    # -- drift detection -----------------------------------------------------

    def _detect_drift(self, state: ConductorState, signal: IntentSignal) -> bool:
        """Simple drift detection based on topic anchor divergence."""
        if len(state.topic_anchors) < 2:
            return False
        if not signal.summary:
            return False

        recent_anchor = state.topic_anchors[-1]
        current = signal.summary.lower()
        anchor = recent_anchor.lower()

        shared_words = set(current.split()) & set(anchor.split())
        all_words = set(current.split()) | set(anchor.split())
        if not all_words:
            return False
        jaccard = len(shared_words) / len(all_words)
        return jaccard < _DRIFT_JACCARD_THRESHOLD

    def _record_to_memory(
        self,
        state: ConductorState,
        signal: IntentSignal,
        msg: ConversationMessage,
    ) -> None:
        """Record significant conversation turns to Memory."""
        if signal.confidence < 0.5:
            return
        try:
            from spec_orch.services.memory.service import get_memory_service
            from spec_orch.services.memory.types import MemoryEntry, MemoryLayer

            svc = get_memory_service(repo_root=self._repo_root)
            svc.store(
                MemoryEntry(
                    key=f"conductor-{state.thread_id}-{msg.message_id}",
                    content=msg.content[:500],
                    layer=MemoryLayer.WORKING,
                    tags=[
                        "conductor",
                        f"intent:{signal.category.value}",
                        f"thread:{state.thread_id}",
                    ],
                    metadata={
                        "intent_category": signal.category.value,
                        "confidence": signal.confidence,
                        "summary": signal.summary,
                        "thread_id": state.thread_id,
                        "channel": msg.channel,
                    },
                )
            )
        except ImportError:
            pass

    @staticmethod
    def _build_history(thread: ConversationThread) -> list[dict[str, str]]:
        history: list[dict[str, str]] = []
        for m in thread.messages:
            role = "assistant" if m.sender == "bot" else "user"
            history.append({"role": role, "content": m.content})
        return history

    # -- persistence ---------------------------------------------------------

    def _get_or_create_state(self, thread_id: str) -> ConductorState:
        if thread_id in self._states:
            return self._states[thread_id]
        path = self._state_dir / f"{thread_id}.json"
        state = self._load_state(path) if path.exists() else ConductorState(thread_id=thread_id)
        self._states[thread_id] = state
        return state

    def _persist_state(self, state: ConductorState) -> None:
        state.updated_at = datetime.now(UTC).isoformat()
        path = self._state_dir / f"{state.thread_id}.json"
        path.write_text(
            json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _load_state(self, path: Path) -> ConductorState:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return ConductorState.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("Corrupted conductor state %s: %s", path, exc)
            return ConductorState(thread_id=path.stem)


ConductorAction = Literal["passthrough", "propose", "formalized"]


class ConductorResponse:
    """What the Conductor tells the caller to do after processing a message."""

    def __init__(
        self,
        *,
        action: ConductorAction,
        intent: IntentSignal | None = None,
        proposal: FormalizationProposal | None = None,
        conductor_message: str | None = None,
    ) -> None:
        self.action = action
        self.intent = intent
        self.proposal = proposal
        self.conductor_message = conductor_message
