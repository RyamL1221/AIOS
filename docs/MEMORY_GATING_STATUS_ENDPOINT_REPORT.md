# Memory Gating Status Endpoint — Implementation Report

## Summary

The kernel now exposes a small, read-only HTTP endpoint,
`GET /memory/gating_status`, that reports which memory-gating variant is
live on the running `MemoryManager` — the adaptive LinUCB policy
(`_adaptive_enabled`), the fixed static-threshold gating
(`_static_thresholds_enabled`), or neither (the frozen baseline). It
also returns the resolved `memory.static_thresholds` config block so a
trial run can record the exact threshold values that were active, not
just the on/off flags.

The change is purely additive: a new dedicated route in
`runtime/launch.py`. No existing route, and no `MemoryManager` code, was
modified. The endpoint reads live instance attributes and never mutates
state.

## Motivation

Experiment/trial runs need machine-readable provenance on which gating
variant produced a given result. Previously the flags lived only inside
`MemoryManager.__init__` (sourced from `config.yaml`) with no runtime
introspection path — the only way to know the live state was to read the
config file and trust it matched the running process. This endpoint
closes that gap.

## Changes

All line numbers reflect the state after the edits below.

### `runtime/launch.py`
- **New route `get_memory_gating_status`** — `runtime/launch.py`, lines
  **915–948**, inserted between the `/memory/report_reward` handler
  (ends ~line 912) and `/core/config/update` (now ~line 950). Both
  memory-policy endpoints (`/memory/report_reward`,
  `/memory/gating_status`) sit together as unprefixed `/memory/...`
  routes.
- Guards with the established pattern (mirrors `/agents/submit`):
  `if "memory" not in active_components or not active_components["memory"]`
  → `raise HTTPException(status_code=400, detail="Memory manager not
  initialized")`.
- Reads the two flags off the live `MemoryManager` via
  `getattr(mm, "_adaptive_enabled", False)` /
  `getattr(mm, "_static_thresholds_enabled", False)` — the
  `getattr(..., False)` form matches the codebase's `__new__`-safe
  access convention at other flag sites in `manager.py`.
- Returns a third key, `static_thresholds_config`, from
  `getattr(mm, "_static_thresholds_config", {})` — the raw
  `memory.static_thresholds` block (JSON-serializable primitives only;
  see Subtask 3 rationale below).

### Source attributes referenced (read-only, NOT modified)
- `aios/memory/manager.py` — class `MemoryManager` (line 24):
  - `self._adaptive_enabled` set at line **107**
  - `self._static_thresholds_config` set at line **159**
  - `self._static_thresholds_enabled` set at line **160**

## Endpoint Shape

- **Method / path:** `GET /memory/gating_status`
- **Success (200):**
  ```json
  {
    "adaptive_policy_enabled": <bool>,
    "static_thresholds_enabled": <bool>,
    "static_thresholds_config": { ... raw memory.static_thresholds ... }
  }
  ```
- **Error (400):** `HTTPException(status_code=400, detail="Memory
  manager not initialized")` when `active_components["memory"]` is
  falsy.

### Why `static_thresholds_config` is safe to include (Subtask 3)

Inspected the live value: it is a plain `dict` produced by the YAML
loader from the `memory.static_thresholds` block — a `bool` (`enabled`)
plus three nested dicts, each with a `float` `default` and a `list`
`overrides` (override entries, when present, are
`{llm_core: str, task_type: str, value: float}`). All JSON-serializable
primitives — no numpy types, no custom classes, no None-heavy nesting.
FastAPI serializes it directly, so it was included rather than skipped.

## Pilot Evidence

