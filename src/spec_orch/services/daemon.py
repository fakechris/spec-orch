from __future__ import annotations

import os
import re
import signal
import subprocess as _subprocess
import sys
import time
from pathlib import Path
from typing import Any

from spec_orch.domain.models import TERMINAL_STATES, RunResult, RunState
from spec_orch.domain.protocols import PlannerAdapter
from spec_orch.services.codex_exec_builder_adapter import CodexExecBuilderAdapter
from spec_orch.services.linear_client import LinearClient
from spec_orch.services.linear_issue_source import LinearIssueSource
from spec_orch.services.linear_write_back import LinearWriteBackService
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

        planner = raw.get("planner", {})
        self.planner_model: str | None = planner.get("model")
        self.planner_api_type: str = planner.get("api_type", "anthropic")
        self.planner_api_key_env: str | None = planner.get("api_key_env")
        self.planner_api_base_env: str | None = planner.get("api_base_env")
        self.planner_token_command: str | None = planner.get("token_command")

        github = raw.get("github", {})
        self.base_branch: str = github.get("base_branch", "main")

        daemon = raw.get("daemon", {})
        self.max_concurrent: int = daemon.get("max_concurrent", 1)
        self.lockfile_dir: str = daemon.get("lockfile_dir", ".spec_orch_locks/")
        self.consume_state: str = daemon.get("consume_state", "Ready")
        self.require_labels: list[str] = daemon.get("require_labels", ["agent-ready"])
        self.exclude_labels: list[str] = daemon.get("exclude_labels", ["blocked"])
        self.skip_parents: bool = daemon.get("skip_parents", True)

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
        self._write_back = LinearWriteBackService(client=client)

        planner = self._build_planner()

        controller = RunController(
            repo_root=self.repo_root,
            builder_adapter=builder,
            issue_source=issue_source,
            planner_adapter=planner,
        )

        print(f"[daemon] started, polling {self.config.team_key} every {self.config.poll_interval_seconds}s")  # noqa: E501
        if planner:
            print(f"[daemon] planner: {planner.ADAPTER_NAME}")
        try:
            while self._running:
                self._poll_and_run(client, controller)
                self._sleep(self.config.poll_interval_seconds)
        finally:
            client.close()
            print("[daemon] stopped")

    def _build_planner(self) -> PlannerAdapter | None:
        """Build a PlannerAdapter from config.

        Token resolution is deferred to the adapter's ``api_key`` property so
        that ``token_command`` tokens are refreshed on every ``plan()`` call,
        not just once at daemon startup.
        """
        if not self.config.planner_model:
            return None

        api_key: str | None = None
        if self.config.planner_api_key_env:
            api_key = os.environ.get(self.config.planner_api_key_env)

        api_base: str | None = None
        if self.config.planner_api_base_env:
            api_base = os.environ.get(self.config.planner_api_base_env)

        try:
            from spec_orch.services.litellm_planner_adapter import (
                LiteLLMPlannerAdapter,
            )

            return LiteLLMPlannerAdapter(
                model=self.config.planner_model,
                api_type=self.config.planner_api_type,
                api_key=api_key,
                api_base=api_base,
                token_command=self.config.planner_token_command,
            )
        except ImportError:
            print("[daemon] litellm not installed, planner disabled")
            return None

    def _poll_and_run(self, client: LinearClient, controller: RunController) -> None:
        try:
            issues = client.list_issues(
                team_key=self.config.team_key,
                assigned_to_me=self.config.issue_filter == "assigned_to_me",
                filter_state=self.config.consume_state,
                filter_labels=self.config.require_labels or None,
                exclude_labels=self.config.exclude_labels or None,
                exclude_parents=self.config.skip_parents,
            )
        except Exception as exc:
            print(f"[daemon] poll error: {exc}")
            return

        for raw_issue in issues:
            issue_id = raw_issue.get("identifier", "")
            linear_uid = raw_issue.get("id", "")
            if not issue_id or issue_id in self._processed:
                continue
            if self._is_locked(issue_id):
                continue

            self._claim(issue_id)
            print(f"[daemon] processing {issue_id} (full pipeline)")

            # Ready → In Progress
            if linear_uid:
                try:
                    client.update_issue_state(linear_uid, "In Progress")
                except Exception as exc:
                    print(f"[daemon] state→InProgress failed: {exc}")

            try:
                result = controller.advance_to_completion(issue_id)
                state = result.state
                mergeable = result.gate.mergeable
                blocked = ",".join(result.gate.failed_conditions) or "none"
                print(
                    f"[daemon] {issue_id}: state={state.value} "
                    f"mergeable={mergeable} blocked={blocked}"
                )
                if state in TERMINAL_STATES or state == RunState.GATE_EVALUATED:
                    self._notify(issue_id, mergeable)
                    pr_created = self._auto_create_pr(issue_id, result)
                    # In Progress → In Review (after PR)
                    if pr_created and linear_uid:
                        try:
                            client.update_issue_state(linear_uid, "In Review")
                        except Exception as exc:
                            print(f"[daemon] state→InReview failed: {exc}")
                    self._write_back_result(raw_issue, result)
                    self._processed.add(issue_id)
                else:
                    self._release(issue_id)
            except Exception as exc:
                print(f"[daemon] {issue_id} failed: {exc}")
                self._release(issue_id)

    def _auto_create_pr(
        self, issue_id: str, result: RunResult,
    ) -> bool:
        """Automatically create a GitHub PR when gate is evaluated.

        Returns True if a PR was successfully created.
        """
        if result.state != RunState.GATE_EVALUATED:
            return False
        try:
            from spec_orch.services.github_pr_service import GitHubPRService

            workspace = result.workspace
            gh_svc = GitHubPRService()
            title = f"[SpecOrch] {issue_id}: {result.issue.title}"
            body_lines = [
                f"## SpecOrch: {issue_id}",
                "",
                f"**Mergeable**: {'yes' if result.gate.mergeable else 'no'}",
            ]
            if result.gate.failed_conditions:
                body_lines.append(
                    f"**Blocked**: {', '.join(result.gate.failed_conditions)}"
                )
            body_lines.extend(["", f"Closes {issue_id}"])

            pr_url = gh_svc.create_pr(
                workspace=workspace,
                title=title,
                body="\n".join(body_lines),
                base=self.config.base_branch,
                draft=True,
            )
            if pr_url:
                print(f"[daemon] PR created: {pr_url}")
                gh_svc.set_gate_status(workspace=workspace, gate=result.gate)
                return True
            print(f"[daemon] could not create PR for {issue_id}")
            return False
        except (RuntimeError, OSError, FileNotFoundError) as exc:
            print(f"[daemon] auto-PR failed for {issue_id}: {exc}")
            return False

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

    def _write_back_result(
        self, raw_issue: dict[str, Any], result: RunResult,
    ) -> None:
        """Post a run summary back to Linear as a comment and move to Done."""
        import httpx

        linear_id = raw_issue.get("id", "")
        if not linear_id or not hasattr(self, "_write_back"):
            return
        try:
            self._write_back.post_run_summary(linear_id=linear_id, result=result)
            print(f"[daemon] wrote summary to Linear for {result.issue.issue_id}")
        except (httpx.HTTPError, RuntimeError, OSError) as exc:
            print(f"[daemon] write-back failed: {exc}")

        if result.gate.mergeable:
            try:
                client: LinearClient = self._write_back._client  # type: ignore[attr-defined]
                client.update_issue_state(linear_id, "Done")
                print(f"[daemon] moved {result.issue.issue_id} to Done")
            except Exception as exc:
                print(f"[daemon] state update failed: {exc}")

    def _notify(self, issue_id: str, mergeable: bool) -> None:
        status = "mergeable=true" if mergeable else "mergeable=false"
        sys.stdout.write("\a")
        sys.stdout.flush()

        if not _SAFE_ID_RE.match(issue_id):
            return

        import contextlib

        with contextlib.suppress(FileNotFoundError):
            _subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display notification "{status}" with title "SpecOrch: {issue_id} completed"',
                ],
                check=False,
                capture_output=True,
            )
