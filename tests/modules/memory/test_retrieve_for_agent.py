"""Tests for the single kernel retrieval path.

Covers ``MemoryManager.retrieve_for_agent`` directly and through both of
its callers, ``ContextInjector.inject`` and the ``retrieve_memory``
branch of ``address_request``.
"""
import re
from pathlib import Path
from unittest.mock import MagicMock

from cerebrum.llm.apis import LLMQuery
from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from aios.memory.context_injector import ContextInjector
from aios.memory.manager import MemoryManager
from aios.memory.providers.base import Candidate, ProviderError
from aios.memory.write_barrier import MemoryWriteBarrier, WaitOutcome
from aios.syscall.memory import MemorySyscall

AGENT = "assistant_agent"
USER = "alice"


def row(content, owner=AGENT, policy="private", user=USER, score=None):
    """Build one provider search result."""
    return {
        "memory_id": f"id-{content}",
        "content": content,
        "timestamp": "t",
        "score": score,
        "metadata": {
            "user_id": user,
            "owner_agent": owner,
            "sharing_policy": policy,
            "memory_type": "profile",
        },
    }


def candidates(rows):
    """Provider search results for ``rows``."""
    return [
        Candidate(
            r["memory_id"], r["content"],
            {"timestamp": r["timestamp"], **r["metadata"]}, r["score"],
        )
        for r in rows
    ]


def make_manager(rows, threshold=0.3):
    """Build a manager whose provider returns ``rows`` for any query."""
    manager = MemoryManager.__new__(MemoryManager)
    manager.provider = MagicMock()
    manager.provider.search.return_value = candidates(rows)
    manager.barrier = MemoryWriteBarrier(config={})
    manager.relevance_threshold = threshold
    return manager


def make_injector(manager, k=5):
    """Build an enabled injector over ``manager``."""
    return ContextInjector(
        memory_manager=manager,
        config={
            "auto_inject": True,
            "max_injected_memories": k,
            "max_memory_tokens": 8000,
        },
    )


def chat_query():
    """Build a chat query that triggers injection."""
    return LLMQuery(
        messages=[{"role": "user", "content": "hello"}],
        action_type="chat",
    )


def sdk_retrieve(manager, agent, **params):
    """Run a retrieve_memory syscall as the SDK sends it."""
    query = MemoryQuery(
        operation_type="retrieve_memory",
        params={"content": "q", "k": 5, **params},
    )
    return manager.address_request(MemorySyscall(agent, query))


def test_injector_source_never_touches_the_provider():
    source = Path(
        "aios/memory/context_injector.py"
    ).read_text()
    assert not re.search(r"provider\.", source)


def test_injector_retrieves_only_through_the_manager():
    # Since Subtask 8 the single path is the manager's MemoryPipeline
    # (retrieve_for_agent delegates to the same library call).
    provider = MagicMock()
    manager = MagicMock()
    manager.provider = provider
    manager.memory_pipeline.return_value.inject.return_value = (
        [], {"resolved_user_id": USER, "injected_count": 0},
    )
    make_injector(manager).inject(AGENT, chat_query(), user_id=USER)
    manager.memory_pipeline.return_value.inject.assert_called_once()
    assert provider.mock_calls == []


def test_sdk_search_without_policy_hides_other_agents_private():
    manager = make_manager([
        row("mine"),
        row("secret", owner="profile_agent"),
        row("open", owner="profile_agent", policy="shared"),
    ])
    response = sdk_retrieve(manager, AGENT, user_id=USER)
    assert response.success
    assert [r["content"] for r in response.search_results] == [
        "mine", "open",
    ]


def test_injection_hides_other_agents_private():
    manager = make_manager([row("secret", owner="profile_agent")])
    query, diagnostics = make_injector(manager).inject(
        AGENT, chat_query(), user_id=USER
    )
    assert diagnostics["injected_count"] == 0
    assert "secret" not in str(query.messages)


def test_sdk_search_returns_memory_id():
    manager = make_manager([row("mine")])
    response = sdk_retrieve(manager, AGENT, user_id=USER)
    assert response.search_results[0]["memory_id"] == "id-mine"


def test_sdk_private_policy_still_excludes_shared_rows():
    manager = make_manager([
        row("mine"),
        row("open", owner="profile_agent", policy="shared"),
    ])
    response = sdk_retrieve(
        manager, AGENT, user_id=USER, sharing_policy="private"
    )
    assert [r["content"] for r in response.search_results] == ["mine"]


