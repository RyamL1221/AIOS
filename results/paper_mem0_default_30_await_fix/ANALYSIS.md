# MEM0_DEBUG Diagnostic Extraction — 30-Trial Run

## Source

- **Log file**: `kernel.log` (project root)
- **Run period**: 2026-06-28 13:29:57 → 13:40:43 (~11 minutes)
- **[MEM0_DEBUG] lines present**: **NO** — the diagnostic logging was added AFTER this run

## What's Available

The kernel.log contains standard INFO-level logs. Extracted into
`mem0_debug_lines.txt` (210 lines):

| Category | Count | Description |
|----------|-------|-------------|
| `op=add_memory` | 60 | 2 adds per trial × 30 trials |
| `op=retrieve_memory` | 30 | 1 retrieve per trial × 30 trials |
| `Registered user_id` | 60 | One per add (user_id discovery) |
| `uid_from_metadata` | 60 | Manager-level add diagnostics |
| `not searchable` warnings | 0 | No timeout logged |
| `failed while checking` errors | 0 | No get_all errors logged |
| `retrieve_memory without user_id` warnings | 0 | All retrievals had user_id |

## Key Observations

### 1. Config: auto_inject=False, auto_extract=False
The personalization pipeline (ContextInjector/ConversationExtractor) is
**disabled**. Memory operations in this benchmark are **explicit SDK
calls** (`create_memory` + `search_memories`), not auto-injection.

### 2. Timing: No _await_searchable Timeout
Each trial's 3 operations (add, add, retrieve) complete in <400ms.
This means `_await_searchable` is either:
- Succeeding quickly (memory immediately visible), or
- The run used code before `_await_searchable` was added, or
- The run used a mem0 version that accepted `get_all(user_id=...)` top-level kwargs

### 3. All 30 Retrievals Had Correct user_id
The `metadata_user_id` field in the log shows a valid user_id for
every retrieve operation. The log extraction fix (subtask 2) is
confirmed working.

### 4. 24 Unique Users Across 30 Trials
Some users appear in multiple trials (sophia_martinez: 5 times).

### 5. No Errors or Warnings
Only a benign Redis connection error (mem0 telemetry). No memory-
related failures were logged at INFO/WARNING/ERROR level.

## What We Cannot Determine (Missing [MEM0_DEBUG])

Without the diagnostic logging, we cannot determine from this log:

- ❓ How many results `client.search()` returned per trial
- ❓ Whether `get_all()` found memories when search() returned 0
- ❓ The total memory count per user after each add
- ❓ Whether mem0's scoring threshold filtered valid results

## Next Steps

To get the `[MEM0_DEBUG]` diagnostic data, the benchmark must be
re-run with the current code (which includes the logging). The
diagnostic lines will then appear in kernel.log with:

```
[MEM0_DEBUG] add: user_id=..., content='...', memory_id=..., total_stored_for_user=N
[MEM0_DEBUG] search: user_id=..., query='...', top_k=K, raw_result_count=N
[MEM0_DEBUG] search returned 0 but get_all(user_id=...) found N memories.
```
