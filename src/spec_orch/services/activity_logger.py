"""Persistent activity log with optional real-time terminal streaming."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import IO, Any

from spec_orch.services.event_formatter import EventFormatter


class ActivityLogger:
    """Writes formatted events to ``activity.log`` and optionally to a live
    stream (e.g. ``sys.stderr``).

    Thread-safe: the underlying file and stream writes are serialised via a
    lock so the ``event_logger`` callback can be invoked from a reader thread
    safely.
    """

    def __init__(
        self,
        log_path: Path,
        *,
        live_stream: IO[str] | None = None,
        verbose: bool = False,
    ) -> None:
        self._log_path = log_path
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._live_stream = live_stream
        self._formatter = EventFormatter(color=False, verbose=verbose)
        self._live_formatter = EventFormatter(
            color=True, verbose=verbose
        ) if live_stream else None
        self._lock = threading.Lock()
        self._handle = self._log_path.open("a", encoding="utf-8")

    # -- public API -------------------------------------------------------

    def log(self, event: dict[str, Any]) -> None:
        """Format and write *event* to ``activity.log`` and the live stream."""
        plain = self._formatter.format_plain(event)
        if plain is None:
            return

        with self._lock:
            self._handle.write(plain + "\n")
            self._handle.flush()

            if self._live_stream and self._live_formatter:
                colored = self._live_formatter.format(event)
                if colored:
                    try:
                        self._live_stream.write(colored + "\n")
                        self._live_stream.flush()
                    except (BrokenPipeError, OSError):
                        pass

    def close(self) -> None:
        with self._lock:
            self._handle.close()

    # -- convenience ------------------------------------------------------

    @staticmethod
    def activity_log_path(workspace: Path) -> Path:
        return workspace / "telemetry" / "activity.log"

    def __enter__(self) -> ActivityLogger:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
