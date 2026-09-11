# owner_agent mechanism — direct confirmation + the real fix

Two parts: (1) a read-only direct-evidence confirmation of what actually
happens to `owner_agent`, which **disproves the stated hypothesis**, and
(2) the minimal fix for the mechanism the evidence actually revealed.

---

## Part 1 — Direct evidence (read-only, no code changes in this step)

### Method

Wrote ONE memory through the real AIOS add path
(`MemoryManager.address_request(add_memory)` → `Mem0Provider.add_memory`)
as a benchmark writer agent does — `owner_agent="profile_agent"`,
`memory_type="profile"`, `sharing_policy="shared"`, fresh disposable
`user_id` — then read the RAW ChromaDB collection directly
(`collection.get(include=["metadatas"])`), bypassing
`retrieve_memory` / `get_all` / `_enrich_metadata`.

### Raw stored metadata (as persisted)

```
{'memory_type': 'profile', 'hash': '2842d19e…', 'user_id': 'probe_user_d6b0d8a8a4e1',
 'category': 'Uncategorized', 'owner_agent': 'profile_agent',
 'updated_at': '2026-09-10T19:02:49…', 'role': 'user',
 'data': '{"user_name": "Probe Person", …}', 'created_at': '2026-09-10T19:02:49…',
 'memory_note_id': '1d5e4f1e…', 'sharing_policy': 'shared',
 'text_lemmatized': '…', 'timestamp': '202609101502', 'context': 'General'}
```

`owner_agent` **PRESENT, value `'profile_agent'`.** A normal
`retrieve_memory` for the same record returned it intact
(`owner_agent='profile_agent'`). A REAL 2×10 pilot collection
(`mem0_memories_alex_martinez_ecb3dd65_s0_kernel_shared_adaptive`,
count 11) likewise holds rows with `owner_agent='profile_agent'` /
`sharing_policy='shared'`.

### Verdict: the hypothesis is WRONG

The stated best explanation — `_enrich_metadata` defaulting
`owner_agent` to `""` because the stored metadata lacks it — is
**disconfirmed**. The write path DOES set `owner_agent`
(`Mem0Provider.add_memory`, `aios/memory/providers/mem0.py:843-852`
copies it from `MemoryNote.metadata` when present, which the SDK's
`build_memory_metadata` always supplies), the store DOES persist it, and
the read path (`_extract_filter_metadata` → `_enrich_metadata`,
`mem0.py:515-533` / `base.py`) preserves it. The `""` default never
fires for a normally-written row. This is neither write-side omission
(a) nor read-side loss (b).

### The actual mechanism: (c) the retrieve-time similarity gate

Replaying the EXACT harness audit
(`retrieve_memory`, `agent_name=<writer>`, `user_id`,
`sharing_policy="shared"`, `k=20`) against the real pilot rows with a
realistic follow-up query (`"What should I work on next?"`):

- **PRE-GATE** (`provider.retrieve_memory`): 1 row,
  `owner_agent='profile_agent'`, **similarity = 0.4766**.
- **POST-GATE** (`MemoryManager.address_request`): the adaptive
  `similarity_threshold` bandit sits at arm 0 = **0.50**, so
  `_filter_by_similarity` logs `kept 0/1` and returns **0 rows**.

The row is dropped **not for `owner_agent`** but because its similarity
to the semantically-distant follow-up query (0.4766) is just below the
initial 0.50 threshold. Empty result → the harness builds
`injected_memory_ids=[]` → `memory_ids_involved=[]` →
`report_reward` credits nothing → the `similarity_threshold` bandit
never leaves arm 0 → it keeps dropping everything. A **self-reinforcing
bootstrap trap**.

(Queries closer to the stored JSON — `"profile"`, the user_id — scored
0.52–0.57 and survived, which is why an earlier trace that used a closer
probe query mistakenly ruled the similarity gate out. The benchmark's
real follow-up query is what pushes below 0.50.)

This also reconciles the 2×10 pilot's `injection_status=unknown` ×20 /
0 reward events: retrieval genuinely returned 0 rows at the gate, so the
harness fell through to the `unknown` audit branch with nothing to
report.

