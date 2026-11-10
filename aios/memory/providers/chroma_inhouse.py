"""
ChromaInHouseProvider - the AIOS in-house memory backend, on Chroma.

Content is stored verbatim: no extraction and no internal LLM. One
persistent Chroma collection per user, cosine space, embedded with the
pinned ``memory.embedding`` model. Scalar metadata is stored as Chroma
metadata so ``where`` filters work; the full metadata also rides along
as JSON so lists round-trip exactly. Registered as provider "in-house".
See docs/PROVIDER_CONTRACT.md.
"""
import json
import logging
import os
import threading
import uuid
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from aios.memory.embedding import Embedder, EmbeddingConfig

from .base import (
    Candidate,
    MemoryProvider,
    ProviderError,
    note_metadata,
    similarity_from_distance,
    user_collection_name,
)

if TYPE_CHECKING:
    from aios.memory.note import MemoryNote

logger = logging.getLogger(__name__)

METADATA_JSON = "_metadata_json"
SPACE = "cosine"


def _chroma_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Scalars as Chroma metadata, plus the whole dict as JSON."""
    stored = {
        key: value for key, value in metadata.items()
        if isinstance(value, (str, int, float, bool))
    }
    stored[METADATA_JSON] = json.dumps(metadata, sort_keys=True)
    return stored


def _read_metadata(stored: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    stored = stored or {}
    if METADATA_JSON in stored:
        return json.loads(stored[METADATA_JSON])
    return dict(stored)


class ChromaInHouseProvider(MemoryProvider):
    """Verbatim memories in per-user Chroma collections."""

    def __init__(self):
        self._client = None
        self._embedder: Optional[Embedder] = None
        self._embedding: Optional[EmbeddingConfig] = None
        self._prefix = "aios_mem"
        self.default_user_id = "default"
        self._collections: Dict[str, Any] = {}
        self._lock = threading.RLock()

    def initialize(self, config: Dict[str, Any]) -> None:
        """Config keys: ``path`` (default ``.aios_state/chroma_inhouse``),
        ``collection_prefix``, ``default_user_id`` and ``embedding`` (the
        ``memory.embedding`` block)."""
        from . import ProviderInitializationError

        try:
            import chromadb
            from chromadb.config import Settings

            path = os.path.abspath(
                config.get("path") or ".aios_state/chroma_inhouse"
            )
            os.makedirs(path, exist_ok=True)
            self._prefix = config.get("collection_prefix", self._prefix)
            self.default_user_id = config.get(
                "default_user_id", self.default_user_id
            )
            self._embedding = EmbeddingConfig.from_memory_config(
                {"embedding": config.get("embedding") or {}}
            )
            self._embedder = Embedder(self._embedding)
            self._client = chromadb.PersistentClient(
                path=path, settings=Settings(anonymized_telemetry=False)
            )
            logger.info(
                "Chroma in-house provider at %s, embedding %s (%d dims)",
                path, self._embedding.model, self._embedding.dimension,
            )
        except Exception as e:
            raise ProviderInitializationError(
                "in-house", f"Failed to initialize Chroma: {e}"
            )

    def capabilities(self) -> Dict[str, bool]:
        return {
            "scored_search": True,
            "semantic_search": True,
            "internal_llm": False,
            "native_sdk": False,
        }

    def _scope(self, user_id: Optional[str]) -> str:
        return str(user_id or self.default_user_id)

    def _collection(self, user_id: Optional[str]):
        """The user's collection, created on first use. Refuses one made
        with a different embedding model."""
        scope = self._scope(user_id)
        with self._lock:
            collection = self._collections.get(scope)
            if collection is not None:
                return collection
            collection = self._client.get_or_create_collection(
                name=user_collection_name(self._prefix, scope),
                embedding_function=None,
                metadata={
                    "hnsw:space": SPACE,
                    "user_id": scope,
                    "embedding_model": self._embedding.model,
                    "embedding_dimension": self._embedding.dimension,
                },
            )
            stored_model = (collection.metadata or {}).get("embedding_model")
            if stored_model != self._embedding.model:
                raise ProviderError(
                    f"collection for {scope!r} was embedded with "
                    f"{stored_model!r}, not {self._embedding.model!r}"
                )
            self._collections[scope] = collection
            return collection

    @staticmethod
    def _candidates(ids, documents, metadatas, distances=None) -> list:
        rows = []
        for i, memory_id in enumerate(ids):
            score = None
            if distances is not None:
                score = similarity_from_distance(distances[i], SPACE)
            rows.append(Candidate(
                memory_id=memory_id,
                content=documents[i] or "",
                metadata=_read_metadata(metadatas[i]),
                score=score,
            ))
        return rows

    def add(self, memory_note: "MemoryNote") -> str:
        metadata = note_metadata(memory_note)
        memory_id = str(uuid.uuid4())
        try:
            self._collection(metadata.get("user_id")).add(
                ids=[memory_id],
                embeddings=[self._embedder.embed(memory_note.content)],
                documents=[memory_note.content],
                metadatas=[_chroma_metadata(metadata)],
            )
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Chroma add failed: {e}") from e
        return memory_id

    def search(
        self, query_text: str, user_id: Optional[str], top_k: int
    ) -> List[Candidate]:
        collection = self._collection(user_id)
        count = collection.count()
        if count == 0 or top_k <= 0:
            return []
        result = collection.query(
            query_embeddings=[self._embedder.embed(query_text)],
            n_results=min(top_k, count),
            include=["documents", "metadatas", "distances"],
        )
        return self._candidates(
            result["ids"][0],
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
        )

    def list(self, user_id: Optional[str], top_k: int) -> List[Candidate]:
        if top_k <= 0:
            return []
        result = self._collection(user_id).get(
            limit=top_k, include=["documents", "metadatas"]
        )
        return self._candidates(
            result["ids"], result["documents"], result["metadatas"]
        )

    def get(
        self, memory_id: str, user_id: Optional[str]
    ) -> Optional[Candidate]:
        result = self._collection(user_id).get(
            ids=[memory_id], include=["documents", "metadatas"]
        )
        if not result["ids"]:
            return None
        return self._candidates(
            result["ids"], result["documents"], result["metadatas"]
        )[0]

    def update(
        self,
        memory_id: str,
        user_id: Optional[str],
        content: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> bool:
        current = self.get(memory_id, user_id)
        if current is None:
            return False
        merged = {**current.metadata, **(metadata or {})}
        new_content = current.content if content is None else content
        try:
            self._collection(user_id).update(
                ids=[memory_id],
                embeddings=[self._embedder.embed(new_content)],
                documents=[new_content],
                metadatas=[_chroma_metadata(merged)],
            )
        except Exception as e:
            raise ProviderError(f"Chroma update failed: {e}") from e
        return True

    def update_metadata(
        self,
        memory_id: str,
        user_id: Optional[str],
        metadata: Dict[str, Any],
    ) -> bool:
        """Write the merged metadata alone: neither documents nor
        embeddings are sent, so Chroma keeps both, and no embedding call
        is made. The full merged dict is sent, so the result is the same
        whether Chroma merges or replaces a record's metadata."""
        current = self.get(memory_id, user_id)
        if current is None:
            return False
        merged = {**current.metadata, **(metadata or {})}
        try:
            self._collection(user_id).update(
                ids=[memory_id], metadatas=[_chroma_metadata(merged)],
            )
        except Exception as e:
            raise ProviderError(f"Chroma metadata update failed: {e}") from e
        return True

    def delete(self, memory_id: str, user_id: Optional[str]) -> bool:
        if self.get(memory_id, user_id) is None:
            return False
        self._collection(user_id).delete(ids=[memory_id])
        return True

    def close(self) -> None:
        with self._lock:
            self._collections.clear()
