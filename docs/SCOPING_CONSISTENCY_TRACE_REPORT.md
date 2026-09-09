# Write/Read-Back Scoping Consistency — Sparse-Retrieval Investigation (Subtask 3)

Cross-repo trace verifying whether `user_id` → collection scoping is
consistent end-to-end between the write path (subtask 1) and the audit
read-back path (subtask 2), and whether the 63-char collection-name
truncation risk flagged in subtask 1 causes any **real** collision in the
actual trial data. Read-and-cross-reference only — **no code was
modified**. Builds on `MEMORY_WRITE_PATH_TRACE_REPORT.md` (subtask 1,
662d93f) and `MEMORY_COUNT_READ_PATH_TRACE_REPORT.md` (subtask 2,
8f3f7ef).

---

## 1. Write-side and read-side use the SAME collection-name logic

The collection name is derived in exactly **one** place —
`Mem0Provider._collection_name_for_user` (`aios/memory/providers/mem0.py`
~line 341), via `_sanitize_collection_component` — and **both** the write
and the read route through it via the same `_get_client_for_user(user_id)`:

- **Write:** `add_memory` (~line 773) resolves `user_id` from
  `memory_note.metadata["user_id"]`, then `client =
  self._get_client_for_user(user_id)` (~line 859).
- **Read:** `retrieve_memory` (~line 1067) resolves `search_user_id`
  (`params["user_id"]` first), then `client =
  self._get_client_for_user(search_user_id)` (~line 1108).

Cerebrum **never computes a collection name** — it only passes `user_id`
in the query params. Both `add_memory`'s `_resolve_op_user_id` priority
(`params["user_id"]` → `metadata["user_id"]` → default) and
`retrieve_memory`'s `search_user_id` (`params["user_id"]` first) consume
the same field, and the harness passes `trial_data.user_id` verbatim on
both the write (via `ProfileAgent`/`TaskAgent` metadata) and the audit
read (via `_audit_shared_memories` params).

**Determination:** for the same conceptual trial, the write-side and
read-side `user_id` strings are **byte-identical**, and the collection
name is computed by a **single shared function**. There is no independent
second implementation that could drift. Write/read scoping is
**self-consistent by construction** — whatever collection a trial writes
to is exactly the collection its audit reads from (including when that
collection name is a truncated, collided one — see §2).

## 2. Collection-name truncation DOES cause real collisions in the data

Prefix `mem0_memories` (13 chars) ⇒ `max_user_len = 63 − 13 − 1 = 49`.
The sanitized `user_id` is truncated to **49 chars** before the
`mem0_memories_` prefix is prepended.

Applying the exact `_collection_name_for_user` logic to the **453
distinct real `user_id`s** in `kernel.log` (a real
`kernel_shared_adaptive` run):

- Mean `user_id` length **69**, max **82**. **450/453 (99%)** exceed the
  49-char component limit and are truncated.
- The truncation drops exactly the **discriminating tail** of the
  user_id: the `_t<index>__kernel_shared_adaptive` suffix.
- **2 real collision pairs** — distinct trials mapping to one physical
  collection:

  | Collection name (truncated) | Colliding distinct user_ids |
  |---|---|
  | `mem0_memories_alexandra_thompson_adaptive_report_v2_qwen25_7b_t` | `…qwen25_7b_t23__kernel_shared_adaptive` + `…qwen25_7b_t31__kernel_shared_adaptive` |
  | `mem0_memories_emily_rachel_patel_adaptive_report_v2_llama31_8b` | `…llama31_8b_t124__kernel_shared_adaptive` + `…llama31_8b_t76__kernel_shared_adaptive` |

These are **not** the same trial logged twice — they are genuinely
different trials. Confirmed from `kernel.log`:

- `alexandra_thompson…_t23`: profile project **"Weather Forecasting
  System"**, wrote 3 memories (`total_stored_for_user` 1→2→3).
- `alexandra_thompson…_t31`: profile project **"CustomerFeedbackPlatform"**,
  wrote into the **same** collection (`total_stored_for_user` 1→2…).

Because §1 proved write and read share the collection function, the
commingled records are physically in one ChromaDB collection and a read
for either trial's `user_id` routes to that same shared collection. The
per-user `get_all(filters={"user_id": …})` in `retrieve_memory` still
filters rows by the full untruncated `user_id` **value** stored in
metadata, so cross-trial rows are filtered out at the value level even
though they share a collection — but the collision is real at the
physical-collection layer and is a latent correctness/isolation hazard
(and a ChromaDB-side scoping surprise), exactly as subtask 1 predicted.

**Determination:** the truncation risk is **not merely theoretical** — 2
concrete collisions exist in the current run's data. Scope: 2 collided
collections out of 451 (≈0.4% of trials), each merging 2 trials.

## 3. Metadata-field alignment (sharing_policy / owner_agent / user_id) checks out