---

## Part 2 — The minimal fix (NARROWED — see update below)

> **Update (narrowing):** the fix was first implemented as a blanket
> total-wipeout fail-open inside the shared `_filter_by_similarity`
> helper. That over-reached — it fired at *every* arm (not just the
> under-informed initial one) and, because the helper is shared, it also
> silently changed the static `kernel_shared_tuned` path. It has since
> been narrowed to a **bootstrap-only** fail-open scoped to the adaptive
> path. The narrowed design is described here; the blanket version is
> retained below only as the rejected-first-cut for the record.

**Change (AIOS-owned):** the fail-open lives in
`MemoryManager._apply_retrieval_policy` (the adaptive retrieve path),
NOT in `_filter_by_similarity`. It triggers only when BOTH (1) the
similarity threshold would drop every row of a non-empty set, AND (2)
the **selected arm** (`sim_arm`) has received fewer than
`MemoryManager.BOOTSTRAP_MIN_UPDATES` (= 1) reward updates. The shared
`_filter_by_similarity` helper is restored to its pre-fix behavior
(returns `[]` on a total wipeout).

```python
kept = self._filter_by_similarity(search_results, sim_threshold)
if search_results and not kept:
    arm_updates = self.policy.arm_update_count("similarity_threshold", sim_arm)
    if arm_updates < self.BOOTSTRAP_MIN_UPDATES:
        # this arm is still bootstrapping: keep the full set so >=1 id
        # reaches report_reward and the arm can be validated
        kept = list(search_results)
    # else: this arm is validated -> honor its strict (empty) result
```

The gate keys on a **per-arm** update count, not the whole-bandit total
(see the per-arm semantics decision below). Per-arm counts are exposed
by `LinUCBBandit.arm_update_count(arm_index)` and
`PolicyManager.arm_update_count(bandit_name, arm_index)`; the
whole-bandit total (`update_count`, now a sum over arms) is retained for
logging/diagnostics only.

### Why this is correct

The similarity gate is meant to *rank down* marginal results, not to
erase the entire retrieval. Erasing it is precisely what starves the
adaptive reward loop: the reward is keyed on surviving rows'
`memory_id`s (`report_reward` credits by id), so a fully-emptied result
means **no id can ever carry the reward that would teach the arm its
threshold was too aggressive** — a self-reinforcing trap. Gating the
fail-open on the selected arm's own update count targets exactly that
trap: while an arm has no learning signal it cannot be trusted to reject
everything, so we keep the set; once *that arm* has been rewarded at
least once, its strict rejection (e.g. a converged 0.90) is trusted and
is allowed to reject everything again, restoring the gate's ceiling.
Partial filtering is unchanged in every state.

### Per-arm vs whole-bandit semantics — EXPLICIT decision

The fail-open gate keys on **per-arm** update count
(`arm_update_count(sim_arm)`), NOT the whole-bandit total. This is
deliberate and load-bearing:

- The wipeout decision is made by the *specific* arm `sim_arm` that
  `select_threshold` returned this trial, and reward attribution is
  per-arm — `_record_decision` stores `sim_arm`, and `report_reward`
  credits that arm. So "can I trust this rejection?" must be answered
  about the arm that *made* it, not about the bandit as a whole.
- LinUCB's exploration (UCB) bonus keeps *selecting* never-rewarded
  arms. A whole-bandit counter would flip the fail-open OFF for such an
  untested arm the moment any *sibling* arm received its first reward —
  reopening a version of the same trap for every arm past the first one
  updated: the untested arm could wipe out, get no reward (empty result
  → empty `memory_ids_involved`), and never be validated.
- A per-arm check means each arm must independently earn trust before
  its total-wipeout rejection is honored, which is the true bootstrap
  condition.

An earlier iteration of this fix used a whole-bandit `update_count`; it
was corrected to per-arm after review flagged exactly this gap. The
regression is locked in by
`test_bootstrap_failopen.test_sibling_arm_reward_does_not_disarm_untested_arm`.

### Known simplification: `arm_update_count` counts ANY reward, not "was a wipeout-rejection validated"

