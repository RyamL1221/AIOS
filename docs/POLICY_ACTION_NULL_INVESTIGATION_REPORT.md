# Null `policy_action` Investigation — Determination Report

Investigation into why `policy_action` is `null` across all 150 trials
of the `kernel_shared_adaptive` benchmark run (GPT-4o, with the LinUCB
reward-normalization fix `286c10c`/`a4cef0f`/`44ed99a` and the ChromaDB
truncation-collision fix `7065d09`/`adfcaeb`/`a3da418` applied). Read-and
-trace only — **no code was modified** (see §6 on the fix judgment).

---

## Determination

**Explanation (a): a harness-side field-population step, not a bandit
malfunction.** The adaptive LinUCB policy was fully exercised during the
run; the null `policy_action` is a cosmetic, expected-pre-join state, not
evidence that the adaptive condition went untested. Even more precisely
than "logging gap": `policy_action` is populated by a **documented,
standalone post-hoc join step** that was simply not run against this
run's output yet.

**The run's results (judge scores, memory counts) are unaffected and can
be trusted as a valid test of the adaptive condition.** Explanation (b)
is conclusively ruled out.

## Evidence

### 1. The adaptive policy was fully exercised (rules out (b))

The run's gating status reported `adaptive_policy_enabled: true` (given).
`kernel.log` confirms the kernel acted on it:

- `aios.memory.policy - INFO - PolicyManager initialized: bandits=['novelty_threshold', 'similarity_threshold', 'redundancy_threshold'], context_dim=8, alpha=1.000`
- `aios.memory.manager - INFO - Adaptive threshold policy ENABLED (alpha=1.000, trial_log=logs/policy_trials.jsonl)`

Call counts over the run (from the existing `policy.py` / `manager.py`
logging — no new logging added):

| Signal | Count |
|--------|-------|
| `select_threshold[novelty_threshold]` | 485 |
| `select_threshold[similarity_threshold]` | 729 |
| `select_threshold[redundancy_threshold]` | 729 |
| `Recorded novelty decision for memory_id=...` | 485 |
| `report_reward: reward applied` | 243 |
| `logs/policy_trials.jsonl` records | 17,986 (7,214 `select` + 10,772 `reward`) |

The bandit selected arms and received rewards continuously across the
run. `select`/`update` were not silently no-op'd; there is no config
guard that disabled them (the `_adaptive_enabled` branch in
`manager.py.address_request` fired, as the "Recorded novelty decision"
and "retrieve gate: …_threshold=… kept …" log lines show).

### 2. The kernel never puts arm selections in the HTTP response — by design

`aios/syscall/syscall.py`:
- `execute_llm_syscall` returns
  `{response, token_usage, start_times, end_times, waiting_times, turnaround_times}`.
- `_execute_syscall` (the memory/tool/storage path) returns the same
  generic envelope.

No field in any `/query` response carries a bandit arm selection. The
arm decisions live entirely kernel-side: in
`MemoryManager._pending_reward_decisions` (transient, for reward
attribution) and, durably, in `logs/policy_trials.jsonl` via
`PolicyTrialLogger`. `grep "policy_action"` over the entire AIOS kernel
repo and the installed `cerebrum` package returns **zero** hits — the
kernel does not emit, and was never designed to emit, a `policy_action`
field on the wire.

### 3. Cerebrum populates `policy_action` out-of-band, after the run

The field is defined in the Cerebrum benchmark repo (`../Cerebrum`),
`benchmarks/shared_memory/models.py`:

```python
class TrialResult(BaseModel):
    ...
    # Adaptive-policy reward records attributed to this trial by the
    # standalone post-hoc join (benchmarks/shared_memory/join_policy_actions.py).
    # NOT threaded through the live path (AssistantAgent/PipelineResult are
    # untouched) — populated after the run by joining the kernel's
    # policy_trials.jsonl reward events on reward.trial_id == trial_index.
    # None = not yet joined; [] = joined but no reward records for this trial.
    policy_action: Optional[List[PolicyActionEntry]] = None
```

The docstring is dispositive: **`None` means "not yet joined."** The live
trial path (`AgentPipeline` / `PipelineResult` / `run_single_trial`)
never reads a `policy_action` from the kernel response — it can't,
because the kernel doesn't send one (§2). Enrichment is a separate
offline step, `benchmarks/shared_memory/join_policy_actions.py`, which
reads `policy_trials.jsonl`, keeps `event == "reward"` records, groups
them by integer `trial_id`, and writes them onto
`TrialResult.policy_action` (`None` → populated list). This is a
deliberate two-phase design, not a wiring gap.

