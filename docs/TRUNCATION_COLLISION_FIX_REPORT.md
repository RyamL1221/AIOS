# Truncation-Collision Fix — Report & Verification

Final deliverable for the follow-up fix task that resolves **Finding 2**
of the sparse-memory investigation (the 63-char ChromaDB
collection-name truncation collision). Self-contained; cross-references
the prior investigation reports where useful.

---

## 1. Problem being fixed

(Reused from Finding 2 of the prior investigation — not re-derived.)
`Mem0Provider._collection_name_for_user` built per-user ChromaDB
collection names as `mem0_memories_<sanitized_user_id>` and truncated to
ChromaDB's 63-char limit with a bare prefix slice. The benchmark's
per-trial `user_id`s share a long common prefix
(`<name>_adaptive_report_v2_<model>_`) and differ only in a **suffix**
(`_t<idx>__kernel_shared_adaptive`) — exactly the part truncation drops.
Empirically, 450/453 (99%) of real trial `user_id`s were truncated, and
**2 collision pairs** resulted: distinct trials (verified different
profiles/projects) mapping to a single physical ChromaDB collection.
Retrieval's `get_all(filters={"user_id": <full value>})` masked the
commingling at the row level, so it did not corrupt the observed
metrics, but it remained a genuine latent violation of the per-identity
isolation invariant and a scoping hazard at re-run scale.

## 2. The fix

- **Location:** `aios/memory/providers/mem0.py`,
  `_collection_name_for_user` — confined to the truncation branch only.
- **Scheme (hash-suffix, master-prompt option (a)):** when the sanitized
  `user_id` component would exceed the truncation budget
  (`max_user_len`), reserve the last 8 chars of that budget for
  `hashlib.sha256(user_id.encode()).hexdigest()[:8]` computed from the
  **full, original, untruncated** `user_id`. The name becomes
  `mem0_memories_{truncated_prefix}{hash8}` with
  `len(truncated_prefix) + 8 <= max_user_len`. All pre-existing naming
  constraints are preserved (3–63 chars, alnum start/end, sanitized
  character set, the "ends with alnum" safety check re-applied to the
  new suffix). `import hashlib` was added.
- **Guarded to the truncation path:** a `user_id` whose sanitized form
  already fits produces **byte-identical** output to the pre-fix
  function — no hash suffix, no behavior change.

### Why this approach over the alternatives

(Reusing the rationale stated in the master prompt / synthesis report.)

- **(a) Readable prefix + short deterministic hash of the full user_id
  (chosen).** Preserves a 1:1 `user_id → collection` mapping with
  negligible collision probability while keeping a human-readable prefix
  for debugging. Most robust; minimal change surface.
- **(b) Replace the name entirely with `mem0_<hash>`.** Collision-safe
  and simplest, but drops the human-readable prefix, hurting
  debuggability of the ChromaDB store. Rejected for readability.
- **(c) Detect-and-raise/log on collision.** Keeps current naming but
  loudly fails when a name is already bound to a different `user_id`.
  Rejected: it surfaces the problem instead of preventing it, and would
  make an otherwise-valid write fail at runtime.

## 3. Verification results

### 3.1 Non-truncated ids are byte-identical (subtask 1)

A direct comparison of the patched function against a faithful
reproduction of the pre-fix function, over short and boundary ids
(including length-49, the exact budget), confirmed **identical** output
for every non-truncated `user_id`. The fix changes names only where
truncation actually occurs.

### 3.2 Reproduction script — Part A fixed, Part B unchanged (subtask 2)

Re-ran `scripts/reproduce_truncation_collision_and_sparse_metrics.py`
against the patched provider (isolated temp ChromaDB, real Ollama
`nomic-embed-text` embedder):

- **Part A (collision):** the named colliding pair
  (`…qwen25_7b_t23…` / `…_t31…`) now produces **distinct** collection
  names (`…qwe093add31` vs `…qwec3b563fc`), distinct clients, and a raw
  collection-level read shows **no commingling** — each physical
  collection holds only its own identity's rows. **PASS (FIX
  CONFIRMED).**
