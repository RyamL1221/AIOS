"""Owner-only listing and deletion (benchmark v2, docs/BENCHMARK_V2.md,
"Revoke and deletion").

A writer revokes a fact by listing its own rows for the user and
deleting every row whose ``metadata.fact_key`` is the revoked slot.
``MemoryPipeline.list_own`` and ``MemoryPipeline.delete`` do both, for
the kernel (``list_memory`` and ``remove_memory``) and the replicated
agents alike. Every failure in those kernel branches is a response:
an exception would leave the FIFO scheduler's syscall unanswered. A
listing waits on the write barrier like a retrieval (Amendment 2).
"""
import threading
import uuid
from unittest.mock import MagicMock, patch

import pytest

from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from aios.memory.conversation_extractor import ConversationExtractor
from aios.memory.manager import MemoryManager
from aios.memory.note import MemoryNote
from aios.memory.pipeline import (
    LIST_TOP_K,
    IdentityResolver,
    IdentityRules,
    MemoryPipeline,
    note_from_request,
)
from aios.memory.providers.base import Candidate, ProviderError
from aios.memory.providers.in_house import InHouseProvider
from aios.syscall.memory import MemorySyscall
from tests.modules.memory._doubles.fake_mem0 import (
    FakeMem0Client,
    provider_with,
)

USER = "alice"
WRITER = "profile_agent"


def store() -> InHouseProvider:
    provider = InHouseProvider()
    provider.initialize({})
    return provider


def write(pipeline, agent, content, user=USER, policy="shared",
          memory_type="profile", **metadata):
    """One write through the library, as a v2 writer makes it."""
    return pipeline.write(agent, user, note_from_request({
        "content": content,
        "metadata": {
            "owner_agent": agent, "user_id": user,
            "memory_type": memory_type, "sharing_policy": policy,
            **metadata,
        },
    }))


def ids(rows):
    return [r["memory_id"] for r in rows]


# --- MemoryPipeline.list_own ------------------------------------------


def test_list_own_returns_the_agents_rows_for_the_user_only():
    pipeline = MemoryPipeline(store())
    pet = write(pipeline, WRITER, "My cat is Mochi.", fact_key="pet")
    secret = write(pipeline, WRITER, "Just between us: an interview.",
                   policy="private", fact_key="interview")
    task = write(pipeline, "task_agent", "Client is Halvorsen.",
                 memory_type="task_context", fact_key="client")
    write(pipeline, "assistant_agent", "User: hi\nAssistant: hello",
          policy="private", memory_type="conversation")
    write(pipeline, WRITER, "Bob lives in Oslo.", user="bob")

    rows = pipeline.list_own(WRITER, USER)
    assert ids(rows) == [pet, secret]  # storage order, private included
    assert all(r["score"] is None for r in rows)
    assert [r["metadata"]["fact_key"] for r in rows] == ["pet", "interview"]
    assert rows[0]["content"] == "My cat is Mochi."
    assert set(rows[0]) == {
        "memory_id", "content", "metadata", "score", "keywords", "tags",
        "category", "timestamp",
    }
    assert ids(pipeline.list_own("task_agent", USER)) == [task]
    assert pipeline.list_own("calendar_agent", USER) == []


def test_list_own_reaches_every_row_and_caps_the_agents_own():
    pipeline = MemoryPipeline(store())
    for i in range(30):
        write(pipeline, "task_agent", f"task filler {i}")
    mine = [write(pipeline, WRITER, f"profile filler {i}") for i in range(30)]
    assert ids(pipeline.list_own(WRITER, USER)) == mine
    # The cap applies to the agent's own rows, though other agents'
    # rows come first in storage order.
    assert ids(pipeline.list_own(WRITER, USER, top_k=5)) == mine[:5]
    assert pipeline.list_own(WRITER, USER, top_k=0) == []


def test_list_own_asks_the_provider_for_the_whole_scope():
    provider = MagicMock()
    provider.list.return_value = [
        Candidate("a", "kept", {"owner_agent": WRITER, "user_id": USER}),
        Candidate("b", "mis-scoped", {"owner_agent": WRITER,
                                      "user_id": "bob"}),
        Candidate("c", "no user", {"owner_agent": WRITER}),
        Candidate("d", "no owner", {"user_id": USER}),
    ]
    pipeline = MemoryPipeline(provider, barrier=None)
    assert ids(pipeline.list_own(WRITER, USER, top_k=3)) == ["a"]
    provider.list.assert_called_once_with(USER, LIST_TOP_K)
    assert LIST_TOP_K >= 10_000


