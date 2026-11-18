"""Memory requests are accepted on the kernel's event loop and served
off it (NeurIPS Subtask 18, docs/STRESS_DIMENSIONS.md, "Concurrency").

Until Subtask 18 the ``/query`` handler served a memory request inline,
so the event loop accepted nothing else until it completed: concurrent
writers were serialized at the HTTP layer, and a probe sent while a
write was in flight was not even read until the write had finished. Now
a request is stamped and queued on the loop, in arrival order, and
awaited off it; and a chat request's barrier snapshot is taken when it
arrives, so it waits for the writes accepted before it and for none
accepted after."""
import asyncio
import threading
import time
from unittest.mock import patch

from cerebrum.llm.apis import LLMQuery
from cerebrum.memory.apis import MemoryQuery

from aios.memory.context_injector import ContextInjector
from aios.memory.manager import MemoryManager
from aios.memory.providers.in_house import InHouseProvider
from aios.scheduler.fifo_scheduler import FIFOScheduler
from aios.syscall.memory import MemorySyscall
from aios.syscall.syscall import SyscallExecutor
from tests.modules.syscall.test_v2_requests import launch_handler

USER = "alice"
WRITER = "travel_agent"
QUEUE = "aios.syscall.syscall.global_memory_req_queue_add_message"
CONFIG = {
    "provider": "in-memory",
    "relevance_threshold": 0.0,
    "max_injected_memories": 10,
    "max_memory_tokens": 2000,
    "write_barrier": {"enabled": True, "timeout_ms": 5000},
    "auto_inject": True,
}


class AsyncCommit(InHouseProvider):
    """The in-memory provider, as a store whose writes a read must wait
    for (Chroma, Mem0)."""

    synchronous_commit = False


def kernel():
    with patch("aios.memory.manager.global_config") as config:
        config.get_memory_config.return_value = CONFIG
        config.get_storage_config.return_value = {}
        manager = MemoryManager()
    manager.provider = AsyncCommit()
    return manager


def write_body(content):
    return {
        "agent_name": WRITER, "query_type": "memory",
        "query_data": MemoryQuery(operation_type="add_memory", params={
            "content": content,
            "metadata": {"owner_agent": WRITER, "user_id": USER,
                         "memory_type": "calendar",
                         "sharing_policy": "shared"},
        }).model_dump(),
    }


def test_two_memory_requests_are_accepted_while_both_are_in_flight():
    """The memory thread is held: both requests are stamped and queued
    before either is served. Served inline, the second could not be
    accepted until the first was answered."""
    manager = kernel()
    scheduler = FIFOScheduler(
        llm=None, memory_manager=manager, storage_manager=None,
        tool_manager=None, log_mode="console", get_llm_syscall=None,
        get_memory_syscall=None, get_storage_syscall=None,
        get_tool_syscall=None,
    )
    queued, served_at, events = [], [], []
    lock = threading.Lock()
    gate = threading.Event()
    stop = threading.Event()

    def enqueue(syscall):
        with lock:
            queued.append(syscall)
            events.append(("queued", time.monotonic()))

    def memory_thread():
        while not stop.is_set():
            gate.wait(2)  # held until the test opens it (or 2 s)
            with lock:
                batch, queued[:] = list(queued), []
            for syscall in batch:
                events.append(("served", time.monotonic()))
                scheduler._execute_syscall(syscall, manager.address_request,
                                           "Memory")
            time.sleep(0.01)

    worker = threading.Thread(target=memory_thread, daemon=True)
    with patch(QUEUE, enqueue):
        worker.start()
        executor = SyscallExecutor()
        executor.memory_manager = manager
        QueryRequest, handle_query = launch_handler(
            executor.execute_request, manager=manager,
            accept_memory_request=executor.accept_memory,
        )

        async def both():
            tasks = [asyncio.create_task(handle_query(QueryRequest(
                **write_body(text)))) for text in ("One.", "Two.")]
            for _ in range(100):
                await asyncio.sleep(0.01)
                if sum(1 for kind, _ in events if kind == "queued") == 2:
                    break
            gate.set()
            return await asyncio.wait_for(asyncio.gather(*tasks), 10)

        try:
            results = asyncio.run(both())
        finally:
            stop.set()
            gate.set()
            worker.join(5)
    assert [kind for kind, _ in events[:2]] == ["queued", "queued"]
    assert all(r["response"].success for r in results)
    assert sorted(r.content for r in manager.provider.list(USER, 10)) == [
        "One.", "Two.",
    ]


