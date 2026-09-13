# Upsert-Path Reachability for task_context Writes

Read-only trace (no code changed) resolving whether TaskAgent's
`_upsert_task_memory` update path was ever reached during the 1×15 run,
what routes a write to create-vs-update, and why the update path was
never taken. Follows `docs/TASK_CONTEXT_WRITE_PATH_TRACE.md` (22
task_context writes, all novelty-gate rejected) and
`docs/NOVELTY_GATE_TASK_CONTEXT_CLASSIFICATION.md` (design gap, not a bug).

## Verdict

**The upsert (update) path was NEVER invoked for task_context during the
run — 0 task_agent `update_memory` calls.** Every task_context write took
the `create_memory` branch, which hits the novelty gate, which rejected
all 22. The cause is a **bootstrapping trap structurally identical in
class to the reward-loop bootstrap trap fixed in `b6ffd7e`**: the update
path can only be taken once a task_context memory already exists, but one
can never come to exist because the first (and every) create is
novelty-rejected — so the "previous" memory to update against never
materializes.

## 1. Create-vs-update routing (from `agent.py:_upsert_task_memory`)

The routing is a search-then-branch (`cerebrum/example/agents/task_agent/agent.py`):
1. `search_memories(agent_name, query="task context {user_id}", user_id=...)`
   — look up existing memories for this user.
2. Filter: `matching = [r for r in existing_results if
   r["metadata"]["memory_type"] == MEMORY_TYPE_TASK_CONTEXT]`.
3. **If `matching` non-empty → `update_memory(memory_id, content)`** for
   each match (the upsert/update path).
4. **Else → `create_memory(content, metadata)`** (the fresh-create path).

So create-vs-update is governed entirely by **"does a task_context-typed
memory already exist for this user?"** — determined by the search + the
`memory_type == task_context` filter.

## 2. What "upsert→update" means mechanically, and that it bypasses the novelty gate

The kernel routes the two ops to different handlers
(`aios/memory/manager.py`):
- `add_memory` (create) branch (`manager.py:~941`): consults
  `_novelty_gate_admits` when adaptive is enabled — **this is where the
  22 rejections happened.**
- `update_memory` branch (`manager.py:1036-1038`): `memory_note =
  self._analyze_query_to_memory(query); return
  self.provider.update_memory(memory_note)` — **no novelty gate, no
  admit check.** It updates the existing memory_id in place.

**So had the write taken the update path, it would have bypassed the
novelty gate entirely** and the task_context content would have persisted
(updated). The novelty gate only stands between the *create* path and the
store.

## 3. Run evidence (kernel.log, run window 16:30–16:38)

Per-agent memory operations:

| agent | add_memory | retrieve_memory | update_memory |
|-------|-----------:|----------------:|--------------:|
| task_agent | **22** | 45 | **0** |
| profile_agent | (1 admitted, rest rejected) | — | **15** |

- **task_agent issued ZERO `update_memory`** — the upsert/update path was
  never taken. All 22 task_context writes were `add_memory` (create),
  all novelty-rejected (`docs/TASK_CONTEXT_WRITE_PATH_TRACE.md`).
- **profile_agent issued 15 `update_memory`** — ProfileAgent's identical
  upsert logic *did* reach the update path from trial 1 onward, because
  its first profile create was **admitted** (max_sim=0.0), giving it a
  stored profile memory to find and update thereafter. This is the
  control that proves the routing works when a prior memory exists.
- task_agent's 45 `retrieve_memory` calls (its search-for-existing) DID
  return rows, but the log shows "retained 1/2", "retained 1/3" — the
  single retained row is the **profile** memory (shared, owned by
  profile_agent), **not** a task_context memory. The
  `memory_type == task_context` filter therefore matched **nothing**, so
  every trial routed to create.

## 4. Why upsert was never attempted — the bootstrapping trap (confirmed)