def test_provider_failure_reaches_the_sdk_caller():
    manager = make_manager([])
    manager.provider.search.side_effect = ProviderError("boom")
    response = sdk_retrieve(manager, AGENT, user_id=USER)
    assert not response.success
    assert "boom" in response.error


def test_threshold_drops_low_scores_when_scores_present():
    manager = make_manager([
        row("low", score=0.1), row("high", score=0.9),
    ])
    results, diagnostics = manager.retrieve_for_agent(
        AGENT, USER, "q", k=5, include_shared=False
    )
    assert [r["content"] for r in results] == ["high"]
    assert diagnostics["scores_present"] is True
    assert diagnostics["after_dedupe"] == 2
    assert diagnostics["after_threshold"] == 1


def test_scores_sort_descending():
    manager = make_manager([
        row("mid", score=0.5), row("high", score=0.9),
    ])
    results, _ = manager.retrieve_for_agent(
        AGENT, USER, "q", k=5, include_shared=False
    )
    assert [r["content"] for r in results] == ["high", "mid"]


def test_no_scores_drops_nothing_and_keeps_order():
    manager = make_manager([row("b"), row("a")], threshold=0.99)
    results, diagnostics = manager.retrieve_for_agent(
        AGENT, USER, "q", k=5, include_shared=False
    )
    assert [r["content"] for r in results] == ["b", "a"]
    assert diagnostics["scores_present"] is False


def test_k_caps_after_dedupe():
    manager = make_manager([])
    own = [row(f"own{i}") for i in range(3)]
    shared = [
        row(f"own{i}", owner="profile_agent", policy="shared")
        for i in range(3)
    ] + [
        row(f"shared{i}", owner="profile_agent", policy="shared")
        for i in range(3)
    ]
    manager.provider.search.side_effect = [
        candidates(own), candidates(shared),
    ]
    results, diagnostics = manager.retrieve_for_agent(
        AGENT, USER, "q", k=4, include_shared=True
    )
    assert diagnostics["after_visibility"] == 9
    assert diagnostics["after_dedupe"] == 6
    assert diagnostics["after_cap"] == 4
    assert [r["content"] for r in results] == [
        "own0", "own1", "own2", "shared0",
    ]


def test_explicit_top_k_reaches_the_provider():
    manager = make_manager([])
    _, diagnostics = manager.retrieve_for_agent(
        AGENT, USER, "q", k=7, include_shared=True
    )
    calls = manager.provider.search.call_args_list
    assert [c.args[2] for c in calls] == [7, 28]
    assert diagnostics["top_k_used"] == {"own": 7, "shared": 28}


def test_partition_fails_closed():
    manager = make_manager([
        row("other", user="bob"), row("none", user=""), row("mine"),
    ])
    results, diagnostics = manager.retrieve_for_agent(
        AGENT, USER, "q", k=5, include_shared=False
    )
    assert [r["content"] for r in results] == ["mine"]
    assert diagnostics["after_partition"] == 1


def test_no_identity_skips_shared_retrieval():
    manager = make_manager([row("mine", user=AGENT)])
    results, diagnostics = manager.retrieve_for_agent(
        AGENT, None, "q", k=5, include_shared=True
    )
    assert manager.provider.search.call_count == 1
    assert diagnostics["resolved_user_id"] is None
    assert [r["content"] for r in results] == ["mine"]


def test_barrier_waited_once_per_injection():
    manager = make_manager([row("x")])
    manager.barrier = MagicMock()
    manager.barrier.snapshot.return_value = 7
    manager.barrier.wait_until_drained.return_value = (
        WaitOutcome.DRAINED
    )
    _, diagnostics = make_injector(manager).inject(
        AGENT, chat_query(), user_id=USER
    )
    manager.barrier.wait_until_drained.assert_called_once_with(USER, 7)
    assert diagnostics["barrier_waits"] == [
        {"user_id": USER, "outcome": "DRAINED"}
    ]