def test_a_request_is_stamped_before_a_chat_that_arrives_after_it():
    """A write or a forget that reaches the handler before a chat is
    stamped before the chat's arrival snapshot, so the chat waits for
    it: acceptance runs on the event loop, in arrival order. Accepted
    off the loop, the write was stamped after the chat in 199 of 200
    pairs (Subtask 18's mutation run), an ``uncovered_write`` in the
    stress measures, which the kernel's concurrency cells report as 0."""
    manager = kernel()
    scheduler = FIFOScheduler(
        llm=None, memory_manager=manager, storage_manager=None,
        tool_manager=None, log_mode="console", get_llm_syscall=None,
        get_memory_syscall=None, get_storage_syscall=None,
        get_tool_syscall=None,
    )
    executor = SyscallExecutor()
    executor.memory_manager = manager
    snapshots = []

    def serve(syscall):  # the memory thread's step, on the caller's
        scheduler._execute_syscall(syscall, manager.address_request,
                                   "Memory")

    def execute_request(agent_name, query):
        if isinstance(query, LLMQuery):  # the chat: its snapshot
            snapshots.append(query._barrier_snapshot)
            return {"response": "ok"}
        return executor.execute_request(agent_name, query)

    forget = {
        "agent_name": "assistant_agent", "query_type": "memory",
        "query_data": MemoryQuery(operation_type="forget_memory", params={
            "user_id": USER, "fact_key": "trip",
        }).model_dump(),
    }
    chat_body = {
        "agent_name": "assistant_agent", "query_type": "llm",
        "query_data": LLMQuery(
            messages=[{"role": "user", "content": "which trip?"}],
            action_type="chat",
        ).model_dump() | {"user_id": USER},
    }
    with patch(QUEUE, serve):
        QueryRequest, handle_query = launch_handler(
            execute_request, manager=manager,
            accept_memory_request=executor.accept_memory,
        )

        async def pair(body):
            first = asyncio.create_task(handle_query(QueryRequest(**body)))
            then = asyncio.create_task(handle_query(QueryRequest(
                **chat_body)))
            reply, _ = await asyncio.gather(first, then)
            assert reply["response"].success
            return reply["response"].metadata["barrier_seq"], snapshots[-1]

        async def pairs():
            stamps = []
            for i in range(20):
                stamps.append(await pair(write_body(f"Trip {i}.")))
                stamps.append(await pair(forget))
            return stamps

        stamps = asyncio.run(pairs())
    assert all(seq and snapshot for seq, snapshot in stamps)
    assert [seq for seq, snapshot in stamps if seq > snapshot] == []


def chat(injector, snapshot):
    query = LLMQuery(messages=[{"role": "user", "content": "which trip?"}],
                     action_type="chat")
    return injector.inject("assistant_agent", query, user_id=USER,
                           barrier_snapshot=snapshot)


def stamped_write(manager, content):
    syscall = MemorySyscall(WRITER, MemoryQuery(
        operation_type="add_memory", params={
            "content": content,
            "metadata": {"owner_agent": WRITER, "user_id": USER,
                         "memory_type": "calendar",
                         "sharing_policy": "shared"},
        }))
    manager.stamp_syscall(syscall)
    return syscall


def test_a_chat_waits_for_the_writes_accepted_before_it_only():
    """A write accepted before the chat arrived is waited for and in the
    block; one accepted after it arrived delays nothing."""
    manager = kernel()
    injector = ContextInjector(manager, CONFIG)
    before = stamped_write(manager, "Trip to Porto in May.")
    snapshot = manager.arrival_snapshot(USER)  # the chat arrives
    assert snapshot == before.barrier_seq
    after = stamped_write(manager, "Trip to Riga in June.")

    done = {}

    def run_chat():
        done["result"] = chat(injector, snapshot)
        done["at"] = time.monotonic()

    reader = threading.Thread(target=run_chat)
    reader.start()
    time.sleep(0.3)
    assert "result" not in done, "the chat did not wait for the write"
    served_at = time.monotonic()
    assert manager.address_request(before).success
    reader.join(5)
    assert done["at"] >= served_at
    _, diagnostics = done["result"]
    assert "Porto" in diagnostics["block_text"]
    assert diagnostics["barrier_snapshot"] == snapshot
    assert diagnostics["barrier_waits"] == [
        {"user_id": USER, "outcome": "DRAINED"},
    ]
    assert after.barrier_seq > snapshot  # never waited for
    assert manager.address_request(after).success


def test_no_snapshot_without_a_user_or_with_a_synchronous_store():
    manager = kernel()
    assert manager.arrival_snapshot(None) is None
    manager.provider = InHouseProvider()
    assert manager.arrival_snapshot(USER) is None