def test_list_own_without_a_user_lists_the_agents_own_scope():
    pipeline = MemoryPipeline(store())
    memory_id = write(pipeline, WRITER, "no user named", user=None)
    assert ids(pipeline.list_own(WRITER, None)) == [memory_id]
    assert pipeline.list_own(WRITER, USER) == []


def test_list_own_and_delete_use_the_canonical_user():
    resolver = IdentityResolver(rules=IdentityRules(casefold=True))
    pipeline = MemoryPipeline(store(), resolver=resolver)
    memory_id = write(pipeline, WRITER, "My cat is Mochi.", user="Alice")
    assert ids(pipeline.list_own(WRITER, "ALICE")) == [memory_id]
    assert pipeline.delete(WRITER, "ALICE", memory_id)
    assert pipeline.list_own(WRITER, "alice") == []


# --- Mem0: one write, several facts -----------------------------------


class ExtractingMem0Client(FakeMem0Client):
    """Mem0 with extraction: a write becomes one fact per sentence, each
    stored with the write's whole metadata, as Mem0 copies it."""

    def add(self, content, user_id, metadata=None, infer=True, **kwargs):
        self.add_calls.append(
            {"user_id": user_id, "metadata": metadata, "infer": infer}
        )
        results = []
        for fact in (s.strip() for s in content.split(".")):
            if not fact:
                continue
            memory_id = str(uuid.uuid4())
            self.store[memory_id] = {
                **(metadata or {}), "data": fact, "user_id": user_id,
                "created_at": "mem0-time",
            }
            results.append({"id": memory_id, "event": "ADD"})
        return {"results": results}


def test_mem0_sibling_facts_are_listed_and_all_deleted():
    client = ExtractingMem0Client()
    provider = provider_with(client)
    provider.backend_extraction = True
    pipeline = MemoryPipeline(provider, barrier=None)
    first = write(pipeline, WRITER,
                  "I have a cat. Her name is Mochi. She is three.",
                  fact_key="pet")
    write(pipeline, WRITER, "I live in Tallinn.", fact_key="home_city")
    # Another writer's echo of the fact (owner-only: not the writer's).
    echo = write(pipeline, "calendar_agent", "Vet visit for Mochi.",
                 memory_type="calendar", fact_key="vet_visit")

    rows = pipeline.list_own(WRITER, USER)
    pets = [r for r in rows if r["metadata"]["fact_key"] == "pet"]
    # add returned one id; the listing finds all three facts.
    assert first in ids(pets) and len(pets) == 3
    assert len(rows) == 4

    # The revoke: delete every own row of the slot.
    assert all(pipeline.delete(WRITER, USER, r["memory_id"]) for r in pets)
    left = pipeline.list_own(WRITER, USER)
    assert [r["metadata"]["fact_key"] for r in left] == ["home_city"]
    # The echo is left behind, and its writer still lists it.
    assert ids(pipeline.list_own("calendar_agent", USER)) == [echo]
    assert not pipeline.delete(WRITER, USER, echo)


# --- MemoryPipeline.delete --------------------------------------------


def test_delete_is_owner_only():
    provider = store()
    pipeline = MemoryPipeline(provider)
    memory_id = write(pipeline, WRITER, "My cat is Mochi.")  # shared
    assert not pipeline.delete("task_agent", USER, memory_id)
    assert provider.get(memory_id, USER) is not None
    assert pipeline.delete(WRITER, USER, memory_id)
    assert provider.get(memory_id, USER) is None
    assert not pipeline.delete(WRITER, USER, memory_id)
    assert not pipeline.delete(WRITER, USER, "no-such-id")


