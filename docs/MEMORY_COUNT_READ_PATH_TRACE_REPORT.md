# Memory Count/Read-Path Trace — Sparse-Retrieval Investigation (Subtask 2)

Cerebrum-harness-side trace of where `written_memories` and
`shared_memory_count` are computed for a benchmark trial, and whether
each is a live per-trial-scoped read of the same ChromaDB collection the
write path uses (subtask 1) or something stale/cached/differently
scoped. Read-and-trace only — **no Cerebrum or AIOS code was modified**.
Pairs with `MEMORY_WRITE_PATH_TRACE_REPORT.md` (subtask 1) and feeds
subtask 3.

---

## 1. `written_memories` — captured from the write call, not a read

**Computed in:** `benchmarks/shared_memory/pipeline.py`,
`AgentPipeline.run_trial` via the nested `capturing_create_memory`
closure (~lines 97–113), collected into `written_records`, set on
`PipelineResult.written_memories` (line 193), then copied verbatim onto
`TrialResult.written_memories` in `benchmarks/shared_memory/run_evaluation.py`
`run_single_trial` (line 586).

**Mechanism:** the pipeline monkeypatches
`cerebrum.memory.apis.create_memory` with `unittest.mock.patch(...)` for
the duration of the three agent runs. Each `create_memory(agent_name,
content, metadata=...)` call appends a `WrittenMemoryRecord` built **from
the `metadata` dict the agent passed into the write**, then calls through
to the real function:

```python
def capturing_create_memory(agent_name, content, metadata=None, base_url=None):
    if metadata:
        written_records.append(WrittenMemoryRecord(
            agent_name=metadata.get("owner_agent", agent_name),
            memory_type=metadata.get("memory_type", ""),
            sharing_policy=metadata.get("sharing_policy", "private"),
            user_id=metadata.get("user_id", ""),
        ))
    return _real_create_memory(agent_name, content, metadata=metadata, base_url=base_url)
```

