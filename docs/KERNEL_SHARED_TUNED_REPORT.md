# kernel_shared_tuned — Static Threshold Gating Implementation Report

Consolidated report for the `kernel_shared_tuned` memory-gating variant:
a non-learning, fixed-threshold alternative to the adaptive LinUCB
policy, driven by a per-`(llm_core, task_type)` lookup table with a
mandatory default. This document is self-contained — it does not
require the prior implementation turns to be understood.

**Scope:** add a config-driven static-threshold gate for the three
memory gates (novelty on add; similarity + redundancy on retrieve),
independent of the adaptive policy, off by default, provably identical
to the current frozen baseline when disabled.

---

## 1. Investigation findings

### 1.1 There is no pre-existing static-threshold read path (deviation A)

The master prompt assumed an existing "static path" that reads a flat
scalar threshold from config when `adaptive_policy.enabled` is false,
which this work would extend. **That path does not exist.** In
`MemoryManager.address_request` (`aios/memory/manager.py`), the three
gates are gated solely by `if getattr(self, "_adaptive_enabled",
False):`. When the flag is off, the gate blocks are **skipped
entirely** — `add_memory` writes unconditionally and `retrieve_memory`
returns the provider's results unfiltered. There is no `else` branch,
no scalar read, and no `novelty_threshold` / `similarity_threshold` /
`redundancy_threshold` key anywhere in config (grep over `**/*.yaml*`
returned no matches).

Consequence: gate-application on the static path had to be **built
new**, not extended. The one genuinely static scalar that does exist
today — `relevance_threshold`, read in `ContextInjector`
(`aios/memory/context_injector.py:48`, applied at line 313) — is a
separate injection-path relevance filter, unrelated to the three
bandit gates, and was left untouched.

### 1.2 `llm_core` context was withheld from the static path (deviation B)

Both gates key their context on `(llm_core, task_type)`.

- `task_type` is derived on demand from data already in scope
  regardless of the flag: the note's `memory_type` metadata (add) or
  `query.params["memory_type"]` (retrieve). Type: `str`, coalesced to
  `""`. **No plumbing needed.**
- `llm_core` is read from `self._latest_llm_core` (type `str`, default
  `"unknown"`), but that attribute was **only updated inside the
  adaptive-gated branch** of `sync_llm_from_query`. On the static path
  it stayed `"unknown"` forever, so a static gate could never key on a
  real model identity. **This gap was fixed in Subtask 6** by ungating
  the capture (see §2.5).

The lookup contract matches the adaptive one: `PolicyManager.
select_threshold(bandit_name: str, llm_core: str, task_type: str)`, so
the static lookup keys on the same `(str, str)` pair with `"unknown"` /
`""` as the empty sentinels.

---

## 2. What changed (file + line citations)

### 2.1 Config schema — `static_thresholds` block

- `aios/config/config.yaml` and `aios/config/config.yaml.example` —
  added a `memory.static_thresholds` block, sibling of
  `adaptive_policy`. Fields: `enabled` (bool, default false) plus
  `novelty_threshold` / `similarity_threshold` / `redundancy_threshold`,
  each accepting **either** a bare scalar **or** a `default` +
  `overrides` table (`overrides`: list of `{llm_core, task_type,
  value}`). All three defaults are `0.7`, explicitly marked
  `# PLACEHOLDER — replace with offline-search output`. A comment notes
  `static_thresholds.enabled` and `adaptive_policy.enabled` are not
  meant to both be true (convention, unenforced). `config.yaml` is
  gitignored (CI regenerates it from the example); both files hold the
  byte-identical block on disk.

### 2.2 New module — `aios/memory/static_thresholds.py`

Pure, stateless lookup (stdlib only; no `MemoryManager` /
`_latest_llm_core` / config coupling):

- `resolve_threshold(gate_config, llm_core: str, task_type: str) ->
  float` — normalizes either config form, does an exact-match
  `(llm_core, task_type)` lookup, falls back to `default` on a miss.
- `normalize_gate_config(...)` → `{"default": float, "overrides":
  {(llm_core, task_type): float}}`; a bare scalar `X` →
  `{"default": X, "overrides": {}}`.
- `StaticThresholdConfigError` — raised for a table form missing
  `default`, non-numeric values, wrong-typed `overrides`, or malformed
  override entries (loud failure, no silent arbitrary fallback). `bool`
  is explicitly rejected (it is an `int` subclass).

### 2.3 `manager.py` — init flag

- `aios/memory/manager.py:157-163` — `__init__` reads the block once
  into `self._static_thresholds_config` (line 159) and
  `self._static_thresholds_enabled` (line 160, from
  `static_thresholds.get("enabled", False)`), mirroring how
  `_adaptive_enabled` is initialized. The two flags are fully
  independent.

### 2.4 `manager.py` — shared helpers + new static gate methods

