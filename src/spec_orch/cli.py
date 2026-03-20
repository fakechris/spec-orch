from __future__ import annotations

import enum
import importlib.metadata
import json
import logging as _logging
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any
from uuid import uuid4

import typer
import yaml

from spec_orch.domain.models import Decision, Finding, Question, RunState
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
evidence_app = typer.Typer(help="Evidence analysis commands.")
app.add_typer(evidence_app, name="evidence")
harness_app = typer.Typer(help="Harness synthesis and rule management commands.")
app.add_typer(harness_app, name="harness")
prompt_app = typer.Typer(help="Prompt evolution and A/B testing commands.")
app.add_typer(prompt_app, name="prompt")
strategy_app = typer.Typer(help="Plan strategy evolution and scoper hints.")
app.add_typer(strategy_app, name="strategy")
policy_app = typer.Typer(help="Policy distiller — deterministic code policies.")
app.add_typer(policy_app, name="policy")
eval_app = typer.Typer(help="Harness eval — offline quality evaluation of historical runs.")
app.add_typer(eval_app, name="eval")
contract_app = typer.Typer(help="Task contract generation and management.")
app.add_typer(contract_app, name="contract")
evolution_app = typer.Typer(help="Evolution pipeline status and lifecycle management.")
app.add_typer(evolution_app, name="evolution")


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


def _load_dotenv() -> None:
    """Load .env from repo root (or parents) if present."""
    candidate = Path.cwd()
    for _ in range(5):
        env_path = candidate / ".env"
        if env_path.is_file():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if key and key not in os.environ:
                    os.environ[key] = value
            break
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent


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
    _load_dotenv()


class ProfileLevel(enum.StrEnum):
    minimal = "minimal"
    standard = "standard"
    full = "full"


@app.command("init")
def init_project(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing spec-orch.toml."),
    non_interactive: bool = typer.Option(
        False, "--yes", "-y", help="Accept defaults without prompting."
    ),
    offline: bool = typer.Option(
        False,
        "--offline",
        help="Use offline rule-based detection instead of LLM analysis.",
    ),
    smart: bool = typer.Option(
        False,
        "--smart",
        hidden=True,
        help="Deprecated: LLM detection is now the default.",
    ),
    reconfigure: bool = typer.Option(
        False,
        "--reconfigure",
        help="Re-run detection and overwrite existing spec-orch.toml.",
    ),
    profile: ProfileLevel = typer.Option(
        ProfileLevel.standard,
        "--profile",
        help="Config profile level.",
    ),
) -> None:
    """Detect project type and generate spec-orch.toml configuration.

    By default, uses LLM-based analysis for project detection when credentials
    are available, and automatically falls back to rule-based detection.
    Use --offline to force rule-based detection.

    Rule-based detection scans for marker files (pyproject.toml, package.json,
    Cargo.toml, go.mod, etc.) and applies language-specific defaults.
    """
    from spec_orch.services.project_detector import generate_toml_config
    from spec_orch.services.smart_project_analyzer import smart_detect_project

    root = Path(repo_root).resolve()
    config_path = root / "spec-orch.toml"

    if smart:
        typer.echo("Warning: --smart is deprecated and no longer needed (LLM is default).")

    if config_path.exists() and not (force or reconfigure):
        typer.echo(f"spec-orch.toml already exists at {config_path}")
        typer.echo("Use --force or --reconfigure to overwrite.")
        raise typer.Exit(1)

    persisted_mode = _read_init_detection_mode(config_path) if config_path.exists() else None
    use_offline = offline or persisted_mode == "rules"
    project_profile, method = smart_detect_project(root, offline=use_offline)
    method_label = "LLM analysis" if method == "llm" else "rule-based detection"
    typer.echo(
        f"Detected project: {project_profile.language}"
        f" ({project_profile.framework or 'no framework'})"
        f" via {method_label}"
    )
    typer.echo("Verification commands:")
    for step, cmd in project_profile.verification.items():
        typer.echo(f"  {step}: {' '.join(cmd)}")
    if project_profile.extra_notes:
        typer.echo(f"Notes: {project_profile.extra_notes}")

    if not non_interactive and method == "llm" and project_profile.verification:
        confirm_verify = typer.confirm(
            "Accept inferred verification commands from LLM?",
            default=True,
        )
        if not confirm_verify:
            typer.echo("Aborted.")
            raise typer.Exit(0)

    if not non_interactive:
        proceed = typer.confirm("Generate spec-orch.toml with these settings?", default=True)
        if not proceed:
            typer.echo("Aborted.")
            raise typer.Exit(0)

    toml_content = generate_toml_config(project_profile, profile_level=profile.value)
    config_path.write_text(toml_content)
    typer.echo(f"\nWrote {config_path}")

    env_path = root / ".env"
    if not env_path.exists():
        example_path = root / ".env.example"
        if example_path.exists():
            import shutil as _shutil

            _shutil.copy2(example_path, env_path)
            typer.echo(f"Copied {example_path} → {env_path}")
            typer.echo("Edit .env to set your API keys before using spec-orch.")
        else:
            typer.echo("Tip: create a .env file with SPEC_ORCH_LLM_API_KEY=your-key")

    typer.echo("\nRunning preflight check...")
    _run_preflight_inline(root)


def _read_init_detection_mode(config_path: Path) -> str | None:
    """Read persisted init detection mode from spec-orch.toml if present."""
    if not config_path.exists():
        return None
    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    init_cfg = raw.get("init", {}) if isinstance(raw, dict) else {}
    if not isinstance(init_cfg, dict):
        return None
    mode = init_cfg.get("detection_mode")
    if isinstance(mode, str) and mode in {"llm", "rules"}:
        return mode
    return None


@app.command("dashboard")
def dashboard(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8420, "--port", "-p"),
) -> None:
    """Launch the web dashboard for pipeline visualization."""
    try:
        import uvicorn
    except ImportError:
        typer.echo("Dashboard dependencies missing. Run: pip install 'spec-orch[dashboard]'")
        raise typer.Exit(1) from None

    from spec_orch.dashboard import create_app

    app = create_app(repo_root=Path(repo_root).resolve())
    typer.echo(f"dashboard: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


def _run_preflight(
    root: Path,
    *,
    try_llm: bool = False,
) -> dict[str, Any]:
    """Run preflight checks and return the report dict (no I/O side effects)."""
    import importlib.util
    import shutil as _shutil

    checks: list[dict[str, Any]] = []

    def _add(name: str, status: str, message: str, fix: str | None = None) -> None:
        entry: dict[str, Any] = {"name": name, "status": status, "message": message}
        if fix:
            entry["fix"] = fix
        checks.append(entry)

    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 11):
        _add("python", "pass", f"Python {major}.{minor}")
    else:
        _add("python", "fail", f"Python {major}.{minor} < 3.11", "pyenv install 3.11")

    git = _shutil.which("git")
    _add("git", "pass" if git else "fail", git or "not found", None if git else "brew install git")

    core_deps = {"typer": "typer", "httpx": "httpx", "yaml": "pyyaml"}
    all_ok = all(importlib.util.find_spec(mod) for mod in core_deps)
    _add("core_deps", "pass" if all_ok else "fail", "typer, httpx, pyyaml")

    litellm_ok = importlib.util.find_spec("litellm") is not None
    _add(
        "planner_deps",
        "pass" if litellm_ok else "warn",
        "litellm" if litellm_ok else "litellm not installed",
        "pip install 'spec-orch[planner]'" if not litellm_ok else None,
    )

    dash_mods = {"fastapi": "fastapi", "uvicorn": "uvicorn", "websockets": "websockets"}
    dash_missing = [name for name, mod in dash_mods.items() if not importlib.util.find_spec(mod)]
    if dash_missing:
        _add(
            "dashboard_deps",
            "warn",
            f"missing: {', '.join(dash_missing)}",
            "pip install 'spec-orch[dashboard]'",
        )
    else:
        _add("dashboard_deps", "pass", "fastapi, uvicorn, websockets")

    env_path = root / ".env"
    _add(
        "dotenv",
        "pass" if env_path.exists() else "warn",
        str(env_path) if env_path.exists() else ".env not found",
        "cp .env.example .env && $EDITOR .env" if not env_path.exists() else None,
    )

    llm_key = os.environ.get("SPEC_ORCH_LLM_API_KEY", "")
    _add(
        "llm_api_key",
        "pass" if llm_key else "fail",
        "SPEC_ORCH_LLM_API_KEY is set" if llm_key else "SPEC_ORCH_LLM_API_KEY not set",
        "Edit .env and set SPEC_ORCH_LLM_API_KEY=your-key" if not llm_key else None,
    )

    config_path = root / "spec-orch.toml"
    if config_path.exists():
        try:
            with config_path.open("rb") as f:
                raw = tomllib.load(f)
            _add("config", "pass", f"spec-orch.toml loaded ({len(raw)} sections)")
            planner_cfg = raw.get("planner", {})
            planner_model = planner_cfg.get("model") if isinstance(planner_cfg, dict) else None
            if planner_model:
                _add("planner_model", "pass", f"model = {planner_model}")
            else:
                _add(
                    "planner_model",
                    "warn",
                    "[planner] model not configured",
                    "Run 'spec-orch init --reconfigure' or edit spec-orch.toml",
                )
        except Exception as exc:
            _add("config", "fail", f"Failed to parse: {exc}")
    else:
        _add("config", "fail", "spec-orch.toml not found", "spec-orch init")

    if try_llm and llm_key and litellm_ok:
        try:
            planner = _build_planner_from_toml(root)
            if planner is not None:
                planner.brainstorm(
                    conversation_history=[{"role": "user", "content": "Say OK"}],
                    codebase_context="",
                )
                _add("llm_connectivity", "pass", "LLM responded successfully")
            else:
                _add("llm_connectivity", "warn", "Planner not configured")
        except Exception as exc:
            _add("llm_connectivity", "fail", f"LLM request failed: {exc}")
    elif try_llm:
        _add("llm_connectivity", "warn", "Skipped (missing API key or litellm)")

    counts = {"pass": 0, "warn": 0, "fail": 0}
    for c in checks:
        counts[c["status"]] += 1

    ready: list[str] = []
    not_ready: list[str] = []
    if litellm_ok and llm_key:
        ready.extend(["run", "discuss", "plan"])
    else:
        not_ready.extend(["run", "discuss", "plan"])
    if not dash_missing:
        ready.append("dashboard")
    else:
        not_ready.append("dashboard")
    if os.environ.get("SPEC_ORCH_LINEAR_TOKEN"):
        ready.append("daemon")
    else:
        not_ready.append("daemon")

    report = {
        "checks": checks,
        "summary": counts,
        "ready": ready,
        "not_ready": not_ready,
    }

    report_dir = root / ".spec_orch"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "preflight.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    )

    return report