`arm_update_count(arm)` counts *every* reward update credited to that
arm, regardless of whether the trial it came from was one where the arm
actually caused a total wipeout. The condition we ideally want is "has
*this arm's rejection behavior* ever been validated by reward"; what we
actually check is "has this arm received reward for any reason." These
usually coincide but are not identical: an arm can clear the
`BOOTSTRAP_MIN_UPDATES` bar purely from trials where it *kept* rows (and
was rewarded normally), then trigger its first total wipeout on a later
trial — at which point it is already "trusted" despite having zero
direct evidence about how a wipeout on that arm gets scored.

This is deliberately left as a known simplification (cf. the equal-split
reward-attribution simplification flagged earlier in this project),
not silently treated as fully resolved:

- It is a much softer edge than the whole-bandit gap. The whole-bandit
  gap disarmed the fail-open for an arm with *zero* updates the moment a
  *sibling* was rewarded; this residual only concerns an arm that has
  itself been rewarded ≥1 time but never specifically on a wipeout
  trial. Per-arm tracking + `BOOTSTRAP_MIN_UPDATES=1` closes the
  important case (a never-rewarded arm can never be trusted).
- Distinguishing "wipeout-rejection validated" from "arm rewarded" would
  require threading whether each recorded decision was a wipeout into
  the reward path — more state and coupling than this soft edge
  justifies right now.

If a future live pilot shows an arm converging to a strict threshold and
starving retrieval *after* being validated only on non-wipeout trials,
revisit by tracking wipeout-specific validation per arm. Until there is
live evidence, this stays a documented simplification.

### Scope decision: `kernel_shared_tuned` (static path) — EXPLICIT

The static/tuned path (`_apply_static_retrieval_policy`) is deliberately
**left untouched / restored to pre-fix**. It calls `_filter_by_similarity`
directly, which now (again) returns `[]` on a total wipeout, so a tuned
run sitting at a deliberately-strict threshold rejects everything as
designed. Re-deriving `kernel_shared_tuned` was explicitly out of scope,
so the fail-open is confined to the adaptive path only. This is a
conscious decision, not a side effect: the bootstrap trap is an
*adaptive-learning* problem (a bandit that cannot learn its way off its
initial arm); a static threshold has no learning loop to starve, so the
fail-open would be meaningless there and would only weaken a
deliberately-chosen tuned value.

### Rejected first cut (blanket fail-open in the shared helper)

Placing the fail-open in `_filter_by_similarity` looked minimal but was
wrong on two counts: (1) it fired at every arm indefinitely, so a
converged strict arm could never reject a full set again — that is not
bootstrap-breaking, it is permanently disabling strict filtering; and
(2) the helper is shared with the static path, so it silently altered
`kernel_shared_tuned`. The narrowed version fixes both.

### Alternatives rejected

- **Fix `owner_agent` at write time / patch the harness owner-filter /
  change `_enrich_metadata`'s default** — rejected: the evidence shows
  `owner_agent` is already correct end-to-end. These would fix a
  non-existent bug and leave the real cause (the gate wipeout)
  untouched.
- **Record the similarity decision even when survivors is empty** —
  rejected: `report_reward` credits by `memory_id`, and the harness
  never sends a dropped row's id, so the decision would never be
  credited and would leak in `_pending_reward_decisions`.
- **Lower the arm-0 threshold / re-tune the action space** — rejected:
  the committed action-space-widening fix already brackets the tuned
  winners; moving the floor further would weaken the gate for every
  context to paper over a bootstrap-only failure, and still leaves a
  total-wipeout edge for any future context whose similarities all fall
  below the chosen arm.
- **Disable the retrieve gate for audit queries (harness-side)** —
  rejected: violates the ownership split (Cerebrum is a pure messenger;
  all memory-gating logic lives in AIOS) and would make the benchmark
  measure something other than the live kernel behavior.

### Compatibility with the three committed fixes

- **Gate-blindness (real similarity via `distance_to_similarity`)** —
  unchanged; the fix consumes the same `similarity` field.
