"""Forgetting through the kernel (NeurIPS Subtask 15, step 1;
docs/DELETION_AND_SUPERSESSION.md, "Kernel and SDK").

A ``forget_memory`` request is the user's: any agent serving the user
may make it, and ``MemoryPipeline.forget`` deletes every row of the
slot and every carrier of its values, across owners. These tests pin
the kernel's side:
- the executor and the /query handler serve it, and the report comes
  back in ``metadata`` without another agent's private text;
- it is stamped against the write barrier when it is accepted, so a
  retrieval accepted after it waits for it;
- after it, injection, SDK search, ``get_memory`` and ``list_memory``
  leave out a carrier that escaped it, each with a WARNING;
- every memory branch answers a failure instead of raising;
- a write's reply says what it swept, retired and lifted;
- ``/memory/config`` reports supersession, the tombstones file and
  Mem0's history file;
- the settings, ``set_memory_mode.py --supersession`` and the SDK's
  ``forget_memories`` reach the kernel.
"""
import ast
import asyncio
import json
import logging
import sqlite3
import threading
import typing
from contextlib import closing, contextmanager
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from cerebrum.llm.apis import LLMQuery
from cerebrum.memory import apis as sdk
from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from aios.memory.context_injector import ContextInjector
from aios.memory.embedding import EmbeddingConfig
from aios.memory.manager import MemoryManager
from aios.memory.note import MemoryNote
from aios.memory.pipeline import (
    PIPELINE_VERSION,
    PipelineSettings,
    TombstoneStore,
)
from aios.memory.providers.in_house import InHouseProvider
from aios.scheduler.fifo_scheduler import FIFOScheduler
from aios.syscall.memory import MemorySyscall
from aios.syscall.syscall import SyscallExecutor
from scripts.set_memory_mode import main as set_memory_mode
from scripts.set_memory_mode import set_mode, set_supersession
from tests.modules.memory.test_list_and_delete import (
    WAIT,
    Background,
    GatedStore,
    ids,
    kernel,
    kernel_write,
    request,
)
from tests.modules.memory.test_provider_contract import needs_ollama
from tests.modules.memory.test_set_memory_mode import (
    EXAMPLE,
    MODE_KEYS,
    changed_lines,
)
from tests.modules.syscall.test_v2_requests import LAUNCH, launch_handler

USER = "alice"
WRITER = "profile_agent"
TASK = "task_agent"
CALENDAR = "calendar_agent"
ASSISTANT = "assistant_agent"

# The fact a forget asks for, and the user's rows (``seed``).
SLOT = "lawyer"
VALUE = "Greta Sandvik"
ALIAS = "Sandvik"
STATEMENT = "My lawyer is Greta Sandvik."
ECHO = "Call with Sandvik on Friday."
PRIVATE = "Private: Greta Sandvik billed 40 hours on the Halvorsen file."
CITY = "I live in Tallinn."
# A carrier planted after a forget, as one that escaped it.
CARRIER = "Lunch with Sandvik at noon."

SELECTOR = "aios.memory.pipeline.selector"
FACADE = "aios.memory.pipeline.facade"
QUEUE = "aios.syscall.syscall.global_memory_req_queue_add_message"
OUTCOME_KEYS = {"swept", "retired", "lifted", "suppressed"}
EMBEDDING = EmbeddingConfig.from_memory_config({})

# Each read path is run after a kernel forget and, as the control, on
# the same kernel without it.
FORGOTTEN = pytest.mark.parametrize(
    "forget", [True, False], ids=["forgotten", "control"],
)


def statement(fact_key, value, aliases=(), event="u0-e1", session=1,
              event_type="add"):
    """The metadata of one benchmark v2 statement, as the v2 writers
    build it (``v2_write_metadata``): the slot, the value as
    ``structured``, the aliases as ``value_aliases`` and the event."""
    return {
        "fact_key": fact_key,
        "event_type": event_type,
        "session": session,
        "structured": json.dumps({
            "event_type": event_type, "fact_key": fact_key,
            "value": value,
        }, sort_keys=True),
        "value_aliases": json.dumps(list(aliases)),
        "provenance_event": event,
    }


def seed(manager):
    """Write the user's rows through the kernel and return their ids:
    the lawyer statement (the profile writer's, shared), an echo that
    names only the alias (the calendar writer's), another agent's
    private row that carries the value, a row of another fact, and
    another user's statement of the same fact."""
    return {
        "statement": kernel_write(
            manager, WRITER, STATEMENT, **statement(SLOT, VALUE, [ALIAS]),
        ),
        "echo": kernel_write(
            manager, CALENDAR, ECHO, memory_type="calendar",
            fact_key="call", provenance_event="u0-e2",
        ),
        "private": kernel_write(
            manager, TASK, PRIVATE, memory_type="task_context",
            sharing_policy="private", fact_key="billing",
            provenance_event="u0-e3",
        ),
        "city": kernel_write(
            manager, WRITER, CITY,
            **statement("home_city", "Tallinn", event="u0-e4"),
        ),
        "bob": kernel_write(
            manager, WRITER, STATEMENT, user="bob",
            **statement(SLOT, VALUE, [ALIAS], event="u1-e1"),
        ),
    }


