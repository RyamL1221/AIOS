"""Test-only shim: lets a provider double written against the pre-contract
interface (``add_memory`` / ``retrieve_memory`` / ``get_memory_for_user``
/ ``update_memory`` / ``remove_memory_for_user``, all returning
``MemoryResponse``) serve the provider contract the kernel now calls
(docs/PROVIDER_CONTRACT.md). Production providers implement the contract
directly; nothing outside tests uses this.
"""
from typing import Any, Dict, List, Optional

from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from aios.memory.providers.base import (
    Candidate,
    MemoryProvider,
    ProviderError,
)


def _enrich_metadata(metadata: dict) -> dict:
    """Fill the cross-agent keys with empty strings, as providers did
    before the contract."""
    for key in ("owner_agent", "user_id", "sharing_policy", "memory_type"):
        metadata.setdefault(key, "")
    return metadata


class LegacyProviderAdapter(MemoryProvider):
    """Implements the contract on top of the old methods. Subclasses
    override the old methods; anything they leave out fails loudly."""

    def initialize(self, config: Dict[str, Any]) -> None:
        pass

    def capabilities(self) -> Dict[str, bool]:
        return {
            "scored_search": False,
            "semantic_search": False,
            "internal_llm": False,
            "native_sdk": False,
        }

    # The old interface -------------------------------------------------

    def add_memory(self, memory_note) -> MemoryResponse:
        raise NotImplementedError

    def retrieve_memory(self, query: MemoryQuery) -> MemoryResponse:
        raise NotImplementedError

    def get_memory(self, memory_id) -> MemoryResponse:
        return MemoryResponse(success=False, error="Memory not found")

    def get_memory_for_user(self, memory_id, user_id=None) -> MemoryResponse:
        """As the old base class did: the default scope's lookup."""
        return self.get_memory(memory_id)

    def update_memory(self, memory_note) -> MemoryResponse:
        return MemoryResponse(success=False, error="Memory not found")

    def remove_memory(self, memory_id) -> MemoryResponse:
        return MemoryResponse(success=False, error="Memory not found")

    def remove_memory_for_user(self, memory_id, user_id=None):
        return self.remove_memory(memory_id)

    # The contract, on top of it ---------------------------------------

    def add(self, memory_note) -> str:
        response = self.add_memory(memory_note)
        if not response.success:
            raise ProviderError(response.error)
        return response.memory_id

    def search(self, query_text, user_id, top_k) -> List[Candidate]:
        params = {"content": query_text, "k": top_k, "top_k": top_k}
        if user_id is not None:
            params["user_id"] = user_id
        response = self.retrieve_memory(
            MemoryQuery(operation_type="retrieve_memory", params=params)
        )
        if not response.success:
            raise ProviderError(response.error)
        return [
            Candidate(
                memory_id=row.get("memory_id") or row.get("id") or "",
                content=row.get("content", ""),
                metadata={
                    "timestamp": row.get("timestamp", ""),
                    **(row.get("metadata") or {}),
                },
                score=row.get("score"),
            )
            for row in (response.search_results or [])
        ]

    def list(self, user_id, top_k) -> List[Candidate]:
        return [
            Candidate(c.memory_id, c.content, c.metadata)
            for c in self.search("", user_id, top_k)
        ]

    def get(self, memory_id, user_id) -> Optional[Candidate]:
        response = self.get_memory_for_user(memory_id, user_id)
        if not response.success:
            return None
        return Candidate(memory_id, response.content or "",
                         dict(response.metadata or {}))

    def update(self, memory_id, user_id, content, metadata) -> bool:
        from aios.memory.note import MemoryNote

        note = MemoryNote(content=content or "", id=memory_id)
        note.metadata = {**(metadata or {}), "user_id": user_id}
        return bool(self.update_memory(note).success)

    def delete(self, memory_id, user_id) -> bool:
        return bool(self.remove_memory_for_user(memory_id, user_id).success)
