"""Tests for the conversation write path and owner-only by-id writes.

Conversation memories go through ``MemoryManager.address_request`` so
the write barrier covers them, and only an owner may update or delete a
memory by id.
"""
import threading
import time
from collections import OrderedDict
from unittest.mock import MagicMock, patch

from cerebrum.llm.apis import LLMQuery
from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from aios.memory.context_injector import ContextInjector
from aios.memory.conversation_extractor import ConversationExtractor
from aios.memory.manager import MemoryManager
from aios.memory.providers.base import Candidate
from tests.modules.memory._doubles.legacy import (
    LegacyProviderAdapter as MemoryProvider,
)
from aios.memory.write_barrier import MemoryWriteBarrier
from aios.syscall.memory import MemorySyscall

AGENT = "assistant_agent"
USER = "alice"
WAIT_SECONDS = 5


class StoreProvider(MemoryProvider):
    """In-memory provider with barrier semantics, like Mem0."""

    def __init__(self):
        self.rows = {}
        self.fail_writes = False
        self.write_gate = threading.Event()
        self.write_gate.set()
        self.written = threading.Event()

    def initialize(self, config):
        pass

    def add_memory(self, memory_note):
        self.write_gate.wait(WAIT_SECONDS)
        try:
            if self.fail_writes:
                raise RuntimeError("store down")
            self.rows[memory_note.id] = memory_note
            return MemoryResponse(success=True, memory_id=memory_note.id)
        finally:
            self.written.set()

    def remove_memory(self, memory_id):
        del self.rows[memory_id]
        return MemoryResponse(success=True, memory_id=memory_id)

    def update_memory(self, memory_note):
        self.rows[memory_note.id].content = memory_note.content
        return MemoryResponse(success=True, memory_id=memory_note.id)

    def get_memory(self, memory_id):
        note = self.rows.get(memory_id)
        if note is None:
            return MemoryResponse(success=False, error="Memory not found")
        return MemoryResponse(
            success=True, content=note.content, metadata=note.metadata
        )

    def retrieve_memory(self, query):
        return MemoryResponse(success=True, search_results=[
            {
                "memory_id": note.id,
                "content": note.content,
                "timestamp": "t",
                "score": None,
                "metadata": note.metadata,
            }
            for note in self.rows.values()
        ])

    def retrieve_memory_raw(self, query):
        return []


def make_manager():
    """Build a real manager over a ``StoreProvider``."""
    manager = MemoryManager.__new__(MemoryManager)
    manager.provider = StoreProvider()
    manager.barrier = MemoryWriteBarrier(config={})
    manager._known_user_ids = OrderedDict()
    manager.relevance_threshold = 0.3
    return manager


def make_extractor(manager):
    """Build an enabled extractor over ``manager``."""
    return ConversationExtractor(manager, {"auto_extract": True})


def extract(extractor):
    """Run one conversation extraction."""
    extractor.extract_async(AGENT, "hi", "hello", user_id=USER)


def wait_for_write(manager):
    """Wait until the background write has finished and released."""
    assert manager.provider.written.wait(WAIT_SECONDS)
    outcome = manager.barrier.wait_until_drained(
        USER, manager.barrier.snapshot(USER)
    )
    assert outcome.name in ("DRAINED", "BYPASSED")


def test_extractor_makes_no_provider_calls():
    manager = MagicMock()
    done = threading.Event()

    def respond(_syscall):
        done.set()
        return MemoryResponse(success=True, memory_id="m")

    manager.address_request.side_effect = respond
    extract(make_extractor(manager))
    assert done.wait(WAIT_SECONDS)
    assert manager.provider.mock_calls == []
    syscall = manager.address_request.call_args.args[0]
    assert syscall.query.operation_type == "add_memory"
    assert syscall.query.params["metadata"] == {
        "user_id": USER,
        "owner_agent": AGENT,
        "memory_type": "conversation",
        "sharing_policy": "private",
    }


def test_stamped_before_extract_async_returns_then_released():
    manager = make_manager()
    manager.provider.write_gate.clear()
    with patch.object(
        manager.barrier, "acquire", wraps=manager.barrier.acquire
    ) as acquire, patch.object(
        manager.barrier, "release", wraps=manager.barrier.release
    ) as release:
        extract(make_extractor(manager))
        acquire.assert_called_once_with(USER)
        release.assert_not_called()
        manager.provider.write_gate.set()
        wait_for_write(manager)
    assert release.call_args.args[0] == USER
    assert release.call_args.kwargs["success"] is True
    assert manager.barrier.stats()["total_pending"] == 0


def test_released_when_the_provider_fails():
    manager = make_manager()
    manager.provider.fail_writes = True
    with patch.object(
        manager.barrier, "release", wraps=manager.barrier.release
    ) as release:
        extract(make_extractor(manager))
        wait_for_write(manager)
    assert release.call_args_list[0].kwargs["success"] is False
    assert manager.barrier.stats()["total_pending"] == 0


def test_released_when_the_thread_cannot_start():
    manager = make_manager()
    with patch(
        "aios.memory.conversation_extractor.threading.Thread",
        side_effect=RuntimeError("no threads"),
    ):
        extract(make_extractor(manager))
    assert manager.barrier.stats()["total_pending"] == 0


def test_write_registers_the_user():
    manager = make_manager()
    extract(make_extractor(manager))
    wait_for_write(manager)
    assert USER in manager.known_user_ids


