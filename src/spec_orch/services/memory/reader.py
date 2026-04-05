from __future__ import annotations

from typing import Any, cast

from spec_orch.services.memory._utils import list_summaries_compat
from spec_orch.services.memory.analytics import MemoryAnalytics
from spec_orch.services.memory.protocol import MemoryProvider
from spec_orch.services.memory.types import MemoryEntry, MemoryQuery


class MemoryReader:
    """Read-only facade over provider and analytics-backed memory queries."""

    def __init__(
        self,
        *,
        provider: MemoryProvider,
        analytics: MemoryAnalytics,
        service: Any,
    ) -> None:
        self._provider = provider
        self._analytics = analytics
        self._service = service

    def recall(self, query: MemoryQuery) -> list[MemoryEntry]:
        return cast(list[MemoryEntry], self._service.recall(query))

    def get(self, key: str) -> MemoryEntry | None:
        return self._provider.get(key)

    def list_keys(
        self,
        *,
        layer: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[str]:
        return self._provider.list_keys(layer=layer, tags=tags, limit=limit)

    def list_summaries(
        self,
        *,
        layer: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
        created_after: str | None = None,
    ) -> list[dict[str, Any]]:
        return list_summaries_compat(
            self._provider,
            layer=layer,
            tags=tags,
            limit=limit,
            created_after=created_after,
        )

    def get_trend_summary(self, *, recent_days: int = 7) -> dict[str, Any]:
        return self._analytics.get_trend_summary(recent_days=recent_days)

    def get_active_run_signals(self, days: int = 7) -> dict[str, Any]:
        return self._analytics.get_active_run_signals(days=days)

    def __getattr__(self, name: str) -> Any:
        allowed = {
            "get_project_profile",
            "get_success_recipes",
            "get_active_run_signals",
            "get_trend_summary",
            "synthesize_active_learning_slice",
        }
        if name in allowed:
            return getattr(self._service, name)
        raise AttributeError(f"{type(self).__name__!s} has no attribute {name!s}")
