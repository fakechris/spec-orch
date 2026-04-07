"""Tests for per-issue transactional state methods on DaemonStateStore."""

from __future__ import annotations

from pathlib import Path

from spec_orch.services.daemon_state_store import DaemonStateStore


def _make_store(tmp_path: Path) -> DaemonStateStore:
    lockdir = tmp_path / "locks"
    lockdir.mkdir(parents=True, exist_ok=True)
    return DaemonStateStore(lockdir)


def test_mark_in_progress(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.mark_in_progress("SPC-1")
    assert store.is_in_progress("SPC-1")
    assert not store.is_processed("SPC-1")


def test_mark_processed_clears_in_progress(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.mark_in_progress("SPC-2")
    store.mark_processed("SPC-2")
    assert store.is_processed("SPC-2")
    assert not store.is_in_progress("SPC-2")


def test_mark_dead_letter_clears_retry(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.mark_in_progress("SPC-3")
    store.mark_dead_letter("SPC-3")
    assert store.is_dead_letter("SPC-3")
    assert not store.is_in_progress("SPC-3")
    assert not store.should_backoff("SPC-3")


def test_clear_dead_letter(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.mark_dead_letter("SPC-4")
    store.clear_dead_letter("SPC-4")
    assert not store.is_dead_letter("SPC-4")
    assert not store.is_processed("SPC-4")


def test_clear_all_dead_letter(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.mark_dead_letter("SPC-5")
    store.mark_dead_letter("SPC-6")
    count = store.clear_all_dead_letter()
    assert count == 2
    assert not store.is_dead_letter("SPC-5")
    assert not store.is_dead_letter("SPC-6")


def test_increment_retry_returns_retry(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    result = store.increment_retry("SPC-7", max_retries=3, base_delay=10)
    assert result == "retry"
    assert store.should_backoff("SPC-7")


def test_increment_retry_returns_dead_letter_on_max(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.increment_retry("SPC-8", max_retries=2, base_delay=10)
    result = store.increment_retry("SPC-8", max_retries=2, base_delay=10)
    assert result == "dead_letter"
    assert store.is_dead_letter("SPC-8")


def test_set_pr_commit(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.set_pr_commit("SPC-9", "abc123")
    state = store.get_issue_state("SPC-9")
    assert state is not None
    assert state["pr_commit"] == "abc123"


def test_list_in_progress(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.mark_in_progress("SPC-10")
    store.mark_in_progress("SPC-11")
    store.mark_processed("SPC-10")
    assert store.list_in_progress() == ["SPC-11"]


def test_list_dead_letter(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.mark_dead_letter("Z-1")
    store.mark_dead_letter("A-2")
    assert store.list_dead_letter() == ["A-2", "Z-1"]


def test_reaction_mark(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    assert not store.has_reaction_mark("test-mark")
    store.add_reaction_mark("test-mark")
    assert store.has_reaction_mark("test-mark")


def test_get_issue_state_returns_none_for_unknown(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    assert store.get_issue_state("NONEXISTENT") is None


def test_mark_triaged_and_clear(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.mark_triaged("SPC-12")
    state = store.get_issue_state("SPC-12")
    assert state is not None
    assert state["triaged"]
    store.clear_triaged("SPC-12")
    state = store.get_issue_state("SPC-12")
    assert state is not None
    assert not state["triaged"]


def test_snapshot_round_trip_with_transactional_state(tmp_path: Path) -> None:
    """Transactional writes are visible in load_snapshot."""
    store = _make_store(tmp_path)
    store.mark_in_progress("SPC-20")
    store.mark_processed("SPC-21")
    store.mark_dead_letter("SPC-22")
    store.add_reaction_mark("react-1")

    snapshot = store.load_snapshot()
    assert "SPC-20" in snapshot["in_progress"]
    assert "SPC-21" in snapshot["processed"]
    assert "SPC-22" in snapshot["dead_letter"]
    assert "react-1" in snapshot["reaction_marks"]
