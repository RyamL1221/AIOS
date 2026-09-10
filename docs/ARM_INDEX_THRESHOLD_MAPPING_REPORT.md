# Arm-Index → Threshold-Value Mapping for the LinUCB Bandits

Establishes exactly what threshold value each `arm_index` (0–5) maps to
for each of the three bandits, so `policy_action` arm selections can be
translated into comparable threshold values against the
`kernel_shared_tuned` overrides.

> **UPDATED (action-space widening).** The `similarity_threshold` and
> `redundancy_threshold` action spaces were **widened** so their arms
> can reach all three models' offline-tuned winners (they previously
> could not — see "Tuned-winner reachability" below). This report has
> been corrected to the new mapping. The original narrow ranges
> (similarity `0.20–0.70`, redundancy `0.70–0.95`) are retained inline
> only as struck-through historical context. `novelty_threshold` is
> unchanged.

---

## Source of truth

All arm definitions live in `aios/memory/policy.py` — a single
class-level constant `PolicyManager.ACTION_SPACES`. Confirmed (not
assumed): there is no separate config module or constants file; the
bandits are constructed directly from this dict. Current source:

```python
    ACTION_SPACES: Dict[str, List[float]] = {
        "novelty_threshold": [0.50, 0.59, 0.68, 0.77, 0.86, 0.95],
        "similarity_threshold": [0.50, 0.60, 0.70, 0.80, 0.90, 0.95],
        "redundancy_threshold": [0.50, 0.60, 0.70, 0.80, 0.90, 0.95],
    }
```

Prior (pre-widening) values, for historical reference only:

```python
    #   similarity_threshold: [0.20, 0.30, 0.40, 0.50, 0.60, 0.70]
    #   redundancy_threshold: [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]
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
| 0 | 0.50 | 0.50 | 0.50 |
| 1 | 0.59 | 0.60 | 0.60 |
| 2 | 0.68 | 0.70 | 0.70 |
| 3 | 0.77 | 0.80 | 0.80 |
| 4 | 0.86 | 0.90 | 0.90 |
| 5 | 0.95 | 0.95 | 0.95 |

> Historical (pre-widening) mapping — do **not** use for post-widening
> runs:
>
> | arm_index | `similarity_threshold` (old) | `redundancy_threshold` (old) |
> |-----------|------------------------------|------------------------------|
> | 0 | 0.20 | 0.70 |
> | 1 | 0.30 | 0.75 |
> | 2 | 0.40 | 0.80 |
> | 3 | 0.50 | 0.85 |
> | 4 | 0.60 | 0.90 |
> | 5 | 0.70 | 0.95 |
>
> Any `policy_trials.jsonl` produced BEFORE the widening must be
> interpreted with the old table; runs AFTER it use the new table above.

## Tuned-winner reachability (why the widening was made)

The offline `kernel_shared_tuned` winners
(`memory.static_thresholds.*.overrides` in `config.yaml`) are:

| bandit | gpt-4o | llama3.1:8b | qwen2.5:7b | reachable pre-widening? |
|--------|--------|-------------|------------|-------------------------|
| similarity_threshold | 0.8 | 0.5 | 0.9 | **No** — old max was 0.70, so 0.8 & 0.9 unreachable |
| redundancy_threshold | 0.5 | 0.5 | 0.7 | **No** — old min was 0.70, so 0.5 unreachable |
| novelty_threshold | 0.7 | 0.6 | 0.6 | Yes (inside 0.50–0.95); left unchanged |

Post-widening, every similarity and redundancy winner is now an **exact
arm**: similarity winners 0.5, 0.8, 0.9 are arms 0, 3, 4; redundancy
winners 0.5 and 0.7 are arms 0 and 2. The bandits can therefore
converge to the tuned optima, which was structurally impossible before.

## Are the three lists the same across bandits? — PARTIALLY (post-widening)

Per the per-bandit rationale comments in `policy.py`:
- `novelty_threshold` spans 0.50–0.95 in irregular steps
  (0.50, 0.59, 0.68, 0.77, 0.86, 0.95) — unchanged by the widening.
- `similarity_threshold` now spans 0.50–0.95
  (0.50, 0.60, 0.70, 0.80, 0.90, 0.95).
- `redundancy_threshold` now spans 0.50–0.95
  (0.50, 0.60, 0.70, 0.80, 0.90, 0.95).

After the widening, `similarity_threshold` and `redundancy_threshold`
happen to share the **same** list, but `novelty_threshold` is still
distinct (irregular steps). Do **not** assume all three are symmetric:
`arm_index=0` is 0.50 for all three now, but higher indices diverge
(e.g. `arm_index=1` is 0.59 for novelty vs 0.60 for the other two). Treat
each bandit's list independently and use the table above.

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
