# Reward-Loop Break Trace (Subtask 1, read-only)

Goal: pinpoint, with cited source lines, exactly where
`memory_ids_involved` goes empty in the
retrieve → gate → credit → `report_reward` → `PolicyManager.update`
chain, so Subtask 2 fixes a confirmed cause rather than a guess.

**No code was changed in this subtask.** All line numbers are as read
on the current tree.

---

## Verdict up front

**Root cause: candidate (b) — the retrieval/audit path drops the
memories before their ids ever reach the reward call. Specifically, the
Cerebrum benchmark harness's per-trial audit/retrieve HTTP query returns
0 memories, so it builds an *empty* `memory_ids_involved` and sends that
to `POST /memory/report_reward`. The break is on the Cerebrum harness
side of the boundary, upstream of every AIOS kernel hop below.**

Candidates (a) and (c) are **ruled out** with disconfirming evidence
(sections 5–6). Candidate (a) — "similarity gate at 0.5 drops all
retrieved memories pre-credit" — is a real *latent* second-order risk on
the AIOS side but is **not** what is emptying `memory_ids_involved` in
the observed runs, because the harness never gets as far as sending
non-empty ids in the first place (its own retrieve returns 0 before the
kernel gate is even a factor for the reward payload it builds).

---

## The identifier space (established first, because it disproves (c))

Both ends speak the **same id**: the Mem0 record id.

- Provider emits it: `Mem0Provider.retrieve_memory` builds each
  `search_results` dict with `"memory_id": item.get("id")` —
  `aios/memory/providers/mem0.py:1308-1312`. The comment there is
  explicit: "Emit the underlying Mem0 item id so downstream reward
  attribution has a stable key to reference."
- Kernel records decisions under that same key: in
  `MemoryManager._apply_retrieval_policy`, the per-survivor loop uses
  `mem_id = r.get("memory_id") or r.get("id")` and calls
  `self._record_decision(mem_id, ...)` —
  `aios/memory/manager.py:592-609` (loop) → `_record_decision`
  (`manager.py:335-345`), which appends to
  `self._pending_reward_decisions[memory_id]`.
- Add path records under the *written* Mem0 id too:
  `MemoryManager.address_request` add branch takes
  `mem_id = getattr(resp, "memory_id", None)` from the provider's
  `add_memory` response and records the novelty decision there —
  `aios/memory/manager.py:920-935`. That `resp.memory_id` is the Mem0
  id (`mem0.py:902-906,956`).
- `report_reward` consumes by the same key:
  `self._pending_reward_decisions.pop(memory_id, None)` for each id in
  `memory_ids_involved` — `aios/memory/manager.py:1188-1191`.

So the keyspace on both the record side and the consume side is the Mem0
record id. If the harness sent the ids that `retrieve_memory` actually
returned, they would match. **They are the same identifier space** →
candidate (c) cannot be the cause.

---

## The chain, hop by hop

### Hop 1 — retrieval returns results (provider level, WORKS)

`Mem0Provider.retrieve_memory` — `aios/memory/providers/mem0.py:1170`
onward. It resolves the per-user collection, calls `get_all`, computes a
real per-id similarity via `_raw_similarity_by_id`
(`mem0.py:1091-1169`; raw ChromaDB distance → `distance_to_similarity`),
and returns a `search_results` list where every entry has `memory_id`,
`content`, and a differentiated `similarity`
(`mem0.py:1301-1335`). Confirmed live-working by the prior pilot:
`docs/ADAPTIVE_POLICY_COMBINED_FIX_PILOT_REPORT.md` records that querying
the live kernel provider for a pilot user returned 5 results with real
similarity (0.58, 0.64, 0.62, 0.59, 0.58). **This hop is not the break.**

### Hop 2 — kernel retrieve gate filters + records (kernel level, adaptive ON)

`MemoryManager.address_request`, `retrieve_memory` branch —
`aios/memory/manager.py:965-1030`. With
`adaptive_policy.enabled: true` (confirmed in
`aios/config/config.yaml:111-112`) and a successful response carrying
`search_results`, it calls
`resp.search_results = self._apply_retrieval_policy(...)`
(`manager.py:1013-1017`).

`_apply_retrieval_policy` (`manager.py:471-611`) runs Gate 1
(`similarity_threshold` via `_filter_by_similarity`, `manager.py:522-528`
+ `613-628`), then Gate 2 (`redundancy_threshold` via
`_dedupe_by_redundancy`, `manager.py:544-548` + `630-660`), then records
one similarity + one redundancy decision **per surviving result**
(`manager.py:592-609`). Decisions are recorded ONLY for survivors: if a
gate drops a result, no decision is recorded for it and it is not
returned to the caller.