### 4. The join would succeed — reward records carry integer trial_ids

Inspecting this run's actual `logs/policy_trials.jsonl`, the `reward`
records carry **integer** `trial_id`s matching `trial_index`
(`"trial_id": 0`, `1`, `10`, `100`, …, ~60–96 records each). So running
`join_policy_actions.py` against this run's results would populate
`policy_action` with real per-trial reward entries — the reward-
attribution loop and trial_id threading work end-to-end.

(A handful of string `trial_id`s — `"probe"`,
`"probe-investigation-2"`, `"trial-subtask3-verify"` — are leftovers
from the prior fix tasks' verification probes. `join_policy_actions.py`
explicitly skips non-integer trial_ids, so they do not contaminate the
join.)

## Why this is (a) and not (b), stated plainly

If (b) were true, `kernel.log` would show the adaptive branch skipped
(no `select_threshold` lines, no "Recorded novelty decision", an empty
or absent `policy_trials.jsonl`). Instead all of those fired thousands
of times. The only thing missing is the *post-run enrichment step* on
the Cerebrum side, whose own field docstring documents `null` as the
"not yet joined" state. The mechanism the fixes were built for ran; its
output was captured in `policy_trials.jsonl`; it simply hasn't been
joined onto the results JSON.

## Run validity

The 150-trial run is a **valid test of the adaptive condition**. Judge
scores, `memory_counts`, and `retrieval_log` are computed on the live
path independent of `policy_action` and are unaffected by its null
state. `memory_counts=0` / `shared_memory_count=2` / `written_memories=[]`
match Finding 1 of the prior sparse-memory investigation (expected,
non-blocking; see `MEMORY_COUNT_READ_PATH_TRACE_REPORT.md`). The null
`policy_action` is cosmetic and recoverable at any time from the
retained `policy_trials.jsonl`.

## Recommendation / fix judgment

**No code fix is warranted — not even a one-line one.** The cause is not
a bug in either repo; it is an operational step (`join_policy_actions.py`)
that was not run on this output. Per the master prompt's guidance to flag
the fix judgment explicitly: the appropriate remedy is **operational, on
the Cerebrum side, and out of scope for this AIOS-kernel task** — run:

```
python benchmarks/shared_memory/join_policy_actions.py \
    --results <this_run_results.json> \
    --policy-log logs/policy_trials.jsonl \
    --output <enriched_results.json>
```

scoped to this run's timestamp window (the `--since/--until` flags exist
precisely to avoid pulling in the probe records). This is a data-
enrichment action for whoever owns the benchmark artifacts, not a kernel
change, so it is left as a recommendation rather than performed here.

## Out-of-scope boundaries honored

- **`policy.py` / `PolicyManager` / LinUCB logic — not touched.** The
  investigation confirmed the bandit works; it was not reopened.
- **`_collection_name_for_user` / `mem0.py` — not touched.**
- **Trial-66 latency outlier — not investigated.** No connection to the
  `policy_action` finding surfaced (the arm-selection and reward records
  are independent of any single trial's LLM latency).
- **450-trial re-run — not started, scheduled, or decided.** This
  finding does not block it: the adaptive mechanism is demonstrably
  live, so there is no `policy_action`-related reason to re-do this run.
- **No fix implemented** (cause is operational/out-of-repo, per §6).

## Commits cross-referenced

- LinUCB reward-normalization fix: `286c10c`, `a4cef0f`, `44ed99a`
  (`docs/REWARD_NORMALIZATION_FIX_REPORT.md`).
- ChromaDB truncation-collision fix: `7065d09`, `adfcaeb`, `a3da418`
  (`docs/TRUNCATION_COLLISION_FIX_REPORT.md`).
- This report is documentation-only; it makes no code change.

## Files traced (no modifications)

- `kernel.log` — PolicyManager init/enabled lines, `select_threshold`
  and `Recorded novelty decision` and `report_reward` counts.
- `logs/policy_trials.jsonl` — 17,986 records; reward records carry
  integer `trial_id`s.
- `aios/syscall/syscall.py` — `execute_llm_syscall` / `_execute_syscall`
  response envelopes (no policy field).
- `../Cerebrum/benchmarks/shared_memory/models.py` — `TrialResult.policy_action`
  definition + docstring.
- `../Cerebrum/benchmarks/shared_memory/join_policy_actions.py` — the
  post-hoc enrichment join.
