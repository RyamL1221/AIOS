"""Per-trial cost instrumentation (NeurIPS Subtask 7): the assistant's
token usage from the LiteLLM call site, the latency breakdown, and the
attribution of a memory backend's own LLM and embedding calls to the
trial (user) they were made for."""

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import litellm
import pytest

from cerebrum.llm.apis import LLMQuery
from cerebrum.utils import usage

# aios.syscall.syscall first: importing aios.syscall.llm alone is circular.
from aios.syscall.syscall import SyscallExecutor
from aios.syscall.llm import LLMSyscall
from aios.llm_core.adapter import LLMAdapter


def fake_completion(**kwargs):
    message = SimpleNamespace(content="hello", tool_calls=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(
            prompt_tokens=12, completion_tokens=8, total_tokens=20
        ),
    )


def adapter_for(model: str) -> LLMAdapter:
    adapter = LLMAdapter.__new__(LLMAdapter)
    adapter.llm_configs = [SimpleNamespace(name="gpt-4o", hostname=None)]
    adapter.llms = [model]
    adapter.use_context_manager = False
    adapter.context_manager = None
    return adapter


def llm_syscall() -> LLMSyscall:
    return LLMSyscall("assistant_agent", LLMQuery(
        messages=[{"role": "user", "content": "hi"}], action_type="chat",
    ))


def test_adapter_records_litellm_usage_and_model_time():
    syscall = llm_syscall()
    with patch("aios.llm_core.adapter.litellm.completion",
               side_effect=fake_completion):
        _, response = adapter_for("azure/gpt-4o").execute_llm_syscall(
            0, syscall
        )
    assert response.response_message == "hello"
    assert syscall.get_token_usage() == {
        "prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20,
    }
    assert syscall.llm_ms is not None and syscall.llm_ms >= 0


def test_partial_usage_keeps_unknown_fields_none():
    syscall = llm_syscall()
    syscall.set_token_usage(SimpleNamespace(completion_tokens=3))
    assert syscall.get_token_usage() == {
        "prompt_tokens": None, "completion_tokens": 3, "total_tokens": None,
    }
    fresh = llm_syscall()
    fresh.set_token_usage(None)
    assert fresh.get_token_usage() is None


def test_llm_timing_is_the_wait_before_the_model_call():
    syscall = llm_syscall()
    syscall.set_created_time(100.0)
    syscall.set_start_time(100.25)
    syscall.llm_ms = 900.0
    assert SyscallExecutor._llm_timing(syscall) == {
        "llm_ms": 900.0, "schedule_wait_ms": 250.0,
    }


def test_chat_reply_carries_usage_and_a_latency_breakdown_that_sums():
    executor = SyscallExecutor()
    query = LLMQuery(
        messages=[{"role": "user", "content": "hi"}], action_type="chat",
    )
    stages = {"barrier_wait_ms": 1.5, "search_ms": 20.0,
              "select_ms": 0.5, "format_ms": 2.0}
    executor.context_injector = MagicMock()
    executor.context_injector.inject.return_value = (
        query, {"injected_count": 2, **stages}
    )
    executor.execute_llm_syscall = MagicMock(return_value={
        "response": "ok",
        "token_usage": {"prompt_tokens": 5, "completion_tokens": 2,
                        "total_tokens": 7},
        "llm_timing": {"llm_ms": 800.0, "schedule_wait_ms": 120.0},
    })
    result = executor.execute_request("assistant_agent", query)
    assert result["token_usage"]["total_tokens"] == 7
    diagnostics = result["injection_diagnostics"]
    # The memory stages (24 ms) plus the scheduler's wait (120 ms).
    assert diagnostics["kernel_overhead_ms"] == pytest.approx(144.0)
    assert diagnostics["kernel_overhead_ms"] == pytest.approx(
        sum(diagnostics[key] for key in SyscallExecutor.KERNEL_STAGES)
        + diagnostics["schedule_wait_ms"]
    )
    assert diagnostics["llm_ms"] == 800.0
    assert diagnostics["schedule_wait_ms"] == 120.0


