from __future__ import annotations

from pathlib import Path

from spec_orch.domain.models import BuilderResult


def test_one_shot_worker_handle_delegates_to_builder_adapter(tmp_path: Path) -> None:
    from spec_orch.services.workers.oneshot_worker_handle import OneShotWorkerHandle

    class StubBuilderAdapter:
        ADAPTER_NAME = "stub"
        AGENT_NAME = "stub-agent"

        def __init__(self) -> None:
            self.calls: list[tuple[str, Path]] = []

        def run(self, *, issue, workspace: Path, run_id=None, event_logger=None) -> BuilderResult:
            self.calls.append((issue.builder_prompt, workspace))
            return BuilderResult(
                succeeded=True,
                command=["stub"],
                stdout="ok",
                stderr="",
                report_path=workspace / "builder_report.json",
                adapter=self.ADAPTER_NAME,
                agent=self.AGENT_NAME,
            )

    builder = StubBuilderAdapter()
    handle = OneShotWorkerHandle(session_id="worker-1", builder_adapter=builder)

    result = handle.send(prompt="Fix the broken packet.", workspace=tmp_path)

    assert result.succeeded is True
    assert builder.calls == [("Fix the broken packet.", tmp_path)]


def test_in_memory_factory_reuses_session_id_handle(tmp_path: Path) -> None:
    from spec_orch.services.workers.in_memory_worker_handle_factory import (
        InMemoryWorkerHandleFactory,
    )
    from spec_orch.services.workers.oneshot_worker_handle import OneShotWorkerHandle

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

    factory = InMemoryWorkerHandleFactory(
        creator=lambda session_id, workspace: OneShotWorkerHandle(
            session_id=session_id,
            builder_adapter=StubBuilderAdapter(),
        )
    )

    handle1 = factory.create(session_id="worker-1", workspace=tmp_path)
    handle2 = factory.get("worker-1")

    assert handle2 is handle1


def test_one_shot_worker_handle_raises_after_close(tmp_path: Path) -> None:
    from spec_orch.services.workers.oneshot_worker_handle import OneShotWorkerHandle

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

    handle = OneShotWorkerHandle(session_id="worker-1", builder_adapter=StubBuilderAdapter())
    handle.close(tmp_path)

    try:
        handle.send(prompt="should fail", workspace=tmp_path)
    except RuntimeError as exc:
        assert "closed" in str(exc)
    else:
        raise AssertionError("expected closed worker handle to raise")


def test_factory_close_all_closes_every_handle(tmp_path: Path) -> None:
    from spec_orch.services.workers.in_memory_worker_handle_factory import (
        InMemoryWorkerHandleFactory,
    )

    closed: list[str] = []

    class StubHandle:
        def __init__(self, session_id: str) -> None:
            self._session_id = session_id

        @property
        def session_id(self) -> str:
            return self._session_id

        def send(self, *, prompt: str, workspace: Path, event_logger=None) -> BuilderResult:
            return BuilderResult(
                succeeded=True,
                command=["stub"],
                stdout="ok",
                stderr="",
                report_path=workspace / "builder_report.json",
                adapter="stub",
                agent="stub",
            )

        def cancel(self, workspace: Path) -> None:
            return None

        def close(self, workspace: Path) -> None:
            closed.append(self._session_id)

    factory = InMemoryWorkerHandleFactory(
        creator=lambda session_id, workspace: StubHandle(session_id)
    )
    factory.create(session_id="worker-1", workspace=tmp_path)
    factory.create(session_id="worker-2", workspace=tmp_path)

    factory.close_all(tmp_path)

    assert closed == ["worker-1", "worker-2"]
    assert factory.get("worker-1") is None