def expected_report(seeded, scrubbed):
    """The report of the assistant's forget of the lawyer over
    ``seed``'s rows: ids, owners and reasons, and the one value the
    assistant may read (the statement is shared)."""
    return {
        "user_id": USER, "fact_key": SLOT, "requested_by": ASSISTANT,
        "listed": 4, "values_count": 1, "forms_count": 2,
        "values": [VALUE],
        "deleted": [
            {"memory_id": seeded["statement"], "owner_agent": WRITER,
             "reason": "fact_key"},
            {"memory_id": seeded["echo"], "owner_agent": CALENDAR,
             "reason": "alias"},
            {"memory_id": seeded["private"], "owner_agent": TASK,
             "reason": "value"},
        ],
        "not_found": [],
        "scrubbed": scrubbed,
    }


def forget_query(user_id=USER, fact_key=SLOT):
    return MemoryQuery(
        operation_type="forget_memory",
        params={"user_id": user_id, "fact_key": fact_key},
    )


def forget_through(manager):
    """The assistant's forget of the lawyer, through acceptance."""
    return request(manager, ASSISTANT, "forget_memory", user_id=USER,
                   fact_key=SLOT)


def plant(manager, content=CARRIER):
    """A shared calendar row of the user, added to the store directly,
    past the kernel's write path, as a carrier that escaped a forget
    would be; its id."""
    note = MemoryNote(content=content)
    note.metadata = {
        "owner_agent": CALENDAR, "user_id": USER,
        "memory_type": "calendar", "sharing_policy": "shared",
        "created_at": "2026-11-10T12:00:00+00:00",
    }
    return manager.provider.add(note)


def stored(manager, user=USER):
    """The contents of the user's stored rows, in storage order."""
    return [row.content for row in manager.provider.list(user, 100)]


def warned(caplog, logger, memory_id):
    """The WARNINGs ``logger`` logged that name ``memory_id``."""
    return [
        record for record in caplog.records
        if record.name == logger and record.levelno == logging.WARNING
        and memory_id in record.getMessage()
    ]


class ScrubbingStore(InHouseProvider):
    """The in-memory store with a history to scrub, as Mem0 has one: its
    ``scrub_history`` records each call and reports ``COUNTS``."""

    COUNTS = {"messages": 2, "history": 5}

    def __init__(self):
        super().__init__()
        self.scrubs = []

    def scrub_history(self, user_id, forms, deleted_ids=(), kept_ids=()):
        self.scrubs.append((user_id, list(forms)))
        return dict(self.COUNTS)


@contextmanager
def kernel_executor(manager):
    """A ``SyscallExecutor`` wired to ``manager`` as runtime/launch.py
    wires it. Its memory queue hands each syscall, once stamped, to the
    FIFO scheduler's own step on the caller's thread, so a request is
    accepted, served and answered as in the kernel, without a scheduler
    thread."""
    scheduler = FIFOScheduler(
        llm=None, memory_manager=manager, storage_manager=None,
        tool_manager=None, log_mode="console", get_llm_syscall=None,
        get_memory_syscall=None, get_storage_syscall=None,
        get_tool_syscall=None,
    )
    executor = SyscallExecutor()
    executor.memory_manager = manager

    def serve(syscall):
        scheduler._execute_syscall(
            syscall, manager.address_request, "Memory"
        )

    with patch(QUEUE, serve):
        yield executor


def answered(call, *args):
    """``call(*args)``'s result, on a thread that must finish within
    ``WAIT``: the scheduler answers a syscall only when the manager
    returns, so a raise would leave the caller waiting."""
    running = Background(call, *args)
    assert running.done(WAIT), "the kernel never answered"
    return running.result


def via_execute_request(executor, agent, query):
    return executor.execute_request(agent, query)


def via_query_handler(executor, agent, query):
    """``query`` posted to /query as the SDK's ``send_request`` posts
    it, served by the handler compiled from runtime/launch.py."""
    QueryRequest, handle_query = launch_handler(executor.execute_request)
    return asyncio.run(handle_query(QueryRequest(
        query_type=query.query_class, agent_name=agent,
        query_data=query.model_dump(),
    )))


def endpoint(name, manager):
    """The handler ``name`` of runtime/launch.py over a kernel whose
    memory manager is ``manager``, compiled from its source: importing
    runtime.launch would start the whole kernel (as for
    ``launch_handler``)."""
    tree = ast.parse(LAUNCH.read_text())
    (node,) = [n for n in tree.body if getattr(n, "name", None) == name]
    node.decorator_list = []  # @app.get(...)
    namespace = {
        "__name__": "launch_under_test",
        "active_components": {"memory": manager},
        "HTTPException": HTTPException,
        "PIPELINE_VERSION": PIPELINE_VERSION,
    }
    module = ast.Module(body=[node], type_ignores=[])
    exec(compile(module, str(LAUNCH), "exec"), namespace)
    return namespace[name]


