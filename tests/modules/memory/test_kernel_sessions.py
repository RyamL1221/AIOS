"""The kernel binds a request to its session's user (NeurIPS Subtask 18,
docs/STRESS_DIMENSIONS.md, "wrong_user").

The deployment opens a kernel session for a user; every request that
carries the session's token is served for that user, whatever user id
the agent put in it, and the reply records an agent's claim the session
overrode (``identity_overridden``). A request with an unknown token is
refused; a request without one is served as before. Through the
registry, the manager, the executor and the ``/query`` handler."""
import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from cerebrum.llm.apis import LLMQuery
from cerebrum.memory.apis import MemoryQuery

from aios.memory.context_injector import ContextInjector
from aios.memory.manager import MemoryManager
from aios.memory.pipeline import (
    MemoryPipeline,
    PipelineSettings,
    SessionRegistry,
    UnknownSession,
    note_from_request,
)
from aios.memory.providers.in_house import InHouseProvider
from aios.scheduler.fifo_scheduler import FIFOScheduler
from aios.syscall.memory import MemorySyscall
from aios.syscall.syscall import SyscallExecutor
from tests.modules.syscall.test_v2_requests import launch_handler

USER = "alice"
VICTIM = "bob"
WRITER = "travel_agent"
QUEUE = "aios.syscall.syscall.global_memory_req_queue_add_message"
MEMORY_CONFIG = {
    "provider": "in-memory",
    "relevance_threshold": 0.0,
    "max_injected_memories": 10,
    "max_memory_tokens": 2000,
    "write_barrier": {"enabled": True, "timeout_ms": 500},
    "auto_inject": True,
    "identity": {"casefold": True, "email_domains": ["users.example"]},
}


def kernel():
    with patch("aios.memory.manager.global_config") as config:
        config.get_memory_config.return_value = MEMORY_CONFIG
        config.get_storage_config.return_value = {}
        return MemoryManager()


def write_query(user_id, content="I fly with Wizzair."):
    return MemoryQuery(operation_type="add_memory", params={
        "content": content,
        "metadata": {"owner_agent": WRITER, "user_id": user_id,
                     "memory_type": "calendar", "sharing_policy": "shared"},
    })


# --- the registry ---------------------------------------------------------

def test_a_session_maps_its_token_to_its_user_until_closed():
    registry = SessionRegistry()
    token = registry.open(USER)
    other = registry.open(USER)
    assert token != other and len(token) == 32
    assert registry.user_of(token) == USER
    assert registry.close(token) is True
    assert registry.close(token) is False
    with pytest.raises(UnknownSession):
        registry.user_of(token)
    with pytest.raises(UnknownSession):
        registry.user_of(None)
    with pytest.raises(ValueError):
        registry.open("  ")


def test_a_token_differs_from_every_earlier_token():
    """A session's token is random (``secrets.token_hex``), so a request
    cannot name another user's session (``SessionRegistry``;
    docs/STRESS_DIMENSIONS.md:547-550): a token opened after others
    were closed differs from every earlier one, and opening never takes
    over a session still open. The harness opens and closes one session
    per v2 session, one after another and, in the load mode,
    overlapping: a reused token would merge the write quota's
    per-session buckets, or serve one user's requests for another."""
    registry = SessionRegistry()
    issued = []
    for user in ("alice", "bob", "carol"):  # one after another
        token = registry.open(user)
        assert token not in issued
        issued.append(token)
        assert registry.close(token) is True
    bob = registry.open("bob")
    alice = registry.open("alice")
    assert registry.close(bob) is True
    carol = registry.open("carol")  # alice's session is still open
    assert len({*issued, bob, alice, carol}) == len(issued) + 3
    assert registry.user_of(alice) == "alice"
    assert registry.user_of(carol) == "carol"


# --- the manager's binding ------------------------------------------------

def test_a_write_claiming_another_user_is_bound_to_the_session():
    manager = kernel()
    token = manager.open_session(USER)
    query = write_query(VICTIM)
    overridden = manager.bind_session(query, token)
    assert overridden == {"claimed": VICTIM, "bound": USER}
    assert query.params["metadata"]["user_id"] == USER


def test_a_claim_of_the_sessions_own_user_is_no_override():
    """A V2 alias canonicalizes to the session's user: no override."""
    manager = kernel()
    token = manager.open_session(USER)
    for claim in (USER, "ALICE", f"{USER}@users.example", None):
        query = write_query(claim)
        assert manager.bind_session(query, token) is None
        assert query.params["metadata"]["user_id"] == USER


@pytest.mark.parametrize("operation,params", [
    ("list_memory", {"user_id": VICTIM}),
    ("forget_memory", {"user_id": VICTIM, "fact_key": "airline"}),
    ("get_memory", {"memory_id": "m1", "user_id": VICTIM}),
    ("remove_memory", {"memory_id": "m1", "user_id": VICTIM}),
    ("retrieve_memory", {"content": "airline", "user_id": VICTIM}),
    ("update_memory", {"memory_id": "m1", "content": "x",
                       "metadata": {"user_id": VICTIM}}),
])
def test_every_request_is_bound(operation, params):
    manager = kernel()
    token = manager.open_session(USER)
    query = MemoryQuery(operation_type=operation, params=dict(params))
    assert manager.bind_session(query, token) == {
        "claimed": VICTIM, "bound": USER,
    }
    assert query.params["user_id"] == USER
    metadata = query.params.get("metadata")
    if metadata:
        assert metadata["user_id"] == USER


