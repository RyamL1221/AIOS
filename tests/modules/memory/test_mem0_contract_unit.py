"""Mem0Provider's contract methods over a fake Mem0 client (no Ollama).

Replaces the pre-contract tests of the ``get_all`` retrieval path
(test_mem0_provider_user_filter, test_mem0_cross_user_retrieval, the
provider-filter classes of test_mem0_cross_user_isolation and
test_mem0_cross_agent_retrieval): the same invariants, on the contract.
The real-store version is test_provider_contract.py.
"""
import logging

import pytest
from cerebrum.llm.apis import LLMQuery

from aios.memory.context_injector import ContextInjector
from aios.memory.manager import MemoryManager
from aios.memory.note import MemoryNote
from aios.memory.write_barrier import MemoryWriteBarrier
from tests.modules.memory._doubles.fake_mem0 import (
    FakeMem0Client,
    provider_with,
)

ALICE = "alice__kernel_shared"
BOB = "bob__kernel_shared"


def note(content, user, owner="profile_agent", policy="shared",
         memory_type="profile"):
    memory = MemoryNote(content=content)
    memory.metadata = {
        "owner_agent": owner, "user_id": user, "memory_type": memory_type,
        "sharing_policy": policy, "created_at": "kernel-time",
    }
    return memory


@pytest.fixture
def client():
    return FakeMem0Client()


@pytest.fixture
def provider(client):
    return provider_with(client)


def test_search_is_prefiltered_to_the_user(provider, client):
    provider.add(note("alice prefers python", ALICE))
    provider.add(note("bob prefers python", BOB))
    found = provider.search("prefers python", ALICE, 10)
    assert [c.content for c in found] == ["alice prefers python"]
    assert client.vector_store.search_calls[-1]["filters"] == {
        "user_id": ALICE,
    }


def test_search_scores_are_similarities_closest_first(provider):
    provider.add(note("lasagna recipe ricotta", ALICE))
    provider.add(note("user prefers python vs code", ALICE))
    found = provider.search("python vs code", ALICE, 10)
    assert found[0].content == "user prefers python vs code"
    assert found[0].score > found[1].score
    # Squared L2 on unit vectors is 2 - 2 cos.
    assert found[1].score == pytest.approx(0.0)


def test_search_without_a_user_uses_the_default_scope(provider, client):
    provider.add(note("x", "default"))
    provider.search("x", None, 5)
    assert client.vector_store.search_calls[-1]["filters"] == {
        "user_id": "default",
    }


def test_list_is_get_all_with_the_user_filter_and_top_k(provider, client):
    first = provider.add(note("one", ALICE))
    second = provider.add(note("two", ALICE))
    provider.add(note("three", BOB))
    listed = provider.list(ALICE, 7)
    assert [c.memory_id for c in listed] == [first, second]
    assert all(c.score is None for c in listed)
    assert client.get_all_calls[-1] == {
        "filters": {"user_id": ALICE}, "top_k": 7,
    }


def test_promoted_keys_are_in_the_metadata(provider):
    memory_id = provider.add(note("x", ALICE))
    for candidate in (provider.get(memory_id, ALICE),
                      provider.list(ALICE, 5)[0],
                      provider.search("x", ALICE, 5)[0]):
        assert candidate.metadata["user_id"] == ALICE
        assert candidate.metadata["owner_agent"] == "profile_agent"
        assert candidate.metadata["created_at"]


def test_add_stores_verbatim_with_the_required_metadata(provider, client):
    provider.add(note("raw {json}", ALICE))
    call = client.add_calls[-1]
    assert call["infer"] is False
    assert call["user_id"] == ALICE
    for key in ("owner_agent", "user_id", "memory_type",
                "sharing_policy", "created_at"):
        assert key in call["metadata"]


def test_add_waits_until_the_memory_is_readable(provider, client):
    client.vector_store.unreadable_reads = 3
    provider.add(note("x", ALICE))
    assert client.vector_store.unreadable_reads == 0


def test_add_warns_when_never_readable(provider, client, caplog):
    client.vector_store.unreadable_reads = 10 ** 6
    with caplog.at_level(logging.WARNING):
        provider._await_stored(client, "m", max_wait=0.05, interval=0.01)
    assert "not readable" in caplog.text


def test_update_merges_metadata_and_keeps_the_owner(provider, client):
    memory_id = provider.add(note("old", ALICE, policy="private"))
    assert provider.update(memory_id, ALICE, "new",
                           {"sharing_policy": "shared"})
    found = provider.get(memory_id, ALICE)
    assert found.content == "new"
    assert found.metadata["sharing_policy"] == "shared"
    assert found.metadata["owner_agent"] == "profile_agent"
    assert "created_at" not in client.update_calls[-1]["metadata"]
    assert not provider.update("missing", ALICE, "x", None)