def memory_config_report(manager):
    """What ``GET /memory/config`` answers."""
    return asyncio.run(endpoint("get_memory_config", manager)())


def mem0_config(root):
    """A Mem0 store under ``root`` (its vectors in ``root/chroma``) on
    the pinned embedding model. Without extraction its LLM is never
    called."""
    return {
        "user_id": "default",
        "llm": {"provider": "ollama", "config": {
            "model": "qwen2.5:7b",
            "ollama_base_url": EMBEDDING.ollama_base_url,
        }},
        "vector_store": {"provider": "chroma", "config": {
            "collection_name": "kernel", "path": str(root / "chroma"),
        }},
    }


# --- forget_memory through the executor and /query ---------------------


@pytest.mark.parametrize(
    "entry", [via_execute_request, via_query_handler],
    ids=["execute_request", "query"],
)
def test_forget_memory_through_the_kernel(entry):
    """``forget_memory`` through ``execute_request`` and through the
    /query handler deletes the slot's rows and every carrier, across
    owners, and answers with the report in ``metadata``. The report
    names ids, owners and reasons, never another agent's private
    text."""
    manager = kernel()
    store = manager.provider = ScrubbingStore()
    seeded = seed(manager)
    with kernel_executor(manager) as executor:
        result = answered(entry, executor, ASSISTANT, forget_query())
    response = result["response"]
    assert isinstance(response, MemoryResponse) and response.success
    assert response.metadata == expected_report(seeded, store.COUNTS)
    assert store.scrubs == [(USER, [VALUE, ALIAS])]
    assert stored(manager) == [CITY]
    assert stored(manager, "bob") == [STATEMENT]
    # In the kernel's own store, which every later request's pipeline
    # reads.
    assert manager.tombstones.forms(USER) == [VALUE, ALIAS]
    # What the HTTP caller receives holds nothing of the private row.
    body = json.dumps(jsonable_encoder(result))
    for text in (PRIVATE, "billed", "Halvorsen"):
        assert text not in body


@pytest.mark.parametrize("params", [
    {"fact_key": SLOT},
    {"user_id": "", "fact_key": SLOT},
    {"user_id": USER},
    {"user_id": USER, "fact_key": ""},
], ids=["no-user", "empty-user", "no-slot", "empty-slot"])
def test_a_forget_without_a_user_or_a_slot_is_refused(params):
    """A forget that names no user or no slot answers ``success`` false
    with a reason instead of raising, deletes nothing and records no
    tombstone."""
    manager = kernel()
    seed(manager)
    response = request(manager, ASSISTANT, "forget_memory", **params)
    assert isinstance(response, MemoryResponse)
    assert response.success is False and response.error
    assert stored(manager) == [STATEMENT, ECHO, PRIVATE, CITY]
    assert manager.tombstones.entries(USER) == []


# --- the barrier --------------------------------------------------------


def test_a_forget_is_stamped_like_a_write():
    """``stamp_syscall`` gives a forget a barrier sequence under its
    canonical user when it is accepted, held until the forget returns;
    a forget without a user gets none."""
    manager = kernel({"identity": {"casefold": True}})
    forget = MemorySyscall(ASSISTANT, forget_query(user_id="ALICE"))
    manager.stamp_syscall(forget)
    assert forget.query.params["user_id"] == USER
    assert forget.barrier_seq > 0
    assert manager.barrier.stats()["pending_by_user"] == {USER: 1}
    # A retrieval accepted now is stamped to wait for it.
    assert manager.barrier.snapshot(USER) >= forget.barrier_seq
    assert manager.address_request(forget).success
    assert manager.barrier.stats()["pending_by_user"] == {}
    unscoped = MemorySyscall(ASSISTANT, MemoryQuery(
        operation_type="forget_memory", params={"fact_key": SLOT},
    ))
    manager.stamp_syscall(unscoped)
    assert getattr(unscoped, "barrier_seq", 0) == 0


@pytest.mark.parametrize("operation, params", [
    ("forget_memory", {"user_id": USER}),
    ("add_memory", {"metadata": {"owner_agent": WRITER, "user_id": USER}}),
    ("update_memory", {"user_id": USER, "content": "I live in Tartu."}),
], ids=["forget-without-a-slot", "add-without-content",
        "update-without-an-id"])
def test_a_refused_request_releases_its_barrier_sequence(operation,
                                                         params):
    """A forget, a write or an update stamped at acceptance and then
    refused releases its barrier sequence, so a later retrieval of the
    user on a store that commits asynchronously does not wait out the
    barrier's timeout."""
    manager = kernel({"write_barrier": {"timeout_ms": 300}})
    manager.provider = GatedStore()  # not synchronous: the barrier waits
    refused = request(manager, WRITER, operation, **params)
    assert refused.success is False
    _, diagnostics = manager.retrieve_for_agent(
        ASSISTANT, USER, "lawyer", k=5, include_shared=False,
    )
    outcomes = [wait["outcome"] for wait in diagnostics["barrier_waits"]]
    assert "TIMEOUT" not in outcomes
    assert manager.barrier.stats()["pending_by_user"] == {}


