# Pilot trace proving token usage capture for an Ollama call flows all
# the way onto the Syscall object via the REAL kernel code path.
#
# This mirrors scripts/pilot_token_usage_gpt4o.py but targets a local
# Ollama model. Per the master prompt's ground truth, LiteLLM normalizes
# Ollama's prompt_eval_count / eval_count into the same response.usage
# shape (prompt_tokens / completion_tokens / total_tokens) used by the
# OpenAI path — this script verifies that holds through the real
# model-resolution + completion path.
#
# What is REAL here:
#   - LLMAdapter built with a real "ollama"/llama3.1:8b LLMConfig, which
#     the adapter resolves to the LiteLLM string model
#     "ollama/llama3.1:8b" (the isinstance(model, str) branch that
#     captures usage).
#   - The full, unmocked execute_llm_syscall -> _get_model_response ->
#     set_token_usage chain.
#   - A real LLMSyscall / Syscall and a real Cerebrum LLMQuery.
#   - The actual litellm.completion(...) call against a LIVE local Ollama
#     server (http://localhost:11434). No mocking. If no server is
#     reachable the script reports that and exits non-zero rather than
#     silently faking a result.
#
# What is MOCKED here:
#   - Nothing. This is a live end-to-end call when Ollama is reachable.
#
# Run:  python scripts/pilot_token_usage_ollama.py

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import requests

from aios.llm_core.adapter import LLMAdapter
# Import via aios.syscall.syscall to avoid the partially-initialized
# circular import when aios.syscall.llm is imported first.
from aios.syscall.syscall import LLMSyscall
from cerebrum.llm.apis import LLMQuery

_OLLAMA_HOST = "http://localhost:11434"
_MODEL = "llama3.1:8b"  # real precedent alongside qwen2.5:7b in this repo


def _ollama_reachable() -> bool:
    try:
        r = requests.get(f"{_OLLAMA_HOST}/api/tags", timeout=4)
        r.raise_for_status()
        names = {m["name"] for m in r.json().get("models", [])}
        return _MODEL in names
    except Exception as e:
        print(f"Ollama not reachable / model missing: {e}")
        return False


def main():
    if not _ollama_reachable():
        print(f"SKIP: live Ollama server with '{_MODEL}' not available.")
        sys.exit(1)

    # Build the REAL adapter with a real ollama-backend config.
    adapter = LLMAdapter(
        llm_configs=[
            {"name": _MODEL, "backend": "ollama", "hostname": _OLLAMA_HOST}
        ],
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
        llms=[{"name": _MODEL, "backend": "ollama"}],
        messages=[
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": "In one sentence, what is AIOS?"},
        ],
        action_type="chat",
        max_new_tokens=64,
    )
    syscall = LLMSyscall("pilot_agent", query)

    print("BEFORE call  -> get_token_usage():", syscall.get_token_usage())

    # Run the REAL path against the LIVE Ollama server (no mocking).
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
    msg = getattr(response, "response_message", None)
    print("response_message:", repr(msg))
    print()

    # --- Assertions: non-null, real numbers on the Syscall -------------
    assert usage is not None, "token_usage was not populated!"
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        assert usage.get(k) is not None, f"{k} is None: {usage}"
        assert isinstance(usage[k], int) and usage[k] > 0, \
            f"{k} not a positive int: {usage}"
    assert response.error is None, response.error
    assert response.response_message, "empty response content"

    print("PASS: non-null token usage landed on the Syscall via the real "
          "execute_llm_syscall -> _get_model_response -> set_token_usage "
          "path (LIVE Ollama).")


if __name__ == "__main__":
    main()
