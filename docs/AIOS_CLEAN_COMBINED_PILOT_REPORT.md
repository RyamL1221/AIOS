# Clean Combined-Fix Pilot (2×10, N=20) — Report

First uncontaminated combined-fix pilot in this chain. The prior 5×4
pilot's "0 retrievals" alarm was traced to a separate-process diagnostic
script (not a kernel bug); the operative lesson was **do not restart the
kernel mid-pilot, and verify accumulation via a genuine later retrieval
rather than the write-time self-count**. This run applies both.

All three fixes are already committed and verified: gate-blindness
(`05772c0`), reward attribution (`cc385c5`), action-space widening
(`13cd04d`). No code changed in this run.

## Subtask 1 — Pre-flight (all passed)

- **Kernel health:** `/status` ok; `adaptive_policy_enabled=true`,
  `static_thresholds_enabled=false`.
- **Kernel process:** PID **39869**, started **Thu Sep 10 12:09:59**
  (after all three fix commits). Same process before, during, and after
  the run (see continuity below).
- **Fixes present in loaded code (spot-checked):** widened arms
  `similarity=[0.5,0.6,0.7,0.8,0.9,0.95]`, `redundancy=[0.5,...,0.95]`;
  `_raw_similarity_by_id`/`distance_to_similarity` present in mem0
  provider; `split_reward` present in manager `report_reward`.
- **Trial log:** previous `logs/policy_trials.jsonl` moved aside to
  `logs/policy_trials.preclean_20260910_132002.jsonl`; run started with a
  fresh log.

## Subtask 2 — Run (completed clean)

- Config: `--users 2 --interactions-per-user 10` (N=20),
  `--method kernel_shared_adaptive`, assistant `gpt-4o:azure`, judge
  `gpt-5.4:azure` (same models as the most recent combined pilot, for
  continuity).
- **Kernel continuity: PID 39869 at pre-flight, mid-run (checked twice),
  and post-run — never restarted.** Non-negotiable constraint satisfied.
- **20/20 interactions completed, 0 failed.** Aggregate scores: Profile
  4.15, Task 2.00, Integration 2.10, avg latency 7.5s.
- Users: `olivia_ramirez_0da89b0f_s0`, `alexandra_reynolds_0da89b0f_s1`.

## Subtask 3 — Genuine post-run retrieval verification (the corrected methodology)

Written (direct store, ground truth) vs. retrievable (fresh retrieval
issued through the **live kernel**, post-run, PID 39869 unchanged):

| User | Written (store count) | Provider `get_all` returned | Post-gate returned |
|------|----------------------|-----------------------------|--------------------|
| olivia_ramirez_0da89b0f_s0 | 11 | **11** | 2 |
| alexandra_reynolds_0da89b0f_s1 | 11 | **11** | 2 |

**Clean match at the provider layer: 11 written = 11 retrievable, both
users.** Accumulation and read-back through the live kernel work
correctly; the earlier "1 of 5" does not reproduce. This is the first
uncontaminated confirmation of accumulation via a genuine later
retrieval (not the write-time self-count). The post-gate count (2) is the
similarity gate at threshold 0.5 selecting the most query-relevant
memories — expected gate behavior, not loss.

## Subtask 4 — Gate behavior and reward signal

From the fresh trial log (179 `select` records):

| gate | selects | arm_index distribution |
|------|---------|------------------------|
| novelty | 21 | {arm 0: 21} |
| similarity | 79 | {arm 0: 79} |
| redundancy | 79 | {arm 0: 79} |

- **Gate decisions did NOT vary across the run** — every select is arm 0
  (threshold 0.5) for all three bandits. **`reward` events: 0.**
- **Reward VALUES vary** across the 20 trials: per-trial reward ∈
  {2.333, 2.667, 3.0} (derived from the judge's profile/task/integration
  sub-scores; profile scored 3/4/5, integration 2/3, task flat at 2).
  Contrasted against the old flat ~3.95-pinned baseline, the judge is
  clearly discriminating — reward is not pinned.

**Why gates stayed at arm 0 (uncontaminated confirmation of the
already-known open loop):** the bandits never received a reward.
`report_reward` fired every trial with **empty `memory_ids_involved`**,
because the injection/audit retrieval's similarity gate (threshold 0.5,
arm 0) filtered the follow-up-query matches down such that no memory_id
was credited. No credited memory_id → no `reward` event → no
`policy.update` → LinUCB stays at its init arm. This is the same reward-
loop-open condition identified in the prior chain, now observed under
verified-clean conditions (PID stable, accumulation confirmed 11/11), so
it is genuine, not a restart artifact.

### Interpretive caveats (as established, applied)

- **similarity vs redundancy correlate exactly** (both 79 selects, both
  all-arm-0). Expected — shared action space, co-firing on the same
  retrieve decision, shared equal-split reward. **Not a new finding.**
- **redundancy firing pattern** could not be assessed on reward (0
  rewards); its select count equals similarity's, consistent with
  co-firing. Thin redundancy signal remains the expected outcome of the
  partial calibration fix, not evidence of failure.
- **N=20 is far too small for any trend claim.** Only "does reward vary
  at all" is asserted (it does); no learning/convergence is claimed.

## Subtask 5 — Synthesis and go/no-go

**What this clean run establishes (uncontaminated, for the first time):**
1. Accumulation + live-kernel read-back are correct (11 written = 11
   retrievable per user) — the staleness alarm is fully retired.
2. The gate machinery fires (179 selects across all three gates) and,
   with the Subtask-1 fix, filters on real similarity (11 → 2 post-gate).
3. Judge reward varies (2.33–3.0), unlike the old flat baseline.

**What it does NOT yet show:** any bandit arm movement, because the
reward loop is still open — retrieval's similarity gate at the initial
0.5 threshold drops the follow-up-query matches, so `memory_ids_involved`
is empty and no reward reaches the bandits. This is a genuine, clean
finding: the three fixes are individually correct, but end-to-end
adaptive learning is gated behind **one remaining issue** — the
retrieve-path relevance filter yields no credited memory_ids for these
benchmark follow-up queries under the stuck-at-0.5 threshold.

**Go/No-Go: NO-GO for a larger adaptive re-run — but now for a precisely
identified, single reason, on clean data.** A larger run would reproduce
the same all-arm-0 / 0-reward outcome at higher cost, because nothing
closes the reward loop yet. This is no longer confounded by restart
contamination or unverified accumulation.

**Precondition before any larger run (the one thing left):** close the
reward loop so `report_reward` receives non-empty `memory_ids_involved`.
Concretely, ensure the injection/audit retrieval credits the memories it
retrieves (e.g. reconcile the audit's shared-policy + follow-up-query
path so at least the profile/task memories survive to attribution, or
seed/bootstrap so the similarity gate at its initial threshold does not
zero out attribution before the bandit has had any reward to move off
0.5). Once a 2×10 pilot shows non-zero `reward` events and any arm
movement, scale up per the accumulating-session pilot/ceiling framework.

## Deviations from the master prompt

- Models: used `gpt-4o` assistant / `gpt-5.4` judge for continuity with
  the most recent combined pilot (the prompt allowed qwen2.5:7b OR
  gpt-4o; picked the one the last pilot actually used).
- Subtask 3 reports the provider-level retrievable count (11) as the
  accumulation measure, plus the post-gate count (2) for completeness —
  because the gate legitimately filters by relevance, the provider count
  is the correct "retrievable/accumulated" measure, and it matches the
  written count exactly.
- No new tooling was built for the retrieval-verification methodology; it
  was applied manually for this pilot only, per scope.
- Diagnostic queries and raw results are uncommitted; only this report is
  committed.
