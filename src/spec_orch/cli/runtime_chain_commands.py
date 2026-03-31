from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from spec_orch.cli import app
from spec_orch.runtime_chain.models import RuntimeChainEvent, RuntimeChainStatus
from spec_orch.runtime_chain.store import read_chain_events, read_chain_status
from spec_orch.services.workspace_service import WorkspaceService

chain_app = typer.Typer(help="Runtime chain observability and live traceability.")
app.add_typer(chain_app, name="chain")


def _resolve_chain_root(
    *,
    repo_root: Path,
    chain_root: Path | None,
    issue_id: str | None,
    mission_id: str | None,
) -> Path:
    selected = [value for value in (chain_root, issue_id, mission_id) if value is not None]
    if len(selected) != 1:
        raise typer.BadParameter("provide exactly one of --chain-root, --issue-id, or --mission-id")
    if chain_root is not None:
        return chain_root.resolve()
    if issue_id is not None:
        workspace = WorkspaceService(repo_root=repo_root).issue_workspace_path(issue_id)
        return workspace / "telemetry" / "runtime_chain"
    return repo_root / "docs" / "specs" / str(mission_id) / "operator" / "runtime_chain"


def _event_payload(event: RuntimeChainEvent) -> dict[str, Any]:
    return event.to_dict()


def _status_payload(root: Path, status: RuntimeChainStatus | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chain_root": str(root),
        "exists": root.exists(),
    }
    if status is None:
        payload["status"] = "missing"
        return payload
    payload.update(status.to_dict())
    payload["status"] = "present"
    return payload


def _render_text(payload: dict[str, Any]) -> str:
    if payload.get("status") == "missing":
        return f"chain_root={payload['chain_root']} status=missing"
    return " ".join(
        [
            f"chain_root={payload['chain_root']}",
            f"chain_id={payload['chain_id']}",
            f"phase={payload['phase']}",
            f"subject={payload['subject_kind']}:{payload['subject_id']}",
            f"span={payload['active_span_id']}",
            f"reason={payload.get('status_reason') or 'none'}",
        ]
    )


@chain_app.command("status")
def chain_status(
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
    chain_root: Path | None = typer.Option(None, "--chain-root"),
    issue_id: str | None = typer.Option(None, "--issue-id"),
    mission_id: str | None = typer.Option(None, "--mission-id"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show the current runtime chain status snapshot."""
    resolved_root = _resolve_chain_root(
        repo_root=repo_root.resolve(),
        chain_root=chain_root,
        issue_id=issue_id,
        mission_id=mission_id,
    )
    payload = _status_payload(resolved_root, read_chain_status(resolved_root))
    typer.echo(json.dumps(payload, indent=2) if as_json else _render_text(payload))


@chain_app.command("tail")
def chain_tail(
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
    chain_root: Path | None = typer.Option(None, "--chain-root"),
    issue_id: str | None = typer.Option(None, "--issue-id"),
    mission_id: str | None = typer.Option(None, "--mission-id"),
    chain_id: str | None = typer.Option(None, "--chain-id"),
    limit: int = typer.Option(10, "--limit", min=1),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show the latest runtime chain events."""
    resolved_root = _resolve_chain_root(
        repo_root=repo_root.resolve(),
        chain_root=chain_root,
        issue_id=issue_id,
        mission_id=mission_id,
    )
    events = read_chain_events(resolved_root)
    if chain_id:
        events = [event for event in events if event.chain_id == chain_id]
    selected = events[-limit:]
    payload = {
        "chain_root": str(resolved_root),
        "event_count": len(selected),
        "events": [_event_payload(event) for event in selected],
    }
    if as_json:
        typer.echo(json.dumps(payload, indent=2))
        return
    if not selected:
        typer.echo(f"chain_root={resolved_root} events=0")
        return
    for event in selected:
        typer.echo(
            " ".join(
                [
                    f"chain_id={event.chain_id}",
                    f"phase={event.phase.value}",
                    f"subject={event.subject_kind.value}:{event.subject_id}",
                    f"span={event.span_id}",
                    f"reason={event.status_reason or 'none'}",
                ]
            )
        )


@chain_app.command("show")
def chain_show(
    chain_id: str,
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
    chain_root: Path | None = typer.Option(None, "--chain-root"),
    issue_id: str | None = typer.Option(None, "--issue-id"),
    mission_id: str | None = typer.Option(None, "--mission-id"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show all known events for one runtime chain."""
    resolved_root = _resolve_chain_root(
        repo_root=repo_root.resolve(),
        chain_root=chain_root,
        issue_id=issue_id,
        mission_id=mission_id,
    )
    events = [event for event in read_chain_events(resolved_root) if event.chain_id == chain_id]
    latest_event = events[-1].to_dict() if events else None
    current_status = read_chain_status(resolved_root)
    payload: dict[str, Any] = {
        "chain_root": str(resolved_root),
        "chain_id": chain_id,
        "event_count": len(events),
        "latest_event": latest_event,
        "events": [_event_payload(event) for event in events],
    }
    if current_status is not None and current_status.chain_id == chain_id:
        payload["current_status"] = current_status.to_dict()
    if as_json:
        typer.echo(json.dumps(payload, indent=2))
        return
    typer.echo(
        " ".join(
            [
                f"chain_root={resolved_root}",
                f"chain_id={chain_id}",
                f"event_count={len(events)}",
                f"latest_reason={(latest_event or {}).get('status_reason', 'none')}",
            ]
        )
    )
