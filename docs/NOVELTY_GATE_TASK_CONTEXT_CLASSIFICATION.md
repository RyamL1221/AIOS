# Novelty-Gate task_context Rejection — Classification

Read-only intent-vs-behavior analysis (no code changed). Classifies why
all 22 task_context writes were rejected at the novelty add-gate in the
1×15 run (`docs/TASK_CONTEXT_WRITE_PATH_TRACE.md`): is it a **bug**,
a **miscalibration**, or **working-as-intended with a design gap**?

## Verdict

**NOT a bug. It is a design gap (no per-task_type novelty calibration)
compounded by an in-run miscalibration (the bandit was exploring strict
low arms).** The admit logic is correctly specified and correctly
implemented per its own stated intent; the rejection is a consequence of
(1) the novelty gate never being designed/tuned with task_context's
distinct similarity distribution in mind, and (2) the LinUCB bandit
being mid-exploration on strict arms during this short run.

## 1. The admit condition is correctly specified (NOT inverted)

The code's own stated intent, verbatim from the implementation:

- `_candidate_max_similarity` docstring (`aios/memory/manager.py:310`):
  "The candidate's novelty is `1 - max_similarity`; the gate compares
  `max_similarity` against the bandit's threshold … Returns `0.0` when
  there are no existing memories … (i.e. treat as maximally novel)."
- `_novelty_admits` (`aios/memory/manager.py:455`): "A candidate is
  admitted iff its max similarity to existing memories is **strictly
  below the threshold** (i.e. novel enough)." → `return max_sim < threshold`.
- `_novelty_gate_admits` docstring (`aios/memory/manager.py:390`):
  "admit iff `max_similarity < threshold` (i.e. the candidate is novel
  enough)."

Intended semantics, confirmed from the code (not from what would help
this run): **low `max_sim` = dissimilar to what's stored = novel = admit;
high `max_sim` = near-duplicate of something stored = reject.** This is
the correct direction for a novelty/dedup gate: don't re-store things you
already have. The `< threshold` comparison matches that intent exactly.
**No inversion, no wrong comparison operator.** Rules out classification
(a) bug.

Corroborating evidence it's working as intended: in the same run the
**profile** task_type shows exactly the designed behavior — the first
profile write (`max_sim=0.0`, nothing stored yet) was **admitted**, and
the 6 subsequent profile writes (`max_sim` up to 1.0, i.e. near-identical
to the already-stored profile) were **rejected as duplicates**. That is
precisely what a correct novelty gate should do. The logic is sound.

## 2. Why task_context is nonetheless always rejected — the calibration/design story

