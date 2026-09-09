# gpt-4o Adaptive Arm-Convergence vs Tuned Overrides — Synthesis

Final synthesis of the four-subtask analysis of whether the
`kernel_shared_adaptive` LinUCB bandits converged, over the gpt-4o
150-trial run, toward the offline-tuned (`kernel_shared_tuned`)
per-model thresholds — i.e. whether "adaptive statistically matches
tuned" is explained by online convergence. Builds on the null-
`policy_action` determination (`POLICY_ACTION_NULL_INVESTIGATION_REPORT.md`),
the scoped join, the arm-index → value mapping
(`ARM_INDEX_THRESHOLD_MAPPING_REPORT.md`), and the LinUCB reward-
normalization fix (`286c10c`/`a4cef0f`/`44ed99a`,
`REWARD_NORMALIZATION_FIX_REPORT.md`).

**No kernel code was modified in any subtask of this analysis.**

---

## Inputs (all verified)

- **Arm → value mapping** (`aios/memory/policy.py` `ACTION_SPACES`,
  static, model-independent — confirmed in subtask 1):
  - novelty: `[0.50, 0.59, 0.68, 0.77, 0.86, 0.95]`
  - similarity: `[0.20, 0.30, 0.40, 0.50, 0.60, 0.70]`
  - redundancy: `[0.70, 0.75, 0.80, 0.85, 0.90, 0.95]`
- **gpt-4o tuned winners** (authoritative:
  `Cerebrum/benchmarks/shared_memory/threshold_search_progress/full-search-360/summary.json`,
  mirrored in `aios/config/config.yaml` `static_thresholds`):
  novelty **0.7**, similarity **0.8**, redundancy **0.5**.
- **Late-window selection distributions** (subtask 3; last 25% of each
  bandit's own gpt-4o select events, value-column cross-checked PASS on
  all 1194 rows).

## The one caveat that governs every classification below

Subtask 3's signal is a **selection-frequency argmax** (which arm was
picked most often in the late window), **not a mean-estimate argmax**
(which arm the bandit actually learned to value highest). LinUCB keeps
an exploration bonus, so a genuinely-converged bandit can still spread
its *selections* across arms, and conversely a spread of selections does
not prove non-convergence. **Therefore none of the classifications below
can confirm or rule out true convergence** — they describe selection
behavior only. This caveat applies to all three bandits; it is stated
once here rather than repeated per bandit.

## Per-bandit comparison

### novelty_threshold — tuned 0.7 (within arm range, no exact arm)
- 0.7 lies inside the arm range [0.50, 0.95] but is **not** an arm value;
  nearest arms are 0.68 (arm2) and 0.77 (arm3).
- Late window: last 75 of 298. Distribution (arm:count):
  `0:13  1:10  2:13  3:15  4:12  5:12`. Mode = **arm3 (0.77)** at 15/75
  = **20.0%**.
- **Classification: NO CONVERGENCE (by selection frequency).** The mode
  (20%) is barely above the 16.7% uniform baseline; all six arms are
  within 10–15 counts. The mode arm (0.77) does happen to be the nearest
  arm *above* tuned 0.7, but at 20% that is not a convergence signal —
  it is a near-even spread.

### similarity_threshold — tuned 0.8 (OUTSIDE arm range)
- **The gpt-4o tuned value 0.8 is outside the similarity arm range
  [0.20, 0.70] entirely** (above the max arm, 0.70). *(This corrects the
  master prompt, which stated similarity tuned = 0.70 with an exact-match
  arm; the authoritative search winner is 0.8 — see Deviations.)*
- Late window: last 112 of 448. Distribution:
  `0:21  1:18  2:24  3:22  4:12  5:15`. Mode = **arm2 (0.40)** at 24/112
  = **21.4%**.
- **Classification: NOT MEANINGFULLY ASSESSABLE.** Convergence toward
  0.8 is impossible to express — the bandit cannot select an arm it does
  not have. The late-window behavior is a near-even spread with a mode
  (0.40) far below the tuned target. "No convergence" here is not a fact
  about the bandit's learning; it is the arm-range/tuned-value mismatch
  (below).

