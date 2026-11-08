"""Benchmark v2 requests through the kernel's entry points
(docs/BENCHMARK_V2.md): the executor dispatches ``list_memory``, and the
caller's current session (``LLMQuery.session``) goes from the ``/query``
handler through the executor to the context injector and the
conversation write.
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
from cerebrum.memory.apis import MemoryQuery
from cerebrum.storage.apis import StorageQuery
from cerebrum.tool.apis import ToolQuery

from aios.syscall.syscall import SyscallExecutor

AGENT = "assistant_agent"
USER = "alice"
LAUNCH = Path(__file__).resolve().parents[3] / "runtime" / "launch.py"


# --- list_memory ------------------------------------------------------


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
    assert extract.call_args.kwargs == {"user_id": USER, "session": 7}


def test_chat_without_a_session_passes_none():
    query = chat_query()
    executor = chat_executor(query)
    executor.execute_request(AGENT, query)
    assert executor.context_injector.inject.call_args.kwargs["session"] \
        is None
    assert executor.conversation_extractor.extract_async.call_args \
        .kwargs["session"] is None


# --- the /query handler -----------------------------------------------


def launch_handler(execute_request):
    """``QueryRequest`` and ``handle_query``, compiled from
    runtime/launch.py's source with the names they use.

    Importing runtime.launch would start the whole kernel (it
    initializes every component on import), so only these two
    definitions run; ``execute_request`` stands in for the executor.
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
        "LLMQuery": LLMQuery, "MemoryQuery": MemoryQuery,
        "StorageQuery": StorageQuery, "ToolQuery": ToolQuery,
        "asyncio": asyncio, "copy": copy,
        "logger": logging.getLogger(__name__),
        "selected_llms": {"llms": []},
        "execute_request": execute_request,
    }
    module = ast.Module(body=nodes, type_ignores=[])
    exec(compile(module, str(LAUNCH), "exec"), namespace)
    return namespace["QueryRequest"], namespace["handle_query"]


def handled_query(**llm_fields):
    """The LLMQuery the /query handler hands the executor for an SDK
    ``llm_chat`` body."""
    seen = []

    def execute_request(agent_name, query):
        seen.append(query)
        return {"response": "ok"}

    QueryRequest, handle_query = launch_handler(execute_request)
    body = {
        "agent_name": AGENT,
        "query_type": "llm",
        "query_data": LLMQuery(
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
