"""Tests for atomic file I/O utilities."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from unittest.mock import patch

from spec_orch.services.io import atomic_write_json, atomic_write_text


class TestAtomicWriteJson:
    def test_basic_write(self, tmp_path: Path) -> None:
        target = tmp_path / "data.json"
        atomic_write_json(target, {"key": "value"})
        assert target.exists()
        assert json.loads(target.read_text()) == {"key": "value"}

    def test_trailing_newline(self, tmp_path: Path) -> None:
        target = tmp_path / "data.json"
        atomic_write_json(target, {"a": 1})
        assert target.read_text().endswith("\n")

    def test_no_trailing_newline(self, tmp_path: Path) -> None:
        target = tmp_path / "data.json"
        atomic_write_json(target, {"a": 1}, trailing_newline=False)
        assert not target.read_text().endswith("\n")

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "sub" / "dir" / "data.json"
        atomic_write_json(target, [1, 2, 3])
        assert json.loads(target.read_text()) == [1, 2, 3]

    def test_preserves_existing_on_failure(self, tmp_path: Path) -> None:
        target = tmp_path / "data.json"
        target.write_text('{"original": true}\n')

        class BadObj:
            def __repr__(self) -> str:
                raise RuntimeError("serialization bomb")

        with contextlib.suppress(TypeError):
            atomic_write_json(target, BadObj())

        assert json.loads(target.read_text()) == {"original": True}

    def test_overwrite_existing(self, tmp_path: Path) -> None:
        target = tmp_path / "data.json"
        atomic_write_json(target, {"v": 1})
        atomic_write_json(target, {"v": 2})
        assert json.loads(target.read_text()) == {"v": 2}

    def test_ensure_ascii(self, tmp_path: Path) -> None:
        target = tmp_path / "data.json"
        atomic_write_json(target, {"msg": "你好"}, ensure_ascii=True)
        raw = target.read_text()
        assert "\\u" in raw

    def test_default_serializer(self, tmp_path: Path) -> None:
        target = tmp_path / "data.json"
        atomic_write_json(target, {"path": Path("/tmp")}, default=str)
        assert json.loads(target.read_text()) == {"path": "/tmp"}

    def test_no_temp_files_left(self, tmp_path: Path) -> None:
        target = tmp_path / "data.json"
        atomic_write_json(target, {"ok": True})
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name == "data.json"

    def test_no_temp_files_on_failure(self, tmp_path: Path) -> None:
        target = tmp_path / "data.json"
        with contextlib.suppress(TypeError):
            atomic_write_json(target, object())
        tmp_files = [f for f in tmp_path.iterdir() if f.suffix == ".tmp"]
        assert len(tmp_files) == 0


class TestAtomicWriteText:
    def test_basic_write(self, tmp_path: Path) -> None:
        target = tmp_path / "out.txt"
        atomic_write_text(target, "hello world")
        assert target.read_text() == "hello world"

    def test_preserves_on_error(self, tmp_path: Path) -> None:
        target = tmp_path / "out.txt"
        target.write_text("original")

        with (
            patch("spec_orch.services.io.os.fsync", side_effect=OSError("disk full")),
            contextlib.suppress(OSError),
        ):
            atomic_write_text(target, "new content")

        assert target.read_text() == "original"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "out.txt"
        atomic_write_text(target, "nested")
        assert target.read_text() == "nested"
