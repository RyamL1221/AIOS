# Pilot trace proving token usage capture for a GPT-4o call flows all
# the way onto the Syscall object via the REAL kernel code path.
#
# What is REAL here:
#   - LLMAdapter (built with a real "openai"/gpt-4o LLMConfig, which the
#     adapter resolves to the LiteLLM string model "openai/gpt-4o").
#   - The full, unmocked execute_llm_syscall -> _get_model_response ->
#     set_token_usage chain.
#   - A real LLMSyscall (subclass of the real Syscall) and a real
#     LLMQuery from the Cerebrum SDK.
#
# What is MOCKED here:
#   - ONLY the outbound network boundary: litellm.completion(...) is
#     patched to return a GPT-4o-shaped response object carrying a
#     genuine-shaped Usage (prompt_tokens / completion_tokens /
#     total_tokens). This is because no OPENAI_API_KEY / network is
#     available in this environment. Nothing else in the code path is
#     stubbed — the usage object is threaded by the real adapter code,
#     not handed directly to set_token_usage.
#
# Run:  python scripts/pilot_token_usage_gpt4o.py

import os
import sys
import time
from unittest.mock import patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from aios.llm_core.adapter import LLMAdapter
# Import via aios.syscall.syscall (the module that wires the syscall
# package together) to avoid the partially-initialized circular import
# that occurs when aios.syscall.llm is imported first.
from aios.syscall.syscall import LLMSyscall
from cerebrum.llm.apis import LLMQuery


# --- GPT-4o-shaped mock response objects -------------------------------
# These mirror the structure of a real litellm.completion(...) return
# value for an OpenAI chat completion: .choices[0].message.content and
# .usage.{prompt_tokens,completion_tokens,total_tokens}.

class _MockUsage:
    """Genuine-shaped usage object, matching a real GPT-4o Usage."""
    def __init__(self, prompt_tokens, completion_tokens, total_tokens):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens

    def __repr__(self):
        return (
            f"Usage(prompt_tokens={self.prompt_tokens}, "
            f"completion_tokens={self.completion_tokens}, "
            f"total_tokens={self.total_tokens})"
        )


class _MockMessage:
    def __init__(self, content):
        self.content = content
        self.tool_calls = None


class _MockChoice:
    def __init__(self, content):
        self.message = _MockMessage(content)


class _MockCompletionResponse:
    """Stand-in for the object litellm.completion(...) returns."""
    def __init__(self, content, usage):
        self.choices = [_MockChoice(content)]
        self.usage = usage


# Realistic GPT-4o numbers for a short prompt/response.
_EXPECTED_CONTENT = "AIOS embeds LLMs into an OS abstraction layer for agents."
_EXPECTED_USAGE = _MockUsage(
    prompt_tokens=41,
    completion_tokens=15,
    total_tokens=56,
)


def _fake_litellm_completion(model, **kwargs):
    """Patched replacement for litellm.completion. Asserts it was called
    with the GPT-4o LiteLLM string model, then returns the mock."""
    assert model == "openai/gpt-4o", f"unexpected model routed: {model!r}"
    return _MockCompletionResponse(_EXPECTED_CONTENT, _EXPECTED_USAGE)


def main():
    # A key is not needed since the network boundary is mocked, but the
    # adapter's key-check path logs a warning otherwise. Set a dummy so
    # the trace is clean; it is never used for a real call.
    os.environ.setdefault("OPENAI_API_KEY", "sk-pilot-dummy-not-used")

    # Build the REAL adapter with a real GPT-4o openai-backend config.
    adapter = LLMAdapter(
        llm_configs=[{"name": "gpt-4o", "backend": "openai"}],
        log_mode="console",
        use_context_manager=False,
    )

    # Confirm the adapter resolved the config to the LiteLLM string model,
    # i.e. we will hit the isinstance(model, str) branch that captures usage.
    print("Resolved model object (self.llms[0]):", repr(adapter.llms[0]))
    print("available_llm_names:", adapter.available_llm_names)
    print()

    # Build a REAL LLMSyscall wrapping a REAL LLMQuery.
    query = LLMQuery(
        llms=[{"name": "gpt-4o", "backend": "openai"}],
        messages=[
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": "In one sentence, what is AIOS?"},
        ],
        action_type="chat",
        max_new_tokens=64,
    )
    syscall = LLMSyscall("pilot_agent", query)

    # Sanity: before the call, token_usage must be the clean default.
    print("BEFORE call  -> get_token_usage():", syscall.get_token_usage())

    # Patch ONLY the network boundary, then run the REAL path.
    with patch(
        "aios.llm_core.adapter.litellm.completion",
        side_effect=_fake_litellm_completion,
    ):
        returned_syscall, response = adapter.execute_llm_syscall(
            model_idx=0,
            llm_syscall=syscall,
        )

    # --- Trace output --------------------------------------------------
    usage = returned_syscall.get_token_usage()
    print("AFTER call   -> get_token_usage():", usage)
    print()
    print("--- Timing fields (for comparison / control-flow sanity) ---")
    print("created_time:", returned_syscall.get_created_time())
    print("start_time:  ", returned_syscall.get_start_time())
    print("end_time:    ", returned_syscall.get_end_time())
    print()
    print("--- Response content (control-flow / content sanity) ---")
    print("status_code:", getattr(response, "status_code", None))
    print("error:      ", getattr(response, "error", None))
    print("finished:   ", getattr(response, "finished", None))
    print("response_message:", getattr(response, "response_message", None))
    print()

    # --- Assertions: non-null, real numbers on the Syscall -------------
    assert usage is not None, "token_usage was not populated!"
    assert usage["prompt_tokens"] == 41, usage
    assert usage["completion_tokens"] == 15, usage
    assert usage["total_tokens"] == 56, usage
    # The setter must be reached via the real path, and content must be
    # the mocked completion content (proves we did not alter response
    # handling / control flow).
    assert response.response_message == _EXPECTED_CONTENT, response.response_message
    assert response.error is None, response.error

    print("PASS: non-null token usage landed on the Syscall via the real "
          "execute_llm_syscall -> _get_model_response -> set_token_usage path.")


if __name__ == "__main__":
    main()
