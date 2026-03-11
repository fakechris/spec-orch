from __future__ import annotations

import importlib.metadata
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import IO

import typer

from spec_orch.services.codex_exec_builder_adapter import CodexExecBuilderAdapter
from spec_orch.services.fixture_issue_source import FixtureIssueSource
from spec_orch.services.run_controller import RunController
from spec_orch.services.workspace_service import WorkspaceService

app = typer.Typer(help="SpecOrch MVP prototype CLI.")


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
) -> None:
    """Run one local issue fixture through the MVP pipeline."""
    live_stream: IO[str] | None = sys.stderr if live else None
    controller = _make_controller(
        repo_root=repo_root,
        codex_executable=codex_executable,
        live_stream=live_stream,
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
    """Record human acceptance for an existing issue run."""
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
    issue_id: str,
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
) -> None:
    """Show the current status of an issue run."""
    ws = WorkspaceService(repo_root=Path(repo_root))
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


def _make_controller(
    *,
    repo_root: Path,
    codex_executable: str = "codex",
    live_stream: IO[str] | None = None,
) -> RunController:
    return RunController(
        repo_root=repo_root,
        builder_adapter=CodexExecBuilderAdapter(executable=codex_executable),
        issue_source=FixtureIssueSource(repo_root=Path(repo_root)),
        live_stream=live_stream,
    )


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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