**Write side** — `build_memory_metadata`
(`cerebrum/example/agents/shared_memory_utils.py`) emits exactly:
`owner_agent`, `user_id`, `memory_type`, `sharing_policy`. `ProfileAgent`
and `TaskAgent` call it with `owner_agent=self.agent_name`
(`profile_agent` / `task_agent`) and `sharing_policy="shared"` when
`share_memory=True`, else `"private"`.

**Read side** — `_apply_sharing_filter` (`aios/memory/providers/base.py`
~line 17) reads `owner_agent`, `user_id`, `sharing_policy` from each
candidate's metadata; `_extract_filter_metadata`
(`aios/memory/providers/mem0.py` ~line 498) merges the Mem0-promoted
top-level `user_id` back into the nested metadata dict so all three keys
are readable from one place.

**Match:** the audit query (`_audit_shared_memories`) fans out with
`agent_name ∈ WRITER_AGENTS = {profile_agent, task_agent}`,
`user_id=trial_user_id`, `sharing_policy="shared"`. In
`_apply_sharing_filter` this hits the **cross-agent-shared** branch
(`user_id is not None and sharing_policy == "shared"`): keep iff
`mem_user == user_id AND mem_policy == "shared"`. Since the writers store
`owner_agent=<same writer>` and `sharing_policy="shared"`, `is_own` is
true and the policy matches. **No metadata-key-name mismatch exists** —
the written keys are exactly the filtered keys, so valid writes are not
being silently excluded by a naming drift.

## 4. Findings (noted, NOT fixed — trace-only subtask)

1. **Real 63-char truncation collisions (2 pairs).** Distinct trials
   commingle in one physical collection when their `user_id`s agree on
   the first 49 sanitized chars. Because the differentiator (`_t<idx>__…`)
   is a **suffix**, and all user_ids share a long common prefix
   (`<name>_adaptive_report_v2_<model>_`), the truncation is
   systematically dropping the only distinguishing part. Row-level
   `user_id` filtering currently masks the impact on retrieval counts,
   but this is a latent isolation bug (and would surface if the row-level
   filter were ever relaxed or if two collided trials shared a name +
   truncation boundary that also aligned on trial index digits).

2. **Read-back is `get_all`, not semantic search (relevant to subtask 2).**
   `retrieve_memory` uses `client.get_all(filters={"user_id": …})`, not a
   similarity search, despite the docstring saying "semantic search."
   Consequently each returned item's `score = item.get("score")` is
   **`None`**. On the Cerebrum side, `_build_retrieval_log_from_search`
   keeps `None`-scored entries (only drops `score < 0.3`), so the 0.3
   relevance threshold identified in subtask 2 **never actually drops
   anything** in these runs. `shared_memory_count` is therefore gated by
   the `sharing_policy=="shared"` + writer-owner filter and the top-`k`
   cutoff, not by relevance — refining subtask 2's explanation for the
   clustering at ~2.

3. **Metadata alignment is correct** — no silent exclusion from key
   naming; the sparse-retrieval symptom is not caused by a
   write/read field-name mismatch.

## 5. Conclusion

`user_id` → collection scoping is **confirmed consistent end-to-end**:
write and read derive the collection via the same single function from a
byte-identical `user_id`, and the `sharing_policy`/`owner_agent`/`user_id`
metadata keys align exactly between writer and audit filter. The 63-char
truncation risk from subtask 1 is **empirically real** — 2 concrete
collision pairs exist in the actual trial data (verified as genuinely
distinct trials via `kernel.log`), though row-level `user_id` filtering
currently prevents those collisions from corrupting retrieval counts. The
sparse-retrieval finding is **not** caused by write/read scope divergence
or a metadata-key mismatch; it remains the structural per-trial-isolation
+ conversation-exclusion effect established in subtasks 1–2, with the
added clarification that read-back is a non-semantic `get_all` so the 0.3
relevance gate is inert.

## 6. Files traced / data cross-referenced (no modifications)

- `aios/memory/providers/mem0.py` — `_resolve_op_user_id`,
  `_sanitize_collection_component`, `_collection_name_for_user`,
  `_get_client_for_user`, `add_memory`, `retrieve_memory`,
  `_extract_filter_metadata`
- `aios/memory/providers/base.py` — `_apply_sharing_filter`,
  `_enrich_metadata`
- `cerebrum/example/agents/shared_memory_utils.py` —
  `build_memory_metadata`, field-name constants
- `cerebrum/example/agents/{profile_agent,task_agent}/agent.py` —
  metadata construction + `create_memory`
- `benchmarks/shared_memory/pipeline.py` — `_audit_shared_memories`
  (`WRITER_AGENTS`, query params), `_build_retrieval_log_from_search`
- `kernel.log` — 453 distinct real `user_id`s; truncation-collision
  empirical test (2 pairs) and per-trial write confirmation for the
  collided `alexandra_thompson` t23/t31 pair