def test_delete_and_missing_get(provider):
    memory_id = provider.add(note("x", ALICE))
    assert provider.delete(memory_id, ALICE)
    assert provider.get(memory_id, ALICE) is None
    assert not provider.delete(memory_id, ALICE)


def kernel(provider):
    manager = MemoryManager.__new__(MemoryManager)
    manager.provider = provider
    manager.barrier = MemoryWriteBarrier(config={})
    manager.relevance_threshold = 0.0
    injector = ContextInjector(manager, {
        "auto_inject": True, "max_injected_memories": 5,
        "max_memory_tokens": 8000,
    })
    return manager, injector


def chat(text):
    return LLMQuery(messages=[{"role": "user", "content": text}],
                    action_type="chat")


def test_injection_gets_another_agents_shared_memory_for_the_user(provider):
    provider.add(note("alice prefers python", ALICE))
    provider.add(note("alice private draft", ALICE, owner="task_agent",
                      policy="private"))
    provider.add(note("bob prefers python", BOB))
    _, injector = kernel(provider)
    query, diagnostics = injector.inject(
        "assistant_agent", chat("python?"), user_id=ALICE
    )
    block = query.messages[0]["content"]
    assert "alice prefers python" in block
    assert "bob" not in block and "draft" not in block
    assert diagnostics["injected_count"] == 1
    assert diagnostics["source_agents"] == ["profile_agent"]
    assert diagnostics["scores_present"] is True
    assert diagnostics["threshold_used"] == 0.0


def test_no_shared_injection_without_a_request_user(provider):
    provider.add(note("alice prefers python", ALICE))
    _, injector = kernel(provider)
    _, diagnostics = injector.inject("assistant_agent", chat("python?"))
    assert diagnostics["injected_count"] == 0


# --- a failed read is not a missing row (Subtask 15 review) -------------


def failing_reads(client, error):
    """Make the client's ``get`` and its vector store's raise ``error``
    from now on: IndexError is how Mem0's Chroma adapter reports a
    missing id; anything else is a failed read (a locked file)."""
    def raise_error(*args, **kwargs):
        raise error
    client.get = raise_error
    client.vector_store.get = raise_error


def test_a_missing_row_is_none_and_nothing_is_deleted(provider, client):
    """IndexError, Mem0's missing-id signal, reads as no row: ``get`` is
    None and delete, update and update_metadata answer False."""
    kept = provider.add(note("my lawyer is Greta Sandvik", ALICE))
    failing_reads(client, IndexError("list index out of range"))
    assert provider.get(kept, ALICE) is None
    assert provider.delete(kept, ALICE) is False
    assert provider.update(kept, ALICE, "x", None) is False
    assert provider.update_metadata(kept, ALICE, {"a": 1}) is False
    assert kept in client.store


def test_a_failed_read_raises_and_deletes_nothing(provider, client):
    """Any other error from Mem0's read is a failed read, not a missing
    row: ``get``, delete, update and update_metadata raise
    ProviderError, and the row is not deleted."""
    from aios.memory.providers.base import ProviderError

    kept = provider.add(note("my lawyer is Greta Sandvik", ALICE))
    failing_reads(client, TimeoutError("database is locked"))
    for call in (
        lambda: provider.get(kept, ALICE),
        lambda: provider.delete(kept, ALICE),
        lambda: provider.update(kept, ALICE, "x", None),
        lambda: provider.update_metadata(kept, ALICE, {"a": 1}),
    ):
        with pytest.raises(ProviderError, match="database is locked"):
            call()
    assert kept in client.store


def test_a_forget_over_a_failed_read_fails(provider, client):
    """A forget whose delete meets a failed read raises instead of
    filing the row as not found and reporting success."""
    import json

    from aios.memory.pipeline import MemoryPipeline
    from aios.memory.providers.base import ProviderError

    pipeline = MemoryPipeline(provider, barrier=None)
    memory = note("My lawyer is Greta Sandvik.", ALICE)
    memory.metadata.update({
        "fact_key": "lawyer", "provenance_event": "e1",
        "structured": json.dumps({"value": "Greta Sandvik"}),
    })
    kept = pipeline.write("profile_agent", ALICE, memory)
    failing_reads(client, TimeoutError("database is locked"))
    with pytest.raises(ProviderError, match="database is locked"):
        pipeline.forget("profile_agent", ALICE, "lawyer")
    assert kept in client.store