class HeldListing(GatedStore):
    """A store that commits asynchronously, as Mem0 and the Chroma
    in-house store do, so the barrier applies. Its ``list``, a forget's
    first provider call, waits for ``list_gate``; it logs each list,
    delete and search with its user, in order."""

    def __init__(self):
        super().__init__()
        self.list_gate = threading.Event()
        self.list_gate.set()
        self.listing = threading.Event()
        self.calls = []

    def list(self, user_id, top_k):
        self.listing.set()
        assert self.list_gate.wait(WAIT)
        self.calls.append(("list", user_id))
        return super().list(user_id, top_k)

    def delete(self, memory_id, user_id):
        self.calls.append(("delete", user_id))
        return super().delete(memory_id, user_id)

    def search(self, query_text, user_id, top_k):
        self.calls.append(("search", user_id))
        return super().search(query_text, user_id, top_k)


def search_query(user_id):
    return MemoryQuery(operation_type="retrieve_memory", params={
        "user_id": user_id, "content": "Who is my lawyer?", "k": 10,
    })


def test_a_retrieval_accepted_after_a_forget_waits_for_it():
    """A retrieval of the user accepted while a forget runs does not
    return before the forget is done: it searches only after the
    forget's deletes, so it returns no deleted row. Another user's
    retrieval does not wait, nor does the forget on its own
    sequence."""
    manager = kernel()
    store = manager.provider = HeldListing()
    seeded = seed(manager)
    store.list_gate.clear()
    store.listing.clear()
    store.calls.clear()
    with kernel_executor(manager) as executor:
        forget = Background(
            executor.execute_request, ASSISTANT, forget_query(),
        )
        # Accepted and listing at once: a wait on its own sequence would
        # last the barrier's 5 s timeout.
        assert store.listing.wait(1)
        retrieval = Background(
            executor.execute_request, ASSISTANT, search_query(USER),
        )
        elsewhere = Background(
            executor.execute_request, ASSISTANT, search_query("bob"),
        )
        assert elsewhere.done(1)
        assert not retrieval.done(0.3)
        store.list_gate.set()
        assert forget.done(WAIT) and retrieval.done(WAIT)
    assert forget.result["response"].success
    found = retrieval.result["response"].search_results
    assert ids(found) == [seeded["city"]]
    assert [op for op, user in store.calls if user == USER] == [
        "list", "delete", "delete", "delete", "search",
    ]
    assert ids(elsewhere.result["response"].search_results) == [
        seeded["bob"],
    ]


# --- the four read paths after a forget --------------------------------


def escaped(forget):
    """A kernel with ``seed``'s rows, the lawyer forgotten through the
    kernel when ``forget`` (the control keeps it), then a carrier of the
    alias planted in the store; the kernel and the carrier's id."""
    manager = kernel()
    seed(manager)
    if forget:
        assert forget_through(manager).success
    return manager, plant(manager)


@FORGOTTEN
def test_injection_leaves_out_an_escaped_carrier(forget, caplog):
    """After a kernel forget, ``ContextInjector.inject`` leaves a
    carrier that escaped it out of the block, lists it in
    ``tombstoned_rows`` and logs a WARNING. Without the forget the same
    row is injected."""
    manager, carrier = escaped(forget)
    injector = ContextInjector(manager, {
        "auto_inject": True, "max_injected_memories": 10,
        "max_memory_tokens": 2000,
    })
    question = LLMQuery(messages=[{
        "role": "user", "content": "What is on today and where do I live?",
    }], action_type="chat")
    with caplog.at_level(logging.WARNING):
        query, diagnostics = injector.inject(
            ASSISTANT, question, user_id=USER,
        )
    block = diagnostics["block_text"]
    assert CITY in block and query.messages[0]["content"] == block
    assert (CARRIER in block) == (not forget)
    assert diagnostics["tombstoned_rows"] == ([carrier] if forget else [])
    assert diagnostics["tombstoned_forms"] == (2 if forget else 0)
    assert len(warned(caplog, SELECTOR, carrier)) == int(forget)


@FORGOTTEN
def test_sdk_search_leaves_out_an_escaped_carrier(forget, caplog):
    """SDK search through the kernel (``retrieve_memory``) leaves out a
    carrier that escaped a forget and logs a WARNING; without the
    forget it returns the row."""
    manager, carrier = escaped(forget)
    with caplog.at_level(logging.WARNING):
        response = request(manager, ASSISTANT, "retrieve_memory",
                           user_id=USER, content="lunch at noon", k=10)
    assert response.success
    assert (carrier in ids(response.search_results)) == (not forget)
    assert len(warned(caplog, SELECTOR, carrier)) == int(forget)


