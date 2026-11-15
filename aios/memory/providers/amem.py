"""
AMemProvider: A-MEM's agentic notes (WujiangXu/A-mem-sys) behind the
provider contract.

NeurIPS Subtask 17; the design is docs/AMEM_BACKEND.md. In short:

- One note per write, in the user's store (an ``AgenticMemorySystem`` of
  the user's own, with its own Chroma collection). A-MEM's LLM generates
  the note's keywords, context and tags, and evolution rewrites the
  tags and context of the notes it is shown. The content is stored
  verbatim, and a row is a note.
- A-MEM's notes carry no metadata mapping, and evolution rewrites
  ``tags`` and ``context``; ours is the note's ``category``, as JSON,
  which nothing in A-MEM writes after ``add_note``.
- ``search`` is A-MEM's ``search``, the README's first example: Chroma's
  hits nearest first, each with a similarity from its distance, so
  ``scored_search`` is true. (``search_agentic`` returns the same notes:
  the linked notes it adds never survive its cut at k.)
- A-MEM's LLM (the pinned ``memory.backend_llm``) and embedder (the
  pinned ``memory.embedding``) come from ``cerebrum.utils.amem``, and
  every call runs in the caller's thread, under its usage tag.
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .base import (
    Candidate,
    MemoryProvider,
    ProviderError,
    note_metadata,
    similarity_from_distance,
)

if TYPE_CHECKING:
    from aios.memory.note import MemoryNote

logger = logging.getLogger(__name__)

DEFAULT_SCOPE = "default"

# Why the scrub deletes a note: its derived text (A-MEM's context,
# keywords and tags, or its Chroma copy) carries a form
# (docs/AMEM_BACKEND.md, "The forget on A-MEM").
REASON_DERIVED = "derived"


def _metadata(category: Any) -> Dict[str, Any]:
    """Our metadata from a note's ``category``: a JSON string in the
    note, already parsed in a Chroma hit (A-MEM converts metadata
    strings, ``retrievers.py:85-110``); anything else is none."""
    if isinstance(category, dict):
        return dict(category)
    if isinstance(category, str):
        try:
            found = json.loads(category)
        except ValueError:
            return {}
        return found if isinstance(found, dict) else {}
    return {}


def _time(created_at: Any) -> str:
    """A-MEM's ``YYYYMMDDHHMM`` for the write's time (now when it has
    none or it does not parse)."""
    if isinstance(created_at, str):
        try:
            return datetime.fromisoformat(created_at).strftime("%Y%m%d%H%M")
        except ValueError:
            pass
    return datetime.now().strftime("%Y%m%d%H%M")


class AMemProvider(MemoryProvider):
    """A-MEM, one store per user (docs/AMEM_BACKEND.md)."""

    # A write takes about two LLM calls; the write barrier orders a
    # retrieval accepted after it.
    synchronous_commit = False

    def __init__(self):
        self.stores = None
        self.default_user_id = DEFAULT_SCOPE
        # A-MEM's LLM annotates and evolves every write.
        self.backend_extraction = True
        # The installed A-MEM commit and Chroma, reported by
        # /memory/config for the run's provenance.
        self.versions: Optional[Dict[str, Optional[str]]] = None

    # -- setup -------------------------------------------------------------

    def initialize(self, config: Dict[str, Any]) -> None:
        from . import ProviderInitializationError

        try:
            from cerebrum.utils import amem as clients

            self._clients = clients
            self.default_user_id = config.get("user_id") or DEFAULT_SCOPE
            namespace = str(config.get("namespace") or "")
            backend_llm = config.get("backend_llm") or {}
            embedding = config.get("embedding") or {}
            if config.get("llm") is None:
                self.stores = clients.shared_stores(
                    backend_llm, embedding, namespace)
            else:  # tests: their own LLM and stores
                self.stores = clients.Stores(
                    config["llm"], clients.embedding_function(embedding),
                    namespace)
            self.versions = clients.versions()
        except Exception as e:
            raise ProviderInitializationError(
                "amem", f"{type(e).__name__}: {e}") from e

    def capabilities(self) -> Dict[str, bool]:
        return {
            "scored_search": True,
            "semantic_search": True,
            "internal_llm": True,
            "native_sdk": True,
        }

    def close(self) -> None:
        self.stores = None

    # -- helpers -------------------------------------------------------------

    def _scope(self, user_id: Optional[str]) -> str:
        return user_id or self.default_user_id

    def _store(self, user_id: Optional[str]):
        if self.stores is None:
            raise ProviderError("A-MEM provider is not initialized")
        return self.stores.store(self._scope(user_id))

    def _lock(self, user_id: Optional[str]):
        return self.stores.lock(self._scope(user_id))

    @staticmethod
    def _candidate(note: Any, score: Optional[float] = None) -> Candidate:
        metadata = _metadata(note.category)
        metadata.update({
            "amem_note_id": note.id,
            "amem_keywords": list(note.keywords or []),
            "amem_context": note.context,
            "amem_tags": (list(note.tags) if isinstance(note.tags, list)
                          else note.tags),
            "amem_links": list(note.links or []),
        })
        return Candidate(memory_id=note.id, content=note.content,
                         metadata=metadata, score=score)

    def _call(self, what: str, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(
                f"A-MEM {what} failed: {type(e).__name__}: {e}") from e

    # -- add -----------------------------------------------------------------

    def add(self, memory_note: "MemoryNote") -> str:
        """One note; returns its id (A-MEM stores every note it is
        given, docs/AMEM_BACKEND.md)."""
        metadata = note_metadata(memory_note)
        scope = metadata.get("user_id") or self.default_user_id
        return self._call("add", self._add, memory_note, metadata, scope)

    def _add(self, memory_note, metadata, scope) -> str:
        store = self._store(scope)
        with self._lock(scope):
            note_id, changed = self._clients.add_note(
                store, memory_note.content,
                category=json.dumps(metadata, default=str),
                time=_time(metadata.get("created_at")))
        logger.info("A-MEM write %s of %s evolved %d note(s)", note_id,
                    scope, len(changed))
        return note_id

    # -- reads ---------------------------------------------------------------

    def search(
        self, query_text: str, user_id: Optional[str], top_k: int
    ) -> List[Candidate]:
        """A-MEM's ``search`` for the user's store, in its order (nearest
        first), each note with a similarity from its squared L2 distance
        (``1 - d/2``: the pinned embedder's vectors are unit vectors)."""
        if top_k <= 0 or not (query_text or "").strip():
            return []
        return self._call("search", self._search, query_text, user_id,
                          int(top_k))

    def _search(self, query_text, user_id, top_k) -> List[Candidate]:
        if not self.stores.has(self._scope(user_id)):
            return []
        store = self._store(user_id)
        with self._lock(user_id):
            rows = []
            for result in store.search(query_text, top_k):
                note = store.memories.get(result["id"])
                if note is None:
                    continue
                score = max(-1.0, min(1.0, similarity_from_distance(
                    float(result["score"]), "l2")))
                rows.append(self._candidate(note, score))
        return rows[:top_k]

    def list(self, user_id: Optional[str], top_k: int) -> List[Candidate]:
        """The user's notes in write order, unscored."""
        if top_k <= 0 or not self.stores.has(self._scope(user_id)):
            return []
        store = self._store(user_id)
        with self._lock(user_id):
            notes = list(store.memories.values())[:int(top_k)]
            return [self._candidate(note) for note in notes]

    def get(
        self, memory_id: str, user_id: Optional[str]
    ) -> Optional[Candidate]:
        if not self.stores.has(self._scope(user_id)):
            return None
        store = self._store(user_id)
        with self._lock(user_id):
            note = store.read(str(memory_id))
            return self._candidate(note) if note is not None else None

    # -- writes to rows ------------------------------------------------------

    def update(
        self,
        memory_id: str,
        user_id: Optional[str],
        content: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> bool:
        """Metadata merges into the note's ``category``; new content goes
        through A-MEM's ``update``, which re-adds the note's document
        with its old keywords, context and tags (no LLM call). A
        metadata-only change rewrites Chroma's metadata alone, with no
        embedding call."""
        return self._call("update", self._update, str(memory_id), user_id,
                          content, metadata)

    def update_metadata(
        self,
        memory_id: str,
        user_id: Optional[str],
        metadata: Dict[str, Any],
    ) -> bool:
        return self.update(memory_id, user_id, None, metadata)

    def _update(self, memory_id, user_id, content, metadata) -> bool:
        if not self.stores.has(self._scope(user_id)):
            return False
        store = self._store(user_id)
        with self._lock(user_id):
            note = store.memories.get(memory_id)
            if note is None:
                return False
            if metadata:
                merged = {**_metadata(note.category), **metadata}
                note.category = json.dumps(merged, default=str)
            if content is not None:
                return bool(store.update(memory_id, content=content))
            if metadata:
                self._write_chroma_category(store, note)
            return True

    @staticmethod
    def _write_chroma_category(store, note) -> None:
        """The note's ``category`` into its Chroma metadata, as A-MEM
        stores metadata (``retrievers.py:57-64``), the document and its
        embedding untouched."""
        collection = store.retriever.collection
        found = collection.get(ids=[note.id], include=["metadatas"])
        if not found["ids"]:
            return
        stored = dict(found["metadatas"][0] or {})
        stored["category"] = str(note.category)
        collection.update(ids=[note.id], metadatas=[stored])

    def delete(self, memory_id: str, user_id: Optional[str]) -> bool:
        """A-MEM's ``delete``: the note leaves the store and Chroma.
        Other notes keep its id in their links and whatever evolution
        wrote into them (docs/AMEM_BACKEND.md, "What deleting a note
        leaves")."""
        return self._call("delete", self._delete, str(memory_id), user_id)

    def _delete(self, memory_id, user_id) -> bool:
        if not self.stores.has(self._scope(user_id)):
            return False
        store = self._store(user_id)
        with self._lock(user_id):
            return bool(store.delete(memory_id))

    # -- the forget's scrub --------------------------------------------------

    def scrub_history(
        self,
        user_id: Optional[str],
        forms: List[str],
        deleted_ids: List[str] = (),
        kept_ids: List[str] = (),
    ) -> Dict[str, Any]:
        """The notes whose derived text carries a form, deleted with no
        LLM call (docs/AMEM_BACKEND.md, "The forget on A-MEM"): A-MEM's
        context, keywords and tags of the note in the store, and its
        Chroma document and metadata (which evolution never updates).
        They are reported as ``detached`` rows with the reason
        ``derived``; ``history`` counts them, and ``messages`` is 0
        (A-MEM keeps none)."""
        return self._call("scrub", self._scrub, user_id, list(forms or ()))

    def _scrub(self, user_id, forms) -> Dict[str, Any]:
        from aios.memory.pipeline.matching import match_forms

        if not forms or not self.stores.has(self._scope(user_id)):
            return {"messages": 0, "history": 0}

        def carries(text: Any) -> bool:
            return bool(text) and bool(match_forms(str(text), forms))

        store = self._store(user_id)
        with self._lock(user_id):
            stored = store.retriever.collection.get(
                include=["documents", "metadatas"])
            chroma = {
                note_id: (document or "") + " " + " ".join(
                    str((meta or {}).get(key) or "")
                    for key in ("context", "keywords", "tags"))
                for note_id, document, meta in zip(
                    stored["ids"], stored["documents"],
                    stored["metadatas"])}
            carriers = []
            for note in list(store.memories.values()):
                derived = " ".join([
                    str(note.context or ""),
                    json.dumps(note.keywords, default=str),
                    json.dumps(note.tags, default=str),
                    chroma.get(note.id, "")])
                if carries(derived):
                    carriers.append(note)
            detached = []
            for note in carriers:
                if store.delete(note.id):
                    detached.append({
                        "memory_id": note.id,
                        "owner_agent": _metadata(note.category).get(
                            "owner_agent", ""),
                        "reason": REASON_DERIVED,
                    })
        if detached:
            logger.info("A-MEM scrub of %s: %d note(s) whose derived text "
                        "carried a form deleted",
                        self._scope(user_id), len(detached))
        counts: Dict[str, Any] = {"messages": 0, "history": len(detached)}
        if detached:
            counts["detached"] = detached
        return counts
