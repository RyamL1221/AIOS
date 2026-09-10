# Combined Fix Pilot & Go/No-Go — Adaptive Memory Policy

Closes out the fix-implementation chain (gate-blindness fix, equal-split
reward attribution, action-space widening). Reports a real small-scale
mechanism pilot run with all three AIOS-side fixes active, and delivers
an honest go/no-go call for a larger re-run.

**Bottom line up front: recommendation DEFERRED — the pilot surfaced a
fourth, distinct issue (benchmark-path retrieval returns 0 memories, so
the reward loop never closes) that prevents the three fixes from being
exercised end-to-end in the benchmark, even though all three are
independently verified working in isolation.**

---

## Pilot setup

- Config: `--users 5 --interactions-per-user 4` (5×4 accumulating-session
  mechanism pilot, 20 interactions), `--method kernel_shared_adaptive`.
- Assistant model: `gpt-4o` (Azure). Judge: `gpt-5.4` (Azure).
- Kernel: restarted to load all three committed fixes (`05772c0`,
  `cc385c5`, `13cd04d`); pre-flight confirmed `adaptive_policy_enabled=
  true`, `static_thresholds_enabled=false`; live import confirmed the
  widened arms `[0.50,0.60,0.70,0.80,0.90,0.95]` for similarity and
  redundancy.
- Trial log isolated to this run (`logs/policy_trials.jsonl` cleared
  first). 20/20 trials completed, 0 failed.

## What the pilot showed — concrete numbers

**Judge reward varies** (the judge discriminates): per-trial
`reward_value` ranged over {1.667, 2.0, 2.667, 3.0, 3.333} across the 20
trials — clearly not pinned. Aggregate scores: Profile 4.00, Task 1.80,
Integration 2.00.

**But the bandits never moved off their init arm.** From the isolated
trial log (172 `select` records):

| gate | selects | distinct values | arms chosen |
|------|---------|-----------------|-------------|
| novelty | 24 | {0.5} | {arm 0} |
| similarity | 74 | {0.5} | {arm 0} |
| redundancy | 74 | {0.5} | {arm 0} |

- **`reward` events logged: 0.** The reward loop never closed.
- Every `report_reward` had **empty `memory_ids_involved`** — the
  benchmark log repeated "0 results ... after ProfileAgent write. Mem0
  fact extraction may have failed silently" and
  `shared_memory_count=0` / `memory_total=0` in every CSV row.

## Root cause of the pilot outcome — a fourth issue, NOT a fix failure

The chain is: benchmark retrieves 0 memories per trial → no `memory_id`
to credit → `report_reward` records no `reward` events → bandits receive
no `update` → LinUCB stays at its initial state → every `select` returns
arm 0. So the flat, all-arm-0 result is a **downstream symptom of zero
retrieval in the benchmark path**, not evidence any of the three fixes
failed.

Critically, this is **not write loss and not my similarity fix**. Direct
inspection of the persisted store shows each pilot user's collection
holds **5 records** (writes landed via `infer=False`, as established
earlier). And querying the **live kernel's provider directly** for a
pilot user returns **5 results with real, differentiated similarity**
(0.58, 0.64, 0.62, 0.59, 0.58) on a basic retrieve, and correctly 1 on a
cross-agent `sharing_policy="shared"` retrieve. So the gate-blindness fix
is demonstrably working in the live kernel.

The 0-results are specific to **how the benchmark harness's audit/retrieve
path scopes its HTTP queries** (its per-writer-agent fan-out audit
returned 0 while the provider returns 5 for the same user_id). That is a
benchmark-harness / kernel-syscall retrieval-scoping mismatch — a
distinct fourth issue, separate from the three fixed here and separate
from the earlier `shared_memory_count` metric-scoping artifact (note: the
assistant responses in the CSV *do* cite profile details like the user's
tools and Python expertise, so some personalization leaks through even
while `shared_memory_count=0` — consistent with that known metric-scoping
quirk).

