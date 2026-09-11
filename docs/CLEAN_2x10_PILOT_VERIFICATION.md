# Subtask 4 — Clean 2×10 pilot: reward-loop closure on a live kernel

First live verification since the similarity-gate bootstrap fix (and its
per-arm narrowing) was implemented. Real Azure spend, gpt-4o assistant /
gpt-5.4 judge, `kernel_shared_adaptive`, `--users 2
--interactions-per-user 10` (20 interactions).

**Bottom line: the reward loop closes end-to-end on a live kernel.**
Reward events went from the historical **0 → 110**, and all three
bandits **moved off arm 0**. This is a closure/mechanism result only —
NOT a learning claim (see caveats).

---

## Pre-flight (all confirmed)

- **Kernel restarted fresh** before the run to clear leftover state, then
  left untouched throughout. **PID 42753**, started **Thu Sep 10
  15:58:02 2026**; confirmed still PID 42753 (elapsed ~14:34) after the
  run — **no mid-run restart**.
- `/memory/gating_status`: `adaptive_policy_enabled: true`,
  `static_thresholds_enabled: false` — `kernel_shared_adaptive` live.
- Fixes present: three originals committed (`05772c0` real similarity,
  `cc385c5` equal-split attribution, `13cd04d` widened action spaces);
  the bootstrap + per-arm fail-open present on disk and loaded by this
  fresh kernel (started after those working-tree edits).
- Prior `policy_trials.jsonl` moved aside to
  `logs/policy_trials.presubtask4_20260910_155435.jsonl`; this run wrote
  a clean `logs/policy_trials.jsonl`.
- Results isolated to `Cerebrum/results/subtask4_2x10_clean/`.

## Reward events: 0 → 110 (the loop closed)

From the isolated `logs/policy_trials.jsonl` (288 records total):

| event | count |
|-------|------:|
| `select` | 178 |
| `reward` | **110** |
| distinct `trial_id`s | 9 |

Historical premise-confirmation run (same 2×10 config, pre-fix): **0
reward events**. This run: **110**. Kernel-side corroboration in
`kernel.log`: **9** `report_reward: reward applied to N arm(s)` lines
and **9** `report_reward` calls carrying a non-empty
`memory_ids_involved` (vs. 11 empty).

## Arms moved off arm 0 (pass signal at this scale)

`select` arm distribution per bandit (arm 0 = the stuck-forever state in
the historical run):

| bandit | arm selections |
|--------|----------------|
| novelty_threshold | `{0: 2, 1: 22}` |
| similarity_threshold | `{0: 14, 1: 4, 2: 47, 3: 4, 4: 4, 5: 4}` |
| redundancy_threshold | `{0: 14, 1: 4, 2: 47, 3: 4, 4: 4, 5: 4}` |

Every bandit selected non-zero arms; novelty spent most of its
selections on arm 1, and similarity/redundancy ranged across all six
arms (dominated by arm 2). `reward` updates likewise landed across arms
0–5 on similarity/redundancy. **At least one non-arm-0 selection was the
pass bar; all three cleared it comfortably.**

## Fail-open mechanism engaged live (both branches)

`kernel.log` shows the narrowed per-arm fail-open actually firing during
the run — not just in synthetic tests:

- **bootstrapping (fail-open kept the rows): 20** occurrences — an
  under-validated arm's total wipeout was overridden so ≥1 id reached
  the reward path.
- **honoring converged arm (strict rejection kept): 43** occurrences —
  once arms had learning signal, wipeouts were honored (the narrowing
  works; the gate's ceiling is intact).

The presence of BOTH branches is the live confirmation that the fix's
mechanism is engaging as designed: it opened when arms were uninformed
and closed once they were validated.

## Genuine post-run retrieval check (fresh query, NOT self-report)

Queried the two users' per-user ChromaDB collections directly after the
run (bypassing any write-time `total_stored_for_user` self-report):

| user (session) | retrievable records | breakdown | shared |
|----------------|--------------------:|-----------|-------:|
| `emily_carter` (s0) | **12** | 1 profile + 1 task_context + 10 conversation | 2 |
| `alex_morgan` (s1) | **12** | 1 profile + 1 task_context + 10 conversation | 2 |

Both users' profile + task_context memories are present, `shared`, and
retrievable. Writes landed for both.

## The 14-vs-0 injected split (honest note)

Harness `injected_memory_ids`: **9 of 20** trials non-empty. But the
split by user is lopsided — `emily_carter` (s0) accounts for **14
injected ids across its 10 interactions**, while `alex_morgan` (s1) had
**0** injected across its 10.

This is NOT write loss: the post-run retrieval check above shows s1 has
the same 12 retrievable records (including its 2 shared memories) as s0.
`alex_morgan`'s zero is a **retrieval-time outcome** — for that user's
follow-up queries the shared rows either fell below the (learned)
similarity arm on a validated arm, or weren't surfaced by the audit — a
per-user retrieval characteristic at N=20, not a data or write-path
failure. Worth watching at larger N, but it does not undercut the
closure result: the loop demonstrably closed on the trials where
retrieval returned ids (9 trials, 110 reward events).

## Interpretive caveats (asserted, not optional)

- **This is "the loop closes / arms can move," NOT "it learns."** N=20
  (9 rewarded trials) is far too small to claim a learning trend or that
  any converged arm is *good*. The only claims supported: reward events
  are non-zero, and arm selection is no longer pinned to arm 0.
- **similarity and redundancy correlate by construction.** They co-fire
  on the same retrieve decision and share an identical action space —
  their near-identical `select` distributions here are expected, not an
  independent signal.
- **redundancy fires rarely / thinly by design** (only when ≥2 survivors
  are near-duplicates); its arm movement here rides on the shared
  retrieve co-fire, and no independent redundancy effect should be read
  from N=20.
- The judge reward's absolute values are not analyzed here; only that
  reward *flowed* and *moved arms*.

## Status

Reward-loop closure is confirmed on a live kernel. **No code changes were
made in this task** (verification only). Per the status gate, scaling to
a larger run is **not** decided here — that is Subtask 5's go/no-go,
pending review of this result.

### Artifacts
- Trial log: `logs/policy_trials.jsonl` (this run) — 178 select + 110 reward.
- Harness results: `Cerebrum/results/subtask4_2x10_clean/` (JSON + CSV)
  and `results/subtask4_2x10_clean_run.log`.
- Pre-run trial log preserved: `logs/policy_trials.presubtask4_20260910_155435.jsonl`.
- Kernel: PID 42753, `kernel.log`.