def test_sdk_search_waits_on_the_acceptance_snapshot():
    manager = make_manager([])
    manager.barrier = MagicMock()
    manager.barrier.wait_until_drained.return_value = (
        WaitOutcome.DRAINED
    )
    query = MemoryQuery(
        operation_type="retrieve_memory",
        params={"content": "q", "k": 5, "user_id": USER},
    )
    syscall = MemorySyscall(AGENT, query)
    syscall.barrier_snapshot = 3
    manager.address_request(syscall)
    manager.barrier.snapshot.assert_not_called()
    manager.barrier.wait_until_drained.assert_called_once_with(USER, 3)


def test_add_memory_stamps_owner_agent():
    manager = make_manager([])
    manager._known_user_ids = {}
    manager.provider.add.return_value = "m"
    query = MemoryQuery(
        operation_type="add_memory", params={"content": "c"}
    )
    manager.address_request(MemorySyscall(AGENT, query))
    note = manager.provider.add.call_args.args[0]
    assert note.metadata["owner_agent"] == AGENT


def test_injection_diagnostics_cover_every_stage():
    manager = make_manager([
        row("kept", owner="profile_agent", policy="shared"),
    ])
    _, diagnostics = make_injector(manager).inject(
        AGENT, chat_query(), user_id=USER
    )
    for key in (
        "resolved_user_id", "own_fetched", "shared_fetched",
        "after_partition", "after_visibility", "after_dedupe",
        "scores_present", "after_threshold", "after_cap",
        "top_k_used", "after_budget", "tokens_estimated",
    ):
        assert key in diagnostics
    assert diagnostics["after_budget"] == 1
    assert diagnostics["tokens_estimated"] > 0
    assert diagnostics["injected_memories"][0]["memory_id"] == "id-kept"


def test_diagnostics_reach_the_llm_response():
    from aios.syscall.syscall import SyscallExecutor

    executor = SyscallExecutor()
    query = chat_query()
    executor.context_injector = MagicMock()
    executor.context_injector.inject.return_value = (
        query, {"injected_count": 1}
    )
    executor.execute_llm_syscall = MagicMock(
        return_value={"response": "ok"}
    )
    result = executor.execute_request(AGENT, query)
    diagnostics = result["injection_diagnostics"]
    assert diagnostics["injected_count"] == 1
    # The latency breakdown is added to them (Subtask 7).
    assert diagnostics["kernel_overhead_ms"] == 0.0
    assert diagnostics["llm_ms"] is None


def test_sdk_search_applies_threshold_on_a_scored_provider():
    manager = make_manager([
        row("low", score=0.2), row("high", score=0.8),
    ], threshold=0.5)
    response = sdk_retrieve(manager, AGENT, user_id=USER)
    assert [r["content"] for r in response.search_results] == ["high"]


def test_add_memory_keeps_an_explicit_owner():
    manager = make_manager([])
    manager._known_user_ids = {}
    manager.provider.add.return_value = "m"
    query = MemoryQuery(
        operation_type="add_memory",
        params={"content": "c", "metadata": {"owner_agent": "other"}},
    )
    manager.address_request(MemorySyscall(AGENT, query))
    note = manager.provider.add.call_args.args[0]
    assert note.metadata["owner_agent"] == "other"


def stored_memory(owner, policy):
    """Build a provider get result."""
    return Candidate(
        "m", "body", {"owner_agent": owner, "sharing_policy": policy}
    )


def sdk_get(manager, agent):
    """Run a get_memory syscall as the SDK sends it."""
    query = MemoryQuery(
        operation_type="get_memory", params={"memory_id": "m"}
    )
    return manager.address_request(MemorySyscall(agent, query))


def test_get_memory_hides_another_agents_private_memory():
    manager = make_manager([])
    manager.provider.get.return_value = stored_memory(
        "agent_a", "private"
    )
    response = sdk_get(manager, "agent_b")
    assert not response.success
    assert response.content is None
    assert response.error == "Memory not found"


def test_get_memory_allows_owner_and_shared():
    manager = make_manager([])
    manager.provider.get.return_value = stored_memory(
        "agent_a", "private"
    )
    assert sdk_get(manager, "agent_a").content == "body"
    manager.provider.get.return_value = stored_memory(
        "agent_a", "shared"
    )
    assert sdk_get(manager, "agent_b").content == "body"


def test_get_memory_fails_closed_without_an_owner():
    manager = make_manager([])
    manager.provider.get.return_value = Candidate("m", "body", {})
    assert not sdk_get(manager, "agent_b").success
