"""Tests for the ConflictResolver service."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from spec_orch.domain.models import BuilderResult, Issue
from spec_orch.services.conflict_resolver import (
    ConflictResolver,
    ConflictResult,
    ConflictType,
)


def _make_issue(issue_id: str = "TST-1") -> Issue:
    return Issue(issue_id=issue_id, title="Test", summary="Test issue")


class TestClassify:
    def test_formatting_conflicts(self, tmp_path: Path) -> None:
        file_a = tmp_path / "src" / "a.py"
        file_a.parent.mkdir(parents=True)
        file_a.write_text(
            "<<<<<<< HEAD\nimport os\nimport sys\n=======\n"
            "import sys\nimport os\n>>>>>>> origin/main\n"
        )
        resolver = ConflictResolver()
        result = resolver.classify(
            ["CONFLICT (content): Merge conflict in src/a.py"],
            tmp_path,
        )
        assert result == ConflictType.FORMATTING

    def test_logic_conflicts(self, tmp_path: Path) -> None:
        file_a = tmp_path / "src" / "service.py"
        file_a.parent.mkdir(parents=True)
        file_a.write_text(
            "class Foo:\n"
            "<<<<<<< HEAD\n"
            "    def compute(self, x):\n"
            "        return x * 2 + self.offset\n"
            "=======\n"
            "    def compute(self, x):\n"
            "        logger.info('computing')\n"
            "        return x + 1\n"
            ">>>>>>> origin/main\n"
        )
        resolver = ConflictResolver()
        result = resolver.classify(
            ["CONFLICT (content): Merge conflict in src/service.py"],
            tmp_path,
        )
        assert result == ConflictType.LOGIC

    def test_architecture_conflicts(self, tmp_path: Path) -> None:
        resolver = ConflictResolver()
        result = resolver.classify(
            ["CONFLICT (content): Merge conflict in pyproject.toml"],
            tmp_path,
        )
        assert result == ConflictType.ARCHITECTURE

    def test_architecture_init_file(self, tmp_path: Path) -> None:
        resolver = ConflictResolver()
        result = resolver.classify(
            ["CONFLICT (content): Merge conflict in src/__init__.py"],
            tmp_path,
        )
        assert result == ConflictType.ARCHITECTURE

    def test_architecture_migrations(self, tmp_path: Path) -> None:
        resolver = ConflictResolver()
        result = resolver.classify(
            ["CONFLICT (content): Merge conflict in migrations/0001.py"],
            tmp_path,
        )
        assert result == ConflictType.ARCHITECTURE

    def test_empty_conflicts(self, tmp_path: Path) -> None:
        resolver = ConflictResolver()
        result = resolver.classify([], tmp_path)
        assert result == ConflictType.LOGIC

    def test_no_markers_in_file(self, tmp_path: Path) -> None:
        file_a = tmp_path / "a.py"
        file_a.write_text("clean content\n")
        resolver = ConflictResolver()
        result = resolver.classify(
            ["CONFLICT (content): Merge conflict in a.py"],
            tmp_path,
        )
        assert result == ConflictType.LOGIC


class TestExtractPaths:
    def test_standard_conflict_line(self) -> None:
        paths = ConflictResolver._extract_paths(
            ["CONFLICT (content): Merge conflict in src/foo.py"]
        )
        assert paths == ["src/foo.py"]

    def test_multiple_conflicts(self) -> None:
        paths = ConflictResolver._extract_paths(
            [
                "CONFLICT (content): Merge conflict in a.py",
                "CONFLICT (modify/delete): b.py deleted in HEAD",
            ]
        )
        assert len(paths) >= 1
        assert "a.py" in paths

    def test_no_match(self) -> None:
        paths = ConflictResolver._extract_paths(["not a conflict line"])
        assert paths == []


class TestResolveTrivial:
    @patch("spec_orch.services.conflict_resolver.subprocess.run")
    def test_trivial_resolve_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        resolver = ConflictResolver()
        result = resolver._resolve_trivial(Path("/fake"))
        assert result.resolved is True
        assert result.method == "trivial"

    @patch("spec_orch.services.conflict_resolver.subprocess.run")
    def test_trivial_resolve_remaining_conflicts(self, mock_run: MagicMock) -> None:
        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if "diff" in cmd and "--diff-filter=U" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout="still_conflicted.py\n",
                    stderr="",
                )
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        resolver = ConflictResolver()
        result = resolver._resolve_trivial(Path("/fake"))
        assert result.resolved is False


class TestResolveWithBuilder:
    def test_no_builder_returns_unavailable(self) -> None:
        resolver = ConflictResolver(builder_adapter=None)
        result = resolver._resolve_with_builder(
            _make_issue(),
            Path("/fake"),
            ["src/a.py"],
        )
        assert result.resolved is False
        assert result.method == "builder_unavailable"

    @patch("spec_orch.services.conflict_resolver.subprocess.run")
    def test_builder_success(self, mock_run: MagicMock) -> None:
        mock_builder = MagicMock()
        mock_builder.run.return_value = BuilderResult(
            succeeded=True,
            command=["test"],
            stdout="",
            stderr="",
            report_path=Path("/fake/report.json"),
            adapter="test",
            agent="test",
        )

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        resolver = ConflictResolver(builder_adapter=mock_builder)
        result = resolver._resolve_with_builder(
            _make_issue(),
            Path("/fake"),
            ["src/a.py"],
        )
        assert result.resolved is True
        assert result.method == "builder"

    @patch("spec_orch.services.conflict_resolver.subprocess.run")
    def test_builder_failure(self, mock_run: MagicMock) -> None:
        mock_builder = MagicMock()
        mock_builder.run.return_value = BuilderResult(
            succeeded=False,
            command=["test"],
            stdout="",
            stderr="error",
            report_path=Path("/fake/report.json"),
            adapter="test",
            agent="test",
        )

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        resolver = ConflictResolver(builder_adapter=mock_builder)
        result = resolver._resolve_with_builder(
            _make_issue(),
            Path("/fake"),
            ["src/a.py"],
        )
        assert result.resolved is False
        assert result.method == "builder"


class TestEscalate:
    def test_escalate_with_linear_client(self) -> None:
        mock_linear = MagicMock()
        mock_linear.find_issue_id.return_value = "uuid-123"
        resolver = ConflictResolver(linear_client=mock_linear)
        resolver._escalate("TST-1", ["CONFLICT in a.py"])
        mock_linear.add_comment.assert_called_once()
        mock_linear.add_label.assert_called_once_with("uuid-123", "conflict")

    def test_escalate_without_linear_client(self) -> None:
        resolver = ConflictResolver(linear_client=None)
        resolver._escalate("TST-1", ["CONFLICT in a.py"])


class TestResolveOrchestration:
    @patch.object(ConflictResolver, "_prepare_conflict_state", return_value=True)
    @patch.object(
        ConflictResolver,
        "_resolve_trivial",
        return_value=ConflictResult(resolved=True, method="trivial"),
    )
    def test_formatting_resolved_trivially(
        self, mock_trivial: MagicMock, mock_prepare: MagicMock, tmp_path: Path
    ) -> None:
        file_a = tmp_path / "a.py"
        file_a.write_text("<<<<<<< HEAD\nimport os\n=======\nimport sys\n>>>>>>> main\n")
        resolver = ConflictResolver()
        result = resolver.resolve(
            issue=_make_issue(),
            workspace=tmp_path,
            conflicting_files=["CONFLICT (content): Merge conflict in a.py"],
        )
        assert result.resolved is True
        assert result.method == "trivial"

    @patch.object(ConflictResolver, "_prepare_conflict_state", return_value=False)
    def test_prepare_failed(self, mock_prepare: MagicMock, tmp_path: Path) -> None:
        resolver = ConflictResolver()
        result = resolver.resolve(
            issue=_make_issue(),
            workspace=tmp_path,
            conflicting_files=["CONFLICT (content): Merge conflict in a.py"],
        )
        assert result.resolved is False
        assert result.method == "prepare_failed"

    @patch.object(ConflictResolver, "_prepare_conflict_state", return_value=True)
    @patch.object(ConflictResolver, "_escalate")
    def test_architecture_escalated(
        self,
        mock_escalate: MagicMock,
        mock_prepare: MagicMock,
        tmp_path: Path,
    ) -> None:
        resolver = ConflictResolver()
        result = resolver.resolve(
            issue=_make_issue(),
            workspace=tmp_path,
            conflicting_files=["CONFLICT (content): Merge conflict in pyproject.toml"],
        )
        assert result.resolved is False
        assert result.method == "escalated"
        mock_escalate.assert_called_once()


class TestConflictResult:
    def test_repr(self) -> None:
        cr = ConflictResult(resolved=True, method="trivial")
        assert "trivial" in repr(cr)
        assert "True" in repr(cr)
