from __future__ import annotations

import importlib.metadata
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any
from uuid import uuid4

import typer

from spec_orch.domain.models import Decision, Finding, Question, RunState
from spec_orch.services.codex_exec_builder_adapter import CodexExecBuilderAdapter
from spec_orch.services.finding_store import (
    append_finding,
    fingerprint_from,
    load_findings,
    resolve_finding,
)
from spec_orch.services.fixture_issue_source import FixtureIssueSource
from spec_orch.services.run_controller import RunController
from spec_orch.services.spec_snapshot_service import (
    create_initial_snapshot,
    read_spec_snapshot,
    write_spec_snapshot,
)
from spec_orch.services.workspace_service import WorkspaceService

app = typer.Typer(help="SpecOrch MVP prototype CLI.")
findings_app = typer.Typer()
app.add_typer(findings_app, name="findings")
questions_app = typer.Typer()
app.add_typer(questions_app, name="questions")
spec_app = typer.Typer()
app.add_typer(spec_app, name="spec")
config_app = typer.Typer()
app.add_typer(config_app, name="config")
mission_app = typer.Typer()
app.add_typer(mission_app, name="mission")
discuss_app = typer.Typer()
app.add_typer(discuss_app, name="discuss")


def _resolve_version() -> str:
    try:
        return importlib.metadata.version("spec-orch")
    except importlib.metadata.PackageNotFoundError:
        return "dev"


def _version_callback(value: bool) -> None:
    if not value:
        return
    typer.echo(_resolve_version())
    raise typer.Exit()


@app.callback()
def cli(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the spec-orch version and exit.",
    ),
) -> None:
    """SpecOrch MVP prototype CLI."""


@app.command("plan-to-spec")
def plan_to_spec(
    plan_path: Path = typer.Argument(..., help="Path to the plan markdown file."),
    issue_id: str = typer.Option(..., "--issue-id", "-i", help="Issue ID for the fixture."),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output path (default: fixtures/issues/{issue-id}.json).",
    ),
    edit: bool = typer.Option(False, "--edit", help="Open in $EDITOR before saving."),
    builder_prompt_from: Path | None = typer.Option(
        None,
        "--builder-prompt-from",
        "-p",
        help="Override builder_prompt from file.",
    ),
    no_builder: bool = typer.Option(
        False, "--no-builder", help="Set builder_prompt to null."
    ),
) -> None:
    """Convert a plan markdown file into an issue fixture JSON file."""
    from spec_orch.services.fixture_issue_source import _VALID_ISSUE_ID_RE
    from spec_orch.services.plan_parser import parse_plan
    from spec_orch.services.spec_generator import generate_fixture

    if not plan_path.exists():
        typer.echo(f"plan not found: {plan_path}")
        raise typer.Exit(1)
    if not _VALID_ISSUE_ID_RE.match(issue_id):
        typer.echo(f"Invalid issue_id: {issue_id!r}")
        raise typer.Exit(1)

    fixture = generate_fixture(parse_plan(plan_path), issue_id)

    if builder_prompt_from is not None:
        if not builder_prompt_from.exists():
            typer.echo(f"builder prompt file not found: {builder_prompt_from}")
            raise typer.Exit(1)
        fixture["builder_prompt"] = builder_prompt_from.read_text(encoding="utf-8")
    if no_builder:
        fixture["builder_prompt"] = None

    if edit:
        fixture = _edit_fixture_json(fixture)

    output_path = output or Path("fixtures") / "issues" / f"{issue_id}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(fixture, indent=2) + "\n"
    output_path.write_text(rendered, encoding="utf-8")
    typer.echo(rendered)


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

    controller = _make_controller(
        repo_root=repo_root, codex_executable=codex_executable
    )
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
    controller = _make_controller(
        repo_root=repo_root, codex_executable=codex_executable
    )
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
    controller = _make_controller(
        repo_root=repo_root, codex_executable=codex_executable
    )
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
    typer.echo(
        f"issue={issue_id} workspace={workspace} "
        f"mergeable={report.get('mergeable', False)} blocked={blocked}"
    )


def _issue_sort_key(issue_id: str) -> list[int | str]:
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", issue_id)
        if part
    ]


def _format_status_table_row(
    values: tuple[str, ...], widths: list[int]
) -> str:
    return "  ".join(
        value.ljust(width)
        for value, width in zip(values, widths, strict=True)
    )


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


@findings_app.command("list")
def list_findings(
    issue_id: str,
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
) -> None:
    """List persisted findings for an issue workspace."""
    workspace = WorkspaceService(repo_root=Path(repo_root)).issue_workspace_path(issue_id)
    findings = load_findings(workspace)
    if not findings:
        typer.echo("no findings")
        return
    for finding in findings:
        typer.echo(
            " ".join(
                [
                    f"id={finding.id}",
                    f"source={finding.source}",
                    f"severity={finding.severity}",
                    f"scope={finding.scope}",
                    f"resolved={finding.resolved}",
                    f"description={finding.description}",
                ]
            )
        )


@findings_app.command("resolve")
def resolve_issue_finding(
    issue_id: str,
    finding_id: str,
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
) -> None:
    """Resolve a persisted finding by ID."""
    workspace = WorkspaceService(repo_root=Path(repo_root)).issue_workspace_path(issue_id)
    if resolve_finding(workspace, finding_id):
        typer.echo(f"resolved finding {finding_id}")
        return
    typer.echo(f"finding not found: {finding_id}")
    raise typer.Exit(1)


