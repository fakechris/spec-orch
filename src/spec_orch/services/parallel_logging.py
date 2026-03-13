"""Structured JSON logging for parallel wave execution."""

from __future__ import annotations

import json
import logging
from typing import Any


class ParallelJsonFormatter(logging.Formatter):
    """Emits log records as single-line JSON with wave/packet correlation fields."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "event": record.getMessage(),
            "logger": record.name,
        }
        for field in (
            "wave_id",
            "packet_id",
            "packet_count",
            "concurrency_limit",
            "exit_code",
            "duration_seconds",
            "all_succeeded",
            "wave_count",
            "total_duration",
            "success",
            "signal",
            "count",
            "reason",
        ):
            val = getattr(record, field, None)
            if val is not None:
                entry[field] = val
        return json.dumps(entry, default=str)


def configure_parallel_logging(
    *,
    level: int = logging.INFO,
    log_file: str | None = None,
) -> None:
    """Configure structured JSON logging for the parallel execution modules."""
    formatter = ParallelJsonFormatter()

    handler: logging.Handler = (
        logging.FileHandler(log_file) if log_file else logging.StreamHandler()
    )
    handler.setFormatter(formatter)

    for module in (
        "spec_orch.services.packet_executor",
        "spec_orch.services.wave_executor",
        "spec_orch.services.cancellation_handler",
        "spec_orch.services.parallel_run_controller",
    ):
        mod_logger = logging.getLogger(module)
        mod_logger.setLevel(level)
        mod_logger.addHandler(handler)
        mod_logger.propagate = False
