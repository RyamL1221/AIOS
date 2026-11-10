# Deletion and supersession

NeurIPS Subtask 15, step 1. This spec came before the code. Its
decisions were settled on review (2026-11-10; "Decisions" at the end),
and this version records them with the design choices the code needed.
It defines what complete deletion and supersession mean for a user's
memory, how each locus provides them, and how benchmark v2 measures
them (`BENCHMARK_V2.md`, Amendment 4).

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
- **The echo.** Another writer's row carries the value ("I booked a vet
  visit for Mochi."). Owner-only deletion cannot reach it. The store
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
- **The budget.** 300 bound in no kernel or replicated in-house probe
  (Decision 8: its binding is now reported, not required).

## Terms

- A **fact** of a user is a slot with a value (`BENCHMARK_V2.md`,
  "Facts"). Its **statements** are the writes that state it: the add,
  each update, and a contradiction by another writer. Each has the
  slot as `fact_key`.
- A **form** of a value is the value or one of its aliases.
- A **carrier** of a value is any row of the user, of any agent and
  any memory type, whose text holds a form of the value under the
  scorer's matcher (below): the statements' rows, an echo, a Mem0 fold,
  a conversation row. A row's text is its stored content and its
  formatted text (`format_memory`), since the scorer reads the
  formatted block.
- **Complete deletion** of a revoked fact: after the revoke, no row of
  the user carries any form of any value the fact had, no later write
  brings one back, and no read returns one, until the user states the
  fact again.
- **Supersession**: after a later statement of a fact, the rows of its
  earlier statements are retired. A retired row stays in the store,
  marked, and is never selected for a block.

## The matcher, shared

Whatever counts as exposure must be what revocation removes (Decision
2). So the forget, the sweep, the guard and the Mem0 scrub use the
scorer's own code, not a copy:
- `normalize`, `value_in` and `match_any` move from Cerebrum
  `benchmarks/shared_memory/probes.py` to the SDK package,
  `cerebrum/utils/matching.py`, which also gains `match_forms(text,
  forms)`: the first form found.
- `probes.py` imports and re-exports them, so the scorer and its
  callers are unchanged. `synth_v2.py` is untouched, so the dataset
  header's `generator_sha256` still matches.
- The library (`aios/memory/pipeline`) imports the same module, as it
  already imports `cerebrum.utils.usage`. `PIPELINE_VERSION` hashes
  the module's bytes with the package's, so a kernel and a replicated
  agent running different matchers show different versions.
- Tests pin that `probes.value_in is matching.value_in` and that the
  library calls the same functions. `test_cerebrum_sdk_consistency.py`
  checks the kernel venv's installed copy.

## Aliases on every statement

The store did not know a value's aliases: `structured` holds
`{fact_key, value, event_type}`, and a revoke event names the slot.
A v2 write of an event with a value now also carries `value_aliases`,
the event's aliases as a JSON string (`'["Sandvik"]'`; `'[]'` when
there are none, since Chroma refuses an empty list).
- It is a key of its own, not part of `structured`, which V5 stores as
  a row's content.
- Mem0 copies a write's metadata onto every fact it extracts, so each
  extracted row of a statement carries the statement's forms.
- Only the forget and the restatement check read it. The block, the
  scorer and every other path are unchanged.

## Deletion

### Kernel and replicated: a user-scoped forget

Both loci run the library, so one implementation serves both, as list
and delete do now.