def test_an_unknown_session_is_refused_and_no_session_changes_nothing():
    manager = kernel()
    query = write_query(VICTIM)
    with pytest.raises(UnknownSession):
        manager.bind_session(query, "f" * 32)
    assert manager.bind_session(query, None) is None
    assert query.params["metadata"]["user_id"] == VICTIM


def test_a_chat_request_is_bound_to_the_session():
    manager = kernel()
    token = manager.open_session(USER)
    assert manager.bind_chat_user(VICTIM, token) == (
        USER, {"claimed": VICTIM, "bound": USER},
    )
    assert manager.bind_chat_user(USER, token) == (USER, None)
    assert manager.bind_chat_user(VICTIM, None) == (VICTIM, None)
    with pytest.raises(UnknownSession):
        manager.bind_chat_user(USER, "0" * 32)


# --- through the executor and the /query handler -------------------------

@contextmanager
def served(manager):
    """An executor wired to ``manager``, its memory queue served by the
    FIFO scheduler's own step on the caller's thread."""
    scheduler = FIFOScheduler(
        llm=None, memory_manager=manager, storage_manager=None,
        tool_manager=None, log_mode="console", get_llm_syscall=None,
        get_memory_syscall=None, get_storage_syscall=None,
        get_tool_syscall=None,
    )
    executor = SyscallExecutor()
    executor.memory_manager = manager

    def serve(syscall):
        scheduler._execute_syscall(syscall, manager.address_request,
                                   "Memory")

    with patch(QUEUE, serve):
        yield executor


def query_body(user_id, token):
    return {
        "agent_name": WRITER, "query_type": "memory",
        "query_data": write_query(user_id).model_dump(),
        "session_token": token,
    }


def test_the_handler_files_a_wrong_user_write_under_the_session():
    """Kernel locus, ``wrong_user``: the write lands in the session's
    user's partition, not the claimed one's, and the reply says so."""
    manager = kernel()
    token = manager.open_session(USER)
    with served(manager) as executor:
        QueryRequest, handle_query = launch_handler(
            executor.execute_request, manager=manager,
            accept_memory_request=executor.accept_memory,
        )
        result = asyncio.run(handle_query(
            QueryRequest(**query_body(VICTIM, token))
        ))
    assert result["response"].success and result["response"].memory_id
    assert result["identity_overridden"] == {
        "claimed": VICTIM, "bound": USER,
    }
    assert [r.content for r in manager.provider.list(USER, 10)] == [
        "I fly with Wizzair.",
    ]
    assert manager.provider.list(VICTIM, 10) == []


def test_the_handler_refuses_an_unknown_session():
    manager = kernel()
    with served(manager) as executor:
        QueryRequest, handle_query = launch_handler(
            executor.execute_request, manager=manager,
            accept_memory_request=executor.accept_memory,
        )
        result = asyncio.run(handle_query(
            QueryRequest(**query_body(USER, "a" * 32))
        ))
    response = result["response"]
    assert response.success is False and "unknown session" in response.error
    assert manager.provider.list(USER, 10) == []


def test_without_a_session_the_claim_is_served_as_before():
    manager = kernel()
    with served(manager) as executor:
        QueryRequest, handle_query = launch_handler(
            executor.execute_request, manager=manager,
            accept_memory_request=executor.accept_memory,
        )
        result = asyncio.run(handle_query(
            QueryRequest(**query_body(VICTIM, None))
        ))
    assert result["response"].success
    assert "identity_overridden" not in result
    assert len(manager.provider.list(VICTIM, 10)) == 1


def test_a_chat_request_reads_the_sessions_user_and_records_the_claim():
    """The handler binds the chat request to the session's user and the
    executor reports the claim it overrode in the injection
    diagnostics."""
    manager = kernel()
    token = manager.open_session(USER)
    seen = []

    def execute_request(agent_name, query):
        seen.append(query)
        return {"response": "ok"}

    QueryRequest, handle_query = launch_handler(execute_request,
                                                manager=manager)
    body = {
        "agent_name": "assistant_agent", "query_type": "llm",
        "query_data": LLMQuery(
            messages=[{"role": "user", "content": "which airline?"}],
            action_type="chat",
        ).model_dump() | {"user_id": VICTIM},
        "session_token": token,
    }
    assert asyncio.run(handle_query(QueryRequest(**body))) == {
        "response": "ok",
    }
    (query,) = seen
    assert query._request_user_id == USER
    assert query._identity_overridden == {"claimed": VICTIM, "bound": USER}

    executor = SyscallExecutor()
    executor.context_injector = MagicMock()
    executor.context_injector.inject.return_value = (
        query, {"resolved_user_id": USER},
    )
    executor.execute_llm_syscall = MagicMock(return_value={
        "response": SimpleNamespace(response_message="Wizzair."),
    })
    result = executor.execute_request("assistant_agent", query)
    assert executor.context_injector.inject.call_args.kwargs["user_id"] \
        == USER
    assert result["injection_diagnostics"]["identity_overridden"] == {
        "claimed": VICTIM, "bound": USER,
    }


