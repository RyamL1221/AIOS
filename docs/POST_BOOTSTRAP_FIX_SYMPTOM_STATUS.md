# Post-Bootstrap-Fix Symptom Status (from existing evidence)

Read-only assessment (no new trials, no code changes) of whether the
"identical results / no learning / all-arm-0" symptom is resolved as of
the current codebase (post-`b6ffd7e`, committed 2026-09-11 12:48:34
-0400). Conclusion is drawn from committed docs cross-checked against the
actual on-disk trial logs and the commit timeline — not from the docs'
self-reported claims alone.

## Bottom line

**The identical-results / no-learning symptom is NOT YET CONCLUSIVELY
TESTED on the current (post-`b6ffd7e`) code.** What exists on disk is:

1. A live 2×10 run (`CLEAN_2x10_PILOT_VERIFICATION.md`) that DID close
   the reward loop and move all three bandits off arm 0 — but it ran on
   the **pre-extension 6-arm action space** (arms 0–5 only), from an
   **uncommitted working tree the day BEFORE `b6ffd7e` was committed**.
   It exercised the *fail-open* half of `b6ffd7e` but NOT the
   *action-space-extension* half.
2. An unanalyzed 14-trial log in `logs/policy_trials.jsonl` that IS on
   the post-`b6ffd7e` extended action space (arms up to 10) — but **no
   committed report analyzes it**, and it is not a benchmark run.

So: closure + arm-movement is demonstrated (strong evidence), but on
code that is not byte-identical to HEAD, and the full current code has no
analyzed benchmark. The evidence supports "the mechanism works," not "the
symptom is confirmed gone on current code."

## Evidence

### A. `REWARD_LOOP_INVESTIGATION_SYNTHESIS.md` (read in full)

Its §1 reports, citing `CLEAN_2x10_PILOT_VERIFICATION.md`:
- Reward events **0 → 110** (178 `select` + 110 `reward` in the log it
  cites; 9 `report_reward` calls with non-empty `memory_ids_involved`).
- **All three bandits moved off arm 0.** Selects: novelty `{0:2, 1:22}`;
  similarity `{0:14,1:4,2:47,3:4,4:4,5:4}`; redundancy identical.
- Both fail-open branches fired live (bootstrap 20×, honoring-converged
  43×).

§2 explains the emily/alex asymmetry (14 injected ids vs 0) as a
**structural cross-session bandit-convergence artifact**, not noise: one
shared `PolicyManager` per kernel lifetime; session s1 inherited s0's
converged similarity arm (arm 2 = 0.70), which then dropped alex's
sub-0.70 rows. Early s0 injections were largely **fail-open overrides
while arms were unvalidated**, not relevance-driven passes.

§4 verdict: **GO for a larger run — conditioned on experiment design**
(control session order, report fail-open provenance, separate
fail-open-injected from gate-passed, re-examine 0.70 calibration), NOT on
any outstanding fix. §5: "the reward loop is closed and demonstrably
functional on a live kernel."

**Trial-to-trial variation question:** the synthesis/verification show
**selection did vary across arms** (not just the reward-firing
mechanism) — similarity/redundancy ranged over arms 0–5, novelty over
0–1. So it is more than "reward now fires while selection stays flat."
BUT the synthesis is explicit that this is **"the loop closes / arms can
move," NOT "it learns"** — N=20 (9 rewarded trials) is far too small for
any learning/quality claim, and much of the early movement was fail-open-
driven, not relevance-driven.

### B. Commit/date reconciliation of the cited run (verified, not assumed)

`CLEAN_2x10_PILOT_VERIFICATION.md` states its kernel was **PID 42753,
started Thu Sep 10 15:58:02 2026** — i.e. **~21 hours BEFORE `b6ffd7e`
was committed (Sep 11 12:48).** The doc claims "the bootstrap + per-arm
fail-open present on disk and loaded by this fresh kernel," meaning the
fix ran as **uncommitted working-tree edits** at that time.

Crucially, the doc's OWN arm-distribution data caps at **arm 5** for all
three bandits (`{0:14,1:4,2:47,3:4,4:4,5:4}`). Six arms (indices 0–5) is
the **pre-extension** action space. `b6ffd7e`'s downward extension made
similarity an 11-arm space (indices 0–10) and novelty/redundancy 10-arm
(0–9). **A run on the committed `b6ffd7e` code would show arm indices up
to 10; this run does not.** Therefore this run exercised the fail-open
logic but under the OLD 6-arm spaces — it is **NOT** a test of the
committed `b6ffd7e` in full.