def _print_preflight(report: dict[str, Any], report_path: Path) -> None:
    """Print preflight report to stdout."""
    for c in report["checks"]:
        line = f"[{c['status'].upper()}] {c['name']}: {c['message']}"
        typer.echo(line)
        if c.get("fix"):
            typer.echo(f"       fix: {c['fix']}")
    counts = report["summary"]
    typer.echo(f"\nPreflight: {counts['pass']} pass, {counts['warn']} warn, {counts['fail']} fail")
    if report.get("ready"):
        typer.echo(f"Ready to use: {', '.join(report['ready'])}")
    if report.get("not_ready"):
        typer.echo(f"Not ready: {', '.join(report['not_ready'])}")
    typer.echo(f"\nReport saved to {report_path}")


def _run_preflight_inline(root: Path) -> None:
    """Run preflight from init — prints results but never fails init."""
    report = _run_preflight(root)
    report_path = root / ".spec_orch" / "preflight.json"
    _print_preflight(report, report_path)


@app.command("preflight")
def preflight_cmd(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
    try_llm: bool = typer.Option(
        False, "--try-llm", help="Send a test request to verify LLM connectivity."
    ),
) -> None:
    """Pre-launch health check: dependencies, config, env, and connectivity."""
    root = Path(repo_root).resolve()
    report = _run_preflight(root, try_llm=try_llm)
    report_path = root / ".spec_orch" / "preflight.json"

    if json_output:
        typer.echo(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_preflight(report, report_path)

    if report["summary"]["fail"] > 0:
        raise typer.Exit(1)


@app.command("tui")
def tui(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8420, "--port", "-p"),
) -> None:
    """Launch the rich terminal UI (requires Node.js)."""
    import shutil
    import subprocess

    tui_dir = Path(__file__).resolve().parent.parent.parent / "packages" / "tui"
    npx = shutil.which("npx")

    if tui_dir.exists() and (tui_dir / "dist" / "index.js").exists():
        node = shutil.which("node")
        if not node:
            typer.echo("Node.js not found. Install it to use the TUI.")
            raise typer.Exit(1)
        subprocess.run(
            [node, str(tui_dir / "dist" / "index.js"), "--host", host, "--port", str(port)],
            check=False,
        )
    elif npx:
        subprocess.run(
            [npx, "@spec-orch/tui", "--host", host, "--port", str(port)],
            check=False,
        )
    else:
        typer.echo("TUI not found. Build with: cd packages/tui && npm install && npm run build")
        raise typer.Exit(1)


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


def _issue_sort_key(issue_id: str) -> list[int | str]:
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", issue_id)
        if part
    ]


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


daemon_app = typer.Typer(help="Daemon process management commands.")
app.add_typer(daemon_app, name="daemon")


@daemon_app.command("start")
def daemon_start(
    config: Path = typer.Option(
        "spec-orch.toml", "--config", "-c", help="Path to spec-orch.toml config file."
    ),
    repo_root: Path = typer.Option(".", "--repo-root", "-r", help="Repository root."),
) -> None:
    """Start the SpecOrch daemon (foreground)."""
    import tomllib

    from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon

    try:
        cfg = DaemonConfig.from_toml(config)
        d = SpecOrchDaemon(config=cfg, repo_root=repo_root.resolve())
        d.run()
    except FileNotFoundError:
        typer.echo(f"Config file not found: {config}")
        typer.echo("Run: spec-orch init")
        raise typer.Exit(1) from None
    except tomllib.TOMLDecodeError as exc:
        typer.echo(f"Malformed TOML in {config}: {exc}")
        raise typer.Exit(1) from None
    except (KeyError, ValueError) as exc:
        typer.echo(f"Invalid configuration: {exc}")
        typer.echo("Run: spec-orch doctor")
        raise typer.Exit(1) from None
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(f"Daemon failed: {exc}")
        typer.echo("Run: spec-orch doctor")
        raise typer.Exit(1) from None


@daemon_app.command("stop")
def daemon_stop(
    label: str = typer.Option("com.specorch.daemon", "--label", help="Service label."),
) -> None:
    """Stop the daemon system service."""
    from spec_orch.services.daemon_installer import stop_service

    try:
        if stop_service(label=label):
            typer.echo("Daemon service stopped.")
        else:
            typer.echo("Failed to stop daemon service (may not be running).")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(f"Failed to stop daemon: {exc}")
        typer.echo("Run: spec-orch doctor")
        raise typer.Exit(1) from None


