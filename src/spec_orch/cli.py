from __future__ import annotations

from pathlib import Path

import typer

from spec_orch.services.run_controller import RunController

app = typer.Typer(help="SpecOrch MVP prototype CLI.")


@app.callback()
def cli() -> None:
    """SpecOrch MVP prototype CLI."""


@app.command("run-issue")
def run_issue(
    issue_id: str,
    repo_root: Path = typer.Option(Path("."), "--repo-root"),
) -> None:
    """Run one local issue fixture through the MVP pipeline."""
    controller = RunController(repo_root=repo_root)
    result = controller.run_issue(issue_id)
    typer.echo(
        " ".join(
            [
                f"issue={result.issue.issue_id}",
                f"workspace={result.workspace}",
                f"mergeable={result.gate.mergeable}",
            ]
        )
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
