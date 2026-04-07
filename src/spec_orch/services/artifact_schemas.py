"""Pydantic schemas for JSON artifact validation.

Each model mirrors the implicit schema of a run artifact file.
Validation is used as a safety net: failures log warnings but never
block writes or reads.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class LiveSnapshot(BaseModel):
    """Schema for run_artifact/live.json"""

    model_config = ConfigDict(extra="allow")

    run_id: str
    issue_id: str
    state: str
    mergeable: bool
    failed_conditions: list[str] = Field(default_factory=list)
    flow_control: dict[str, Any] = Field(default_factory=dict)
    builder: dict[str, Any] = Field(default_factory=dict)
    review: dict[str, Any] = Field(default_factory=dict)
    verification: dict[str, Any] = Field(default_factory=dict)
    event_tail: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: str = ""


class Conclusion(BaseModel):
    """Schema for run_artifact/conclusion.json"""

    model_config = ConfigDict(extra="allow")

    run_id: str
    issue_id: str
    verdict: str  # "pass" | "fail"
    mergeable: bool
    failed_conditions: list[str] = Field(default_factory=list)
    flow_control: dict[str, Any] = Field(default_factory=dict)
    state: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)
    generated_at: str = ""


class ArtifactManifestSchema(BaseModel):
    """Schema for run_artifact/manifest.json"""

    model_config = ConfigDict(extra="allow")

    schema_version: str = "1.0"
    run_id: str
    issue_id: str
    state: str = ""
    mergeable: bool = False
    flow_control: dict[str, Any] = Field(default_factory=dict)
    events_count: int = 0
    generated_at: str = ""
    artifacts: dict[str, str] = Field(default_factory=dict)


class RunReport(BaseModel):
    """Schema for report.json (legacy) or run_artifact/live.json"""

    model_config = ConfigDict(extra="allow")

    state: str = ""
    run_id: str = ""
    issue_id: str = ""
    title: str = ""
    mergeable: bool = False
    failed_conditions: list[str] = Field(default_factory=list)
    flow_control: dict[str, Any] = Field(default_factory=dict)
    builder: dict[str, Any] = Field(default_factory=dict)
    review: dict[str, Any] = Field(default_factory=dict)
    verification: dict[str, Any] = Field(default_factory=dict)
    human_acceptance: dict[str, Any] = Field(default_factory=dict)


class RoundSummarySchema(BaseModel):
    """Schema for rounds/round-N/round_summary.json"""

    model_config = ConfigDict(extra="allow")

    round_id: int
    wave_id: int
    status: str
    started_at: str = ""
    completed_at: str | None = None
    worker_results: list[dict[str, Any]] = Field(default_factory=list)
    decision: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_live_snapshot(data: dict[str, Any]) -> LiveSnapshot | None:
    """Validate *data* against :class:`LiveSnapshot`.

    Returns the validated model on success, or ``None`` on failure
    (after logging a warning).
    """
    try:
        return LiveSnapshot.model_validate(data)
    except ValidationError as exc:
        logger.warning("LiveSnapshot validation failed: %s", exc)
        return None


def validate_conclusion(data: dict[str, Any]) -> Conclusion | None:
    try:
        return Conclusion.model_validate(data)
    except ValidationError as exc:
        logger.warning("Conclusion validation failed: %s", exc)
        return None


def validate_manifest(data: dict[str, Any]) -> ArtifactManifestSchema | None:
    try:
        return ArtifactManifestSchema.model_validate(data)
    except ValidationError as exc:
        logger.warning("ArtifactManifestSchema validation failed: %s", exc)
        return None


def validate_run_report(data: dict[str, Any]) -> RunReport | None:
    try:
        return RunReport.model_validate(data)
    except ValidationError as exc:
        logger.warning("RunReport validation failed: %s", exc)
        return None


def validate_round_summary(data: dict[str, Any]) -> RoundSummarySchema | None:
    try:
        return RoundSummarySchema.model_validate(data)
    except ValidationError as exc:
        logger.warning("RoundSummarySchema validation failed: %s", exc)
        return None