@daemon_app.command("status")
def daemon_status(
    label: str = typer.Option("com.specorch.daemon", "--label", help="Service label."),
    config: Path = typer.Option(
        "spec-orch.toml", "--config", "-c", help="Path to spec-orch.toml config file."
    ),
    repo_root: Path = typer.Option(".", "--repo-root", "-r", help="Repository root."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show daemon status (service + persisted state)."""
    import tomllib

    from spec_orch.services.daemon_installer import service_status

    try:
        info = service_status(label=label)
    except Exception as exc:
        if json_output:
            typer.echo(json.dumps({"error": str(exc)}))
        else:
            typer.echo(f"Failed to query service status: {exc}")
            typer.echo("Run: spec-orch doctor")
        raise typer.Exit(1) from None

    config_status = "ok"
    from spec_orch.services.daemon import DaemonConfig

    try:
        cfg = DaemonConfig.from_toml(config)
        lockfile_dir = cfg.lockfile_dir
    except FileNotFoundError:
        config_status = f"not found ({config})"
        lockfile_dir = ".spec_orch_locks/"
    except tomllib.TOMLDecodeError as exc:
        config_status = f"malformed TOML ({exc})"
        lockfile_dir = ".spec_orch_locks/"
    except (KeyError, ValueError) as exc:
        config_status = f"invalid ({exc})"
        lockfile_dir = ".spec_orch_locks/"

    state_data: dict[str, object] | None = None
    state_error: str | None = None
    state_path = repo_root.resolve() / lockfile_dir / "daemon_state.json"
    if state_path.exists():
        try:
            state_data = json.loads(state_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            state_data = None
            state_error = f"corrupt state file ({exc})"

    def _safe_len(val: object) -> int:
        return len(val) if isinstance(val, (list, tuple)) else 0

    if json_output:
        output: dict[str, object] = {
            "platform": info["platform"],
            "installed": info["installed"],
            "running": info["running"],
            "config": config_status,
        }
        if state_error:
            output["state_error"] = state_error
        elif state_data is not None:
            output["last_poll"] = state_data.get("last_poll", "unknown")
            output["processed_count"] = _safe_len(state_data.get("processed"))
            output["triaged_count"] = _safe_len(state_data.get("triaged"))
        typer.echo(json.dumps(output, indent=2))
        return

    typer.echo(f"Platform:  {info['platform']}")
    typer.echo(f"Installed: {info['installed']}")
    typer.echo(f"Running:   {info['running']}")
    if config_status != "ok":
        typer.echo(f"Config:    {config_status}")
    if state_error:
        typer.echo(f"State:     {state_error}")
    elif state_data is not None:
        typer.echo(f"Last poll: {state_data.get('last_poll', 'unknown')}")
        typer.echo(f"Processed: {_safe_len(state_data.get('processed'))} issues")
        typer.echo(f"Triaged:   {_safe_len(state_data.get('triaged'))} issues")
    else:
        typer.echo("State:     no persisted state found")


@daemon_app.command("health")
def daemon_health(
    repo_root: Path = typer.Option(".", "--repo-root", "-r"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show daemon health from heartbeat file (no service query)."""
    from spec_orch.services.daemon import SpecOrchDaemon

    hb = SpecOrchDaemon.read_heartbeat(repo_root.resolve())
    if json_output:
        typer.echo(json.dumps(hb, indent=2))
        return
    status = hb.get("status", "unknown")
    typer.echo(f"Status:       {status}")
    typer.echo(f"PID:          {hb.get('pid', '-')}")
    typer.echo(f"Timestamp:    {hb.get('timestamp', '-')}")
    typer.echo(f"Age:          {hb.get('age_seconds', '-')}s")
    typer.echo(f"Processed:    {hb.get('processed_count', '-')}")
    typer.echo(f"In progress:  {hb.get('in_progress', [])}")
    typer.echo(f"Dead letter:  {hb.get('dead_letter_count', '-')}")
    if hb.get("last_error"):
        typer.echo(f"Last error:   {hb['last_error']}")
    if status in ("stale", "not_running"):
        raise typer.Exit(1)


@daemon_app.command("dlq")
def daemon_dlq(
    repo_root: Path = typer.Option(".", "--repo-root", "-r"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show dead letter queue contents."""
    from spec_orch.services.daemon import SpecOrchDaemon

    state = SpecOrchDaemon.read_state(repo_root.resolve())
    dlq = state.get("dead_letter", [])
    retry_counts = state.get("retry_counts", {})
    if json_output:
        typer.echo(json.dumps({"dead_letter": dlq, "retry_counts": retry_counts}, indent=2))
        return
    if not dlq:
        typer.echo("Dead letter queue is empty.")
        return
    typer.echo(f"Dead letter queue ({len(dlq)} issues):")
    for issue_id in dlq:
        typer.echo(f"  - {issue_id}")


@daemon_app.command("dlq-retry")
def daemon_dlq_retry(
    issue_id: str = typer.Argument(..., help="Issue ID to move out of DLQ."),
    repo_root: Path = typer.Option(".", "--repo-root", "-r"),
) -> None:
    """Remove an issue from the dead letter queue for retry."""
    from spec_orch.services.daemon import SpecOrchDaemon

    state = SpecOrchDaemon.read_state(repo_root.resolve())
    dlq = set(state.get("dead_letter", []))
    if issue_id not in dlq:
        typer.echo(f"{issue_id} is not in the dead letter queue.")
        raise typer.Exit(1)
    dlq.discard(issue_id)
    state["dead_letter"] = sorted(dlq)
    state.get("retry_counts", {}).pop(issue_id, None)
    processed = set(state.get("processed", []))
    processed.discard(issue_id)
    state["processed"] = sorted(processed)
    state_path = repo_root.resolve() / ".spec_orch_locks" / "daemon_state.json"
    try:
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        typer.echo(f"{issue_id} removed from DLQ. Will be retried on next daemon poll.")
    except OSError as exc:
        typer.echo(f"Failed to update state: {exc}")
        raise typer.Exit(1) from None


@daemon_app.command("install")
def daemon_install(
    config: Path = typer.Option(
        "spec-orch.toml", "--config", "-c", help="Path to spec-orch.toml config file."
    ),
    repo_root: Path = typer.Option(".", "--repo-root", "-r", help="Repository root."),
    label: str = typer.Option("com.specorch.daemon", "--label", help="Service label."),
) -> None:
    """Install the daemon as a system service (systemd/launchd)."""
    from spec_orch.services.daemon_installer import install_service

    path = install_service(
        repo_root=repo_root.resolve(),
        config_path=config.resolve(),
        label=label,
    )
    typer.echo(f"Service installed: {path}")
    typer.echo(f"Start with: spec-orch daemon start --config {config}")
    if "LaunchAgents" in path:
        typer.echo(f"Or via service manager: launchctl load {path}")
    else:
        typer.echo(f"Or via service manager: systemctl --user start {label}")


@config_app.command("check")
def config_check(
    config: Path = typer.Option(
        "spec-orch.toml", "--config", "-c", help="Path to spec-orch.toml config file."
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Validate spec-orch.toml and related external dependencies."""
    import shutil

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
    builder_adapter = (
        builder.get("adapter", "codex_exec") if isinstance(builder, dict) else "codex_exec"
    )
    codex_executable = (
        builder.get("executable") or builder.get("codex_executable", "codex")
        if isinstance(builder, dict)
        else "codex"
    )
    builder_agent = builder.get("agent") if isinstance(builder, dict) else None
    builder_model = builder.get("model") if isinstance(builder, dict) else None
    planner_model = planner.get("model") if isinstance(planner, dict) else None
    planner_api_type = (
        planner.get("api_type", "anthropic") if isinstance(planner, dict) else "anthropic"
    )
    planner_api_key_env = planner.get("api_key_env") if isinstance(planner, dict) else None

    reviewer = raw.get("reviewer", {}) if isinstance(raw, dict) else {}
    reviewer_adapter = reviewer.get("adapter", "local") if isinstance(reviewer, dict) else "local"
    valid_reviewers = {"local", "llm"}
    if reviewer_adapter not in valid_reviewers:
        results.append(
            CheckResult(
                name="reviewer", status="fail", message=f"Unknown adapter: {reviewer_adapter!r}"
            )
        )
    else:
        results.append(
            CheckResult(name="reviewer", status="pass", message=f"Adapter: {reviewer_adapter}")
        )

    results.extend(checker.check_linear(linear_token, linear_team_key))
    results.append(
        checker.check_builder(builder_adapter, codex_executable, builder_agent, builder_model)
    )
    results.extend(checker.check_planner(planner_model, planner_api_key_env, planner_api_type))

    verification = raw.get("verification", {}) if isinstance(raw, dict) else {}
    if isinstance(verification, dict):
        for step_name, cmd_list in verification.items():
            if not isinstance(cmd_list, list) or not cmd_list:
                results.append(
                    CheckResult(
                        name=f"verify:{step_name}",
                        status="warn",
                        message=f"Invalid command definition for {step_name}",
                    )
                )
                continue
            token = cmd_list[0]
            if not isinstance(token, str):
                results.append(
                    CheckResult(
                        name=f"verify:{step_name}",
                        status="warn",
                        message=f"Non-string executable: {token!r}",
                    )
                )
                continue
            exe = token.replace("{python}", sys.executable)
            found = shutil.which(exe)
            if found:
                results.append(
                    CheckResult(
                        name=f"verify:{step_name}",
                        status="pass",
                        message=f"Executable found: {found}",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        name=f"verify:{step_name}",
                        status="fail",
                        message=f"Executable not found: {exe}",
                    )
                )

    if json_output:
        checks = [{"name": r.name, "status": r.status, "message": r.message} for r in results]
        counts = {"pass": 0, "warn": 0, "fail": 0}
        for r in results:
            counts[r.status] = counts.get(r.status, 0) + 1
        typer.echo(json.dumps({"checks": checks, "summary": counts}, indent=2))
    else:
        _print_check_report(results)

    if any(r.status == "fail" for r in results):
        raise typer.Exit(1)


@app.command("doctor")
def doctor_cmd(
    config: Path = typer.Option(
        "spec-orch.toml", "--config", "-c", help="Path to spec-orch.toml config file."
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
    fix_hints: bool = typer.Option(False, "--fix-hints", help="Show fix commands."),
) -> None:
    """Comprehensive health check (superset of config check)."""
    from spec_orch.services.doctor import Doctor

    doc = Doctor(config_path=config)
    health_path = doc.write_health_file()

    if json_output:
        import json as _json

        data = doc.to_json()
        typer.echo(_json.dumps(data, indent=2))
        summary = data.get("summary", {})
        if isinstance(summary, dict) and summary.get("fail", 0) > 0:
            raise typer.Exit(1)
        return

    checks = doc.run_all()
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for check in checks:
        counts[check.status] += 1
        line = f"[{check.status.upper()}] {check.name}: {check.message}"
        typer.echo(line)
        if fix_hints and check.fix_hint:
            typer.echo(f"       fix: {check.fix_hint}")
    typer.echo(f"Doctor: {counts['pass']} pass, {counts['warn']} warn, {counts['fail']} fail")
    typer.echo(f"Health report: {health_path}")
    if counts["fail"] > 0:
        raise typer.Exit(1)


@app.command("selftest")
def selftest_cmd(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Run end-to-end smoke test using a fixture issue (plan through gate)."""
    root = Path(repo_root).resolve()

    report = _run_preflight(root)
    if report["summary"]["fail"] > 0:
        typer.echo("Selftest aborted: preflight has failures. Run 'spec-orch preflight' first.")
        raise typer.Exit(1)

    fixture_dir = root / ".spec_orch_runs" / "__selftest__"
    fixture_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []

    def _step(name: str, fn: Any) -> bool:
        try:
            fn()
            results.append({"step": name, "status": "pass"})
            return True
        except Exception as exc:
            results.append({"step": name, "status": "fail", "error": str(exc)})
            return False

    fixture_src = FixtureIssueSource(repo_root=root)
    fixture_issue = None

    def load_fixture() -> None:
        nonlocal fixture_issue
        fixtures_dir = root / "fixtures" / "issues"
        if not fixtures_dir.is_dir():
            raise RuntimeError(f"No fixture issues found. Create {fixtures_dir} with JSON files.")
        json_files = sorted(fixtures_dir.glob("*.json"))
        if not json_files:
            raise RuntimeError(f"No fixture issues found in {fixtures_dir}.")
        issue_id = json_files[0].stem
        fixture_issue = fixture_src.load(issue_id)

    _step("load_fixture", load_fixture)

    if fixture_issue is not None:
        planner = _build_planner_from_toml(root)
        if planner is not None:

            def plan_step() -> None:
                planner.brainstorm(
                    conversation_history=[
                        {"role": "user", "content": f"Analyze: {fixture_issue.title}"}
                    ],
                    codebase_context="selftest",
                )

            _step("planner_call", plan_step)
        else:
            results.append(
                {"step": "planner_call", "status": "skip", "error": "planner not configured"}
            )

    from spec_orch.services.doctor import Doctor

    doc = Doctor(config_path=root / "spec-orch.toml")
    _step("doctor", lambda: doc.run_all())

    counts = {"pass": 0, "fail": 0, "skip": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    selftest_report = {"steps": results, "summary": counts}
    report_dir = root / ".spec_orch"
    report_dir.mkdir(parents=True, exist_ok=True)
    selftest_path = report_dir / "selftest.json"
    selftest_path.write_text(json.dumps(selftest_report, indent=2, ensure_ascii=False) + "\n")

    if json_output:
        typer.echo(json.dumps(selftest_report, indent=2, ensure_ascii=False))
    else:
        for r in results:
            typer.echo(f"[{r['status'].upper()}] {r['step']}")
            if r.get("error"):
                typer.echo(f"       {r['error']}")
        typer.echo(
            f"\nSelftest: {counts['pass']} pass, {counts.get('fail', 0)} fail, "
            f"{counts.get('skip', 0)} skip"
        )
        typer.echo(f"Report: {selftest_path}")

    if counts.get("fail", 0) > 0:
        raise typer.Exit(1)


compliance_app = typer.Typer(help="Compliance evaluation commands.")
app.add_typer(compliance_app, name="compliance")


@compliance_app.command("evaluate")
def compliance_evaluate(
    events_file: Path = typer.Argument(
        ...,
        help="Path to builder events JSONL or report.json.",
    ),
    contracts: Path = typer.Option(
        "compliance.contracts.yaml",
        "--contracts",
        "-c",
        help="Path to compliance contracts YAML.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write compliance_report.json to this path.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Evaluate builder events against compliance contracts."""
    from spec_orch.domain.models import BuilderEvent
    from spec_orch.services.compliance_engine import (
        ConfigurableComplianceEngine,
    )

    engine = ConfigurableComplianceEngine.from_yaml(contracts)

    events: list[BuilderEvent] = []
    if not events_file.exists():
        typer.echo(f"Warning: events file not found: {events_file}", err=True)
    else:
        skipped = 0
        for line in events_file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
                kind = raw.get("kind") or raw.get("method") or raw.get("type", "")
                text = raw.get("text") or raw.get("excerpt") or ""
                if not text and "item" in raw:
                    text = str(raw["item"])
                events.append(
                    BuilderEvent(
                        timestamp=raw.get("timestamp", ""),
                        kind=kind,
                        text=text,
                    )
                )
            except json.JSONDecodeError:
                skipped += 1
                continue
        if skipped:
            typer.echo(
                f"Warning: {skipped} malformed line(s) skipped",
                err=True,
            )

    report = engine.evaluate(events)

    if output:
        report.save(output)
        typer.echo(f"Report saved to {output}")

    if json_output:
        typer.echo(json.dumps(report.to_dict(), indent=2))
    else:
        status = "COMPLIANT" if report.compliant else "NON-COMPLIANT"
        typer.echo(f"Status: {status}")
        typer.echo(f"Errors: {report.error_count}  Warnings: {report.warning_count}")
        for r in report.results:
            icon = "✅" if r.passed else ("❌" if r.severity == "error" else "⚠️")
            typer.echo(f"  {icon} [{r.severity}] {r.contract_name}")
            for v in r.violations[:3]:
                excerpt = v.get("excerpt", v.get("text", ""))[:80]
                typer.echo(f"     → {excerpt}")


@compliance_app.command("list-contracts")
def compliance_list_contracts(
    contracts: Path = typer.Option(
        "compliance.contracts.yaml",
        "--contracts",
        "-c",
        help="Path to compliance contracts YAML.",
    ),
) -> None:
    """List all configured compliance contracts."""
    from spec_orch.services.compliance_engine import load_contracts

    loaded = load_contracts(contracts)
    if not loaded:
        typer.echo("No contracts found.")
        return
    for c in loaded:
        typer.echo(f"  [{c.severity}] {c.id}: {c.name}")
        if c.description:
            typer.echo(f"    {c.description.strip()[:100]}")


gate_app = typer.Typer(help="Gate evaluation commands.")
app.add_typer(gate_app, name="gate")


@gate_app.command("evaluate")
def gate_evaluate(
    issue_id: str = typer.Argument(default="", help="Issue ID to evaluate gate for."),
    repo_root: Path = typer.Option(".", "--repo-root", "-r"),
    policy: Path = typer.Option(
        "gate.policy.yaml", "--policy", "-p", help="Path to gate.policy.yaml."
    ),
    profile: str = typer.Option(
        "", "--profile", help="Gate profile to apply (e.g. daemon, ci, strict)."
    ),
    report_file: Path | None = typer.Option(
        None, "--report", help="Path to report.json (overrides issue workspace)."
    ),
    output_json: bool = typer.Option(False, "--json", help="Output in JSON format."),
) -> None:
    """Evaluate the gate for an issue or report file."""
    from spec_orch.services.gate_service import GateService

    gate_policy = _load_gate_policy(policy, profile)
    svc = GateService(policy=gate_policy)

    if not issue_id and report_file is None:
        typer.echo("provide an issue_id or --report")
        raise typer.Exit(1)

    if report_file is not None:
        result_file = Path(report_file)
    else:
        ws = WorkspaceService(repo_root=Path(repo_root))
        workspace = ws.issue_workspace_path(issue_id)
        result_file = workspace / "report.json"

    if not result_file.exists():
        typer.echo(f"report not found: {result_file}")
        raise typer.Exit(1)

    data = json.loads(result_file.read_text())
    gate_input = _build_gate_input_from_report(data)
    verdict = svc.evaluate(gate_input)
    auto_merge = svc.should_auto_merge(gate_input)

    if output_json:
        typer.echo(
            json.dumps(
                {
                    "issue_id": issue_id or data.get("issue_id", ""),
                    "mergeable": verdict.mergeable,
                    "failed_conditions": verdict.failed_conditions,
                    "auto_merge": auto_merge,
                    "profile": profile or "default",
                },
                indent=2,
            )
        )
        return

    label = issue_id or result_file.parent.name
    typer.echo(f"{label}: mergeable={verdict.mergeable}")
    if verdict.failed_conditions:
        typer.echo(f"  blocked: {', '.join(verdict.failed_conditions)}")
    else:
        typer.echo("  all conditions passed")
    typer.echo(f"  auto_merge: {gate_policy.auto_merge} (would_trigger={auto_merge})")
    if profile:
        typer.echo(f"  profile: {profile}")


@gate_app.command("show-policy")
def gate_show_policy(
    policy: Path = typer.Option(
        "gate.policy.yaml", "--policy", "-p", help="Path to gate.policy.yaml."
    ),
    profile: str = typer.Option("", "--profile", help="Apply a profile before showing."),
    output_json: bool = typer.Option(False, "--json", help="Output in JSON format."),
) -> None:
    """Print the current gate policy."""
    from spec_orch.services.gate_service import GateService

    gate_policy = _load_gate_policy(policy, profile)
    svc = GateService(policy=gate_policy)

    if output_json:
        typer.echo(json.dumps(svc.describe_as_dict(), indent=2))
    else:
        typer.echo(svc.describe_policy())
        if profile:
            typer.echo(f"\n  (profile '{profile}' applied)")


@gate_app.command("list-conditions")
def gate_list_conditions(
    policy: Path = typer.Option(
        "gate.policy.yaml", "--policy", "-p", help="Path to gate.policy.yaml."
    ),
) -> None:
    """List all known gate conditions and their status."""
    from spec_orch.services.gate_service import ALL_KNOWN_CONDITIONS

    gate_policy = _load_gate_policy(policy, "")
    for cond in sorted(ALL_KNOWN_CONDITIONS):
        status = "required" if cond in gate_policy.required_conditions else "optional"
        typer.echo(f"  {cond:25s} [{status}]")


@gate_app.command("profiles")
def gate_list_profiles(
    policy: Path = typer.Option(
        "gate.policy.yaml", "--policy", "-p", help="Path to gate.policy.yaml."
    ),
) -> None:
    """List available gate profiles."""
    gate_policy = _load_gate_policy(policy, "")
    profiles = gate_policy.available_profiles()
    if not profiles:
        typer.echo("no profiles defined")
        return
    for pname in profiles:
        pcfg = gate_policy.profiles[pname]
        disables = pcfg.get("disable", [])
        enables = pcfg.get("enable", [])
        am = pcfg.get("auto_merge", "inherit")
        parts = []
        if disables:
            parts.append(f"disable=[{','.join(disables)}]")
        if enables:
            parts.append(f"enable=[{','.join(enables)}]")
        parts.append(f"auto_merge={am}")
        typer.echo(f"  {pname:15s} {' '.join(parts)}")


def _load_gate_policy(
    policy_path: Path,
    profile: str,
) -> Any:
    from spec_orch.services.gate_service import GatePolicy

    if Path(policy_path).exists():
        gate_policy = GatePolicy.from_yaml(Path(policy_path))
    else:
        gate_policy = GatePolicy.default()
    if profile:
        gate_policy = gate_policy.with_profile(profile)
    return gate_policy


def _build_gate_input_from_report(data: dict[str, Any]) -> Any:
    """Construct a GateInput from a report.json dict."""
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

    _fail = VerificationDetail(command=[], exit_code=1, stdout="", stderr="")
    details = {
        name: VerificationDetail(
            command=detail.get("command", []),
            exit_code=detail.get("exit_code", 1),
            stdout="",
            stderr="",
        )
        for name, detail in verification_data.items()
    }
    verification = VerificationSummary(details=details)
    for name, detail in details.items():
        verification.set_step_passed(name, detail.exit_code == 0)
    review = ReviewSummary(
        verdict=review_data.get("verdict", "pending"),
        reviewed_by=review_data.get("reviewed_by"),
    )
    return GateInput(
        spec_exists=True,
        spec_approved=True,
        within_boundaries=True,
        builder_succeeded=builder_data.get("succeeded", False),
        verification=verification,
        review=review,
        human_acceptance=acceptance_data.get("accepted", False),
    )


@app.command("watch")
def watch_issue(
    issue_id: str,
    repo_root: Path = typer.Option(".", "--repo-root", "-r"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Keep watching even after log ends."),
    tail: int = typer.Option(0, "--tail", "-n", help="Show last N lines only (0 = all)."),
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
    filter_type: str = typer.Option("", "--filter", help="Filter by event type substring."),
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
    typer.echo(f"Summary: {counts['pass']} pass, {counts['warn']} warn, {counts['fail']} fail")


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

    evidence_ctx: str | None = None
    try:
        from spec_orch.services.evidence_analyzer import EvidenceAnalyzer

        analyzer = EvidenceAnalyzer(Path(repo_root))
        summary = analyzer.analyze()
        if summary.total_runs > 0:
            evidence_ctx = analyzer.format_as_llm_context(summary)
    except (OSError, ValueError) as exc:
        typer.echo(f"[plan] evidence analysis skipped: {exc}", err=True)

    hints_ctx: str | None = None
    try:
        from spec_orch.services.plan_strategy_evolver import PlanStrategyEvolver

        strategy_evolver = PlanStrategyEvolver(Path(repo_root))
        hints_ctx = strategy_evolver.format_hints_for_prompt() or None
    except (OSError, ValueError) as exc:
        typer.echo(f"[plan] scoper hints skipped: {exc}", err=True)

    scoper = LiteLLMScoperAdapter(
        model=planner_cfg.get("model", "claude-sonnet-4-20250514"),
        api_type=planner_cfg.get("api_type", "anthropic"),
        api_key=planner_cfg.get("api_key"),
        api_base=planner_cfg.get("api_base"),
        token_command=planner_cfg.get("token_command"),
        evidence_context=evidence_ctx,
        scoper_hints=hints_ctx,
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
    typer.echo(f"plan generated: {len(plan.waves)} waves, {total_packets} work packets")
    for w in plan.waves:
        typer.echo(f"  wave {w.wave_number}: {w.description} ({len(w.work_packets)} packets)")
    _show_next_step(mission_id, Path(repo_root))


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
    _show_next_step(mission_id, Path(repo_root))


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

    linear_client = None
    linear_token = os.environ.get("SPEC_ORCH_LINEAR_TOKEN")
    if linear_token:
        from spec_orch.services.linear_client import LinearClient

        linear_client = LinearClient(token=linear_token)

    try:
        svc = PromotionService(linear_client=linear_client)
        plan = svc.promote(plan)
        save_plan(plan, plan_path)
    finally:
        if linear_client is not None:
            linear_client.close()

    total = sum(len(w.work_packets) for w in plan.waves)
    typer.echo(f"promoted {total} work packets to execution")
    for w in plan.waves:
        for p in w.work_packets:
            typer.echo(f"  {p.linear_issue_id}: {p.title}")
    _show_next_step(mission_id, Path(repo_root))


def _show_next_step(mission_id: str, repo_root: Path) -> None:
    """Print the next pipeline step hint after a command completes."""
    from spec_orch.services.pipeline_checker import next_step

    nxt = next_step(mission_id, repo_root)
    if nxt:
        typer.echo(f"\n>> next: {nxt.label}  ({nxt.command_hint})")


@app.command("pipeline")
def pipeline_status(
    mission_id: str = typer.Argument(..., help="Mission ID to check."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Show the EODF pipeline progress for a mission."""
    from spec_orch.services.pipeline_checker import check_pipeline, format_pipeline

    stages = check_pipeline(mission_id, Path(repo_root))
    typer.echo(f"Pipeline: {mission_id}\n")
    typer.echo(format_pipeline(stages))

    done = sum(1 for s in stages if s.status == "done")
    typer.echo(f"\n{done}/{len(stages)} stages complete")


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
            f"- **{issue_id}**: {data.get('title', '')} | state={state} | mergeable={mergeable}"
        )
        deviations = load_deviations(issue_dir)
        if deviations:
            total_deviations += len(deviations)
            for d in deviations:
                retro_lines.append(f"  - [{d.severity}] {d.description} ({d.resolution})")

    retro_lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Total deviations: {total_deviations}",
            f"- Issues processed: {issues_included}",
        ]
    )

    retro_content = "\n".join(retro_lines) + "\n"
    retro_path = Path(repo_root) / "docs/specs" / mission_id / "retrospective.md"
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
    if planner_cfg.get("api_type"):
        result["api_type"] = planner_cfg["api_type"]
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
    template: str | None = typer.Option(
        None,
        "--template",
        help="Create from an existing mission's spec (mission ID).",
    ),
    from_example: str | None = typer.Option(
        None,
        "--from-example",
        help="Reverse-engineer spec from a local file (JSON/MD/TXT).",
    ),
    from_url: str | None = typer.Option(
        None,
        "--from-url",
        help="Reverse-engineer spec from a URL.",
    ),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Create a new Mission with a canonical spec skeleton.

    Optionally use --template, --from-example, or --from-url (mutually exclusive)
    to seed the spec from existing content.
    """
    from spec_orch.services.mission_service import MissionService

    sources = [s for s in (template, from_example, from_url) if s is not None]
    if len(sources) > 1:
        typer.echo(
            "Error: --template, --from-example, and --from-url are mutually exclusive.",
            err=True,
        )
        raise typer.Exit(code=1)

    svc = MissionService(repo_root=Path(repo_root))

    if template is not None:
        try:
            m = svc.create_mission_from_template(title, template, mission_id=mission_id)
        except (FileNotFoundError, ValueError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    elif from_example is not None:
        example_path = Path(from_example)
        if not example_path.exists():
            typer.echo(f"Error: file not found: {from_example}", err=True)
            raise typer.Exit(code=1)
        content = example_path.read_text()
        planner = _build_planner_from_toml(Path(repo_root))
        m = svc.create_mission_from_example(title, content, mission_id=mission_id, planner=planner)
    elif from_url is not None:
        try:
            import httpx

            resp = httpx.get(from_url, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            content = resp.text
        except Exception as exc:
            typer.echo(f"Error fetching URL: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        planner = _build_planner_from_toml(Path(repo_root))
        m = svc.create_mission_from_example(title, content, mission_id=mission_id, planner=planner)
    else:
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
    _show_next_step(m.mission_id, Path(repo_root))


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
    from spec_orch.services.adapter_factory import (
        create_builder,
        create_issue_source,
        create_reviewer,
    )

    toml_raw = _load_toml_raw(repo_root)
    if codex_executable != "codex":
        builder_cfg = toml_raw.setdefault("builder", {})
        builder_cfg["executable"] = codex_executable
        builder_cfg.setdefault("adapter", "codex_exec")

    issue_source = create_issue_source(repo_root, toml_override=toml_raw, source_override=source)

    planner = _build_planner_from_toml(repo_root)
    builder = create_builder(repo_root, toml_override=toml_raw)
    reviewer = create_reviewer(repo_root, toml_override=toml_raw)

    return RunController(
        repo_root=repo_root,
        builder_adapter=builder,
        issue_source=issue_source,
        planner_adapter=planner,
        review_adapter=reviewer,
        live_stream=live_stream,
    )


def _load_toml_raw(repo_root: Path) -> dict[str, Any]:
    """Load spec-orch.toml as raw dict. Returns empty dict on failure."""
    config_path = repo_root / "spec-orch.toml"
    if not config_path.exists():
        return {}
    try:
        import tomllib

        with config_path.open("rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


_planner_logger = _logging.getLogger("spec_orch.cli.planner")


def _require_planner(repo_root: Path) -> Any:
    """Build planner or exit with actionable error if unavailable."""
    planner = _build_planner_from_toml(repo_root)
    if planner is None:
        typer.echo("Planner not available. Possible causes:")
        typer.echo("  1. litellm not installed      → pip install 'spec-orch[planner]'")
        typer.echo("  2. [planner] model not set     → spec-orch init --reconfigure")
        typer.echo("  3. API key not configured      → edit .env, set SPEC_ORCH_LLM_API_KEY")
        typer.echo("Run 'spec-orch preflight' for full diagnostics.")
        raise typer.Exit(1)
    return planner


def _build_planner_from_toml(repo_root: Path) -> Any:
    """Build a PlannerAdapter from spec-orch.toml if planner section exists."""
    config_path = repo_root / "spec-orch.toml"
    if not config_path.exists():
        _planner_logger.info("spec-orch.toml not found at %s; planner disabled", config_path)
        return None
    try:
        import tomllib

        with config_path.open("rb") as f:
            raw = tomllib.load(f)
    except Exception:
        _planner_logger.warning("Failed to parse %s; planner disabled", config_path, exc_info=True)
        return None

    planner_cfg = raw.get("planner", {})
    model = planner_cfg.get("model")
    if not model:
        _planner_logger.info(
            "[planner] model not set in spec-orch.toml; planner disabled. "
            "Fix: run 'spec-orch init --reconfigure' or edit spec-orch.toml."
        )
        return None

    api_key: str | None = None
    api_key_env = planner_cfg.get("api_key_env")
    if api_key_env:
        api_key = os.environ.get(api_key_env)
        if not api_key:
            _planner_logger.warning(
                "Environment variable %s is not set; LLM calls will fail. "
                "Fix: edit .env and set %s=your-key",
                api_key_env,
                api_key_env,
            )

    api_base: str | None = None
    api_base_env = planner_cfg.get("api_base_env")
    if api_base_env:
        api_base = os.environ.get(api_base_env)

    token_command = planner_cfg.get("token_command")
    api_type = planner_cfg.get("api_type", "anthropic")

    try:
        from spec_orch.services.litellm_planner_adapter import LiteLLMPlannerAdapter

        return LiteLLMPlannerAdapter(
            model=model,
            api_type=api_type,
            api_key=api_key,
            api_base=api_base,
            token_command=token_command,
        )
    except ImportError:
        _planner_logger.warning(
            "litellm not installed; planner disabled. Fix: pip install 'spec-orch[planner]'"
        )
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
        api_type = planner_cfg.get("api_type", "anthropic")

        from spec_orch.services.litellm_planner_adapter import LiteLLMPlannerAdapter

        api_key = os.environ.get(api_key_env) if api_key_env else None
        if not api_key and not token_command:
            hint_env = api_key_env or "SPEC_ORCH_LLM_API_KEY"
            typer.echo(
                f"Warning: environment variable '{hint_env}' is not set.\n"
                f"  The LLM planner will not work until you provide an API key.\n"
                f"  Option 1: Add to .env file   →  {hint_env}=your-key\n"
                f"  Option 2: Export in shell     →  export {hint_env}=your-key\n"
                f'  Option 3: Set token_command   →  [planner] token_command = "..."\n',
            )

        return LiteLLMPlannerAdapter(
            model=model,
            api_type=api_type,
            api_key=api_key,
            api_base=os.environ.get(api_base_env) if api_base_env else None,
            token_command=token_command,
        )
    except (ImportError, FileNotFoundError, tomllib.TOMLDecodeError):
        return None


@discuss_app.callback(invoke_without_command=True)
def discuss_tui(
    ctx: typer.Context,
    channel: str = typer.Option(
        "cli",
        "--channel",
        "-c",
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
        try:
            reply = svc.handle_message(msg)
        except Exception as exc:
            error_message = f"\n[error] {type(exc).__name__}: {exc}\n"
            if planner:
                hint = (
                    "Hint: check your .env file or environment variables.\n"
                    "Run `spec-orch config check` for a configuration health check."
                )
            else:
                hint = "An unexpected error occurred. This might be a bug in spec-orch."
            typer.echo(error_message + hint, err=True)
            continue
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


@evidence_app.command("summary")
def evidence_summary(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Show aggregate pattern summary from historical run data."""
    from spec_orch.services.evidence_analyzer import EvidenceAnalyzer

    analyzer = EvidenceAnalyzer(repo_root)
    summary = analyzer.analyze()
    typer.echo(analyzer.format_summary(summary))


@harness_app.command("synthesize")
def harness_synthesize(
    last_n: int = typer.Option(20, "--last-n", "-n", help="Number of recent runs to analyse."),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write candidates YAML to file."
    ),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Synthesize candidate compliance rules from recent failure patterns."""
    from spec_orch.services.harness_synthesizer import HarnessSynthesizer

    planner = _build_planner_from_toml(repo_root)

    synth = HarnessSynthesizer(repo_root, planner=planner)
    candidates = synth.synthesize(last_n=last_n)

    if not candidates:
        typer.echo("No candidate rules generated.")
        return

    yaml_str = synth.format_candidates_yaml(candidates)
    typer.echo(yaml_str)

    if output:
        output.write_text(yaml_str)
        typer.echo(f"Candidates written to {output}")


def _load_candidate_rules(input_file: Path) -> list[Any]:
    """Load CandidateRule objects from a YAML file."""
    from spec_orch.services.harness_synthesizer import CandidateRule

    raw = yaml.safe_load(input_file.read_text())
    if not isinstance(raw, dict) or not isinstance(raw.get("contracts"), list):
        typer.echo("No valid contracts list found in input file.", err=True)
        raise typer.Exit(1)

    candidates: list[CandidateRule] = []
    for c in raw["contracts"]:
        if not isinstance(c, dict) or "id" not in c or "name" not in c:
            typer.echo(f"Skipping malformed entry: {c!r}", err=True)
            continue
        candidates.append(
            CandidateRule(
                id=c["id"],
                name=c["name"],
                description=c.get("description", ""),
                severity=c.get("severity", "warning"),
                patterns=c.get("patterns", []),
                check_fields=c.get("check_fields", ["text"]),
            )
        )
    return candidates


@harness_app.command("validate")
def harness_validate(
    input_file: Path = typer.Option(..., "--input", "-i", help="Path to candidates YAML file."),
    threshold: float = typer.Option(0.1, "--threshold", "-t", help="Max false positive rate."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Validate candidate rules from a YAML file against historical data."""
    from spec_orch.services.harness_synthesizer import RuleValidator

    candidates = _load_candidate_rules(input_file)
    validator = RuleValidator(repo_root)
    accepted, rejected = validator.validate(candidates, max_false_positive_rate=threshold)

    if accepted:
        typer.echo(f"Accepted ({len(accepted)}):")
        for r in accepted:
            typer.echo(f"  [{r.severity}] {r.id}: {r.name}")
    if rejected:
        typer.echo(f"Rejected ({len(rejected)}):")
        for r in rejected:
            typer.echo(f"  [{r.severity}] {r.id}: {r.name}")

    if not accepted and not rejected:
        typer.echo("No candidates to validate.")


@harness_app.command("apply")
def harness_apply(
    input_file: Path = typer.Option(..., "--input", "-i", help="Path to candidates YAML file."),
    contracts: Path = typer.Option(
        "compliance.contracts.yaml", "--contracts", "-c", help="Path to contracts YAML."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without modifying."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Apply validated rules to compliance.contracts.yaml."""
    from spec_orch.services.harness_synthesizer import RuleValidator

    candidates = _load_candidate_rules(input_file)

    validator = RuleValidator(repo_root)
    accepted, rejected = validator.validate(candidates)
    if rejected:
        typer.echo(f"Skipping {len(rejected)} invalid rule(s):", err=True)
        for r in rejected:
            typer.echo(f"  {r.id}: {r.name}", err=True)

    summary = validator.apply(accepted, contracts, dry_run=dry_run)
    typer.echo(summary)


@strategy_app.command("status")
def strategy_status(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Show current scoper hints."""
    from spec_orch.services.plan_strategy_evolver import PlanStrategyEvolver

    evolver = PlanStrategyEvolver(repo_root)
    hint_set = evolver.load_hints()

    if not hint_set.hints:
        typer.echo("No scoper hints found. Run 'spec-orch strategy analyze' to generate.")
        return

    if hint_set.analysis_summary:
        typer.echo(f"Summary: {hint_set.analysis_summary}")
    typer.echo(f"Hints ({len(hint_set.hints)}):")
    for h in hint_set.hints:
        active = " [active]" if h.is_active else " [inactive]"
        typer.echo(f"  {h.hint_id}{active} [{h.confidence}]: {h.text}")
        if h.evidence:
            typer.echo(f"    evidence: {h.evidence}")


@strategy_app.command("analyze")
def strategy_analyze(
    last_n: int = typer.Option(20, "--last-n", "-n", help="Number of recent runs to analyse."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Use LLM to analyze plan outcomes and generate scoper hints."""
    from spec_orch.services.plan_strategy_evolver import PlanStrategyEvolver

    planner = _build_planner_from_toml(repo_root)
    evolver = PlanStrategyEvolver(repo_root, planner=planner)
    result = evolver.analyze(last_n=last_n)

    if result is None:
        typer.echo("Could not generate hints. Check planner config and run data.")
        return

    typer.echo(f"Generated {len(result.hints)} hint(s):")
    for h in result.hints:
        typer.echo(f"  [{h.confidence}] {h.hint_id}: {h.text}")
    if result.analysis_summary:
        typer.echo(f"\nSummary: {result.analysis_summary}")


@strategy_app.command("inject-preview")
def strategy_inject_preview(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Preview the text that would be injected into the scoper prompt."""
    from spec_orch.services.plan_strategy_evolver import PlanStrategyEvolver

    evolver = PlanStrategyEvolver(repo_root)
    text = evolver.format_hints_for_prompt()

    if not text:
        typer.echo("No active hints to inject.")
        return

    typer.echo(text)


@policy_app.command("list")
def policy_list(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """List all registered policies."""
    from spec_orch.services.policy_distiller import PolicyDistiller

    distiller = PolicyDistiller(repo_root)
    policies = distiller.load_policies()

    if not policies:
        typer.echo("No policies found. Run 'spec-orch policy distill' to create one.")
        return

    for p in policies:
        active = " [active]" if p.is_active else " [inactive]"
        rate = f"{p.success_rate:.0%}" if p.total_executions > 0 else "n/a"
        typer.echo(f"  {p.policy_id}{active}: {p.name} ({p.total_executions} runs, {rate})")
        if p.description:
            typer.echo(f"    {p.description}")


@policy_app.command("candidates")
def policy_candidates(
    min_occurrences: int = typer.Option(3, "--min", "-m", help="Minimum occurrences."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Identify recurring task patterns that could become policies."""
    from spec_orch.services.policy_distiller import PolicyDistiller

    distiller = PolicyDistiller(repo_root)
    candidates = distiller.identify_candidates(min_occurrences=min_occurrences)

    if not candidates:
        typer.echo("No recurring patterns found.")
        return

    for c in candidates:
        typer.echo(f"  {c['pattern']}: {c['occurrences']} occurrences")
        if c.get("examples"):
            for ex in c["examples"]:
                typer.echo(f"    example: {ex}")


@policy_app.command("distill")
def policy_distill(
    task: str | None = typer.Option(None, "--task", "-t", help="Task description to distill."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Generate a deterministic policy for a recurring task."""
    from spec_orch.services.policy_distiller import PolicyDistiller

    planner = _build_planner_from_toml(repo_root)
    distiller = PolicyDistiller(repo_root, planner=planner)
    policy = distiller.distill(task_description=task)

    if policy is None:
        typer.echo("Could not generate a policy. Check planner config and task description.")
        return

    typer.echo(f"Created policy: {policy.policy_id}")
    typer.echo(f"  Name: {policy.name}")
    typer.echo(f"  Script: {policy.script_path}")
    if policy.estimated_savings:
        typer.echo(f"  Estimated savings: {policy.estimated_savings}")


@policy_app.command("run")
def policy_run(
    policy_id: str = typer.Option(..., "--policy", "-p", help="Policy ID to execute."),
    workspace: Path | None = typer.Option(None, "--workspace", "-w", help="Workspace directory."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Execute a policy script."""
    from spec_orch.services.policy_distiller import PolicyDistiller

    distiller = PolicyDistiller(repo_root)
    result = distiller.execute(policy_id, workspace=workspace)

    if result.get("succeeded"):
        typer.echo(f"Policy {policy_id} executed successfully.")
        if result.get("stdout"):
            typer.echo(result["stdout"])
    else:
        typer.echo(f"Policy {policy_id} failed: {result.get('error', 'unknown')}", err=True)
        if result.get("stderr"):
            typer.echo(result["stderr"], err=True)
        raise typer.Exit(1)


@prompt_app.command("init")
def prompt_init(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Initialize prompt history with the current builder prompt as v0."""
    from spec_orch.services.codex_exec_builder_adapter import PREAMBLE
    from spec_orch.services.prompt_evolver import PromptEvolver

    evolver = PromptEvolver(repo_root)
    v0 = evolver.initialize_from_current(PREAMBLE)
    typer.echo(f"Initialized prompt history with {v0.variant_id}")


@prompt_app.command("status")
def prompt_status(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Show current prompt variant status and history."""
    from spec_orch.services.prompt_evolver import PromptEvolver

    evolver = PromptEvolver(repo_root)
    history = evolver.load_history()
    if not history:
        typer.echo("No prompt history found. Run 'spec-orch prompt init' first.")
        return

    for v in history:
        marker = " [ACTIVE]" if v.is_active else " [CANDIDATE]" if v.is_candidate else ""
        rate = f"{v.success_rate:.0%}" if v.total_runs > 0 else "n/a"
        typer.echo(f"  {v.variant_id}{marker}: {v.total_runs} runs, {rate} success")
        if v.rationale:
            typer.echo(f"    rationale: {v.rationale}")


@prompt_app.command("evolve")
def prompt_evolve(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Use LLM to propose an improved builder prompt variant."""
    from spec_orch.services.prompt_evolver import PromptEvolver

    planner = _build_planner_from_toml(repo_root)
    evolver = PromptEvolver(repo_root, planner=planner)
    new_variant = evolver.evolve()

    if new_variant is None:
        typer.echo("Could not generate a new variant. Check planner config and prompt history.")
        return

    typer.echo(f"New candidate: {new_variant.variant_id}")
    typer.echo(f"Rationale: {new_variant.rationale}")
    if new_variant.target_improvements:
        typer.echo("Target improvements:")
        for imp in new_variant.target_improvements:
            typer.echo(f"  - {imp}")


@prompt_app.command("compare")
def prompt_compare(
    variant_a: str = typer.Option(..., "--a", help="First variant ID."),
    variant_b: str = typer.Option(..., "--b", help="Second variant ID."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Compare two prompt variants' performance."""
    from spec_orch.services.prompt_evolver import PromptEvolver

    evolver = PromptEvolver(repo_root)
    result = evolver.compare_variants(variant_a, variant_b)

    if result is None:
        typer.echo("Cannot compare: variants not found or insufficient run data.")
        return

    typer.echo(
        f"Winner: {result.winner_id} "
        f"({result.winner_success_rate:.0%} over {result.winner_runs} runs)"
    )
    typer.echo(
        f"Loser:  {result.loser_id} ({result.loser_success_rate:.0%} over {result.loser_runs} runs)"
    )
    typer.echo(f"Confidence: {result.confidence}")


@prompt_app.command("promote")
def prompt_promote(
    variant_id: str = typer.Option(..., "--variant", "-v", help="Variant ID to promote."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Promote a prompt variant to active."""
    from spec_orch.services.prompt_evolver import PromptEvolver

    evolver = PromptEvolver(repo_root)
    if evolver.promote(variant_id):
        typer.echo(f"Promoted {variant_id} to active.")
    else:
        typer.echo(f"Variant {variant_id} not found.", err=True)
        raise typer.Exit(1)


@prompt_app.command("auto-promote")
def prompt_auto_promote(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Auto-promote candidate if it outperforms the active variant."""
    from spec_orch.services.prompt_evolver import PromptEvolver

    evolver = PromptEvolver(repo_root)
    result = evolver.auto_promote_if_ready()

    if result is None:
        typer.echo("No candidate ready for comparison or no active variant.")
        return

    typer.echo(f"Winner: {result.winner_id} ({result.winner_success_rate:.0%})")
    typer.echo(f"Loser:  {result.loser_id} ({result.loser_success_rate:.0%})")
    active = evolver.get_active_prompt()
    if active:
        typer.echo(f"Active variant is now: {active.variant_id}")


# ---------------------------------------------------------------------------
# Memory commands
# ---------------------------------------------------------------------------

memory_app = typer.Typer(help="Memory subsystem — unified knowledge store.")
app.add_typer(memory_app, name="memory")


@memory_app.command("list")
def memory_list(
    layer: str = typer.Option("", help="Filter by layer (working/episodic/semantic/procedural)"),
    tag: str = typer.Option("", help="Filter by tag"),
    limit: int = typer.Option(50, help="Max entries to show"),
    repo_root: str = typer.Option(".", help="Repository root"),
) -> None:
    """List memory entry keys."""
    from spec_orch.services.memory.service import get_memory_service

    svc = get_memory_service(repo_root=Path(repo_root).resolve())
    tag_list = [tag] if tag else None
    summaries = svc.list_summaries(layer=layer or None, tags=tag_list, limit=limit)
    if not summaries:
        typer.echo("No entries found.")
        return
    for s in summaries:
        tags_str = ", ".join(s.get("tags", [])) or "-"
        typer.echo(f"  [{s['layer']:11s}] {s['key']}  ({tags_str})")


@memory_app.command("show")
def memory_show(
    key: str = typer.Argument(..., help="Entry key to display"),
    repo_root: str = typer.Option(".", help="Repository root"),
) -> None:
    """Display a single memory entry."""
    from spec_orch.services.memory.service import get_memory_service

    svc = get_memory_service(repo_root=Path(repo_root).resolve())
    entry = svc.get(key)
    if entry is None:
        typer.echo(f"Entry '{key}' not found.", err=True)
        raise typer.Exit(1)
    typer.echo(f"Key:       {entry.key}")
    typer.echo(f"Layer:     {entry.layer.value}")
    typer.echo(f"Tags:      {', '.join(entry.tags) or '-'}")
    typer.echo(f"Created:   {entry.created_at}")
    typer.echo(f"Updated:   {entry.updated_at}")
    if entry.metadata:
        typer.echo(f"Metadata:  {entry.metadata}")
    typer.echo(f"\n{entry.content}")


@memory_app.command("search")
def memory_search(
    query: str = typer.Argument(..., help="Search text"),
    layer: str = typer.Option("", help="Filter by layer"),
    limit: int = typer.Option(10, help="Max results"),
    repo_root: str = typer.Option(".", help="Repository root"),
) -> None:
    """Search memory entries by keyword."""
    from spec_orch.services.memory.service import get_memory_service
    from spec_orch.services.memory.types import MemoryLayer, MemoryQuery

    svc = get_memory_service(repo_root=Path(repo_root).resolve())
    q = MemoryQuery(text=query, top_k=limit)
    if layer:
        q.layer = MemoryLayer(layer)
    results = svc.recall(q)
    if not results:
        typer.echo("No results.")
        return
    for entry in results:
        snippet = entry.content[:120].replace("\n", " ")
        typer.echo(f"  [{entry.layer.value:11s}] {entry.key}")
        typer.echo(f"    {snippet}{'…' if len(entry.content) > 120 else ''}")


@memory_app.command("import")
def memory_import(
    repo_root: str = typer.Option(".", help="Repository root"),
) -> None:
    """Import existing implicit memory (prompt history, hints, reports, policies)."""
    from spec_orch.services.memory.migration import import_all
    from spec_orch.services.memory.service import get_memory_service

    root = Path(repo_root).resolve()
    svc = get_memory_service(repo_root=root)
    counts = import_all(svc.provider, root)
    total = sum(counts.values())
    typer.echo(f"Imported {total} entries:")
    for cat, n in counts.items():
        typer.echo(f"  {cat}: {n}")


@memory_app.command("forget")
def memory_forget(
    key: str = typer.Argument(..., help="Entry key to delete"),
    repo_root: str = typer.Option(".", help="Repository root"),
) -> None:
    """Delete a memory entry."""
    from spec_orch.services.memory.service import get_memory_service

    svc = get_memory_service(repo_root=Path(repo_root).resolve())
    if svc.forget(key):
        typer.echo(f"Deleted: {key}")
    else:
        typer.echo(f"Not found: {key}")


_OPENSPEC_LAYER_MAP = {
    "spec.md": "semantic",
    "prd.md": "semantic",
    "proposal.md": "semantic",
    "design.md": "semantic",
    "tasks.md": "procedural",
}


@memory_app.command("ingest-openspec")
def memory_ingest_openspec(
    openspec_dir: str = typer.Option("openspec", help="Path to openspec directory"),
    repo_root: str = typer.Option(".", help="Repository root"),
) -> None:
    """Ingest OpenSpec artifacts (specs, contracts, evidence) into Memory.

    Layer mapping:
      spec.md / prd.md / proposal.md / design.md → Semantic
      tasks.md / contracts/*.md                   → Procedural
      evidence/*.md                               → Episodic
    """
    from spec_orch.services.memory.service import get_memory_service
    from spec_orch.services.memory.types import MemoryEntry, MemoryLayer

    root = Path(repo_root).resolve()
    svc = get_memory_service(repo_root=root)
    odir = root / openspec_dir / "changes"

    if not odir.is_dir():
        typer.echo(f"No changes directory at {odir}", err=True)
        raise typer.Exit(1)

    counts: dict[str, int] = {"semantic": 0, "episodic": 0, "procedural": 0}

    for change_dir in sorted(odir.iterdir()):
        if not change_dir.is_dir():
            continue
        change_name = change_dir.name

        for filename, layer_str in _OPENSPEC_LAYER_MAP.items():
            fpath = change_dir / filename
            if not fpath.is_file():
                continue
            content = fpath.read_text(encoding="utf-8")
            key = f"openspec-{change_name}-{fpath.stem}"
            entry = MemoryEntry(
                key=key,
                content=content,
                layer=MemoryLayer(layer_str),
                tags=["openspec", f"change:{change_name}", fpath.stem],
                metadata={
                    "change": change_name,
                    "file": filename,
                    "source": str(fpath.relative_to(root)),
                },
            )
            svc.store(entry)
            counts[layer_str] += 1

        contracts_dir = change_dir / "contract"
        if not contracts_dir.is_dir():
            contracts_dir = change_dir.parent.parent / "contracts"
        if contracts_dir.is_dir():
            for cpath in sorted(contracts_dir.glob("*.md")):
                if change_name not in cpath.stem and contracts_dir.name == "contracts":
                    continue
                content = cpath.read_text(encoding="utf-8")
                key = f"openspec-contract-{cpath.stem}"
                entry = MemoryEntry(
                    key=key,
                    content=content,
                    layer=MemoryLayer.PROCEDURAL,
                    tags=["openspec", "contract", f"change:{change_name}"],
                    metadata={
                        "change": change_name,
                        "file": cpath.name,
                        "source": str(cpath.relative_to(root)),
                    },
                )
                svc.store(entry)
                counts["procedural"] += 1

        evidence_dir = change_dir / "evidence"
        if evidence_dir.is_dir():
            for epath in sorted(evidence_dir.glob("*.md")):
                content = epath.read_text(encoding="utf-8")
                key = f"openspec-evidence-{epath.stem}"
                entry = MemoryEntry(
                    key=key,
                    content=content,
                    layer=MemoryLayer.EPISODIC,
                    tags=["openspec", "evidence", f"change:{change_name}", epath.stem],
                    metadata={
                        "change": change_name,
                        "file": epath.name,
                        "source": str(epath.relative_to(root)),
                    },
                )
                svc.store(entry)
                counts["episodic"] += 1

    top_contracts = root / openspec_dir / "contracts"
    if top_contracts.is_dir():
        for cpath in sorted(top_contracts.glob("*.md")):
            content = cpath.read_text(encoding="utf-8")
            key = f"openspec-contract-{cpath.stem}"
            entry = MemoryEntry(
                key=key,
                content=content,
                layer=MemoryLayer.PROCEDURAL,
                tags=["openspec", "contract", cpath.stem],
                metadata={"file": cpath.name, "source": str(cpath.relative_to(root))},
            )
            svc.store(entry)
            counts["procedural"] += 1

    total = sum(counts.values())
    typer.echo(f"Ingested {total} OpenSpec entries into Memory:")
    for layer_name, n in counts.items():
        typer.echo(f"  {layer_name}: {n}")


@contract_app.command("generate")
def contract_generate(
    issue_id: str = typer.Argument(help="Issue identifier (e.g. SPC-1)"),
    output: str = typer.Option("", help="Output file path (default: stdout)"),
    repo_root: str = typer.Option("", help="Repository root (default: cwd)"),
) -> None:
    """Generate a TaskContract from an issue definition."""
    from spec_orch.domain.task_contract import generate_contract_from_issue

    root = Path(repo_root) if repo_root else Path.cwd()
    source = FixtureIssueSource(repo_root=root)
    issue = source.load(issue_id)
    contract = generate_contract_from_issue(issue)

    errors = contract.validate()
    if errors:
        for err in errors:
            typer.echo(f"  WARNING: {err}", err=True)

    data = contract.to_dict()
    content = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)

    if output:
        Path(output).write_text(content)
        typer.echo(f"Contract written to {output}")
    else:
        typer.echo(content)


@contract_app.command("validate")
def contract_validate(
    path: str = typer.Argument(help="Path to contract YAML file"),
) -> None:
    """Validate a TaskContract YAML file."""
    from spec_orch.domain.task_contract import TaskContract

    data = yaml.safe_load(Path(path).read_text())
    contract = TaskContract.from_dict(data)
    errors = contract.validate()
    if errors:
        for err in errors:
            typer.echo(f"  ERROR: {err}", err=True)
        raise typer.Exit(1)
    typer.echo(f"Contract {contract.contract_id} is valid (risk: {contract.risk_level})")


@contract_app.command("assess-risk")
def contract_assess_risk(
    issue_id: str = typer.Argument(help="Issue identifier"),
    repo_root: str = typer.Option("", help="Repository root (default: cwd)"),
) -> None:
    """Assess the risk level of an issue for contract purposes."""
    from spec_orch.domain.task_contract import assess_risk_level

    root = Path(repo_root) if repo_root else Path.cwd()
    source = FixtureIssueSource(repo_root=root)
    issue = source.load(issue_id)
    risk = assess_risk_level(
        title=issue.title,
        summary=issue.summary,
        files_in_scope=list(issue.context.files_to_read),
        run_class=issue.run_class or "",
    )
    typer.echo(f"Issue {issue_id}: risk_level={risk}")


# ── eval commands ────────────────────────────────────────────────────────────


@eval_app.command("run")
def eval_run(
    repo_root: Path = typer.Option(".", "--repo-root", "-r"),
    output: Path = typer.Option("eval_report.json", "--output", "-o", help="Output JSON path."),
    tag: list[str] = typer.Option(
        [], "--tag", "-t", help="Filter by tag=value (e.g. adapter=codex)."
    ),
    output_json: bool = typer.Option(False, "--json", help="Print JSON to stdout."),
) -> None:
    """Evaluate historical runs and produce a quality report."""
    from spec_orch.services.eval_runner import EvalRunner

    filter_tags: dict[str, str] = {}
    for t in tag:
        if "=" in t:
            k, v = t.split("=", 1)
            filter_tags[k.strip()] = v.strip()

    runner = EvalRunner(repo_root)
    report = runner.evaluate(filter_tags=filter_tags or None)
    runner.write_report(report, output)

    if output_json:
        typer.echo(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        typer.echo(
            f"Eval: {report.total} runs, {report.passed} passed, "
            f"{report.failed} failed — pass rate {report.pass_rate:.1%}"
        )
        if report.failure_breakdown:
            typer.echo("Failure breakdown:")
            for reason, count in sorted(report.failure_breakdown.items(), key=lambda x: -x[1]):
                typer.echo(f"  {reason}: {count}")
        if report.adapter_breakdown:
            typer.echo("Adapter breakdown:")
            for adapter, stats in sorted(report.adapter_breakdown.items()):
                total = stats.get("total", 0)
                ok = stats.get("passed", 0)
                rate = ok / total if total else 0
                typer.echo(f"  {adapter}: {ok}/{total} ({rate:.0%})")
        typer.echo(f"Report written to {output}")


@eval_app.command("compare")
def eval_compare(
    baseline: Path = typer.Argument(..., help="Baseline eval_report.json"),
    candidate: Path = typer.Argument(..., help="Candidate eval_report.json"),
) -> None:
    """Compare two eval reports (A/B or regression check)."""
    import json as _json

    def _load(p: Path) -> dict[str, Any]:
        data: dict[str, Any] = _json.loads(p.read_text(encoding="utf-8"))
        return data

    b = _load(baseline)
    c = _load(candidate)
    b_rate = b.get("pass_rate", 0)
    c_rate = c.get("pass_rate", 0)
    delta = c_rate - b_rate
    arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "=")

    typer.echo(f"Baseline:  {b.get('total', 0)} runs, pass rate {b_rate:.1%}")
    typer.echo(f"Candidate: {c.get('total', 0)} runs, pass rate {c_rate:.1%}")
    typer.echo(f"Delta:     {delta:+.1%} {arrow}")

    b_avr = b.get("avg_verification_rate", 0)
    c_avr = c.get("avg_verification_rate", 0)
    typer.echo(f"Avg verify: {b_avr:.1%} → {c_avr:.1%}")

    b_dev = b.get("avg_deviation_count", 0)
    c_dev = c.get("avg_deviation_count", 0)
    typer.echo(f"Avg deviations: {b_dev:.1f} → {c_dev:.1f}")

    eval_regression_threshold = -0.05
    if delta < eval_regression_threshold:
        typer.echo(f"⚠ Candidate regressed by more than {-eval_regression_threshold:.0%}")
        raise typer.Exit(1)


def main() -> None:
    app()


@eval_app.command("degradation")
def eval_degradation(
    repo_root: Path = typer.Option(".", "--repo-root", "-r"),
    recent: int = typer.Option(10, "--recent", help="Recent window size."),
    baseline: int = typer.Option(30, "--baseline", help="Baseline window size."),
    threshold: float = typer.Option(0.10, "--threshold", help="Regression threshold."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write JSON report."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Detect quality degradation by comparing recent runs against baseline."""
    from spec_orch.services.degradation_detector import DegradationDetector

    detector = DegradationDetector(
        repo_root.resolve(),
        recent_window=recent,
        baseline_window=baseline,
        threshold=threshold,
    )
    report = detector.detect()

    if output:
        detector.write_report(report, output)

    if json_output:
        typer.echo(json.dumps(report.to_dict(), indent=2))
    elif not report.degraded:
        typer.echo(
            f"No degradation detected. "
            f"(baseline={report.baseline_runs} runs, recent={report.recent_runs} runs)"
        )
    else:
        typer.echo(f"⚠️  Degradation detected ({len(report.signals)} signal(s)):")
        for sig in report.signals:
            typer.echo(
                f"  - {sig.metric}: {sig.baseline_value:.3f} → {sig.recent_value:.3f} "
                f"(Δ={sig.delta:+.3f}, severity={sig.severity})"
            )

    if report.degraded:
        raise typer.Exit(1)


# ── evolution commands ──


@evolution_app.command("status")
def evolution_status(
    repo_root: Path = typer.Option(".", "--repo-root", "-r"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show evolution pipeline status: policy rules, recent activity, and proposals."""
    import tomllib as _tomllib

    from spec_orch.services.evolution_policy import EvolutionPolicy

    repo = repo_root.resolve()
    toml_path = repo / "spec-orch.toml"
    toml_data: dict[str, Any] = {}
    if toml_path.exists():
        with toml_path.open("rb") as f:
            toml_data = _tomllib.load(f)

    policy = EvolutionPolicy.from_toml(toml_data)

    import contextlib

    log_path = repo / ".spec_orch_evolution" / "evolution_log.jsonl"
    recent_runs: list[dict[str, Any]] = []
    if log_path.exists():
        lines = log_path.read_text().strip().splitlines()
        for line in lines[-5:]:
            with contextlib.suppress(json.JSONDecodeError):
                recent_runs.append(json.loads(line))

    counter_path = repo / ".spec_orch_evolution" / "run_counter.json"
    current_count = 0
    if counter_path.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            current_count = json.loads(counter_path.read_text()).get("count", 0)

    status_data = {
        "global_min_runs": policy.global_min_runs,
        "current_run_count": current_count,
        "policy_rules": {
            name: {
                "enabled": rule.enabled,
                "min_runs": rule.min_runs,
                "trigger_on": rule.trigger_on,
                "threshold": rule.threshold,
            }
            for name, rule in policy.rules.items()
        },
        "recent_cycles": recent_runs,
    }

    if json_output:
        typer.echo(json.dumps(status_data, indent=2))
        return

    typer.echo(f"Evolution Pipeline Status (counter: {current_count}/{policy.global_min_runs})")
    typer.echo()

    if policy.rules:
        typer.echo("Policy Rules:")
        for name, rule in policy.rules.items():
            flag = "✅" if rule.enabled else "❌"
            typer.echo(
                f"  {flag} {name}: trigger_on={rule.trigger_on}, "
                f"min_runs={rule.min_runs}, threshold={rule.threshold}"
            )
    else:
        typer.echo("Policy Rules: (none configured, using defaults)")

    if recent_runs:
        typer.echo()
        typer.echo("Recent Cycles:")
        for entry in recent_runs:
            ts = entry.get("timestamp", "?")[:19]
            triggered = "triggered" if entry.get("triggered") else "skipped"
            errors = entry.get("errors", [])
            err_txt = f" ({len(errors)} error(s))" if errors else ""
            typer.echo(f"  [{ts}] {triggered}{err_txt}")


if __name__ == "__main__":
    main()
