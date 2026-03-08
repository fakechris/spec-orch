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
    pi_executable: str = typer.Option("pi", "--pi-executable"),
) -> None:
    """Run one local issue fixture through the MVP pipeline."""
    controller = RunController(repo_root=repo_root, pi_executable=pi_executable)
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
    pi_executable: str = typer.Option("pi", "--pi-executable"),
) -> None:
    """Record human acceptance for an existing issue run."""
    controller = RunController(repo_root=repo_root, pi_executable=pi_executable)
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
    pi_executable: str = typer.Option("pi", "--pi-executable"),
) -> None:
    """Record review verdict for an existing issue run."""
    controller = RunController(repo_root=repo_root, pi_executable=pi_executable)
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