def test_a_row_without_an_owner_cannot_be_deleted():
    provider = store()
    note = MemoryNote(content="orphan")
    note.metadata = {"user_id": USER, "sharing_policy": "shared"}
    memory_id = provider.add(note)
    pipeline = MemoryPipeline(provider)
    for agent in (WRITER, "task_agent", ""):
        assert not pipeline.delete(agent, USER, memory_id)
    assert pipeline.list_own(WRITER, USER) == []
    assert provider.get(memory_id, USER) is not None


def test_delete_goes_to_the_scope_the_row_was_found_in():
    provider = MagicMock()
    provider.get.return_value = Candidate(
        "m", "c", {"owner_agent": WRITER, "user_id": USER}
    )
    provider.delete.return_value = True
    pipeline = MemoryPipeline(provider, barrier=None)
    assert pipeline.delete(WRITER, USER, "m")
    provider.get.assert_called_once_with("m", USER)
    provider.delete.assert_called_once_with("m", USER)


def test_delete_raises_provider_errors():
    provider = MagicMock()
    provider.get.return_value = Candidate(
        "m", "c", {"owner_agent": WRITER, "user_id": USER}
    )
    provider.delete.side_effect = ProviderError("Mem0 delete failed")
    with pytest.raises(ProviderError):
        MemoryPipeline(provider, barrier=None).delete(WRITER, USER, "m")


# --- the kernel's list_memory and remove_memory -----------------------


def kernel(memory_config=None):
    """A real MemoryManager on the in-memory provider."""
    with patch("aios.memory.manager.global_config") as config:
        config.get_memory_config.return_value = {
            "provider": "in-memory", **(memory_config or {}),
        }
        config.get_storage_config.return_value = {}
        return MemoryManager()


def request(manager, agent, operation, **params):
    """One memory request as the SDK sends it, through acceptance."""
    syscall = MemorySyscall(agent, MemoryQuery(
        operation_type=operation, params=params,
    ))
    manager.stamp_syscall(syscall)
    return manager.address_request(syscall)


def kernel_write(manager, agent, content, user=USER, **metadata):
    response = request(manager, agent, "add_memory", content=content,
                       metadata={"owner_agent": agent, "user_id": user,
                                 "memory_type": "profile",
                                 "sharing_policy": "shared", **metadata})
    assert response.success
    return response.memory_id


def test_kernel_list_memory_is_the_librarys_list_own():
    manager = kernel()
    kernel_write(manager, WRITER, "My cat is Mochi.", fact_key="pet")
    kernel_write(manager, "task_agent", "Client is Halvorsen.")
    kernel_write(manager, WRITER, "I live in Tallinn.", fact_key="city")
    # The kernel lists through list_own_report: the rows of list_own and
    # the ids a tombstone withheld (none here).
    original = MemoryPipeline.list_own_report
    with patch.object(MemoryPipeline, "list_own_report", autospec=True,
                      side_effect=original) as list_own:
        response = request(manager, WRITER, "list_memory", user_id=USER)
    assert isinstance(response, MemoryResponse) and response.success
    assert response.metadata == {"withheld": []}
    _, agent, user = list_own.call_args.args
    # The snapshot stamped at acceptance, after the three writes.
    snapshot = manager.barrier.snapshot(USER)
    assert snapshot == 3
    assert (agent, user, list_own.call_args.kwargs) == (
        WRITER, USER, {"top_k": None, "barrier_snapshot": snapshot},
    )
    library = MemoryPipeline(manager.provider)
    assert response.search_results == library.list_own(WRITER, USER)
    assert [r["metadata"]["fact_key"] for r in response.search_results] \
        == ["pet", "city"]
    one = request(manager, WRITER, "list_memory", user_id=USER, k=1)
    assert len(one.search_results) == 1


def test_kernel_list_memory_canonicalizes_the_user():
    manager = kernel({"identity": {"casefold": True}})
    memory_id = kernel_write(manager, WRITER, "My cat is Mochi.",
                             user="Alice")
    response = request(manager, WRITER, "list_memory", user_id="ALICE")
    assert [r["memory_id"] for r in response.search_results] == [memory_id]


