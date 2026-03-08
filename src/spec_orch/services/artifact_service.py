from __future__ import annotations

from pathlib import Path


class ArtifactService:
    def write_initial_artifacts(
        self,
        *,
        workspace: Path,
        issue_id: str,
        issue_title: str,
    ) -> tuple[Path, Path]:
        task_spec = workspace / "task.spec.md"
        progress = workspace / "progress.md"

        task_spec.write_text(
            "\n".join(
                [
                    f"# {issue_title}",
                    "",
                    "## Intent",
                    f"- Issue: {issue_id}",
                    f"- Title: {issue_title}",
                    "",
                    "## Boundaries",
                    "- MVP prototype only",
                ]
            )
            + "\n"
        )
        progress.write_text(
            "\n".join(
                [
                    "# Progress",
                    "",
                    f"- Issue: {issue_id}",
                    "- Status: drafted",
                    "- Next: run local builder adapter",
                ]
            )
            + "\n"
        )

        return task_spec, progress
