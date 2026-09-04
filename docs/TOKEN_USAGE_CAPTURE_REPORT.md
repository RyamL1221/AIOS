# Token Usage Capture — Implementation Report

## Summary

The kernel now captures per-call LLM token usage
(`prompt_tokens` / `completion_tokens` / `total_tokens`) at the LiteLLM
call site and lands it on the `Syscall` object as a queryable
`token_usage` field, alongside the existing timing metrics. This makes
token counts available kernel-side without changing the `LLMResponse`
shape or the HTTP payload sent back to Cerebrum.

## Changes

All line numbers reflect the state after the edits below.

### `aios/llm_core/adapter.py`
- **`_get_model_response`** — capture usage in the LiteLLM `str` branch:
  `usage = getattr(response, "usage", None)` immediately after the
  existing `logger.info("Model usage: ...")` line (~line 905). The
  existing log line is untouched.
- **`_get_model_response`** — return type annotation changed to
  `tuple[Union[str, List, Dict], bool, Optional[object]]  #
  (response, finished, usage)` (~line 809); docstring `Returns` updated.
- **`_get_model_response`** — all six return paths now emit a uniform
  3-tuple `(response, finished, usage)`:
  - context-manager path → `..., None` (~line 870)
  - LiteLLM `str`, tools → `return response, True, usage` (~line 923)
  - LiteLLM `str`, no tools → `return message.content, True, usage`
    (~line 926)
  - OpenAI, tool calls → `..., True, None` (~line 941)
  - OpenAI, content → `..., True, None` (~line 944)
  - HfLocalBackend → `return generated_text, True, None` (~line 967)
- **`_get_model_response`** — "Token-usage note" comment block at the
  top of the "Execute Call Based on Model Type" section (~lines
  903–910) documenting that only the LiteLLM branch captures usage and
  the other three paths return `None` intentionally.
- **`execute_llm_syscall`** — unpack the 3-tuple:
  `completed_response, finished, usage = self._get_model_response(...)`
  (~line 743); call `llm_syscall.set_token_usage(usage)` just before
  `return (llm_syscall, processed_response)` (~line 776).

### `aios/syscall/__init__.py` (`Syscall`)
- **`__init__`** — new field `self.token_usage: Optional[dict] = None`
  next to the timing metrics (~line 61).
- **`get_token_usage()`** — returns the field or `None` (~line 276).
- **`set_token_usage(usage)`** — populates a dict of
  `prompt_tokens` / `completion_tokens` / `total_tokens` via
  `getattr(..., None)`; no-ops on `usage is None` (~lines 293–318).

### `tests/modules/syscall/test_token_usage.py` (new)
- `unittest`-based, standalone-runnable. Covers: `set_token_usage(None)`
  no-op, partial/malformed object → partial dict with `None` values,
  `get_token_usage()` clean `None` on a fresh syscall, full-object
  population, and "None call does not clobber prior data". 5 tests, all
  pass. (`tests/modules/syscall/__init__.py` added as package marker.)

### `scripts/pilot_token_usage_gpt4o.py` (new)
- Pilot harness driving the real `execute_llm_syscall` path for a
  GPT-4o (`openai`) config with the network boundary
  (`litellm.completion`) mocked.

### `scripts/pilot_token_usage_ollama.py` (new)
- Pilot harness driving the real `execute_llm_syscall` path for a live
  Ollama (`llama3.1:8b`) call — no mocking.

## Pilot Traces

### GPT-4o (Subtask 5) — network boundary MOCKED

Only `aios.llm_core.adapter.litellm.completion` was patched (no
`OPENAI_API_KEY` / network available). The adapter, syscall, query, and
the entire `execute_llm_syscall → _get_model_response → set_token_usage`
chain are real; the config resolved to the LiteLLM string
`"openai/gpt-4o"`.

```
Resolved model object (self.llms[0]): 'openai/gpt-4o'
BEFORE call  -> get_token_usage(): None
Model usage: Usage(prompt_tokens=41, completion_tokens=15, total_tokens=56)
AFTER call   -> get_token_usage(): {'prompt_tokens': 41, 'completion_tokens': 15, 'total_tokens': 56}
created_time: None | start_time: <ts> | end_time: None
status_code: 200 | error: None | finished: True
response_message: AIOS embeds LLMs into an OS abstraction layer for agents.
```

### Ollama (Subtask 6) — fully LIVE, nothing mocked