- **Part B (sparse metrics):** byte-for-byte unchanged —
  `total_stored_for_user=3`, `shared_memory_count=2`, distributions
  `[3,3,3]` / `[2,2,2]`, conversation memory structurally excluded.
  **PASS (unchanged).** This proves the fix did not touch Finding 1's
  code path.
- **Assertion-semantics note:** Part A's pass gate was originally written
  to *reproduce the bug* (`same_name and commingled`). It was inverted to
  assert the *fixed* behavior (`(not same_name) and (not commingled)`) —
  a deliberate, documented update to a verification script's success
  criteria now that the code under test has changed, not a production
  change.

### 3.3 Full-scale empirical re-check across all 453 real identities (subtask 3)

Extracted the same 453 distinct real `user_id`s from `kernel.log` (same
`grep -oE "user_id=…"` methodology) and ran the **actual patched**
`_collection_name_for_user` over all of them
(`scripts/verify_collision_free_real_user_ids.py`):

| | Distinct collection names | Collision groups |
|--|--------------------------|------------------|
| Pre-fix  | 451 | 2 (`alexandra_thompson…t23/t31`, `emily_rachel_patel…t124/t76`) |
| Post-fix | **453** | **0** |

- **Zero remaining collisions** across all 453 identities (distinct
  collection count now equals the identity count exactly).
- Of the 453, **449 were non-colliding pre-fix**; running the patched
  function over that safe set introduced **0 new collisions**.
- All 453 post-fix names satisfy ChromaDB constraints (0 violations).

**Result: the fix eliminates both known collisions, introduces none, and
holds at the scale the 450-trial re-run operates at.**

## 4. Out-of-scope boundaries honored

Every boundary from the master prompt was respected:

- **Finding 1 (`written_memories` / `shared_memory_count`) not touched.**
  The conversation-exclusion / per-trial-isolation behavior is unchanged
  (Part B is byte-identical pre/post fix).
- **`kernel_shared_adaptive` re-run not started or scheduled.**
- **LinUCB code not touched** (the reward-normalization fix and its files
  are unrelated and untouched here).
- **`trial_id` logging gap not touched.**
- **Redundancy-bucket miscalibration not touched.**
- **No existing ChromaDB collections migrated or backfilled** — the fix
  only changes how *new* collection names are computed going forward.
- Change surface was confined to `_collection_name_for_user` (+ the
  `hashlib` import); no other production function was modified.

## 5. Commits (this fix task)

| Commit | Subtask | What |
|--------|---------|------|
| `7065d09` | 1 | `fix(aios): hash-suffix truncated collection names to prevent user_id collisions` |
| `adfcaeb` | 2 | `test(aios): verify truncation-collision fix against reproduction script` |
| `a3da418` | 3 | `test(aios): confirm zero collisions across real trial user_ids post-fix` |
| _(this report)_ | 4 | `docs(aios): document truncation-collision fix and verification results` |

## 6. State of the original open question — is the re-run unblocked?

**Concrete statement:** With this fix landed and verified, **Finding 2 no
longer blocks the `kernel_shared_adaptive` re-run.** The prior synthesis
report's recommendation was to fix the truncation collision as a cheap,
low-risk precondition before re-running; that precondition is now
satisfied and verified at full scale (453/453 distinct collections, zero
collisions, zero regressions, zero new collisions among the previously-
safe 449).

The other item the synthesis flagged, **Finding 1 (sparse
`shared_memory_count` clustering at 2), was determined to be a
by-design/measurement characteristic, not a blocking bug** — it was
explicitly out of scope for this task and remains unchanged. Nothing in
this fix task surfaced a new blocker.

**Recommendation (the decision itself remains a separate, human call):**
proceed to authorize the `kernel_shared_adaptive` re-run. There are no
remaining code-level blockers from the sparse-memory investigation.
Two caveats for the decision-maker, neither blocking:
1. The fix applies to **newly computed** collection names; any collided
   collections already on disk from the *previous* run are not migrated
   (out of scope by design). A clean re-run writes fresh per-trial
   collections, so this does not affect a new run — only pre-existing
   on-disk data.
2. Finding 1's `shared_memory_count=2` pattern will reproduce in the
   re-run (it is structural); interpret those metrics with that known
   characteristic in mind, as documented in the synthesis report.

This subtask made **no code changes and did not start the re-run**; the
recommendation is stated for a human to act on.
