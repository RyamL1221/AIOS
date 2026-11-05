"""Decoding settings reach the model call (NeurIPS Subtask 9d).

The ``/query`` handler drops ``LLMQuery.temperature``, so decoding rides
on the request's ``llms`` entry. These tests drive
``LLMAdapter.execute_llm_syscall`` with LiteLLM mocked and check the
temperature and seed in the completion call, and that the syscall
records what it used for the response envelope.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from cerebrum.llm.apis import LLMQuery

from aios.llm_core.adapter import LLMAdapter
from aios.llm_core.decoding import decoding_for


def test_decoding_for_reads_the_matching_entry():
    llms = [
        {"name": "gpt-4o", "backend": "azure", "temperature": 0.0,
         "seed": 7},
        {"name": "qwen2.5:7b", "backend": "ollama", "temperature": 0.3},
    ]
    assert decoding_for(llms, "gpt-4o") == {"temperature": 0.0, "seed": 7}
    assert decoding_for(llms, "qwen2.5:7b") == {"temperature": 0.3}
    assert decoding_for(llms, "llama3.1:8b") == {}
    assert decoding_for(None, "gpt-4o") == {}
    assert decoding_for([{"name": "x", "seed": None}], "x") == {}


def _adapter(model_name: str, identifier: str) -> LLMAdapter:
    adapter = LLMAdapter.__new__(LLMAdapter)
    adapter.llm_configs = [SimpleNamespace(name=model_name, hostname=None)]
    adapter.llms = [identifier]
    adapter.use_context_manager = False
    adapter.context_manager = None
    return adapter


class _Syscall(SimpleNamespace):
    def set_status(self, status):
        self.status = status

    def set_start_time(self, value):
        self.start = value

    def set_token_usage(self, usage):
        self.usage = usage


def _completion(content="ok"):
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)], usage=None,
    )


def _run(adapter, llms, temperature=1.0):
    query = LLMQuery(messages=[{"role": "user", "content": "hi"}],
                     llms=llms, temperature=temperature)
    syscall = _Syscall(query=query)
    with patch("aios.llm_core.adapter.litellm.completion",
               MagicMock(return_value=_completion())) as completion:
        _, response = adapter.execute_llm_syscall(0, syscall)
    assert response.response_message == "ok", response
    return completion.call_args.kwargs, syscall


def test_temperature_and_seed_from_the_llms_entry_reach_ollama():
    adapter = _adapter("qwen2.5:7b", "ollama/qwen2.5:7b")
    kwargs, syscall = _run(adapter, [{
        "name": "qwen2.5:7b", "backend": "ollama",
        "temperature": 0.0, "seed": 20261105,
    }])
    assert kwargs["model"] == "ollama/qwen2.5:7b"
    assert kwargs["temperature"] == 0.0
    assert kwargs["seed"] == 20261105
    assert syscall.decoding == {"temperature": 0.0, "seed": 20261105}


def test_temperature_and_seed_reach_azure():
    adapter = _adapter("gpt-4o", "azure/gpt-4o")
    kwargs, _ = _run(adapter, [{
        "name": "gpt-4o", "backend": "azure", "temperature": 0.0, "seed": 3,
    }])
    assert (kwargs["temperature"], kwargs["seed"]) == (0.0, 3)


def test_without_decoding_the_query_temperature_and_no_seed_apply():
    adapter = _adapter("qwen2.5:7b", "ollama/qwen2.5:7b")
    kwargs, syscall = _run(
        adapter, [{"name": "qwen2.5:7b", "backend": "ollama"}],
    )
    assert kwargs["temperature"] == 1.0
    assert "seed" not in kwargs
    assert syscall.decoding == {"temperature": 1.0, "seed": None}


def test_the_envelope_carries_the_decoding():
    """The /query response gets the decoding as a sibling of
    ``response``, as ``token_usage`` is."""
    import aios.syscall.syscall as module
    from aios.syscall.llm import LLMSyscall

    query = LLMQuery(messages=[{"role": "user", "content": "hi"}])

    def scheduled(sc):  # the scheduler and the model call, in one step
        sc.set_start_time(sc.get_created_time())
        sc.set_end_time(sc.get_created_time())
        sc.set_response("ok")
        sc.set_status("done")
        sc.decoding = {"temperature": 0.0, "seed": 5}

    executor = module.SyscallExecutor()
    with patch.object(module, "global_llm_req_queue_add_message",
                      scheduled), \
         patch.object(LLMSyscall, "start", lambda self: None), \
         patch.object(LLMSyscall, "join", lambda self, *a: None):
        result = executor._execute_syscall("agent", query)
    assert result["response"] == "ok"
    assert result["decoding"] == {"temperature": 0.0, "seed": 5}
