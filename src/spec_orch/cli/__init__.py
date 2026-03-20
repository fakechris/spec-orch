from __future__ import annotations

import typer

from spec_orch.cli._helpers import _load_dotenv, _resolve_version, _version_callback

app = typer.Typer(help="SpecOrch MVP prototype CLI.")


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


from spec_orch.cli import (  # noqa: E402
    daemon_commands,
    dashboard_commands,
    diag_commands,
    evolution_commands,
    gate_commands,
    mission_commands,
    run_commands,
    spec_commands,
)

__all__ = [
    "_resolve_version",
    "app",
    "main",
    "daemon_commands",
    "dashboard_commands",
    "diag_commands",
    "evolution_commands",
    "gate_commands",
    "mission_commands",
    "run_commands",
    "spec_commands",
]


def main() -> None:
    app()
