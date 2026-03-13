from __future__ import annotations

import json as _json
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
        self.require_labels: list[str] = daemon.get("require_labels", [])
        self.exclude_labels: list[str] = daemon.get(
            "exclude_labels", ["blocked", "needs-clarification"],
        )
        self.skip_parents: bool = daemon.get("skip_parents", True)

    @classmethod
    def from_toml(cls, path: Path) -> DaemonConfig:
        import tomllib

        with open(path, "rb") as f:
            raw = tomllib.load(f)
        return cls(raw)


class SpecOrchDaemon:
    STATE_FILE = "daemon_state.json"

    def __init__(self, *, config: DaemonConfig, repo_root: Path) -> None:
        self.config = config
        self.repo_root = repo_root
        self._running = True
        self._readiness_checker: Any = None
        self._lockdir = repo_root / config.lockfile_dir
        self._lockdir.mkdir(parents=True, exist_ok=True)
        self._state_path = self._lockdir / self.STATE_FILE
        saved = self._load_state()
        self._processed: set[str] = set(saved.get("processed", []))
        self._triaged: set[str] = set(saved.get("triaged", []))
        self._last_poll: str = saved.get("last_poll", "")

    def _load_state(self) -> dict[str, Any]:
        if self._state_path.exists():
            try:
                return _json.loads(self._state_path.read_text())
            except (_json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_state(self) -> None:
        data = {
            "processed": sorted(self._processed),
            "triaged": sorted(self._triaged),
            "last_poll": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        try:
            self._state_path.write_text(_json.dumps(data, indent=2) + "\n")
        except OSError as exc:
            print(f"[daemon] failed to save state: {exc}")

    def run(self) -> None:
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        client = LinearClient(token_env=self.config.linear_token_env)
        issue_source = LinearIssueSource(client=client)
        builder = CodexExecBuilderAdapter(executable=self.config.codex_executable)
        self._write_back = LinearWriteBackService(client=client)

        planner = self._build_planner()

        from spec_orch.services.readiness_checker import ReadinessChecker

        self._readiness_checker = ReadinessChecker(planner=planner)

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
                self._check_clarification_replies(client)
                self._poll_and_run(client, controller)
                self._save_state()
                self._sleep(self.config.poll_interval_seconds)
        finally:
            self._save_state()
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

            if not self._triage_issue(client, raw_issue):
                self._release(issue_id)
                continue

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

                    gate_policy = self._load_gate_policy()
                    auto_merged = (
                        pr_created
                        and gate_policy.auto_merge
                        and mergeable
                    )

                    if pr_created and linear_uid:
                        try:
                            target_state = "Done" if auto_merged else "In Review"
                            client.update_issue_state(linear_uid, target_state)
                            print(f"[daemon] {issue_id} → {target_state}")
                        except Exception as exc:
                            print(f"[daemon] state update failed: {exc}")
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

        When the gate policy's daemon profile allows auto-merge and
        all auto-merge conditions pass, the PR is created as non-draft
        and auto-merge is enabled.

        Returns True if a PR was successfully created.
        """
        if result.state != RunState.GATE_EVALUATED:
            return False
        try:
            from spec_orch.services.github_pr_service import GitHubPRService

            gate_policy = self._load_gate_policy()
            should_auto = gate_policy.auto_merge and result.gate.mergeable

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
                draft=not should_auto,
            )
            if pr_url:
                print(f"[daemon] PR created: {pr_url}")
                gh_svc.set_gate_status(workspace=workspace, gate=result.gate)

                if should_auto:
                    merged = gh_svc.merge_pr(workspace, method="squash")
                    if merged:
                        print(f"[daemon] auto-merged PR for {issue_id}")
                    else:
                        print("[daemon] auto-merge requested (waiting for checks)")
                return True
            print(f"[daemon] could not create PR for {issue_id}")
            return False
        except (RuntimeError, OSError, FileNotFoundError) as exc:
            print(f"[daemon] auto-PR failed for {issue_id}: {exc}")
            return False

    def _load_gate_policy(self) -> Any:
        """Load gate policy with daemon profile applied."""
        from spec_orch.services.gate_service import GatePolicy

        policy_path = self.repo_root / "gate.policy.yaml"
        if policy_path.exists():
            base_policy = GatePolicy.from_yaml(policy_path)
        else:
            base_policy = GatePolicy.default()
        return base_policy.with_profile("daemon")

    def _triage_issue(
        self, client: LinearClient, raw_issue: dict[str, Any],
    ) -> bool:
        """Check issue readiness before execution.

        Returns True if the issue is ready to execute, False if it
        needs clarification (comment posted, label applied).
        """
        issue_id = raw_issue.get("identifier", "")
        linear_uid = raw_issue.get("id", "")
        description = raw_issue.get("description", "") or ""

        result = self._readiness_checker.check(description)
        if result.ready:
            return True

        if issue_id in self._triaged:
            return False

        print(f"[daemon] {issue_id}: needs clarification ({result.missing_fields})")

        if linear_uid:
            try:
                comment = result.format_comment()
                client.add_comment(linear_uid, comment)
                print(f"[daemon] {issue_id}: posted clarification request")
            except Exception as exc:
                print(f"[daemon] {issue_id}: comment failed: {exc}")

            try:
                client.add_label(linear_uid, "needs-clarification")
            except Exception as exc:
                print(f"[daemon] {issue_id}: add label failed: {exc}")

        self._triaged.add(issue_id)
        return False

    def _check_clarification_replies(self, client: LinearClient) -> None:
        """Check for user replies on issues waiting for clarification.

        When a user replies, remove the needs-clarification label so the
        issue re-enters the Ready candidate pool on the next poll.
        """
        try:
            waiting = client.list_issues(
                team_key=self.config.team_key,
                filter_state=self.config.consume_state,
                filter_labels=["needs-clarification"],
                exclude_parents=self.config.skip_parents,
            )
        except Exception as exc:
            print(f"[daemon] clarification check error: {exc}")
            return

        for raw_issue in waiting:
            issue_id = raw_issue.get("identifier", "")
            linear_uid = raw_issue.get("id", "")
            if not linear_uid:
                continue

            try:
                comments = client.list_comments(linear_uid)
            except Exception as exc:
                print(f"[daemon] {issue_id}: failed to list comments: {exc}")
                continue

            bot_comment_idx = -1
            for idx, c in enumerate(comments):
                body = c.get("body", "")
                if "SpecOrch: Clarification Needed" in body:
                    bot_comment_idx = idx

            if bot_comment_idx < 0:
                continue

            has_reply = any(
                c.get("body", "")
                and "SpecOrch: Clarification Needed" not in c.get("body", "")
                for c in comments[bot_comment_idx + 1:]
            )

            if has_reply:
                print(f"[daemon] {issue_id}: user replied, re-entering pool")
                try:
                    client.remove_label(linear_uid, "needs-clarification")
                except Exception as exc:
                    print(f"[daemon] {issue_id}: remove label failed: {exc}")
                self._triaged.discard(issue_id)

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