@findings_app.command("add")
def add_finding(
    issue_id: str,
    source: str = typer.Option(..., "--source"),
    severity: str = typer.Option("advisory", "--severity"),
    description: str = typer.Option(..., "--description"),
    file_path: str | None = typer.Option(None, "--file-path"),
    line: int | None = typer.Option(None, "--line"),
    scope: str = typer.Option("in_spec", "--scope"),
    confidence: float = typer.Option(0.5, "--confidence"),
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
) -> None:
    """Persist a new finding for an issue workspace."""
    workspace = WorkspaceService(repo_root=Path(repo_root)).issue_workspace_path(issue_id)
    finding = Finding(
        id=f"f-{uuid4().hex[:8]}",
        source=source,
        severity=severity,
        confidence=confidence,
        scope=scope,
        fingerprint=fingerprint_from(source, description, file_path, line),
        description=description,
        file_path=file_path,
        line=line,
    )
    append_finding(workspace, finding)
    typer.echo(f"added finding {finding.id}")


@questions_app.command("list")
def list_questions(
    issue_id: str,
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
) -> None:
    """List questions in the spec snapshot for an issue."""
    workspace = WorkspaceService(repo_root=Path(repo_root)).issue_workspace_path(issue_id)
    snapshot = read_spec_snapshot(workspace)
    if snapshot is None:
        typer.echo("no spec snapshot found")
        raise typer.Exit(1)
    if not snapshot.questions:
        typer.echo("no questions")
        return
    answered_ids = {d.question_id for d in snapshot.decisions}
    for q in snapshot.questions:
        status = "answered" if q.id in answered_ids else "open"
        blocking = " [blocking]" if q.blocking else ""
        typer.echo(f"{q.id} [{q.category}]{blocking} ({status}) {q.text}")


@questions_app.command("add")
def add_question(
    issue_id: str,
    text: str = typer.Option(..., "--text", "-t"),
    category: str = typer.Option("requirement", "--category", "-c"),
    blocking: bool = typer.Option(True, "--blocking/--no-blocking"),
    asked_by: str = typer.Option("user", "--asked-by"),
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
) -> None:
    """Add a question to the spec snapshot."""
    workspace = WorkspaceService(repo_root=Path(repo_root)).issue_workspace_path(issue_id)
    snapshot = read_spec_snapshot(workspace)
    if snapshot is None:
        issue_source = FixtureIssueSource(repo_root=Path(repo_root))
        issue = issue_source.load(issue_id)
        snapshot = create_initial_snapshot(issue)
    qid = f"q-{uuid4().hex[:8]}"
    snapshot.questions.append(
        Question(
            id=qid,
            asked_by=asked_by,
            target="user",
            category=category,
            blocking=blocking,
            text=text,
        )
    )
    write_spec_snapshot(workspace, snapshot)
    typer.echo(f"added question {qid}")


@questions_app.command("answer")
def answer_question(
    issue_id: str,
    question_id: str,
    answer: str = typer.Option(..., "--answer", "-a"),
    decided_by: str = typer.Option("user", "--decided-by"),
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
) -> None:
    """Answer a question by recording a Decision."""
    workspace = WorkspaceService(repo_root=Path(repo_root)).issue_workspace_path(issue_id)
    snapshot = read_spec_snapshot(workspace)
    if snapshot is None:
        typer.echo("no spec snapshot found")
        raise typer.Exit(1)
    matching = [q for q in snapshot.questions if q.id == question_id]
    if not matching:
        typer.echo(f"question not found: {question_id}")
        raise typer.Exit(1)
    matching[0].answer = answer
    matching[0].answered_by = decided_by
    snapshot.decisions.append(
        Decision(
            question_id=question_id,
            answer=answer,
            decided_by=decided_by,
            timestamp=datetime.now(UTC).isoformat(),
        )
    )
    write_spec_snapshot(workspace, snapshot)
    typer.echo(f"answered {question_id}")


@spec_app.command("show")
def spec_show(
    issue_id: str,
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
) -> None:
    """Show the current spec snapshot for an issue."""
    workspace = WorkspaceService(repo_root=Path(repo_root)).issue_workspace_path(issue_id)
    snapshot = read_spec_snapshot(workspace)
    if snapshot is None:
        typer.echo("no spec snapshot found")
        raise typer.Exit(1)
    typer.echo(f"version={snapshot.version} approved={snapshot.approved}")
    typer.echo(f"  title: {snapshot.issue.title}")
    typer.echo(f"  questions: {len(snapshot.questions)}")
    typer.echo(f"  decisions: {len(snapshot.decisions)}")
    if snapshot.has_unresolved_blocking_questions():
        typer.echo("  status: has unresolved blocking questions")
    elif snapshot.approved:
        typer.echo("  status: approved")
    else:
        typer.echo("  status: draft")


