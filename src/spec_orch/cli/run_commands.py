from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import IO

import typer

from spec_orch.cli import app
from spec_orch.cli._helpers import (
    _linear_writeback_on_pr,
    _make_controller,
)
from spec_orch.services.workspace_service import WorkspaceService


@app.command("run-issue")
def run_issue(
    issue_id: str,
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
    codex_executable: str = typer.Option("codex", "--codex-executable"),
    pi_executable: str = typer.Option("pi", "--pi-executable"),
    live: bool = typer.Option(
        False, "--live", help="Stream builder events to stderr in real-time."
    ),
    source: str = typer.Option(
        "fixture", "--source", "-s", help="Issue source: fixture or linear."
    ),
) -> None:
    """Run one issue through the MVP pipeline."""
    live_stream: IO[str] | None = sys.stderr if live else None
    controller = _make_controller(
        repo_root=repo_root,
        codex_executable=codex_executable,
        live_stream=live_stream,
        source=source,
    )
    result = controller.run_issue(issue_id)
    typer.echo(
        " ".join(
            [
                f"issue={result.issue.issue_id}",
                f"workspace={result.workspace}",
                f"mergeable={result.gate.mergeable}",
                f"blocked={','.join(result.gate.failed_conditions) or 'none'}",
            ]
        )
    )


@app.command("accept-issue")
def accept_issue(
    issue_id: str,
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
    accepted_by: str = typer.Option(..., "--accepted-by"),
    codex_executable: str = typer.Option("codex", "--codex-executable"),
    pi_executable: str = typer.Option("pi", "--pi-executable"),
) -> None:
    """Record human acceptance — shows spec compliance checklist first."""
    from spec_orch.services.deviation_service import (
        detect_deviations,
        write_deviations,
    )
    from spec_orch.services.spec_snapshot_service import read_spec_snapshot

    ws = WorkspaceService(repo_root=Path(repo_root))
    workspace = ws.issue_workspace_path(issue_id)

    snapshot = read_spec_snapshot(workspace)
    if snapshot:
        typer.echo("--- Spec Compliance Checklist ---")
        for i, ac in enumerate(snapshot.issue.acceptance_criteria, 1):
            typer.echo(f"  [{i}] {ac}")
        deviations = detect_deviations(workspace=workspace, snapshot=snapshot)
        if deviations:
            typer.echo(f"\n--- {len(deviations)} Deviation(s) Detected ---")
            for d in deviations:
                typer.echo(f"  [{d.severity}] {d.description}")
            write_deviations(workspace, deviations)
        else:
            typer.echo("\nNo deviations detected.")

    controller = _make_controller(repo_root=repo_root, codex_executable=codex_executable)
    result = controller.accept_issue(issue_id, accepted_by=accepted_by)
    typer.echo(
        " ".join(
            [
                f"issue={result.issue.issue_id}",
                f"workspace={result.workspace}",
                f"mergeable={result.gate.mergeable}",
                f"blocked={','.join(result.gate.failed_conditions) or 'none'}",
                f"accepted_by={accepted_by}",
            ]
        )
    )


@app.command("review-issue")
def review_issue(
    issue_id: str,
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
    verdict: str = typer.Option(..., "--verdict"),
    reviewed_by: str = typer.Option(..., "--reviewed-by"),
    codex_executable: str = typer.Option("codex", "--codex-executable"),
    pi_executable: str = typer.Option("pi", "--pi-executable"),
) -> None:
    """Record review verdict for an existing issue run."""
    controller = _make_controller(repo_root=repo_root, codex_executable=codex_executable)
    result = controller.review_issue(
        issue_id,
        verdict=verdict,
        reviewed_by=reviewed_by,
    )
    typer.echo(
        " ".join(
            [
                f"issue={result.issue.issue_id}",
                f"workspace={result.workspace}",
                f"mergeable={result.gate.mergeable}",
                f"blocked={','.join(result.gate.failed_conditions) or 'none'}",
                f"review_verdict={verdict}",
                f"reviewed_by={reviewed_by}",
            ]
        )
    )


@app.command("rerun")
def rerun_issue(
    issue_id: str,
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
    codex_executable: str = typer.Option("codex", "--codex-executable"),
) -> None:
    """Re-run verification and gate on an existing issue workspace."""
    if Path(issue_id).name != issue_id:
        typer.echo(f"Invalid issue_id: {issue_id}")
        raise typer.Exit(1)
    controller = _make_controller(repo_root=repo_root, codex_executable=codex_executable)
    result = controller.rerun_issue(issue_id)
    typer.echo(
        " ".join(
            [
                f"issue={result.issue.issue_id}",
                f"workspace={result.workspace}",
                f"mergeable={result.gate.mergeable}",
                f"blocked={','.join(result.gate.failed_conditions) or 'none'}",
            ]
        )
    )


