"""MemoryService — singleton façade for the memory subsystem.

Wraps a :class:`MemoryProvider` and hooks into the :class:`EventBus`
to automatically capture mission lifecycle events into episodic memory.

Heavy concerns are delegated to:

* :class:`MemoryAnalytics`  — trend / learning-view queries
* :class:`MemoryDistiller`  — compaction and distillation
* :class:`MemoryRecorder`   — structured lifecycle event writers
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from spec_orch.services.memory._utils import list_summaries_compat
from spec_orch.services.memory.analytics import MemoryAnalytics
from spec_orch.services.memory.distiller import MemoryDistiller
from spec_orch.services.memory.fs_provider import FileSystemMemoryProvider
from spec_orch.services.memory.lifecycle import (
    MemoryLifecycleManager,
    SessionMemorySnapshot,
    SessionSnapshotCadenceDecision,
    SharedMemorySyncEvent,
)
from spec_orch.services.memory.protocol import MemoryProvider
from spec_orch.services.memory.recorder import MemoryRecorder
from spec_orch.services.memory.types import MemoryEntry, MemoryLayer, MemoryQuery

logger = logging.getLogger(__name__)

_DEFAULT_MEMORY_DIR = ".spec_orch_memory"

_instance: MemoryService | None = None


class MemoryService:
    """High-level façade over a pluggable :class:`MemoryProvider`.

    Also subscribes to the ``EventBus`` so that mission/issue state
    changes are transparently recorded in episodic memory.
    """

    def __init__(
        self,
        provider: MemoryProvider | None = None,
        *,
        repo_root: Path | None = None,
        qdrant_config: dict[str, Any] | None = None,
        derivation_mode: str = "sync",
    ) -> None:
        if provider is not None:
            self._provider = provider
            self._memory_root: Path = getattr(
                provider, "root", (repo_root or Path.cwd()) / _DEFAULT_MEMORY_DIR
            )
        else:
            self._memory_root = (repo_root or Path.cwd()) / _DEFAULT_MEMORY_DIR
            self._provider = _build_provider(self._memory_root, qdrant_config)
        self._derivation_mode = derivation_mode
        self._derivation_queue: Any = None
        self._derivation_worker: Any = None
        self._analytics = MemoryAnalytics(self._provider)
        self._distiller = MemoryDistiller(self._provider)
        self._recorder = MemoryRecorder(self._provider)
        self._lifecycle = MemoryLifecycleManager(self._memory_root / "_lifecycle", self._provider)

    @property
    def provider(self) -> MemoryProvider:
        return self._provider

    @property
    def derivation_mode(self) -> str:
        return self._derivation_mode

    # -- delegated CRUD ------------------------------------------------------

    def store(self, entry: MemoryEntry) -> str:
        key = self._provider.store(entry)
        self._emit("memory.stored", {"key": key, "layer": entry.layer.value})
        return key

    def recall(self, query: MemoryQuery) -> list[MemoryEntry]:
        results = self._provider.recall(query)
        self._emit("memory.recalled", {"query_text": query.text, "count": len(results)})
        return results

    def forget(self, key: str) -> bool:
        removed = self._provider.forget(key)
        if removed:
            self._emit("memory.forgotten", {"key": key})
        return removed

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
        """Return index-only summaries (no file I/O per entry)."""
        return list_summaries_compat(
            self._provider, layer=layer, tags=tags, limit=limit, created_after=created_after
        )

    # -- derivation ----------------------------------------------------------

    def _ensure_derivation_queue(self) -> Any:
        """Lazily create the derivation queue and worker."""
        if self._derivation_queue is not None:
            return self._derivation_queue
        from spec_orch.services.memory.derivation import (
            DerivationQueue,
            DerivationWorker,
        )

        db_path = self._memory_root / "_derivation.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._derivation_queue = DerivationQueue(db_path)
        self._derivation_worker = DerivationWorker(self._derivation_queue)
        self._register_derivation_handlers()
        return self._derivation_queue

    def _register_derivation_handlers(self) -> None:
        """Register standard derivation task handlers."""
        if self._derivation_worker is None:
            return

        def _handle_compact(payload: dict[str, Any]) -> None:
            self.compact(
                max_age_days=payload.get("max_age_days", 30),
                summarize=payload.get("summarize", True),
                planner_config=payload.get("planner_config"),
            )

        def _handle_profile_refresh(payload: dict[str, Any]) -> None:
            repo_root = Path(payload["repo_root"]) if payload.get("repo_root") else None
            self.get_project_profile(repo_root=repo_root)

        def _handle_stale_cleanup(payload: dict[str, Any]) -> None:
            self._soft_delete_stale_entries(max_age_days=payload.get("max_age_days", 90))

        def _handle_recipe_extraction(payload: dict[str, Any]) -> None:
            entity_id = payload.get("entity_id")
            self.get_success_recipes(entity_id=entity_id, top_k=10)

        def _handle_active_learning_synthesis(payload: dict[str, Any]) -> None:
            kind = str(payload.get("kind", "")).strip().lower()
            if kind:
                self.synthesize_active_learning_slice(kind, top_k=int(payload.get("top_k", 5)))

        self._derivation_worker.register("compact", _handle_compact)
        self._derivation_worker.register("profile-refresh", _handle_profile_refresh)
        self._derivation_worker.register("stale-cleanup", _handle_stale_cleanup)
        self._derivation_worker.register("recipe-extraction", _handle_recipe_extraction)
        self._derivation_worker.register(
            "active-learning-synthesis", _handle_active_learning_synthesis
        )

    def enqueue_derivation(self, task_type: str, payload: dict[str, Any] | None = None) -> str:
        """Enqueue a background derivation task."""
        q = self._ensure_derivation_queue()
        result: str = q.enqueue(task_type, payload)
        return result

    def process_derivations(self, batch_size: int = 5) -> int:
        """Process pending derivation tasks. Returns count processed."""
        self._ensure_derivation_queue()
        if self._derivation_worker is None:
            return 0
        result: int = self._derivation_worker.process_batch(batch_size)
        return result

    def schedule_post_run_derivations(
        self,
        *,
        issue_id: str,
        run_id: str,
        repo_root: Path | None = None,
    ) -> list[str]:
        """Schedule standard post-run derivation tasks.

        In sync mode, executes inline. In async mode, enqueues for later.
        """
        task_ids: list[str] = []
        if self._derivation_mode == "async":
            task_ids.append(
                self.enqueue_derivation("compact", {"max_age_days": 30, "summarize": True})
            )
            task_ids.append(
                self.enqueue_derivation(
                    "profile-refresh",
                    {"repo_root": str(repo_root) if repo_root else ""},
                )
            )
            task_ids.append(self.enqueue_derivation("recipe-extraction", {"entity_id": issue_id}))
            for kind in ("self", "delivery", "feedback"):
                task_ids.append(
                    self.enqueue_derivation(
                        "active-learning-synthesis",
                        {"kind": kind, "top_k": 5},
                    )
                )
        else:
            self.compact(max_age_days=30, summarize=True)
            if repo_root:
                self.get_project_profile(repo_root=repo_root)
            self.get_success_recipes(entity_id=issue_id, top_k=10)
            for kind in ("self", "delivery", "feedback"):
                self.synthesize_active_learning_slice(kind, top_k=5)
        return task_ids

    def _soft_delete_stale_entries(self, *, max_age_days: int = 90) -> int:
        marked = self._distiller.soft_delete_stale_entries(max_age_days=max_age_days)
        self._distiller.gc_superseded(max_age_days=max_age_days)
        return marked

    # -- distillation delegates ----------------------------------------------

    def compact(
        self,
        *,
        max_age_days: int = 30,
        summarize: bool = True,
        planner_config: dict[str, Any] | None = None,
    ) -> dict[str, int]:
        """Remove expired episodic entries, optionally distilling them first."""
        return self._distiller.compact(
            max_age_days=max_age_days,
            summarize=summarize,
            planner_config=planner_config,
        )

    # -- analytics delegates -------------------------------------------------

    def get_trend_summary(self, *, recent_days: int = 7) -> dict[str, Any]:
        return self._analytics.get_trend_summary(recent_days=recent_days)

    def get_active_run_signals(self, days: int = 7) -> dict[str, Any]:
        return self._analytics.get_active_run_signals(days=days)

    def get_failure_patterns(
        self, entity_id: str | None = None, top_k: int = 10
    ) -> list[dict[str, Any]]:
        return self._analytics.get_failure_patterns(entity_id=entity_id, top_k=top_k)

    def get_success_recipes(
        self, entity_id: str | None = None, top_k: int = 5
    ) -> list[dict[str, Any]]:
        return self._analytics.get_success_recipes(entity_id=entity_id, top_k=top_k)

    def get_project_profile(self, repo_root: Path | None = None) -> dict[str, Any]:
        return self._analytics.get_project_profile(repo_root=repo_root)

    def get_reviewed_decision_failures(self, top_k: int = 5) -> list[dict[str, Any]]:
        return self._analytics.get_reviewed_decision_failures(top_k=top_k)

    def get_reviewed_decision_recipes(self, top_k: int = 5) -> list[dict[str, Any]]:
        return self._analytics.get_reviewed_decision_recipes(top_k=top_k)

    def get_reviewed_acceptance_findings(self, top_k: int = 5) -> list[dict[str, Any]]:
        return self._analytics.get_reviewed_acceptance_findings(top_k=top_k)

    def recall_latest_with_provenance(
        self,
        *,
        entity_scope: str,
        entity_id: str,
        layer: MemoryLayer | None = None,
        tags: list[str] | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        return self._analytics.recall_latest_with_provenance(
            entity_scope=entity_scope,
            entity_id=entity_id,
            layer=layer,
            tags=tags,
            top_k=top_k,
        )

    def synthesize_active_learning_slice(
        self,
        kind: str,
        *,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        return self._distiller.synthesize_active_learning_slice(kind, top_k=top_k)

    def get_active_learning_slice(self, kind: str) -> list[dict[str, Any]]:
        entry = self._provider.get(f"active-learning-{kind.strip().lower()}")
        if entry is None:
            return []
        try:
            payload = json.loads(entry.content)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, dict):
            return []
        items = payload.get("items", [])
        return items if isinstance(items, list) else []

    def get_recent_evolution_journal(self, *, limit: int = 5) -> list[dict[str, Any]]:
        query = MemoryQuery(layer=MemoryLayer.EPISODIC, tags=["evolution-journal"], top_k=limit)
        entries = self._provider.recall(query)
        journal: list[dict[str, Any]] = []
        for entry in entries:
            journal.append(
                {
                    "key": entry.key,
                    "evolver_name": entry.metadata.get("evolver_name", ""),
                    "stage": entry.metadata.get("stage", ""),
                    "summary": entry.content,
                    "metadata": entry.metadata,
                }
            )
        return journal

    def get_learning_memory_refs(self, mission_id: str) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        for kind in ("self", "delivery", "feedback"):
            for item in self.get_active_learning_slice(kind):
                if not isinstance(item, dict):
                    continue
                metadata = item.get("metadata", {})
                if not isinstance(metadata, dict):
                    continue
                if str(metadata.get("mission_id", "")) != mission_id:
                    continue
                key = str(item.get("key", "")).strip()
                refs.append(
                    {
                        "memory_ref_id": f"memory-ref:{kind}:{key}",
                        "origin_finding_ref": str(
                            metadata.get("origin_finding_ref") or metadata.get("finding_id") or ""
                        ),
                        "origin_review_ref": str(
                            metadata.get("origin_review_ref") or metadata.get("judgment_id") or ""
                        ),
                        "memory_layer": MemoryLayer.SEMANTIC.value,
                        "distillation_summary": str(item.get("content", ""))[:160],
                        "created_at": str(item.get("created_at", "")),
                        "kind": kind,
                        "source_key": key,
                    }
                )
        refs.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return refs

    # -- lifecycle ----------------------------------------------------------

    def should_snapshot_session(self, event_count: int, *, every_n_events: int = 2) -> bool:
        return self._lifecycle.should_snapshot_session(event_count, every_n_events=every_n_events)

    def evaluate_snapshot_cadence(
        self,
        *,
        event_count: int,
        token_growth: int = 0,
        tool_calls: int = 0,
        natural_break: bool = False,
        every_n_events: int = 2,
    ) -> SessionSnapshotCadenceDecision:
        return self._lifecycle.evaluate_snapshot_cadence(
            event_count=event_count,
            token_growth=token_growth,
            tool_calls=tool_calls,
            natural_break=natural_break,
            every_n_events=every_n_events,
        )

    def record_session_snapshot(
        self,
        *,
        session_id: str,
        subject_kind: str,
        subject_id: str,
        event_count: int,
        facts: list[str],
        artifact_refs: dict[str, str] | None = None,
    ) -> str:
        snapshot = SessionMemorySnapshot(
            snapshot_id=f"{session_id}-{event_count}",
            session_id=session_id,
            subject_kind=subject_kind,
            subject_id=subject_id,
            event_count=event_count,
            facts=list(facts),
            artifact_refs=dict(artifact_refs or {}),
        )
        return self._lifecycle.record_session_snapshot(snapshot)

    def reserve_shared_memory_write(self, freshness_key: str, *, ttl_seconds: int = 3600) -> bool:
        return self._lifecycle.reserve_shared_memory_write(
            freshness_key,
            ttl_seconds=ttl_seconds,
        )

    def consolidation_lock(self, lock_name: str = "consolidation") -> Any:
        return self._lifecycle.consolidation_lock(lock_name)

    def validate_shared_memory_content(
        self,
        *,
        repo_scope: str,
        content: str,
    ) -> tuple[bool, str]:
        return self._lifecycle.validate_shared_memory_content(
            repo_scope=repo_scope,
            content=content,
        )

    def record_shared_memory_sync(
        self,
        *,
        sync_id: str,
        repo_scope: str,
        source: str,
        freshness_key: str,
        content: str,
        status: str = "written",
    ) -> SharedMemorySyncEvent:
        return self._lifecycle.record_shared_memory_sync(
            sync_id=sync_id,
            repo_scope=repo_scope,
            source=source,
            freshness_key=freshness_key,
            content=content,
            status=status,
        )

    # -- recorder delegates --------------------------------------------------

    def consolidate_run(self, **kwargs: Any) -> str | None:
        return self._recorder.consolidate_run(**kwargs)

    def record_builder_telemetry(self, **kwargs: Any) -> str | None:
        return self._recorder.record_builder_telemetry(**kwargs)

    def record_execution_outcome(self, **kwargs: Any) -> str:
        return self._recorder.record_execution_outcome(**kwargs)

    def record_decision_record(self, **kwargs: Any) -> str:
        return self._recorder.record_decision_record(**kwargs)

    def record_decision_review(self, **kwargs: Any) -> str:
        return self._recorder.record_decision_review(**kwargs)

    def record_acceptance_judgments(self, **kwargs: Any) -> list[str]:
        return self._recorder.record_acceptance_judgments(**kwargs)

    def record_acceptance(self, **kwargs: Any) -> str:
        return self._recorder.record_acceptance(**kwargs)

    def record_evolution_journal(self, **kwargs: Any) -> str:
        return self._recorder.record_evolution_journal(**kwargs)

    def recall_latest(
        self,
        *,
        entity_scope: str,
        entity_id: str,
        layer: str | None = None,
        tags: list[str] | None = None,
        top_k: int = 5,
    ) -> list[MemoryEntry]:
        """Recall the most recent entries for a given entity, excluding superseded ones."""
        query = MemoryQuery(
            layer=MemoryLayer(layer) if layer else None,
            tags=tags or [],
            top_k=top_k,
            entity_scope=entity_scope,
            entity_id=entity_id,
            exclude_relation_types=["superseded"],
        )
        return self._provider.recall(query)

    def record_mission_event(
        self,
        mission_id: str,
        phase: str,
        *,
        detail: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return self._recorder.record_mission_event(
            mission_id, phase, detail=detail, metadata=metadata
        )

    def record_issue_completion(
        self,
        issue_id: str,
        *,
        succeeded: bool,
        summary: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        return self._recorder.record_issue_completion(
            issue_id, succeeded=succeeded, summary=summary, metadata=metadata
        )

    # -- EventBus integration ------------------------------------------------

    def subscribe_to_event_bus(self) -> None:
        """Wire up automatic memory capture from EventBus events."""
        try:
            from spec_orch.services.event_bus import EventTopic, get_event_bus

            bus = get_event_bus()
            bus.subscribe(self._on_mission_state, EventTopic.MISSION_STATE)
            bus.subscribe(self._on_issue_state, EventTopic.ISSUE_STATE)
            bus.subscribe(self._on_conductor, EventTopic.CONDUCTOR)
            bus.subscribe(self._on_gate_result, EventTopic.GATE_RESULT)
            logger.info("MemoryService subscribed to EventBus")
        except ImportError:
            logger.debug("EventBus not available, skipping subscription")

    def _on_mission_state(self, event: Any) -> None:
        payload = event.payload if hasattr(event, "payload") else event
        mission_id = payload.get("mission_id", "unknown")
        new_state = payload.get("new_state", "unknown")
        old_state = payload.get("old_state", "")
        detail = f"Transition: {old_state} → {new_state}" if old_state else ""
        self.record_mission_event(mission_id, new_state, detail=detail, metadata=payload)

    def _on_issue_state(self, event: Any) -> None:
        payload = event.payload if hasattr(event, "payload") else event
        issue_id = payload.get("issue_id", "unknown")
        state = payload.get("state", "unknown")
        succeeded = state in ("accepted", "merged")
        if state in ("accepted", "merged", "failed"):
            self.record_issue_completion(issue_id, succeeded=succeeded, metadata=payload)

    def _on_conductor(self, event: Any) -> None:
        payload = event.payload if hasattr(event, "payload") else event
        self._recorder.record_conductor_event(payload)

    def _on_gate_result(self, event: Any) -> None:
        payload = event.payload if hasattr(event, "payload") else event
        self._recorder.record_gate_result(payload)

    # -- EventBus emit helper ------------------------------------------------

    @staticmethod
    def _emit(topic_str: str, payload: dict[str, Any]) -> None:
        try:
            from spec_orch.services.event_bus import Event, EventTopic, get_event_bus

            bus = get_event_bus()
            topic = EventTopic.MEMORY
            bus.publish(
                Event(topic=topic, payload={"sub": topic_str, **payload}, source="memory_service")
            )
        except ImportError:
            pass


def _build_provider(
    root: Path,
    qdrant_config: dict[str, Any] | None,
) -> MemoryProvider:
    """Select the best available MemoryProvider based on config."""
    if qdrant_config:
        try:
            from spec_orch.services.memory.vector_provider import (
                VectorEnhancedProvider,
            )

            return VectorEnhancedProvider(root, qdrant_config=qdrant_config)
        except Exception:
            logger.warning(
                "VectorEnhancedProvider unavailable; falling back to FileSystemMemoryProvider",
                exc_info=True,
            )
    return FileSystemMemoryProvider(root)


def _load_qdrant_config(repo_root: Path) -> dict[str, Any] | None:
    """Read ``[memory.qdrant]`` from spec-orch.toml if present."""
    import tomllib

    toml_path = repo_root / "spec-orch.toml"
    if not toml_path.exists():
        return None
    try:
        with toml_path.open("rb") as f:
            raw = tomllib.load(f)
    except Exception:
        return None
    mem_cfg = raw.get("memory", {})
    if not isinstance(mem_cfg, dict):
        return None
    provider = mem_cfg.get("provider", "")
    if provider not in ("filesystem_qdrant", "vector_enhanced"):
        return None
    return mem_cfg.get("qdrant") if isinstance(mem_cfg.get("qdrant"), dict) else None


def _load_derivation_mode(repo_root: Path) -> str:
    """Read ``[memory].derivation_mode`` from spec-orch.toml if present."""
    import tomllib

    toml_path = repo_root / "spec-orch.toml"
    if not toml_path.exists():
        return "sync"
    try:
        with toml_path.open("rb") as f:
            raw = tomllib.load(f)
    except Exception:
        return "sync"
    mem_cfg = raw.get("memory", {})
    mode = mem_cfg.get("derivation_mode", "sync") if isinstance(mem_cfg, dict) else "sync"
    return mode if mode in ("sync", "async") else "sync"


def get_memory_service(repo_root: Path | None = None) -> MemoryService:
    """Return the global ``MemoryService`` singleton, creating it if needed."""
    global _instance  # noqa: PLW0603
    if _instance is None:
        root = repo_root or Path.cwd()
        qdrant_config = _load_qdrant_config(root)
        derivation_mode = _load_derivation_mode(root)
        _instance = MemoryService(
            repo_root=root,
            qdrant_config=qdrant_config,
            derivation_mode=derivation_mode,
        )
    return _instance


def reset_memory_service() -> None:
    """Reset the singleton (for testing)."""
    global _instance  # noqa: PLW0603
    _instance = None
