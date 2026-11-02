"""
ZepProvider - Memory provider using Zep for memory management.

Uses the Zep graph API (available on free tier) for storing and retrieving
memories as graph episodes with semantic search via graph.search.

Zep Cloud free tier supports:
  - user.add / user.get
  - graph.add (store text as episodes)
  - graph.search (semantic search over graph)

The sessions/memory API requires a paid plan.

Does not conform to the provider contract (docs/PROVIDER_CONTRACT.md):
Zep stores text only, so the required metadata (owner_agent, user_id,
memory_type, sharing_policy, created_at) is lost, and the kernel's user
partition and visibility rule, which fail closed, drop every row it
returns. ``list`` and ``update`` are not supported.
"""
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .base import Candidate, MemoryProvider, ProviderError

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

    def capabilities(self) -> Dict[str, bool]:
        return {
            "scored_search": True,
            "semantic_search": True,
            "internal_llm": True,
            "native_sdk": True,
        }

    def _scope(self, user_id: Optional[str]) -> str:
        return str(user_id or self.default_user_id)

    def add(self, memory_note: "MemoryNote") -> str:
        user_id = self._scope((memory_note.metadata or {}).get("user_id"))
        try:
            result = self.client.graph.add(
                user_id=user_id, type="text", data=memory_note.content
            )
        except Exception as e:
            raise ProviderError(f"Zep add failed: {e}") from e
        return getattr(result, "uuid", None) or memory_note.id

    def search(
        self, query_text: str, user_id: Optional[str], top_k: int
    ) -> List[Candidate]:
        scope = self._scope(user_id)
        results = self.client.graph.search(
            query=query_text, user_id=scope, limit=top_k, scope="edges"
        )
        return [
            Candidate(
                memory_id=str(getattr(edge, "uuid_", "")),
                content=getattr(edge, "fact", "") or "",
                metadata=dict(getattr(edge, "metadata", None) or {}),
                score=getattr(edge, "score", None),
            )
            for edge in (getattr(results, "edges", []) or [])
        ]

    def list(self, user_id: Optional[str], top_k: int) -> List[Candidate]:
        raise ProviderError("Zep has no listing")

    def get(
        self, memory_id: str, user_id: Optional[str]
    ) -> Optional[Candidate]:
        try:
            result = self.client.graph.episode.get(memory_id)
        except Exception:
            return None
        if result is None:
            return None
        return Candidate(memory_id, getattr(result, "content", "") or "")

    def update(
        self,
        memory_id: str,
        user_id: Optional[str],
        content: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> bool:
        raise ProviderError("Zep cannot update an episode in place")

    def delete(self, memory_id: str, user_id: Optional[str]) -> bool:
        try:
            self.client.graph.episode.delete(episode_uuid=memory_id)
        except Exception:
            return False
        return True

    def close(self) -> None:
        self.client = None
