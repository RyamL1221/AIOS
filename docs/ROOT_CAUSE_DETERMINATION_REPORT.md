# Root-Cause Determination — Sparse-Retrieval Investigation (Subtask 5)

Runnable, isolated reproduction of the two distinct defects behind the
original "sparse-memory-retrieval" finding, plus the final root-cause
**category determination**. Reproduction only — **no fixes applied** (per
the master prompt's "do not fix anything yet" instruction). Builds on
subtasks 1–4 (662d93f, 8f3f7ef, 4ab8a9c, 199ca10).

Reproduction script: `scripts/reproduce_truncation_collision_and_sparse_metrics.py`
(commit 8ad2b6e). It drives the **real** `Mem0Provider` (real ChromaDB
`PersistentClient` + Ollama `nomic-embed-text` embedder) in a throwaway
temp directory — nothing touches the project's `.mem0/chroma` store.

Run (from the AIOS repo root, using the Cerebrum venv that has the
editable `cerebrum` SDK; the script direct-loads `mem0.py` to skip the
`providers/__init__` → in-house → `sentence_transformers` chain the Mem0
path does not need):

```
PYTHONPATH="$PWD:/…/Cerebrum" /…/Cerebrum/.venv/bin/python \
    scripts/reproduce_truncation_collision_and_sparse_metrics.py
```

---

## 1. Two findings, reproduced independently

### Part A — 63-char truncation collision → real data commingling (PASS)

Reused the two REAL colliding user_ids from subtask 3 (qwen25_7b t23 vs
t31). Key captured output:

```
UID_A = 'alexandra_thompson_adaptive_report_v2_qwen25_7b_t23__kernel_shared_adaptive'  (len 75)
UID_B = 'alexandra_thompson_adaptive_report_v2_qwen25_7b_t31__kernel_shared_adaptive'  (len 75)
collection(UID_A) = 'mem0_memories_alexandra_thompson_adaptive_report_v2_qwen25_7b_t'  (len 63)
collection(UID_B) = 'mem0_memories_alexandra_thompson_adaptive_report_v2_qwen25_7b_t'  (len 63)
(a) SAME collection name?  True
    same Memory client object? False
[MEM0_DEBUG] add: user_id=…t23…, memory_id=…, total_stored_for_user=1
[MEM0_DEBUG] add: user_id=…t31…, memory_id=…, total_stored_for_user=1
(b) rows physically in collection 'mem0_memories_…qwen25_7b_t': 2
    distinct user_ids co-resident in that ONE collection:
        - alexandra_thompson_…_t23__kernel_shared_adaptive
        - alexandra_thompson_…_t31__kernel_shared_adaptive
(c) COMMINGLING (>1 distinct identity in one collection)? True
[MEM0_DEBUG] retrieve(get_all): user_id=…t23…, result_count=1
    retrieve_memory(user_id=UID_A) returned 1 rows; user_ids in result: ['…t23…']
PART A result: REPRODUCED  (same_collection_name=True, distinct_clients_share_physical_collection=True)
```

**Mechanism (precise, from the run):** the two identities get **distinct**
per-user `Memory` clients (`_user_clients` is cached by the *full*
untruncated user_id — "same Memory client object? False"), but both
clients are handed the **same 63-char-truncated `collection_name`** and
the **same shared `PersistentClient`**, so they bind to **one physical
ChromaDB collection**. A raw `get_collection(name).get()` returns **both**
identities' rows (2 rows, both user_ids) — genuine data commingling at
the physical-collection layer, not just a name clash. This is the
"teeth-check" beyond name matching the subtask required.

Note each per-client `total_stored_for_user=1` and the `retrieve_memory`
returning only 1 row: mem0's `get_all(filters={"user_id": <full value>})`
filters by the untruncated user_id **value** within the shared
collection, which currently **masks** the commingling at retrieval time
(the subtask-3 observation, now reproduced). The masking is incidental,
not a safeguard — the physical isolation invariant is already broken.

### Part B — sparse metrics (written_memories≈0 / shared_memory_count≈2) (PASS)

Three per-trial-isolated identities, each written exactly as the harness
does (profile + task as `shared`; conversation as the kernel's
auto_extract writes it — owner `assistant_agent`, `private`). Captured:

```
  trial 0: total_stored_for_user=3  shared_memory_count=2  owners=[('profile_agent','profile'),('task_agent','task_context')]
  trial 1: total_stored_for_user=3  shared_memory_count=2  owners=[('profile_agent','profile'),('task_agent','task_context')]
  trial 2: total_stored_for_user=3  shared_memory_count=2  owners=[('profile_agent','profile'),('task_agent','task_context')]
  total_stored distribution: [3, 3, 3] (each trial writes 3)
  shared_memory_count distribution: [2, 2, 2]
  conversation memory (owner=assistant_agent) EXCLUDED from audit? True
  shared_memory_count capped at 2 despite 3 stored? True
PART B result: REPRODUCED
```

This confirms subtask 2's structural explanation exactly: all three
memories are physically stored (`total_stored=3`), but the harness audit
counts only `sharing_policy=="shared"` writer-owned memories, so the
`conversation` memory (owner `assistant_agent`, private) is excluded and
`shared_memory_count` caps at **2** — not a stale/failed read, and not a
different unexplained cause. (Subtask 3 additionally showed the 0.3
relevance gate is inert because retrieval is `get_all`, so it plays no
role here; the cap is purely the owner + sharing_policy filter.)

`written_memories≈0` in the finalized results is the same structural
effect at the client layer (subtask 2): it is a capture of client-issued
`create_memory` intent, and in the finalized runs it was empty/omitted;
it is not evidence of a read failure.

## 2. Final root-cause category determination

Per the master prompt's categories — **harness read-back bug**, **kernel
write bug**, **scoping mismatch**, or **expected-but-undocumented
behavior** — the honest answer is **two separate findings, two
categories**:

### Finding 1 — the sparse numbers (`written_memories≈0`, `shared_memory_count≈2`)
**Category: EXPECTED-BUT-UNDOCUMENTED behavior.**
- Writes succeed on all paths (subtask 1); read-back is correctly
  per-trial-scoped and post-write (subtask 2); user_id derivation and
  metadata keys align write↔read (subtask 3); per-trial isolation is the
  intended design and cross-trial accumulation was never intended
  (subtask 4, paper + `benchmark-memory-isolation-v2` spec).
- The numbers are a **definitional artifact**: `shared_memory_count`
  counts shared writer-owned retrieval hits, which structurally excludes
  the private `conversation` memory (cap 2 of 3), and `written_memories`
  is a client-intent log. Reproduced deterministically in Part B.
- **Not** a read-back bug, **not** a write bug, **not** a scoping
  mismatch. It is correct behavior that is merely **undocumented /
  easily-misread as a defect** — the metric name oversells what it
  measures.

### Finding 2 — the 63-char truncation collision
**Category: SCOPING BUG (kernel-side, `Mem0Provider`).**
- Distinct trial identities whose sanitized user_id agrees on the first
  49 chars are truncated to one `collection_name` and bound to one
  physical ChromaDB collection (Part A), violating the "one user_id = one
  isolated namespace" invariant documented in AIOS
  `mem0-user-id-scoping` (subtask 4).
- This is a genuine latent defect in `_collection_name_for_user` /
  `_get_client_for_user`, currently **masked** by the untruncated
  `user_id`-value filter in `get_all`, so it does not corrupt the
  reported metrics today — but it is real, reproduced against the live
  provider, and independent of Finding 1.

These do **not** collapse into one root cause. Finding 1 explains the
original sparse-retrieval numbers (and clears them as expected). Finding
2 is a separate isolation bug surfaced during the investigation that must
be reported and fixed on its own merits.

## 3. No fixes applied

Per instruction, nothing was fixed: the truncation logic, the metric
definitions, and the harness audit are all untouched. The reproduction
script is additive (new file under `scripts/`) and self-cleans its temp
ChromaDB directory. Reproduction output and category calls are captured
here for subtask 6.

## 4. Artifacts

- `scripts/reproduce_truncation_collision_and_sparse_metrics.py` (8ad2b6e)
  — runnable reproduction (Parts A + B), real provider, temp store.
- Subtask reports: `MEMORY_WRITE_PATH_TRACE_REPORT.md` (662d93f),
  `MEMORY_COUNT_READ_PATH_TRACE_REPORT.md` (8f3f7ef),
  `SCOPING_CONSISTENCY_TRACE_REPORT.md` (4ab8a9c),
  `TRIAL_ISOLATION_INTENT_REPORT.md` (199ca10).
