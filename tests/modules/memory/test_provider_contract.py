"""The provider contract (docs/PROVIDER_CONTRACT.md), run against every
conforming provider.

``chroma_inhouse`` and ``mem0`` use real stores in a temp directory and
the pinned embedding model on a local Ollama; they are skipped without
one. ``graphiti`` (NeurIPS Subtask 16) runs Graphiti on the local Neo4j
and the pinned embedder, in a namespace of its own, with a scripted LLM
that makes each write one fact worded as the write
(``_graphiti_script.py``; docs/GRAPHITI_BACKEND.md, "Tests"); it is
skipped without Ollama or Neo4j. ``in_house`` is the in-memory dict
provider.
"""
import requests
import pytest

from cerebrum.memory.apis import MemoryQuery

from aios.memory.embedding import DEFAULTS, EmbeddingConfig
from aios.memory.manager import MemoryManager
from aios.memory.note import MemoryNote
from aios.memory.providers.base import CAPABILITIES, REQUIRED_METADATA
from aios.memory.providers.chroma_inhouse import ChromaInHouseProvider
from aios.memory.providers.in_house import InHouseProvider
from aios.memory.providers.mem0 import Mem0Provider
from aios.memory.write_barrier import MemoryWriteBarrier
from aios.syscall.memory import MemorySyscall

from tests.modules.memory._graphiti_script import (
    drop, graphiti_provider, needs_neo4j,
)

USER = "contract_user"
OTHER_USER = "contract_other"
EMBEDDING = EmbeddingConfig.from_memory_config({})


def retrieve_syscall(agent, user, text, operation="retrieve_memory"):
    """A retrieval as the SDK sends it."""
    return MemorySyscall(agent, MemoryQuery(
        operation_type=operation,
        params={"content": text, "k": 10, "user_id": user},
    ))


def ollama_ready() -> bool:
    try:
        tags = requests.get(
            f"{DEFAULTS['ollama_base_url']}/api/tags", timeout=2
        ).json()
    except (requests.RequestException, ValueError):
        return False
    return any(
        m.get("name", "").startswith(EMBEDDING.model)
        for m in tags.get("models", [])
    )


needs_ollama = pytest.mark.skipif(
    not ollama_ready(), reason="needs a local Ollama with the pinned model"
)


def build(name, tmp_path):
    if name == "in_house":
        provider = InHouseProvider()
        provider.initialize({})
    elif name == "graphiti":
        provider = graphiti_provider()
    elif name == "chroma_inhouse":
        provider = ChromaInHouseProvider()
        provider.initialize({
            "path": str(tmp_path / "chroma"),
            "embedding": EMBEDDING.as_dict(),
        })
    else:
        provider = Mem0Provider()
        provider.initialize({
            "user_id": "default",
            "embedder": EMBEDDING.mem0_embedder(),
            "llm": {"provider": "ollama", "config": {
                "model": "qwen2.5:7b",
                "ollama_base_url": EMBEDDING.ollama_base_url,
            }},
            "vector_store": {"provider": "chroma", "config": {
                "collection_name": "contract",
                "path": str(tmp_path / "mem0"),
            }},
        })
    return provider


@pytest.fixture(params=[
    pytest.param("chroma_inhouse", marks=needs_ollama),
    pytest.param("mem0", marks=needs_ollama),
    pytest.param("graphiti", marks=[needs_ollama, needs_neo4j]),
    "in_house",
])
def provider(request, tmp_path):
    provider = build(request.param, tmp_path)
    yield provider
    if request.param == "graphiti":
        drop(provider)
    else:
        provider.close()


def note(content, owner="profile_agent", policy="private", user=USER,
         memory_type="profile", **extra):
    memory = MemoryNote(content=content, tags=["t1", "t2"])
    memory.metadata = {
        "owner_agent": owner,
        "user_id": user,
        "memory_type": memory_type,
        "sharing_policy": policy,
        "created_at": "2026-11-02T00:00:00+00:00",
        **extra,
    }
    return memory


DOCS = [
    "The user prefers Python and edits code in VS Code.",
    "The current project is a Rust web server with tail latency.",
    "A lasagna recipe that needs ricotta and fresh basil.",
]
QUERY = "Which editor and language does the user prefer Python VS Code"


def test_capabilities_are_complete_bools(provider):
    caps = provider.capabilities()
    assert set(caps) == set(CAPABILITIES)
    assert all(isinstance(v, bool) for v in caps.values())


def test_add_get_round_trips_content_and_required_metadata(provider):
    memory = note("verbatim: {\"a\": 1}  spaces ", extra_key="x")
    memory_id = provider.add(memory)
    assert isinstance(memory_id, str) and memory_id
    found = provider.get(memory_id, USER)
    assert found.memory_id == memory_id
    assert found.content == memory.content
    for key in REQUIRED_METADATA:
        assert key in found.metadata, key
        if key != "created_at":  # Mem0 stamps its own time
            assert found.metadata[key] == memory.metadata[key], key
    assert found.metadata["extra_key"] == "x"
    assert found.metadata["tags"] == ["t1", "t2"]