def test_retrieval_stages_are_timed():
    from tests.modules.memory.test_retrieve_for_agent import (
        AGENT, USER, make_manager, row,
    )

    manager = make_manager([
        row("a", owner="profile_agent", policy="shared"),
    ])
    _, diagnostics = manager.retrieve_for_agent(
        AGENT, USER, "query", k=5, include_shared=True,
    )
    for key in ("barrier_wait_ms", "search_ms", "select_ms"):
        assert diagnostics[key] >= 0


# --- backend calls -----------------------------------------------------


@pytest.fixture
def accumulator():
    fresh = usage.UsageAccumulator()
    callback = usage.install_litellm_logger(fresh)
    yield fresh
    litellm.callbacks.remove(callback)


def backend_call(tag, start, reply):
    """A backend's LLM call made for one trial, as Mem0 makes it."""
    with usage.tagged(tag):
        start.wait()
        litellm.completion(
            model="azure/gpt-4o",
            messages=[{"role": "user", "content": "extract"}],
            mock_response=reply,
        )


def test_backend_calls_count_to_their_trial_under_interleaved_users(
    accumulator,
):
    # Two users' calls run at the same time, three each, interleaved.
    start = threading.Barrier(6)
    threads = [
        threading.Thread(target=backend_call, args=(tag, start, reply))
        for tag, reply in [("alice", "a b c")] * 3 + [("bob", "x")] * 3
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    # A call made with no trial tag (the kernel's own assistant call).
    litellm.completion(
        model="azure/gpt-4o", messages=[{"role": "user", "content": "q"}],
        mock_response="untagged",
    )

    alice = accumulator.take("alice")
    bob = accumulator.take("bob")
    assert len(alice) == 3 and len(bob) == 3
    assert {r["trial_tag"] for r in alice} == {"alice"}
    assert {r["trial_tag"] for r in bob} == {"bob"}
    assert {r["model"] for r in alice + bob} == {"azure/gpt-4o"}
    assert {r["purpose"] for r in alice} == {usage.BACKEND_EXTRACTION}
    summary = usage.summarize(alice, usage.BACKEND_EXTRACTION)
    assert summary["calls"] == 3
    assert summary["total_tokens"] == sum(
        r["prompt_tokens"] + r["completion_tokens"] for r in alice
    ) > 0
    # Reading empties the record; nothing went to an untagged bucket.
    assert accumulator.take("alice", wait=0) == []
    assert accumulator._records == {}


def test_take_waits_for_a_call_still_being_recorded():
    accumulator = usage.UsageAccumulator()
    accumulator.begin("alice", "call-1")

    def finish():
        time.sleep(0.2)
        accumulator.record("alice", usage.BACKEND_EXTRACTION,
                           "azure/gpt-4o", 10, 5, call_id="call-1")

    threading.Thread(target=finish).start()
    records = accumulator.take("alice", wait=5)
    assert [r["prompt_tokens"] for r in records] == [10]


def test_embedding_calls_count_separately_per_trial():
    accumulator = usage.UsageAccumulator()
    client = SimpleNamespace(embed=lambda model, input: {
        "embeddings": [[0.0]], "prompt_eval_count": len(input.split()),
    })
    usage.count_embeddings(client, "nomic-embed-text", accumulator)
    usage.count_embeddings(client, "nomic-embed-text", accumulator)
    with usage.tagged("alice"):
        client.embed(model="nomic-embed-text", input="three word text")
    with usage.tagged("bob"):
        client.embed(model="nomic-embed-text", input="two words")
    client.embed(model="nomic-embed-text", input="untagged")

    alice = accumulator.take("alice")
    assert usage.summarize(alice, usage.EMBEDDING) == {
        "calls": 1, "prompt_tokens": 3, "completion_tokens": 0,
        "total_tokens": 3, "models": ["ollama/nomic-embed-text"],
    }
    assert usage.summarize(alice, usage.BACKEND_EXTRACTION)["calls"] == 0
    assert len(accumulator.take("bob")) == 1