The precondition for the update path is: **a task_context memory already
exists for this user.** The chain that prevents it ever existing:

1. Trial 0: TaskAgent searches → no task_context exists yet → routes to
   `create_memory`.
2. The create hits the novelty gate → `max_sim` (0.0 on the very first
   task_context, since none stored) … **but** the store already contains
   the admitted **profile** memory, and task_context vs profile similarity
   is ~0.48–0.59, so even the first task_context create sees `max_sim
   ≈ 0.5 > threshold (0.1–0.2)` → **rejected**. (Even if the first
   task_context saw max_sim=0.0 against an empty store, the profile write
   lands first in each trial, so there is always a profile memory to be
   similar to.)
3. Nothing is stored → next trial's search still finds no task_context →
   routes to create again → rejected again.
4. Repeat for all 15 trials: **create → reject → no stored memory → next
   search finds nothing → create again.** The update path's precondition
   (a prior task_context memory) is never satisfied.

This is a **self-reinforcing bootstrap trap**: the mechanism that would
let writes persist (in-place update, which bypasses the gate) can only
engage *after* at least one write has persisted, but the gate blocks that
first persistence, so the update path is永 unreachable.

## 5. Relation to the `b6ffd7e` reward-loop bootstrap fix (flagged, not coincidence)

This is a **related-but-distinct instance of the same problem class** as
the trap fixed in `b6ffd7e` (documented in
`.kiro/steering/memory-providers.md` and `docs/FAILOPEN_EVENT_ACCOUNTING.md`):

| | Reward-loop bootstrap trap (fixed in `b6ffd7e`) | task_context write bootstrap trap (this trace) |
|---|---|---|
| Gate | similarity **retrieve** gate | novelty **add** gate |
| Self-reinforcing loop | over-strict arm empties retrieval → empty `memory_ids_involved` → `report_reward` credits nothing → arm never validated → keeps emptying | over-strict novelty arm rejects create → nothing stored → upsert precondition never met → always create → always rejected |
| The blocked "escape hatch" | reward that would teach the arm a better threshold | in-place update that would bypass the gate |
| Fix applied | per-arm bootstrap fail-open (`BOOTSTRAP_MIN_UPDATES`) keeps ≥1 creditable id until the arm has evidence | **NONE — this trap is unfixed** |

Both are "the corrective mechanism can't engage until the thing it
corrects has already succeeded once, but the failure prevents that first
success." The reward-loop instance got a per-arm fail-open on the
*retrieve* side; **the novelty/add side has no analogous bootstrap
escape** — a create that would be the first-ever memory of its type gets
no leniency. This is worth flagging as the same class of bug, not a
coincidence.

## Answers to the subtask's questions
- **Was `_upsert_task_memory` ever invoked as an update during the run?**
  No — 0 task_agent `update_memory` ops; all 22 were create→rejected.
- **What precondition governs create-vs-update?** Whether the search +
  `memory_type == task_context` filter finds an existing task_context
  memory for the user. It never did (only the profile memory came back).
- **Should this run's writes have taken the upsert path?** Only from
  trial 1 onward *if* trial 0's create had persisted. It didn't (novelty
  reject), so the upsert precondition was never bootstrapped.
- **Bootstrapping problem?** Confirmed, and explicitly the same class as
  the `b6ffd7e` reward-loop bootstrap trap — on the novelty/add gate,
  currently unfixed.

## Caveats
- The "first task_context sees the profile memory at max_sim ~0.5" step
  is inferred from the ordering (ProfileAgent runs before TaskAgent each
  trial, `pipeline.py:110-150`) plus the observed 0.48–0.59 max_sim; the
  trace did not isolate trial-0's task_context max_sim specifically from
  the 22 (all 22 rejected regardless, so the conclusion is unchanged).
- Whether the *fix* should be a novelty-gate bootstrap fail-open, a
  per-task_type threshold, or routing task_context updates around the
  gate is a design decision, out of scope here.
