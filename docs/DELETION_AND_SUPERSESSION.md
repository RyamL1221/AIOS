# Deletion and supersession

NeurIPS Subtask 15. This spec comes before any code and is for review.
It defines what complete deletion and supersession mean for a user's
memory, how each locus provides them, and how benchmark v2 measures
them. Decisions the spec cannot make alone are marked **Decision** and
collected at the end.

## Why

Benchmark v2 (`BENCHMARK_V2.md`) deletes a fact the way one writer
can: a revoke lists the owner's own rows and deletes those whose
`fact_key` is the revoked slot ("Revoke and deletion"). It keeps every
earlier statement of a fact next to the later one ("Updates and
contradictions are plain writes"). The smoke (`s14b`, revision 2,
H = 0, 30 users per cell) measured what this leaves:

| Cell | Deletion, echo users | Deletion, no echo | Recency (strict) | Contradiction (strict) |
|---|---:|---:|---:|---:|
| kernel in-house | 1 / 10 | 20 / 20 | 8 / 30 | 14 / 30 |
| kernel Mem0 | 4 / 10 | 18 / 20 | 9 / 30 | 15 / 30 |
| replicated in-house | 1 / 10 | 20 / 20 | 8 / 30 | 14 / 30 |
| replicated Mem0 | 4 / 10 | 18 / 20 | 9 / 30 | 14 / 30 |
| native in-house | 2 / 10 | 20 / 20 | 13 / 30 | 11 / 30 |
| native Mem0 | 8 / 10 | 20 / 20 | 0 / 30 | 1 / 30 |

These ran with the probes' stored answers, which Amendment 3 removed,
so they are motivation, not a baseline. The baseline is the functional
check under Amendment 3 (`f15a`, "Baseline" below).

**What a revoke leaves** (`DEV_STATUS.md`, known issues 38 and 43):
- **The echo.** Another writer's row carries the value ("I booked a
  vet visit for Mochi."). Owner-only deletion cannot reach it. The store
  kept a carrier behind all 20 echo-user deletion passes of the smoke;
  the cap or native's fetch hid it from the block, not the delete.
- **Mem0 folds.** Mem0's extraction can fold the value into another
  fact's row by the same writer (users 13, 19 and 25 in the smoke's
  kernel and replicated Mem0 cells, all three failing through the fold).
  The revoke deletes by `fact_key`, so it misses the fold.
- **Mem0's message history.** Mem0 reads the scope's last 10 messages
  (user id and agent id) into each extraction. A delete leaves them, so
  a write after the revoke can extract the value again. The kernel's
  and the replicated loci's Mem0 keep this history in
  `~/.mem0/history.db`, shared by every run (known issue 46).
- **Conversation rows** that quoted the value. Since Amendment 3 v2
  probes store none, but a deployment's assistant does.

**What an update or a contradiction leaves:** the stale row, which the
consumer must tell apart from the new one by its session age. In the
smoke, recency failed for 17 to 30 of 30 users per cell and
contradiction for 15 to 29. In the revision-2 functional check, 15 of
the 45 Mem0 update rows that reached a block carried the old value
(as "moved from X").

## Baseline

The functional check under Amendment 3 (`f15a`; Cerebrum
`results/bench_v2_functional_a3/`; `DEV_STATUS.md`, Subtask 15):
`pilot_v2` users 0 to 4, Qwen, no judge, probes that write nothing,
budget 300. At H = 0:

| Cell | Deletion, echo users | Deletion, no echo | Recency (strict) | Contradiction (strict) |
|---|---:|---:|---:|---:|
| kernel in-house | 0 / 2 | 3 / 3 | 1 / 5 | 3 / 5 |
| kernel Mem0 | 1 / 2 | 3 / 3 | 1 / 5 | 3 / 5 |
| replicated in-house | 0 / 2 | 3 / 3 | 1 / 5 | 3 / 5 |
| replicated Mem0 | 1 / 2 | 2 / 3 | 3 / 5 | 3 / 5 |
| native in-house | 0 / 2 | 3 / 3 | 2 / 5 | 3 / 5 |
| native Mem0 | 2 / 2 | 3 / 3 | 0 / 5 | 0 / 5 |

- **Deletion.** Every failure in the real conditions (H = 0 and 2)
  came through the echo row of users 0 and 4, except one Mem0 fold
  (replicated Mem0, H = 0, user 1). Native Mem0 passed for every user,
  though both echoes stayed in its store: its ranking keeps the rows
  nearest the question out of the fetch (`NATIVE_USAGE.md`,
  "Evidence").
