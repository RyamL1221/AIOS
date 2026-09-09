# Sparse-Memory-Retrieval Investigation — Synthesis & Recommendation

Final deliverable for the sparse-memory-retrieval investigation. This
report synthesizes subtasks 1–5 in one place (not by reference only),
lands the two-category root-cause determination, names a proposed (not
implemented) fix for the scoping bug, and gives a concrete, actionable
recommendation on the original question: **proceed with the
`kernel_shared_adaptive` re-run as-is, or change the experiment design
first?**

**Scope boundary (carried forward from the master prompt):** this
investigation is trace / reproduce / recommend only. **No fix has been
implemented and no re-run has been started.** Implementing a fix or
launching the re-run is a separate follow-up task and is explicitly *not*
started here.

---

## 1. The original finding

A `kernel_shared` / `kernel_shared_adaptive` run read back near-empty
memory: `written_memories` ≈ 0 and `shared_memory_count` ≈ 2 per trial,
which looked like memory writes were failing or retrieval was broken. The
investigation split into: does memory get written? read back? at the
right scope? is per-trial isolation intended? — then reproduced the
mechanics in isolation.

## 2. Two findings, two categories

The honest result is **two distinct findings** with **two different
categories** — they must not be collapsed into one "bug."

### Finding 1 — the sparse numbers are EXPECTED-BUT-UNDOCUMENTED behavior

**Reasoning chain (subtasks 1→4):** (1) Writes are **attempted and
succeed** on both paths — explicit `create_memory` (profile/task) and
kernel `auto_extract` (conversation) — committing real vectors to
per-user ChromaDB collections; `total_stored_for_user` reaches 3 per
trial (subtask 1). (2) The harness read-back is a **live, post-write,
per-trial-scoped** query, not a stale/cached read; `written_memories` is
a client-side capture of *write intent* (misses the kernel-side
conversation write), and `shared_memory_count` counts only
`sharing_policy=="shared"`, writer-owned retrieval hits (subtask 2). (3)
Write-side and read-side derive the same collection from a byte-identical
`user_id`, and the `owner_agent`/`user_id`/`sharing_policy` metadata keys
align exactly between writer and audit filter — no scope or key mismatch
(subtask 3). (4) Per-trial isolation is the **intended design**: the
paper defines "shared" as within-trial cross-agent visibility and each
trial as a self-contained synthetic identity, and the
`benchmark-memory-isolation-v2` spec scopes the shared `user_id` "within
a single Trial"; cross-trial accumulation was never intended (subtask 4).
**Therefore** the numbers are a *definitional artifact*: 3 memories are
stored but the audit counts only the 2 shared writer-owned ones (the
private `conversation` memory, owned by `assistant_agent`, is excluded),
so `shared_memory_count` caps at 2 — reproduced deterministically
(`[2,2,2]` with `total_stored=[3,3,3]`) in subtask 5, Part B. This is
correct behavior; it is merely undocumented and the metric name oversells
what it measures. **Category: expected-but-undocumented — not a
read-back bug, not a write bug, not a scoping mismatch.**

### Finding 2 — the 63-char truncation collision is a REAL scoping bug

**Reasoning chain (subtasks 3 & 5):** ChromaDB collection names are
capped at 63 chars. With prefix `mem0_memories` (13 chars) the sanitized
`user_id` is truncated to 49 chars before the prefix is prepended. In the
real adaptive run, all trial user_ids share a long common prefix
(`<name>_adaptive_report_v2_<model>_`) and differ only in a **suffix**
(`_t<idx>__kernel_shared_adaptive`) — exactly the part truncation drops.
Empirically, **450/453 (99%)** user_ids are truncated, and **2 collision
pairs** result — distinct trials (verified different profiles/projects)
mapping to one collection name (subtask 3). Subtask 5 reproduced the
*teeth*: driving the real `Mem0Provider`, the two colliding identities
get **distinct** per-user Memory clients (cached by full user_id) but
both are handed the **same truncated `collection_name`** on the **same
shared `PersistentClient`**, so they bind to **one physical ChromaDB
collection** — a raw read of that collection returns **both** identities'
rows (genuine commingling, not just a name clash). It is **currently
masked** at retrieval time only because mem0's
`get_all(filters={"user_id": <full value>})` re-filters by the
untruncated user_id value. This violates the "one `user_id` = one
isolated namespace" invariant documented in AIOS `mem0-user-id-scoping`.
**Category: scoping bug, kernel-side (`Mem0Provider`).**

## 3. Proposed fix for Finding 2 (NAMED, NOT IMPLEMENTED)

The fix belongs in `aios/memory/providers/mem0.py`,
`_collection_name_for_user` (and consumed by `_get_client_for_user`).
Options to choose between later — **not decided or implemented here**:

- **(a) Hash-suffix the truncated component.** Replace the naive
  `[:max_user_len]` truncation with `truncated_prefix + short_hash(full
  user_id)` (e.g. a 8–10 char hex of a SHA-1/blake2 of the full user_id),
  fitting within 63 chars. Preserves 1:1 user_id→collection mapping with
  negligible collision probability; readable prefix retained for
  debugging. Most robust.
- **(b) Use a shorter deterministic identifier.** Map each full user_id
  to a compact deterministic id (e.g. `mem0_<hash>`), dropping the
  human-readable prefix entirely. Simplest and collision-safe, at the
  cost of collection-name readability.
- **(c) Detect and raise/log on collision.** Keep current naming but,
  when a to-be-created collection name is already bound to a *different*
  full user_id, raise or loudly warn rather than silently sharing.
  Lowest-effort safety net; does not by itself restore isolation, so best
  as a guard combined with (a) or (b).

Recommended default if/when a fix is authorized: **(a)** — it restores
the documented isolation invariant with minimal behavioral change and
keeps collections debuggable. (Decision deferred to the follow-up task.)

## 4. Recommendation on the `kernel_shared_adaptive` re-run

**Recommendation: the sparse numbers do NOT block a re-run; the
truncation collision does NOT block it either at its measured magnitude,
but SHOULD be fixed first as a cheap, low-risk precondition — proceed
only after applying fix option (a)/(b), or knowingly accept a ~0.9%
contaminated-identity rate if re-running immediately.**

Reasoning from both findings together:

- **Finding 1 is not a blocker.** The sparse numbers are expected; a
  re-run will reproduce them and they don't indicate broken memory. If
  anything, the metric should be *documented/renamed* (out of scope
  here), not "fixed" before re-running.
- **Finding 2 is a real but small-magnitude contaminant.** In the actual
  450-trial adaptive run, **4 of 453 identities (0.88%) across 2
  collections** collided. Impact is further limited because the
  `get_all` user_id-value filter masks the commingling at retrieval time,
  so even the affected trials likely read back only their own rows in
  practice. So a re-run *as-is* would not be grossly corrupted — but the
  contamination is real, non-zero, and depends on an incidental masking
  behavior rather than a designed safeguard, which is a fragile basis for
  a paper-cited result.
- **The fix is cheap and low-risk relative to the re-run cost.** Option
  (a)/(b) is a localized change to one naming function; a 450-trial ×
  3-model re-run is expensive. Fixing first removes the ~0.9%
  contaminated-identity footnote entirely and eliminates reliance on the
  masking behavior — a clearly favorable trade.

**Concrete action for the human decision-maker:** choose one —
1. **Preferred:** authorize fix option (a) (hash-suffix) as a separate
   follow-up, verify with the subtask-5 reproduction (collision pairs
   should now map to distinct collections), then launch the re-run.
2. **Acceptable if time-critical:** launch the re-run now and disclose
   the 0.88% collided-identity rate as a known, bounded limitation,
   deferring the fix.
3. **Not recommended:** treat the sparse numbers as a bug and delay the
   re-run to "fix" them — they are expected behavior.

## 5. All commits from this investigation (traceability)

| Commit | Subtask | Deliverable |
|--------|---------|-------------|
| `662d93f` | 1 | `MEMORY_WRITE_PATH_TRACE_REPORT.md` — writes attempted & succeed; per-trial collection scope |
| `8f3f7ef` | 2 | `MEMORY_COUNT_READ_PATH_TRACE_REPORT.md` — `written_memories`/`shared_memory_count` source & semantics |
| `4ab8a9c` | 3 | `SCOPING_CONSISTENCY_TRACE_REPORT.md` — write/read byte-identical scope; empirical truncation collisions |
| `199ca10` | 4 | `TRIAL_ISOLATION_INTENT_REPORT.md` — "shared" = within-trial cross-agent; per-trial isolation intended |
| `8ad2b6e` | 5 | `scripts/reproduce_truncation_collision_and_sparse_metrics.py` — runnable reproduction (Parts A + B) |
| `f835eca` | 5 | `ROOT_CAUSE_DETERMINATION_REPORT.md` — two-category determination + captured output |
| _(this report)_ | 6 | `SPARSE_MEMORY_INVESTIGATION_SYNTHESIS_REPORT.md` — synthesis + recommendation |

## 6. Out-of-scope confirmation

- **No fix implemented.** `_collection_name_for_user`/`_get_client_for_user`,
  the metric definitions, and the harness audit are all untouched. Section 3
  names options only.
- **No re-run started.**
- **Subtask 5's determination report is not folded into a decision to
  proceed** — the recommendation in Section 4 is presented for a human to
  act on, not acted upon here.
- Implementing the chosen fix (Section 3) and launching the re-run
  (Section 4) are **separate follow-up tasks**.
