"""
InHouseProvider - an in-memory dict provider, for tests.

Registered as provider "in-memory". Nothing persists, and search scores
by bag-of-words cosine, so it needs no embedding model: it is scored but
not semantic. The production in-house backend is
``ChromaInHouseProvider`` (provider "in-house").
"""
import math
import re
import threading
import uuid
from collections import Counter
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .base import Candidate, MemoryProvider, note_metadata

if TYPE_CHECKING:
    from aios.memory.note import MemoryNote


def _words(text: str) -> Counter:
    return Counter(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _cosine(a: Counter, b: Counter) -> float:
    dot = sum(a[w] * b[w] for w in a.keys() & b.keys())
    norm = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(
        sum(v * v for v in b.values())
    )
    return dot / norm if norm else 0.0


class InHouseProvider(MemoryProvider):
    """Memories in a dict keyed by user, then id, in insertion order."""

    synchronous_commit = True

    def __init__(self):
        self.default_user_id = "default"
        self._store: Dict[str, Dict[str, Candidate]] = {}
        self._lock = threading.Lock()

    def initialize(self, config: Dict[str, Any]) -> None:
        self.default_user_id = config.get(
            "default_user_id", self.default_user_id
        )

    def capabilities(self) -> Dict[str, bool]:
        return {
            "scored_search": True,
            "semantic_search": False,
            "internal_llm": False,
            "native_sdk": False,
        }

    def _rows(self, user_id: Optional[str]) -> Dict[str, Candidate]:
        return self._store.setdefault(
            str(user_id or self.default_user_id), {}
        )

    @staticmethod
    def _copy(row: Candidate, score: Optional[float] = None) -> Candidate:
        return Candidate(row.memory_id, row.content, dict(row.metadata), score)

    def add(self, memory_note: "MemoryNote") -> str:
        metadata = note_metadata(memory_note)
        memory_id = str(uuid.uuid4())
        with self._lock:
            self._rows(metadata.get("user_id"))[memory_id] = Candidate(
                memory_id, memory_note.content, metadata
            )
        return memory_id

    def search(
        self, query_text: str, user_id: Optional[str], top_k: int
    ) -> List[Candidate]:
        query = _words(query_text)
        with self._lock:
            scored = [
                self._copy(row, _cosine(query, _words(row.content)))
                for row in self._rows(user_id).values()
            ]
        scored.sort(key=lambda row: row.score, reverse=True)
        return scored[:max(top_k, 0)]

    def list(self, user_id: Optional[str], top_k: int) -> List[Candidate]:
        with self._lock:
            rows = list(self._rows(user_id).values())
        return [self._copy(row) for row in rows[:max(top_k, 0)]]

    def get(
        self, memory_id: str, user_id: Optional[str]
    ) -> Optional[Candidate]:
        with self._lock:
            row = self._rows(user_id).get(memory_id)
        return self._copy(row) if row else None

    def update(
        self,
        memory_id: str,
        user_id: Optional[str],
        content: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> bool:
        with self._lock:
            rows = self._rows(user_id)
            row = rows.get(memory_id)
            if row is None:
                return False
            rows[memory_id] = Candidate(
                memory_id,
                row.content if content is None else content,
                {**row.metadata, **(metadata or {})},
            )
        return True

    def delete(self, memory_id: str, user_id: Optional[str]) -> bool:
        with self._lock:
            return self._rows(user_id).pop(memory_id, None) is not None
