"""Shared helpers for the memory subsystem."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from spec_orch.services.memory.protocol import MemoryProvider


def list_summaries_compat(
    provider: MemoryProvider,
    *,
    layer: str | None = None,
    tags: list[str] | None = None,
    limit: int = 100,
    created_after: str | None = None,
) -> list[dict[str, Any]]:
    """Return lightweight summaries, with a correct fallback for any provider.

    Prefers the provider's ``list_summaries`` when available (e.g.
    ``FileSystemMemoryProvider`` pushes ``created_after`` into SQL).
    Otherwise falls back to ``list_keys`` + ``get`` so that
    ``created_at`` is always populated from the real entry and
    ``created_after`` filtering still works.
    """
    if hasattr(provider, "list_summaries"):
        result: list[dict[str, Any]] = provider.list_summaries(  # type: ignore[union-attr]
            layer=layer, tags=tags, limit=limit, created_after=created_after
        )
        return result

    keys = provider.list_keys(layer=layer, tags=tags, limit=limit)
    results: list[dict[str, Any]] = []
    for k in keys:
        entry = provider.get(k)
        if entry is None:
            continue
        ca = entry.created_at
        if created_after and ca < created_after:
            continue
        results.append(
            {
                "key": k,
                "layer": entry.layer.value,
                "tags": list(entry.tags),
                "created_at": ca,
                "updated_at": entry.updated_at,
            }
        )
        if len(results) >= limit:
            break
    return results
