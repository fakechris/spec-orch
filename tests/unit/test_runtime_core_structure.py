from __future__ import annotations

from pathlib import Path


def _source(repo_relative_path: str) -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / repo_relative_path).read_text(encoding="utf-8")


def test_migrated_leaf_owners_do_not_hand_roll_worker_report_targets() -> None:
    oneshot_source = _source("src/spec_orch/services/workers/oneshot_worker_handle.py")
    assert "write_worker_attempt_payloads" in oneshot_source
    assert "builder_report.json" not in oneshot_source
    assert "atomic_write_json(" not in oneshot_source


def test_packet_executor_routes_attempt_shaping_through_runtime_core_adapter() -> None:
    packet_executor_source = _source("src/spec_orch/services/packet_executor.py")
    assert "from spec_orch.runtime_core.adapters import build_packet_attempt_payload" in (
        packet_executor_source
    )
    assert '"normalized_attempt": build_packet_attempt_payload(' in packet_executor_source
    assert "builder_report.json" not in packet_executor_source
    assert "round_summary.json" not in packet_executor_source


def test_execution_semantics_service_shims_remain_logic_free_reexports() -> None:
    reader_source = _source("src/spec_orch/services/execution_semantics_reader.py")
    writer_source = _source("src/spec_orch/services/execution_semantics_writer.py")
    assert "from spec_orch.runtime_core.readers import" in reader_source
    assert "from spec_orch.runtime_core.writers import" in writer_source
    assert "def " not in reader_source
    assert "def " not in writer_source
