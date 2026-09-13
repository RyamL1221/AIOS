# 15-Run Benchmark Timeline Reconciliation

Read-only reconciliation (no code changes) of *when* the benchmark that
showed the "identical results / no learning" symptom ran, relative to
the two candidate fixes:

- **`286c10c`** — reward normalization (`r / JUDGE_MAX_SCORE`) —
  committed **2026-09-09 09:03:24 -0400**.
- **`b6ffd7e`** — per-arm bootstrap fail-open + downward-extended action
  spaces — committed **2026-09-11 12:48:34 -0400**.

(For reference: `a61eb2f`, the 2×10 clean-pilot report, is **2026-09-10
13:54:20 -0400** — between the two fixes.)

## Headline determination

**A benchmark of exactly "15 interactions" could NOT be located in any
on-disk artifact or committed report.** No trial log, results file, or
doc references a 15-interaction / 15-trial / N=15 run. The run scales
that actually exist in the artifacts are:

- **150-trial** `kernel_shared_adaptive` gpt-4o run — the recurring
  "identical results / flat reward / no learning" benchmark analyzed by
  `AIOS_REWARD_TREND_REPORT.md`, `AIOS_ARM_CONVERGENCE_REPORT.md`,
  `POLICY_ACTION_NULL_INVESTIGATION_REPORT.md`,
  `MEMORY_COUNT_READ_PATH_TRACE_REPORT.md`.
- **N=20 pilots** — 5×4 (`ADAPTIVE_POLICY_COMBINED_FIX_PILOT_REPORT.md`)
  and 2×10 (`AIOS_CLEAN_COMBINED_PILOT_REPORT.md`,
  `CLEAN_2x10_PILOT_VERIFICATION.md`).
- **N=11 dry-runs** (`logs/policy_trials.predryrun5_*.jsonl`).

So "the 15-interaction benchmark" as literally described **cannot be
conclusively dated, because no such run is evidenced.** The most
probable referent — the run that actually exhibits the identical-results
symptom — is the **150-trial run**. The remainder of this report dates
*that* run, and flags the "15" as unmatched.

## The most-likely referent: the 150-trial run

The symptom described in the subtask ("identical results", no arm
movement) is exactly what `AIOS_REWARD_TREND_REPORT.md` documents for the
150-trial gpt-4o `kernel_shared_adaptive` run: reward FLAT at ~3.95/5
start-to-finish, no measurable improvement; and
`AIOS_ARM_CONVERGENCE_REPORT.md` reports the similarity/redundancy arm
distributions are **byte-identical** (`21,18,24,22,12,15`).

### Evidence dating the 150-trial run relative to the fixes

1. **It POSTDATES normalization (`286c10c`, Sep 9).**
   `AIOS_REWARD_TREND_REPORT.md` states outright that the mechanism it
   analyzes "was verified by the LinUCB reward-normalization fix
   (`286c10c`/`a4cef0f`/`44ed99a`)". The report is written as an
   after-the-fact analysis of a run whose reward path already had
   normalization. So the 150-trial run's *analysis* — and the run it
   analyzes — sit at or after `286c10c`.

2. **It PREDATES the `b6ffd7e` action-space extension (Sep 11).** Both
   analysis reports describe the **6-value** action spaces, NOT the
   extended 10–11 arm spaces `b6ffd7e` introduced:
   - `AIOS_REWARD_TREND_REPORT.md`: "Each picks a threshold from a
     6-value discrete 'action space'".
   - `AIOS_ARM_CONVERGENCE_REPORT.md`: similarity arms "≤0.70",
     redundancy arms "≥0.70", novelty "[0.50, 0.95]" — i.e. the
     pre-extension spaces. It even notes the tuned targets were
     *unreachable* because the arms hadn't been widened/extended yet.
   The `21,18,24,22,12,15` distribution is over **6 arms** (indices
   0–5), which is only possible under the 6-value space. Under
   `b6ffd7e`'s 10–11 arm spaces this distribution shape cannot occur.
   Therefore the 150-trial run is from **before `b6ffd7e`**.

3. **On-disk log corroboration (weak, mixed).** The largest surviving
   trial log, `logs/policy_trials.prepilot.1789056633.jsonl` (mtime
   **Sep 10 11:53**), holds **152 distinct trial_ids** with a `ts` span
   of **2026-09-03 16:10 → 2026-09-10 11:53**. Its first record is a
   similarity `select` with `value: 0.2, arm_index: 0` — a `0.2` arm
   that only exists in the *oldest* pre-widening space (before even the
   `13cd04d` widening, let alone `b6ffd7e`). This log is an
   **accumulation across many runs** (Sep 3–10), not a single clean
   150-run, so it dates the *era* (pre-`b6ffd7e`, mtime one day before
   `b6ffd7e`) but cannot be attributed to one specific run.

### Determination for the 150-trial run

**The 150-trial "identical results" benchmark falls BETWEEN the two
fixes: it postdates normalization (`286c10c`, Sep 9) and predates the
bootstrap fail-open + action-space extension (`b6ffd7e`, Sep 11).**

Evidence: the trend report explicitly credits `286c10c` as already
applied; the convergence + trend reports both describe the pre-extension
6-value action spaces and a 6-arm (`21,18,24,22,12,15`) distribution
that is impossible under `b6ffd7e`'s 10–11 arm spaces; and the largest
trial-log snapshot's mtime (Sep 10 11:53) sits one day before
`b6ffd7e`.

## Implication for Subtask 3 (flagged, not assumed)

If the run of interest is the 150-trial run (the only run that clearly
shows the identical-results symptom), then Subtask 3 is **NOT** "confirm
the fixes work end-to-end", because that run was executed *before*
`b6ffd7e` existed. Its flat/identical outcome is therefore **expected
under the old code** and says nothing about whether `b6ffd7e` fixed it.
The `b6ffd7e` commit message itself states the 900-/150-trial accum run
is "invalidated (produced under the 0.50-floor gate) pending a fresh
run", and `REWARD_LOOP_INVESTIGATION_SYNTHESIS.md` reports a *separate*
post-`b6ffd7e` N=20 run where rewards fired (0→110) and arms moved. So:

- **Subtask 3 should be "run a fresh benchmark on current
  (post-`b6ffd7e`) code and see whether the identical-results symptom
  reproduces"** — i.e. find/confirm the *real remaining* behavior — not
  re-interpret the stale 150-trial numbers as evidence about the fixes.

## Explicit caveat on the "15" figure

The subtask's "15-interaction benchmark" does not match any artifact
(all evidenced runs are 150-trial, N=20, or N=11). Possibilities, none
confirmable from the repo:

- a mis-scaling in the task prompt (150 → 15, or a 3×5 / 5×3 config that
  was never persisted), or
- an ad-hoc run whose artifacts were not committed and no longer survive
  on disk.

This is flagged rather than resolved. If a literal 15-interaction run is
meant, **its artifacts are not present in the repo and it cannot be
dated at all.** The dating above is for the 150-trial run, the only
surviving benchmark that exhibits the identical-results symptom the
subtask describes.