@spec_app.command("approve")
def spec_approve(
    issue_id: str,
    approved_by: str = typer.Option("user", "--approved-by"),
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
) -> None:
    """Approve the spec snapshot, enabling the build stage."""
    workspace = WorkspaceService(repo_root=Path(repo_root)).issue_workspace_path(issue_id)
    snapshot = read_spec_snapshot(workspace)
    if snapshot is None:
        typer.echo("no spec snapshot found")
        raise typer.Exit(1)
    if snapshot.has_unresolved_blocking_questions():
        typer.echo("cannot approve: unresolved blocking questions remain")
        raise typer.Exit(1)
    snapshot.approved = True
    snapshot.approved_by = approved_by
    snapshot.version += 1
    write_spec_snapshot(workspace, snapshot)
    typer.echo(f"spec approved (v{snapshot.version}) by {approved_by}")


@spec_app.command("draft")
def spec_draft(
    issue_id: str,
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
) -> None:
    """Create an initial draft spec snapshot from the issue fixture."""
    workspace = WorkspaceService(repo_root=Path(repo_root)).issue_workspace_path(issue_id)
    existing = read_spec_snapshot(workspace)
    if existing is not None:
        typer.echo(
            f"spec snapshot already exists (v{existing.version}, "
            f"approved={existing.approved})"
        )
        raise typer.Exit(1)
    issue_source = FixtureIssueSource(repo_root=Path(repo_root))
    issue = issue_source.load(issue_id)
    workspace.mkdir(parents=True, exist_ok=True)
    snapshot = create_initial_snapshot(issue)
    write_spec_snapshot(workspace, snapshot)
    typer.echo(f"created draft spec v1 for {issue_id}")


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
        "fixture", "--source", "-s", help="Issue source: fixture or linear.",
    ),
    auto_pr: bool = typer.Option(
        False, "--auto-pr", help="Automatically create a GitHub PR on completion.",
    ),
    base: str = typer.Option("main", "--base", "-b", help="Base branch for PR."),
) -> None:
    """Run an issue through the full pipeline in one shot.

    Drives the issue from DRAFT all the way to GATE_EVALUATED (or FAILED),
    using LLM self-answer for blocking questions when a planner is configured.
    Optionally creates a GitHub PR and writes back to Linear.
    """
    live_stream: IO[str] | None = sys.stderr if live else None
    controller = _make_controller(
        repo_root=repo_root,
        codex_executable=codex_executable,
        live_stream=live_stream,
        source=source,
    )
    typer.echo(f"running full pipeline for {issue_id}...")
    result = controller.advance_to_completion(issue_id)
    typer.echo(
        " ".join([
            f"issue={result.issue.issue_id}",
            f"state={result.state.value}",
            f"mergeable={result.gate.mergeable}",
            f"blocked={','.join(result.gate.failed_conditions) or 'none'}",
        ])
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
            body_lines.append(
                f"**Blocked**: {', '.join(result.gate.failed_conditions)}"
            )
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
                draft=True,
            )
            if pr_url:
                typer.echo(f"PR created: {pr_url}")
                gh_svc.set_gate_status(workspace=workspace, gate=gate_verdict)
                _linear_writeback_on_pr(
                    issue_id, data, pr_url, gate_verdict, Path(repo_root),
                )
            else:
                typer.echo("could not create PR (branch may be main)")
        except RuntimeError as exc:
            typer.echo(f"auto-PR failed: {exc}")


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


@app.command()
def daemon(
    config: Path = typer.Option(
        "spec-orch.toml", "--config", "-c", help="Path to spec-orch.toml config file."
    ),
    repo_root: Path = typer.Option(".", "--repo-root", "-r", help="Repository root."),
) -> None:
    """Run the SpecOrch daemon that polls Linear for issues and processes them."""
    from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon

    cfg = DaemonConfig.from_toml(config)
    d = SpecOrchDaemon(config=cfg, repo_root=repo_root.resolve())
    d.run()


@config_app.command("check")
def config_check(
    config: Path = typer.Option(
        "spec-orch.toml", "--config", "-c", help="Path to spec-orch.toml config file."
    ),
) -> None:
    """Validate spec-orch.toml and related external dependencies."""
    from spec_orch.services.config_checker import CheckResult, ConfigChecker

    checker = ConfigChecker()
    results: list[CheckResult] = checker.check_toml(config)

    try:
        raw = checker.load_toml(config)
    except (FileNotFoundError, ValueError, OSError):
        raw = {}
    except Exception:
        raw = {}

    linear = raw.get("linear", {}) if isinstance(raw, dict) else {}
    builder = raw.get("builder", {}) if isinstance(raw, dict) else {}
    planner = raw.get("planner", {}) if isinstance(raw, dict) else {}

    linear_token_env = linear.get("token_env") if isinstance(linear, dict) else None
    linear_token = os.environ.get(linear_token_env, "") if linear_token_env else ""
    linear_team_key = linear.get("team_key", "") if isinstance(linear, dict) else ""
    codex_executable = (
        builder.get("codex_executable", "codex") if isinstance(builder, dict) else "codex"
    )
    planner_model = planner.get("model") if isinstance(planner, dict) else None
    planner_api_key_env = planner.get("api_key_env") if isinstance(planner, dict) else None

    results.extend(checker.check_linear(linear_token, linear_team_key))
    results.append(checker.check_codex(codex_executable))
    results.extend(checker.check_planner(planner_model, planner_api_key_env))

    _print_check_report(results)
    if any(result.status == "fail" for result in results):
        raise typer.Exit(1)


