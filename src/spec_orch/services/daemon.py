from __future__ import annotations

import json as _json
import os
import re
import signal
import subprocess as _subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast

from spec_orch.domain.models import TERMINAL_STATES, RunResult, RunState
from spec_orch.domain.protocols import PlannerAdapter
from spec_orch.services.adapter_factory import create_builder, create_reviewer
from spec_orch.services.conflict_resolver import ConflictResolver
from spec_orch.services.github_pr_service import GitHubPRService
from spec_orch.services.linear_client import LinearClient
from spec_orch.services.linear_issue_source import LinearIssueSource
from spec_orch.services.linear_write_back import LinearWriteBackService
from spec_orch.services.run_controller import RunController

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_PR_ISSUE_ID_RE = re.compile(r"\[SpecOrch\]\s+([A-Za-z0-9_-]+):")


class DaemonConfig:
    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw
        linear = raw.get("linear", {})
        self.linear_token_env: str = linear.get("token_env", "SPEC_ORCH_LINEAR_TOKEN")
        self.team_key: str = linear.get("team_key", "SPC")
        self.poll_interval_seconds: int = linear.get("poll_interval_seconds", 60)
        self.issue_filter: str = linear.get("issue_filter", "assigned_to_me")

        builder = raw.get("builder", {})
        self.builder_adapter: str = builder.get("adapter", "codex_exec")
        self.codex_executable: str = builder.get("executable") or builder.get(
            "codex_executable", "codex"
        )

        reviewer = raw.get("reviewer", {})
        self.reviewer_adapter: str = reviewer.get("adapter", "local")

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
            "exclude_labels",
            ["blocked", "needs-clarification"],
        )
        self.skip_parents: bool = daemon.get("skip_parents", True)
        self.max_retries: int = daemon.get("max_retries", 3)
        self.retry_base_delay: int = daemon.get("retry_base_delay_seconds", 60)
        self.hotfix_labels: list[str] = daemon.get("hotfix_labels", ["hotfix", "urgent", "P0"])

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
        self._pr_commits: dict[str, str] = dict(saved.get("pr_commits", {}))
        self._retry_counts: dict[str, int] = dict(saved.get("retry_counts", {}))
        self._dead_letter: set[str] = set(saved.get("dead_letter", []))
        self._in_progress: set[str] = set(saved.get("in_progress", []))

        from spec_orch.services.event_bus import get_event_bus

        self._event_bus = get_event_bus()

        from spec_orch.services.lifecycle_manager import MissionLifecycleManager

        self._lifecycle_manager = MissionLifecycleManager(
            repo_root=repo_root, event_bus=self._event_bus
        )

        from spec_orch.services.memory.service import get_memory_service

        self._memory_service = get_memory_service(repo_root=repo_root)
        self._memory_service.subscribe_to_event_bus()

    def _load_state(self) -> dict[str, Any]:
        if self._state_path.exists():
            try:
                return cast(dict[str, Any], _json.loads(self._state_path.read_text()))
            except (_json.JSONDecodeError, OSError) as exc:
                print(f"[daemon] failed to load state: {exc}")
        return {}

    def _save_state(self) -> None:
        data = {
            "processed": sorted(self._processed),
            "triaged": sorted(self._triaged),
            "pr_commits": self._pr_commits,
            "retry_counts": self._retry_counts,
            "dead_letter": sorted(self._dead_letter),
            "in_progress": sorted(self._in_progress),
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
        builder = create_builder(self.repo_root, toml_override=self.config._raw)
        reviewer = create_reviewer(self.repo_root, toml_override=self.config._raw)
        self._builder = builder
        self._write_back = LinearWriteBackService(client=client)

        planner = self._build_planner()

        from spec_orch.services.evidence_analyzer import EvidenceAnalyzer

        self._evidence_analyzer = EvidenceAnalyzer(self.repo_root)

        from spec_orch.services.readiness_checker import ReadinessChecker

        self._readiness_checker = ReadinessChecker(
            planner=planner,
            evidence_context=self._get_evidence_context(),
        )

        controller = RunController(
            repo_root=self.repo_root,
            builder_adapter=builder,
            issue_source=issue_source,
            planner_adapter=planner,
            review_adapter=reviewer,
        )

        interval = self.config.poll_interval_seconds
        print(f"[daemon] started, polling {self.config.team_key} every {interval}s")
        if planner:
            print(f"[daemon] planner: {planner.ADAPTER_NAME}")
        if self._dead_letter:
            print(f"[daemon] dead letter queue: {sorted(self._dead_letter)}")

        self.resume_in_progress(controller)

        try:
            while self._running:
                self._tick_missions()
                self._check_clarification_replies(client)
                self._check_review_updates(client)
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

    def _tick_missions(self) -> None:
        """Advance mission lifecycles on each daemon tick."""
        try:
            from spec_orch.services.mission_service import MissionService

            ms = MissionService(self.repo_root)
            missions = ms.list_missions()
        except Exception as exc:
            print(f"[daemon] mission tick error: {exc}")
            return

        for mission in missions:
            if mission.status.value not in ("approved", "in_progress"):
                continue

            state = self._lifecycle_manager.get_state(mission.mission_id)
            if state is None:
                print(f"[daemon] tracking mission {mission.mission_id}")
                self._lifecycle_manager.begin_tracking(mission.mission_id)

            try:
                self._lifecycle_manager.auto_advance(mission.mission_id)
            except Exception as exc:
                print(f"[daemon] mission {mission.mission_id} advance error: {exc}")

    def _find_mission_for_issue(self, issue_id: str) -> str | None:
        """Return the mission_id that owns *issue_id*, if any."""
        for mid, state in self._lifecycle_manager.all_states().items():
            if issue_id in state.issue_ids and issue_id not in state.completed_issues:
                return mid
        return None

    def handle_btw(self, issue_id: str, message: str, channel: str) -> bool:
        """Inject /btw context into a running issue via the lifecycle manager."""
        return self._lifecycle_manager.inject_btw(issue_id, message, channel)

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

        sorted_issues = sorted(
            issues,
            key=lambda i: 0 if self._is_hotfix(i) else 1,
        )
        for raw_issue in sorted_issues:
            issue_id = raw_issue.get("identifier", "")
            linear_uid = raw_issue.get("id", "")
            if not issue_id or issue_id in self._processed:
                continue
            if issue_id in self._dead_letter:
                continue
            if self._is_locked(issue_id):
                continue
            if self._should_backoff(issue_id):
                continue

            self._claim(issue_id)

            is_hotfix = self._is_hotfix(raw_issue)
            if not is_hotfix and not self._triage_issue(client, raw_issue):
                self._release(issue_id)
                continue

            # Ready → In Progress
            if linear_uid:
                try:
                    client.update_issue_state(linear_uid, "In Progress")
                except Exception as exc:
                    print(f"[daemon] state→InProgress failed: {exc}")

            mission_id = self._detect_mission(issue_id, raw_issue)
            if mission_id:
                self._execute_mission(
                    issue_id,
                    mission_id,
                    raw_issue,
                    client,
                )
            else:
                self._execute_single(
                    issue_id,
                    raw_issue,
                    client,
                    controller,
                    is_hotfix=is_hotfix,
                )

    @staticmethod
    def _sanitize_id(raw_id: str) -> str:
        """Strip path-traversal characters from a mission/issue ID."""
        return re.sub(r"[/\\.\s]+", "-", raw_id).strip("-")

    def _detect_mission(
        self,
        issue_id: str,
        raw_issue: dict[str, Any],
    ) -> str | None:
        """Check if the issue references a mission plan.json.

        Returns the mission_id if a plan.json exists, else None.
        """
        desc = raw_issue.get("description", "") or ""
        specs_dir = self.repo_root / "docs" / "specs"

        mission_match = re.search(r"mission[:\s]+(\S+)", desc, re.IGNORECASE)
        if mission_match:
            mid = self._sanitize_id(mission_match.group(1))
            if (specs_dir / mid / "plan.json").exists():
                return mid

        if re.search(r"plan\.json", desc, re.IGNORECASE):
            safe_id = self._sanitize_id(issue_id)
            if (specs_dir / safe_id / "plan.json").exists():
                return safe_id

        safe_id = self._sanitize_id(issue_id)
        if (specs_dir / safe_id / "plan.json").exists():
            return safe_id
        return None

    def _execute_single(
        self,
        issue_id: str,
        raw_issue: dict[str, Any],
        client: LinearClient,
        controller: RunController,
        *,
        is_hotfix: bool = False,
    ) -> None:
        """Execute a single issue through the standard pipeline."""
        from spec_orch.domain.models import FlowType

        linear_uid = raw_issue.get("id", "")
        flow_type = FlowType.HOTFIX if is_hotfix else None
        label = "hotfix" if is_hotfix else "single issue"
        print(f"[daemon] processing {issue_id} ({label} pipeline)")
        self._in_progress.add(issue_id)
        self._save_state()
        self._event_bus.emit_issue_state(issue_id, "building")
        try:
            result = controller.advance_to_completion(issue_id, flow_type=flow_type)
            state = result.state
            mergeable = result.gate.mergeable
            blocked = ",".join(result.gate.failed_conditions) or "none"
            print(
                f"[daemon] {issue_id}: state={state.value} mergeable={mergeable} blocked={blocked}"
            )
            if state in TERMINAL_STATES or state == RunState.GATE_EVALUATED:
                self._event_bus.emit_issue_state(issue_id, "completed", mergeable=mergeable)
                mission_id = self._find_mission_for_issue(issue_id)
                if mission_id:
                    self._lifecycle_manager.mark_issue_done(mission_id, issue_id)

                self._notify(issue_id, mergeable)
                pr_created = self._auto_create_pr(issue_id, result)

                gate_policy = self._load_gate_policy_for("hotfix" if is_hotfix else "daemon")
                auto_merged = pr_created and gate_policy.auto_merge and mergeable

                if pr_created and linear_uid:
                    try:
                        target_state = "Done" if auto_merged else "In Review"
                        client.update_issue_state(linear_uid, target_state)
                        print(f"[daemon] {issue_id} → {target_state}")
                    except Exception as exc:
                        print(f"[daemon] state update failed: {exc}")
                self._write_back_result(raw_issue, result)
                self._processed.add(issue_id)
                self._in_progress.discard(issue_id)
                self._retry_counts.pop(issue_id, None)
            else:
                self._in_progress.discard(issue_id)
                self._release(issue_id)
        except Exception as exc:
            print(f"[daemon] {issue_id} failed: {exc}")
            self._in_progress.discard(issue_id)
            self._record_failure(issue_id, str(exc), client, linear_uid)
            self._release(issue_id)

    def _execute_mission(
        self,
        issue_id: str,
        mission_id: str,
        raw_issue: dict[str, Any],
        client: LinearClient,
    ) -> None:
        """Execute a mission-level plan with parallel wave execution."""
        from spec_orch.services.parallel_run_controller import (
            ParallelRunController,
        )

        linear_uid = raw_issue.get("id", "")
        print(f"[daemon] processing {issue_id} (mission: {mission_id})")
        self._event_bus.emit_issue_state(issue_id, "building")

        try:
            plan = ParallelRunController.load_plan(mission_id, self.repo_root)
            prc = ParallelRunController(
                repo_root=self.repo_root,
                codex_bin=self.config.codex_executable,
            )

            for wave in plan.waves:
                if linear_uid:
                    try:
                        wave_msg = (
                            f"🔄 Wave {wave.wave_number}: "
                            f"{len(wave.work_packets)} packets — {wave.description}"
                        )
                        client.add_comment(linear_uid, wave_msg)
                    except Exception as exc:
                        print(f"[daemon] wave comment failed: {exc}")

            plan_result = prc.run_plan(plan)

            summary_lines = [
                f"## Mission Execution: {mission_id}",
                "",
                f"**Duration**: {plan_result.total_duration:.1f}s",
                f"**Result**: {'✅ Success' if plan_result.is_success() else '❌ Failed'}",
                "",
            ]
            for wr in plan_result.wave_results:
                status = "✅" if wr.all_succeeded else "❌"
                summary_lines.append(
                    f"- Wave {wr.wave_id}: {status} ({len(wr.packet_results)} packets)"
                )
                for pr in wr.failed_packets:
                    summary_lines.append(f"  - ❌ {pr.packet_id}: exit={pr.exit_code}")
            summary = "\n".join(summary_lines)

            if linear_uid:
                try:
                    client.add_comment(linear_uid, summary)
                except Exception as exc:
                    print(f"[daemon] summary comment failed: {exc}")

            if plan_result.is_success():
                self._event_bus.emit_issue_state(issue_id, "completed", mergeable=True)
                print(f"[daemon] {issue_id}: mission succeeded")
                if linear_uid:
                    try:
                        client.update_issue_state(linear_uid, "In Review")
                    except Exception as exc:
                        print(f"[daemon] state update failed: {exc}")
                self._processed.add(issue_id)
            else:
                self._event_bus.emit_issue_state(issue_id, "completed", mergeable=False)
                print(f"[daemon] {issue_id}: mission failed")
                if linear_uid:
                    try:
                        client.update_issue_state(linear_uid, "Ready")
                        print(f"[daemon] {issue_id} → Ready (for retry)")
                    except Exception as exc:
                        print(f"[daemon] state reset failed: {exc}")
                self._release(issue_id)

        except FileNotFoundError as exc:
            print(f"[daemon] {issue_id}: plan not found: {exc}")
            self._release(issue_id)
        except Exception as exc:
            print(f"[daemon] {issue_id}: mission execution failed: {exc}")
            self._release(issue_id)

    def _auto_create_pr(
        self,
        issue_id: str,
        result: RunResult,
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
            gate_policy = self._load_gate_policy()
            should_auto = gate_policy.auto_merge and result.gate.mergeable

            workspace = result.workspace
            gh_svc = GitHubPRService()

            branch = gh_svc._current_branch(workspace)
            if branch and branch != self.config.base_branch:
                check = gh_svc.check_mergeable(
                    workspace,
                    branch=branch,
                    base=self.config.base_branch,
                )
                if not check["mergeable"]:
                    print(f"[daemon] {issue_id}: conflicts detected, attempting rebase")
                    rebased = gh_svc.auto_rebase(
                        workspace,
                        base=self.config.base_branch,
                    )
                    if rebased:
                        print(f"[daemon] {issue_id}: rebase succeeded")
                    else:
                        print(f"[daemon] {issue_id}: rebase failed, attempting AI resolution")
                        resolver = ConflictResolver(
                            builder_adapter=getattr(self, "_builder", None),
                            linear_client=getattr(self._write_back, "_client", None),
                        )
                        conflict_files = cast(list[str], check["conflicting_files"])
                        cr = resolver.resolve(
                            issue=result.issue,
                            workspace=workspace,
                            conflicting_files=conflict_files,
                            base=self.config.base_branch,
                        )
                        if cr.resolved:
                            print(f"[daemon] {issue_id}: conflict resolved via {cr.method}")
                        else:
                            print(
                                f"[daemon] {issue_id}: conflict resolution failed "
                                f"({cr.method}), PR will be created with conflicts"
                            )

            title = f"[SpecOrch] {issue_id}: {result.issue.title}"
            body_lines = [
                f"## SpecOrch: {issue_id}",
                "",
                f"**Mergeable**: {'yes' if result.gate.mergeable else 'no'}",
            ]
            if result.gate.failed_conditions:
                body_lines.append(f"**Blocked**: {', '.join(result.gate.failed_conditions)}")
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
                head_sha = gh_svc._head_sha(workspace)
                if head_sha:
                    self._pr_commits[issue_id] = head_sha

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
        return self._load_gate_policy_for("daemon")

    def _load_gate_policy_for(self, profile: str) -> Any:
        """Load gate policy with the specified profile applied."""
        from spec_orch.services.gate_service import GatePolicy

        policy_path = self.repo_root / "gate.policy.yaml"
        if policy_path.exists():
            base_policy = GatePolicy.from_yaml(policy_path)
        else:
            base_policy = GatePolicy.default()
        return base_policy.with_profile(profile)

    def _triage_issue(
        self,
        client: LinearClient,
        raw_issue: dict[str, Any],
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
                c.get("body", "") and "SpecOrch: Clarification Needed" not in c.get("body", "")
                for c in comments[bot_comment_idx + 1 :]
            )

            if has_reply:
                print(f"[daemon] {issue_id}: user replied, re-entering pool")
                try:
                    client.remove_label(linear_uid, "needs-clarification")
                except Exception as exc:
                    print(f"[daemon] {issue_id}: remove label failed: {exc}")
                self._triaged.discard(issue_id)

    def _check_review_updates(self, client: LinearClient) -> None:
        """Poll In Review PRs for new commits pushed after review fixes.

        When a PR has a new HEAD commit compared to the stored hash,
        the issue is moved from _processed back to the Ready pool so
        the daemon re-evaluates verification + gate on the next cycle.
        """
        if not self._pr_commits:
            return

        try:
            gh = GitHubPRService()
            open_prs = gh.list_open_prs(self.repo_root, base=self.config.base_branch)
        except Exception as exc:
            print(f"[daemon] review-update check error: {exc}")
            return

        pr_by_issue: dict[str, str] = {}
        for pr in open_prs:
            sha = pr.get("headRefOid", "")
            title = pr.get("title", "")
            if sha and title:
                match = _PR_ISSUE_ID_RE.search(title)
                if match:
                    pr_by_issue[match.group(1)] = sha

        for issue_id in list(self._pr_commits):
            if issue_id not in self._processed:
                continue

            stored_sha = self._pr_commits[issue_id]
            current_sha = pr_by_issue.get(issue_id)

            if current_sha is None:
                continue

            if current_sha != stored_sha:
                print(
                    f"[daemon] {issue_id}: new commit detected "
                    f"({stored_sha[:8]} → {current_sha[:8]}), "
                    "re-entering review loop"
                )
                self._processed.discard(issue_id)
                self._pr_commits[issue_id] = current_sha

                try:
                    issues = client.list_issues(
                        team_key=self.config.team_key,
                        filter_state="In Review",
                    )
                    for raw in issues:
                        if raw.get("identifier") == issue_id:
                            client.update_issue_state(
                                raw["id"],
                                self.config.consume_state,
                            )
                            print(f"[daemon] {issue_id} → {self.config.consume_state}")
                            break
                except Exception as exc:
                    print(f"[daemon] {issue_id}: state reset failed: {exc}")

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

    def _get_evidence_context(self) -> str | None:
        """Build LLM context from historical evidence, refreshed each call."""
        try:
            summary = self._evidence_analyzer.analyze()
            if summary.total_runs > 0:
                return self._evidence_analyzer.format_as_llm_context(summary)
        except (OSError, ValueError) as exc:
            print(f"[daemon] evidence analysis skipped: {exc}")
        return None

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        print(f"\n[daemon] received signal {signum}, shutting down gracefully...")
        self._running = False

    def _write_back_result(
        self,
        raw_issue: dict[str, Any],
        result: RunResult,
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

    def _is_hotfix(self, raw_issue: dict[str, Any]) -> bool:
        """Check if an issue has hotfix labels — skip triage if so."""
        labels = raw_issue.get("labels", {}).get("nodes", [])
        issue_labels = {lbl.get("name", "").lower() for lbl in labels}
        return bool(issue_labels & {h.lower() for h in self.config.hotfix_labels})

    def _should_backoff(self, issue_id: str) -> bool:
        """Check if the issue is in a retry backoff period."""
        count = self._retry_counts.get(issue_id, 0)
        if count == 0:
            return False
        lockfile = self._lockdir / f"{issue_id}.retry_at"
        if not lockfile.exists():
            return False
        try:
            retry_at = float(lockfile.read_text().strip())
            return time.time() < retry_at
        except (ValueError, OSError):
            return False

    def _record_failure(
        self,
        issue_id: str,
        error_msg: str,
        client: Any,
        linear_uid: str,
    ) -> None:
        """Record an issue failure, increment retry counter, move to dead letter if max exceeded."""
        count = self._retry_counts.get(issue_id, 0) + 1
        self._retry_counts[issue_id] = count

        if count >= self.config.max_retries:
            print(
                f"[daemon] {issue_id}: max retries ({self.config.max_retries}) "
                "exceeded → dead letter"
            )
            self._dead_letter.add(issue_id)
            self._retry_counts.pop(issue_id, None)
            if linear_uid:
                try:
                    client.add_comment(
                        linear_uid,
                        f"## SpecOrch: Moved to Dead Letter\n\n"
                        f"This issue failed {count} times and has been removed from "
                        f"the automatic execution pool.\n\n"
                        f"**Last error**: `{error_msg[:500]}`\n\n"
                        f"_To retry, remove the `dead-letter` label and move back to Ready._",
                    )
                    client.add_label(linear_uid, "dead-letter")
                except Exception as exc:
                    print(f"[daemon] {issue_id}: dead letter notification failed: {exc}")
        else:
            delay = self.config.retry_base_delay * (2 ** (count - 1))
            retry_at = time.time() + delay
            retry_file = self._lockdir / f"{issue_id}.retry_at"
            retry_file.write_text(str(retry_at))
            print(
                f"[daemon] {issue_id}: attempt {count}/{self.config.max_retries}, retry in {delay}s"
            )

    def resume_in_progress(self, controller: RunController) -> None:
        """Resume issues that were in_progress when the daemon last stopped."""
        if not self._in_progress:
            return
        print(f"[daemon] resuming {len(self._in_progress)} in-progress issues")
        for issue_id in list(self._in_progress):
            try:
                result = controller.advance_to_completion(issue_id)
                print(f"[daemon] resumed {issue_id}: state={result.state.value}")
                self._in_progress.discard(issue_id)
                self._processed.add(issue_id)
            except Exception as exc:
                print(f"[daemon] resume {issue_id} failed: {exc}")
                self._in_progress.discard(issue_id)

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
