# task_context Bootstrap Trap — Synthesis & Primary Explanation for the Adaptive Score Gap

Closing document for the write-path diagnosis chain. Answers the original
question — **"why did adaptive score 4/2/2 (profile/task/integration)
while baseline scored higher on Task/Integration?"** — with the full,
now-traced mechanism, and hands off a scoped fix recommendation.

This **supersedes the "not yet explained" verdict** in
`docs/GATE_REJECTION_DIAGNOSIS_FINAL.md` (see reconciliation below).

## The full causal chain (end to end, cited)

1. **Adaptive cold-starts and explores strict novelty arms.** The LinUCB
   novelty bandit is in-memory only (no persistence, v1) and begins with
   optimistic exploration. In the 1×15 run it selected novelty arms
   **0.1 and 0.2** — the strict end of the action space.
   [`docs/TASK_CONTEXT_WRITE_PATH_TRACE.md`]

2. **task_context writes are rejected at the novelty add-gate.**
   task_context content evolves per interaction, so each write sits at
   `max_sim ≈ 0.48–0.59` (mean 0.558) to what's stored. The gate admits
   iff `max_sim < threshold`; with the explored threshold at 0.1–0.2,
   **all 22 task_context writes were rejected** (0 admitted).
   [`docs/TASK_CONTEXT_WRITE_PATH_TRACE.md`]. This is not a bug in the
   gate logic — the admit condition is correctly specified and works
   for profile content; it is a **design gap** (no per-task_type novelty
   calibration) plus an in-run exploration miscalibration.
   [`docs/NOVELTY_GATE_TASK_CONTEXT_CLASSIFICATION.md`]

3. **The update/upsert path that would bypass the gate can never
   engage.** TaskAgent's `_upsert_task_memory` routes to in-place
   `update_memory` (which skips the novelty gate entirely,
   `manager.py:1036-1038`) **only if a task_context memory already
   exists**. Since step 2 blocks the first create from ever persisting,
   the search-for-existing always returns no task_context (only the
   profile memory), so every write routes back to create → rejected.
   Confirmed: **0 task_agent `update_memory` ops in the run.**
   [`docs/UPSERT_PATH_REACHABILITY_TRACE.md`]

4. **task_context never accumulates for the adaptive condition.** The
   loop in step 3 is self-reinforcing: reject → nothing stored →
   upsert precondition unmet → create → reject. **This is the same class
   of bootstrap trap as the reward-loop trap fixed in `b6ffd7e`**, but on
   the novelty *add* gate and currently **unfixed**.
   [`docs/UPSERT_PATH_REACHABILITY_TRACE.md`]

5. **Only the profile memory is ever available to inject**, so every
   assistant response is generated with profile context but **zero
   task_context**. [`docs/GATE_REJECTION_JOINED_TABLE.md` established the
   single-profile-memory ceiling empirically; this chain traced its
   cause.]

6. **Adaptive's Task/Integration scores measure a memory-starved
   condition** — not a degraded-retrieval condition, an *absent-content*
   one. And the starvation is **adaptive-specific**: baseline skips the
   novelty gate entirely (both flags false, no `else` branch), and tuned
   admits the first task_context write (fixed thresholds 0.7/0.6/0.6 all
   exceed the observed max_sim 0.587). **Only adaptive is trapped.**
   [`docs/BOOTSTRAP_TRAP_PER_CONDITION_EXPOSURE.md`]

## Reconciliation with `GATE_REJECTION_DIAGNOSIS_FINAL.md` (explicit)

