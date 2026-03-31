from __future__ import annotations

from spec_orch.runtime_core.compaction.models import (
    CompactionBoundary,
    CompactionRestoreBundle,
)


def build_restore_bundle(
    *,
    restored_state: dict[str, object] | None = None,
    attachment_refs: dict[str, object] | None = None,
    discovered_tools: list[str] | None = None,
) -> CompactionRestoreBundle:
    return CompactionRestoreBundle(
        restored_state=dict(restored_state or {}),
        attachment_refs=dict(attachment_refs or {}),
        discovered_tools=list(discovered_tools or []),
    )


def restore_bundle_from_boundary(boundary: CompactionBoundary) -> CompactionRestoreBundle:
    return CompactionRestoreBundle.from_dict(boundary.restore_bundle)


__all__ = [
    "build_restore_bundle",
    "restore_bundle_from_boundary",
]