- **Recency and contradiction.** In every kernel and replicated cell
  at H = 0, the stale row reached the block in all 5 recency and all 5
  contradiction probes, next to the new one. Every failing recency
  answer named both values (14 of 14, the stale one as past in 12),
  and 6 of the 8 failing contradiction answers did not name the later
  value.
- **The budget.** The check failed one criterion: 300 bound in no
  kernel or replicated in-house probe (Decision 8).

## Terms

- A **fact** of a user is a slot with a value (`BENCHMARK_V2.md`,
  "Facts"). Its **statements** are the writes that state it: the add,
  each update, and a contradiction by another writer. Each has the
  slot as `fact_key`.
- A **carrier** of a value is any row of the user, of any agent and
  any memory type, whose text holds the value under the scoring matcher
  (`BENCHMARK_V2.md`, "Scoring"): the statements' rows, an echo, a
  Mem0 fold, a conversation row.
- **Complete deletion** of a revoked fact: after the revoke, no row of
  the user carries any value the fact had, and no later write brings
  one back, until the user states the fact again.
- **Supersession**: after a later statement of a fact, the rows of its
  earlier statements are retired. A retired row stays in the store,
  marked, and is never selected for a block.

## Deletion

### Kernel and replicated: a user-scoped forget

Both loci run the library (`aios/memory/pipeline`), so one
implementation serves both, as list and delete do now.

`MemoryPipeline.forget(agent_name, user_id, fact_key)`:
1. Waits for the user's pending writes (the write barrier), as a
   listing does, and holds the barrier while it runs, as a write does.
