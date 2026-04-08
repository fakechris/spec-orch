from __future__ import annotations

import json as _json
import re
import threading
import time
from typing import TYPE_CHECKING, Any

from spec_orch.services.event_bus import Event, EventTopic
from spec_orch.services.github_pr_service import GitHubPRService
from spec_orch.services.linear_client import LinearClient
from spec_orch.services.reaction_engine import (
    ReactionDecision,
    ReactionEngine,
    interpolate_template,
)

if TYPE_CHECKING:
    from spec_orch.services.daemon import _DaemonSharedState

_PR_ISSUE_ID_RE = re.compile(r"\[SpecOrch\]\s+([A-Za-z0-9_-]+):")


class DaemonReactionProcessor:
    """Handles clarification replies, review updates, and reaction side-channel.

    Owns auto-merge PRs, requeue, CI failure comments, and reaction mark tracking.
    """

    def __init__(
        self,
        *,
        config: Any,
        repo_root: Any,
        reaction_engine: ReactionEngine,
        event_bus: Any,
        state_lock: threading.Lock,
        shared_state: _DaemonSharedState,
        host: Any = None,
    ) -> None:
        self._config = config
        self._repo_root = repo_root
        self.__reaction_engine = reaction_engine
        self._event_bus = event_bus
        self._state_lock = state_lock
        self._shared = shared_state
        self._host = host

    @property
    def _reaction_engine(self) -> ReactionEngine:
        """Allow tests to monkey-patch daemon._reaction_engine and have it take effect."""
        if self._host is not None:
            engine = getattr(self._host, "_reaction_engine", None)
            if engine is not None:
                return engine  # type: ignore[no-any-return]
        return self.__reaction_engine

    @_reaction_engine.setter
    def _reaction_engine(self, value: ReactionEngine) -> None:
        self.__reaction_engine = value

    # -- public API --

    def check_clarification_replies(self, client: LinearClient) -> None:
        """Check for user replies on issues waiting for clarification.

        When a user replies, remove the needs-clarification label so the
        issue re-enters the Ready candidate pool on the next poll.
        """
        try:
            waiting = client.list_issues(
                team_key=self._config.team_key,
                filter_state=self._config.consume_state,
                filter_labels=["needs-clarification"],
                exclude_parents=self._config.skip_parents,
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
                self._shared.triaged.discard(issue_id)

    def check_review_updates(self, client: LinearClient) -> None:
        """Poll In Review PRs for new commits pushed after review fixes."""
        if not self._shared.pr_commits:
            return

        try:
            gh = GitHubPRService()
            open_prs = gh.list_open_prs(self._repo_root, base=self._config.base_branch)
        except Exception as exc:
            print(f"[daemon] review-update check error: {exc}")
            return

        pr_meta_by_issue: dict[str, dict[str, Any]] = {}
        for pr in open_prs:
            sha = pr.get("headRefOid", "")
            title = pr.get("title", "")
            pr_number = pr.get("number")
            if sha and title:
                match = _PR_ISSUE_ID_RE.search(title)
                if match:
                    pr_meta_by_issue[match.group(1)] = {"sha": sha, "number": pr_number}

        for issue_id in list(self._shared.pr_commits):
            if issue_id not in self._shared.processed:
                continue

            stored_sha = self._shared.pr_commits[issue_id]
            current = pr_meta_by_issue.get(issue_id)
            current_sha = current.get("sha") if current else None

            if current_sha is None:
                continue

            if current_sha != stored_sha:
                print(
                    f"[daemon] {issue_id}: new commit detected "
                    f"({stored_sha[:8]} -> {current_sha[:8]}), "
                    "re-entering review loop"
                )
                self._shared.processed.discard(issue_id)
                self._shared.pr_commits[issue_id] = current_sha

                try:
                    issues = client.list_issues(
                        team_key=self._config.team_key,
                        filter_state="In Review",
                    )
                    for raw in issues:
                        if raw.get("identifier") == issue_id:
                            client.update_issue_state(
                                raw["id"],
                                self._config.consume_state,
                            )
                            print(f"[daemon] {issue_id} -> {self._config.consume_state}")
                            break
                except Exception as exc:
                    print(f"[daemon] {issue_id}: state reset failed: {exc}")

        self._run_reactions(client, gh, pr_meta_by_issue)

    # -- reaction engine --

    def _run_reactions(
        self,
        client: LinearClient,
        gh: GitHubPRService,
        pr_meta_by_issue: dict[str, dict[str, Any]],
    ) -> None:
        # Pre-fetch In Review issues once to build a UID lookup, avoiding
        # N+1 list_issues calls inside individual reaction handlers.
        linear_uid_map: dict[str, str] = {}
        try:
            issues = client.list_issues(team_key=self._config.team_key, filter_state="In Review")
            for raw in issues:
                ident = raw.get("identifier", "")
                uid = raw.get("id", "")
                if ident and uid:
                    linear_uid_map[ident] = uid
        except Exception as exc:
            print(f"[daemon] pre-fetch In Review issues failed: {exc}")

        for issue_id, meta in pr_meta_by_issue.items():
            pr_number = meta.get("number")
            if not isinstance(pr_number, int):
                continue
            signal = gh.get_pr_signal(self._repo_root, pr_number)
            if not signal:
                continue
            tpl_ctx = self._reaction_template_context(
                issue_id=issue_id,
                pr_number=pr_number,
                sha=str(meta.get("sha", "")),
                signal=signal,
            )
            decisions = self._reaction_engine.evaluate(signal)
            for decision in decisions:
                mark = f"{issue_id}:{meta.get('sha', '')}:{decision.rule_name}:{decision.action}"
                if mark in self._shared.reaction_marks:
                    continue
                consumed = self._apply_reaction_decision(
                    client,
                    gh,
                    issue_id=issue_id,
                    pr_number=pr_number,
                    decision=decision,
                    tpl_ctx=tpl_ctx,
                    linear_uid=linear_uid_map.get(issue_id),
                )
                if consumed:
                    self._shared.reaction_marks.add(mark)

    def _reaction_template_context(
        self,
        *,
        issue_id: str,
        pr_number: int,
        sha: str,
        signal: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "issue_id": issue_id,
            "pr_number": pr_number,
            "sha": sha,
            "consume_state": self._config.consume_state,
            "review_decision": str(signal.get("review_decision", "") or ""),
            "merge_state": str(signal.get("merge_state", "") or ""),
            "checks_passed": signal.get("checks_passed", False),
            "checks_failed": signal.get("checks_failed", False),
            "mergeable": signal.get("mergeable", False),
        }

    def _append_reaction_trace(self, record: dict[str, Any]) -> None:
        """Append JSONL trace for replay / evaluation."""
        trace_path = self._repo_root / ".spec_orch" / "reactions_trace.jsonl"
        try:
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            with trace_path.open("a", encoding="utf-8") as fh:
                fh.write(_json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            print(f"[daemon] reaction trace write failed: {exc}")
        try:
            self._event_bus.publish(
                Event(
                    topic=EventTopic.SYSTEM,
                    payload={"kind": "reaction.executed", **record},
                )
            )
        except Exception as exc:
            print(f"[daemon] reaction event publish failed: {exc}")

    def _apply_reaction_decision(
        self,
        client: LinearClient,
        gh: GitHubPRService,
        *,
        issue_id: str,
        pr_number: int,
        decision: ReactionDecision,
        tpl_ctx: dict[str, Any],
        linear_uid: str | None = None,
    ) -> bool:
        """Execute one reaction; return True if the mark should be consumed."""
        base_record: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "issue_id": issue_id,
            "pr_number": pr_number,
            "rule_name": decision.rule_name,
            "action": decision.action,
            "reason": decision.reason,
        }

        if decision.action == "noop":
            rec = {**base_record, "result": "noop"}
            self._append_reaction_trace(rec)
            return True

        if decision.action == "auto_merge":
            method = str(decision.params.get("merge_method", "squash")).strip() or "squash"
            merged = gh.merge_pr(
                self._repo_root,
                pr_number=pr_number,
                method=method,
            )
            rec = {
                **base_record,
                "result": "merged" if merged else "merge_failed",
                "merge_method": method,
            }
            self._append_reaction_trace(rec)
            if merged:
                self._mark_issue_done_if_in_review(client, issue_id)
                print(f"[daemon] reaction auto-merge applied for {issue_id}")
            return merged

        if decision.action == "requeue_ready":
            ok = self._requeue_issue_to_consume_state(client, issue_id)
            rec = {**base_record, "result": "requeued" if ok else "requeue_failed"}
            self._append_reaction_trace(rec)
            if ok:
                print(f"[daemon] reaction requeue -> {self._config.consume_state} for {issue_id}")
            return ok

        if decision.action in {"comment_ci_failed", "comment_changes_requested"}:
            ok = self._comment_reaction(client, issue_id, decision, tpl_ctx, linear_uid=linear_uid)
            rec = {**base_record, "result": "commented" if ok else "comment_failed"}
            self._append_reaction_trace(rec)
            return ok

        rec = {**base_record, "result": "unknown_action"}
        self._append_reaction_trace(rec)
        return False

    def _requeue_issue_to_consume_state(self, client: LinearClient, issue_id: str) -> bool:
        """Move an In Review issue back to consume_state."""
        try:
            issues = client.list_issues(team_key=self._config.team_key, filter_state="In Review")
            for raw in issues:
                if raw.get("identifier") == issue_id and raw.get("id"):
                    client.update_issue_state(raw["id"], self._config.consume_state)
                    return True
        except Exception as exc:
            print(f"[daemon] {issue_id}: requeue reaction failed: {exc}")
        return False

    def _mark_issue_done_if_in_review(self, client: LinearClient, issue_id: str) -> None:
        try:
            issues = client.list_issues(team_key=self._config.team_key, filter_state="In Review")
            for raw in issues:
                if raw.get("identifier") == issue_id and raw.get("id"):
                    client.update_issue_state(raw["id"], "Done")
                    break
        except Exception as exc:
            print(f"[daemon] {issue_id}: failed to set Done after auto-merge: {exc}")

    def _comment_reaction(
        self,
        client: LinearClient,
        issue_id: str,
        decision: ReactionDecision,
        tpl_ctx: dict[str, Any],
        *,
        linear_uid: str | None = None,
    ) -> bool:
        """Post a Linear comment from rule params or built-in defaults."""
        action = decision.action
        params = decision.params
        template_key = "comment_template"
        if action == "comment_ci_failed":
            default_body = (
                "## SpecOrch Reaction: CI failed\n\n"
                "Detected failed checks on the PR. Please push a fix commit; "
                "daemon will re-enter the review loop automatically."
            )
        else:
            default_body = (
                "## SpecOrch Reaction: Changes requested\n\n"
                "Detected `CHANGES_REQUESTED` review state. Please address feedback "
                "and push updates; daemon will pick up new commits."
            )
        raw_tpl = params.get(template_key)
        if isinstance(raw_tpl, str) and raw_tpl.strip():
            body = interpolate_template(raw_tpl, tpl_ctx)
        else:
            body = default_body

        try:
            # Use pre-resolved linear_uid to avoid an N+1 list_issues call.
            if linear_uid:
                client.add_comment(linear_uid, body)
                return True
            issues = client.list_issues(team_key=self._config.team_key, filter_state="In Review")
            for raw in issues:
                if raw.get("identifier") != issue_id or not raw.get("id"):
                    continue
                client.add_comment(raw["id"], body)
                return True
        except Exception as exc:
            print(f"[daemon] {issue_id}: reaction comment failed: {exc}")
        return False