Real `litellm.completion(...)` against a live local Ollama server
(`http://localhost:11434`, model `llama3.1:8b`). Config resolved to the
LiteLLM string `"ollama/llama3.1:8b"`. Confirms LiteLLM normalizes
Ollama's `prompt_eval_count`/`eval_count` into the same `response.usage`
shape as OpenAI.

```
Resolved model object (self.llms[0]): 'ollama/llama3.1:8b'
Model usage: Usage(completion_tokens=28, prompt_tokens=29, total_tokens=57, ...)
BEFORE call  -> get_token_usage(): None
AFTER call   -> get_token_usage(): {'prompt_tokens': 29, 'completion_tokens': 28, 'total_tokens': 57}
created_time: None | start_time: <ts> | end_time: None
status_code: 200 | error: None | finished: True
response_message: 'AIOS stands for AI Operations System, a software system designed to
streamline and optimize the use of artificial intelligence across various industries and applications.'
```

## Regression Check

Side-by-side, the only new behavior is `token_usage` going from absent
to populated. Everything else is identical between the two branches.

| Field | GPT-4o (mocked completion) | Ollama (live) | Same? |
|---|---|---|---|
| `get_token_usage()` before | `None` | `None` | ✅ |
| `get_token_usage()` after | `{41, 15, 56}` | `{29, 28, 57}` | ✅ both populated |
| `status_code` | 200 | 200 | ✅ |
| `error` | None | None | ✅ |
| `finished` | True | True | ✅ |
| `response_message` | non-empty, expected | non-empty, coherent | ✅ |
| `start_time` | populated | populated | ✅ |
| `created_time` | None | None | ✅ identical |
| `end_time` | None | None | ✅ identical |

**`created_time` / `end_time` = None artifact (resolved):** these are
stamped by the batch wrapper `execute_llm_syscalls` (plural) and the
`SyscallExecutor`, **not** by `execute_llm_syscall` (singular), which
only calls `set_start_time` (adapter.py ~line 727). Both pilots call the
singular method directly, bypassing the wrapper, so `created_time` /
`end_time` are `None` regardless of the token-usage change. Identical in
both traces → confirmed pre-existing, not introduced here.

## Acceptance Criteria Checklist (master prompt)

- **New `token_usage` field on `Syscall` holding prompt/completion/total,
  next to timing fields** — met (`aios/syscall/__init__.py` `__init__`;
  Subtask 3).
- **Setter populates the field, called from `execute_llm_syscall` with the
  threaded usage** — met (`set_token_usage`, adapter.py ~line 776;
  Subtasks 2–3).
- **Works for both LLM branches (OpenAI + Ollama), non-null real numbers
  via the real path** — met (GPT-4o trace, Subtask 5; live Ollama trace,
  Subtask 6).
- **Graceful None / partial / missing usage handling, no crash** — met
  (Subtask 4 hardening + `tests/modules/syscall/test_token_usage.py`,
  5/5 pass).
- **Flag-off / before-state regression check — no change to response
  content, status, control flow, timing** — met (side-by-side table
  above; Subtask 6).
- **Pilot trace captured with actual numbers, real-vs-mocked explicit** —
  met (both traces above).

## Non-Goals Confirmation

- `LLMResponse`, `LLMQuery`, and all Cerebrum SDK files are **untouched**;
  `usage` rides as a separate local variable and a `Syscall` field, never
  entering the `LLMResponse` the pipeline builds.
- The HTTP response payload shape is **unchanged** — no endpoint,
  `QueryRequest`, or response serialization was modified.
- Scheduling, retry, and error-handling behavior are **unchanged** — the
  `set_token_usage` call is additive at the existing success return; all
  error/exception branches are as before.

## Deviations / Scope Notes

- **3-tuple across all six return paths of `_get_model_response`, not just
  the LiteLLM branch.** Extending the return contract required every
  return path in the function to match the new arity, so the
  context-manager, OpenAI, and HfLocalBackend paths return `usage=None`.
  This keeps the function internally consistent and the single caller's
  unpack (`a, b, c = ...`) valid; it does not capture usage from those
  backends (out of scope) and is documented in-code. `_get_model_response`
  is private with exactly one caller, so no unrelated call sites were
  affected. Within scope.
- **Import-order workaround in the pilot scripts.** Both pilots import
  `LLMSyscall` via `aios.syscall.syscall` instead of `aios.syscall.llm`
  to avoid a pre-existing partially-initialized circular import that
  triggers only when the `llm` submodule is imported first. This is a
  harness detail, not a kernel code change. Within scope.
