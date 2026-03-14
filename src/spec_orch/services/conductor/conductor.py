"""Conductor Agent — progressive formalization layer.

Sits between the user and the structured pipeline.  In *explore* mode
it lets users chat freely; when it detects actionable intent it proposes
formalizing the conversation into an Issue/Epic (*crystallize*); on
approval it hands off to the existing lifecycle pipeline (*execute*).

The Conductor never executes code itself — it only manages the
conversation-to-structure bridge.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from spec_orch.domain.models import ConversationMessage, ConversationThread
from spec_orch.services.conductor.intent_classifier import classify_intent
from spec_orch.services.conductor.types import (
    ACTIONABLE_INTENTS,
    ConductorState,
    ConversationMode,
    FormalizationProposal,
    IntentCategory,
    IntentSignal,
)

logger = logging.getLogger(__name__)

_STATE_DIR = ".spec_orch_conductor"
_CRYSTALLIZE_THRESHOLD = 3
APPROVE_RE_PATTERN = r"@?spec[_-]?orch\s+approve"
_DRIFT_JACCARD_THRESHOLD = 0.15


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
    ) -> None:
        self._repo_root = Path(repo_root)
        self._planner = planner
        self._state_dir = self._repo_root / _STATE_DIR
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._states: dict[str, ConductorState] = {}

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
        )
        state.intent_history.append(signal)

        # Detect drift
        if self._detect_drift(state, signal):
            signal = IntentSignal(
                category=IntentCategory.DRIFT,
                confidence=signal.confidence,
                summary=signal.summary,
                reasoning="Topic drift detected",
            )
            state.intent_history[-1] = signal

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
