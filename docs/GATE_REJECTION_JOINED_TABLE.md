# Joined Per-Trial Table + Outcome Comparison (1×15 run)

Table-building + comparison only (no files changed). Joins the
similarity-arm mapping (`docs/TRIAL_TO_SIMILARITY_ARM_MAPPING.md`), the
fail-open classification (`docs/FAILOPEN_EVENT_ACCOUNTING.md`), injection
counts, and the judge's per-trial scores from
`../Cerebrum/results/subtask4_fresh_1x15/results_kernel_shared_adaptive.json`
for the fresh 1×15 `kernel_shared_adaptive` run (commit `d3a79cb`).

## Complete per-trial table (all 15 trials, all fields populated)

| trial | sim arm (val) | outcome | inj | task | integ | profile | inj_status | map conf |
|------:|---------------|---------|----:|-----:|------:|--------:|------------|----------|
| 0  | 0 (0.0)  | clean            | 1 | 1 | 1 | 4 | audit_inferred | HIGH |
| 1  | 1 (0.1)  | clean            | 1 | 2 | 2 | 4 | audit_inferred | HIGH |
| 2  | 2 (0.2)  | clean            | 1 | 2 | 2 | 4 | audit_inferred | HIGH |
| 3  | 3 (0.3)  | clean            | 1 | 2 | 3 | 4 | audit_inferred | HIGH |
| 4  | 4 (0.4)  | clean            | 1 | 2 | 2 | 4 | audit_inferred | HIGH |
| 5  | 5 (0.5)  | rescued          | 1 | 2 | 3 | 4 | audit_inferred | HIGH |
| 6  | 6 (0.6)  | rescued          | 1 | 2 | 3 | 5 | audit_inferred | HIGH |
| 7  | 7 (0.7)  | rescued          | 1 | 2 | 2 | 4 | audit_inferred | HIGH |
| 8  | 8 (0.8)  | rescued          | 1 | 3 | 4 | 4 | audit_inferred | HIGH |
| 9  | 9 (0.9)  | rescued          | 1 | 2 | 2 | 4 | audit_inferred | HIGH |
| 10 | 10 (0.95)| rescued          | 1 | 2 | 2 | 5 | audit_inferred | HIGH |
| 11 | 0 (0.0)  | clean            | 1 | 2 | 2 | 4 | audit_inferred | HIGH |
| 12 | 8 (0.8)  | permanently_wiped| 0 | 2 | 2 | 4 | unknown | LOW-split |
| 13 | 8 (0.8)  | permanently_wiped| 0 | 2 | 3 | 4 | unknown | LOW-split |
| 14 | 8 (0.8)  | permanently_wiped| 0 | 2 | 2 | 4 | unknown | LOW-split |

(`inj` = injected memory count; scores are the gpt-5.4 judge's 1–5
per-dimension scores. `map conf` per Subtask 2: trials 12–14 share the
arm-8/0.8 group but their per-trial split is low-confidence.)

## Do trials 12–14 still get scored? YES.

The three permanently-wiped trials (0 injected, `unknown` status) **did**
receive full judge scores — the assistant still responded, just without
any injected memory. Their scores: task `[2,2,2]`, integration `[2,3,2]`,
profile `[4,4,4]`. So the cleanest test the master prompt asked for is
answerable.

## Group comparison (clean vs rescued vs permanently_wiped)

| group | trials | n | task mean [range] | integ mean [range] | profile mean [range] |
|-------|--------|--:|-------------------|--------------------|----------------------|
| clean | 0–4, 11 | 6 | **1.833** [1,2] | **2.000** [1,3] | 4.000 [4,4] |
| rescued | 5–10 | 6 | **2.167** [2,3] | **2.667** [2,4] | 4.333 [4,5] |
| permanently_wiped | 12–14 | 3 | **2.000** [2,2] | **2.333** [2,3] | 4.000 [4,4] |

## Verdict: this COMPLICATES the gate-over-rejection hypothesis (does not support it)

The hypothesis was: if permanently_wiped trials score notably *lower*
than clean trials, that is direct evidence over-rejection hurts the
outcome. **The data does not show that.**

- **permanently_wiped ≈ clean, not lower.** Wiped task 2.00 vs clean
  1.83; wiped integ 2.33 vs clean 2.00; profile identical at 4.00.
  Losing the one injected memory entirely (12–14) did **not** measurably
  hurt any score dimension versus the clean trials.
- **rescued scored *highest*, not lowest.** If fail-open rescues were
  salvaging value, we'd at least expect rescued ≥ wiped; they are
  (task 2.17, integ 2.67). But rescued also edges out clean, which the
  over-rejection story doesn't predict — so this is more plausibly
  trial-position / judge noise than a rescue effect.
- **The differences are within noise at this N.** Groups of 6/6/3 on a
  discrete 1–5 scale with ~0.2–0.7 mean gaps and fully overlapping ranges
  support no directional claim.

### The confound that explains the flat scores (important)
Across **all** injecting trials (0–11) the injected item was **always the
same single profile memory** (`a0162e92…`, `memory_type=profile`,
`owner_agent=profile_agent`) — never a task_context or conversation
memory. Consequences:

- **Profile score is pinned at ~4.0 everywhere, including the wiped
  trials** — the assistant reflects the profile whether or not that
  memory is injected (the accumulating single-user session and the
  profile itself carry it). So injection presence barely moves profile.
- **Task score is pinned low (~2) everywhere** — no task_context memory
  ever survived retrieval for any trial, so the task dimension had
  nothing to gain from injection in any group.
- Net: with only one profile memory ever passing the gate, injected-vs-
  not is a *weak* lever on these scores, so the outcome categories can't
  separate. The gate's over-rejection is real at the mechanism level
  (Subtask 3), but in THIS run it did not translate into a measurable
  score penalty because the surviving content (a profile memory) wasn't
  what the low task scores needed anyway.

## Honest bottom line
- The per-trial join is complete and the mechanism finding from Subtask 3
  stands: trials 5–10 were fail-open rescues, 12–14 were honored wipeouts.
- **But the outcome scores do NOT support "over-rejection hurt quality"
  in this run.** permanently_wiped trials scored on par with clean ones,
  and rescued scored highest — the opposite of the predicted gradient.
- The most defensible reading at N=15: the outcome signal is **dominated
  by the single-profile-memory confound and small-N noise**, so this run
  can neither confirm nor refute that gate over-rejection hurts task/
  integration quality. A larger run with task_context memories that
  actually clear (or are meant to clear) the gate — and enough trials to
  separate outcome groups from position/noise — is required to answer it.
  Reported as inconclusive rather than forced into the hypothesis.
