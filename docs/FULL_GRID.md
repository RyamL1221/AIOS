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
