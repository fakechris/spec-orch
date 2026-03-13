"""CancellationHandler — manages SIGINT/SIGTERM graceful shutdown for parallel execution."""

from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Callable
from types import FrameType
from typing import Any

logger = logging.getLogger(__name__)

_SignalHandler = Callable[[int, FrameType | None], Any] | int | None


class CancellationHandler:
    """Installs signal handlers that set an asyncio.Event on SIGINT/SIGTERM.

    Usage::

        cancel = asyncio.Event()
        handler = CancellationHandler(cancel)
        handler.install()
        # ... run parallel execution with cancel_event=cancel ...
        handler.uninstall()
    """

    def __init__(self, cancel_event: asyncio.Event) -> None:
        self._cancel_event = cancel_event
        self._original_sigint: _SignalHandler = None
        self._original_sigterm: _SignalHandler = None
        self._signal_count = 0

    def install(self) -> None:
        self._original_sigint = signal.getsignal(signal.SIGINT)
        self._original_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGINT, self._handle)
        signal.signal(signal.SIGTERM, self._handle)

    def uninstall(self) -> None:
        if self._original_sigint is not None:
            signal.signal(signal.SIGINT, self._original_sigint)
        if self._original_sigterm is not None:
            signal.signal(signal.SIGTERM, self._original_sigterm)

    def _handle(self, signum: int, frame: FrameType | None) -> None:
        self._signal_count += 1
        sig_name = signal.Signals(signum).name

        if self._signal_count == 1:
            logger.info(
                "cancellation_requested",
                extra={"signal": sig_name},
            )
            self._cancel_event.set()
        elif self._signal_count >= 2:
            logger.warning(
                "forced_exit",
                extra={"signal": sig_name, "count": self._signal_count},
            )
            raise KeyboardInterrupt
