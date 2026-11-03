"""
The provider contract: what every memory backend implements.

A provider stores and finds memories. The kernel decides which ones an
agent sees: visibility, the user partition, dedupe, the relevance
threshold and the count cap all live in
``MemoryManager.retrieve_for_agent``, never here. A provider returns
everything in the user's scope that matches, scored where it can.
See docs/PROVIDER_CONTRACT.md.
"""
import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from aios.memory.note import MemoryNote

# Every stored item carries these; the kernel fills them before ``add``.
REQUIRED_METADATA = (
    "owner_agent",
    "user_id",
    "memory_type",
    "sharing_policy",
    "created_at",
)

CAPABILITIES = (
    "scored_search",
    "semantic_search",
    "internal_llm",
    "native_sdk",
)


class ProviderError(Exception):
    """A backend operation failed (not the same as "not found")."""


@dataclass
class Candidate:
    """One stored memory as a provider returns it.

    ``score`` is a similarity, higher is closer, or ``None`` when the
    backend did not score this row (``list``, or a backend without
    scored search).
    """

    memory_id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: Optional[float] = None

    def to_row(self) -> Dict[str, Any]:
        """The kernel's row shape, which SDK search returns. The note
        fields are repeated at the top level as before the contract."""
        meta = self.metadata
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "metadata": meta,
            "score": self.score,
            "keywords": meta.get("keywords", []),
            "tags": meta.get("tags", []),
            "category": meta.get("category", "Uncategorized"),
            "timestamp": meta.get("timestamp", ""),
        }


def note_metadata(memory_note: "MemoryNote") -> Dict[str, Any]:
    """The metadata a provider stores for a note: the note's own fields
    plus everything the caller put in ``note.metadata``. Drops values a
    vector store cannot hold (``None``, empty lists, nested dicts)."""
    metadata: Dict[str, Any] = {
        "keywords": memory_note.keywords,
        "tags": memory_note.tags,
        "category": memory_note.category,
        "context": memory_note.context,
        "timestamp": memory_note.timestamp,
        "memory_note_id": memory_note.id,
    }
    metadata.update(getattr(memory_note, "metadata", None) or {})
    return {
        key: value for key, value in metadata.items()
        if value is not None
        and not isinstance(value, dict)
        and not (isinstance(value, list) and not value)
    }


def similarity_from_distance(distance: float, space: str) -> float:
    """Convert a Chroma distance to a similarity, higher is closer.

    ``cosine`` and ``ip`` distances are ``1 - similarity``. Chroma's
    ``l2`` is the squared Euclidean distance, which for unit vectors is
    ``2 - 2 cos``; the pinned embedding model returns unit vectors, so
    this gives the cosine similarity.
    """
    if space in ("cosine", "ip"):
        return 1.0 - distance
    if space == "l2":
        return 1.0 - distance / 2.0
    raise ValueError(f"unknown Chroma distance space {space!r}")


def user_collection_name(prefix: str, user_id: str) -> str:
    """A valid Chroma collection name for one user's memories: the
    prefix, a readable part of the user id and a hash of the whole id,
    so long or similar ids never share a collection."""
    readable = re.sub(r"[^a-zA-Z0-9_-]", "_", str(user_id))
    readable = re.sub(r"_+", "_", readable).strip("_-")[:30] or "user"
    digest = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{readable}_{digest}"


class MemoryProvider(ABC):
    """The interface every memory backend implements.

    Every method takes the user scope explicitly. ``None`` means the
    provider's default scope. No method filters by visibility: an agent's
    private memory is returned to anyone who asks, and the kernel removes
    it. See docs/PROVIDER_CONTRACT.md for the full contract.
    """

    # True when a write is durable once ``add`` returns, so the write
    # barrier is skipped for it (a wait would only add latency).
    synchronous_commit = False

    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> None:
        """Configure the backend. Raises ProviderInitializationError."""

    @abstractmethod
    def capabilities(self) -> Dict[str, bool]:
        """What the backend can do, one bool per key in CAPABILITIES:

        - ``scored_search``: ``search`` returns a score on every row.
        - ``semantic_search``: ``search`` ranks by meaning, not words.
        - ``internal_llm``: the backend has its own LLM (fact extraction
          or similar), whether or not the kernel uses it.
        - ``native_sdk``: the backend is a third-party memory SDK.
        """

    @abstractmethod
    def add(self, memory_note: "MemoryNote") -> str:
        """Store a note verbatim with ``note_metadata(note)``; return its
        id. Raises ProviderError on failure. The note's metadata carries
        every key in REQUIRED_METADATA, and ``user_id`` names the scope.
        """

    @abstractmethod
    def search(
        self, query_text: str, user_id: Optional[str], top_k: int
    ) -> List[Candidate]:
        """Up to ``top_k`` of the user's memories, closest first, scored
        if ``scored_search``. No visibility filtering and no threshold.
        """

    @abstractmethod
    def list(self, user_id: Optional[str], top_k: int) -> List[Candidate]:
        """Up to ``top_k`` of the user's memories in storage order,
        unscored."""

    @abstractmethod
    def get(
        self, memory_id: str, user_id: Optional[str]
    ) -> Optional[Candidate]:
        """One memory by id in the user's scope, or ``None``."""

    @abstractmethod
    def update(
        self,
        memory_id: str,
        user_id: Optional[str],
        content: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> bool:
        """Replace the content (when not ``None``) and merge ``metadata``
        over the stored metadata; required keys are never removed.
        Returns False if the memory does not exist. Raises ProviderError
        on failure."""

    @abstractmethod
    def delete(self, memory_id: str, user_id: Optional[str]) -> bool:
        """Delete one memory; False if it does not exist."""

    def close(self) -> None:
        """Release resources. Override if needed."""

    def sync_llm_from_query(self, llms: "list[dict] | None") -> None:
        """Point a provider's internal LLM at the agent's model. No-op for
        providers without one."""