`MemoryPipeline.forget(agent_name, user_id, fact_key)`:
1. **The barrier.** A forget needs a user. It holds a barrier sequence
   (the kernel stamps one when the request is accepted) until it
   returns, so a retrieval accepted after it sees its result. It first
   waits for the user's writes accepted before it, through `sequence -
   1`, never a fresh snapshot, which would include its own sequence.
2. **The listing.** It lists every row in the user's partition, of
   every agent, through the provider's `list` (not `list_own`). A
   listing that reaches its limit (`LIST_TOP_K`) fails the forget.
3. **The forms.** It collects the fact's forms: the `structured` value
   and the `value_aliases` of every row whose `fact_key` is the slot
   (Mem0 copies the writer's metadata onto each fact, so these are the
   values the writers stated, not Mem0's rewording), and those of any
   tombstone the slot already has.
4. **The tombstone first.** It records a tombstone: the user, the slot,
   each value with its aliases, the forgotten statements'
   `provenance_event`s and the agent that asked. It does so before
   any delete, so a forget that fails partway still guards every read,
   and a write that commits meanwhile is swept.
5. **The deletes.** It deletes, through the provider, every row whose
   `fact_key` is the slot and every carrier of a form, whoever owns it.
6. **The history.** It scrubs the provider's stored messages and
   history (Mem0, Decision 3).
7. **The reply.** It returns the ids deleted, each with its owner and
   reason (`fact_key`, `value` or `alias`), the number of values and
   forms, the values the caller may read (from its own and shared
   rows), and the scrub's counts. It names ids and owners, never
   another agent's text (Decision 1). A forget that found no value says
   so (`values_count` 0): it then deleted by `fact_key` only.

**Where tombstones live.** A SQLite sidecar per store, read on every
check: the kernel's `memory.tombstones_path` (default
`.aios_state/tombstones.sqlite`), and `<store root>/tombstones.sqlite`
for a replicated store. So the kernel's per-request pipelines and a
replicated cell's four agents see the same tombstones. The path is not
a pipeline setting: a replicated store must not inherit the kernel's.
Library-only use without a path keeps tombstones in memory.

**After the forget.**
- **A re-write is suppressed.** After any write or update for a user
  with tombstones, the library lists the user's partition and deletes
  every carrier of a tombstoned form, recorded as `swept`, then scrubs
  the history. This runs inside the write's barrier hold, so a later
  re-write of the value by any agent (an echo, a fold Mem0 extracts
  again, a conversation row) is gone before a retrieval accepted after
  it can read it. A write whose own rows were all swept reports
  `suppressed` and no id.
- **Only the user lifts it.** A tombstone stays until the user states
  the fact again: a write whose `fact_key` is the slot, whose
  `structured` value is the tombstoned value or one of its aliases
  (compared after the matcher's normalization), and whose
  `provenance_event` is not one of the forgotten statements'. That
  value's tombstone is lifted before the sweep, so the restatement is
  kept. A replay of a forgotten statement, or the value in any other
  row, is swept. v2 has no restatement; unit tests cover it.
- **No read returns a carrier.** A row carrying a tombstoned form is
  absent from all four retrieval paths, each with a test:
  - injection and SDK search: the selector's `after_tombstone` stage;
  - `get_memory`: `MemoryPipeline.read`, which answers "not found";
  - `list_own` (the kernel's `list_memory`): the row is left out, and
    only its id is reported, as `withheld`.

  Each drop logs a WARNING. After a complete forget nothing is
  dropped, so a drop means a carrier escaped the forget and the sweep.
  The harness counts withheld ids as carriers, so the guard cannot
  hide an incomplete deletion from the audit.
- **Not under the controls.** `no_delete` and `writer_scoped` revoke
  without a forget, so they record no tombstone, and nothing is swept
  or guarded.

**Decision 1, authority (settled: yes).** A forget deletes other
agents' rows, which the library's owner-only rule (Subtask 2) forbids.
A forget is the user's request, not an agent's: any agent serving the
user may make it, and the library acts for the user and logs the agent
that asked. It deletes; it never reads another agent's private row back
to the caller.

**Decision 2, matching (settled: the scorer's matcher, aliases
included).** Carriers are matched by the fact's stated values and their
aliases, with the scorer's own code. Otherwise the scorer could count
an alias in the block as exposure the revoker was never allowed to
remove, and the kernel would fail a deletion probe for a definitional
reason. Only a rewording the matcher does not find survives (Mem0
paraphrasing a value).

**Decision 3, Mem0's message history (settled: scrub it, and a history
file per store).**
- **The scrub.** The forget and the sweep delete every stored message
  of the user, in any agent's scope, whose content carries a form. They
  also clear the text (`old_memory`, `new_memory`) of every history
  record of a deleted row, and of any record of the user's other rows
  that carries a form.
  - Messages go whole: extraction reads them verbatim, and a redaction
    cannot be mapped back through the matcher's normalization.
  - A scope is the user's when its `user_id` entry is the user's id,
    compared exactly, never with SQL `LIKE` (v2 ids contain `_`).
  - A test pins mem0ai 2.0.2's schema and the scrub on a real history
    file.
- **A history file per store.** The kernel's and the replicated Mem0
  provider set `history_db_path` inside the store
  (`<store root>/history.db`, next to its `chroma` directory), so a
  store and its history go together, and no run shares the old
  `~/.mem0/history.db` (known issue 46). `/memory/config` reports the
  kernel's path.

### Native

Native agents use their backend's documented calls and manage their
own rows (`NATIVE_USAGE.md`). A native revoke stays writer-scoped: the
owner lists its own rows and deletes the fact's, as the backends'
documented delete by id allows. Native is the reference for
agent-managed deletion, and its echo and fold failures are expected.

**Decision 4 (settled: writer-scoped).**

## Supersession

### Kernel and replicated: mark and exclude

With `memory.supersession: exclude`, after a successful write of a
note with a `fact_key` and a `provenance_event`, if the write stored a
row (a row of its `provenance_event` is listed):
1. Every other row of that `fact_key` in the user's partition, of any
   agent, whose `provenance_event` differs and that is not yet marked,
   is marked `superseded_by` (the write's `provenance_event`) and
   `superseded_session` (its session, when it has one).
2. A mark is a metadata-only update (`MemoryProvider.update_metadata`):
   in-house and Mem0 keep the row's text and embedding, so a mark costs
   no embedding call and writes no Mem0 history record. Like a forget,
   it crosses owners (Decision 1): a contradiction by the task writer
   retires the profile writer's row.
3. The write's reply lists the ids it retired.

Agents cannot set or clear marks: a write's `superseded_by` and
`superseded_session` are dropped, and an update cannot change them.

The selector excludes marked rows in a new stage, `after_supersession`,
after visibility and before the tombstone guard, dedupe, the threshold
and the cap, so the new statement competes for the slot the stale one
held. It records the excluded ids as `superseded_rows`. The shared
fetch's over-fetch (4 × k) leaves the room; the selector does not
fetch again. Listings still return retired rows, so a forget finds and
deletes them too.

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

With `supersession: off` (the default, and the `no_supersession`
control) nothing is marked or excluded, as before.

**Decision 5 (settled: exclude),** recording the excluded rows
(`superseded_rows`).

### Native

**Decision 6 (settled: none).** Mem0 2.0's additive extraction keeps
both rows, as its documentation describes, and a minimal Chroma writer
adds rows; nothing in either's documented usage retires a row. Native
is the agent-managed reference here too.

## Kernel and SDK

- **The operation.** `forget_memory` (`params: {user_id, fact_key}`)
  is dispatched by `execute_request`, stamped with a barrier sequence
  when it is accepted (`MemoryManager.stamp_syscall`), and handled
  through `MemoryPipeline.forget`; its reply's `metadata` holds the
  report.
- **Every branch answers.** Each memory branch that runs this step's
  code (add, update, get, retrieve, list, forget) catches every
  exception and answers `success` false, so the scheduler always
  answers (`BENCHMARK_V2.md`, "Before any v2 run").
- **The SDK.** `MemoryQuery.operation_type` gains `"forget_memory"`,
  and `cerebrum.memory.apis` gains `forget_memories(agent_name,
  fact_key, user_id)`. The installed copy is checked by
  `test_cerebrum_sdk_consistency.py`.
- **Replies.** A write's reply (`add_memory`) carries in `metadata`
  what it swept, retired and lifted, and whether it was suppressed. A
  listing's reply (`list_memory`) carries the ids it withheld.
- **Settings**, flat keys under `memory:` like the other selection
  settings:
  - `supersession` (`off` or `exclude`): in `PipelineSettings`, so
    `/memory/config` reports it and replicated agents copy it, and set
    by `set_memory_mode.py --supersession`;
  - `tombstones_path`: the kernel's sidecar, read by the manager only.

  The defaults keep today's behavior. `PIPELINE_VERSION` covers the new
  modules and the matcher.
- **Who chooses the forget.** The writer, not a kernel setting. The
  kernel and replicated v2 writers revoke through `forget`, and through
  their own list and delete under `writer_scoped` and in native. Each
  revoke records which it used (`revoke_path`), so a cell's choice is
  checked revoke by revoke. This replaces the reviewed draft's
  `forget_scope` setting: a control that only changes what the writer
  does needs no kernel of its own, and a per-revoke record is a stronger
  check than a reported setting.

## Order of work

1. The shared matcher; the library's `forget`, tombstones, sweep,
   supersession, `read` and the two selector stages; the providers'
   metadata-only update, history path and scrub; with their tests.
2. The kernel operation, the SDK call and the settings, with their
   tests, and the v2 writers' revoke through `forget`.
3. The harness records and the controls; the functional check; then
   the smoke.
4. One adversarial review of the code and the write-up and one
   verification pass of its fixes (`DEV_STATUS.md`, rule 6), and
   mutation testing once, on the final code.

## Benchmark v2 changes

`BENCHMARK_V2.md`, Amendment 4, states these as the benchmark's rules:
- **Settings and pre-flight:** `supersession: exclude` (`off` under
  `no_supersession`), checked per control and recorded in
  `run_settings`.
- **Per probe:** `after_supersession`, `superseded_rows`,
  `after_tombstone`, `tombstoned_rows` and `tombstoned_forms` (how many
  forms the guard held for the user), and `retired_in_block`: injected
  rows whose `provenance_event` is an earlier statement of a fact with
  a later one. The last is computed from the dataset, not from the
  marks, so it measures `no_supersession` too, and a marking that
  silently failed.
- **Per user:**
  - each revoke's path (`forget` or `owner`), its ids by owner and
    reason, its value and form counts and its scrub counts;
  - each write's swept, retired and lifted ids, and suppression;
  - each listing's withheld ids;
  - `revoked_value_rows`, over every statement of the revoked slot and
    the withheld ids, and the reappearance check.
- **Controls at H = 0**, in the kernel and replicated cells on both
  backends, beside the existing ones:
  - `writer_scoped`: the writers revoke by their own list and delete,
    with no forget. Deletion then fails for echo users wherever the
    echo is retrievable, as in Subtask 14.
  - `no_supersession`: `supersession: off`, in kernels of its own,
    since the kernel and the replicated agents read the setting.
    Retired rows return to the blocks.
- **The functional check** (`pilot_v2` users 0 to 4, Qwen, no judge, as
  in Subtask 14) passes when, at H = 0, in the kernel and replicated
  cells on both backends:
  - every deletion probe passes (an unscored probe or a failed trial
    counts against it), every trial's `revoked_value_rows` is empty,
    every revoke went through `forget`, and `writer_scoped` fails some
    echo user;
  - no block holds a retired row, and `no_supersession` puts one in
    some block;
  - the guard was armed and dropped nothing: every probe reports
    `after_tombstone`, `tombstoned_forms` is positive in every probe
    of a user whose forget ran, and no probe dropped and no listing
    withheld a row;
  - every Mem0 forget scrubbed at least one message (each revoked value
    was stated in an utterance Mem0 stored as a message);
  - the Subtask 14 criteria still hold, except the budget's, which is
    reported, not required (Decision 8). The cap must still bind.

  H = 2 is reported, not required: its V2 identity variant writes under
  another partition in replicated, which a forget for the canonical id
  does not reach.

**Decision 8, the budget (settled: 300, binding reported).** The
budget stays 300. Whether it binds is reported, not required, in the
functional check and in the smoke. If it never binds in the smoke's 30
users, that is a finding about v2's row sizes, not a design failure:
the cap is the limit that matters, and it must bind. The writer-only
replay proposed before the smoke is not needed.

## Pre-stated expectations

Expectations, not rules:
- **Kernel and replicated:** deletion passes for every user at H = 0
  on both backends, unless Mem0 rewords a value past the matcher.
- **Recency and contradiction** improve in kernel and replicated: the
  stale row never reaches the block. Failures that remain: the new row
  outside the cap, a Mem0 transition row that names both values, or a
  model that answers from its own knowledge.
- **Native** is unchanged on deletion (Decision 4) and supersession
  (Decision 6). The kernel-against-native contrast on echo deletion and
  on contradiction is the measured cost of agent-managed memory without
  a shared rule.
- **The sweep and the scrub** act only through Mem0: v2 scripts no
  utterance that carries a revoked value after its revoke, so in-house
  cells never exercise suppression. Their correctness rests on the unit
  tests, and on the criterion that the guard drops nothing.

## Tests

Each mechanism gets a test that fails without it:
- **The matcher:** the scorer and the library call the same functions;
  `match_forms` returns the first form found.
- **Forget:** it deletes the owner's rows, another writer's echo, a
  Mem0 fold by value and a row naming only an alias; it leaves rows
  that carry no form; it records the tombstone before its deletes; it
  waits for earlier writes and blocks later retrievals without waiting
  on itself; it fails cleanly on a provider error and on a listing at
  its limit; its reply names no other agent's text.
- **Suppression:** a re-write by another agent after the forget is
  swept (a statement row, an echo, a conversation row, an alias only),
  and the reply says suppressed; a restatement by the user (a new
  statement of the slot with the value or an alias) lifts the
  tombstone and is kept, and the next re-write is kept; a replay of the
  forgotten statement is swept.
- **The four paths:** with an escaped carrier planted in the store
  after a forget, injection, SDK search, `get_memory` and `list_own`
  each leave it out and log a WARNING, and the listing reports its id
  as withheld.
- **Supersession:** a later statement retires earlier rows of its slot,
  across owners, without changing their text or embedding; the selector
  excludes them and records them; a listing still returns them; a
  forget deletes them; `off` marks nothing; agents cannot set or clear
  marks; a write that stored nothing retires nothing.
- **The kernel:** `forget_memory` through `execute_request` and
  `/query`; the barrier (a retrieval accepted after a forget sees no
  deleted row); every branch answers on an exception; `/memory/config`
  reports `supersession` and the history path.
- **Mem0:** each client's history file is the store's; the scrub
  removes the value from the stored messages and history records of
  the user and nothing else, on a real `mem0ai` 2.0.2 history file;
  a mark keeps the row's text, embedding and score.
- **The writers:** they revoke through `forget` in kernel and
  replicated, and through list and delete in native and under
  `writer_scoped`; every statement carries `value_aliases`.
- **The harness and the analysis:** the audit counts a withheld id as a
  carrier; `retired_in_block` from the dataset; the new criteria, with
  the budget reported, not required.

## What this does not show

- What the consumer already said: an answer is not memory.
- Rewordings the matcher does not find (Mem0 paraphrasing a value).
- **Chroma's own log.** Chroma keeps the text of every deleted row in
  its write-ahead log (`embeddings_queue` in `chroma.sqlite3`) until
  the log is purged. Every kernel and replicated store measured on
  2026-11-10 still held the ADD record of each row ever deleted from
  it (kernel Mem0 111 of 111, kernel in-house 65 of 65, each `f15a`
  replicated store 10 of 10). No API call purges it while a client has
  the store open. Complete deletion here covers what the memory system
  reads: the rows, Mem0's messages and Mem0's history.
- Concurrent writers during a forget: v2 runs sessions one at a time.
- Retention outside the memory system (logs, the model provider).
- Rows another identity convention puts in another partition (H = 2).
- In-place updates of extracted facts (known issue 23).

## Decisions (settled on review, 2026-11-10)

1. **Authority:** a forget and a supersession cross agents, as the
   user's request. They are the placement difference the probes
   measure.
2. **Matching:** the fact's stated values with their aliases, under
   the scorer's own matcher: whatever counts as exposure is what
   revocation removes.
3. **Mem0's message history:** scrubbed, and each kernel and replicated
   store gets its own history file; the shared file was a parity bug on
   its own.
4. **Native deletion:** writer-scoped, as its documented delete by id
   allows.
5. **Retired rows:** excluded from the block, the excluded rows
   recorded in diagnostics (`superseded_rows`).
6. **Native supersession:** none; nothing in Mem0's documented usage
   does it.
7. **Runs:** the functional check, then a smoke on `pilot_v2` (30
   users, H = 0, all six cells, judge on integration), as in Subtask 14,
   before any full run.
8. **The budget:** 300, its binding reported, not required: "cap
   binds; budget binding is reported, not required."

Added on review: a tombstone suppresses a later re-write of the same
value by any agent until the user re-asserts it, and tombstoned rows
are absent from all four retrieval paths (injection, SDK search,
`get_memory`, `list_own`), each with a test.
