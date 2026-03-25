from __future__ import annotations

import json
from pathlib import Path

import typer

from spec_orch.cli import app
from spec_orch.services.io import atomic_write_json

daemon_app = typer.Typer(help="Daemon process management commands.")
app.add_typer(daemon_app, name="daemon")


@daemon_app.command("start")
def daemon_start(
    config: Path = typer.Option(
        "spec-orch.toml", "--config", "-c", help="Path to spec-orch.toml config file."
    ),
    repo_root: Path = typer.Option(".", "--repo-root", "-r", help="Repository root."),
    live_mission_workers: bool = typer.Option(
        False,
        "--live-mission-workers",
        help="Stream supervised mission worker events to stderr in foreground mode.",
    ),
) -> None:
    """Start the SpecOrch daemon (foreground)."""
    import tomllib

    from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon

    try:
        cfg = DaemonConfig.from_toml(config)
        d = SpecOrchDaemon(
            config=cfg,
            repo_root=repo_root.resolve(),
            live_mission_workers=live_mission_workers,
        )
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


def _resolve_lockfile_dir(
    config: Path,
    repo_root: Path,
) -> str:
    """Read lockfile_dir from daemon config, falling back to default."""
    from spec_orch.services.daemon import DaemonConfig

    try:
        cfg = DaemonConfig.from_toml(config)
        return cfg.lockfile_dir
    except Exception:
        return ".spec_orch_locks/"


@daemon_app.command("dlq")
def daemon_dlq(
    repo_root: Path = typer.Option(".", "--repo-root", "-r"),
    config: Path = typer.Option("spec-orch.toml", "--config", "-c", help="Path to spec-orch.toml."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show dead letter queue contents."""
    from spec_orch.services.daemon import SpecOrchDaemon

    lockfile_dir = _resolve_lockfile_dir(config, repo_root)
    state = SpecOrchDaemon.read_state(repo_root.resolve(), lockfile_dir=lockfile_dir)
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
    config: Path = typer.Option("spec-orch.toml", "--config", "-c", help="Path to spec-orch.toml."),
) -> None:
    """Remove an issue from the dead letter queue for retry."""
    from spec_orch.services.daemon import SpecOrchDaemon

    lockfile_dir = _resolve_lockfile_dir(config, repo_root)
    state = SpecOrchDaemon.read_state(repo_root.resolve(), lockfile_dir=lockfile_dir)
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
    state_path = repo_root.resolve() / lockfile_dir / "daemon_state.json"
    try:
        atomic_write_json(state_path, state)
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