### C. On-disk log audit (the decisive cross-check)

Parsed every surviving `logs/policy_trials.*.jsonl` for event counts and
**max arm_index actually selected** (the extension's fingerprint):

| log (mtime) | events | max arm_index (nov/sim/red) | action space era |
|-------------|--------|------------------------------|------------------|
| `policy_trials.jsonl` (Sep 11 14:51) | 164 sel / 149 rew, 14 trials | 1 / **10** / **9** | **post-`b6ffd7e`** (extended) |
| `...20260911_144122.pre_gpt4o` (Sep 11 13:43) | 60 / 48, 4 trials | 2 / 6 / 6 | transitional (7-arm) |
| `...presubtask5_20260911_133928` (Sep 11 13:39) | 46 / 39, 4 trials | 1 / 5 / 5 | 6-arm |
| `...presubtask4_20260910_155435` (Sep 10 15:15) | 212 sel / **0 rew** | 0 / 4 / 0 | pre-fix (arm-0-pinned) |

Findings:
- **The current `logs/policy_trials.jsonl` IS post-`b6ffd7e`** — it
  reaches similarity arm 10 and redundancy arm 9, which exist ONLY in the
  extended spaces. Its ts is Sep 11 14:44–14:51 (after the 12:48
  commit). It has 14 generic integer trial_ids (`1`–`14`) and rewards
  landing across arms 0–10.
- **But no committed report analyzes this log.** No doc references the
  Sep 11 14:44 timestamps, the 14-trial/149-reward shape, or arm indices
  6–10. It looks like an unanalyzed dry-run/smoke test, not a benchmark.
- The `presubtask4` log (the one preserved *before* the
  `CLEAN_2x10_PILOT_VERIFICATION.md` run) is the arm-0-pinned, **0-reward**
  historical baseline — consistent with the pre-fix symptom.

## Reconciliation with Subtask 2

Subtask 2 established the identical-results **150-trial** run sat BETWEEN
`286c10c` (normalization) and `b6ffd7e`. This subtask adds: the only
**live closure evidence** (`CLEAN_2x10_PILOT_VERIFICATION.md`) also
predates the `b6ffd7e` COMMIT (ran Sep 10 on an uncommitted working
tree), and used the pre-extension 6-arm spaces. The only genuinely
post-commit `b6ffd7e` artifact (`logs/policy_trials.jsonl`, 14 trials) is
unanalyzed and too small to be a benchmark.

## Determination

- **Confirmed resolved?** No — not on the committed current code. The
  strongest closure evidence ran on a pre-commit working tree with the
  old action space.
- **Confirmed still present?** No — the pre-`b6ffd7e` live run clearly
  shows the loop closing and all three bandits leaving arm 0, so the
  symptom is NOT simply persisting unchanged.
- **Not yet conclusively tested on current code?** **YES — this is the
  accurate status.** The fail-open + attribution mechanism demonstrably
  works (arms move, reward fires) on near-current code; but no analyzed
  benchmark exists on the exact committed `b6ffd7e` HEAD, and the one
  post-commit log (14 trials, arms 0–10) is an unanalyzed smoke run far
  too small for a learning or symptom-resolution claim.

**Implication:** a fresh benchmark on current HEAD is still required to
close the question — consistent with `b6ffd7e`'s own note that the prior
accum run is "invalidated ... pending a fresh run" and the synthesis's
"GO for a larger, properly-powered run." The mechanism is de-risked; the
symptom-on-current-code verdict is still open.

## Caveats on this assessment

- Arm-index-as-action-space-fingerprint is a strong inference (indices
  6–10 cannot occur under the 6-arm space), but I did not re-derive each
  log's exact `ACTION_SPACES` from its own records' `value` fields
  beyond spot values; the counts above are from `arm_index` alone.
- "No committed report analyzes the current jsonl" is based on a
  timestamp/shape/arm-index grep across `docs/`; an uncommitted or
  external (Cerebrum/results) analysis could exist but is out of this
  repo's committed scope.
