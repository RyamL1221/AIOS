# Gate-Rejection Diagnosis — Final Report

Closing document for the diagnosis chain investigating why the adaptive
condition scored ~4/2/2 (profile/task/integration) while the baseline
scored higher on Task/Integration, using the fresh 1×15
`kernel_shared_adaptive` run (commit `d3a79cb`, kernel PID 69841). Builds
on and references — does not restate — the reward-loop closeout in
`docs/FRESH_POST_FIX_BENCHMARK_1x15.md` (that doc already established
loop closure, arm movement, timeline attribution of the old
"identical results" symptom, and the coupled-signal / convergence-quality
open questions; this doc is the *outcome-causation* diagnosis, a distinct
scope).

Evidence chain (all read-only, this session):
- `docs/GATE_REJECTION_DIAGNOSIS_ARTIFACT_CHECK.md` — artifacts intact.
- `docs/TRIAL_TO_SIMILARITY_ARM_MAPPING.md` — trial→arm map (0–11 HIGH).
- `docs/FAILOPEN_EVENT_ACCOUNTING.md` — all 74 fail-open events by trial.
- `docs/GATE_REJECTION_JOINED_TABLE.md` — joined per-trial scores.

## Reconciliation against the two original hypotheses

### H1 — Exploration cost
The master prompt's first candidate: adaptive underperforms because the
bandit spends early trials *exploring* sub-optimal arms. **Partially
relevant but not the story here.** The run does show the mandatory LinUCB
optimism sweep (arms 0→10 across trials 0–10 before concentrating), which
is exploration cost by definition. But the joined table
(`GATE_REJECTION_JOINED_TABLE.md`) shows the explored trials did **not**
score systematically worse — clean/rescued/wiped groups are within noise
— so exploration cost is present mechanically yet **not shown to drive
the score gap** in this run.

### H2 — Gate over-rejection
The second candidate: the similarity gate rejects genuinely-relevant
memories because the relevant band (~0.45–0.65 cosine) sits below the
0.5+ arm thresholds. **CONFIRMED as a mechanism, and pervasive — not an
edge case.** Per `FAILOPEN_EVENT_ACCOUNTING.md`:
- Trials 5–10 (arms 0.5–0.95) each had raw-retrieval wipeouts rescued
  only by the bootstrap fail-open (44 `still bootstrapping` events,
  rising with the threshold), so their "normal-looking" 1-injected
  status was fail-open-driven, not a clean pass.
- Trials 12–14 (converged arm 0.8) had those same wipeouts *honored*
  (30 events) → 0 injected → `unknown`.
- Only trials 0–4 and 11 (low arms 0.0–0.4) retrieved cleanly.

So over-rejection is happening across the whole high-threshold region,
usually masked by fail-open. **But — and this is the crux — this run's
data cannot show that over-rejection caused the Task/Integration
deficit**, because of the confound below.

## Explicit answer to the original question (appropriately hedged)

**"Why did adaptive score 4/2/2 while baseline scored higher on
Task/Integration?" — NOT YET EXPLAINED by this run.**

The most defensible current statement:

- The gate **over-rejection mechanism is real and pervasive** (H2
  confirmed at the mechanism level).
- But it is **unproven as the cause** of adaptive's Task/Integration
  deficit: in this run, trials that lost their injected memory entirely
  (permanently_wiped, 12–14) scored *on par with* clean trials, and
  rescued trials scored *highest* — the opposite of the gradient the
  "over-rejection hurts outcome" hypothesis predicts
  (`GATE_REJECTION_JOINED_TABLE.md`).
- A competing explanation is at least as plausible and is **structural,
  not an adaptive-specific bug**: baseline uses unfiltered top-k
  retrieval and therefore has **no gate bottleneck at all**, whereas
  every kernel_shared* condition (adaptive AND tuned) funnels retrieval
  through the gate. If baseline's Task/Integration edge comes from simply
  never gating, that is a **structural asymmetry between the conditions**,
  not evidence that adaptive's bandit is misbehaving. This run cannot
  distinguish "adaptive over-rejects" from "baseline never gates" as the
  source of the gap.

So: mechanism confirmed, outcome-causation unproven, and the
condition-level asymmetry is a live alternative that must not be
mis-attributed to an adaptive bug.

## Separation of claims (proven vs. unproven)

