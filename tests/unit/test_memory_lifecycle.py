from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from spec_orch.services.memory.fs_provider import FileSystemMemoryProvider
from spec_orch.services.memory.lifecycle import MemoryLifecycleManager, SessionMemorySnapshot


def test_memory_lifecycle_records_session_snapshot_and_working_entry(tmp_path: Path) -> None:
    provider = FileSystemMemoryProvider(tmp_path / "memory")
    manager = MemoryLifecycleManager(tmp_path / "memory" / "_lifecycle", provider)

    key = manager.record_session_snapshot(
        SessionMemorySnapshot(
            snapshot_id="snap-1",
            session_id="acceptance-run-1",
            subject_kind="acceptance_graph",
            subject_id="mission-1:round-1",
            event_count=2,
            facts=["surface_scan completed", "guided_probe completed"],
            artifact_refs={"graph_run": "graph_run.json"},
        )
    )

    snapshots = manager.read_session_snapshots()
    entry = provider.get(key)

    assert len(snapshots) == 1
    assert snapshots[0].session_id == "acceptance-run-1"
    assert entry is not None
    assert entry.layer.value == "working"
    assert entry.metadata["session_id"] == "acceptance-run-1"


def test_memory_lifecycle_respects_shared_memory_freshness(tmp_path: Path) -> None:
    provider = FileSystemMemoryProvider(tmp_path / "memory")
    manager = MemoryLifecycleManager(tmp_path / "memory" / "_lifecycle", provider)

    assert manager.reserve_shared_memory_write("acceptance:route:/dashboard") is True
    assert manager.reserve_shared_memory_write("acceptance:route:/dashboard") is False


def test_memory_lifecycle_consolidation_lock_is_exclusive(tmp_path: Path) -> None:
    provider = FileSystemMemoryProvider(tmp_path / "memory")
    manager = MemoryLifecycleManager(tmp_path / "memory" / "_lifecycle", provider)

    with (
        manager.consolidation_lock("distill"),
        pytest.raises(RuntimeError),
        manager.consolidation_lock("distill"),
    ):
        pass


def test_memory_lifecycle_records_session_snapshot_without_rewrite_all(
    tmp_path: Path,
) -> None:
    provider = FileSystemMemoryProvider(tmp_path / "memory")
    manager = MemoryLifecycleManager(tmp_path / "memory" / "_lifecycle", provider)

    with (
        patch.object(manager._provider, "store", return_value="memory-key"),
        patch("pathlib.Path.write_text", side_effect=AssertionError("rewrite-all")),
    ):
        manager.record_session_snapshot(
            SessionMemorySnapshot(
                snapshot_id="snap-1",
                session_id="acceptance-run-1",
                subject_kind="acceptance_graph",
                subject_id="mission-1:round-1",
                event_count=2,
                facts=["surface_scan completed"],
            )
        )

    snapshots = manager.read_session_snapshots()
    assert len(snapshots) == 1
    assert snapshots[0].snapshot_id == "snap-1"