Captured from a live server (`.venv/bin/python -m runtime.launch` on
`localhost:8000`, per `runtime/launch_kernel.sh`). Each state required a
full server restart to load the new config (the kernel initializes
components once at import via `_ensure_initialized()`; `/core/refresh`
was deliberately not used as part of the endpoint's own logic).

**State A — baseline, both flags off**
(`adaptive_policy.enabled: false`, `static_thresholds.enabled: false`):
```json
{"adaptive_policy_enabled":false,"static_thresholds_enabled":false,"static_thresholds_config":{"enabled":false,"novelty_threshold":{"default":0.7,"overrides":[]},"similarity_threshold":{"default":0.7,"overrides":[]},"redundancy_threshold":{"default":0.7,"overrides":[]}}}
```

**State B — tuned-style**
(`static_thresholds.enabled: true`, `novelty_threshold.default: 0.65`,
adaptive off):
```json
{"adaptive_policy_enabled":false,"static_thresholds_enabled":true,"static_thresholds_config":{"enabled":true,"novelty_threshold":{"default":0.65,"overrides":[]},"similarity_threshold":{"default":0.7,"overrides":[]},"redundancy_threshold":{"default":0.7,"overrides":[]}}}
```

State B confirms both that the booleans flip correctly **and** that the
edited threshold value (`0.65`) round-trips through
`static_thresholds_config` — the provenance field carries real,
non-default values.

After the pilot, `config.yaml` was reverted to its pre-pilot state
(`adaptive_policy.enabled: true`, `static_thresholds.enabled: false`,
all thresholds `0.7`); `git diff aios/config/config.yaml` is empty.

## Regression Evidence

Checked against a live server at the normal pre-pilot config
(`adaptive_policy.enabled: true`, `static_thresholds.enabled: false`).

`GET /status` — unchanged shape:
```json
{"status":"ok","message":"All core components are active."}
```

`GET /core/status` — unchanged per-component map, no gating fields
injected:
```json
{"llms":"active","storage":"active","memory":"active","tool":"active","scheduler":"active","factory":"active"}
```

- **No field leakage:** grepped the live `/status` and `/core/status`
  responses for `gating|adaptive|threshold` — none present. The new
  route's fields stay confined to `/memory/gating_status`.
- **Route table intact:** the full route list from `/openapi.json`
  shows all pre-existing routes still registered plus the new
  `GET /memory/gating_status`. `/core/config/update` (the route
  immediately after the insertion point) is present and registered —
  confirmed **without invoking it**, since it triggers a full component
  reinit (side effects, per the non-goals).
- **Clean teardown:** server stopped, nothing left on port 8000, config
  diff empty.

## Acceptance Criteria Walk-Through

Against the master prompt's original acceptance criteria:

- **✅ New route added and reachable** — see route at
  `runtime/launch.py:915`; live responses in Pilot Evidence (States
  A/B) and Regression Evidence.
- **✅ Returns a dict with exactly the two required boolean keys on
  success** — `adaptive_policy_enabled` + `static_thresholds_enabled`
  present in every captured response (plus the optional
  `static_thresholds_config` provenance key, per the "optionally add
  resolved config" subtask).
- **✅ Returns a 400 HTTPException if `active_components["memory"]` is
  falsy** — guard at `runtime/launch.py` lines ~928–931, matching the
  `/agents/submit` pattern.
- **✅ No existing route's code is touched** — only an additive insertion
  between two existing handlers; Regression Evidence confirms `/status`,
  `/core/status`, and the route table are unchanged.
- **✅ `_adaptive_enabled` / `_static_thresholds_enabled` /
  `_static_thresholds_config` on `MemoryManager` not modified** — read
  via `getattr` only; `manager.py` untouched.
- **✅ Config cleanly serializable check backed by real contents** — see
  "Why `static_thresholds_config` is safe to include"; State A/B
  outputs show it serializing to valid JSON.
- **✅ Pilot evidence under two distinct live states, not just code
  review** — verbatim State A and State B JSON above, each matching the
  config live at capture time.
- **✅ `config.yaml` restored after the pilot** — empty
  `git diff aios/config/config.yaml`.
- **✅ Regression: `/status` and `/core/status` behave as expected
  post-change; new fields don't leak** — see Regression Evidence.
- **✅ Naming choice deliberate and stated** — `/memory/gating_status`
  chosen; rationale in Deviations.
- **✅ Server stopped cleanly, no side effects left behind** — confirmed
  in both Pilot and Regression steps.

## Deviations from the Master Prompt's Literal Suggestions

1. **Endpoint path — `/memory/gating_status` instead of the suggested
   `/core/memory/gating`.** Both prefixed (`/core/...`) and unprefixed
   memory routes exist in this file, so the prompt explicitly left this
   open. Chose the unprefixed form to sit directly beside its sibling
   memory-policy endpoint, `/memory/report_reward`, keeping the two
   policy endpoints grouped.

2. **Error shape — `HTTPException(400, detail=...)` instead of the
   suggested `{"status": "warning", ...}` dict-return.** Subtask 1's
   read of `launch.py` found `HTTPException` is the actual established
   error convention (used by `/agents/submit`, `/core/refresh`,
   `/query`, `/memory/report_reward`, `/core/config/update`). Matched
   the real convention over the prompt's illustrative shape.

3. **Config-state assumption — prompt assumed both flags started off;
   the live repo had `adaptive_policy.enabled: true`.** To produce a
   genuine "both off" State A baseline, `adaptive_policy.enabled` was
   temporarily set to `false`, then restored to `true` after the pilot.
   Restoration verified via an empty `git diff aios/config/config.yaml`.

## Commit History (as landed)

- `feat(memory-gating): add read-only gating status endpoint` — Subtask
  2 (the route + guard + two boolean keys).
- `feat(memory-gating): include resolved static threshold config in
  gating status` — Subtask 3 (the `static_thresholds_config` key).
- `docs(memory-gating): add implementation report for gating status
  endpoint` — this report.

Note: Subtasks 2 and 3 both edit the same handler in `runtime/launch.py`.
Whether they land as one squashed commit or two sequential commits is a
repo-history choice; the two messages above are the intended logical
units. Subtasks 4 and 5 were verification-only (no commits). Subtask 4's
`config.yaml` edits were fully reverted, so they contribute no diff.

## Follow-Up (non-blocking)

The `sdk-and-api` steering doc maintains an HTTP endpoint table. This
new endpoint is not yet listed there. Adding a one-line entry
(`GET /memory/gating_status` — report live memory-gating configuration
state) is a reasonable follow-up but was left out as an optional
documentation touch-up, not a blocker for the endpoint itself.