@FORGOTTEN
def test_get_memory_refuses_an_escaped_carrier(forget, caplog):
    """``get_memory`` of a carrier that escaped a forget answers exactly
    as for a missing id and logs a WARNING; without the forget it
    returns the row."""
    manager, carrier = escaped(forget)
    with caplog.at_level(logging.WARNING):
        response = request(manager, ASSISTANT, "get_memory",
                           memory_id=carrier, user_id=USER)
    missing = request(manager, ASSISTANT, "get_memory",
                      memory_id="no-such-id", user_id=USER)
    assert (missing.success, missing.error) == (False, "Memory not found")
    if forget:
        assert response == missing
    else:
        assert (response.success, response.content) == (True, CARRIER)
    assert len(warned(caplog, FACADE, carrier)) == int(forget)


@FORGOTTEN
def test_list_memory_withholds_an_escaped_carrier(forget, caplog):
    """The owner's listing (``list_memory``) leaves out a carrier that
    escaped a forget, reports its id in ``metadata["withheld"]`` and
    logs a WARNING; without the forget it lists the row."""
    manager, carrier = escaped(forget)
    with caplog.at_level(logging.WARNING):
        response = request(manager, CALENDAR, "list_memory", user_id=USER)
    assert response.success
    assert (carrier in ids(response.search_results)) == (not forget)
    assert response.metadata == {"withheld": [carrier] if forget else []}
    assert len(warned(caplog, FACADE, carrier)) == int(forget)


# --- every branch answers -----------------------------------------------

OPERATIONS = (
    "add_memory", "update_memory", "get_memory", "retrieve_memory",
    "retrieve_memory_raw", "list_memory", "forget_memory",
)


def served(operation, reply):
    """Whether a branch served a request on a healthy store: a
    ``retrieve_memory_raw`` reply is a non-empty list of notes, every
    other branch's a successful ``MemoryResponse``."""
    if operation == "retrieve_memory_raw":
        return isinstance(reply, list) and bool(reply)
    return reply.success


def well_formed(operation, seeded):
    """A request each branch serves on ``seed``'s rows, made by the
    profile writer (the owner of the row it updates)."""
    return {
        "add_memory": {"content": "I have a cat.", "metadata": {
            "owner_agent": WRITER, "user_id": USER,
            "memory_type": "profile", "sharing_policy": "shared",
        }},
        "update_memory": {
            "memory_id": seeded["city"], "user_id": USER,
            "content": "I live in Tartu.", "metadata": {"user_id": USER},
        },
        "get_memory": {"memory_id": seeded["city"], "user_id": USER},
        "retrieve_memory": {"user_id": USER, "content": "home", "k": 5},
        "retrieve_memory_raw": {"user_id": USER, "content": "home", "k": 5},
        "list_memory": {"user_id": USER},
        "forget_memory": {"user_id": USER, "fact_key": SLOT},
    }[operation]


@pytest.mark.parametrize("operation, method", [
    ("add_memory", "add"),
    ("update_memory", "update"),
    ("get_memory", "get"),
    ("retrieve_memory", "search"),
    ("retrieve_memory_raw", "search"),
    ("list_memory", "list"),
    ("forget_memory", "delete"),
])
def test_every_branch_answers_a_failing_provider(operation, method):
    """Each branch answers ``success`` false, through
    ``address_request``, when its provider call raises an exception
    that is not a ``ProviderError``, and releases any barrier sequence
    it held. The same request on a healthy store succeeds."""
    healthy = kernel()
    assert served(operation, request(healthy, WRITER, operation,
                                     **well_formed(operation, seed(healthy))))
    manager = kernel()
    params = well_formed(operation, seed(manager))
    setattr(manager.provider, method,
            MagicMock(side_effect=RuntimeError("store down")))
    response = request(manager, WRITER, operation, **params)
    assert isinstance(response, MemoryResponse)
    assert response.success is False
    assert "RuntimeError: store down" in response.error
    assert manager.barrier.stats()["total_pending"] == 0


@pytest.mark.parametrize("operation", OPERATIONS)
def test_every_branch_answers_a_failing_tombstone_store(operation):
    """Each branch also answers ``success`` false when the tombstone
    store raises (an unreadable sidecar). For SDK search only the
    branch's own catch answers it: the selector reports a failed
    provider search itself."""
    manager = kernel()
    params = well_formed(operation, seed(manager))
    for method in ("entries", "forms", "lift", "record"):
        setattr(manager.tombstones, method,
                MagicMock(side_effect=RuntimeError("sidecar unreadable")))
    response = request(manager, WRITER, operation, **params)
    assert isinstance(response, MemoryResponse)
    assert response.success is False
    assert "RuntimeError: sidecar unreadable" in response.error
    assert manager.barrier.stats()["total_pending"] == 0


@pytest.mark.parametrize("operation, params", [
    ("add_memory", {"metadata": {"owner_agent": WRITER, "user_id": USER}}),
    ("update_memory", {"user_id": USER, "content": "I live in Tartu."}),
    ("get_memory", {"user_id": USER}),
], ids=["add-without-content", "update-without-an-id", "get-without-an-id"])
def test_every_branch_answers_a_request_it_cannot_serve(operation, params):
    """A request a branch cannot serve (nothing to write, no id to
    update or read) is answered with ``success`` false, not raised: the
    FIFO scheduler answers a syscall only when the manager returns."""
    manager = kernel()
    response = request(manager, WRITER, operation, **params)
    assert isinstance(response, MemoryResponse)
    assert response.success is False