## Interpretive lens applied (as agreed before the run)

Because retrieval returned 0, the retrieve gates never received a reward,
so the intended three-tier read (novelty; similarity fires-every-retrieve;
redundancy fires-rarely) could not be evaluated on reward dynamics —
there were no reward events for any tier. What the log *does* confirm:

- **All three gates fire on selection** (novelty 24, similarity 74,
  redundancy 74), so the gate machinery is active and logging.
- **similarity and redundancy track each other exactly** (both 74
  selects, both all-arm-0). Per the agreed framing this is **expected,
  not a new finding**: they co-fire on the same retrieve decision and now
  share an identical action space — reinforced correlation, not signal.
- **redundancy's thin contribution** could not be assessed here (no
  rewards), but its select count equals similarity's, consistent with
  co-firing.
- The meaningful independent comparison (novelty vs the
  similarity+redundancy pair) is **inconclusive from this pilot** because
  no tier received reward — the precondition for that comparison (closed
  reward loop) was not met.

## Go/No-Go

**DEFER the larger re-run.** Not a no-go on the fixes — each is
independently verified (Subtask 1: real differentiated similarity + gates
discriminate; Subtask 2: equal-split conserves and differentiates;
Subtask 3: widened arms bracket the tuned winners, construction verified).
It would be premature to green-light a larger, costlier adaptive re-run
while the benchmark path retrieves 0 memories, because the bandits cannot
learn without a closed reward loop, and a scaled run would reproduce this
same flat, all-arm-0 outcome at higher cost — telling us nothing new.

**Precondition before any larger adaptive re-run:** resolve the
benchmark-path zero-retrieval issue so `report_reward` receives non-empty
`memory_ids_involved`. Concretely: reconcile the harness audit/retrieve
scoping with the provider (which returns the records correctly) so
retrieved memories carry through to reward attribution. Once a pilot of
this same 5×4 scale shows non-empty `memory_ids_involved` and non-zero
`reward` events, re-run this pilot; if the bandits then show arm
variation and the reward loop closes, scale up per the accumulating-
session design's pilot/ceiling framework. Until then, a larger run is not
justified.

## Documentation consistency (bundled corrections — final check)

- `.kiro/steering/memory-providers.md` — **consistent** with code:
  similarity now described as raw-distance + `distance_to_similarity`
  (Subtask 1); reward attribution described as equal-split v2
  (Subtask 2); action spaces shown widened to
  `[0.50,0.60,0.70,0.80,0.90,0.95]` (Subtask 3). (`.kiro` is gitignored;
  saved to disk, not committed.)
- `docs/ARM_INDEX_THRESHOLD_MAPPING_REPORT.md` — updated to the widened
  mapping (Subtask 3, committed `d3dfc8b`).
- `Cerebrum/docs/mem0-search-results-memory-id-gap.md` — **now annotated
  RESOLVED** (the previously-outstanding item): `retrieve_memory` emits
  `memory_id`; the separate similarity-null issue is also fixed and
  cross-referenced. This closes the last dangling documentation item from
  the whole chain.

## Deviations from the master prompt

- The master prompt anticipated an "unexpected finding → recommendation
  deferred" branch, and this pilot hit exactly that. I followed that
  branch: reported the fourth issue plainly with concrete evidence rather
  than forcing a go/no-go. The "reference the accumulating-session
  pilot/ceiling framework for next scale" step is stated conditionally
  (only after the precondition is met), not as an immediate go.
- Assistant/judge models were `gpt-4o`/`gpt-5.4` (Azure), per the user's
  instruction during the run (initial attempt with local `qwen2.5:7b` was
  aborted before producing results).
- The kernel was restarted (medium-risk, flagged) to load the committed
  fixes, since the previously-running instance predated them.
- Diagnostic scripts and the pilot's raw results remain uncommitted;
  only this report is committed.