The bandit's context vector **does** distinguish task_type: `KNOWN_TASK_TYPES
= ("profile", "task")` (`aios/memory/policy.py:103`) and the one-hot uses
a substring match, so `"task_context"` matches the `"task"` slot. So the
gate *could* learn a different threshold for task_context. Two things
prevent admission in this run:

### (a) task_context has a structurally higher max_sim than profile — by content design
Observed in-run (kernel.log): task_context `max_sim` = 0.482–0.587
(mean **0.558**, n=22); profile `max_sim` = 0.0 then ~1.0 after the first
write. This is **structural, not noise**:
- task_context content **evolves each interaction** (updated goals /
  blockers / next_steps for the same project), so each new task_context
  write is **moderately similar (~0.55)** to the previous one — similar
  enough to look "not novel," different enough to be worth keeping.
- profile content is comparatively **static**, so after the first write
  every later profile write is a near-duplicate (max_sim ≈ 1.0) —
  correctly rejected — or, on the first write, maximally novel (0.0) —
  correctly admitted.

A novelty gate designed around this profile pattern (admit the first,
reject near-identical repeats) **structurally misfits** task_context,
whose legitimate updates land in the ~0.55 "moderately similar" band that
a novelty gate is built to suppress. To admit task_context the threshold
must exceed ~0.55.

### (b) The action space CAN admit task_context, but the tuned/converged region wasn't reached in-run
The novelty action space is `[0.1, 0.2, 0.3, 0.4, 0.50, 0.59, 0.68,
0.77, 0.86, 0.95]` (`aios/memory/policy.py`). Arms **≥0.59 would admit**
a 0.55-max_sim task_context. Those arms exist and are reachable. But:
- In the 1×15 run the bandit selected only novelty arms **0.1 and 0.2**
  (per the write-path trace) — the **strict** end. At those thresholds
  `0.55 > 0.2` → reject, every time. This is LinUCB **exploring** strict
  arms early in a very short run, not a stuck state.
- The offline-tuned novelty winner is **0.7** (`docs/AIOS_ARM_CONVERGENCE_REPORT.md`
  lines 28/47/100; static config `aios/config/config.yaml:148-150`
  default 0.7, per-model overrides gpt-4o 0.7 / llama 0.6 / qwen 0.6).
  **0.7 > 0.55, so the tuned/static path WOULD admit task_context.** The
  adaptive bandit simply hadn't converged toward 0.7 in 15 trials.

### (c) The action-space design never considered task_context writes
The downward extension of the novelty arms (0.1–0.4) came from `b6ffd7e`,
whose own comment says all three bandits were extended downward because
of the **similarity RETRIEVE gate** wipeout ("genuinely-relevant … run
~0.45–0.65 … BELOW the old 0.50 floor"; `docs/FILTER_TO_HARNESS_DROP_TRACE.md`).
The novelty gate was extended "for exploration completeness (Option A)" —
a side effect, explicitly **not** motivated by novelty-write behavior. And
the tuning that produced 0.7 keys on **model only, never on task_type**
(config overrides list `llm_core` values with **no `task_type` field**;
the convergence report discusses per-model winners, never per-task-type).
So no one ever calibrated the novelty threshold *for task_context vs
profile* — that per-task_type calibration was never built.

## 3. Was this a known/deferred issue? (git history)

`git log --oneline -- aios/memory/manager.py aios/memory/policy.py`
shows the novelty gate wired in `0f658ba` ("wire add_memory novelty
check … behind config flag") and the arm extension in `b6ffd7e`. **No
commit message mentions per-task_type novelty calibration, task_context
admission, or a profile-vs-task novelty distinction.** The absence
across the whole gate history indicates this is a **newly-surfaced design
gap**, not a previously-tracked-and-deferred item. (Stated as an evidence
observation, not proof of intent.)

## Classification (evidence-backed)

| Candidate | Verdict | Key evidence |
|-----------|---------|--------------|
| (a) Bug — inverted logic / wrong comparison | **NO** | `_novelty_admits` intent ("admitted iff … strictly below … novel enough") matches `max_sim < threshold`; profile writes behave correctly (admit first, reject dupes) |
| (b) Miscalibration — correct logic, wrong arm for this task_type | **PARTIAL** | Bandit explored strict arms (0.1, 0.2) in-run; tuned winner 0.7 *would* admit — so the *converged* threshold is fine, the *in-run explored* threshold isn't. A short-run/exploration miscalibration, self-correcting with more trials. |
| (c) Working as intended, design gap — no per-task_type calibration | **YES (primary)** | task_context's ~0.55 max_sim band structurally misfits a novelty gate tuned on static profile content; action-space downward extension was motivated by the retrieve gate, not novelty writes; tuning keys on model only, never task_type; no history of per-task_type novelty design |

**Primary classification: (c) design gap**, with (b) as the proximate
in-run cause. It is definitively **not (a) a bug** — the logic and
comparison are correct and provably work for profile content.

## Implication (for the next subtask, not resolved here)
The novelty (add) gate suppressing evolving task_context is a *conceptual*
mismatch: a novelty gate exists to prevent near-duplicate storage, but
task_context is *meant* to be re-written as it evolves (the TaskAgent even
has an `_upsert_task_memory` update path). The real question is whether
task_context writes should pass through the novelty gate at all, or
whether the gate needs a per-task_type threshold (admit-friendly for
task_context, strict for profile). Either is a design change, not a bug
fix. Also note: even the tuned 0.7 arm sits only ~0.15 above the observed
0.55 — a thin margin, so a per-task_type calibration (not just "let the
bandit converge to 0.7") is the more robust fix. Deferred to the design
step.