@app.command("status")
def status_issue(
    ctx: typer.Context,
    issue_id: str | None = typer.Argument(None),
    all_issues: bool = typer.Option(False, "--all", "-a"),
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
) -> None:
    """Show the current status of an issue run."""
    from spec_orch.cli._helpers import _issue_sort_key

    ws = WorkspaceService(repo_root=Path(repo_root))
    if all_issues:
        if issue_id:
            ctx.fail("Do not provide ISSUE_ID with --all.")
        workspace_root = (
            Path(repo_root) / ".worktrees"
            if ws._is_git_repository()
            else Path(repo_root) / ".spec_orch_runs"
        )
        if not workspace_root.exists():
            typer.echo("no issues found")
            return

        rows: list[tuple[str, str, str, str]] = []
        sorted_dirs = sorted(
            workspace_root.iterdir(),
            key=lambda path: _issue_sort_key(path.name),
        )
        for workspace in sorted_dirs:
            if not workspace.is_dir():
                continue

            report_path = workspace / "report.json"
            if report_path.exists():
                report = json.loads(report_path.read_text())
                state = str(report.get("state", "in_progress"))
                mergeable = str(report.get("mergeable", False))
                title = str(report.get("title", workspace.name))
            else:
                state = "in_progress"
                mergeable = "False"
                title = workspace.name
            rows.append((workspace.name, state, mergeable, title))

        if not rows:
            typer.echo("no issues found")
            return

        headers = ("Issue ID", "State", "Mergeable", "Title")
        widths = [
            max(len(header), *(len(row[index]) for row in rows))
            for index, header in enumerate(headers)
        ]
        typer.echo(_format_status_table_row(headers, widths))
        typer.echo(_format_status_table_row(tuple("-" * width for width in widths), widths))
        for row in rows:
            typer.echo(_format_status_table_row(row, widths))
        return

    if not issue_id:
        ctx.fail("Missing argument 'ISSUE_ID'.")
    workspace = ws.issue_workspace_path(issue_id)
    if not workspace.exists():
        typer.echo(f"no run found for {issue_id}")
        raise typer.Exit(1)
    report_path = workspace / "report.json"
    if not report_path.exists():
        typer.echo(f"issue={issue_id} workspace={workspace} status=in_progress")
        return
    report = json.loads(report_path.read_text())
    blocked = ",".join(report.get("failed_conditions", [])) or "none"
    flow_type = report.get("claimed_flow", "unknown")
    builder_adapter = report.get("builder", {}).get("adapter", "unknown")
    typer.echo(
        f"issue={issue_id} workspace={workspace} "
        f"mergeable={report.get('mergeable', False)} blocked={blocked} "
        f"flow={flow_type} builder={builder_adapter}"
    )


def _format_status_table_row(values: tuple[str, ...], widths: list[int]) -> str:
    return "  ".join(value.ljust(width) for value, width in zip(values, widths, strict=True))


@app.command("explain")
def explain_issue(
    issue_id: str,
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
) -> None:
    """Print the explain.md report for an issue."""
    ws = WorkspaceService(repo_root=Path(repo_root))
    workspace = ws.issue_workspace_path(issue_id)
    explain_path = workspace / "explain.md"
    if not explain_path.exists():
        typer.echo(f"no explain report found for {issue_id}")
        raise typer.Exit(1)
    typer.echo(explain_path.read_text())


@app.command("advance")
def advance_issue(
    issue_id: str,
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
    codex_executable: str = typer.Option("codex", "--codex-executable"),
    live: bool = typer.Option(False, "--live"),
    source: str = typer.Option(
        "fixture", "--source", "-s", help="Issue source: fixture or linear."
    ),
) -> None:
    """Advance an issue to the next state in the lifecycle."""
    live_stream: IO[str] | None = sys.stderr if live else None
    controller = _make_controller(
        repo_root=repo_root,
        codex_executable=codex_executable,
        live_stream=live_stream,
        source=source,
    )
    result = controller.advance(issue_id)
    typer.echo(
        " ".join(
            [
                f"issue={result.issue.issue_id}",
                f"state={result.state.value}",
                f"mergeable={result.gate.mergeable}",
                f"blocked={','.join(result.gate.failed_conditions) or 'none'}",
            ]
        )
    )