Shared comparison/filter logic was extracted so the adaptive and
static paths run identical mechanics with different threshold sources
(no duplicated logic):

- `_note_task_type(memory_note)` — `manager.py:430` (shared add-path
  `task_type` derivation).
- `_novelty_admits(max_sim, threshold)` — `manager.py:440` (the
  `max_sim < threshold` admit comparison; adaptive `_novelty_gate_admits`
  refactored to call it).
- `_filter_by_similarity(results, threshold)` — `manager.py:651`
  (retrieve Gate 1 loop).
- `_dedupe_by_redundancy(results, threshold)` — `manager.py:668`
  (retrieve Gate 2 loop). Adaptive `_apply_retrieval_policy` refactored
  to call both.

New static-path methods (source thresholds from `resolve_threshold`,
record NO reward decision, touch NO bandit state):

- `_static_novelty_gate_admits(memory_note, user_id)` —
  `manager.py:451`.
- `_apply_static_retrieval_policy(search_results, query)` —
  `manager.py:703`.

### 2.5 `manager.py` — elif wiring + ungated `_latest_llm_core`

- Add branch: `elif getattr(self, "_static_thresholds_enabled",
  False):` at `manager.py:886`, after the adaptive `if`. A reject
  returns `success=True, memory_id=None` and releases the write barrier,
  exactly like the adaptive reject.
- Retrieve branch: sibling `elif` calling
  `_apply_static_retrieval_policy` at `manager.py:1026`.
- **Precedence (documented, exclusivity unenforced):** the adaptive
  `if` is always checked first, so if both flags are somehow true the
  adaptive path wins and the static `elif` never fires. Both flags off
  ⇒ neither fires ⇒ frozen baseline.
- **Ungated `_latest_llm_core` capture (fixes deviation B):**
  `sync_llm_from_query` guard changed from `if _adaptive_enabled and
  llms:` to `if llms:` at `manager.py:1091`, so the model name is
  captured whenever the query carries it, regardless of gating mode.
  The downstream `self.provider.sync_llm_from_query(llms)` was already
  unconditional and is unchanged.

### 2.6 Tests + pilot

- `tests/modules/memory/test_static_thresholds.py` — 17 unit tests for
  `resolve_threshold` (scalar, table+match, table+no-match→default,
  missing-`default` error, malformed configs, purity).
- `tests/modules/memory/test_static_threshold_gate.py` — 13 integration
  tests for the wired gates: novelty admit/reject/override, retrieve
  similarity/redundancy filtering, both-flags-off baseline, adaptive
  precedence, no-bandit-state, and (Subtask 6) `_latest_llm_core`
  population + override-driven gating on the static path.
- `scripts/policy_pilot.py` — three new modes:
  `--mode kernel-shared` (both-flags-off regression + gate-spy),
  `--mode kernel-shared-tuned` (lookup-correctness pilot with fake
  overrides), plus the supporting `_build_manager_flags` /
  `_build_manager_static_cfg` builders. The pre-existing `--mode off`,
  `on`, `calib` are unchanged.

---

## 3. Regression-check evidence (kernel_shared baseline)

Method: the original flag-off proof, `scripts/policy_pilot.py --mode
off`, re-run as-is on current code → PASS. It was then faithfully
extended into `--mode kernel-shared`, which runs three managers (pure
baseline with the block absent; current kernel_shared with the block
present-but-disabled; an old config with the block absent through
current code), asserts their admit/retrieve decisions are identical,
and installs spies proving the static `elif` branches fire **0** times.
`--shared-user` is rejected for this mode because its shared ChromaDB
collection is non-deterministic across runs even for two identical
no-gate baselines (a store artifact, not a gating regression — verified
directly).

Captured output (`--mode kernel-shared`):

```
KERNEL_SHARED REGRESSION (adaptive=false AND static=false)
  trials run                     : 16
  admit decisions identical (3x) : True
  retrieval results identical(3x): True
  static novelty elif calls (KS) : 0 (must be 0)
  static retrieve elif calls (KS): 0 (must be 0)
  static elif calls (old config) : 0/0 (must be 0/0)
  old config (no block) loaded OK: True (flag defaulted to False)
  policy never instantiated      : True
  all candidates admitted        : True (unconditional write == baseline)
  RESULT: PASS
```

Supporting suites (all green): `test_static_thresholds` (17),
`test_static_threshold_gate` (13), `test_adaptive_novelty_gate` (7),
`test_adaptive_retrieval_gate` (7), `test_policy_manager` (13),
`test_policy_trial_logging` (3).

---

## 4. Lookup-correctness pilot trace (kernel_shared_tuned)

Method: `scripts/policy_pilot.py --mode kernel-shared-tuned` builds a
manager with `static_thresholds.enabled: true`,
`adaptive_policy.enabled: false`, and a fake override table (held in
the script fixture, NOT in the shared config; all model names use the
`pilot-fake-` prefix). It drives real `add_memory` (novelty) and
`retrieve_memory` (similarity + redundancy) syscalls, and a spy on
`resolve_threshold` captures its **actual return value** per gate.
Six data points — each gate × {override-match, no-match→default}:

