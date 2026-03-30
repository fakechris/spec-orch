from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from spec_orch.domain.models import BuilderResult
from spec_orch.services.workers.oneshot_worker_handle import OneShotWorkerHandle


def test_one_shot_worker_handle_delegates_worker_payload_write(tmp_path: Path) -> None:
    class StubBuilderAdapter:
        ADAPTER_NAME = "stub"
        AGENT_NAME = "stub-agent"

        def run(self, *, issue, workspace: Path, run_id=None, event_logger=None) -> BuilderResult:
            return BuilderResult(
                succeeded=True,
                command=["stub"],
                stdout="ok",
                stderr="",
                report_path=workspace / "builder_report.json",
                adapter=self.ADAPTER_NAME,
                agent=self.AGENT_NAME,
            )

    delegated: dict[str, object] = {}

    def fake_write_worker_attempt_payloads(
        worker_dir: Path,
        *,
        builder_result: BuilderResult,
        session_name: str | None = None,
        extra_report: dict | None = None,
    ) -> dict[str, Path]:
        delegated["worker_dir"] = worker_dir
        delegated["builder_result"] = builder_result
        delegated["session_name"] = session_name
        delegated["extra_report"] = extra_report
        return {"builder_report": worker_dir / "builder_report.json"}

    handle = OneShotWorkerHandle(session_id="worker-1", builder_adapter=StubBuilderAdapter())

    with patch(
        "spec_orch.services.workers.oneshot_worker_handle.write_worker_attempt_payloads",
        fake_write_worker_attempt_payloads,
    ):
        result = handle.send(prompt="Fix the broken packet.", workspace=tmp_path)

    assert result.succeeded is True
    assert delegated["worker_dir"] == tmp_path
    assert delegated["builder_result"] is result
    assert delegated["session_name"] == "worker-1"
    assert delegated["extra_report"] is None
