"""A fake Mem0 ``Memory`` client for Mem0Provider unit tests.

One store shared by every user, so a provider that forgets the
``user_id`` filter leaks rows and fails. ``vector_store.search`` returns
Chroma-shaped hits whose ``score`` is a squared-L2 distance, as Mem0's
Chroma adapter does; ``get_all`` and ``get`` return Mem0's item shape,
with ``user_id`` and ``created_at`` promoted to the top level.
"""
import math
import re
import uuid
from collections import Counter
from types import SimpleNamespace

PROMOTED = ("user_id", "agent_id", "run_id", "actor_id", "role")
CORE = {"data", "hash", "created_at", "updated_at", "text_lemmatized"}


def _words(text):
    return Counter(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _distance(a, b):
    """Squared L2 between unit vectors with this bag-of-words cosine."""
    wa, wb = _words(a), _words(b)
    dot = sum(wa[w] * wb[w] for w in wa.keys() & wb.keys())
    norm = math.sqrt(sum(v * v for v in wa.values())) * math.sqrt(
        sum(v * v for v in wb.values())
    )
    cosine = dot / norm if norm else 0.0
    return 2.0 - 2.0 * cosine


def _matches(payload, filters):
    return all(payload.get(k) == v for k, v in (filters or {}).items())


class FakeVectorStore:
    def __init__(self, store):
        self.store = store
        self.search_calls = []
        self.collection = SimpleNamespace(
            count=lambda: len(self.store), metadata=None
        )
        self.unreadable_reads = 0  # get() returns None this many times

    def search(self, query, vectors, top_k, filters=None):
        self.search_calls.append({"top_k": top_k, "filters": filters})
        hits = [
            SimpleNamespace(
                id=memory_id,
                score=_distance(query, payload["data"]),
                payload=dict(payload),
            )
            for memory_id, payload in self.store.items()
            if _matches(payload, filters)
        ]
        hits.sort(key=lambda hit: hit.score)
        return hits[:top_k]

    def get(self, vector_id):
        if self.unreadable_reads:
            self.unreadable_reads -= 1
            return None
        payload = self.store.get(vector_id)
        return SimpleNamespace(id=vector_id, payload=payload) if payload \
            else None


class FakeMem0Client:
    def __init__(self):
        self.store = {}
        self.vector_store = FakeVectorStore(self.store)
        self.embedding_model = SimpleNamespace(embed=lambda text, kind: [0.0])
        self.add_calls = []
        self.get_all_calls = []
        self.update_calls = []

    @staticmethod
    def _item(memory_id, payload):
        item = {
            "id": memory_id,
            "memory": payload["data"],
            "created_at": payload.get("created_at"),
        }
        for key in PROMOTED:
            if key in payload:
                item[key] = payload[key]
        extra = {
            k: v for k, v in payload.items()
            if k not in CORE and k not in PROMOTED
        }
        if extra:
            item["metadata"] = extra
        return item

    def add(self, content, user_id, metadata=None, infer=True, **kwargs):
        self.add_calls.append(
            {"user_id": user_id, "metadata": metadata, "infer": infer}
        )
        memory_id = str(uuid.uuid4())
        self.store[memory_id] = {
            **(metadata or {}),
            "data": content,
            "user_id": user_id,
            "created_at": "mem0-time",
        }
        return {"results": [{"id": memory_id, "event": "ADD"}]}

    def get_all(self, filters=None, top_k=20):
        self.get_all_calls.append({"filters": filters, "top_k": top_k})
        return {"results": [
            self._item(memory_id, payload)
            for memory_id, payload in self.store.items()
            if _matches(payload, filters)
        ][:top_k]}

    def get(self, memory_id):
        payload = self.store.get(memory_id)
        return self._item(memory_id, payload) if payload else None

    def update(self, memory_id, data, metadata=None):
        self.update_calls.append({"data": data, "metadata": metadata})
        old = self.store[memory_id]
        self.store[memory_id] = {
            **(metadata or {}),
            "data": data,
            "user_id": old["user_id"],
            "created_at": old["created_at"],
        }

    def delete(self, memory_id):
        del self.store[memory_id]


def provider_with(client):
    """A Mem0Provider whose every user goes to ``client``."""
    from aios.memory.providers.mem0 import Mem0Provider

    provider = Mem0Provider()
    provider.client = client
    provider._get_client_for_user = lambda user_id: client
    return provider
