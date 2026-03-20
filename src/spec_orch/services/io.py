"""Atomic file I/O utilities.

Provides ``atomic_write_json`` and ``atomic_write_text`` which write to a
temporary file first, then use ``os.replace`` (POSIX atomic rename) to
swap into place.  This guarantees that readers never see a partially-written
file — even if the process is killed mid-write.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_json(
    path: Path,
    data: Any,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
    default: Any | None = None,
    trailing_newline: bool = True,
) -> None:
    """Write *data* as JSON to *path* atomically.

    The file is first written to a temporary sibling, flushed + fsynced,
    then renamed over *path*.  On failure the temp file is cleaned up and
    *path* is left untouched.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    kwargs: dict[str, Any] = {
        "indent": indent,
        "ensure_ascii": ensure_ascii,
    }
    if default is not None:
        kwargs["default"] = default

    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, **kwargs)
            if trailing_newline:
                fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
) -> None:
    """Write *text* to *path* atomically (same strategy as ``atomic_write_json``)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
