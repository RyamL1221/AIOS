# Memory Write-Path Trace — Sparse-Retrieval Investigation (Subtask 1)

AIOS-kernel-side trace of the memory write path during a benchmark
trial. Read-and-trace only — **no kernel code was modified**. This
establishes whether writes happen, whether they succeed, and (since they
do) exactly what scope/collection they land in, feeding subtask 3.

---

## 1. The two write paths

A trial produces memory writes on **two** distinct paths:

**(A) Explicit `create_memory` (ProfileAgent / TaskAgent → SDK → kernel):**
```
SDK create_memory(...)  →  HTTP /query (MemoryQuery, op="add_memory")
  → SyscallExecutor.execute_request / _execute_syscall
      (stamps barrier_seq = barrier.acquire(user_id) for the write)
  → memory queue → FIFOScheduler.process_memory_requests
  → MemoryManager.address_request  [aios/memory/manager.py, op=="add_memory"]
      → _analyze_query_to_memory (preserves metadata: user_id, owner_agent,
        sharing_policy, memory_type)
      → adaptive novelty gate (adaptive_policy.enabled=true) — may REJECT
      → self.provider.add_memory(memory_note)   [Mem0Provider]
      → barrier.release(user_id, barrier_seq, success) in finally
```

**(B) Auto-extract conversation (assistant chat turn):**
```
SyscallExecutor.execute_request  [aios/syscall/syscall.py, LLMQuery chat]
  → execute_llm_syscall (the assistant response)
  → ConversationExtractor.extract_async(agent, user_msg, assistant_msg,
        user_id=resolved_uid)   [aios/memory/conversation_extractor.py]
      → background daemon thread → _store_conversation
      → self.memory_manager.provider.add_memory(memory_note)  [Mem0Provider]
```

Both terminate in `Mem0Provider.add_memory`
(`aios/memory/providers/mem0.py`), which calls `client.add(content,
infer=False, user_id=..., metadata=...)` on a **per-user** Mem0/ChromaDB
client.

## 2. Are writes attempted? Do they succeed? — YES, both.

Confirmed from runtime evidence in `kernel.log` (a real
`kernel_shared_adaptive` run):

- **1,348** `[MEM0_DEBUG] add:` lines — the provider's `client.add()` is
  genuinely invoked.
- Every corresponding `add_memory result: ... success=True,
  memory_id=<uuid>, error=None` — writes succeed with real UUIDs.
- `mem0.vector_stores.chroma - INFO - Inserting 1 vectors into
  collection ...` — vectors actually land in ChromaDB.
- Per-trial pattern (e.g. user `sophia_..._t0`): profile write
  (`total_stored_for_user=1`) → task write (`=2`) → conversation
  write (`=3`), then `barrier.release ... (success)`.

The write barrier does **not** suppress writes: in `address_request` the
`add_memory` branch only *releases* the barrier (never waits). The
barrier gates *retrievals* (`wait_until_drained`), not writes. So the
barrier is not a write-suppression suspect.

## 3. Write scope / location (captured precisely for subtask 3)

For each write, `Mem0Provider` routes to a **per-user_id ChromaDB
collection** via `_get_client_for_user(user_id)` →
`_collection_name_for_user(user_id)`:

- **user_id** (from `MemoryNote.metadata["user_id"]`; for auto-extract,
  the injector's `resolved_user_id`, else `agent_name`): e.g.
  `sophia_ramirez_adaptive_report_v2_gpt4o_t0__kernel_shared_adaptive`.
- **collection name**: `mem0_memories_<sanitized_user_id>`, **truncated
  to 63 chars** and trailing non-alnum stripped
  (`_collection_name_for_user`). Observed:
  `mem0_memories_sophia_ramirez_adaptive_report_v2_gpt4o_t0_kernel`
  — note the truncation drops the `_shared_adaptive` suffix.
- **storage dir**: single shared `PersistentClient` at `.mem0/chroma/`
  (all per-user collections live under it).
- **session identifier**: none used — Mem0 sessions are not used on this
  path; scoping is purely by `user_id` → collection.
- **agent_id**: `default_agent_id` from config (unset here).

## 4. Findings (noted, NOT fixed — trace-only subtask)

1. **Per-trial user_id ⇒ each collection caps at ~3 memories (primary
   lead for the sparse-retrieval finding).** Across 1,348 writes the
   `total_stored_for_user` values are almost perfectly even: **450×
   `=1`, 451× `=2`, 447× `=3`**, and effectively none above 3. Each
   trial uses a fresh per-trial `user_id` (…`_t0`, `_t1`, …), so every
   collection holds exactly the 3 writes of its own trial (profile +
   task + one conversation) and never accumulates history. From the
   benchmark's read-back view this looks like near-empty stores
   (consistent with the reported "zero written_memories,
   shared_memory_count=2"). **Whether this is intended (per-trial
   isolation) or a scoping bug is exactly what subtask 3 must decide** —
   captured here, not judged.

2. **Collection-name truncation to 63 chars can collide across
   user_ids.** Because `user_id`s share a long common prefix and differ
   in a suffix (`…_kernel_shared_adaptive` vs `…_kernel_shared_static`),
   truncation to 63 chars may map *distinct* user_ids to the *same*
   collection name. Not observed causing a collision in this log, but a
   latent scoping risk to check in subtask 3.

3. **ConversationExtractor ignores `add_memory`'s result.**
   `_store_conversation` captures `result = ...add_memory(...)` but never
   inspects `result.success`, then unconditionally logs "Stored
   conversation memory …". A failed conversation write would be reported
   as stored. It also swallows all exceptions (WARNING, never raised).
   Not the cause here (writes succeed), but a silent-failure hazard.

4. **`add_memory` returns `success=True` even when no memory_id is
   returned** — it falls back to `memory_note.id` and only logs a
   WARNING. Success therefore does not strictly prove a distinct
   ChromaDB record; the authoritative signal is the
   `total_stored_for_user` diagnostic (which confirms real storage
   here).

5. **Stray debug instrumentation left in production code.** Both
   `MemoryManager.address_request` and `Mem0Provider.add_memory` write
   to `/tmp/per_user_proof.txt` and `print([PER_USER]…)` on every add.
   Harmless to correctness but should be removed; flagged, not touched.

## 5. Conclusion

Writes are **attempted and succeed** on both paths (explicit
create_memory and auto-extract), committing real vectors to per-user
ChromaDB collections under `.mem0/chroma/`. The write path is **not**
silently failing and the write barrier is **not** suppressing writes.
The most likely explanation for the sparse-retrieval finding is
**scope**, not write failure: each trial writes to its own per-trial
`user_id` collection that only ever holds ~3 records, so retrieval reads
back a near-empty store. That scoping question is handed to subtask 3.

## 6. Files traced (no modifications)

- `aios/syscall/syscall.py` — `execute_request` (chat → extractor call)
- `aios/memory/conversation_extractor.py` — `extract_async`,
  `_store_conversation`
- `aios/memory/manager.py` — `address_request` (`add_memory` branch),
  `_provider_supports_barrier`, `_analyze_query_to_memory`
- `aios/memory/providers/mem0.py` — `add_memory`,
  `_get_client_for_user`, `_collection_name_for_user`,
  `_resolve_op_user_id`
- `aios/config/config.yaml` — provider=mem0, auto_extract/auto_inject
  true, write_barrier enabled, adaptive_policy enabled
- `kernel.log` — runtime evidence (1,348 successful adds)