@app.command()
def gate(
    issue_id: str = typer.Argument(
        default="", help="Issue ID to evaluate gate for (optional)."
    ),
    repo_root: Path = typer.Option(".", "--repo-root", "-r"),
    policy: Path = typer.Option(
        "gate.policy.yaml", "--policy", "-p", help="Path to gate.policy.yaml."
    ),
    show_policy: bool = typer.Option(
        False, "--show-policy", help="Print the gate policy and exit."
    ),
) -> None:
    """Evaluate the gate for an issue, or show gate policy."""
    from spec_orch.services.gate_service import GatePolicy, GateService

    gate_policy: GatePolicy | None = None
    if Path(policy).exists():
        gate_policy = GatePolicy.from_yaml(Path(policy))

    svc = GateService(policy=gate_policy)

    if show_policy:
        typer.echo(svc.describe_policy())
        return

    if not issue_id:
        typer.echo("provide an issue_id or use --show-policy")
        raise typer.Exit(1)

    ws = WorkspaceService(repo_root=Path(repo_root))
    workspace = ws.issue_workspace_path(issue_id)
    result_file = workspace / "report.json"
    if not result_file.exists():
        typer.echo(f"no run found for {issue_id}")
        raise typer.Exit(1)

    data = json.loads(result_file.read_text())

    from spec_orch.domain.models import (
        GateInput,
        ReviewSummary,
        VerificationDetail,
        VerificationSummary,
    )

    builder_data = data.get("builder", {})
    review_data = data.get("review", {})
    verification_data = data.get("verification", {})
    acceptance_data = data.get("human_acceptance", {})

    _fail = VerificationDetail(
        command=[], exit_code=1, stdout="", stderr="",
    )
    details = {
        name: VerificationDetail(
            command=detail.get("command", []),
            exit_code=detail.get("exit_code", 1),
            stdout="",
            stderr="",
        )
        for name, detail in verification_data.items()
    }
    verification = VerificationSummary(
        lint_passed=details.get("lint", _fail).exit_code == 0,
        typecheck_passed=details.get("typecheck", _fail).exit_code == 0,
        test_passed=details.get("test", _fail).exit_code == 0,
        build_passed=details.get("build", _fail).exit_code == 0,
        details=details,
    )
    review = ReviewSummary(
        verdict=review_data.get("verdict", "pending"),
        reviewed_by=review_data.get("reviewed_by"),
    )
    gate_input = GateInput(
        spec_exists=True,
        spec_approved=True,
        within_boundaries=True,
        builder_succeeded=builder_data.get("succeeded", False),
        verification=verification,
        review=review,
        human_acceptance=acceptance_data.get("accepted", False),
    )
    verdict = svc.evaluate(gate_input)

    typer.echo(f"{issue_id}: mergeable={verdict.mergeable}")
    if verdict.failed_conditions:
        typer.echo(f"  blocked: {', '.join(verdict.failed_conditions)}")
    else:
        typer.echo("  all conditions passed")

    if gate_policy:
        typer.echo(f"  auto_merge: {gate_policy.auto_merge}")


@app.command("watch")
def watch_issue(
    issue_id: str,
    repo_root: Path = typer.Option(".", "--repo-root", "-r"),
    follow: bool = typer.Option(
        False, "--follow", "-f", help="Keep watching even after log ends."
    ),
    tail: int = typer.Option(
        0, "--tail", "-n", help="Show last N lines only (0 = all)."
    ),
) -> None:
    """Watch real-time activity log for an issue run."""
    ws = WorkspaceService(repo_root=Path(repo_root))
    workspace = ws.issue_workspace_path(issue_id)
    log_path = workspace / "telemetry" / "activity.log"
    if not log_path.exists():
        typer.echo(f"no activity log found for {issue_id}")
        raise typer.Exit(1)

    content = log_path.read_text(encoding="utf-8")
    offset = len(content.encode("utf-8"))
    lines = content.splitlines()
    if tail > 0:
        lines = lines[-tail:]
    for line in lines:
        typer.echo(line)

    if not follow:
        still_running = not (workspace / "report.json").exists()
        if not still_running:
            return

    try:
        while True:
            time.sleep(0.3)
            current_size = log_path.stat().st_size
            if current_size > offset:
                with log_path.open("r", encoding="utf-8") as f:
                    f.seek(offset)
                    new_data = f.read()
                offset = current_size
                for line in new_data.splitlines():
                    typer.echo(line)
            elif (workspace / "report.json").exists() and not follow:
                break
    except KeyboardInterrupt:
        pass


@app.command("logs")
def logs_issue(
    issue_id: str,
    repo_root: Path = typer.Option(".", "--repo-root", "-r"),
    raw: bool = typer.Option(
        False, "--raw", help="Print raw codex events (incoming_events.jsonl)."
    ),
    events: bool = typer.Option(
        False, "--events", help="Print orchestrator events (events.jsonl)."
    ),
    filter_type: str = typer.Option(
        "", "--filter", help="Filter by event type substring."
    ),
) -> None:
    """View complete activity logs for an issue run."""
    ws = WorkspaceService(repo_root=Path(repo_root))
    workspace = ws.issue_workspace_path(issue_id)
    telemetry_dir = workspace / "telemetry"

    if raw:
        _print_jsonl(telemetry_dir / "incoming_events.jsonl", filter_type)
        return
    if events:
        _print_jsonl(telemetry_dir / "events.jsonl", filter_type)
        return

    log_path = telemetry_dir / "activity.log"
    if not log_path.exists():
        typer.echo(f"no activity log found for {issue_id}")
        raise typer.Exit(1)

    for line in log_path.read_text(encoding="utf-8").splitlines():
        if filter_type and filter_type.upper() not in line.upper():
            continue
        typer.echo(line)


