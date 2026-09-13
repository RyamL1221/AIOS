# task_context Novelty Bootstrap-Trap — Per-Condition Exposure

Read-only conditional-logic trace (no code changed) determining which of
the three paper conditions are exposed to the task_context novelty
bootstrap trap traced in `docs/UPSERT_PATH_REACHABILITY_TRACE.md`.

## Verdict (per condition)

| condition | novelty gate consulted? | exposed to trap? | basis |
|-----------|-------------------------|------------------|-------|
| `kernel_shared` (baseline) | **NO** | **NO** | both flags false → gate skipped; write unconditional |
| `kernel_shared_tuned` (static) | YES (fixed threshold) | **NO** (all 3 models) | tuned novelty ≥0.6 > observed max_sim 0.587 → first write admitted |
| `kernel_shared_adaptive` | YES (bandit) | **YES** (confirmed) | bandit explored strict arms 0.1–0.2 < 0.55 → all rejected |

**Only the adaptive condition is trapped.** Baseline never gates;
tuned's fixed thresholds all admit the first task_context write. So the
Task/Integration comparability is compromised for **one** of the three
conditions, not all three — but that one is the adaptive condition under
study.

## 1. kernel_shared (baseline) — NOT exposed (code-cited)

The `add_memory` gating conditional (`aios/memory/manager.py:~939-983`):

```
if getattr(self, "_adaptive_enabled", False):
    ... adaptive novelty gate (reject path) ...
elif getattr(self, "_static_thresholds_enabled", False):
    ... static novelty gate (reject path) ...
# (no else) -->
resp = self.provider.add_memory(memory_note)   # runs unconditionally
```

Baseline has `adaptive_policy_enabled=false` AND
`static_thresholds_enabled=false` (confirmed via `/memory/gating_status`
earlier and the config defaults). With **both** `getattr` guards false,
**neither branch executes and there is no `else`** — control falls
straight through to `self.provider.add_memory(...)`. **The novelty gate
is never consulted; every task_context create succeeds.** Baseline is
structurally immune to this trap.

**Sanity-check limitation (stated, not glossed):** no preserved
baseline kernel.log exists to empirically confirm task_context
accumulation in a prior baseline run. The current `kernel.log` covers
only the adaptive 1×15 run. The surviving `logs/policy_trials.*.jsonl`
files record only bandit select/reward events (which baseline never
emits) and do not record novelty-gate admits or per-type writes, so they
cannot serve as a baseline task_context sanity check. The baseline
"not exposed" conclusion therefore rests on the **code path** (no gate in
the flag-off branch), which is definitive, rather than on a log
spot-check, which is unavailable.

## 2. kernel_shared_tuned (static) — NOT exposed, all three models resolved

Tuned uses the static novelty gate with fixed per-model thresholds
(`aios/config/config.yaml`, `static_thresholds.novelty_threshold`):

```
default: 0.7
overrides: gpt-4o=0.7, llama3.1:8b=0.6, qwen2.5:7b=0.6
```

The gate admits iff `max_sim < threshold`. Observed task_context max_sim
in the run (gpt-4o embeddings): min 0.482, mean 0.558, **max 0.587**.
Resolving each model's fixed threshold against the observed **max**
(0.587), the strictest realistic case:

| model | tuned novelty threshold | > observed max (0.587)? | first write admitted? |
|-------|------------------------:|-------------------------|-----------------------|
| gpt-4o | 0.7 | yes (+0.113) | **YES** |
| llama3.1:8b | 0.6 | yes (+0.013) | **YES** |
| qwen2.5:7b | 0.6 | yes (+0.013) | **YES** |
| (unlisted → default) | 0.7 | yes (+0.113) | **YES** |

**No model's tuned novelty threshold is below the observed max_sim**, so
the qwen/llama check is resolved: 0.6 > 0.587 → the **first** task_context
write is admitted for every model. Once one task_context memory exists,
subsequent writes route to the TaskAgent's in-place `update_memory` path
(which bypasses the gate — `manager.py:1036-1038`), so tuned never enters
the trap. **Tuned is NOT exposed.**

