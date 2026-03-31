from __future__ import annotations

from spec_orch.runtime_core.observability.models import RuntimeRecap


def build_runtime_recap(
    *,
    subject_key: str,
    title: str,
    bullets: list[str],
    artifact_refs: dict[str, str] | None = None,
    updated_at: str = "",
) -> RuntimeRecap:
    return RuntimeRecap(
        subject_key=subject_key,
        title=title,
        bullets=list(bullets),
        artifact_refs=dict(artifact_refs or {}),
        updated_at=updated_at,
    )


__all__ = ["build_runtime_recap"]
