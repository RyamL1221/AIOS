# Trial Index → similarity_threshold Arm Mapping (1×15 run)

Extraction + reconciliation only (no files changed) for the fresh 1×15
`kernel_shared_adaptive` run (commit `d3a79cb`, kernel PID 69841, window
2026-09-13 16:30:47–16:38:03). Source:
`logs/policy_trials.subtask4fresh_1x15_20260913_163934.jsonl` (run
records = the 286 lines after the 313-line pre-run baseline) +
`../Cerebrum/results/subtask4_fresh_1x15/results_kernel_shared_adaptive.json`.

## Headline mapping

| harness `interaction_index` | similarity arm(s) selected | value | confidence | anchor |
|---|---|---|---|---|
| 0  | 0 | 0.0 | **HIGH** | reward block trial_id=0 |
| 1  | 1 | 0.1 | **HIGH** | reward block trial_id=1 |
| 2  | 2 | 0.2 | **HIGH** | reward block trial_id=2 |
| 3  | 3 | 0.3 | **HIGH** | reward block trial_id=3 |
| 4  | 4 | 0.4 | **HIGH** | reward block trial_id=4 |
| 5  | 5 | 0.5 | **HIGH** | reward block trial_id=5 |
| 6  | 6 | 0.6 | **HIGH** | reward block trial_id=6 |
| 7  | 7 | 0.7 | **HIGH** | reward block trial_id=7 |
| 8  | 8 | 0.8 | **HIGH** | reward block trial_id=8 |
| 9  | 9 | 0.9 | **HIGH** | reward block trial_id=9 |
| 10 | 10 | 0.95 | **HIGH** | reward block trial_id=10 |
| 11 | 0 | 0.0 | **HIGH** | reward block trial_id=11 |
| 12 | 8 (0.8) — *likely* | 0.8 | **LOW** | no reward anchor; trailing select block |
| 13 | 8 (0.8) — *likely* | 0.8 | **LOW** | no reward anchor; trailing select block |
| 14 | 8 (0.8) — *likely* | 0.8 | **LOW** | no reward anchor; trailing select block |

## How the anchored mapping was validated (not assumed)

`select` events carry **no** `trial_id`; `reward` events **do**. The
alignment rests on three cross-checks that all agree:

1. **`reward.trial_id` == harness `interaction_index`.** Reward
   trial_ids run 0–11; harness interaction indices run 0–14. The reward
   side is a strict prefix of the harness side (see the gap section).

2. **Each reward block's `arm_index` is uniform and equals the arm of
   the immediately-preceding select block.** `report_reward` replays
   every *pending decision* recorded for the credited memory_id, so one
   interaction that made ~5 similarity `select` calls yields ~5 `reward`
   records, all stamped with that interaction's single selected arm:

   | trial_id | #reward | reward arm | preceding select block (ts, arm) |
   |---|---|---|---|
   | 0 | 4 | 0 | 16:30:47–52 arm 0 (×4) |
   | 1 | 5 | 1 | 16:30:58–31:08 arm 1 (×5) |
   | 2 | 5 | 2 | 16:31:15–24 arm 2 (×5) |
   | 3 | 5 | 3 | 16:31:39–52 arm 3 (×5) |
   | 4 | 5 | 4 | 16:31:58–32:13 arm 4 (×5) |
   | 5 | 5 | 5 | 16:33:10–24 arm 5 (×5) |
   | 6 | 5 | 6 | 16:33:31–45 arm 6 (×5) |
   | 7 | 5 | 7 | 16:33:51–34:04 arm 7 (×5) |
   | 8 | 5 | 8 | 16:34:17–35 arm 8 (×5) |
   | 9 | 5 | 9 | 16:34:42–55 arm 9 (×5) |
   | 10 | 5 | 10 | 16:35:02–12 arm 10 (×5) |
   | 11 | 5 | 0 | 16:35:18–36:11 arm 0 (×5) |

   The select-block arm and the reward arm match for all 12 anchored
   trials, and the reward timestamp falls just after its select block —
   so the mapping is timestamp-consistent AND arm-consistent, not
   inferred from sequence position alone.

