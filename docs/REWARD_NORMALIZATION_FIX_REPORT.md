# Reward-Normalization Fix — Verification Report

Consolidated report for the judge-reward normalization fix in the
adaptive LinUCB memory policy. This document is self-contained.

**Scope of this work:** confirm the insertion point/denominator, apply
the normalization at a single choke point, document it inline, build a
verification probe, and report pass/fail. It does **not** include the
full evaluation re-run (see §6, Out of scope).

---

## 1. Root cause (confirmed diagnosis, not re-investigated)

`MemoryManager.report_reward` forwarded the **raw** judge reward
straight into `PolicyManager.update` → `LinUCBBandit.update`. The judge
scores on a **1–5 scale**, so rewards reached the bandit at magnitudes
up to 5.0. LinUCB selects the arm with the highest `mean_estimate +
alpha * UCB_bonus`. At `alpha = 1.0` with this module's context
geometry (`x·x = 3`: two one-hot blocks + a bias term), an unexplored
arm's exploration bonus is `≈ 1.7`. A reward of up to 5.0 dwarfs that
`~1.7` bonus, so once any single arm accrued reward its exploitation
term dominated every other arm's exploration optimism permanently. The
bandit collapsed onto one arm (the "always picks arm 0 / never learns"
symptom) instead of exploring the six threshold buckets and learning a
per-context best. The reward scale, not the algorithm, was the defect.

## 2. The fix

- **File / function:** `aios/memory/policy.py`, `PolicyManager.update`.
- **Normalization formula:** `normalized_reward = float(reward_value) /
  JUDGE_MAX_SCORE`, where `JUDGE_MAX_SCORE = 5.0` is a named module
  constant. Applied as the first transformation, before the value
  reaches `self._bandits[bandit_name].update(...)`.
- **Single choke point:** `PolicyManager.update` is the sole caller of
  the per-arm `LinUCBBandit.update`, and `MemoryManager.report_reward`
  calls it once per recorded decision. Normalizing here covers all
  three bandits (novelty, similarity, redundancy) and any future bandit
  with one conversion. `manager.py` still passes the raw reward
  unchanged; `LinUCBBandit` internals and `alpha` were untouched.
- **Floor decision (max-scale division, not min-max):** the judge scale
  is **1–5, not 0–5**. We use simple `r / 5.0` (range `[0.2, 1.0]`)
  rather than a min-max rescale `(r - 1) / (5 - 1)` (range `[0, 1]`).
  Justification: the design specifies `r / 5.0`; it keeps the transform
  a single well-known constant; and preserving the judge's floor as a
  nonzero reward (`1/5 = 0.2`) is harmless for LinUCB because the bandit
  ranks arms by *relative* reward — a constant additive offset does not
  change which arm wins. There was no concrete reason the floor shift
  was needed, so the simpler scheme was chosen and stated explicitly
  rather than silently.
- **Denominator confirmed against documentation (not assumed):** the
  evaluation paper (§Evaluation) states each trial is scored by GPT-5.4
  on three dimensions — Profile Usage, Task Usage, Integration — **each
  on a 1–5 scale**. The reward is a flat per-dimension score, not a
  weighted composite, so the practical maximum is a flat 5.0.
- **Inline documentation:** the `JUDGE_MAX_SCORE` comment names the 1–5
  rubric source, the three dimensions, and the drift consequence (a
  silent re-break of the "always picks arm 0" bug if the judge scale
  changes without updating this one constant). The normalization line
  carries a comment explaining the `~1.7` UCB-bonus magnitude so the
  purpose is clear without git-blame.

## 3. Verification method

`scripts/verify_reward_normalization_probe.py` drives the **real,
patched** `PolicyManager` (imported; select/update path not mocked)
through a realistic online loop: `select_threshold` → synthetic judge
reward on the confirmed 1–5 scale → `update` (raw reward passed exactly
as `report_reward` does). 70 iterations per (bandit, context). Synthetic
rewards: designed best arm draws `N(4.6, 0.4)`, others `N(1.6, 0.4)`,
clipped to `[1, 5]` — noisy, realistic feedback rather than a clean
step. No kernel server, Ollama, or provider needed (bandits are pure
numpy).

## 4. Verification results

### Axis 1 — Exploration (single context gpt-4o/profile, designed best arm = 4, non-zero)

