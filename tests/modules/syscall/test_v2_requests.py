"""Benchmark v2 requests through the kernel's entry points
(docs/BENCHMARK_V2.md): the executor dispatches ``list_memory`` and
answers a memory operation it does not dispatch with a failure, and the
caller's current session (``LLMQuery.session``) and probe id
(``LLMQuery.provenance_event``) go from the ``/query`` handler through
the executor to the context injector and the conversation write.
"""
import ast
import asyncio
import copy
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

from fastapi import HTTPException
from pydantic import BaseModel, model_validator
from typing_extensions import Literal

from cerebrum.llm.apis import LLMQuery
from cerebrum.memory.apis import MemoryQuery, MemoryResponse
from cerebrum.storage.apis import StorageQuery
from cerebrum.tool.apis import ToolQuery

from aios.syscall.syscall import SyscallExecutor

AGENT = "assistant_agent"
USER = "alice"
LAUNCH = Path(__file__).resolve().parents[3] / "runtime" / "launch.py"


class ProvenanceLLMQuery(LLMQuery):
    """``LLMQuery`` with ``provenance_event``, as the Cerebrum SDK sends
    it from Amendment 2 on. The kernel venv's installed copy may
    predate the field and drop it, which the kernel must survive."""

    provenance_event: Optional[str] = None


# --- memory operations ------------------------------------------------


def test_execute_request_dispatches_list_memory():
    executor = SyscallExecutor()
    executor.execute_memory_syscall = MagicMock(
        return_value={"response": "rows"}
    )
    query = MemoryQuery(
        operation_type="list_memory", params={"user_id": USER},
    )
    assert executor.execute_request("profile_agent", query) == {
        "response": "rows",
    }
    executor.execute_memory_syscall.assert_called_once_with(
        "profile_agent", query
    )


def test_an_unsupported_memory_operation_gets_an_explicit_failure(caplog):
    """``retrieve_memory_raw`` is in the SDK's Literal but not
    dispatched: it used to fall through to None, which ``/query``
    returned as HTTP 200 ``null``."""
    executor = SyscallExecutor()
    executor.execute_memory_syscall = MagicMock()
    query = MemoryQuery(
        operation_type="retrieve_memory_raw",
        params={"user_id": USER, "content": "lawyer"},
    )
    with caplog.at_level(logging.WARNING, logger="aios.syscall.syscall"):
        result = executor.execute_request("profile_agent", query)
    assert set(result) == {"response"}
    response = result["response"]
    assert isinstance(response, MemoryResponse)
    assert (response.success, response.error) == (
        False, "Unsupported memory operation_type 'retrieve_memory_raw'",
    )
    executor.execute_memory_syscall.assert_not_called()
    assert [r.levelname for r in caplog.records
            if "Unsupported memory operation_type" in r.getMessage()] == [
        "WARNING",
    ]
    # The /query handler hands it back, never null.
    QueryRequest, handle_query = launch_handler(executor.execute_request)
    answer = asyncio.run(handle_query(QueryRequest(
        agent_name="profile_agent", query_type="memory",
        query_data=query.model_dump(),
    )))
    assert answer["response"].success is False


# --- the session on the chat path -------------------------------------


def chat_executor(query):
    """An executor whose injector, extractor and model call are fakes."""
    executor = SyscallExecutor()
    executor.context_injector = MagicMock()
    executor.context_injector.inject.return_value = (
        query, {"resolved_user_id": USER},
    )
    executor.conversation_extractor = MagicMock()
    executor.execute_llm_syscall = MagicMock(return_value={
        "response": SimpleNamespace(response_message="Birch."),
    })
    return executor


def chat_query():
    return LLMQuery(
        messages=[{"role": "user", "content": "where is the sync?"}],
        action_type="chat",
    )


def test_chat_passes_the_request_session_to_injection_and_extraction():
    query = chat_query()
    query._request_user_id = USER
    query._request_session = 7
    executor = chat_executor(query)
    executor.execute_request(AGENT, query)
    inject = executor.context_injector.inject
    assert inject.call_args.kwargs == {"user_id": USER, "session": 7}
    extract = executor.conversation_extractor.extract_async
    assert extract.call_args.args == (AGENT, "where is the sync?", "Birch.")
    assert extract.call_args.kwargs == {
        "user_id": USER, "session": 7, "provenance_event": None,
    }