### redundancy_threshold — tuned 0.5 (OUTSIDE arm range)
- **The gpt-4o tuned value 0.5 is outside the redundancy arm range
  [0.70, 0.95] entirely** (below the min arm, 0.70).
- Late window: last 112 of 448. Distribution:
  `0:21  1:18  2:24  3:22  4:12  5:15`. Mode = **arm2 (0.80)** at 24/112
  = **21.4%**.
- **Classification: NOT MEANINGFULLY ASSESSABLE**, same reason as
  similarity: the tuned target is unreachable in the action space, so a
  "no convergence" label reflects the space mismatch, not bandit
  behavior.

## Two structural findings, not "3-for-3 non-convergence"

1. **similarity and redundancy are ONE shared signal, not two
   independent ones.** Their late-window arm-index distributions are
   **byte-identical** (`21,18,24,22,12,15`) because both gates fire
   together on every retrieve, over the same context, in lockstep — only
   their arm→value maps differ. So the evidence is really **2 bandits:
   novelty (independent) + a single similarity/redundancy co-firing
   pattern** — not three independent confirmations. Any write-up must not
   present this as 3-for-3.

2. **The tuned search space and the adaptive action space do not align
   for 2 of 3 bandits (the more important structural finding).** For
   gpt-4o, the offline search's winning values are **outside the
   adaptive bandit's own arms** for both similarity (tuned 0.8 vs arms
   ≤0.70) and redundancy (tuned 0.5 vs arms ≥0.70). Only novelty (0.7 in
   [0.50, 0.95]) is even in-range. This means the adaptive policy and the
   tuned policy were **searching different threshold spaces** for two of
   the three gates — the adaptive bandit could not have reproduced the
   tuned similarity/redundancy values even in principle. That is a
   design-level mismatch worth flagging for the paper, independent of
   (and arguably more consequential than) the convergence question.

## Direct answer to the original question

**Does this analysis explain "adaptive statistically matches tuned"? No
— it neither confirms nor rules out convergence, and it is not a
mechanistic explanation.**

- The only signal available (late-window selection frequency) shows a
  **near-even spread** for all three bandits (modes 20–21%, barely above
  the 16.7% uniform floor). That is consistent with LinUCB still
  exploring, but because selection frequency is not the mean-estimate
  argmax, it **cannot** be read as "the bandit did not converge."
- For 2 of the 3 bandits the comparison is moot regardless: the tuned
  target is **outside the adaptive action space**, so "matching tuned"
  via arm convergence was never possible for similarity/redundancy.
- Consequently, the observed "adaptive ≈ tuned" *outcome* (judge scores)
  is **not explained** by this arm-level analysis. It remains open
  whether the two conditions land at similar scores for reasons
  unrelated to threshold convergence (e.g. the gates rarely being the
  binding constraint on this data — cf. the redundancy-calibration
  caveat in `memory-providers.md`, where observed pairwise similarities
  sit below even the lowest redundancy arm). A mechanistic explanation
  would require (a) the mean-estimate argmax per context rather than
  selection frequency, and (b) reconciling the adaptive vs tuned action
  spaces — neither of which this analysis performed.

## Deviations from the master prompt

- **similarity tuned value corrected 0.70 → 0.8.** The master prompt
  stated gpt-4o similarity tuned = 0.70 with an exact-match arm (arm5).
  The authoritative search winner (`full-search-360/summary.json`, and
  `config.yaml`) is **0.8**, which is **outside** the similarity arm
  range. So the arm-range/tuned-value mismatch the prompt flagged for
  redundancy **also applies to similarity** — two bandits, not one, have
  an unreachable tuned target. This strengthens structural finding (2).
- No other deviations. The redundancy out-of-range flag, the
  selection-vs-mean-estimate caveat, and the correlated-not-independent
  note were applied as instructed.

## Scope / non-modification

Read-only analysis over `logs/policy_trials.jsonl` (scoped gpt-4o
window) and the tuned-search artifacts. No AIOS kernel code, no
`policy.py`, no Cerebrum source modified. Intermediate dataset:
`logs/gpt4o_select_events_scoped.csv` (gitignored scratch).