def test_an_operation_the_manager_does_not_serve_is_answered():
    """An operation no branch of ``address_request`` serves (the
    executor rewrites ``add_agentic_memory`` before it gets here) is
    answered with ``success`` false, not raised."""
    manager = kernel()
    response = request(manager, WRITER, "add_agentic_memory",
                       content=CITY, metadata={"user_id": USER})
    assert isinstance(response, MemoryResponse)
    assert response.success is False
    assert "add_agentic_memory" in response.error


# --- what a write's reply says -----------------------------------------


def test_a_write_reply_reports_its_outcome():
    """The ``add_memory`` reply's ``metadata`` says what the write
    swept, retired and lifted and whether it was suppressed; a plain
    write did none of it."""
    manager = kernel()
    response = request(manager, WRITER, "add_memory", content=CITY,
                       metadata={"owner_agent": WRITER, "user_id": USER,
                                 "memory_type": "profile"})
    assert response.success and response.memory_id
    assert response.metadata == {
        "swept": [], "retired": [], "lifted": [], "suppressed": False,
    }


@FORGOTTEN
def test_a_rewrite_after_a_forget_is_suppressed(forget):
    """After a kernel forget, another agent's write of the value is
    swept before the write answers: the reply has ``memory_id`` "" and
    ``suppressed`` true and names the swept row. Without the forget the
    write is stored and answered with its id."""
    manager = kernel()
    seed(manager)
    if forget:
        assert forget_through(manager).success
    response = request(manager, CALENDAR, "add_memory", content=CARRIER,
                       metadata={"owner_agent": CALENDAR, "user_id": USER,
                                 "memory_type": "calendar",
                                 "sharing_policy": "shared",
                                 "fact_key": "lunch",
                                 "provenance_event": "u0-e9"})
    assert response.success
    assert OUTCOME_KEYS <= set(response.metadata)
    kept = [row.memory_id for row in manager.provider.list(USER, 100)
            if row.content == CARRIER]
    if forget:
        assert (response.memory_id, response.metadata["suppressed"]) == (
            "", True,
        )
        (swept,) = response.metadata["swept"]
        assert swept["owner_agent"] == CALENDAR
        assert manager.provider.get(swept["memory_id"], USER) is None
        assert kept == []
    else:
        assert kept == [response.memory_id]
        assert response.metadata["suppressed"] is False
        assert response.metadata["swept"] == []


@pytest.mark.parametrize("mode", ["exclude", "off"])
def test_a_later_statement_reports_the_rows_it_retired(mode):
    """With ``memory.supersession: exclude``, another writer's later
    statement of a fact retires the earlier row: the write's reply lists
    it, the row is marked and SDK search leaves it out. With ``off``
    nothing is retired."""
    manager = kernel({"supersession": mode})
    earlier = kernel_write(manager, WRITER, "My manager is Dana Whitfield.",
                           **statement("manager", "Dana Whitfield"))
    later = request(
        manager, TASK, "add_memory",
        content="My manager is now Callum Reyes.",
        metadata={"owner_agent": TASK, "user_id": USER,
                  "memory_type": "task_context", "sharing_policy": "shared",
                  **statement("manager", "Callum Reyes", event="u0-e7",
                              session=3, event_type="contradict")},
    )
    assert later.success
    marks = manager.provider.get(earlier, USER).metadata
    found = ids(request(manager, ASSISTANT, "retrieve_memory",
                        user_id=USER, content="who is my manager",
                        k=10).search_results)
    if mode == "exclude":
        assert later.metadata["retired"] == [earlier]
        assert (marks["superseded_by"], marks["superseded_session"]) == (
            "u0-e7", 3,
        )
        assert found == [later.memory_id]
    else:
        assert later.metadata["retired"] == []
        assert "superseded_by" not in marks
        assert sorted(found) == sorted([earlier, later.memory_id])


# --- /memory/config -----------------------------------------------------


def test_memory_config_reports_supersession_and_the_paths(tmp_path):
    """``/memory/config`` reports ``supersession`` inside ``pipeline``,
    where a replicated agent copies it from, and, outside it, the
    kernel's tombstones file and its store's history file (none for a
    store that keeps no history)."""
    path = tmp_path / "tombstones.sqlite"
    manager = kernel({"supersession": "exclude",
                      "tombstones_path": str(path)})
    report = memory_config_report(manager)
    assert report["pipeline"]["supersession"] == "exclude"
    copied = PipelineSettings.from_memory_config(report["pipeline"])
    assert copied.supersession == "exclude"
    assert report["tombstones_path"] == str(path)
    assert report["history_db_path"] is None
    assert "tombstones_path" not in report["pipeline"]
    json.dumps(report)  # served as JSON