def _print_jsonl(path: Path, filter_type: str) -> None:
    if not path.exists():
        typer.echo(f"file not found: {path}")
        raise typer.Exit(1)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if filter_type:
            try:
                obj = json.loads(line)
                etype = obj.get("event_type", "") or obj.get("type", "")
                if filter_type.lower() not in etype.lower():
                    continue
            except json.JSONDecodeError:
                continue
        typer.echo(line)


def _print_check_report(results: list[Any]) -> None:
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
        typer.echo(f"[{result.status.upper()}] {result.name}: {result.message}")
    typer.echo(
        f"Summary: {counts['pass']} pass, {counts['warn']} warn, {counts['fail']} fail"
    )


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


def _linear_writeback_on_pr(
    issue_id: str,
    report: dict[str, Any],
    pr_url: str | None,
    gate: Any,
    repo_root: Path,
) -> None:
    """Post a pipeline summary to Linear when a token is available."""
    import tomllib as _tomllib

    config_path = repo_root / "spec-orch.toml"
    if not config_path.exists():
        return
    try:
        with config_path.open("rb") as f:
            raw = _tomllib.load(f)
    except (FileNotFoundError, _tomllib.TOMLDecodeError):
        return

    linear_cfg = raw.get("linear", {})
    token_env = linear_cfg.get("token_env", "")
    token = os.environ.get(token_env, "") if token_env else ""
    if not token:
        return

    try:
        import httpx

        from spec_orch.services.linear_client import LinearClient

        client = LinearClient(token=token)
    except (ImportError, RuntimeError) as exc:
        typer.echo(f"linear writeback skipped: {exc}")
        return

    try:
        issue_data = client.get_issue(issue_id)
        linear_id = issue_data["id"]

        state = report.get("state", "unknown")
        title = report.get("title", issue_id)
        mergeable = "yes" if gate.mergeable else "no"
        blocked = ", ".join(gate.failed_conditions) if gate.failed_conditions else "none"

        comment = (
            f"## SpecOrch Pipeline Complete\n\n"
            f"**Issue**: {issue_id} — {title}\n"
            f"**State**: {state}\n"
            f"**Mergeable**: {mergeable}\n"
            f"**Blocked by**: {blocked}\n"
        )
        if pr_url:
            comment += f"**PR**: {pr_url}\n"
        comment += f"\n_Auto-close on merge via `Closes {issue_id}` in PR body._"

        client.add_comment(linear_id, comment)
        client.update_issue_state(linear_id, "In Progress")
        typer.echo(f"linear: posted summary to {issue_id}")
    except (httpx.HTTPError, ValueError, RuntimeError, OSError) as exc:
        typer.echo(f"linear writeback skipped: {exc}")
    finally:
        client.close()