**Explicit caveats on the margin (not left as "probably fine"):**
- The 0.6 thresholds for llama/qwen clear the observed max by only
  **+0.013** — a thin margin. The admit conclusion is definitive for the
  *observed* distribution, but that distribution was measured with the
  **gpt-4o/gpt-5.4** run's embeddings. task_context max_sim is
  content- and embedder-dependent; a llama/qwen run could shift the
  distribution. So: **first-write admission holds for the observed data
  with certainty for gpt-4o (wide margin) and with a thin margin for
  llama/qwen.** If a future llama/qwen run showed task_context max_sim
  creeping above 0.6, tuned could become trapped for that model — worth
  re-checking empirically per model rather than assuming the gpt-4o
  distribution transfers.
- No static/tuned kernel.log was preserved either, so tuned
  non-exposure also rests on the threshold arithmetic + code path, not a
  log spot-check.

## 3. kernel_shared_adaptive — EXPOSED (confirmed prior)

Already established (`docs/TASK_CONTEXT_WRITE_PATH_TRACE.md`,
`docs/UPSERT_PATH_REACHABILITY_TRACE.md`): the adaptive bandit selected
novelty arms **0.1 and 0.2** during the run, both below the ~0.55
task_context max_sim, so all 22 task_context creates were rejected, the
upsert precondition never bootstrapped, and no task_context memory ever
persisted.

**Nature of the exposure:** this is a bootstrap/exploration-phase issue.
The action space *contains* admitting arms (≥0.59), and the tuned target
is ~0.7, so the bandit **could self-resolve** if it converged near 0.7.
But:
- It is a **real problem for any short run** (N=15 here) that ends before
  convergence, and
- for **every cold-restart session** (the bandit is in-memory only, per
  the policy docs — no persistence in v1), so each fresh kernel restarts
  exploration from scratch and can re-trap task_context until it
  re-converges.

So even though it *can* self-resolve within a long enough single session,
adaptive is genuinely exposed for the run lengths and restart cadence
actually used.

## Impact on paper comparability

- **Baseline (kernel_shared):** task_context accumulates normally (no
  gate). Its Task/Integration scores reflect full memory availability.
- **Tuned (kernel_shared_tuned):** task_context accumulates (first write
  admitted, then updates bypass the gate). Comparable to baseline on
  availability, modulo the thin llama/qwen margin caveat.
- **Adaptive (kernel_shared_adaptive):** task_context does **not**
  accumulate in short/cold runs → its Task/Integration scores are
  measured under a **memory-starved** condition the other two don't
  share. This is a **condition-specific confound**, not a uniform one:
  comparing adaptive's Task/Integration to baseline/tuned is
  apples-to-oranges until the trap is addressed or the bandit is
  pre-converged/persisted.

## Answers to the subtask's questions
- **kernel_shared exposed?** NO — code path skips the gate entirely
  (both flags false, no `else`).
- **kernel_shared_tuned exposed?** NO for all three models — 0.7/0.6/0.6
  all exceed the observed max_sim 0.587; qwen/llama (0.6) resolved
  explicitly as admitting, with a flagged thin +0.013 margin and an
  embedder-dependence caveat.
- **kernel_shared_adaptive exposed?** YES — confirmed; a bootstrap/
  exploration issue that self-resolves only if the bandit converges
  near ~0.7 within a session, which short and cold-restarted runs do not
  reach.

## Caveats
- Exposure conclusions for baseline and tuned rest on code-path +
  threshold arithmetic against the *adaptive run's* observed max_sim;
  no preserved baseline/tuned kernel.log was available for an empirical
  task_context-accumulation spot-check (stated above).
- The observed max_sim (0.587) is from gpt-4o embeddings; per-model
  distributions may differ, which only matters for the thin-margin
  llama/qwen tuned case.
