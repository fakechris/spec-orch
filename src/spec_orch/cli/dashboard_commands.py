from __future__ import annotations

import time
import tomllib
from pathlib import Path

import typer

from spec_orch.cli import app
from spec_orch.cli._helpers import (
    ProfileLevel,
    _print_jsonl,
    _run_preflight_inline,
)
from spec_orch.services.env_files import find_dotenv_path
from spec_orch.services.workspace_service import WorkspaceService


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

    env_path = find_dotenv_path(root)
    local_env_path = root / ".env"
    if env_path is None:
        example_path = root / ".env.example"
        if example_path.exists():
            import shutil as _shutil

            _shutil.copy2(example_path, local_env_path)
            typer.echo(f"Copied {example_path} → {local_env_path}")
            typer.echo("Edit .env to set your API keys before using spec-orch.")
        else:
            typer.echo("Tip: create a .env file with SPEC_ORCH_LLM_API_KEY=your-key")
    elif env_path != local_env_path:
        typer.echo(f"Using shared env file: {env_path}")

    typer.echo("\nRunning preflight check...")
    _run_preflight_inline(root)


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

    dash_app = create_app(repo_root=Path(repo_root).resolve())
    typer.echo(f"dashboard: http://{host}:{port}")
    uvicorn.run(dash_app, host=host, port=port, log_level="warning")


@app.command("tui")
def tui(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8420, "--port", "-p"),
) -> None:
    """Launch the rich terminal UI (requires Node.js)."""
    import shutil
    import subprocess

    tui_dir = Path(__file__).resolve().parent.parent.parent.parent / "packages" / "tui"
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
