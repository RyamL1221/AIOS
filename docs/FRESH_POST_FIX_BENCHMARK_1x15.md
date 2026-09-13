# Fresh Post-Fix Benchmark (1×15) — Symptom-Reproduction Verdict

First benchmark run whose provenance is unambiguously on the **committed**
current HEAD (`d3a79cb`), which includes both fix commits:
`286c10c` (reward normalization) and `b6ffd7e` (per-arm bootstrap
fail-open + downward-extended action spaces). Prior "closure" evidence
(`CLEAN_2x10_PILOT_VERIFICATION.md`) ran on an *uncommitted working tree*
the day before `b6ffd7e` and used the old 6-arm action space (see
`POST_BOOTSTRAP_FIX_SYMPTOM_STATUS.md`); this run closes that gap.

## Verdict

**The identical-results / no-learning / all-arm-0 symptom does NOT
reproduce on current HEAD.** At both levels:

- **Bandit level:** all three bandits move off arm 0 and exhibit healthy
  explore-then-concentrate behavior over the extended (post-`b6ffd7e`)
  action space (arm indices up to 10, which cannot occur under the old
  6-arm space).
- **Output level:** 15/15 assistant responses are distinct, and judge
  scores span 6 distinct (profile, task, integration) tuples — not one
  pinned value.

This is a **closure + arm-movement** result, NOT a learning-quality
claim: N=15 on one user is far too small to assert the policy converges
to a *good* threshold (consistent with every prior pilot's caveat).

## Provenance (recorded, unambiguous)

| Field | Value |
|-------|-------|
| Git commit (HEAD) | `d3a79cb` (contains `286c10c` and `b6ffd7e` as ancestors) |
| Working tree | clean for tracked source; `policy.py` / `manager.py` unmodified |
| Kernel PID | **69841** |
| Kernel start | **Sun Sep 13 16:24:23 2026 EDT** |
| Kernel restarted mid-run? | **No** — same PID before, during, after |
| `/memory/gating_status` | `adaptive_policy_enabled: true`, `static_thresholds_enabled: false` |
| Method | `kernel_shared_adaptive` |
| Assistant model | `gpt-4o:azure` |
| Judge model | `gpt-5.4:azure` |
| Scale | 1 user (`samantha_carter_6fcfc373_s0`) × 15 interactions |
| Run window | 2026-09-13 16:30:46 → 16:38:03 |
| Result | 15/15 completed, **0 failed** |
| Aggregate scores | Profile 4.133, Task 2.000, Integration 2.333 |
| Avg latency | 7.4 s/interaction |
| Preserved trial log | `logs/policy_trials.subtask4fresh_1x15_20260913_163934.jsonl` |
| Harness results | `../Cerebrum/results/subtask4_fresh_1x15/` (JSON + CSV) |

A first launch attempt failed with the VPN off (15/15 errored on Azure
`LLM returned None`, ~2s total); it wrote **no** policy events (trial log
verified byte-identical to its pre-run backup) and its output was
discarded. The valid run above is the second launch, after VPN-up was
confirmed with a live gpt-4o + gpt-5.4 probe through the kernel.

## Reward-loop closure (select vs reward)

Isolating this run's records (the 286 events appended after the 313-line
pre-run baseline in the preserved log):

| event | count |
|-------|------:|
| `select` | 167 |
| `reward` | 119 |

- Harness sent **15** `report_reward` calls, all with **non-empty**
  `memory_ids_involved` (e.g. trial 2 credited memory `a0162e92…`,
  reward 2.667). Contrast the pre-fix identical-results run: **0** reward
  events.
- Kernel-side fail-open branches both fired during the run
  (`kernel.log`): bootstrap fail-open (`still bootstrapping`) and
  strict-honor (`honoring converged arm`) — the per-arm mechanism engages
  when arms are uninformed and closes once they are validated, exactly as
  designed.

## Per-bandit arm behavior over time (the core evidence)

Selects ordered by timestamp. The signature is a clean LinUCB
explore-then-concentrate:

**similarity_threshold** (n=74): swept arms 0→1→2→…→**10** in order
(optimism trying every untried arm), then concentrated on **arm 8 =
value 0.8**.
- first-half arms: `{0:4,1:5,2:5,3:5,4:5,5:5,6:5,7:3}`
- last-half arms: `{0:5, 7:2, 8:20, 9:5, 10:5}` — arm 8 dominates.
- Arm 8 (0.8) is the offline-tuned gpt-4o similarity winner, and it is
  reachable ONLY because `b6ffd7e` extended the space (the old 0.5–0.95
  6-arm space could reach 0.8, but the pre-fix run never left arm 0).

**redundancy_threshold** (n=74): same 0→9 sweep, then concentrated on
**arm 6 = value 0.7**.
- last-half arms: `{0:5, 6:15, 7:2, 8:10, 9:5}` — arm 6 dominates.

**novelty_threshold** (n=19): `[0,0,1,1,1,…,1]` — tried arm 0 twice then
settled on **arm 1 = value 0.2** for the rest.

Reward updates landed across the full arm range for
similarity/redundancy (arms 0–10 / 0–9), so the concentration is
reward-driven, not a dead gate.

### Reading of the pattern
This is the textbook opposite of the historical symptom. The pre-fix
150-trial run pinned every bandit to arm 0 with 0 rewards
(`AIOS_REWARD_TREND_REPORT.md`); here every bandit explores its whole
action space and then concentrates on a specific learned arm. The arm
indices reaching 10 are themselves proof the run is on the extended
post-`b6ffd7e` space.

**Caveat (honest):** similarity and redundancy co-fire on every retrieve
and share reward attribution, so their movement is one coupled signal,
not two independent confirmations (a known, documented property). And
the visible "sweep" is partly LinUCB's mandatory initial optimism, not
proof of learned optimality — with N=15 we can say the arms *move and
concentrate*, not that 0.8 / 0.7 / 0.2 are *good* converged values.

## Output-level variation (the "identical results" question directly)

From the harness results JSON (15 trials):

- **Distinct assistant responses: 15/15** (lengths 433–4806 chars, all
  different openings).
- **Distinct (profile, task, integration) score tuples: 6/15.** Profile
  ranged 4–5, Task 1–3, Integration 1–4.

So neither the responses nor the scores are identical trial-to-trial —
the original "identical results" symptom is absent at the output level
too, not just in the bandit internals.

## Cross-reference to the timeline

- Subtask 2 established the identical-results **150-trial** run sat
  between `286c10c` and `b6ffd7e` (old 6-arm space, arm-0-pinned, flat
  reward).
- Subtask 3 found the only prior *closure* evidence predated the
  `b6ffd7e` commit and used the 6-arm space, leaving current-HEAD status
  "not conclusively tested."
- **This run resolves that:** on committed HEAD with the extended action
  space, the loop closes (119 reward events), arms move and concentrate
  (similarity→0.8, redundancy→0.7, novelty→0.2), and outputs vary. The
  symptom does not reproduce.

## Scope / limitations (asserted, not optional)

1. **N=15, one user, one session — closure not learning.** No
   convergence-quality or trend claim is made or supported.
2. **Single shared `PolicyManager`** for the kernel lifetime (by design;
   not isolated per user). With one user this raises no cross-session
   confound, but per-persona generalization is untestable here — the
   synthesis doc's session-order conditions still apply to any larger
   multi-user run.
3. **similarity/redundancy are one coupled signal** (co-fire + shared
   attribution).
4. **Judge/assistant are real paid Azure calls**; scores are gpt-5.4's,
   not re-verified.
5. `select` records are not stamped with `trial_id` (only `reward`
   records are), so temporal ordering — not per-trial grouping — is the
   correct lens for the select stream; this is how the arm sequence above
   was derived.

## Artifacts

- Preserved run trial log:
  `logs/policy_trials.subtask4fresh_1x15_20260913_163934.jsonl`
- Pre-run baseline (untouched, for diff):
  `logs/policy_trials.presubtask4fresh_20260913_162402.jsonl`
- Harness results: `../Cerebrum/results/subtask4_fresh_1x15/`
  (`results_kernel_shared_adaptive.json`, `results.csv`)
- Kernel log: `kernel.log` (PID 69841)