# The attributes /memory/config read before this step.
PRE_STEP_ATTRIBUTES = (
    "relevance_threshold", "max_injected_memories", "max_memory_tokens",
    "provider_type", "provider", "embedding", "auto_inject",
    "auto_extract", "backend_llm", "identity_rules",
)


def test_memory_config_defaults_for_a_manager_built_with_new():
    """A manager built with ``__new__`` without this step's attributes,
    as older tests build it, reports the defaults: supersession off, no
    tombstones file and no history file."""
    legacy = MemoryManager.__new__(MemoryManager)
    source = kernel()
    for name in PRE_STEP_ATTRIBUTES:
        setattr(legacy, name, getattr(source, name))
    report = memory_config_report(legacy)
    assert (
        report["pipeline"]["supersession"], report["tombstones_path"],
        report["history_db_path"],
    ) == ("off", None, None)


@needs_ollama
def test_a_mem0_kernel_reports_and_scrubs_its_own_history_file(tmp_path):
    """A Mem0 kernel keeps Mem0's history in its store's own file, next
    to its vectors, and reports it at ``/memory/config``; a forget
    through the kernel clears the text of the deleted rows' records in
    that file and keeps the text of every other row's records."""
    root = tmp_path / "store"
    manager = kernel({"provider": "mem0", "mem0": mem0_config(root),
                      "tombstones_path": str(root / "tombstones.sqlite")})
    try:
        report = memory_config_report(manager)
        history = root / "history.db"
        assert report["history_db_path"] == str(history)
        assert report["tombstones_path"] == str(root / "tombstones.sqlite")
        assert history.exists()
        seeded = seed(manager)
        forgotten = forget_through(manager)
        assert forgotten.success
        assert forgotten.metadata["scrubbed"]["history"] > 0
        with closing(sqlite3.connect(history)) as db:
            records = db.execute(
                "SELECT memory_id, old_memory, new_memory FROM history"
            ).fetchall()
        texts = {}
        for memory_id, *record in records:
            texts.setdefault(memory_id, []).extend(t for t in record if t)
        for name in ("statement", "echo", "private"):
            assert texts[seeded[name]] == [], name
        # The user's other row, and another user's statement, keep it.
        assert texts[seeded["city"]] == [CITY]
        assert texts[seeded["bob"]] == [STATEMENT]
    finally:
        manager.close()


# --- the kernel's settings ----------------------------------------------


def test_the_supersession_setting_reaches_the_kernels_pipeline():
    """``memory.supersession`` reaches ``pipeline_settings()`` and the
    pipeline the kernel builds for each request, ``off`` by default; an
    invalid value fails when the manager is built."""
    manager = kernel({"supersession": "exclude"})
    assert manager.pipeline_settings().supersession == "exclude"
    pipeline = manager.memory_pipeline()
    assert pipeline.settings.supersession == "exclude"
    assert pipeline.selector.settings.supersession == "exclude"
    assert kernel().memory_pipeline().settings.supersession == "off"
    with pytest.raises(ValueError, match="supersession"):
        kernel({"supersession": "retire"})


def test_tombstones_path_gives_a_file_store_there(tmp_path):
    """With ``memory.tombstones_path`` the manager keeps its tombstones
    in that SQLite file and hands that store to every pipeline it
    builds; without it they are kept in memory."""
    path = tmp_path / "state" / "tombstones.sqlite"
    manager = kernel({"tombstones_path": str(path)})
    assert manager.tombstones_path == str(path)
    assert manager.tombstones.path == str(path) and path.exists()
    assert manager.memory_pipeline().tombstones is manager.tombstones
    seed(manager)
    assert forget_through(manager).success
    assert TombstoneStore(str(path)).forms(USER) == [VALUE, ALIAS]
    unset = kernel()
    assert (unset.tombstones_path, unset.tombstones.path) == (None, None)
    assert unset.memory_pipeline().tombstones is unset.tombstones


def test_two_kernels_on_one_tombstones_file_share_a_forget(tmp_path):
    """Two managers on one tombstones file share their forgets: a forget
    through one hides a carrier in the other's store from its
    ``get_memory``. A manager with a file of its own, or with none,
    still returns the row."""
    path = str(tmp_path / "tombstones.sqlite")
    first = kernel({"tombstones_path": path})
    others = {
        "same_file": kernel({"tombstones_path": path}),
        "own_file": kernel(
            {"tombstones_path": str(tmp_path / "other.sqlite")}
        ),
        "in_memory": kernel(),
    }
    carriers = {name: plant(manager) for name, manager in others.items()}
    seed(first)
    assert forget_through(first).success
    for name, manager in others.items():
        got = request(manager, ASSISTANT, "get_memory",
                      memory_id=carriers[name], user_id=USER)
        if name == "same_file":
            assert (got.success, got.error) == (False, "Memory not found")
        else:
            assert (got.success, got.content) == (True, CARRIER), name


# --- the production stores ----------------------------------------------


