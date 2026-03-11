from __future__ import annotations

import re
import signal
import sys
import time
from pathlib import Path
from typing import Any

from spec_orch.services.codex_exec_builder_adapter import CodexExecBuilderAdapter
from spec_orch.services.linear_client import LinearClient
from spec_orch.services.linear_issue_source import LinearIssueSource
from spec_orch.services.run_controller import RunController

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class DaemonConfig:
    def __init__(self, raw: dict[str, Any]) -> None:
        linear = raw.get("linear", {})
        self.linear_token_env: str = linear.get("token_env", "SPEC_ORCH_LINEAR_TOKEN")
        self.team_key: str = linear.get("team_key", "SPC")
        self.poll_interval_seconds: int = linear.get("poll_interval_seconds", 60)
        self.issue_filter: str = linear.get("issue_filter", "assigned_to_me")

        builder = raw.get("builder", {})
        self.builder_adapter: str = builder.get("adapter", "codex_exec")
        self.codex_executable: str = builder.get("codex_executable", "codex")

        daemon = raw.get("daemon", {})
        self.max_concurrent: int = daemon.get("max_concurrent", 1)
        self.lockfile_dir: str = daemon.get("lockfile_dir", ".spec_orch_locks/")

    @classmethod
    def from_toml(cls, path: Path) -> DaemonConfig:
        import tomllib

        with open(path, "rb") as f:
            raw = tomllib.load(f)
        return cls(raw)


class SpecOrchDaemon:
    def __init__(self, *, config: DaemonConfig, repo_root: Path) -> None:
        self.config = config
        self.repo_root = repo_root
        self._running = True
        self._processed: set[str] = set()
        self._lockdir = repo_root / config.lockfile_dir
        self._lockdir.mkdir(parents=True, exist_ok=True)

    def run(self) -> None:
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        client = LinearClient(token_env=self.config.linear_token_env)
        issue_source = LinearIssueSource(client=client)
        builder = CodexExecBuilderAdapter(executable=self.config.codex_executable)
        controller = RunController(
            repo_root=self.repo_root,
            builder_adapter=builder,
            issue_source=issue_source,
        )

        print(f"[daemon] started, polling {self.config.team_key} every {self.config.poll_interval_seconds}s")  # noqa: E501
        try:
            while self._running:
                self._poll_and_run(client, controller)
                self._sleep(self.config.poll_interval_seconds)
        finally:
            client.close()
            print("[daemon] stopped")

    def _poll_and_run(self, client: LinearClient, controller: RunController) -> None:
        try:
            issues = client.list_issues(
                team_key=self.config.team_key,
                assigned_to_me=self.config.issue_filter == "assigned_to_me",
                filter_state="Todo",
            )
        except Exception as exc:
            print(f"[daemon] poll error: {exc}")
            return

        for raw_issue in issues:
            issue_id = raw_issue.get("identifier", "")
            if not issue_id or issue_id in self._processed:
                continue
            if self._is_locked(issue_id):
                continue

            self._claim(issue_id)
            print(f"[daemon] processing {issue_id}")
            try:
                result = controller.run_issue(issue_id)
                mergeable = result.gate.mergeable
                blocked = ",".join(result.gate.failed_conditions) or "none"
                print(f"[daemon] {issue_id} done: mergeable={mergeable} blocked={blocked}")
                self._notify(issue_id, mergeable)
                self._processed.add(issue_id)
            except Exception as exc:
                print(f"[daemon] {issue_id} failed: {exc}")
                self._release(issue_id)

    def _is_locked(self, issue_id: str) -> bool:
        return (self._lockdir / f"{issue_id}.lock").exists()

    def _claim(self, issue_id: str) -> None:
        lockfile = self._lockdir / f"{issue_id}.lock"
        lockfile.write_text(str(time.time()))

    def _release(self, issue_id: str) -> None:
        lockfile = self._lockdir / f"{issue_id}.lock"
        lockfile.unlink(missing_ok=True)

    def _sleep(self, seconds: int) -> None:
        for _ in range(seconds):
            if not self._running:
                break
            time.sleep(1)

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        print(f"\n[daemon] received signal {signum}, shutting down gracefully...")
        self._running = False

    def _notify(self, issue_id: str, mergeable: bool) -> None:
        status = "mergeable=true" if mergeable else "mergeable=false"
        sys.stdout.write("\a")
        sys.stdout.flush()

        if not _SAFE_ID_RE.match(issue_id):
            return

        try:
            import subprocess

            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display notification "{status}" with title "SpecOrch: {issue_id} completed"',
                ],
                check=False,
                capture_output=True,
            )
        except FileNotFoundError:
            pass
