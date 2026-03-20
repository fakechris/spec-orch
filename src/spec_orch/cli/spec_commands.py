from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import typer

from spec_orch.cli import app
from spec_orch.cli._helpers import _edit_fixture_json
from spec_orch.domain.models import Decision, Finding, Question
from spec_orch.services.finding_store import (
    append_finding,
    fingerprint_from,
    load_findings,
    resolve_finding,
)
from spec_orch.services.fixture_issue_source import FixtureIssueSource
from spec_orch.services.spec_snapshot_service import (
    create_initial_snapshot,
    read_spec_snapshot,
    write_spec_snapshot,
)
from spec_orch.services.workspace_service import WorkspaceService

findings_app = typer.Typer()
app.add_typer(findings_app, name="findings")
questions_app = typer.Typer()
app.add_typer(questions_app, name="questions")
spec_app = typer.Typer()
app.add_typer(spec_app, name="spec")


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
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
    edit: bool = typer.Option(False, "--edit", help="Open in $EDITOR before saving."),
    builder_prompt_from: Path | None = typer.Option(
        None,
        "--builder-prompt-from",
        "-p",
        help="Override builder_prompt from file.",
    ),
    no_builder: bool = typer.Option(False, "--no-builder", help="Set builder_prompt to null."),
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

    fixture = generate_fixture(parse_plan(plan_path), issue_id, repo_root=Path(repo_root))

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


# ---------------------------------------------------------------------------
# findings commands
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# questions commands
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# spec commands
# ---------------------------------------------------------------------------


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
            f"spec snapshot already exists (v{existing.version}, approved={existing.approved})"
        )
        raise typer.Exit(1)
    issue_source = FixtureIssueSource(repo_root=Path(repo_root))
    issue = issue_source.load(issue_id)
    workspace.mkdir(parents=True, exist_ok=True)
    snapshot = create_initial_snapshot(issue)
    write_spec_snapshot(workspace, snapshot)
    typer.echo(f"created draft spec v1 for {issue_id}")


@spec_app.command("import")
def spec_import(
    format_id: str = typer.Option(
        ..., "--format", "-f", help="Source format: spec-kit, ears, bdd."
    ),
    path: str = typer.Option(..., "--path", "-p", help="Path to spec file or directory."),
    title: str = typer.Option(
        "", "--title", "-t", help="Mission title (defaults to format+filename)."
    ),
    mission_id: str | None = typer.Option(
        None, "--mission-id", help="Override generated mission ID."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print parsed spec without creating mission."
    ),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Import a spec from an external format (spec-kit, ears, bdd) and create a mission."""
    from spec_orch.spec_import.parser import PARSER_REGISTRY

    parser = PARSER_REGISTRY.get(format_id)
    if parser is None:
        supported = ", ".join(PARSER_REGISTRY.supported_formats())
        typer.echo(f"Error: unsupported format '{format_id}'. Supported: {supported}", err=True)
        raise typer.Exit(code=1)

    source_path = Path(path)
    if not source_path.exists():
        typer.echo(f"Error: path not found: {path}", err=True)
        raise typer.Exit(code=1)

    try:
        spec_structure = parser.parse(source_path)
    except Exception as exc:
        typer.echo(f"Error parsing {format_id}: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    resolved_title = title or f"{format_id}-import-{source_path.stem}"

    if dry_run:
        typer.echo(spec_structure.to_markdown(resolved_title))
        return

    from spec_orch.services.mission_service import MissionService

    svc = MissionService(repo_root=repo_root)
    m = svc.create_mission_from_structure(resolved_title, spec_structure, mission_id=mission_id)
    typer.echo(f"mission created: {m.mission_id}")
    typer.echo(f"spec: {m.spec_path}")