@needs_ollama
@pytest.mark.parametrize("backend", ["in-house", "mem0"])
def test_a_kernel_forget_on_a_real_store(backend, tmp_path):
    """On the production stores, a forget through the kernel deletes the
    slot's row and every carrier, across owners, keeps the user's other
    rows and other users' rows, and leaves nothing for the guard to
    drop."""
    root = tmp_path / "store"
    config = (
        {"provider": "mem0", "mem0": mem0_config(root)}
        if backend == "mem0"
        else {"provider": "in-house",
              "chroma_inhouse": {"path": str(root / "chroma")}}
    )
    manager = kernel(config)
    try:
        seeded = seed(manager)
        forgotten = forget_through(manager)
        assert forgotten.success
        assert {
            entry["memory_id"]: (entry["owner_agent"], entry["reason"])
            for entry in forgotten.metadata["deleted"]
        } == {
            seeded["statement"]: (WRITER, "fact_key"),
            seeded["echo"]: (CALENDAR, "alias"),
            seeded["private"]: (TASK, "value"),
        }
        assert stored(manager) == [CITY]
        assert stored(manager, "bob") == [STATEMENT]
        _, diagnostics = manager.retrieve_for_agent(
            ASSISTANT, USER, "Who is my lawyer?", k=10,
            include_shared=True, request_user_id=USER,
        )
        assert diagnostics["tombstoned_forms"] == 2
        assert diagnostics["tombstoned_rows"] == []
    finally:
        manager.close()


# --- scripts/set_memory_mode.py --supersession --------------------------

SUPERSESSION = "  supersession:"


def supersession_line(text):
    (line,) = [l for l in text.split("\n") if l.startswith(SUPERSESSION)]
    return line


def test_the_example_config_ships_the_defaults():
    """config.yaml.example ships supersession off and the kernel's
    tombstones file."""
    memory = yaml.safe_load(EXAMPLE.read_text())["memory"]
    assert memory["supersession"] == "off"
    assert memory["tombstones_path"] == ".aios_state/tombstones.sqlite"


def test_supersession_flag_sets_its_line_only(tmp_path):
    """``--supersession`` sets ``memory.supersession`` to exclude and
    back to off, keeping its comment in its column and every other byte
    of the file; without the flag the line is left as it is."""
    original = EXAMPLE.read_text()
    config = tmp_path / "config.yaml"
    config.write_text(original)
    args = [str(config), "--provider", "mem0", "--kernel-memory", "on"]
    set_memory_mode(args + ["--supersession", "exclude"])
    excluded = config.read_text()
    assert yaml.safe_load(excluded)["memory"]["supersession"] == "exclude"
    assert all(line.startswith(MODE_KEYS + (SUPERSESSION,))
               for line in changed_lines(original, excluded))
    before, after = supersession_line(original), supersession_line(excluded)
    assert after.startswith('  supersession: "exclude" ')
    assert after.index("#") == before.index("#")
    assert after[after.index("#"):] == before[before.index("#"):]
    set_memory_mode(args + ["--supersession", "off"])
    assert config.read_text() == set_mode(original, "mem0", True)
    config.write_text(excluded)
    set_memory_mode(args)
    assert supersession_line(config.read_text()) == after


def test_supersession_flag_refuses_a_config_without_the_key(tmp_path):
    """``--supersession`` exits on a config without the key, writing
    nothing, and argparse refuses a mode other than off or exclude."""
    text = "\n".join(
        line for line in EXAMPLE.read_text().split("\n")
        if not line.startswith(SUPERSESSION)
    )
    with pytest.raises(SystemExit):
        set_supersession(text, "exclude")
    config = tmp_path / "config.yaml"
    config.write_text(text)
    args = [str(config), "--provider", "mem0", "--kernel-memory", "on"]
    with pytest.raises(SystemExit):
        set_memory_mode(args + ["--supersession", "exclude"])
    assert config.read_text() == text
    config.write_text(EXAMPLE.read_text())
    with pytest.raises(SystemExit):
        set_memory_mode(args + ["--supersession", "retire"])
    assert config.read_text() == EXAMPLE.read_text()


# --- the SDK ------------------------------------------------------------


def test_the_installed_sdk_sends_a_forget():
    """The kernel venv's SDK accepts ``forget_memory`` as an operation,
    and ``forget_memories(agent_name, fact_key, user_id)`` sends a
    ``forget_memory`` MemoryQuery with ``params`` {user_id, fact_key}
    to the kernel."""
    operations = typing.get_args(
        MemoryQuery.model_fields["operation_type"].annotation
    )
    assert "forget_memory" in operations
    with patch.object(sdk, "send_request", return_value="sent") as send:
        assert sdk.forget_memories(ASSISTANT, SLOT, USER) == "sent"
    agent, query, base_url = send.call_args.args
    assert (agent, base_url) == (ASSISTANT, sdk.aios_kernel_url)
    assert isinstance(query, MemoryQuery)
    assert query.query_class == "memory"
    assert (query.operation_type, query.params) == (
        "forget_memory", {"user_id": USER, "fact_key": SLOT},
    )
