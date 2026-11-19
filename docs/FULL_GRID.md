# The full grid (stub)

Subtask 23 runs the final evaluation, the full grid: every scored cell
at 150 users (`BENCHMARK_V2.md`, Amendment 7). This stub holds what is
decided before
then. It is not the grid's pre-registration: Subtask 23 writes the cell
list, the rules and the analyses before any grid run, and fills in the
sections marked open.

Started 2026-11-16 (Subtask 18 housekeeping).

## Cells decided so far

- **Native k = 30 on Graphiti**, beside its k = 10 cell, to measure how
  much of a native gap is the k native kept (`BENCHMARK_V2.md`,
  Amendment 7; DEV_STATUS open decision 6 (b), confirmed 2026-11-16).
  Graphiti, because the cap binds hardest there: at k = 10 it bound in
  all 540 probes of the Graphiti smoke. The harness switch for the
  native k is the grid's to add.
- **The stress dimensions of Subtask 18** (`STRESS_DIMENSIONS.md`):
  agent count, concurrency and the faulty agent run judge-free in
  Subtask 18; their scored runs wait for the grid.

Open: the full cell list (loci, backends, models, H, the stress
levels), the users per cell, the run order and the cost.

## The judge window

**Why.** The judge drifts. The same answers, judged again with the
same prompt, seed and greedy decoding (DEV_STATUS known issue 24):
- in one sitting, 92.2% of profile, 100% of task and 94.4% of
  integration scores were the same (Subtask 9d, 90 trials re-judged);
- a week apart, 75.8%, 98.8% and 83.6% (Subtask 17, 165 identical
  pilot_v1 answers), with mean differences within 0.03.

A judge that moves between the judging of two cells adds a difference
that is not theirs. So every score the paper compares comes from one
window.

**The plan.**
1. **Answers first, scores after.** Every grid cell runs with
   `--no-judge`. Each trial keeps what the judge needs: the integration
   probe's answer and the user's final profile and task context. No cell
   is judged while the grid runs.
2. **One pass over every cell**, after the last cell has finished, with
   one deployment (`gpt-5.4` on Azure, judge prompt v2, greedy
   decoding, the fixed seed), one harness commit and a fixed
   concurrency.
3. **Interleaved.** The pass judges user by user across cells: user i
   of every cell, in a seeded cell order, before user i + 1. Drift
   during the pass then falls alike on every cell, and on both sides of
   every paired comparison.
4. **Bounded.** The window runs from the pass's first judgment to its
   last and closes within 24 hours. Subtask 23 checks that bound
   against the pass's size and Azure's rate limits before the run. An
   interrupted pass resumes inside the window; one that cannot finish
   in it is redone whole in a new window, never completed in another.
5. **Anchors.** A fixed anchor set, the 165 pilot_v1 answers of
   Subtask 17's test-retest, is judged at the window's start and at its
   end. Reported per score: the share of identical scores, and the
   paired mean difference (end − start) with its 95% CI. Stated now: if
   a score's CI excludes 0, that score's judgments from the window are
   not used and the pass is redone.
6. **Recorded.** Per judgment: the window id, a timestamp, the
   deployment and its API version, and the judge prompt's sha256. Per
   results file: the window id. The analysis refuses to compare scores
   from two windows.
7. **Re-runs.** A cell re-run after its window (a failed user, known
   issue 36) is judged again, in a new window, with every cell it is
   compared against.

**Tooling Subtask 23 adds.** `rejudge.py` judges the top-level (v1)
fields, which a v2 trial mirrors from its integration probe; it must
also write the probe's own record, interleave across results files and
record the window. And a window report: the anchors' agreement and the
pass's start, end and failures.

Open: the pass's size and cost (one judge call per judged trial, plus
retries), the concurrency, and the cell order's seed.

## The two judges (Subtask 20)

Definitions, the reliability protocol and the k rule are in
`METRICS.md` ("Judged measures"). Fixed here for the grid:

**Decoding differs, and neither judge is claimed to be deterministic.**
The primary judge, `gpt-5.4` on Azure, decodes greedily (temperature
0.0) with a best-effort seed (20261105). The second judge, Claude
Sonnet 5.5, uses default sampling: its API accepts no sampling
parameter. Repeatability is measured for each judge by the repeat
protocol (10 judgments of each of 200 calibration answers), and the k
rule (the smallest k in {1, 3, 5} whose median reaches Krippendorff's
alpha ≥ 0.80 on Profile and Integration) is applied to each judge
separately. If the two judges need different k, each is used at its
own k and both are reported.

| Judge | k | Cost multiplier | Evidence |
|---|---|---|---|
| `gpt-5.4` (primary) | open: its calibration waits on the Azure deployment | k calls per judged answer | |
| Claude Sonnet 5.5 (second) | 1 | 1 call per answer in its subset | median-of-1 alpha: Profile 0.966 [0.951, 0.977], Integration 0.963 [0.947, 0.975] (Cerebrum `results/judge_reliability_s20/`) |

At k > 1 each judged answer is judged k times in the window, and its
score is the median; every repeat is recorded.

**The second judge's subset**, fixed before the grid runs. The second
judge scores 30% of the judged answers, at its k, chosen by user, so
the same users are in the subset in every cell and every paired
difference of the grid (kernel − other, H2 − H0) also exists on the
subset:
- strata: echo users (i mod 9 in {0, 4, 8}, `synth_v2.is_echo_user`)
  and the other users;
- order: within each stratum, the indices of users_v2's 150 users in
  the order `random.Random(20261121).shuffle` gives the stratum's
  sorted list (echo stratum shuffled first, then the other, from one
  generator);
- a cell with users U takes, from each stratum, the first
  round(0.3 × |U ∩ stratum|) of U's users in that order (at least one
  when U has a user of the stratum); at 150 users, 15 echo and 30
  others, 45 in all;
- the subset never depends on a score: it is fixed by the user index
  alone.

Code: Cerebrum `judge.second_judge_users(users)`. At 150 users it is
users 4, 5, 7, 11, 15, 16, 20, 25, 26, 27, 28, 32, 36, 38, 41, 43, 44,
49, 54, 56, 57, 60, 61, 62, 66, 72, 74, 78, 79, 80, 89, 90, 93, 94,
96, 97, 105, 106, 115, 120, 130, 134, 138, 140 and 147.

The second judge's answers go in one Batch submission after the
primary judge's pass has closed. The Batches API orders its work as it
chooses, so the interleaving of the primary pass does not apply; the
batch's submission and end bound its window, recorded with every
judgment. Reported on the subset: inter-judge alpha, Spearman and mean
offset per dimension, and direction agreement for each of the grid's
paired differences (`METRICS.md`, "Agreement between the judges").