3. **Select-call count per interaction ≈ 5.** Trial 0 made 4 (the run's
   first interaction), every other anchored trial made exactly 5. These
   are the retrieval attempts within one interaction (audit + injection
   retrieval, with retries), not separate trials — so a "block of ~5
   consecutive same-arm selects" == one interaction.

## The 11-vs-15 discrepancy — EXPLAINED (not an indexing offset)

Reward trial_ids stop at **11** while the harness ran **15**
interactions (0–14). This is **not** an off-by-one/indexing offset and
**not** fewer selects — it is because trials **12, 13, 14 retrieved zero
memories**, so no reward could be attributed:

- Harness results: trials 0–11 have `injection_status = audit_inferred`
  with **1** injected memory id each; trials 12, 13, 14 have
  `injection_status = unknown` with **0** injected ids and **0**
  retrieved memories.
- Harness run log: `report_reward` was sent for trial_ids 0–11 only
  ("reporting reward for 1 memories" each). Trials 12–14 sent
  `report_reward` with an **empty** `memory_ids_involved`, so the kernel
  credited nothing and logged **no** `reward` events for them.
- Kernel.log (window 16:36–16:38): repeated
  `similarity_threshold=0.800 (arm 8) dropped all` — the **converged
  arm 8 (0.8), now past bootstrap, is honoring its strict rejection and
  wiping out the retrieval** for those trials. That wipeout is exactly
  why trials 12–14 injected nothing → no memory_id → no reward anchor.

So the reward side is a clean prefix (0–11), and the missing 12–14 are
accounted for by empty retrievals, not lost data.

## The trailing, unanchored selects (trials 12–14) — LOW confidence

After the last reward (trial 11 @16:36:15), there are **15 more**
similarity selects, **all arm 8 (0.8)**, in two time-separated bursts:
- 16:36:19–16:36:39 (7 selects)
- 16:37:34–16:38:03 (8 selects)

These belong to the 3 zero-retrieval trials (12,13,14). They are marked
**LOW confidence** in the table because:
- There is **no reward event** to anchor them to a specific
  `interaction_index` (empty `memory_ids_involved`).
- The 15 trailing selects do **not** split into 3 clean blocks of 5
  (the gap heuristic finds 2 bursts of 7 and 8), because these
  wiped-out trials retry the retrieval more than a normal trial — so the
  per-trial boundary among 12/13/14 cannot be drawn reliably from the
  select stream alone.

What **is** safe to say: all of trials 12–14's similarity selects were
**arm 8 (0.8)** — every trailing select is arm 8, and kernel.log
confirms the arm-8/0.8 wipeouts occurred in this window. So the *arm*
(8/0.8) is high-confidence for the group 12–14; only the *per-trial
split* among them is low-confidence. No arm is guessed from sequence
position for these — it is read directly from the (unanchored but
arm-uniform) select records and corroborated by the kernel gate lines.

## Timestamp cross-check gap (flagged)

The harness results JSON has **no absolute per-trial timestamps** — only
`latency_seconds` per trial (2.06, 3.63, 5.35, … ascending) and
`interaction_index`. So the harness→trial-log timestamp cross-check
could only be done via (a) the ascending latency/interaction order
matching the ascending reward-block order, and (b) the `reward.trial_id`
field itself (which is the harness `interaction_index`, set by the
harness). Both agree, but a direct wall-clock join per trial is **not
available** from the results JSON — noted as a data gap, not a
contradiction.

## Bottom line for the downstream diagnosis
- **Trials 0–11: HIGH-confidence** trial→arm map (arms 0→10 sweep, then
  trial 11 back to arm 0), anchored by matching reward blocks.
- **Trials 12–14: arm 8 (0.8) group, LOW-confidence per-trial split**,
  and — importantly for the gate-rejection diagnosis — these are exactly
  the trials where the converged 0.8 arm dropped all retrieved rows,
  producing `unknown`/0-injected and no reward.