- **Equal-split reward attribution (`cc385c5`)** — unchanged; the fix
  only affects which rows survive to be recorded, not how recorded
  decisions are credited. Verified steps 1–2 of the reward path
  (`_apply_retrieval_policy` → `_pending_reward_decisions`) still record
  one similarity + one redundancy decision per surviving id.
- **Action-space widening (`13cd04d`)** — unchanged; arms are untouched.
- **Reward normalization (`r / JUDGE_MAX_SCORE`)** — unchanged; the fix
  is upstream of `report_reward` / `PolicyManager.update`.

### Ownership

Entirely **AIOS-owned** (memory-management/policy logic). Cerebrum is
unchanged — it remains a pure messenger that reports whatever ids
survive retrieval.

---

## Verification

Verifying the NARROWED, PER-ARM fix (bootstrap-only, adaptive-path-scoped):

- **Bootstrap end-to-end** against the real previously-dropped pilot row
  (selected arm has 0 updates): now **survives** (log: `... (arm N)
  would drop all 1 result(s) but this arm is still bootstrapping
  (arm_updates=0 < 1); failing open`), with `owner_agent='profile_agent'`
  intact and a `similarity_threshold` decision recorded for it.
- **Converged end-to-end** against the same row after the selected arm
  is rewarded: its strict rejection is honored and the row is
  **dropped** (log: `... (arm N) dropped all 1 result(s); honoring
  converged arm (arm_updates>=1)`). The ceiling is restored.
- **Regression test** `tests/modules/memory/test_bootstrap_failopen.py`
  (5 cases, all pass): bootstrap-fails-open; converged-arm-rejects-
  everything; partial-filter-never-triggers-failopen; static-helper-
  does-not-failopen (proving `kernel_shared_tuned` is unaffected); and
  **`test_sibling_arm_reward_does_not_disarm_untested_arm`** — the
  specific per-arm regression proving that rewarding one arm does NOT
  turn off the fail-open for a different, still-untested selected arm
  (whole-bandit semantics would fail this).
- `tests/modules/memory/test_adaptive_retrieval_gate.py`:
  `test_threshold_value_is_decisive` and
  `test_bootstrap_failopen_vs_converged_wipeout` updated to pin the
  selected arm (via `_force_thresholds(..., sim_arm=...)`) and reward
  THAT arm, so they exercise the per-arm gate deterministically. All
  pass except one **pre-existing, unrelated** failure
  (`test_retrieve_then_report_reward_updates_and_cleans_up`), which
  asserts the superseded v1 equal-credit reward math (`0.25 != 1.0`) and
  fails identically with these changes reverted (confirmed via
  `git stash`).
- `tests/modules/memory/test_policy_manager.py` (13/13),
  `test_adaptive_novelty_gate.py` (7/7),
  `test_static_threshold_gate.py` (13/13),
  `test_policy_trial_logging.py` (3/3): all pass.

The pre-existing failure in `scripts/verify_mem0_reward_attribution.py`
(step 3c "equal-credit") is likewise unrelated and untouched.

## Status gate: next step is a LIVE pilot, not more unit-level revision

The fail-open mechanism has now changed twice (blanket → bootstrap-only
→ per-arm) on the strength of reasoning + unit tests alone. Both
revisions were correct and are well-covered at the unit level, but
nothing has touched a live pilot since the mechanism was first written.

This project's own track record (see `learnings-and-workflow.md`) is
that in-process/unit verification and live-pilot verification have
diverged repeatedly *in this very investigation* — e.g. the Mem0 id-gap
"RESOLVED" claim, and the 5×4-vs-2×10 retrieval discrepancy. So:

**Gate for moving forward: no further unit-level narrowing of this fix
from armchair reasoning. The next action is to run it live** — a real
`kernel_shared_adaptive` pilot (the 2×10 config used throughout) against
a freshly-restarted kernel — and confirm from the run that (a)
`report_reward` now receives non-empty `memory_ids_involved`, (b)
`reward` events are logged (bandit updates > 0), and (c) at least one
`similarity_threshold` arm moves off arm 0. Only live evidence should
drive any further change to this mechanism, including the known
simplification flagged above.