**Source classification: (b)/intent-log — NOT a read of the collection.**
It records what the harness *asked to write*, regardless of whether/where
AIOS stored it. It captures **only explicit `create_memory` calls**
(ProfileAgent + TaskAgent). It does **not** capture the kernel's
`auto_extract` conversation write (that happens kernel-side during the
assistant's `llm_chat`, never through the patched client function). So
`written_memories` structurally lists **2** records (profile + task) and
never the 3rd conversation memory.

## 2. `shared_memory_count` — two possible sources; in real runs it is a live post-write relevance-gated retrieval

**Computed in:** `benchmarks/shared_memory/pipeline.py`. `run_trial`
(~lines 165–185) chooses one of two paths:

- **Path A — inline kernel diagnostics** (`_retrieval_log_from_diagnostics`,
  line 257): `shared_memory_count = diagnostics.injected_count`, read
  inline from the assistant's own `llm_chat` response. Source (b).
  **Per subtask 3, this path fired in 0 real trials.**
- **Path B — audit fallback** (`_audit_shared_memories` →
  `_build_retrieval_log_from_search`, ~lines 265–465): used when
  diagnostics are absent/zero. **Per subtask 3, this produced 100% of the
  real `shared_memory_count` values (`injection_status="audit_inferred"`
  for 150/150 trials in every results file).**

**What Path B actually does (the crux):**

1. It runs **after** `assistant_agent.run(...)` returns (the audit is in
   the `else` branch following the assistant call), so it is a **post-write**
   read — the trial's profile/task writes are already issued. It is **not**
   a pre-write/mid-write/stale snapshot.
2. It is a **live, per-trial-scoped query**:
   `MemoryQuery(operation_type="retrieve_memory", params={"content": query_text,
   "k": 20, "user_id": user_id, "sharing_policy": "shared",
   "agent_name": writer_agent})` with `user_id = trial_data.user_id` — the
   **same fresh per-trial user_id the write path used**. Scope is correct:
   same per-trial collection the writes landed in.
3. **But it is a relevance-ranked retrieval, not a count of stored rows.**
   It queries by `content=follow_up_query`, then
   `_build_retrieval_log_from_search` drops any entry with
   `score < RELEVANCE_THRESHOLD (0.3)` and increments `shared_count`
   **only for entries whose `metadata.sharing_policy == "shared"`**
   (pipeline.py line 438).
4. The fan-out iterates `WRITER_AGENTS = ["profile_agent", "task_agent"]`
   only (~line 262). **AssistantAgent is never queried**, so the
   conversation memory is doubly excluded — by owner scope and by the
   `sharing_policy == "shared"` filter (auto-extracted conversation
   memories aren't tagged `shared`).

**Source classification: live per-trial-scoped read — but of relevance-gated,
shared-tagged, writer-owned retrieval hits, NOT `total_stored_for_user`.**

## 3. Reconciliation with subtask 1 (the `2` vs `3` question)

Subtask 1's `total_stored_for_user` distribution (**450×1, 451×2,
447×3**) counts **all** rows in the per-trial collection — profile + task
+ auto-extracted conversation. `shared_memory_count` cannot reach that
top end, for reasons that are **structural in the harness code**, not
retrieval flakiness or a stale read:

- **The conversation memory is categorically excluded.** It is written
  kernel-side by `auto_extract` (not via the patched `create_memory`), it
  is owned by `assistant_agent` (not in `WRITER_AGENTS`), and it is not
  tagged `sharing_policy="shared"`. Each of those three independently
  removes it from `shared_count`, capping `shared_memory_count` at **2**
  (profile + task) by construction. Clustering at ~2 rather than 3 is
  therefore **expected** and does not require a pre-write/mid-write read
  to explain.
- **Variance below 2** (trials at 0 or 1) is attributable to Path B being
  a **relevance-thresholded top-k retrieval**: a profile/task memory that
  scores below 0.3 against the follow-up query, or isn't returned in the
  fan-out, is not counted even though it is stored.

The earlier hypothesis ("reading a pre-write or mid-write count") is
**disconfirmed**: the read is correctly ordered after the writes and
correctly scoped to the per-trial `user_id`. The clustering near 2 is
explained by **what is counted** (relevance-gated, shared-tagged,
writer-owned retrieval hits) versus **what subtask 1 counted** (all stored
rows including the shared-excluded conversation memory).

## 4. Findings (noted, NOT fixed — trace-only subtask)

1. **`shared_memory_count` conflates "retrieved & relevant" with "stored."**
   For a field named like a count of shared memories, it silently applies
   a 0.3 relevance gate and a `sharing_policy == "shared"` filter, so it
   can never equal the collection's stored total. Describing it as "number
   of shared memories" in the paper is imprecise — it is "number of shared
   writer-owned memories that passed the audit retrieval's relevance
   threshold for this query."

2. **The conversation memory is structurally invisible to both fields.**
   `written_memories` misses it (kernel-side write) and
   `shared_memory_count` excludes it (owner + sharing_policy). Any
   narrative implying these fields reflect the full 3-write per-trial
   state is wrong.

3. **`written_memories` is a client-intent log, not collection evidence.**
   It proves the harness issued the write, not that AIOS stored it, and
   should not be cited as storage confirmation (subtask 1's
   `total_stored_for_user` is the authoritative storage signal).

4. **Path A vs Path B divergence is undocumented in the output.** Both
   write into the same `shared_memory_count` field but mean different
   things (kernel-injected count vs harness audit-retrieval count). Only
   `injection_status` distinguishes them, and subtask 3 shows it is always
   `audit_inferred`, i.e. always the retrieval-count meaning.

## 5. Conclusion

Both `written_memories` and `shared_memory_count` are **correctly scoped
to the per-trial `user_id`** and are **not stale/cached**:
`written_memories` is a client-side intercept of the outbound write
intent, and `shared_memory_count` (in 100% of real runs) is a live
post-write retrieval against the same per-trial collection the writes
landed in. The reason `shared_memory_count` clusters near **2** rather
than matching subtask 1's up-to-**3** stored distribution is
**structural, not a read-timing bug**: the auto-extracted conversation
memory is excluded by owner scope and sharing-policy filter, and the
remaining profile/task hits are further gated by a 0.3 relevance
threshold. The sparse-retrieval symptom is a write-vs-read **semantics/scope
mismatch**, consistent with subtask 1's per-trial-isolation lead — not a
failed or stale read on the Cerebrum side.

## 6. Files traced (no modifications)

- `benchmarks/shared_memory/pipeline.py` — `AgentPipeline.run_trial`,
  `capturing_create_memory`, `_audit_shared_memories`,
  `_build_retrieval_log_from_search`, `_retrieval_log_from_diagnostics`,
  `WRITER_AGENTS`, `RELEVANCE_THRESHOLD`
- `benchmarks/shared_memory/run_evaluation.py` — `run_single_trial`
  (field assignment onto `TrialResult`)
- `benchmarks/shared_memory/models.py` — `WrittenMemoryRecord`,
  `RetrievalLog` (`shared_memory_count`), `TrialResult`, `PipelineResult`
- Cross-referenced: `MEMORY_WRITE_PATH_TRACE_REPORT.md` (subtask 1) —
  write scope + `total_stored_for_user` distribution (450×1 / 451×2 /
  447×3)