```
  Per-gate evidence table (6 data points, all FAKE placeholders):
    gate                   case      llm_core             task_type resolved  expected  ok
    --------------------------------------------------------------------------------------
    novelty_threshold      MATCH     pilot-fake-model-A   profile   0.61      0.61      True
    novelty_threshold      default   pilot-fake-model-Z   profile   0.7       0.7       True
    similarity_threshold   MATCH     pilot-fake-model-A   task      0.42      0.42      True
    similarity_threshold   default   pilot-fake-model-Z   task      0.5       0.5       True
    redundancy_threshold   MATCH     pilot-fake-model-A   task      0.88      0.88      True
    redundancy_threshold   default   pilot-fake-model-Z   task      0.8       0.8       True

  RESULT: PASS (all values are pilot placeholders, not tuned data)
```

The raw `resolve_threshold` call trace also shows the novelty
seed-adds under `(pilot-fake-model-A, task)` correctly falling to the
default `0.7` (the novelty override is keyed on `profile`), confirming
exact-match semantics do not over-match. All numbers above are
illustrative placeholders — this pilot supplies no real tuned data.

---

## 5. Acceptance criteria checklist

Walking the master prompt's checklist literally:

- **[Done] Config schema supports scalar + lookup-table thresholds
  with a mandatory default, behind a new `static_thresholds.enabled`
  flag independent of `adaptive_policy`.** §2.1; both forms unit-tested
  in `test_static_thresholds.py`.
- **[Done] Lookup logic (`resolve_threshold`) is pure, keyed on
  `(llm_core, task_type)`, exact-match-or-default, with a loud error on
  missing default.** §2.2; four-case unit evidence (scalar,
  table-match, table-no-match, missing-default) + malformed/purity
  cases.
- **[Done] Gate-application on the static path for all three gates,
  mirroring the adaptive admit/filter mechanics with the threshold
  sourced from `resolve_threshold`.** §2.4–2.5; end-to-end evidence in
  `test_static_threshold_gate.py` and §4.
- **[Done] `_latest_llm_core` captured regardless of the adaptive
  flag, so the static path keys on real model identity.** §2.5;
  captured-evidence tests show an override matching a synced `llm_core`
  (not the default) driving both the novelty and retrieve gates.
- **[Done] kernel_shared baseline (both flags off) provably identical
  to current no-filter behavior; old configs lacking the block still
  work; static `elif` provably never fires when disabled.** §3
  (`RESULT: PASS`, spy counts 0, old-config loads with flag defaulting
  to False).
- **[Done] Lookup-correctness pilot proving override-match vs default
  for all three gates end-to-end with clearly-fake placeholder
  values.** §4 (6-point table, `RESULT: PASS`).
- **[Done] This consolidated implementation report.** This document.

### Deviations reported explicitly (not resolved silently)

- **(A) No pre-existing scalar-read path.** The master prompt assumed
  gate-application already existed on the OFF-of-adaptive path and would
  be extended. Subtask 1 found it does not exist (§1.1) — the flag-off
  path skips gating entirely. Gate-application was therefore **built
  new**, as a sibling `elif` to the adaptive branch, rather than
  extending an existing scalar read.
- **(B) `llm_core` threading gap.** The `(llm_core, task_type)` context
  the gates need was only half-available on the static path: `task_type`
  was in scope, but `_latest_llm_core` was captured only inside the
  adaptive branch (§1.2), leaving it permanently `"unknown"` for static
  gating. This required a fix beyond the assumed scope — ungating the
  capture (§2.5, Subtask 6).

---

## 6. Explicitly not done (non-goals honored)

- **No search / optimization implemented.** The lookup mechanism is
  built and exercised; choosing real threshold values is out of scope.
- **No changes to the adaptive path:** `PolicyManager`, the LinUCB
  bandits, `report_reward`, and `policy_trials.jsonl` are untouched.
  The static path records no reward decisions and never instantiates
  `PolicyManager`.
- **No Cerebrum SDK changes.** All work is kernel-side.
- **No new `task_type` taxonomy invented.** The gates reuse the
  existing `memory_type` metadata values; the pilot reuses existing
  shapes with fake `llm_core` names only.

---

## 7. Next steps (out of scope for this report)

- Real tuned threshold values must come from the **separate offline
  search process**. When available, they replace the `0.7` PLACEHOLDER
  defaults (and any real overrides) in `static_thresholds`.
- `kernel_shared_tuned` trials can then be run alongside
  `kernel_shared` and `kernel_shared_adaptive` for comparison.
- Optional fast-follow: enforce mutual exclusivity of
  `static_thresholds.enabled` and `adaptive_policy.enabled` (currently
  a documented convention only).
```
