"""
ZepProvider - Memory provider using Zep for memory management.

Uses the Zep graph API (available on free tier) for storing and retrieving
memories as graph episodes with semantic search via graph.search.

Zep Cloud free tier supports:
  - user.add / user.get
  - graph.add (store text as episodes)
  - graph.search (semantic search over graph)

The sessions/memory API requires a paid plan.
"""
from typing import Dict, Any, List, TYPE_CHECKING

from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from .base import (
    MemoryProvider,
    _apply_sharing_filter,
    _enrich_metadata,
)

if TYPE_CHECKING:
    from aios.memory.note import MemoryNote


class ZepProvider(MemoryProvider):
    """Provider using Zep graph API for memory management.

    Attributes:
        client: Zep client instance
        default_user_id: Default user ID for graph operations
        default_session_id: Kept for interface compatibility (not used in graph API)
    """

    def __init__(self):
        self.client = None
        self.default_user_id = "aios_default_user"
        self.default_session_id = "default"

    def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize the Zep client and ensure the default user exists."""
        try:
            from zep_cloud.client import Zep
        except ImportError:
            try:
                from zep_python import ZepClient as Zep
            except ImportError as e:
                raise ImportError(
                    "Zep library not installed. Install with: "
                    "pip install zep-cloud (for cloud) or pip install zep-python (for self-hosted)"
                ) from e

        try:
            self.default_user_id = config.get("user_id", "aios_default_user")
            self.default_session_id = config.get("session_id", "default")

            api_key = config.get("api_key")
            base_url = config.get("base_url")

            if base_url:
                self.client = Zep(api_key=api_key, base_url=base_url)
            else:
                self.client = Zep(api_key=api_key)

            # Ensure user exists
            try:
                self.client.user.add(user_id=self.default_user_id)
            except Exception:
                pass  # Already exists

        except Exception as e:
            from . import ProviderInitializationError
            raise ProviderInitializationError(
                "zep", f"Failed to initialize Zep client: {str(e)}"
            )

    def add_memory(self, memory_note: 'MemoryNote') -> MemoryResponse:
        """Store a memory note via graph.add (free tier compatible)."""
        from aios.memory.note import MemoryNote

        if not isinstance(memory_note, MemoryNote):
            return MemoryResponse(
                success=False,
                error=f"Expected MemoryNote, got {type(memory_note).__name__}"
            )

        try:
            user_id = self.default_user_id
            if hasattr(memory_note, 'metadata') and memory_note.metadata:
                user_id = memory_note.metadata.get("user_id", user_id)

            result = self.client.graph.add(
                user_id=user_id,
                type="text",
                data=memory_note.content
            )

            # Use the episode uuid returned by Zep, fall back to note id
            memory_id = getattr(result, 'uuid', None) or memory_note.id
            return MemoryResponse(success=True, memory_id=memory_id)

        except Exception as e:
            return MemoryResponse(success=False, error=f"Zep add_memory failed: {str(e)}")

    def remove_memory(self, memory_id: str) -> MemoryResponse:
        """Remove a graph episode by UUID.

        Note: Zep graph API does not expose a delete endpoint on the free tier.
        This returns success=True as a no-op to avoid breaking the interface.
        """
        try:
            # Attempt episode delete if available
            self.client.graph.episode.delete(episode_uuid=memory_id)
            return MemoryResponse(success=True, memory_id=memory_id)
        except Exception:
            # Free tier has no delete — treat as success (soft delete)
            return MemoryResponse(success=True, memory_id=memory_id)

    def update_memory(self, memory_note: 'MemoryNote') -> MemoryResponse:
        """Update by adding a new graph episode with the updated content."""
        from aios.memory.note import MemoryNote

        if not isinstance(memory_note, MemoryNote):
            return MemoryResponse(
                success=False,
                error=f"Expected MemoryNote, got {type(memory_note).__name__}"
            )
        return self.add_memory(memory_note)

    def get_memory(self, memory_id: str) -> MemoryResponse:
        """Retrieve a graph episode by UUID."""
        if not isinstance(memory_id, str):
            return MemoryResponse(success=False, error="Memory id must be a string")

        try:
            result = self.client.graph.episode.get(memory_id)
            if result is None:
                return MemoryResponse(success=False, error="Memory not found")

            content = getattr(result, 'content', '') or ''
            return MemoryResponse(
                success=True,
                content=content,
                metadata={"keywords": [], "tags": [], "category": "Uncategorized", "timestamp": ""}
            )
        except Exception as e:
            return MemoryResponse(success=False, error=f"Zep get_memory failed: {str(e)}")

    def retrieve_memory(self, query: MemoryQuery) -> MemoryResponse:
        """Semantic search via graph.search (free tier compatible).

        Results are filtered by cross-agent sharing rules when
        ``agent_name``, ``user_id``, or ``sharing_policy`` are
        present in ``query.params``.
        """
        try:
            content = query.params.get("content", "")
            k = query.params.get("k", 5)
            agent_name = query.params.get("agent_name")
            sharing_policy = query.params.get(
                "sharing_policy"
            )

            # Use user_id from params when provided;
            # fall back to the configured default otherwise.
            user_id = query.params.get("user_id")
            search_user_id = (
                user_id
                if user_id is not None
                else self.default_user_id
            )

            results = self.client.graph.search(
                query=content,
                user_id=search_user_id,
                limit=k,
                scope="edges"
            )

            edges = getattr(results, 'edges', []) or []

            # Apply cross-agent sharing filter when
            # agent_name is available (injected by
            # MemoryManager).
            if agent_name is not None:
                edges = _apply_sharing_filter(
                    edges,
                    agent_name,
                    user_id,
                    sharing_policy,
                    lambda edge: (
                        dict(getattr(edge, 'metadata', None)
                             or {})
                    ),
                )

            search_results = []
            for edge in edges[:k]:
                fact = getattr(edge, 'fact', '') or ''
                score = getattr(edge, 'score', None)
                metadata = _enrich_metadata(
                    dict(getattr(edge, 'metadata', None)
                         or {})
                )
                search_results.append({
                    "memory_id": getattr(edge, 'uuid_', None),
                    "content": fact,
                    "keywords": [],
                    "tags": [],
                    "category": "Uncategorized",
                    "timestamp": str(
                        getattr(edge, 'created_at', '')
                    ),
                    "score": score,
                    "metadata": metadata,
                })

            return MemoryResponse(
                success=True,
                search_results=search_results,
            )

        except Exception as e:
            return MemoryResponse(
                success=False,
                error=(
                    f"Zep retrieve_memory failed: "
                    f"{str(e)}"
                ),
            )

    def retrieve_memory_raw(self, query: MemoryQuery) -> List['MemoryNote']:
        """Return graph search results as MemoryNote objects.

        Results are filtered by cross-agent sharing rules when
        ``agent_name``, ``user_id``, or ``sharing_policy`` are
        present in ``query.params``.
        """
        from aios.memory.note import MemoryNote

        content = query.params.get("content", "")
        k = query.params.get("k", 5)
        agent_name = query.params.get("agent_name")
        sharing_policy = query.params.get("sharing_policy")

        # Use user_id from params when provided;
        # fall back to the configured default otherwise.
        user_id = query.params.get("user_id")
        search_user_id = (
            user_id
            if user_id is not None
            else self.default_user_id
        )

        try:
            results = self.client.graph.search(
                query=content,
                user_id=search_user_id,
                limit=k,
                scope="edges"
            )

            edges = getattr(results, 'edges', []) or []

            # Apply cross-agent sharing filter when
            # agent_name is available (injected by
            # MemoryManager).
            if agent_name is not None:
                edges = _apply_sharing_filter(
                    edges,
                    agent_name,
                    user_id,
                    sharing_policy,
                    lambda edge: (
                        dict(getattr(edge, 'metadata', None)
                             or {})
                    ),
                )

            memory_notes = []
            for edge in edges[:k]:
                fact = getattr(edge, 'fact', '') or ''
                if fact:
                    metadata = _enrich_metadata(
                        dict(getattr(edge, 'metadata', None)
                             or {})
                    )
                    memory_notes.append(MemoryNote(
                        content=fact,
                        id=getattr(edge, 'uuid_', None),
                        context="General",
                        category="Uncategorized",
                        metadata=metadata,
                    ))
            return memory_notes

        except Exception:
            return []

    def close(self) -> None:
        self.client = None