2. Lists every row in the user's partition, of every agent.
3. Collects the fact's values: the `structured` value of every row
   whose `fact_key` is the revoked slot (Mem0 copies a write's metadata
   onto each fact it extracts, so this reads the values the writers
   stated, not Mem0's rewording).
4. Deletes every row with that `fact_key`, of any agent, and every
   carrier of a value (step 3), of any agent.
5. Records a **tombstone**: the user, the slot and its values.
6. Returns the ids deleted, by owner and by reason (`fact_key`,
   `value`), and the values.

**Decision 1, authority.** This deletes other agents' rows, which the
library's owner-only rule (Subtask 2) forbids. The proposal: a forget
is the user's request, not an agent's; any agent serving the user may
make it; the kernel or library acts for the user and logs the agent
that asked. It deletes; it never reads another agent's private row
back to the caller (the reply names ids and owners, not texts).

**Decision 2, matching.** The proposal matches carriers by the stated
values under the scoring matcher, the rule that decides a deletion
probe's failure. The values' aliases are not used: the store does not
know them (the dataset does). So a row that names only an alias
("Ms. Sandvik") survives, and its deletion probe fails; such rows are
counted apart. The alternative, matching by provenance links, finds
an echo only through the dataset's `echo_of`, which no real writer
records.

**After the forget: the tombstone.**
- **Post-write sweep.** After any write for a user with tombstones,
  the library checks the rows that write stored (its
  `provenance_event`'s rows; for Mem0, every extracted fact) and
  deletes each carrier of a tombstoned value, recorded as `swept`. This
  removes what Mem0 extracts again from its message history (a fold
  after the revoke).
- **A restatement lifts it.** A write whose own `structured` value is a
  tombstoned value of its slot lifts that value's tombstone: the user
  stated the fact again. v2 has no such event; a unit test covers it.
- **Selection guard.** The selector drops any candidate that carries a
  tombstoned value (a new stage, `after_tombstone`) and logs a WARNING:
  after a complete deletion it drops nothing, so a drop means a carrier
  escaped. It keeps a block free of the value either way.
- **Storage.** Tombstones persist with the store: a sidecar next to the
  provider's data (`memory.tombstones.path`), keyed by user id, so a
  kernel restart keeps them.

**Decision 3, Mem0's message history.** The sweep removes what Mem0
re-extracts, but the value stays in Mem0's stored messages. Options:
- (a) leave the messages; rely on the sweep and the guard, and report
  how many swept rows each run had;
- (b) also scrub the value from the user's message rows in Mem0's
  SQLite history (an internal table of `mem0ai` 2.0.2, pinned; a test
  pins the schema), so a later extraction never sees it;
- and in either case, give the kernel's and the replicated Mem0
  provider an explicit `history_db_path` inside the store, so a store
  and its history are reset together (known issue 46).

Recommended: (b) with the explicit path. Deletion is a user's request
to be forgotten, and only (b) removes the value from every place the
memory system keeps it; (a) leaves it where Mem0 reads it for every
extraction.

### Native

Native agents use their backend's documented calls and manage their
own rows (`NATIVE_USAGE.md`). A native revoke stays writer-scoped: the
owner lists its own rows and deletes the fact's. Mem0's `delete`
accepts any id, so a native agent could delete other agents' rows, but
only under a convention every agent shares, which is what the kernel
provides. Native is therefore the reference for agent-managed deletion,
and its echo and fold failures are expected.

**Decision 4.** Keep native writer-scoped (proposed), or add a
"careful developer" native convention: the revoking writer searches the
user's whole store for the fact's values and deletes every match (Mem0
`search` with the user's id, then `delete`; Chroma `get` on the user's
collection). The second removes the locus difference by design; it
could be a heterogeneity variant instead.

## Supersession

### Kernel and replicated: mark and exclude

`MemoryPipeline.write`, after a successful write of a note with a
`fact_key`:
1. Lists the user's rows of that `fact_key`, of every agent, whose
   `provenance_event` is not this write's.
2. Marks each `superseded_by` (this write's `provenance_event`) and
   `superseded_session` (its session), through the provider contract's
   `update` with the row's own text (the Mem0 provider re-sends it,
   one embedding call per row). Like a forget, this crosses owners: a
   contradiction by the task writer retires the profile writer's row
   (Decision 1 covers it).
3. Logs the ids it marked. The harness reads the marks from its
   listings (each row's `superseded_by`), so no reply changes.

The selector excludes rows with `superseded_by` (a new stage,
`after_supersession`, before dedupe, the threshold and the cap, so the
new statement competes for the slot the stale one held). Listings still
return retired rows, so a forget finds and deletes them too.

- The latest statement wins, whoever wrote it. That is the spec's rule
  for contradictions ("the later one is true") and for updates.
- Base rows, fillers, echoes and private facts have their own slots,
  so no other write retires them.
- Mem0 rows of the new statement that name the old value as past
  ("moved from Juniper to Birch") are not retired: they are the new
  statement. The scorer still counts an answer that repeats both
  (`transition_marked`).
- Folds: a row of another fact that carries the stale value is not
  retired (its `fact_key` differs). It is counted apart, by value.

**Decision 5.** Exclude retired rows (proposed), or keep them and mark
them in the block ("previously Juniper"). Excluding is the cleaner
test of supersession; marking tests whether the consumer can read a
marked history.

### Native

**Decision 6.** Native agents have no shared rule for this either.
Options:
- (a) none: Mem0 2.0's additive extraction keeps both rows, as its
  documentation describes, and a minimal Chroma writer adds rows
  (proposed, the agent-managed reference);
- (b) writer-scoped replace: on an update, the owner deletes its own
  earlier rows of the slot (documented calls). A contradiction comes
  from another writer, so its stale row stays.

## Kernel and SDK

- A memory operation `forget_memory` (`params: {user_id, fact_key}`),
  dispatched by `execute_request` and handled by
  `MemoryManager.address_request` through `MemoryPipeline.forget`.
  Every branch catches every exception and returns `success` false
  (`BENCHMARK_V2.md`, "Before any v2 run").
- The SDK's `MemoryQuery.operation_type` gains `"forget_memory"`, and
  `cerebrum.memory.apis` gains `forget_memories(agent_name, fact_key,
  user_id)`. The installed copy is checked by
  `test_cerebrum_sdk_consistency.py`.
- Settings under `memory.pipeline`: `forget_scope` (`writer` or
  `user`) and `supersession` (`off` or `exclude`, or `mark` if Decision
  5 takes it), reported by `/memory/config`. The defaults keep today's
  behavior (`writer`, `off`); v2 runs set `user` and `exclude`, and the
  pre-flight checks them. Each edit changes `PIPELINE_VERSION`.
- The kernel and replicated v2 writers revoke through `forget` when
  `forget_scope` is `user`, and through list and delete otherwise.

## Order of work, after review

1. The library: `forget`, the tombstones and the sweep, supersession
   and the two selector stages, with their tests.
2. The kernel operation, the SDK call and the settings, with their
   tests, and the v2 writers' revoke through `forget`.
3. The harness records and the controls; the functional check; then
   the smoke.
4. One adversarial review of the code and the write-up and one
   verification pass of its fixes (`DEV_STATUS.md`, rule 6), and
   mutation testing once, on the final code.

## Benchmark v2 changes

- **Settings and pre-flight** as above, recorded in `run_settings`.
- **Per probe** (diagnostics): `after_supersession`, `after_tombstone`,
  the retired and tombstoned rows each stage dropped, and whether a
  retired row reached the block (it must not, in kernel and
  replicated).
- **Per user:** each forget's ids by owner and reason, its values, the
  rows swept after later writes, each write's retired ids, and the
  existing `revoked_value_rows` and reappearance checks, which must come
  out empty in kernel and replicated.
- **A control per mechanism, at H = 0:**
  - `writer_scoped`: `forget_scope` `writer`. Deletion then fails for
    echo users wherever the echo is retrievable, as in Subtask 14.
  - `no_supersession`: `supersession` `off`. Retired rows return to the
    blocks.

  Each runs in the kernel and replicated cells, paired with the
  reference over users. The existing controls stay.
- **Functional check** (`pilot_v2` users 0 to 4, Qwen, no judge, as in
  Subtask 14). It passes when:
  - in kernel and replicated, on both backends, every deletion probe
    passes and every forget leaves `revoked_value_rows` empty, echo
    users included, and `writer_scoped` fails some echo user;
  - no retired row reaches a kernel or replicated block, and
    `no_supersession` puts one in some block;
  - the selection guard drops nothing (a drop fails the check: a
    carrier escaped the forget);
  - the Subtask 14 criteria still hold, the budget's as Decision 8
    settles it.

**Decision 8, the budget** (`DEV_STATUS.md`, open decision 4). `f15a`
failed its budget criterion: 300 bound in no kernel or replicated
in-house probe of users 0 to 4 (largest block 291 estimated tokens),
and in 3 Mem0 probes. Options:
- (a) keep 300, and check the in-house criterion on the smoke's 30
  users, once a writer-only replay of their in-house stores on revision
  3 (embedding calls only) shows where it binds (proposed);
- (b) 280, which binds in 14 of the check's 112 in-house probes without
  cutting a base row or a probe's value row, but cuts base rows in the
  smoke that native, with no budget, keeps;
- (c) no budget criterion.

Supersession and the forget change which rows fill a block, so the
check after this subtask's code measures the budget again either way.

## Pre-stated expectations

Expectations, not rules:
- **Kernel and replicated:** deletion passes for every user on
  in-house. On Mem0, a row that names only an alias, or a value Mem0
  reworded, can survive and fail its probe.
- **Recency and contradiction** improve in kernel and replicated: the
  stale row never reaches the block. Failures that remain: the new row
  outside the cap, a Mem0 transition row that names both values, or a
  model that answers from its own knowledge.
- **Native** is unchanged on deletion (Decision 4), and on supersession
  under Decision 6 (a). The kernel-against-native contrast on echo
  deletion and on contradiction is the measured cost of agent-managed
  memory without a shared rule.

## Tests

Each mechanism gets a test that fails without it:
- forget deletes the owner's rows, another writer's echo, a Mem0 fold
  by value, and records the tombstone; it leaves rows that carry no
  value; it fails cleanly on a provider error;
- the post-write sweep deletes a re-extracted carrier; a restatement
  lifts the tombstone;
- the selection guard drops a tombstoned carrier and logs a WARNING;
- a later statement retires earlier rows of its slot, across owners;
  the selector excludes them; a listing still returns them; a forget
  deletes them;
- `forget_memory` through `execute_request` and `/query`, and the
  barrier: a retrieval accepted after a forget sees no deleted row;
- the v2 writers revoke through forget in kernel and replicated, and
  through list and delete in native and under `writer_scoped`;
- (Decision 3 (b)) the scrub removes the value from Mem0's stored
  messages and nothing else, on a real `mem0ai` 2.0.2 history file.

## What this does not show

- What the consumer already said: an answer is not memory.
- Aliases and rewordings the store cannot know (Decision 2).
- Concurrent writers during a forget: v2 runs sessions one at a time.
- Retention outside the memory system (logs, the model provider).
- In-place updates of extracted facts (known issue 23).

## Decisions for review

1. **Authority:** a forget and a supersession cross agents, as the
   user's request (proposed), or stay owner-only.
2. **Matching:** carriers by the stated values under the scoring
   matcher, without aliases (proposed), or by provenance.
3. **Mem0's message history:** scrub it (b, proposed) or rely on the
   sweep (a); in both, an explicit history path per store.
4. **Native deletion:** writer-scoped (proposed) or a search-and-delete
   convention (or a variant).
5. **Retired rows:** excluded (proposed) or marked in the block.
6. **Native supersession:** none (proposed) or writer-scoped replace.
7. **Runs:** the functional check, then a smoke on `pilot_v2` (30
   users, H = 0, all six cells, judge on integration), as in Subtask 14,
   before any full run.
8. **The budget:** keep 300 and check it on the smoke (proposed), 280,
   or no budget criterion.