def test_retrieval_right_after_extraction_observes_the_write():
    """The write has not started when the retrieval is accepted, as
    when the chat response beats the background thread."""
    manager = make_manager()
    started = []
    real_thread = threading.Thread

    class DeferredThread:
        def __init__(self, target, args, daemon):
            def run():
                time.sleep(0.2)
                target(*args)

            self.thread = real_thread(target=run, daemon=daemon)

        def start(self):
            started.append(True)
            self.thread.start()

    with patch(
        "aios.memory.conversation_extractor.threading.Thread",
        DeferredThread,
    ):
        extract(make_extractor(manager))
    assert started
    assert manager.provider.rows == {}

    syscall = MemorySyscall(AGENT, MemoryQuery(
        operation_type="retrieve_memory",
        params={"content": "q", "k": 5, "user_id": USER},
    ))
    manager.stamp_syscall(syscall)
    response = manager.address_request(syscall)
    assert len(response.search_results) == 1
    assert response.search_results[0]["metadata"]["memory_type"] == (
        "conversation"
    )


def inject_for(manager, agent):
    """Run one injection and return its diagnostics and messages."""
    injector = ContextInjector(manager, {
        "auto_inject": True,
        "max_injected_memories": 5,
        "max_memory_tokens": 8000,
    })
    query = LLMQuery(
        messages=[{"role": "user", "content": "next"}],
        action_type="chat",
    )
    return injector.inject(agent, query, user_id=USER)


def test_conversation_is_never_injected_into_another_agent():
    manager = make_manager()
    extract(make_extractor(manager))
    wait_for_write(manager)
    query, diagnostics = inject_for(manager, "profile_agent")
    assert diagnostics["own_fetched"] == 1
    assert diagnostics["after_visibility"] == 0
    assert diagnostics["injected_count"] == 0
    assert "hello" not in str(query.messages)


def test_conversation_is_injected_into_its_owner():
    manager = make_manager()
    extract(make_extractor(manager))
    wait_for_write(manager)
    query, diagnostics = inject_for(manager, AGENT)
    assert diagnostics["injected_count"] == 1
    assert "hello" in str(query.messages)


def stored(manager, owner, policy):
    """Store one memory through the manager and return its id."""
    query = MemoryQuery(operation_type="add_memory", params={
        "content": "v1",
        "metadata": {
            "user_id": USER,
            "owner_agent": owner,
            "sharing_policy": policy,
            "memory_type": "profile",
        },
    })
    return manager.address_request(
        MemorySyscall(owner, query)
    ).memory_id


def by_id(manager, agent, operation, memory_id, **params):
    """Run one by-id operation as the SDK sends it."""
    query = MemoryQuery(operation_type=operation, params={
        "memory_id": memory_id, "user_id": USER, **params,
    })
    return manager.address_request(MemorySyscall(agent, query))


def assert_refused(manager, memory_id):
    for operation, params in (
        ("update_memory", {"content": "v2"}),
        ("remove_memory", {}),
    ):
        response = by_id(
            manager, "agent_b", operation, memory_id, **params
        )
        assert not response.success
        assert response.error == "Memory not found"
    assert manager.provider.rows[memory_id].content == "v1"


def test_other_agent_cannot_change_a_private_memory():
    manager = make_manager()
    assert_refused(manager, stored(manager, "agent_a", "private"))


def test_other_agent_cannot_change_a_shared_memory():
    manager = make_manager()
    assert_refused(manager, stored(manager, "agent_a", "shared"))


def test_shared_memory_stays_readable_by_others():
    manager = make_manager()
    memory_id = stored(manager, "agent_a", "shared")
    assert by_id(
        manager, "agent_b", "get_memory", memory_id
    ).content == "v1"


def test_owner_can_update_and_delete():
    for policy in ("private", "shared"):
        manager = make_manager()
        memory_id = stored(manager, "agent_a", policy)
        assert by_id(
            manager, "agent_a", "update_memory", memory_id, content="v2"
        ).success
        assert manager.provider.rows[memory_id].content == "v2"
        assert by_id(
            manager, "agent_a", "remove_memory", memory_id
        ).success
        assert memory_id not in manager.provider.rows


def test_missing_memory_gets_the_same_refusal():
    manager = make_manager()
    response = by_id(manager, "agent_a", "remove_memory", "nope")
    assert response.error == "Memory not found"


def test_lookup_without_user_id_tries_agent_scope_then_default():
    manager = make_manager()
    manager.provider = MagicMock()
    manager.provider.get.side_effect = [
        None, Candidate("m", "c", {"owner_agent": AGENT}),
    ]
    query = MemoryQuery(
        operation_type="get_memory", params={"memory_id": "m"}
    )
    response = manager.address_request(MemorySyscall(AGENT, query))
    assert response.content == "c"
    scopes = [
        call.args[1]
        for call in manager.provider.get.call_args_list
    ]
    assert scopes == [AGENT, None]


def test_update_routes_to_the_collection_the_memory_was_found_in():
    manager = make_manager()
    manager.provider = MagicMock()
    manager.provider.get.return_value = Candidate(
        "m", "c", {"owner_agent": AGENT, "user_id": USER}
    )
    query = MemoryQuery(
        operation_type="update_memory",
        params={"memory_id": "m", "content": "new"},
    )
    manager.address_request(MemorySyscall(AGENT, query))
    memory_id, user_id, content, _ = manager.provider.update.call_args.args
    assert (memory_id, user_id, content) == ("m", USER, "new")