def test_kernel_remove_memory_goes_through_the_library():
    manager = kernel()
    memory_id = kernel_write(manager, WRITER, "My cat is Mochi.")
    original = MemoryPipeline.delete
    with patch.object(MemoryPipeline, "delete", autospec=True,
                      side_effect=original) as delete:
        refused = request(manager, "task_agent", "remove_memory",
                          memory_id=memory_id, user_id=USER)
        removed = request(manager, WRITER, "remove_memory",
                          memory_id=memory_id, user_id=USER)
    assert [c.args[1:] for c in delete.call_args_list] == [
        ("task_agent", USER, memory_id), (WRITER, USER, memory_id),
    ]
    assert (refused.success, refused.error) == (False, "Memory not found")
    assert (removed.success, removed.memory_id) == (True, memory_id)
    assert manager.provider.get(memory_id, USER) is None


def test_revoke_through_the_kernel_leaves_only_the_echo():
    """A writer's revoke as v2 makes it: list its own rows, delete every
    row of the slot, list again."""
    manager = kernel()
    for text in ("I have a cat.", "Her name is Mochi."):
        kernel_write(manager, WRITER, text, fact_key="pet")
    kernel_write(manager, WRITER, "I live in Tallinn.", fact_key="city")
    echo = kernel_write(manager, "calendar_agent", "Vet visit for Mochi.",
                        fact_key="vet_visit")
    listed = request(manager, WRITER, "list_memory", user_id=USER)
    revoked = [r["memory_id"] for r in listed.search_results
               if r["metadata"]["fact_key"] == "pet"]
    assert len(revoked) == 2
    for memory_id in revoked:
        assert request(manager, WRITER, "remove_memory",
                       memory_id=memory_id, user_id=USER).success
    after = request(manager, WRITER, "list_memory", user_id=USER)
    assert [r["metadata"]["fact_key"] for r in after.search_results] == [
        "city",
    ]
    others = request(manager, "calendar_agent", "list_memory", user_id=USER)
    assert [r["memory_id"] for r in others.search_results] == [echo]


@pytest.mark.parametrize("operation, broken, error", [
    ("list_memory", "list", RuntimeError("chroma down")),
    ("remove_memory", "get", RuntimeError("chroma down")),
    ("remove_memory", "delete", KeyError("m")),
])
def test_a_failing_provider_gives_a_failed_response(operation, broken,
                                                    error):
    manager = kernel()
    memory_id = kernel_write(manager, WRITER, "My cat is Mochi.")
    setattr(manager.provider, broken, MagicMock(side_effect=error))
    response = request(manager, WRITER, operation, memory_id=memory_id,
                       user_id=USER)
    assert isinstance(response, MemoryResponse)
    assert response.success is False
    assert type(error).__name__ in response.error


def test_a_provider_error_keeps_its_message():
    manager = kernel()
    memory_id = kernel_write(manager, WRITER, "My cat is Mochi.")
    manager.provider.delete = MagicMock(
        side_effect=ProviderError("Mem0 delete failed: boom")
    )
    response = request(manager, WRITER, "remove_memory",
                       memory_id=memory_id, user_id=USER)
    assert (response.success, response.error) == (
        False, "Mem0 delete failed: boom",
    )


def test_a_failing_list_still_answers_the_scheduler():
    """The FIFO scheduler sets a syscall's event only when the manager
    returns; an exception would leave the caller waiting forever."""
    from aios.scheduler.fifo_scheduler import FIFOScheduler

    manager = kernel()
    manager.provider.list = MagicMock(side_effect=RuntimeError("down"))
    scheduler = FIFOScheduler(
        llm=None, memory_manager=manager, storage_manager=None,
        tool_manager=None, log_mode="console", get_llm_syscall=None,
        get_memory_syscall=None, get_storage_syscall=None,
        get_tool_syscall=None,
    )
    syscall = MemorySyscall(WRITER, MemoryQuery(
        operation_type="list_memory", params={"user_id": USER},
    ))
    scheduler._execute_syscall(syscall, manager.address_request, "Memory")
    assert syscall.event.is_set()
    assert syscall.get_status() == "done"
    assert syscall.get_response().success is False


# --- listings wait for writes (BENCHMARK_V2.md, Amendment 2) ----------

WAIT = 5  # seconds: the barrier's default timeout
ASSISTANT = "assistant_agent"