def test_chat_without_a_session_passes_none():
    query = chat_query()
    executor = chat_executor(query)
    executor.execute_request(AGENT, query)
    assert executor.context_injector.inject.call_args.kwargs["session"] \
        is None
    extract = executor.conversation_extractor.extract_async
    assert extract.call_args.kwargs["session"] is None
    assert extract.call_args.kwargs["provenance_event"] is None


def test_chat_passes_the_request_provenance_event_to_extraction():
    """The kernel assistant's probe id reaches the stored turn
    (BENCHMARK_V2.md, Amendment 2); the block does not need it."""
    query = chat_query()
    query._request_user_id = USER
    query._request_session = 7
    query._request_provenance_event = "u004-p6-integration"
    executor = chat_executor(query)
    executor.execute_request(AGENT, query)
    extract = executor.conversation_extractor.extract_async
    assert extract.call_args.kwargs == {
        "user_id": USER, "session": 7,
        "provenance_event": "u004-p6-integration",
    }
    assert executor.context_injector.inject.call_args.kwargs == {
        "user_id": USER, "session": 7,
    }


# --- the /query handler -----------------------------------------------


def launch_handler(execute_request, llm_query=LLMQuery):
    """``QueryRequest`` and ``handle_query``, compiled from
    runtime/launch.py's source with the names they use.

    Importing runtime.launch would start the whole kernel (it
    initializes every component on import), so only these two
    definitions run; ``execute_request`` stands in for the executor,
    and ``llm_query`` for the SDK's ``LLMQuery``.
    """
    tree = ast.parse(LAUNCH.read_text())
    wanted = {"QueryRequest", "handle_query"}
    nodes = [
        node for node in tree.body
        if getattr(node, "name", None) in wanted
    ]
    assert {node.name for node in nodes} == wanted
    for node in nodes:
        if isinstance(node, ast.AsyncFunctionDef):
            node.decorator_list = []  # @app.post("/query")
    namespace = {
        "__name__": "launch_under_test",
        "Any": Any, "Dict": Dict, "Literal": Literal, "Optional": Optional,
        "BaseModel": BaseModel, "model_validator": model_validator,
        "HTTPException": HTTPException,
        "LLMQuery": llm_query, "MemoryQuery": MemoryQuery,
        "StorageQuery": StorageQuery, "ToolQuery": ToolQuery,
        "asyncio": asyncio, "copy": copy,
        "logger": logging.getLogger(__name__),
        "selected_llms": {"llms": []},
        "execute_request": execute_request,
    }
    module = ast.Module(body=nodes, type_ignores=[])
    exec(compile(module, str(LAUNCH), "exec"), namespace)
    return namespace["QueryRequest"], namespace["handle_query"]


def handled_query(llm_query=LLMQuery, **llm_fields):
    """The LLMQuery the /query handler hands the executor for an SDK
    ``llm_chat`` body, sent with the SDK's ``llm_query`` class."""
    seen = []

    def execute_request(agent_name, query):
        seen.append(query)
        return {"response": "ok"}

    QueryRequest, handle_query = launch_handler(execute_request, llm_query)
    body = {
        "agent_name": AGENT,
        "query_type": "llm",
        "query_data": llm_query(
            messages=[{"role": "user", "content": "where is the sync?"}],
            action_type="chat",
            **llm_fields,
        ).model_dump(),
    }
    assert asyncio.run(handle_query(QueryRequest(**body))) == {
        "response": "ok",
    }
    (query,) = seen
    return query


def test_query_handler_promotes_the_session():
    query = handled_query(user_id=USER, session=7)
    assert query._request_session == 7
    assert query._request_user_id == USER  # as before


def test_query_handler_without_a_session_promotes_none():
    query = handled_query(user_id=USER)
    assert query._request_session is None


def test_query_handler_promotes_the_provenance_event():
    query = handled_query(
        ProvenanceLLMQuery, user_id=USER, session=7,
        provenance_event="u004-p6-integration",
    )
    # The rebuilt query drops the field; the handler keeps it.
    assert query.provenance_event is None
    assert query._request_provenance_event == "u004-p6-integration"
    assert (query._request_session, query._request_user_id) == (7, USER)


def test_query_handler_without_a_provenance_event_promotes_none():
    # As sent with the installed LLMQuery (until the venv is reinstalled,
    # a copy without the field, which the handler reads with getattr)
    # and with one that has the field and leaves it unset.
    for llm_query in (LLMQuery, ProvenanceLLMQuery):
        query = handled_query(llm_query, user_id=USER, session=7)
        assert query._request_provenance_event is None
