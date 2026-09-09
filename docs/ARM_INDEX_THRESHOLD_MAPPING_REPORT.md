# Arm-Index → Threshold-Value Mapping for the LinUCB Bandits

Read-only investigation (subtask 1 of the adaptive-convergence analysis).
Establishes exactly what threshold value each `arm_index` (0–5) maps to
for each of the three bandits, so late-window `policy_action` arm
selections can be translated into comparable threshold values against
the `kernel_shared_tuned` overrides. **No kernel code was modified.**

---

## Source of truth

All arm definitions live in `aios/memory/policy.py` — a single
class-level constant `PolicyManager.ACTION_SPACES`. Confirmed (not
assumed): there is no separate config module or constants file; the
bandits are constructed directly from this dict. Direct source lines
(`aios/memory/policy.py`, lines 371–376):

```python
    ACTION_SPACES: Dict[str, List[float]] = {
        "novelty_threshold": [0.50, 0.59, 0.68, 0.77, 0.86, 0.95],
        "similarity_threshold": [0.20, 0.30, 0.40, 0.50, 0.60, 0.70],
        "redundancy_threshold": [0.70, 0.75, 0.80, 0.85, 0.90, 0.95],
    }
```

Each `LinUCBBandit` is built once from these lists (lines 387–394):

```python
        self._bandits: Dict[str, LinUCBBandit] = {
            name: LinUCBBandit(
                actions=actions,
                context_dim=CONTEXT_DIM,
                alpha=self.alpha,
            )
            for name, actions in self.ACTION_SPACES.items()
        }
```

The bandit stores the list verbatim and indexes it positionally
(lines 219–220):

```python
        self.actions: List[float] = list(actions)
        self.n_arms: int = len(self.actions)
```

and returns the value by positional index (line 303, in `select_arm`):

```python
        return self.actions[arm_index], arm_index
```

So `arm_index N` for a given bandit is unambiguously
`ACTION_SPACES[bandit][N]`.

## Mapping table (bandit → arm_index → threshold value)

| arm_index | `novelty_threshold` | `similarity_threshold` | `redundancy_threshold` |
|-----------|---------------------|------------------------|------------------------|
| 0 | 0.50 | 0.20 | 0.70 |
| 1 | 0.59 | 0.30 | 0.75 |
| 2 | 0.68 | 0.40 | 0.80 |
| 3 | 0.77 | 0.50 | 0.85 |
| 4 | 0.86 | 0.60 | 0.90 |
| 5 | 0.95 | 0.70 | 0.95 |

## Are the three lists the same across bandits? — NO

The three action spaces are **distinct**, not a shared symmetric list.
Per the per-bandit rationale comments (`policy.py` lines ~353–371):
- `novelty_threshold` spans 0.50–0.95 in irregular steps
  (0.50, 0.59, 0.68, 0.77, 0.86, 0.95).
- `similarity_threshold` spans 0.20–0.70 in 0.10 steps.
- `redundancy_threshold` spans 0.70–0.95 in 0.05 steps.

Do **not** assume symmetry: the same `arm_index` means different
threshold values (and lives in a different range) for each bandit. E.g.
`arm_index=0` is 0.50 for novelty, 0.20 for similarity, 0.70 for
redundancy.

## Is the mapping `llm_core`-dependent? — NO

**The arm_index → threshold-value mapping is static and identical for
every `llm_core` (gpt-4o, llama3.1:8b, qwen2.5:7b all see the same
lists).** `ACTION_SPACES` is a class constant with no model keying, and
`LinUCBBandit.__init__` takes no `llm_core` argument. `llm_core` enters
the system **only** through `build_context_vector(llm_core, task_type)`
(a one-hot context feature), which influences *which* arm the bandit
selects (`select_arm` = `argmax` of the context-dependent LinUCB
scores) — it does **not** change what value a given `arm_index` maps to.
`select_arm` returns `self.actions[arm_index]` from the same
model-independent `actions` list regardless of context.

**Implication for the convergence analysis (subtask 3):** translating an
`arm_index` to a threshold value needs **no** `llm_core` filtering — the
table above applies uniformly. However, `llm_core` filtering is still
required for a *different* reason established earlier: the shared
`policy_trials.jsonl` interleaves models, and *which arm was selected*
is context (hence model) dependent. So filter to the gpt-4o run window
when choosing *which* arm-selection records to analyze, then apply this
static table to convert those arm indices to values.

## Files inspected (no modifications)

- `aios/memory/policy.py` — `PolicyManager.ACTION_SPACES` (arm-value
  lists), `PolicyManager.__init__` (bandit construction),
  `LinUCBBandit.__init__` / `select_arm` (positional arm indexing),
  `build_context_vector` (where `llm_core` enters — context only).
