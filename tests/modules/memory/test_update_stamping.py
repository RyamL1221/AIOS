"""An update is stamped against the write barrier like a write: a
retrieval issued right after it waits for it and reads the new content.
"""
import threading
import time

from cerebrum.memory.apis import MemoryQuery

from aios.memory.manager import MemoryManager
from aios.memory.note import MemoryNote
from aios.memory.providers.base import MemoryProvider
from aios.memory.providers.in_house import InHouseProvider
from aios.memory.write_barrier import MemoryWriteBarrier, WaitOutcome
from aios.syscall.memory import MemorySyscall

AGENT = "profile_agent"
USER = "stamp_user"


class GatedProvider(MemoryProvider):
    """The in-memory provider, but ``update`` waits for ``gate``, like a
    slow commit. Not an InHouseProvider, so the barrier applies."""

    def __init__(self):
        self.inner = InHouseProvider()
        self.gate = threading.Event()

    def initialize(self, config):
        pass

    def capabilities(self):
        return self.inner.capabilities()

    def add(self, memory_note):
        return self.inner.add(memory_note)

    def search(self, query_text, user_id, top_k):
        return self.inner.search(query_text, user_id, top_k)

    def list(self, user_id, top_k):
        return self.inner.list(user_id, top_k)

    def get(self, memory_id, user_id):
        return self.inner.get(memory_id, user_id)

    def update(self, memory_id, user_id, content, metadata):
        assert self.gate.wait(5)
        return self.inner.update(memory_id, user_id, content, metadata)

    def delete(self, memory_id, user_id):
        return self.inner.delete(memory_id, user_id)


def make_manager():
    manager = MemoryManager.__new__(MemoryManager)
    manager.provider = GatedProvider()
    manager.barrier = MemoryWriteBarrier(config={"timeout_ms": 5000})
    manager.relevance_threshold = 0.0
    return manager


def store(manager, content):
    memory = MemoryNote(content=content)
    memory.metadata = {
        "owner_agent": AGENT, "user_id": USER, "memory_type": "profile",
        "sharing_policy": "private", "created_at": "t",
    }
    return manager.provider.add(memory)


def update_syscall(memory_id, content):
    return MemorySyscall(AGENT, MemoryQuery(
        operation_type="update_memory",
        params={"memory_id": memory_id, "content": content,
                "user_id": USER},
    ))


def test_retrieval_after_an_update_reads_the_new_content():
    manager = make_manager()
    memory_id = store(manager, "old value")
    syscall = update_syscall(memory_id, "new value")
    manager.stamp_syscall(syscall)
    assert syscall.barrier_seq

    writer = threading.Thread(target=manager.address_request, args=(syscall,))
    writer.start()
    threading.Timer(0.3, manager.provider.gate.set).start()

    started = time.monotonic()
    rows, diagnostics = manager.retrieve_for_agent(
        AGENT, USER, "value", k=5, include_shared=False,
        request_user_id=USER,
    )
    writer.join(5)
    assert [r["content"] for r in rows] == ["new value"]
    assert time.monotonic() - started >= 0.25
    assert diagnostics["barrier_waits"] == [
        {"user_id": USER, "outcome": WaitOutcome.DRAINED.name}
    ]


def test_a_refused_update_still_releases_the_barrier():
    manager = make_manager()
    syscall = update_syscall("no-such-id", "x")
    manager.stamp_syscall(syscall)
    response = manager.address_request(syscall)
    assert not response.success
    stats = manager.barrier.stats()
    assert stats["last_acquired_seq"] == syscall.barrier_seq
    assert stats["total_pending"] == 0
