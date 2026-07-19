"""
SlowMem0Provider - a controllable Mem0-shaped test double.

Behaviour:
    - ``add_memory`` registers the writer at a per-instance gate
      (``threading.Event``) and blocks until ``release()`` is
      invoked by the test driver.  Once released, the memory is
      committed to an in-memory store.
    - ``retrieve_memory`` consults the post-commit store snapshot
      only - parked-but-uncommitted writes are NOT visible to
      retrieval.  This is the same observable behaviour the real
      kernel exhibits before the write-barrier fix.
    - The double also exposes ``park()`` / ``release()`` /
      ``wait_until_pending(n)`` helpers so tests can deterministically
      surface the write-before-read race.

The double honours the standard ``MemoryProvider`` contract so it can
be plugged into ``MemoryManager`` via ``ProviderFactory.register``.
Cross-agent metadata (``owner_agent`` / ``user_id`` / ``sharing_policy``
/ ``memory_type``) is preserved end-to-end and the same
``_apply_sharing_filter`` / ``_enrich_metadata`` helpers used by
``Mem0Provider`` are applied on retrieval, so retrieval results match
the real Mem0 result shape.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, TYPE_CHECKING

from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from aios.memory.providers.base import (
    MemoryProvider,
    _apply_sharing_filter,
    _enrich_metadata,
)

if TYPE_CHECKING:  # pragma: no cover
    from aios.memory.note import MemoryNote


class SlowMem0Provider(MemoryProvider):
    """A Mem0-shaped provider whose ``add_memory`` blocks on a gate
    event until the test driver releases it."""

    def __init__(self) -> None:
        # Gate: when not set, ``add_memory`` blocks.  Default
        # state is "set" so calls outside an explicit park()
        # window proceed normally.
        self._gate: threading.Event = threading.Event()
        self._gate.set()

        # Number of writers currently parked at the gate.
        # Tests use ``wait_until_pending(n)`` to synchronise.
        self._pending_lock: threading.Lock = threading.Lock()
        self._pending_cv: threading.Condition = (
            threading.Condition(self._pending_lock)
        )
        self._pending_count: int = 0

        # Committed store and per-store mutex.
        self._store_lock: threading.Lock = threading.Lock()
        self._store: List[Dict[str, Any]] = []

        # Test diagnostics: number of times ``add_memory`` /
        # ``retrieve_memory`` were called.
        self.add_calls: int = 0
        self.retrieve_calls: int = 0

    # ------------------------------------------------------------------
    # Provider contract
    # ------------------------------------------------------------------

    def initialize(self, config: Dict[str, Any]) -> None:  # noqa: D401
        """No-op initialiser.  Configuration is supplied via
        ``park()`` / ``release()`` from the test driver."""
        return None

    def add_memory(self, memory_note: "MemoryNote") -> MemoryResponse:
        """Register the writer at the gate, block until released,
        then append to the committed store."""
        with self._pending_lock:
            self._pending_count += 1
            self.add_calls += 1
            self._pending_cv.notify_all()
        try:
            # Block until release() is called.
            self._gate.wait()
        finally:
            with self._pending_lock:
                self._pending_count -= 1
                self._pending_cv.notify_all()

        with self._store_lock:
            self._store.append({
                "memory_id": memory_note.id,
                "content": memory_note.content,
                "metadata": dict(memory_note.metadata or {}),
                "timestamp": memory_note.timestamp,
                "keywords": list(memory_note.keywords or []),
                "tags": list(memory_note.tags or []),
                "category": memory_note.category or "Uncategorized",
            })
        return MemoryResponse(success=True, memory_id=memory_note.id)

    def remove_memory(self, memory_id: str) -> MemoryResponse:
        with self._store_lock:
            before = len(self._store)
            self._store = [
                item for item in self._store
                if item["memory_id"] != memory_id
            ]
            removed = before - len(self._store)
        if removed:
            return MemoryResponse(
                success=True, memory_id=memory_id,
            )
        return MemoryResponse(
            success=False, error=f"memory {memory_id} not found",
        )

    def update_memory(
        self, memory_note: "MemoryNote",
    ) -> MemoryResponse:
        with self._store_lock:
            for item in self._store:
                if item["memory_id"] == memory_note.id:
                    item["content"] = memory_note.content
                    item["metadata"] = dict(
                        memory_note.metadata or {},
                    )
                    return MemoryResponse(
                        success=True, memory_id=memory_note.id,
                    )
        return MemoryResponse(
            success=False, error=f"memory {memory_note.id} not found",
        )

    def get_memory(self, memory_id: str) -> MemoryResponse:
        with self._store_lock:
            for item in self._store:
                if item["memory_id"] == memory_id:
                    return MemoryResponse(
                        success=True,
                        content=item["content"],
                        metadata=dict(item["metadata"]),
                    )
        return MemoryResponse(
            success=False, error=f"memory {memory_id} not found",
        )

    def retrieve_memory(self, query: MemoryQuery) -> MemoryResponse:
        """Return the post-commit store snapshot, applying the same
        cross-agent sharing filter as ``Mem0Provider``."""
        self.retrieve_calls += 1
        agent_name = query.params.get("agent_name")
        user_id = query.params.get("user_id")
        sharing_policy = query.params.get("sharing_policy")
        k = query.params.get("k", 5)

        with self._store_lock:
            snapshot = [
                {
                    "content": item["content"],
                    "metadata": dict(item["metadata"]),
                    "score": 0.9,
                    "timestamp": item["timestamp"],
                    "keywords": list(item["keywords"]),
                    "tags": list(item["tags"]),
                    "category": item["category"],
                }
                for item in self._store
            ]

        # Use the requesting agent_name to apply sharing rules.
        if agent_name is not None:
            snapshot = _apply_sharing_filter(
                snapshot,
                agent_name,
                user_id,
                sharing_policy,
                lambda item: item.get("metadata", {}),
            )

        results = []
        for item in snapshot[:k]:
            metadata = _enrich_metadata(
                dict(item.get("metadata", {})),
            )
            results.append({
                "content": item.get("content", ""),
                "keywords": metadata.get("keywords", []),
                "tags": metadata.get("tags", []),
                "category": metadata.get(
                    "category", "Uncategorized",
                ),
                "timestamp": metadata.get("timestamp", ""),
                "score": item.get("score"),
                "metadata": metadata,
            })
        return MemoryResponse(success=True, search_results=results)

    def retrieve_memory_raw(
        self, query: MemoryQuery,
    ) -> List["MemoryNote"]:
        from aios.memory.note import MemoryNote

        resp = self.retrieve_memory(query)
        notes: List[MemoryNote] = []
        if not resp.success or not resp.search_results:
            return notes
        for item in resp.search_results:
            metadata = item.get("metadata", {})
            notes.append(
                MemoryNote(
                    content=item.get("content", ""),
                    keywords=metadata.get("keywords", []),
                    tags=metadata.get("tags", []),
                    category=metadata.get(
                        "category", "Uncategorized",
                    ),
                    timestamp=metadata.get("timestamp"),
                    metadata=metadata,
                ),
            )
        return notes

    def close(self) -> None:
        # Release any parked writers so their threads can exit.
        self._gate.set()

    # ------------------------------------------------------------------
    # Test driver helpers
    # ------------------------------------------------------------------

    def park(self) -> None:
        """Subsequent ``add_memory`` calls block until ``release()``
        is invoked."""
        self._gate.clear()

    def release(self) -> None:
        """Allow all parked (and future) ``add_memory`` calls to
        commit and return."""
        self._gate.set()

    def wait_until_pending(
        self, n: int, timeout: float = 5.0,
    ) -> bool:
        """Block until at least ``n`` writers are parked at the gate
        or ``timeout`` seconds elapse.  Returns ``True`` on success."""
        deadline = time.monotonic() + timeout
        with self._pending_cv:
            while self._pending_count < n:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._pending_cv.wait(timeout=remaining)
            return True

    @property
    def pending_count(self) -> int:
        with self._pending_lock:
            return self._pending_count

    def store_size(self) -> int:
        with self._store_lock:
            return len(self._store)