def test_a_chat_request_takes_its_barrier_snapshot_on_arrival():
    """The handler takes a chat request's barrier snapshot when it
    accepts the request (Subtask 18): it covers the user's writes
    accepted before, and not one accepted while the request waited to
    be served."""

    class AsyncCommit(InHouseProvider):
        synchronous_commit = False  # a store a read waits for

    manager = kernel()
    manager.provider = AsyncCommit()
    before = manager.barrier.acquire(USER)  # a write still in flight
    seen = []

    def execute_request(agent_name, query):
        # A write the kernel accepts after the chat arrived.
        seen.append((query, manager.barrier.acquire(USER)))
        return {"response": "ok"}

    QueryRequest, handle_query = launch_handler(execute_request,
                                                manager=manager)
    body = {
        "agent_name": "assistant_agent", "query_type": "llm",
        "query_data": LLMQuery(
            messages=[{"role": "user", "content": "which airline?"}],
            action_type="chat",
        ).model_dump() | {"user_id": USER},
    }
    asyncio.run(handle_query(QueryRequest(**body)))
    ((query, after),) = seen
    assert before <= query._barrier_snapshot < after


def test_a_chat_request_with_an_unknown_session_is_refused():
    from fastapi import HTTPException

    manager = kernel()
    QueryRequest, handle_query = launch_handler(
        lambda *a: {"response": "ok"}, manager=manager,
    )
    body = {
        "agent_name": "assistant_agent", "query_type": "llm",
        "query_data": LLMQuery(
            messages=[{"role": "user", "content": "hi"}],
            action_type="chat",
        ).model_dump(),
        "session_token": "b" * 32,
    }
    with pytest.raises(HTTPException) as raised:
        asyncio.run(handle_query(QueryRequest(**body)))
    assert raised.value.status_code == 400


def test_bound_requests_equal_the_library_for_the_sessions_user():
    """The equivalence test's property under a session (Subtask 18):
    each user's writes and chat, every one claiming the next user's id
    but sent in the user's kernel session, leave the kernel the stored
    rows and the prompts a library builds from the same writes made
    with the user's own id."""
    from tests.modules.memory.test_pipeline_library import (
        MEMORY_CONFIG as LIBRARY_CONFIG,
        query_text,
        seeded_requests,
        stored_rows,
        without_timings,
    )

    with patch("aios.memory.manager.global_config") as config:
        config.get_memory_config.return_value = LIBRARY_CONFIG
        config.get_storage_config.return_value = {}
        manager = MemoryManager()
    injector = ContextInjector(manager, LIBRARY_CONFIG)
    store = InHouseProvider()
    store.initialize({})
    library = MemoryPipeline(store, PipelineSettings.from_memory_config(
        manager.pipeline_settings().as_dict()
    ))
    users = [f"user{seed:02d}" for seed in range(20)]
    tokens = {user: manager.open_session(user) for user in users}
    claimed = {user: users[(i + 1) % 20] for i, user in enumerate(users)}
    overridden = 0
    for seed, user in enumerate(users):
        for agent, params in seeded_requests(seed):
            right = dict(params, metadata=dict(params["metadata"],
                                               user_id=user))
            library.write(agent, None, note_from_request(right))
            wrong = dict(params, metadata=dict(params["metadata"],
                                               user_id=claimed[user]))
            query = MemoryQuery(operation_type="add_memory", params=wrong)
            overridden += bool(manager.bind_session(query, tokens[user]))
            syscall = MemorySyscall(agent, query)
            manager.stamp_syscall(syscall)
            assert manager.address_request(syscall).success
    assert overridden == sum(len(seeded_requests(s)) for s in range(20))
    for seed, user in enumerate(users):
        assert stored_rows(manager.provider, user) == stored_rows(store, user)
        messages = [{"role": "user", "content": query_text(seed)}]
        bound, override = manager.bind_chat_user(claimed[user], tokens[user])
        assert (bound, override) == (
            user, {"claimed": claimed[user], "bound": user})
        query = LLMQuery(messages=list(messages), action_type="chat")
        query, kernel_diag = injector.inject("assistant_agent", query,
                                             user_id=bound)
        library_messages, library_diag = library.inject(
            "assistant_agent", list(messages), user_id=user)
        assert query.messages == library_messages

        def same(diagnostics):  # two stores: their row ids differ
            out = without_timings(diagnostics)
            out["injected_memories"] = [
                {k: v for k, v in m.items() if k != "memory_id"}
                for m in out["injected_memories"]]
            return out
        assert same(kernel_diag) == same(library_diag)
        assert kernel_diag["injected_count"]