class GatedStore(InHouseProvider):
    """The in-memory store, but ``add`` waits for ``gate``, like a
    commit still in flight. Not synchronous, so the barrier applies, as
    for Mem0 and the Chroma in-house store."""

    synchronous_commit = False

    def __init__(self):
        super().__init__()
        self.gate = threading.Event()
        self.gate.set()

    def add(self, memory_note):
        assert self.gate.wait(WAIT)
        return super().add(memory_note)


class Background:
    """Runs ``call(*args, **kwargs)`` on a daemon thread and keeps what
    it returned."""

    def __init__(self, call, *args, **kwargs):
        self.result = None
        self.thread = threading.Thread(
            target=self._run, args=(call, args, kwargs), daemon=True,
        )
        self.thread.start()

    def _run(self, call, args, kwargs):
        self.result = call(*args, **kwargs)

    def done(self, timeout: float) -> bool:
        """True once the call returned, waiting up to ``timeout``."""
        self.thread.join(timeout)
        return not self.thread.is_alive()


def test_list_memory_is_stamped_like_a_retrieval():
    manager = kernel({"identity": {"casefold": True}})
    pending = manager.barrier.acquire("alice")  # an accepted write
    listing = MemorySyscall(WRITER, MemoryQuery(
        operation_type="list_memory", params={"user_id": "ALICE"},
    ))
    manager.stamp_syscall(listing)
    # Canonical, so the wait keys on the user the write was stamped for.
    assert listing.query.params["user_id"] == "alice"
    assert listing.barrier_snapshot == pending
    # Without a user, nothing to wait for: the sentinel, as for search.
    unscoped = MemorySyscall(WRITER, MemoryQuery(
        operation_type="list_memory", params={},
    ))
    manager.stamp_syscall(unscoped)
    assert getattr(unscoped, "barrier_snapshot", 0) == 0
    manager.barrier.release("alice", pending, success=True)


def test_list_own_waits_for_a_write_accepted_before_it():
    provider = GatedStore()
    pipeline = MemoryPipeline(provider)
    note = note_from_request({"content": "My lawyer is Greta Sandvik.",
                              "metadata": {"owner_agent": WRITER,
                                           "user_id": USER}})
    # Accepted (stamped) before the listing; its commit in flight.
    seq = pipeline.barrier.acquire(USER)
    provider.gate.clear()
    writer = Background(pipeline.write, WRITER, USER, note,
                        barrier_seq=seq)
    listing = Background(pipeline.list_own, WRITER, USER)
    # Another user's listing, and one told to skip the wait, return at
    # once.
    elsewhere = Background(pipeline.list_own, WRITER, "bob")
    skipped = Background(pipeline.list_own, WRITER, USER,
                         barrier_snapshot=0)
    assert elsewhere.done(1) and elsewhere.result == []
    assert skipped.done(1) and skipped.result == []
    assert not listing.done(0.3)
    provider.gate.set()
    assert writer.done(WAIT) and listing.done(WAIT)
    assert ids(listing.result) == [writer.result]


def test_kernel_listing_right_after_a_chat_turn_includes_the_turn():
    """The harness lists every agent right after the last probe, while
    the kernel still writes that probe's conversation turn in the
    background: the listing used to miss it, and with it a revoked
    value the answer quoted."""
    manager = kernel()
    provider = manager.provider = GatedStore()
    bobs = kernel_write(manager, ASSISTANT, "User: hi\nAssistant: hello",
                        user="bob")
    provider.gate.clear()
    ConversationExtractor(manager, {"auto_extract": True}).extract_async(
        ASSISTANT, "Who is my lawyer?", "Greta Sandvik.", user_id=USER,
    )
    listing = Background(request, manager, ASSISTANT, "list_memory",
                         user_id=USER)
    elsewhere = Background(request, manager, ASSISTANT, "list_memory",
                           user_id="bob")
    assert elsewhere.done(1)
    assert ids(elsewhere.result.search_results) == [bobs]
    assert not listing.done(0.3)  # waiting on the turn
    provider.gate.set()
    assert listing.done(WAIT) and listing.result.success
    assert [r["content"] for r in listing.result.search_results] == [
        "User: Who is my lawyer?\nAssistant: Greta Sandvik.",
    ]
    assert manager.barrier.stats()["total_pending"] == 0