This is where candidate (a) *would* bite **if** the harness relied on the
kernel-gated result: at `alpha=1.0`, an unrewarded bandit sits at arm 0,
which for `similarity_threshold` is `0.50`
(`aios/memory/policy.py` `ACTION_SPACES["similarity_threshold"][0]` =
`0.50`). Observed Mem0 similarities (~0.58–0.64) are *above* 0.50, so
`_filter_by_similarity` (`>= threshold` keeps) would **keep** them — the
gate does not currently zero them out at 0.5. So even on the kernel path,
(a) is not firing destructively at the current arm-0 value. **This hop is
not the break either.**

### Hop 3 — harness builds `memory_ids_involved` (Cerebrum harness, THE BREAK)

The Cerebrum benchmark harness
(`benchmarks/shared_memory/pipeline.py` / `run_evaluation.py`) lives in
the **separate Cerebrum repo and is not present in this workspace**
(confirmed: a workspace-wide search for `shared_memory` finds only
stdlib `multiprocess/shared_memory.py` and an AIOS test, no benchmark
pipeline). So this hop is cited from the committed pilot evidence rather
than re-read from source here.

Per `docs/ADAPTIVE_POLICY_COMBINED_FIX_PILOT_REPORT.md`
("What the pilot showed" and "Root cause of the pilot outcome"):

- Every `report_reward` in the pilot had **empty `memory_ids_involved`**.
- The benchmark log repeated "0 results ... after ProfileAgent write"
  and every CSV row had `shared_memory_count=0` / `memory_total=0`.
- Crucially, the store was NOT empty (each user collection held 5
  records) and the **live provider returned 5 results with real
  similarity for the same `user_id`**. The 0-results are specific to
  "how the benchmark harness's audit/retrieve path scopes its HTTP
  queries — its per-writer-agent fan-out audit returned 0 while the
  provider returns 5 for the same user_id."

So the harness reads its `memory_ids_involved` from **its own
audit/retrieve HTTP response**, which is already empty by the time the
harness assembles the reward payload — the field is emptied *before*
Cerebrum's reward-building logic, by the harness's retrieval-scoping
mismatch, not by anything the kernel gate does to a populated response.

### Hop 4 — `POST /memory/report_reward` → `report_reward` (kernel, correct no-op)

The endpoint builds a `ReportRewardQuery` and dispatches through the
memory queue to `MemoryManager.report_reward`
(`aios/memory/manager.py:1102`+). With an empty `memory_ids_involved`,
the `for memory_id in memory_ids_involved or []` loop
(`manager.py:1188`) never iterates, `pending` stays empty, `n_decisions`
is 0, no `PolicyManager.update` is called, and the "reward applied" INFO
line (guarded by `if updates > 0:`, `manager.py:1263`) is never emitted.
This exactly matches the pilot's "**`reward` events logged: 0**". The
kernel is behaving correctly given an empty input — it is not the break,
it is the victim of it.

### Hop 5 — `PolicyManager.update` never invoked → bandits frozen at arm 0

Because Hop 4 makes zero `update` calls, every bandit stays at its
initial ridge state, so `select_arm` (`policy.py`, `LinUCBBandit`) keeps
returning arm 0 for every context. The pilot's all-arm-0 selection table
(novelty/similarity/redundancy each 100% arm 0) is the terminal symptom
of the Hop-3 break, not an independent policy bug.

---

## Candidate reconciliation

| Candidate | Verdict | Evidence |
|-----------|---------|----------|
| (a) similarity gate @ 0.5 drops all retrieved memories pre-credit | **Ruled out as the cause** | Arm-0 `similarity_threshold` is `0.50` (`policy.py` ACTION_SPACES); `_filter_by_similarity` keeps `sim >= threshold` (`manager.py:613-628`); observed Mem0 sims ~0.58–0.64 (pilot) are above 0.50, so the gate keeps them. More decisively, the harness never sends the kernel-gated ids anyway (Hop 3). Latent risk only. |
| (b) retrieval/audit path drops `memory_id` before the reward call | **CONFIRMED** | Pilot: every `report_reward` had empty `memory_ids_involved`; harness audit returns 0 while live provider returns 5 for the same user_id (pilot "Root cause" section). The field is empty at harness-build time, upstream of all kernel hops. |
| (c) decisions recorded under an id that never matches what's sent | **Ruled out** | Both record side (`mem0.py:1308-1312` → `manager.py:592-609,920-935`) and consume side (`manager.py:1188-1191`) key on the Mem0 record id. Same identifier space. The mismatch is *count* (0 ids sent), not *namespace*. |
| (d) some other mechanism | Not needed | (b) fully explains the observed empty payload and zero reward events. |

---

## Where Subtask 2 must act (named, not designed)

The confirmed root cause is on the **Cerebrum harness side**: its
per-trial audit/retrieve HTTP query is scoped such that it returns 0
memories even though the AIOS provider returns the records correctly for
the same `user_id`. The fix belongs to reconciling the harness's
audit/retrieve scoping with the provider's, so the harness builds a
non-empty `memory_ids_involved` from ids that the provider actually
returns. (No fix is proposed or sketched here beyond naming this
location, per the subtask's read-only scope.)