That doc (the prior chain's closing statement) correctly concluded the
score gap was **"NOT YET EXPLAINED by this run"**, that gate
over-rejection was confirmed as a *mechanism* but unproven as the *cause*
of the Task/Integration deficit, and it filed the "single-profile-memory
ceiling" as a new backlog item to investigate before the next run.

**This document is that investigation's result, and it explains the gap.**
Updating the two statements:

- **"single-profile-memory ceiling" (backlog item, was open):** now
  **RESOLVED into a specific mechanism** — the ceiling exists because the
  novelty add-gate bootstrap trap prevents any task_context memory from
  ever persisting under adaptive; only the (once-admitted) profile memory
  survives.
- **"score gap not yet explained":** now **EXPLAINED**. The prior chain
  looked at the similarity *retrieve* gate (fail-open rescues, honored
  wipeouts) and found the outcome scores didn't separate by
  retrieve-outcome — correctly inconclusive, because it was looking at
  the wrong gate. The actual cause is upstream at the novelty *add* gate:
  task_context never gets *written*, so no retrieve-side analysis could
  have surfaced it. The two docs are consistent — the earlier one ruled
  out the retrieve gate as the explanation and pointed at the write path;
  this one found the write-path cause.

## Answer to the original question

**The task_context novelty bootstrap trap is now the most likely PRIMARY
explanation for adaptive's 4/2/2 vs. baseline's higher Task/Integration.**
It is more direct than either original master-prompt hypothesis:

- vs. **exploration-cost (H1):** exploration cost is the *trigger* (strict
  arms explored early), but the trap explains why the cost is
  *catastrophic and persistent* rather than a transient dip — the
  rejection blocks the very mechanism that would let content accumulate.
- vs. **similarity-gate over-rejection (H2):** that hypothesis explains
  *degraded* retrieved content quality; the trap explains a **structural,
  complete absence** of task_context content for adaptive specifically.
  Absence of the content that Task/Integration scores depend on is a far
  more direct cause of a Task/Integration deficit than degraded ranking
  of content that (for task_context) was never there to rank.

Hedge preserved: this is the *most likely primary* explanation on the
evidence of one 1×15 run; the joined-table outcome scores at N=15 were
themselves too noisy to prove causation directly
(`docs/GATE_REJECTION_JOINED_TABLE.md`). A run with the fix applied (task
context actually accumulating for adaptive) is what would confirm it by
showing the gap close.

## Recommended fix (scoped — for a future master prompt, NOT implemented here)

**Primary recommendation — novelty-gate bootstrap fail-open, by analogy
to `b6ffd7e`.** Add a per-task_type bootstrap fail-open to the novelty
add-gate symmetric to the similarity gate's `BOOTSTRAP_MIN_UPDATES`
fail-open: **admit a candidate on total rejection when the store holds
zero existing memories of that `task_type` for the user**, so the
first-ever task_context (or any type) write always lands regardless of
the bandit's currently-explored arm. Once one exists, the normal
upsert/update path takes over and the gate resumes governing genuine
near-duplicates. This is the minimal change that breaks the
self-reinforcing loop, mirrors an already-accepted pattern in the
codebase, and leaves the gate's dedup purpose intact for the non-bootstrap
case.

**Two viable alternative/complementary fixes (surfaced across the chain;
presented without prescribing one):**
- **(a) Warm-start the novelty bandit near the tuned value (~0.7)**
  instead of cold-starting into strict exploration. Notably this is the
  **same fix already under consideration for the similarity gate's
  exploration-cost problem** — one change addressing two problems. It
  reduces the trap's likelihood but does not *guarantee* the first write
  lands (exploration could still momentarily pick a strict arm), so it
  pairs well with, rather than replaces, the fail-open.
- **(b) Bypass the novelty gate for task_context entirely**, treating it
  as always-upsert-eligible (evolving) content rather than
  dedup-candidate content. This matches task_context's semantics
  (TaskAgent already models it as an upsert), but is a broader behavioral
  change and would need a decision on whether other evolving types get
  the same treatment.

Choosing among these is a design decision for the next session; this
document recommends the fail-open as the primary, lowest-risk fix and
records (a)/(b) as the alternatives without ranking them beyond that.

## Backlog update

**NEW tracked item (higher priority than prior open items):**
> **Novelty-gate task_context bootstrap trap (adaptive condition).**
> Adaptive never accumulates task_context because the novelty add-gate
> rejects the first write and the gate-bypassing upsert path requires a
> prior write to exist. Compromises the validity of ANY
> adaptive-vs-baseline / adaptive-vs-tuned comparison on Task and
> Integration dimensions (adaptive is memory-starved; the other two are
> not). Recommended fix: per-task_type novelty bootstrap fail-open
> (see above). **Priority: HIGH** — blocks trustworthy adaptive outcome
> comparison.

Priority relative to previously-open items:
- **This item > redundancy-gate calibration** (the known embedding-space
  caveat): redundancy calibration affects retrieval-dedup fidelity; this
  affects whether adaptive has any task content at all.
- **This item > non-contextual baseline / condition-asymmetry** concerns:
  those are comparability framing questions; this is a concrete,
  fixable mechanism that invalidates a specific comparison until fixed.
- **Resolves/absorbs** the prior "single-profile-memory ceiling" backlog
  item into a specific root cause (no longer a separate open item).

## Standing caveats (carried, not re-litigated)
- Evidence is one 1×15 gpt-4o/gpt-5.4 run; the observed task_context
  max_sim (~0.55) is gpt-4o-embedder-specific, and the tuned
  non-exposure margin for llama/qwen is thin (+0.013)
  [`docs/BOOTSTRAP_TRAP_PER_CONDITION_EXPOSURE.md`].
- No code was changed in this diagnosis chain; no adaptive-policy *bug*
  (inverted logic) was found — the trap is a design gap + cold-start
  interaction, fixable by the recommended fail-open.

## Chain documents (this diagnosis)
- `docs/GATE_REJECTION_DIAGNOSIS_ARTIFACT_CHECK.md` — artifacts intact.
- `docs/TRIAL_TO_SIMILARITY_ARM_MAPPING.md` — trial↔arm map.
- `docs/FAILOPEN_EVENT_ACCOUNTING.md` — similarity-gate fail-open census.
- `docs/GATE_REJECTION_JOINED_TABLE.md` — joined scores; single-profile ceiling.
- `docs/GATE_REJECTION_DIAGNOSIS_FINAL.md` — prior close ("not yet explained"); superseded here.
- `docs/TASK_CONTEXT_WRITE_PATH_TRACE.md` — writes fire, novelty-rejected.
- `docs/NOVELTY_GATE_TASK_CONTEXT_CLASSIFICATION.md` — design gap, not a bug.
- `docs/UPSERT_PATH_REACHABILITY_TRACE.md` — upsert never engages; bootstrap trap.
- `docs/BOOTSTRAP_TRAP_PER_CONDITION_EXPOSURE.md` — adaptive-only exposure.
- **THIS DOC** — synthesis, primary explanation, scoped fix, backlog.