| Claim | Status |
|-------|--------|
| Reward loop closes; all 3 bandits leave arm 0 | **PROVEN** (see `FRESH_POST_FIX_BENCHMARK_1x15.md`) |
| Similarity gate over-rejects the ~0.45–0.65 relevant band at arms ≥0.5 | **PROVEN (mechanism)** — 44 bootstrap rescues + 30 honored wipeouts |
| Over-rejection is pervasive (trials 5–14), not just the trailing 3 | **PROVEN** (`FAILOPEN_EVENT_ACCOUNTING.md`) |
| Over-rejection *caused* adaptive's Task/Integration deficit | **UNPROVEN** — wiped ≈ clean on scores; confounded |
| Adaptive is worse than baseline *because of the bandit* | **UNPROVEN** — condition-level gating asymmetry is an untested alternative |
| 0.8 / 0.7 / 0.2 are *good* converged values | **UNPROVEN** (already open in `FRESH_POST_FIX_BENCHMARK_1x15.md`) |

## NEW BACKLOG ITEM — single-profile-memory retrieval ceiling

**Tracked here as its own investigation item, not a footnote.**

Finding (`GATE_REJECTION_JOINED_TABLE.md`): across **all** 12 injecting
trials, the retrieved/injected memory was **always the same single
profile memory** (`a0162e92…`, `memory_type=profile`,
`owner_agent=profile_agent`). **No task_context or conversation memory
was ever retrieved for any trial**, in any outcome group.

Why this matters (candidate root cause, broader than adaptive):
- It pins profile score ~4.0 everywhere and task score ~2 everywhere,
  which is exactly why the outcome groups couldn't separate — the
  confound that blocked H2's outcome test.
- More importantly, it suggests the **retrieval/injection pipeline may
  never be surfacing task_context memories at all** — regardless of
  gating. If task_context memories aren't being written, aren't matching
  the follow-up query, or are being out-ranked/deduped before the gate,
  then Task/Integration scores are capped for a reason that has **nothing
  to do with the bandit** and **affects tuned and baseline too**.
- This is a candidate explanation for the whole Task/Integration deficit
  independent of gate over-rejection, and it should be investigated
  **before** the next real run, because a run that can't inject
  task_context can't test any memory-quality hypothesis.

Suggested first checks for this item (not done here — out of scope):
1. Do ProfileAgent/TaskAgent both actually write their memories for the
   user (confirm a task_context memory exists in the store post-run)?
2. If written, does it match the assistant's follow-up query above the
   gate threshold, or is it dropped at retrieval / dedup / gate?
3. Is the audit/injection path only ever fetching one memory (a top-k or
   dedup cap) regardless of what's stored?

## Requirements for a follow-up run that could actually test H2

1. **Multiple memory types must be retrievable** — the store must contain
   (and the pipeline must surface) task_context and conversation
   memories, not just one profile memory. Otherwise injected-vs-not is a
   weak lever and outcome groups can't separate (this run's failure mode).
   Resolve the backlog item above first.
2. **Enough trials per arm/outcome** — N=3-vs-N=6 groups on a 1–5 scale
   cannot separate signal from noise. Size so each outcome category
   (clean / rescued / wiped) has enough trials for a real comparison
   (tens, not a handful), and so per-arm reward has repeated observations.
3. **A no-gate control within the same memory content** — to separate
   "adaptive over-rejects" from "baseline never gates," compare adaptive
   vs. tuned vs. a genuinely-unfiltered condition on the *same* retrieval
   content, so the condition-level asymmetry is measured directly.
4. **Balance/randomize session order and report fail-open provenance**
   per the conditions already in `docs/REWARD_LOOP_INVESTIGATION_SYNTHESIS.md`.

## Bottom line
- **H2 (gate over-rejection): mechanism CONFIRMED and pervasive.**
- **Outcome-causation: UNPROVEN** — this run's single-profile-memory
  ceiling and small N prevent attributing the score gap to it, and a
  structural adaptive-vs-baseline gating asymmetry is an equally live
  explanation.
- **New tracked confound:** the single-profile-memory retrieval ceiling,
  a candidate root cause affecting all conditions, to investigate before
  the next run.
- No code changed in this diagnosis chain; no bug in the adaptive policy
  was demonstrated. The next step is the pipeline/retrieval investigation
  above, then a properly-powered run — not a policy change.