def test_search_scores_honestly_and_ranks_closest_first(provider):
    ids = [provider.add(note(doc)) for doc in DOCS]
    found = provider.search(QUERY, USER, top_k=10)
    assert {c.memory_id for c in found} == set(ids)
    assert found[0].memory_id == ids[0]
    if provider.capabilities()["scored_search"]:
        scores = [c.score for c in found]
        assert all(isinstance(s, float) for s in scores)
        assert scores == sorted(scores, reverse=True)
        assert all(-1.0 <= s <= 1.0 for s in scores)
    assert len(provider.search(QUERY, USER, top_k=2)) == 2


def test_search_and_list_stay_in_the_user_scope(provider):
    provider.add(note(DOCS[0]))
    provider.add(note(DOCS[1], user=OTHER_USER))
    assert [c.content for c in provider.search(QUERY, USER, 10)] == [DOCS[0]]
    assert [c.content for c in provider.list(OTHER_USER, 10)] == [DOCS[1]]


def test_list_is_unscored_in_storage_order(provider):
    ids = [provider.add(note(doc)) for doc in DOCS]
    listed = provider.list(USER, top_k=10)
    assert [c.memory_id for c in listed] == ids
    assert all(c.score is None for c in listed)
    assert len(provider.list(USER, top_k=2)) == 2


def test_update_replaces_content_and_merges_metadata(provider):
    memory_id = provider.add(note(DOCS[2]))
    assert provider.update(
        memory_id, USER, DOCS[0], {"sharing_policy": "shared"}
    )
    found = provider.get(memory_id, USER)
    assert found.content == DOCS[0]
    assert found.metadata["sharing_policy"] == "shared"
    assert found.metadata["owner_agent"] == "profile_agent"
    assert found.metadata["memory_type"] == "profile"
    assert provider.search(QUERY, USER, 1)[0].memory_id == memory_id
    assert provider.update(memory_id, USER, None, {"tags": ["new"]})
    assert provider.get(memory_id, USER).content == DOCS[0]
    assert not provider.update("missing-id", USER, "x", None)


def test_delete(provider):
    memory_id = provider.add(note(DOCS[0]))
    assert provider.delete(memory_id, USER)
    assert provider.get(memory_id, USER) is None
    assert not provider.delete(memory_id, USER)
    assert provider.search(QUERY, USER, 10) == []


def test_get_unknown_id_is_none(provider):
    provider.add(note(DOCS[0]))
    assert provider.get("no-such-id", USER) is None


def test_provider_never_filters_by_visibility(provider):
    """Agent B's private memory comes back from search; the kernel is
    what removes it for agent A."""
    mine = provider.add(note(DOCS[0], owner="agent_a"))
    theirs = provider.add(note(DOCS[1], owner="agent_b"))
    shared = provider.add(note(DOCS[2], owner="agent_b", policy="shared"))
    assert {c.memory_id for c in provider.search(QUERY, USER, 10)} == {
        mine, theirs, shared,
    }

    manager = MemoryManager.__new__(MemoryManager)
    manager.provider = provider
    manager.barrier = MemoryWriteBarrier(config={})
    manager.relevance_threshold = 0.0
    rows, diagnostics = manager.retrieve_for_agent(
        "agent_a", USER, QUERY, k=10, include_shared=True,
        request_user_id=USER,
    )
    assert {r["memory_id"] for r in rows} == {mine, shared}
    assert diagnostics["after_partition"] > diagnostics["after_visibility"]
    if provider.capabilities()["scored_search"]:
        assert diagnostics["scores_present"]
        assert diagnostics["threshold_used"] == 0.0

    # SDK search scoped to the user: own memories and shared ones.
    response = manager.address_request(
        retrieve_syscall("agent_a", USER, QUERY)
    )
    assert {r["memory_id"] for r in response.search_results} == {
        mine, shared,
    }


def test_no_provider_module_has_a_visibility_filter():
    import inspect
    from aios.memory import providers
    from aios.memory.providers import (
        base, chroma_inhouse, graphiti, in_house, mem0,
    )

    for module in (base, chroma_inhouse, graphiti, in_house, mem0,
                   providers):
        source = inspect.getsource(module)
        assert "sharing_filter" not in source, module.__name__


def test_retrieve_memory_raw_goes_through_the_kernel_rule(tmp_path):
    provider = build("in_house", tmp_path)
    provider.add(note("mine", owner="agent_a"))
    provider.add(note("theirs", owner="agent_b"))
    manager = MemoryManager.__new__(MemoryManager)
    manager.provider = provider
    manager.barrier = MemoryWriteBarrier(config={})
    manager.relevance_threshold = 0.0
    notes = manager.address_request(
        retrieve_syscall("agent_a", USER, "x", operation="retrieve_memory_raw")
    )
    assert [n.content for n in notes] == ["mine"]