| Bandit | Arm distribution (arm0..arm5) | Distinct arms | Non-arm0 selections | Converged argmax |
|--------|-------------------------------|---------------|---------------------|------------------|
| `novelty_threshold`    | 2 / 2 / 1 / 2 / 61 / 2 | 6 | 68 | 4 |
| `similarity_threshold` | 2 / 2 / 2 / 2 / 61 / 1 | 6 | 68 | 4 |
| `redundancy_threshold` | 2 / 2 / 1 / 2 / 61 / 2 | 6 | 68 | 4 |

All six arms explored; the converged argmax is the designed non-zero
best arm (4), not arm 0.

### Axis 2 — Context-sensitivity (one manager per bandit, 3 interleaved contexts, distinct designed best arm each)

Designed best arm per context: gpt-4o/profile → 1, llama3.1:8b/task →
3, qwen2.5:7b/integration → 5.

| Bandit | ctx gpt-4o/profile | ctx llama/task | ctx qwen/integration | Distinct converged |
|--------|-------------------|----------------|----------------------|--------------------|
| `novelty_threshold`    | designed 1 → converged 1 ✓ | designed 3 → 3 ✓ | designed 5 → 5 ✓ | 3 |
| `similarity_threshold` | designed 1 → converged 1 ✓ | designed 3 → 3 ✓ | designed 5 → 5 ✓ | 3 |
| `redundancy_threshold` | designed 1 → converged 1 ✓ | designed 3 → 3 ✓ | designed 5 → 5 ✓ | 3 |

Every one of the 9 (bandit × context) cases converged to the
context-specific designed best arm, and each bandit produced 3 distinct
converged arms across the 3 contexts — so the choice tracks the reward
signal per context, not aggregate variety.

### Teeth check (probe would have caught the pre-fix bug)

Feeding the **raw** 1–5 reward straight to the bandit (bypassing the
normalization, simulating the pre-fix path) collapsed exploration to
`{arm0: 50, arm1: 20}` — arms 2–5 never explored — and converged to arm
1, which does **not** match the designed best arm 4. This confirms the
probe genuinely distinguishes the fixed path from the bug rather than
passing trivially.

## 5. Pass/fail confirmation

- **Axis 1 (exploration): PASS** — all three bandits explore arms
  beyond arm 0 and converge to the designed non-zero best arm.
- **Axis 2 (context-sensitivity): PASS** — converged arm tracks the
  per-context designed best arm in all 9 cases, with distinct winners
  across contexts.

Both required verification checks passed. The existing unit suite
(`tests/modules/memory/test_policy_manager.py`, 13 tests) and the
reward-loop integration tests
(`tests/modules/memory/test_adaptive_retrieval_gate.py`, 7 tests) also
still pass after the change.

## 6. Explicitly out of scope (not silently dropped)

These three items were called out and are **not** addressed here:

1. **Full 450-trial re-run** — a separate, later decision. Not started
   or scheduled by this work. The probe is fix-verification only, not
   the evaluation.
2. **`trial_id: None` logging gap** — tracked separately; it is a
   logging/observability nit, **not** a kernel bug. Not fixed here.
3. **Sparse-memory-retrieval finding** (zero `written_memories`,
   `shared_memory_count = 2` in 97–100% of trials) — flagged as a
   **prerequisite to resolve or explicitly accept before committing to
   the full re-run**. It was **not** investigated as part of this work.
   Whoever authorizes the 450-trial re-run should decide on this first;
   a re-run over sparse retrieval data may not exercise the gates
   meaningfully.

## 7. Commits (traceability)

| Commit | Message |
|--------|---------|
| `7c0a3a4` | `docs(aios): confirm reward normalization insertion point and denominator` |
| `286c10c` | `fix(aios): normalize judge reward to UCB bonus scale in PolicyManager.update` |
| `a4cef0f` | `docs(aios): expand inline documentation for judge reward normalization` |
| `44ed99a` | `test(aios): add verification probe for reward-normalization fix` |

(The confirmation commit `7c0a3a4` from the pre-work investigation is
listed for completeness; the three commits produced by the fix →
document → probe sequence are `286c10c`, `a4cef0f`, `44ed99a`.)

## 8. Suggested steering update (flagged, NOT applied)

`.kiro/steering/sdk-and-api.md` (~line 71) currently reads: "The
handler is still a logging stub — no bandit routing yet (arrives in a
later subtask)." That statement is now **stale** — the `report_reward`
→ `PolicyManager.update` reward loop is wired and, as of this work,
verified. This line should be updated to reflect that the reward loop
is live (and normalized), but that change is **flagged here, not
applied**, pending confirmation.