@app.command("run")
def run_full(
    issue_id: str,
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
    codex_executable: str = typer.Option("codex", "--codex-executable"),
    live: bool = typer.Option(False, "--live"),
    source: str = typer.Option(
        "fixture",
        "--source",
        "-s",
        help="Issue source: fixture or linear.",
    ),
    auto_pr: bool = typer.Option(
        False,
        "--auto-pr",
        help="Automatically create a GitHub PR on completion.",
    ),
    auto_merge: bool = typer.Option(
        False,
        "--auto-merge",
        help="Auto-merge if gate passes (implies --auto-pr).",
    ),
    gate_profile: str = typer.Option(
        "",
        "--gate-profile",
        help="Gate profile to apply (e.g. daemon, ci).",
    ),
    base: str = typer.Option("main", "--base", "-b", help="Base branch for PR."),
    flow: str = typer.Option(
        "",
        "--flow",
        help="Override flow type: full, standard, or hotfix.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Run an issue through the full pipeline in one shot.

    Drives the issue from DRAFT all the way to GATE_EVALUATED (or FAILED),
    using LLM self-answer for blocking questions when a planner is configured.
    Optionally creates a GitHub PR and writes back to Linear.
    """
    from spec_orch.domain.models import RunState

    if auto_merge:
        auto_pr = True
    live_stream: IO[str] | None = sys.stderr if live else None
    controller = _make_controller(
        repo_root=repo_root,
        codex_executable=codex_executable,
        live_stream=live_stream,
        source=source,
    )
    from spec_orch.domain.models import FlowType as _FlowType

    resolved_flow = _FlowType(flow) if flow else None
    if not json_output:
        typer.echo(f"running full pipeline for {issue_id}...")
    result = controller.advance_to_completion(issue_id, flow_type=resolved_flow)

    failed: list[str] = list(result.gate.failed_conditions)
    run_summary: dict[str, object] = {
        "issue_id": result.issue.issue_id,
        "state": result.state.value,
        "mergeable": result.gate.mergeable,
        "failed_conditions": failed,
    }

    if not json_output:
        typer.echo(
            " ".join(
                [
                    f"issue={result.issue.issue_id}",
                    f"state={result.state.value}",
                    f"mergeable={result.gate.mergeable}",
                    f"blocked={','.join(failed) or 'none'}",
                ]
            )
        )

    if auto_pr and result.state == RunState.GATE_EVALUATED:
        from spec_orch.services.github_pr_service import GitHubPRService

        workspace = result.workspace
        data = json.loads((workspace / "report.json").read_text())
        gate_verdict = result.gate
        gh_svc = GitHubPRService()
        title = f"[SpecOrch] {issue_id}: {data.get('title', issue_id)}"
        body_lines = [
            f"## SpecOrch: {issue_id}",
            "",
            f"**Mergeable**: {'yes' if result.gate.mergeable else 'no'}",
        ]
        if result.gate.failed_conditions:
            body_lines.append(f"**Blocked**: {', '.join(result.gate.failed_conditions)}")
        explain_path = workspace / "explain.md"
        if explain_path.exists():
            text = explain_path.read_text().strip()
            if len(text) > 3000:
                text = text[:3000] + "\n\n*(truncated)*"
            body_lines.extend(["", "### Explain", "", text])
        body_lines.extend(["", f"Closes {issue_id}"])

        should_merge = auto_merge and result.gate.mergeable
        try:
            pr_url = gh_svc.create_pr(
                workspace=workspace,
                title=title,
                body="\n".join(body_lines),
                base=base,
                draft=not should_merge,
            )
            if pr_url:
                if not json_output:
                    typer.echo(f"PR created: {pr_url}")
                run_summary["pr_url"] = pr_url
                gh_svc.set_gate_status(workspace=workspace, gate=gate_verdict)

                if should_merge:
                    merged = gh_svc.merge_pr(workspace, method="squash")
                    run_summary["auto_merge"] = merged
                    if not json_output:
                        if merged:
                            typer.echo("auto-merge: enabled (waiting for checks)")
                        else:
                            typer.echo("auto-merge: could not enable")

                _linear_writeback_on_pr(
                    issue_id,
                    data,
                    pr_url,
                    gate_verdict,
                    Path(repo_root),
                )
            else:
                if not json_output:
                    typer.echo("could not create PR (branch may be main)")
                run_summary["pr_error"] = "could not create PR (branch may be main)"
        except RuntimeError as exc:
            if not json_output:
                typer.echo(f"auto-PR failed: {exc}")
            run_summary["pr_error"] = str(exc)

    if json_output:
        typer.echo(json.dumps(run_summary, indent=2))


@app.command("diff")
def diff_issue(
    issue_id: str,
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
) -> None:
    """Show git diff --stat for an issue worktree."""
    ws = WorkspaceService(repo_root=Path(repo_root))
    workspace = ws.issue_workspace_path(issue_id)
    if not workspace.exists():
        typer.echo(f"no workspace found for {issue_id}")
        raise typer.Exit(1)
    if not (workspace / ".git").exists():
        typer.echo("workspace is not a git worktree")
        raise typer.Exit(1)
    result = subprocess.run(
        ["git", "diff", "--stat", "main"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    typer.echo(result.stdout or "(no changes)")


@app.command("cherry-pick")
def cherry_pick_issue(
    issue_id: str,
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
) -> None:
    """Cherry-pick worktree commits into the current branch."""
    ws = WorkspaceService(repo_root=Path(repo_root))
    workspace = ws.issue_workspace_path(issue_id)
    if not workspace.exists() or not (workspace / ".git").exists():
        typer.echo(f"no git worktree found for {issue_id}")
        raise typer.Exit(1)
    commits_result = subprocess.run(
        ["git", "log", "main..HEAD", "--format=%H", "--reverse"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    commits = [c.strip() for c in commits_result.stdout.strip().splitlines() if c.strip()]
    if not commits:
        typer.echo("no commits to cherry-pick")
        return
    for commit in commits:
        pick = subprocess.run(
            ["git", "cherry-pick", commit],
            cwd=Path(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if pick.returncode != 0:
            typer.echo(f"cherry-pick failed at {commit}: {pick.stderr.strip()}")
            typer.echo("resolve conflicts, then run: git cherry-pick --continue")
            raise typer.Exit(1)
        typer.echo(f"cherry-picked {commit[:12]}")
    typer.echo(f"cherry-picked {len(commits)} commit(s) from {issue_id}")


@app.command("review-pr")
def review_pr(
    issue_id: str = typer.Argument(default="", help="Issue ID (optional, auto-detects PR)."),
    pr_number: int | None = typer.Option(None, "--pr", help="PR number."),
    repo_root: Path = typer.Option(".", "--repo-root", "-r"),
) -> None:
    """Auto-review a PR: fetch review comments, map to Findings, evaluate gate."""
    from spec_orch.services.github_review_adapter import GitHubReviewAdapter

    ws = WorkspaceService(repo_root=Path(repo_root))
    workspace = ws.issue_workspace_path(issue_id) if issue_id else Path(repo_root)

    adapter = GitHubReviewAdapter()
    summary, meta = adapter.auto_review(workspace=workspace, pr_number=pr_number)

    typer.echo(f"verdict: {summary.verdict}")
    typer.echo(f"reviewed_by: {summary.reviewed_by}")
    typer.echo(f"findings: {len(meta.findings)} total, {len(meta.blocking_unresolved)} blocking")

    for f in meta.findings:
        icon = "!" if f.severity == "blocking" else "~"
        loc = f"{f.file_path}:{f.line}" if f.file_path else "(general)"
        typer.echo(f"  [{icon}] [{f.source}] {loc}: {f.description[:80]}")


@app.command("create-pr")
def create_pr(
    issue_id: str,
    repo_root: Path = typer.Option(".", "--repo-root", "-r"),
    base: str = typer.Option("main", "--base", "-b", help="Base branch for the PR."),
    no_draft: bool = typer.Option(False, "--no-draft", help="Create as ready (not draft)."),
) -> None:
    """Create a GitHub PR for an issue worktree and set gate status."""
    from spec_orch.services.github_pr_service import GitHubPRService

    ws = WorkspaceService(repo_root=Path(repo_root))
    workspace = ws.issue_workspace_path(issue_id)
    if not workspace.exists():
        typer.echo(f"no workspace found for {issue_id}")
        raise typer.Exit(1)

    result_file = workspace / "report.json"
    if not result_file.exists():
        typer.echo(f"no run found for {issue_id}")
        raise typer.Exit(1)

    data = json.loads(result_file.read_text())
    mergeable = data.get("mergeable", False)
    failed = data.get("failed_conditions", [])

    from spec_orch.domain.models import GateVerdict

    gate_verdict = GateVerdict(mergeable=mergeable, failed_conditions=failed)

    gh_svc = GitHubPRService()

    title = f"[SpecOrch] {issue_id}: {data.get('title', issue_id)}"
    body_lines = [
        f"## SpecOrch: {issue_id}",
        "",
        f"**Mergeable**: {'yes' if mergeable else 'no'}",
    ]
    if failed:
        body_lines.append(f"**Blocked**: {', '.join(failed)}")

    explain_path = workspace / "explain.md"
    if explain_path.exists():
        text = explain_path.read_text().strip()
        if len(text) > 3000:
            text = text[:3000] + "\n\n*(truncated)*"
        body_lines.extend(["", "### Explain", "", text])

    body_lines.extend(["", f"Closes {issue_id}"])

    try:
        pr_url = gh_svc.create_pr(
            workspace=workspace,
            title=title,
            body="\n".join(body_lines),
            base=base,
            draft=not no_draft,
        )
        if pr_url:
            typer.echo(f"PR created: {pr_url}")
        else:
            typer.echo("could not create PR (branch may be main)")
            raise typer.Exit(1)
    except RuntimeError as exc:
        typer.echo(f"PR creation failed: {exc}")
        raise typer.Exit(1) from exc

    gh_svc.set_gate_status(workspace=workspace, gate=gate_verdict)
    typer.echo(f"gate status set: {'success' if mergeable else 'failure'}")

    _linear_writeback_on_pr(issue_id, data, pr_url, gate_verdict, Path(repo_root))


@app.command("run-plan")
def run_plan(
    mission_id: str = typer.Argument(..., help="Mission ID to execute."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
    max_concurrency: int = typer.Option(3, "--concurrency", "-j", help="Max parallel packets."),
    codex_executable: str = typer.Option("codex", "--codex-executable"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without executing."),
    full_pipeline: bool = typer.Option(
        False,
        "--full-pipeline",
        help="Run build → verify → gate per packet.",
    ),
) -> None:
    """Execute a Mission's plan with parallel wave execution."""
    from spec_orch.domain.models import ParallelConfig
    from spec_orch.services.cancellation_handler import CancellationHandler
    from spec_orch.services.parallel_logging import configure_parallel_logging
    from spec_orch.services.parallel_run_controller import ParallelRunController
    from spec_orch.services.promotion_service import load_plan

    plan_path = Path(repo_root) / "docs/specs" / mission_id / "plan.json"
    if not plan_path.exists():
        typer.echo(f"no plan found for {mission_id}")
        raise typer.Exit(1)

    plan = load_plan(plan_path)
    total = sum(len(w.work_packets) for w in plan.waves)
    typer.echo(
        f"plan: {plan.plan_id} | {len(plan.waves)} waves, "
        f"{total} packets | concurrency={max_concurrency}"
    )
    for w in plan.waves:
        typer.echo(f"  wave {w.wave_number}: {len(w.work_packets)} packets — {w.description}")
        for p in w.work_packets:
            typer.echo(f"    [{p.run_class}] {p.packet_id}: {p.title}")

    if dry_run:
        typer.echo("\n(dry run — not executing)")
        return

    config = ParallelConfig(max_concurrency=max_concurrency)
    configure_parallel_logging()

    import asyncio

    cancel_event = asyncio.Event()
    handler = CancellationHandler(cancel_event)
    handler.install()

    try:
        from spec_orch.domain.protocols import PacketExecutor

        pkt_exec: PacketExecutor
        if full_pipeline:
            from spec_orch.services.adapter_factory import load_verification_commands
            from spec_orch.services.packet_executor import FullPipelinePacketExecutor

            pkt_exec = FullPipelinePacketExecutor(
                codex_bin=codex_executable,
                workspace=str(Path(repo_root).resolve()),
                verify_commands=load_verification_commands(Path(repo_root)),
            )
        else:
            from spec_orch.services.packet_executor import SubprocessPacketExecutor

            pkt_exec = SubprocessPacketExecutor(
                codex_bin=codex_executable,
                workspace=str(Path(repo_root).resolve()),
            )

        ctrl = ParallelRunController(
            repo_root=Path(repo_root),
            config=config,
            codex_bin=codex_executable,
        )
        ctrl._packet_executor = pkt_exec
        ctrl._wave_executor._packet_executor = pkt_exec
        result = ctrl.run_plan(plan, cancel_event=cancel_event)
    finally:
        handler.uninstall()

    for wr in result.wave_results:
        status = "ok" if wr.all_succeeded else "FAILED"
        typer.echo(f"\nwave {wr.wave_id}: {status}")
        for pr in wr.packet_results:
            icon = "✓" if pr.exit_code == 0 else "✗"
            typer.echo(f"  {icon} {pr.packet_id} (exit={pr.exit_code}, {pr.duration_seconds:.1f}s)")

    typer.echo(
        f"\ntotal: {result.total_duration:.1f}s | {'SUCCESS' if result.is_success() else 'FAILED'}"
    )

    if not result.is_success():
        raise typer.Exit(1)
