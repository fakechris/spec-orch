"""Common protocol for all evolvers."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Evolver(Protocol):
    """Minimal interface shared by all evolvers.

    Each evolver reads historical evidence (from Memory or filesystem),
    produces improvement suggestions, and optionally applies them.
    """

    def evolve(self) -> Any:
        """Analyse evidence and produce an improvement suggestion.

        Returns the suggestion object (type varies per evolver), or
        ``None`` if there is not enough data or the LLM call fails.
        """
        ...