@app.command("plan")
def plan_mission(
    mission_id: str = typer.Argument(..., help="Mission ID to scope."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Generate a wave-based execution plan (DAG) from a Mission spec."""
    from spec_orch.services.mission_service import MissionService
    from spec_orch.services.promotion_service import save_plan
    from spec_orch.services.scoper_adapter import LiteLLMScoperAdapter

    svc = MissionService(repo_root=Path(repo_root))
    mission = svc.get_mission(mission_id)

    spec_file = Path(repo_root) / mission.spec_path
    spec_content = spec_file.read_text() if spec_file.exists() else ""

    tree_lines: list[str] = []
    src = Path(repo_root) / "src"
    if src.exists():
        for p in sorted(src.rglob("*.py")):
            tree_lines.append(str(p.relative_to(repo_root)))

    planner_cfg = _load_planner_config(Path(repo_root))
    scoper = LiteLLMScoperAdapter(
        model=planner_cfg.get("model", "anthropic/claude-sonnet-4-20250514"),
        api_key=planner_cfg.get("api_key"),
        api_base=planner_cfg.get("api_base"),
        token_command=planner_cfg.get("token_command"),
    )

    plan = scoper.scope(
        mission=mission,
        codebase_context={
            "spec_content": spec_content,
            "file_tree": "\n".join(tree_lines),
        },
    )

    plan_path = Path(repo_root) / "docs/specs" / mission_id / "plan.json"
    save_plan(plan, plan_path)

    total_packets = sum(len(w.work_packets) for w in plan.waves)
    typer.echo(
        f"plan generated: {len(plan.waves)} waves, "
        f"{total_packets} work packets"
    )
    for w in plan.waves:
        typer.echo(
            f"  wave {w.wave_number}: {w.description} "
            f"({len(w.work_packets)} packets)"
        )


@app.command("plan-show")
def plan_show(
    mission_id: str = typer.Argument(..., help="Mission ID."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Display the execution plan for a Mission."""
    from spec_orch.services.promotion_service import load_plan

    plan_path = Path(repo_root) / "docs/specs" / mission_id / "plan.json"
    if not plan_path.exists():
        typer.echo(f"no plan found for {mission_id}")
        raise typer.Exit(1)

    plan = load_plan(plan_path)
    typer.echo(f"plan: {plan.plan_id} | mission: {plan.mission_id}")
    typer.echo(f"status: {plan.status.value}")
    for w in plan.waves:
        typer.echo(f"\n--- Wave {w.wave_number}: {w.description} ---")
        for p in w.work_packets:
            deps = f" (depends: {', '.join(p.depends_on)})" if p.depends_on else ""
            issue = f" [{p.linear_issue_id}]" if p.linear_issue_id else ""
            typer.echo(f"  [{p.run_class}] {p.packet_id}: {p.title}{deps}{issue}")


@app.command("promote")
def promote_plan(
    mission_id: str = typer.Argument(..., help="Mission ID to promote."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Promote a plan to execution — create Linear issues from work packets."""
    from spec_orch.services.promotion_service import PromotionService, load_plan, save_plan

    plan_path = Path(repo_root) / "docs/specs" / mission_id / "plan.json"
    if not plan_path.exists():
        typer.echo(f"no plan found for {mission_id}")
        raise typer.Exit(1)

    plan = load_plan(plan_path)
    svc = PromotionService()
    plan = svc.promote(plan)
    save_plan(plan, plan_path)

    total = sum(len(w.work_packets) for w in plan.waves)
    typer.echo(f"promoted {total} work packets to execution")
    for w in plan.waves:
        for p in w.work_packets:
            typer.echo(f"  {p.linear_issue_id}: {p.title}")


@app.command("retro")
def retro_mission(
    mission_id: str = typer.Argument(..., help="Mission ID."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Generate a retrospective for a Mission — deviations, decisions, outcomes."""
    from spec_orch.services.deviation_service import load_deviations
    from spec_orch.services.mission_service import MissionService
    from spec_orch.services.promotion_service import load_plan

    svc = MissionService(repo_root=Path(repo_root))
    mission = svc.get_mission(mission_id)

    mission_issue_ids: set[str] | None = None
    plan_path = Path(repo_root) / "docs/specs" / mission_id / "plan.json"
    if plan_path.exists():
        plan = load_plan(plan_path)
        mission_issue_ids = set()
        for w in plan.waves:
            for p in w.work_packets:
                if p.linear_issue_id:
                    mission_issue_ids.add(p.linear_issue_id)

    ws = WorkspaceService(repo_root=Path(repo_root))
    base_dir = ws.repo_root / ".spec_orch_runs"
    if not base_dir.exists():
        base_dir = ws.repo_root / ".worktrees"

    retro_lines = [
        f"# Retrospective: {mission.title}",
        f"\n**Mission**: `{mission_id}`",
        f"**Status**: {mission.status.value}",
        "",
        "## Issues",
        "",
    ]

    issue_dirs = sorted(base_dir.iterdir()) if base_dir.exists() else []
    total_deviations = 0
    issues_included = 0
    for issue_dir in issue_dirs:
        report_path = issue_dir / "report.json"
        if not report_path.exists():
            continue
        data = json.loads(report_path.read_text())
        issue_id = data.get("issue_id", issue_dir.name)
        if mission_issue_ids is not None and issue_id not in mission_issue_ids:
            continue
        issues_included += 1
        state = data.get("state", "unknown")
        mergeable = data.get("mergeable", False)
        retro_lines.append(
            f"- **{issue_id}**: {data.get('title', '')} "
            f"| state={state} | mergeable={mergeable}"
        )
        deviations = load_deviations(issue_dir)
        if deviations:
            total_deviations += len(deviations)
            for d in deviations:
                retro_lines.append(
                    f"  - [{d.severity}] {d.description} ({d.resolution})"
                )

    retro_lines.extend([
        "",
        "## Summary",
        "",
        f"- Total deviations: {total_deviations}",
        f"- Issues processed: {issues_included}",
    ])

    retro_content = "\n".join(retro_lines) + "\n"
    retro_path = (
        Path(repo_root) / "docs/specs" / mission_id / "retrospective.md"
    )
    retro_path.parent.mkdir(parents=True, exist_ok=True)
    retro_path.write_text(retro_content)
    typer.echo(f"retrospective written: {retro_path}")
    typer.echo(retro_content)


def _load_planner_config(repo_root: Path) -> dict[str, Any]:
    """Load planner config from spec-orch.toml."""
    config_path = repo_root / "spec-orch.toml"
    if not config_path.exists():
        return {}
    try:
        import tomllib

        with config_path.open("rb") as f:
            raw = tomllib.load(f)
    except (ImportError, FileNotFoundError, tomllib.TOMLDecodeError):
        return {}
    planner_cfg = raw.get("planner", {})
    result: dict[str, Any] = {}
    if planner_cfg.get("model"):
        result["model"] = planner_cfg["model"]
    api_key_env = planner_cfg.get("api_key_env")
    if api_key_env:
        result["api_key"] = os.environ.get(api_key_env)
    api_base_env = planner_cfg.get("api_base_env")
    if api_base_env:
        result["api_base"] = os.environ.get(api_base_env)
    result["token_command"] = planner_cfg.get("token_command")
    return result


@mission_app.command("create")
def mission_create(
    title: str = typer.Argument(..., help="Mission title."),
    mission_id: str | None = typer.Option(None, "--id", help="Override generated ID."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Create a new Mission with a canonical spec skeleton."""
    from spec_orch.services.mission_service import MissionService

    svc = MissionService(repo_root=Path(repo_root))
    m = svc.create_mission(title, mission_id=mission_id)
    typer.echo(f"mission created: {m.mission_id}")
    typer.echo(f"spec: {m.spec_path}")


@mission_app.command("approve")
def mission_approve(
    mission_id: str = typer.Argument(..., help="Mission ID to approve."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Approve a Mission spec, freezing it for execution."""
    from spec_orch.services.mission_service import MissionService

    svc = MissionService(repo_root=Path(repo_root))
    m = svc.approve_mission(mission_id)
    typer.echo(f"mission {m.mission_id} approved at {m.approved_at}")


@mission_app.command("status")
def mission_status(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """List all Missions and their status."""
    from spec_orch.services.mission_service import MissionService

    svc = MissionService(repo_root=Path(repo_root))
    missions = svc.list_missions()
    if not missions:
        typer.echo("no missions found")
        return
    for m in missions:
        typer.echo(f"{m.mission_id:40s} {m.status.value:12s} {m.title}")


@mission_app.command("show")
def mission_show(
    mission_id: str = typer.Argument(..., help="Mission ID."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Print the canonical spec for a Mission."""
    from spec_orch.services.mission_service import MissionService

    svc = MissionService(repo_root=Path(repo_root))
    m = svc.get_mission(mission_id)
    spec_file = Path(repo_root) / m.spec_path
    if spec_file.exists():
        typer.echo(spec_file.read_text())
    else:
        typer.echo(f"spec file not found: {m.spec_path}")


def _make_controller(
    *,
    repo_root: Path,
    codex_executable: str = "codex",
    live_stream: IO[str] | None = None,
    source: str = "fixture",
) -> RunController:
    issue_source: Any
    if source == "linear":
        from spec_orch.services.linear_client import LinearClient
        from spec_orch.services.linear_issue_source import LinearIssueSource

        client = LinearClient()
        issue_source = LinearIssueSource(client=client)
    else:
        issue_source = FixtureIssueSource(repo_root=Path(repo_root))

    planner = _build_planner_from_toml(repo_root)

    return RunController(
        repo_root=repo_root,
        builder_adapter=CodexExecBuilderAdapter(executable=codex_executable),
        issue_source=issue_source,
        planner_adapter=planner,
        live_stream=live_stream,
    )


def _build_planner_from_toml(repo_root: Path) -> Any:
    """Build a PlannerAdapter from spec-orch.toml if planner section exists."""
    config_path = repo_root / "spec-orch.toml"
    if not config_path.exists():
        return None
    try:
        import tomllib

        with config_path.open("rb") as f:
            raw = tomllib.load(f)
    except Exception:
        return None

    planner_cfg = raw.get("planner", {})
    model = planner_cfg.get("model")
    if not model:
        return None

    api_key: str | None = None
    api_key_env = planner_cfg.get("api_key_env")
    if api_key_env:
        api_key = os.environ.get(api_key_env)

    api_base: str | None = None
    api_base_env = planner_cfg.get("api_base_env")
    if api_base_env:
        api_base = os.environ.get(api_base_env)

    token_command = planner_cfg.get("token_command")

    try:
        from spec_orch.services.litellm_planner_adapter import LiteLLMPlannerAdapter

        return LiteLLMPlannerAdapter(
            model=model,
            api_key=api_key,
            api_base=api_base,
            token_command=token_command,
        )
    except ImportError:
        return None


def _edit_fixture_json(fixture: dict[str, object]) -> dict[str, object]:
    editor = os.environ.get("EDITOR")
    if not editor:
        typer.echo("$EDITOR is not set")
        raise typer.Exit(1)

    with tempfile.NamedTemporaryFile(
        mode="w+",
        suffix=".json",
        encoding="utf-8",
        delete=False,
    ) as temp_file:
        temp_path = Path(temp_file.name)
        temp_file.write(json.dumps(fixture, indent=2) + "\n")

    try:
        result = subprocess.run(shlex.split(editor) + [str(temp_path)], check=False)
        if result.returncode != 0:
            typer.echo(f"editor exited with code {result.returncode}")
            raise typer.Exit(1)
        result_data: dict[str, object] = json.loads(
            temp_path.read_text(encoding="utf-8"),
        )
        return result_data
    except json.JSONDecodeError as exc:
        typer.echo(f"edited fixture is not valid JSON: {exc}")
        raise typer.Exit(1) from exc
    finally:
        temp_path.unlink(missing_ok=True)


def _load_conversation_planner(
    repo_root: Path,
) -> Any:
    """Build a LiteLLMPlannerAdapter from spec-orch.toml for conversation use."""
    try:
        import tomllib
    except ImportError:
        return None
    toml_path = repo_root / "spec-orch.toml"
    if not toml_path.exists():
        return None
    try:
        with open(toml_path, "rb") as f:
            raw = tomllib.load(f)
        planner_cfg = raw.get("planner", {})
        model = planner_cfg.get("model")
        if not model:
            return None
        api_key_env = planner_cfg.get("api_key_env")
        api_base_env = planner_cfg.get("api_base_env")
        token_command = planner_cfg.get("token_command")

        from spec_orch.services.litellm_planner_adapter import LiteLLMPlannerAdapter

        return LiteLLMPlannerAdapter(
            model=model,
            api_key=os.environ.get(api_key_env) if api_key_env else None,
            api_base=os.environ.get(api_base_env) if api_base_env else None,
            token_command=token_command,
        )
    except (ImportError, FileNotFoundError, tomllib.TOMLDecodeError):
        return None


@discuss_app.callback(invoke_without_command=True)
def discuss_tui(
    ctx: typer.Context,
    channel: str = typer.Option(
        "cli", "--channel", "-c",
        help="Conversation channel: cli, slack, or linear.",
    ),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Interactive brainstorming with the LLM planner."""
    if ctx.invoked_subcommand is not None:
        return

    from spec_orch.services.conversation_service import ConversationService

    planner = _load_conversation_planner(repo_root)
    svc = ConversationService(repo_root=repo_root, planner=planner)

    if channel == "slack":
        _start_slack_adapter(svc, repo_root)
        return

    if channel == "linear":
        _start_linear_adapter(svc, repo_root)
        return

    thread_id = f"cli-{uuid4().hex[:8]}"
    typer.echo("SpecOrch brainstorming (type 'quit' to exit, '@spec-orch freeze' to freeze)")
    typer.echo(f"Thread: {thread_id}")

    while True:
        try:
            user_input = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            typer.echo("\nbye")
            break
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            break

        from spec_orch.domain.models import ConversationMessage

        msg = ConversationMessage(
            message_id=f"cli-{uuid4().hex[:8]}",
            thread_id=thread_id,
            sender="user",
            content=user_input,
            timestamp=datetime.now(UTC).isoformat(),
            channel="cli",
        )
        reply = svc.handle_message(msg)
        if reply:
            typer.echo(f"\nbot> {reply}")


def _start_slack_adapter(svc: Any, repo_root: Path) -> None:
    try:
        from spec_orch.services.slack_conversation_adapter import (
            SlackConversationAdapter,
        )
    except ImportError as exc:
        typer.echo("slack-bolt not installed. Run: pip install spec-orch[slack]")
        raise typer.Exit(1) from exc

    adapter = SlackConversationAdapter()
    typer.echo("Starting Slack bot (Socket Mode)...")
    adapter.listen(callback=svc.handle_message)


def _start_linear_adapter(svc: Any, repo_root: Path) -> None:
    try:
        import tomllib
    except ImportError as exc:
        typer.echo("tomllib not available")
        raise typer.Exit(1) from exc

    toml_path = repo_root / "spec-orch.toml"
    if not toml_path.exists():
        typer.echo("spec-orch.toml not found")
        raise typer.Exit(1)

    with open(toml_path, "rb") as f:
        raw = tomllib.load(f)

    linear_cfg = raw.get("linear", {})
    conv_section = raw.get("conversation", {})
    conv_cfg = conv_section.get("linear", {}) if isinstance(conv_section, dict) else {}

    from spec_orch.services.linear_client import LinearClient
    from spec_orch.services.linear_conversation_adapter import LinearConversationAdapter

    client = LinearClient(token_env=linear_cfg.get("token_env", "SPEC_ORCH_LINEAR_TOKEN"))
    adapter = LinearConversationAdapter(
        client=client,
        team_key=linear_cfg.get("team_key", "SON"),
        watch_label=conv_cfg.get("watch_label", "spec-orch"),
        poll_interval_seconds=conv_cfg.get("poll_interval_seconds", 30),
    )
    typer.echo("Starting Linear comment bot (polling)...")
    adapter.listen(callback=svc.handle_message)


@discuss_app.command("list")
def discuss_list(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """List active conversation threads."""
    from spec_orch.services.conversation_service import ConversationService

    svc = ConversationService(repo_root=repo_root)
    threads = svc.list_threads()
    if not threads:
        typer.echo("No conversation threads found.")
        return
    for t in threads:
        n_msgs = len(t.messages)
        typer.echo(
            f"  {t.thread_id}  channel={t.channel}  status={t.status.value}  "
            f"messages={n_msgs}  mission={t.mission_id or '-'}"
        )


@discuss_app.command("freeze")
def discuss_freeze(
    thread_id: str = typer.Argument(..., help="Thread ID to freeze."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Manually freeze a conversation thread into a spec."""
    from spec_orch.domain.models import ConversationMessage
    from spec_orch.services.conversation_service import ConversationService

    planner = _load_conversation_planner(repo_root)
    svc = ConversationService(repo_root=repo_root, planner=planner)

    thread = svc.get_thread(thread_id)
    if thread is None or not thread.messages:
        typer.echo(f"Thread {thread_id} not found or empty.")
        raise typer.Exit(1)

    msg = ConversationMessage(
        message_id=f"cmd-{uuid4().hex[:8]}",
        thread_id=thread_id,
        sender="user",
        content="@spec-orch freeze",
        timestamp=datetime.now(UTC).isoformat(),
        channel=thread.channel,
    )
    result = svc.handle_message(msg)
    if result:
        typer.echo(result)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
