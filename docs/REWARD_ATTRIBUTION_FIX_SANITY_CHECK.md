# Reward-Attribution Fix — Sanity Check Results

Validation of the equal-split reward attribution change (commit
`cc385c5`, `feat(aios): replace equal-credit reward attribution with
equal-split per-trial credit`). Script: `scratch_reward_attrib_sanity.py`
(uncommitted diagnostic). Uses a real `PolicyManager` with a spy wrapped
around `PolicyManager.update` to capture the raw reward passed per
decision and the value reaching each LinUCB bandit after normalization.

## Scheme chosen

**Option A — split the trial reward evenly across the total number of
bandit decisions credited in the `report_reward` call** (each decision
gets `reward_value / N`).

**Option B (content-weighted, e.g. by retrieval `similarity`) rejected
— on data-availability *and* principle:**
- Data: the `_pending_reward_decisions` tuples carry
  `(bandit_name, arm_index, context_vector, trial_id)` and **no**
  similarity. Similarity exists only at retrieval time; supporting B
  would require extending the pending structure.
- Principle: there is no single coherent per-memory relevance scalar
  shared across the three bandits — the novelty gate's signal is a
  max-similarity-to-existing measured at *add* time, while the retrieve
  gates use *query* similarity. Weighting by "similarity" would mix
  incomparable quantities across bandit types. Rejected for both reasons,
  not silently defaulted.

## Results — all five checks PASS

Trial: 3 decisions across 2 memory_ids (memA: novelty; memB: similarity
+ redundancy), `reward_value = 4.0`.

1. **Even split:** each decision received `4.0 / 3 = 1.3333` (not the
   full 4.0 of v1).
2. **Conservation:** the three per-decision rewards sum to `4.0` — the
   trial's total signal is conserved. (v1 would have injected
   `3 × 4.0 = 12.0`.)
3. **Pop-on-reward preserved:** `_pending_reward_decisions` was emptied
   for the rewarded memory_ids — consume-once mechanics unchanged.
4. **Normalization compatible:** after `PolicyManager.update`'s
   `r / JUDGE_MAX_SCORE` (÷5.0), each bandit received `0.2667` — in
   range and sensible; the existing normalization needs no re-tuning
   (the split reward stays on the 1–5 judge scale, just smaller).
5. **Differentiation:** a high-reward trial (5.0 → `1.6667`/decision)
   and a low-reward trial (1.0 → `0.3333`/decision) produce clearly
   different per-decision rewards.

`OVERALL: PASS`.

## Orthogonality confirmations

- **Reward-normalization fix (`JUDGE_MAX_SCORE` division in
  `PolicyManager.update`):** unchanged and untouched. The split happens
  in `report_reward` before `update`; normalization still divides by 5.0
  once per call. Confirmed compatible (check 4).
- **`trial_index`-as-attribution-key (accumulating-session audit):**
  orthogonal. This change alters only reward *magnitude* per decision
  (`split_reward`); the lookup key (`memory_id` in
  `_pending_reward_decisions`) and the logged `trial_id` are unchanged.
  No key semantics were modified.
