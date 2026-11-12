# Deletion and supersession

NeurIPS Subtask 15, step 1. This spec came before the code. Its
decisions were settled on review (2026-11-10; "Decisions" at the end),
and this version records them with the design choices the code needed.
It defines what complete deletion and supersession mean for a user's
memory, how each locus provides them, and how benchmark v2 measures
them (`BENCHMARK_V2.md`, Amendment 4).

## Why

This section describes benchmark v2 before this step. Benchmark v2
(`BENCHMARK_V2.md`) deleted a fact the way one writer can: a revoke
listed the owner's own rows and deleted those whose `fact_key` is the
revoked slot ("Revoke and deletion"). It kept every earlier statement
of a fact next to the later one ("Updates and contradictions are plain
writes"). The smoke (`s14b`, revision 2,
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
  a write after the revoke can extract the value again. Until this
  step the kernel's and the replicated loci's Mem0 kept this history
  in Mem0's default `~/.mem0/history.db`, one file for every store and
  run (known issue 46; Decision 3 gives each store its own).
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
  brings one back, and no read returns one, until a new statement of
  the fact states the value again (a restatement, "After the forget"
  below).
- **Supersession**: after a later statement of a fact, the rows of its
  earlier statements are retired. A retired row stays in the store,
  marked, and is never selected for a block.

## The matcher, shared

Whatever counts as exposure must be what revocation removes (Decision
2). So the forget, the sweep, the guard and the Mem0 scrub use the
scorer's own code, not a copy:
- `normalize`, `value_in` and `match_any` move from Cerebrum
  `benchmarks/shared_memory/probes.py` into the library,
  `aios/memory/pipeline/matching.py`, with `match_forms(text, forms)`:
  the first form found.
- `probes.py` re-exports them, loading that file from the AIOS checkout
  (`AIOS_ROOT`) by path; it cannot import `aios`, which in a Cerebrum
  process resolves to the Cerebrum checkout's `aios/` stub. The scorer
  and its callers are unchanged, and `synth_v2.py`, which imports the
  names from `probes.py`, is untouched, so the dataset header's
  `generator_sha256` still matches.
- `PIPELINE_VERSION` covers the matcher with the rest of the package.
- **No module of the library imports `cerebrum`**, and a test scans
  each file of the package for an import. The scan does not follow
  imports: importing the library still loads `cerebrum.utils.usage`,
  through the providers package's Mem0 provider, so the SDK must be
  installed. The usage tag that counts a provider's own LLM and
  embedding calls to the user they serve
  (`cerebrum.utils.usage.tagged`, which the library imported before
  this step) is passed in as `usage_tag`: the kernel and the replicated
  agents pass it, so cost accounting is unchanged; library-only use
  tags nothing.
- A test pins that the scorer's functions are defined in the library's
  file.

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
   any delete, so a forget that fails partway still guards every read.
   A write that commits after the forget's listing and before its
   tombstone escapes both the forget and its own sweep; the read guard
   still drops it, and v2 never writes during a forget ("What this does
   not show").
5. **The deletes.** It deletes, through the provider, every row whose
   `fact_key` is the slot and every carrier of a form, whoever owns it.
6. **The history.** It scrubs the provider's stored messages and
   history (Mem0, Decision 3).
7. **The reply.** It returns the ids deleted, each with its owner and
   reason (`fact_key`, `value` or `alias`; `entity` for a row the
   provider's scrub deleted with an entity a form names, Graphiti,
   Subtask 16), the number of values and
   forms, the values the caller may read (from its own and shared
   rows, spelled as those rows spell them), the scrub's counts,
   `listed` (how many rows it listed) and `not_found` (rows it listed
   but found gone when deleting them, with a WARNING; their history is
   scrubbed as a deleted row's). It names ids and owners, never another
   agent's text (Decision 1). A forget that found no value says so
   (`values_count` 0): it then deleted by `fact_key` only, deleted no
   other carrier and no message (it has no form), and recorded no
   tombstone; on Mem0 the history records of the rows it deleted (or
   found gone) still lose their text, as Decision 3 says, and
   `scrubbed.history` counts them.

A provider error fails the forget. On Mem0 a failed read is an error,
not a missing row: its Chroma adapter reports a missing id with
`IndexError`, the only error `Mem0Provider.get` reads as "not found".

**Where tombstones live.** A SQLite file, read on every check. The
kernel's is the file `memory.tombstones_path` names
(`.aios_state/tombstones.sqlite` in the shipped config), whichever
provider the kernel runs: its Mem0 and in-house stores share it, and
resetting a store does not clear it. A replicated store keeps its own,
`<store root>/tombstones.sqlite`. Tombstones are keyed by user, and v2
user ids carry the run id, so no v2 cell meets another's. The kernel's
per-request pipelines and a replicated cell's four agents see the same
tombstones. The same file keeps each slot's forgotten statements (their
`provenance_event`s) apart from its tombstones, and a lift never
removes them. The path is not a pipeline setting: a replicated store
must not inherit the kernel's. Without a path, tombstones live in
memory, as in library-only use and the unit tests; a kernel restart
then loses them, so the v2 pre-flight refuses a kernel that reports no
path.

**After the forget.**
- **A re-write is suppressed.** After any write or update for a user
  with tombstones, the library lists the user's partition and deletes
  every carrier of a tombstoned form, recorded as `swept`, then scrubs
  the history. This runs inside the write's barrier hold, so a later
  re-write of the value by any agent (an echo, a fold Mem0 extracts
  again, a conversation row) is gone before a retrieval accepted after
  it can read it. A write's own rows are the rows that carry its
  note's id (`memory_note_id`): Mem0's extraction may store several. A
  write whose own rows were all swept reports `suppressed` and no id;
  one whose first row was swept and another kept returns the kept
  row's id.
- **A restatement lifts it.** A tombstone stays until a write or an
  update, by any agent, is labelled as a new statement of the fact:
  its `fact_key` is the slot, its `structured` value is the tombstoned
  value or one of its aliases (compared after the matcher's
  normalization), and it carries a `provenance_event` that is not one
  of the slot's forgotten statements. The writer supplies these labels;
  the library does not check who made the statement and takes such a
  write as the user's. That value's tombstone is lifted before the
  sweep, so the restatement is kept. The slot's forgotten statements
  outlive the lift, so after a restatement and a second forget a
  replay of any statement forgotten before is still a replay. Swept:
  a replay, a statement without a `provenance_event` (it cannot be told
  from a replay), an update that carries no event of its own (the
  stored row's event is not a new statement), and the value in any
  other row. v2 has no restatement; unit tests cover it.
- **No read returns a carrier.** A row carrying a tombstoned form is
  absent from all four retrieval paths, each with a test:
  - injection and SDK search: the selector's `after_tombstone` stage;
  - `get_memory`: `MemoryPipeline.read`, which answers "not found";
  - `list_own` (the kernel's `list_memory`): the row is left out, and
    only its id is reported, as `withheld`.

  Each drop logs a WARNING. After a complete forget nothing is
  dropped, so a drop means a carrier escaped the forget and the sweep.
  The benchmark's audit does not read through any of these paths
  ("The audit reads the store", below).
- **Not under the controls.** `no_delete` and `writer_scoped` revoke
  without a forget, so they record no tombstone, and nothing is swept
  or guarded.

**The audit reads the store.** The harness checks what a revoke left
with `revoked_value_rows` (every row, of any agent, that carries a form
of the revoked fact after the history and after the probes) and the
reappearance check (a deleted id in a later listing or block). Both,
and `probe_writes`, `extraction_failure` and the retired rows, read the
harness's listings after each session and after the probes.
- **Until this step** those listings were each agent's owner-only
  `list_own`, which now leaves tombstoned rows out. An escaped carrier
  would then be hidden from the audit by the guard, and "no carrier is
  left" would hold by construction, whether the forget worked or not.
- **So the kernel and replicated listings are the raw store**: every
  row of the user's partition, of every agent, with no visibility rule
  and no tombstone guard, grouped by owner.
  - Kernel: `GET /memory/audit?user_id=` (`MemoryManager.audit_rows`,
    the provider's `list`). A route for the audit; no agent and no SDK
    call uses it.
  - Replicated: the store's provider `list`, in process.
  - Native: unchanged, each agent's own rows through its backend, which
    has no guard.
- A carrier the forget missed therefore shows in `revoked_value_rows`
  with its text. A deletion probe's pass alone could come from the
  guard; the check also requires an empty audit and a guard that
  dropped nothing.
- **A write a forget emptied.** A forget can delete every row of a
  write made earlier in its own session (a Mem0 fold of the value), so
  the listing after the session holds no row of that write.
  `extraction_failure` excuses it when the write's reply named rows and
  the session removed every one, as it excuses a suppressed write
  (whose reply names none); any other write whose reply named no row
  still fails it (`BENCHMARK_V2.md`, Amendment 4, "Corrected during
  the smoke").

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
  `~/.mem0/history.db` (known issue 46) unless its Chroma directory is
  `~/.mem0/chroma` (a kernel started from the home directory with no
  `path`), which the v2 pre-flight refuses. `/memory/config` reports
  the kernel's path.

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
note with a `fact_key` and a `provenance_event`, if the write kept a
row of its own (a listed row that carries its note's id; a write that
stored nothing, or whose rows were all swept, retires nothing):
1. Every other row of that `fact_key` in the user's partition, of any
   agent, whose `provenance_event` differs and that is not yet marked,
   is marked `superseded_by` (the write's `provenance_event`) and
   `superseded_session` (its session, when it has one).
2. A mark is a metadata-only update (`MemoryProvider.update_metadata`):
   in-house and Mem0 keep the row's text and embedding, so a mark costs
   no embedding call and writes no Mem0 history record (the contract's
   default, for any other provider, goes through `update`). Like a
   forget, it crosses owners (Decision 1): a contradiction by the task
   writer retires the profile writer's row.
3. The write's reply lists the ids it retired.

Agents cannot set or clear marks: a write's `superseded_by` and
`superseded_session` are dropped, and an update cannot change them. An
`update_memory` retires nothing, even one that names a new event.

The selector excludes marked rows in a new stage, `after_supersession`,
after visibility and before the tombstone guard, dedupe, the threshold
and the cap, so, for every reader that may see the new statement, it
competes for the slot the stale one held. It records the excluded ids
as `superseded_rows`. The shared fetch's over-fetch (4 × k) leaves the
room; the selector does not fetch again. An own-only search (SDK
`retrieve_memory` without `sharing_policy` "shared", made only by the
v1 writers) fetches k rows, so each retired row among them leaves it a
row short; no v2 path searches own-only. Listings still return retired
rows, so a forget finds and deletes them too.

- The latest write of a slot wins, whoever wrote it: supersession
  orders statements by the order their writes arrive, not by session.
  v2 writes each statement once, in session order, so there the latest
  write is the latest statement, as the spec's rule for contradictions
  ("the later one is true") and for updates requires. A replay of an
  earlier statement after a later one would retire the later one.
- Whatever its sharing: a later statement stored private retires the
  slot's earlier rows too. Every agent but its writer, the retired
  rows' owners included, is then left with no selectable row of the
  slot, while native still shows them the earlier row. In the kernel
  and replicated loci every statement of a V1 or V3 writer is private
  (`HETEROGENEITY.md`), so at H = 1 and 2 this happens when such a
  writer contradicts a shared statement. The contradiction probe fails
  either way (the stale value without supersession, no value with it);
  only the failure changes.
- Base rows, fillers, echoes and private facts have their own slots,
  so no other write retires them.
- Mem0 rows of the new statement that name the old value as past
  ("moved from Juniper to Birch") are not retired: they are the new
  statement. The scorer still counts an answer that repeats both
  (`transition_marked`).
- Folds: a row of another fact that carries the stale value is not
  retired (its `fact_key` differs). It is counted apart, by value.
- A forget that later deletes the new statement's rows (a Mem0 fold of
  a forgotten value) leaves the earlier rows retired: the slot then
  has no selectable row.

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
- **Every branch answers.** Each memory branch of `address_request`
  (add, update, get, retrieve, `retrieve_memory_raw`, list, forget)
  catches every exception of its provider and store calls and answers
  `success` false, a failed own fetch included (in SDK search with
  `sharing_policy` "shared", a failed shared fetch is not reported,
  and the reply holds the own fetch's rows), and so does an operation
  no branch serves, so the scheduler answers every request `/query`
  accepts (`BENCHMARK_V2.md`, "Before any v2 run"). A request whose
  `params.metadata` is not a dict can still raise before or inside a
  branch; over `/query` one that would fails with HTTP 500 before it
  is queued.
- **The SDK.** `MemoryQuery.operation_type` gains `"forget_memory"`,
  and `cerebrum.memory.apis` gains `forget_memories(agent_name,
  fact_key, user_id)`. The installed copy is checked by
  `test_cerebrum_sdk_consistency.py`.
- **Replies.** A write's reply (`add_memory`) carries in `metadata`
  what it swept, retired and lifted, and whether it was suppressed. A
  listing's reply (`list_memory`) carries the ids it withheld.
- **The audit route.** `GET /memory/audit?user_id=` lists the store's
  rows for the user, unfiltered, for the benchmark's audit ("The audit
  reads the store"); it is not part of the SDK.
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
  `no_supersession`), checked per control in kernel and replicated
  cells (native runs no supersession; its setting is only recorded),
  and recorded in `run_settings`.
- **Per probe:** `after_supersession`, `superseded_rows`,
  `after_tombstone`, `tombstoned_rows` and `tombstoned_forms` (how many
  forms the guard held for the user; all five are None in native,
  which runs neither stage), and `retired_in_block`: injected
  rows whose `provenance_event` is an earlier statement of a fact with
  a later one. The last is computed from the dataset, not from the
  marks, so it measures `no_supersession` too, and a marking that
  silently failed.
- **Per user:**
  - each revoke's path (`forget` or `owner`), its ids by owner and
    reason, its value and form counts and its scrub counts;
  - each write's swept and retired ids, the values it lifted, and
    suppression;
  - `revoked_value_rows`, over every statement of the revoked slot,
    and the reappearance check, both read from the raw store ("The
    audit reads the store").
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
    of a user whose forget ran, and no probe dropped a row;
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

**Not pre-stated** (found in the smoke's first attempt, `s15`): a Mem0
fold row also states its own fact, and the forget deletes it whole, so
that fact goes with it. In its kernel Mem0 cell the forgets deleted
the only rows of users 13's and 25's recall targets, whose recall
probes then failed; `s14b`'s revokes left those folds in place, and
both passed. The smoke (`s15b`) deleted the same two folds in kernel
and replicated Mem0, and both users failed recall in both; the
analysis files such a failure as `target_forgotten` (Cerebrum
`0995994`). In-house cells store utterances verbatim. In `pilot_v2`
the only other utterances that carry a revoked value are the 10
echoes, each a carrier by design: its own value is the revoked value,
and no probe asks for an echo's fact. Besides the 30 slot rows, the
smoke's in-house forgets deleted exactly those 10 rows, so the in-house
cells lose no probed fact this way.

## Tests

Each mechanism gets a test that fails without it:
- **The matcher:** the scorer's functions are defined in the library's
  file; `match_forms` returns the first form found; the library imports
  no `cerebrum` module (a scan of every file, with a planted import to
  show the scan finds one).
- **The audit:** the kernel's `/memory/audit` and the replicated
  provider listing return a row the guard hides from the agents, and
  `revoked_value_rows` reports an escaped carrier with its text.
- **Forget:** it deletes the owner's rows, another writer's echo, a
  Mem0 fold by value and a row naming only an alias; it leaves rows
  that carry no form; it records the tombstone before its deletes; it
  waits for earlier writes and does not wait on itself; holding the
  sequence stamped for it (as the kernel stamps one), it blocks later
  retrievals; it fails cleanly on a provider error and on a listing at
  its limit; its reply names no other agent's text.
- **Suppression:** a re-write by another agent after the forget is
  swept (a statement row, an echo, a conversation row, an alias only),
  and the reply says suppressed; a restatement by the user (a new
  statement of the slot with the value or an alias) lifts the
  tombstone and is kept, and the next re-write is kept; a replay of the
  forgotten statement is swept, also after a restatement and a second
  forget; a statement without an event, and an update without an event
  of its own, lift nothing.
- **A write's own rows:** a write that stored several rows (as Mem0's
  extraction does) and lost its first to the sweep returns a kept
  row's id and is not suppressed; one that lost them all is; a write
  that shares an earlier write's event is judged by its own rows.
- **The four paths:** with an escaped carrier planted in the store
  after a forget, injection, SDK search, `get_memory` and `list_own`
  each leave it out and log a WARNING, and the listing reports its id
  as withheld.
- **Supersession:** a later statement retires earlier rows of its slot,
  across owners, without changing their text or embedding; the selector
  excludes them and records them (the tests' statements carry a
  session, so their rows carry both marks); a listing still returns
  them; a forget deletes them; `off` marks nothing; agents cannot set
  or clear marks; a write that stored nothing retires nothing, even
  when another row carries its event; retired rows leave before dedupe
  and the threshold.
- **The kernel:** `forget_memory` through `execute_request` and
  `/query`; the barrier (a retrieval accepted after a forget sees no
  deleted row); every branch, `retrieve_memory_raw` included, answers
  on an exception; `/memory/config` reports `supersession` and the
  history path.
- **Mem0:** each client's history file is the store's; the scrub
  deletes the user's messages that carry a form, clears every history
  record of the rows it deleted and the carrying text of the user's
  other rows' records, and changes nothing else, on a real `mem0ai`
  2.0.2 history file;
  a mark keeps the row's text, embedding and score; a failed read
  raises instead of reading as a missing row, so a forget over it
  fails.
- **The writers:** they revoke through `forget` in kernel and
  replicated, and through list and delete in native and under
  `writer_scoped`; every statement carries `value_aliases`.
- **The harness and the analysis:** the kernel and replicated listings
  come from the raw store, so `revoked_value_rows` sees a carrier the
  guard hides; `extraction_failure` excuses a write whose reply's rows
  its own session removed, and a suppressed write, and still fails any
  other whose reply named no row; `retired_in_block` from the dataset;
  the new criteria, with the budget reported, not required.

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
- Writes that arrive out of statement order, or replays of an earlier
  statement: supersession follows write order.
- Concurrent writers during a forget: v2 runs sessions one at a time.
  A write that commits between a forget's listing and its tombstone
  stays stored (the read guard drops it from every read).
- Mem0 history records of rows deleted before the forget by another
  path (an owner's delete) keep their text: the scrub clears the
  records of the rows it deletes and of the user's rows still stored.
  Extraction reads the messages, never these records.
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
