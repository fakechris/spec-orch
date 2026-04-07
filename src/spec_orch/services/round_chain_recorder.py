"""Runtime chain event recording for supervised rounds."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from spec_orch.runtime_chain.models import (
    ChainPhase,
    RuntimeChainEvent,
    RuntimeChainStatus,
    RuntimeSubjectKind,
)
from spec_orch.runtime_chain.store import append_chain_event, write_chain_status


class RoundChainRecorder:
    """Records runtime chain events for a single supervised mission run.

    Constructed once per ``run_supervised()`` invocation and threaded through
    the main loop so individual call-sites stay concise.
    """

    def __init__(
        self,
        *,
        chain_root: Path,
        chain_id: str,
        mission_span_id: str,
    ) -> None:
        self.chain_root = chain_root
        self.chain_id = chain_id
        self.mission_span_id = mission_span_id

    # -- mission-level events ------------------------------------------------

    def record_mission_started(self, *, mission_id: str, mission_root: str) -> None:
        updated_at = datetime.now(UTC).isoformat()
        append_chain_event(
            self.chain_root,
            RuntimeChainEvent(
                chain_id=self.chain_id,
                span_id=self.mission_span_id,
                parent_span_id=None,
                subject_kind=RuntimeSubjectKind.MISSION,
                subject_id=mission_id,
                phase=ChainPhase.STARTED,
                status_reason="mission_supervision_started",
                artifact_refs={"mission_root": mission_root},
                updated_at=updated_at,
            ),
        )
        write_chain_status(
            self.chain_root,
            RuntimeChainStatus(
                chain_id=self.chain_id,
                active_span_id=self.mission_span_id,
                subject_kind=RuntimeSubjectKind.MISSION,
                subject_id=mission_id,
                phase=ChainPhase.STARTED,
                status_reason="mission_supervision_started",
                artifact_refs={"mission_root": mission_root},
                updated_at=updated_at,
            ),
        )

    # -- round-level events --------------------------------------------------

    def round_span_id(self, round_id: int) -> str:
        return f"{self.chain_id}:round:{round_id:02d}"

    def record_round_started(self, *, round_id: int, round_dir: Path) -> None:
        append_chain_event(
            self.chain_root,
            RuntimeChainEvent(
                chain_id=self.chain_id,
                span_id=self.round_span_id(round_id),
                parent_span_id=self.mission_span_id,
                subject_kind=RuntimeSubjectKind.ROUND,
                subject_id=f"round-{round_id:02d}",
                phase=ChainPhase.STARTED,
                status_reason="round_started",
                artifact_refs={"round_dir": str(round_dir)},
                updated_at=datetime.now(UTC).isoformat(),
            ),
        )

    def record_round_completed(self, *, round_id: int, round_dir: Path) -> None:
        append_chain_event(
            self.chain_root,
            RuntimeChainEvent(
                chain_id=self.chain_id,
                span_id=self.round_span_id(round_id),
                parent_span_id=self.mission_span_id,
                subject_kind=RuntimeSubjectKind.ROUND,
                subject_id=f"round-{round_id:02d}",
                phase=ChainPhase.COMPLETED,
                status_reason="round_completed",
                artifact_refs={"round_dir": str(round_dir)},
                updated_at=datetime.now(UTC).isoformat(),
            ),
        )

    def record_round_failed(self, *, round_id: int, round_dir: Path) -> None:
        append_chain_event(
            self.chain_root,
            RuntimeChainEvent(
                chain_id=self.chain_id,
                span_id=self.round_span_id(round_id),
                parent_span_id=self.mission_span_id,
                subject_kind=RuntimeSubjectKind.ROUND,
                subject_id=f"round-{round_id:02d}",
                phase=ChainPhase.FAILED,
                status_reason="round_failed",
                artifact_refs={"round_dir": str(round_dir)},
                updated_at=datetime.now(UTC).isoformat(),
            ),
        )
