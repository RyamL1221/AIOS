# Benchmark v2: memory over time

NeurIPS Subtask 14. This spec was committed before the generator code.
It defines the accumulating multi-session benchmark: the users
(`users_v2`, 150 users, and `pilot_v2`, the first 30), their scripted
histories, the six probes and their ground truth, the scoring, the
harness flow, and the kernel support the probes exercise. It is the
benchmark the paper owns; the adaptive-gating paper reuses it.

## Why a second benchmark

`users_v1` gives each user one interaction: two writers store the
profile and the task context once, and the consumer answers one
question. Memory never accumulates.
- **No pressure.** In the pilot's 1,080 trials, the largest block held
  8 rows and about 250 estimated tokens, against a cap of 10 rows and
  a budget of 2,000 tokens. Neither ever bound.
- **No time.** Nothing is updated, contradicted or deleted, so
  recency and deletion are untested. HETEROGENEITY.md lists the effects
  that need history ("the update path generally").

In v2 each user accumulates about 15 to 20 writer rows over six
sessions written by three agents. Six probes then ask questions whose
answers depend on cross-agent recall, recency, deletion and privacy.

## A user

- **Base.** User *i* of `users_v2` is user *i* of `users_v1`: its
  profile, task context, `follow_up_query` and `plausible_actions`.
  So `pilot_v2` has the same 30 base users as `pilot_v1`.
- **Agents.** Three writers, `profile_agent`, `task_agent` and the new
  `calendar_agent`, and the consumer, `assistant_agent`. Where an order
  matters, `WRITERS = (profile_agent, task_agent, calendar_agent)`.
- **History.** S = 6 sessions. Each session belongs to one writer and
  holds 2 to 4 events. `users_v2` fixes S = 6; any other S is a new
  dataset version.
- **Probes.** Six consumer turns after the history, at session 7.
- **Memory scope.** Every session and every probe of a user uses one
  user id, `{name}_{run_id}_t{i}__{method}`, the v1 convention. Memory
  persists across the sessions of a user, which is the point. It is
  reset between users: each user has a fresh id, so no row of one user
  is retrievable under another's (`cross_user_rows` checks this), and
  the agents' in-process state is rebuilt per user. No store is deleted
  (known issue 36).

## Facts

A **fact** is a slot with a value, for example `pet = Mochi`. A fact
belongs to the writer that states it first.

- **Base facts.** The v1 profile and task context, each written once as
  one row, in sessions 1 and 2. The text is v1's `render()` of the
  fields, unchanged, so the base rows equal what v1 stored. No event
  changes a base field, so the user's final profile and task context
  are the base ones, and the integration probe's judge inputs equal
  v1's.
- **Slots.** Each writer has a catalog of slots (`synth_v2.py`). Each
  slot names the roles it can play, its add, update and contradiction
  templates, its revoke and echo templates where it has them, and one
  probe question:

  | Writer | Slots (examples) |
  |---|---|
  | `profile_agent` | home city, team chat app, pet, manager; private: a job interview, a planned move |
  | `task_agent` | client, internal codename, pairing teammate, staging server; private: an acquisition, a confidential pilot customer |
  | `calendar_agent` | team-sync room, conference talk, weekly one-on-one, team offsite city; private: a doctor's appointment |

  A private slot never shares a topic with a shared slot of the same
  writer.
- **Fillers.** Facts that no probe asks about (a CI service, a keyboard
  layout, a book club), so the store holds more than the cap.
- **Values** are drawn from curated pools with a seed. They are proper
  names that a model would not guess or use for another reason:
  people ("Dana Whitfield"), companies, rooms, cities, codenames,
  hosts, conference names. Each value has a short alias list (a
  distinctive surname, "Rocket Chat" for "Rocket.Chat", "Dr. Okafor"
  for "Okafor").
- **Distinctness**, checked by the generator for every user, with
  "matches" meaning the scoring matcher below:
  - no value or alias of one fact matches a value or alias of another
    fact (an echo shares its target's value by design);
  - no value or alias matches the user's name or any token of it, a
    token of 3 or more characters of the base profile or task context,
    a probe question, or the consumer's system prompt;
  - every value is ASCII and at least 3 characters.

  No weekday, date or time is ever a probed value. Mem0's extraction
  rewrites them ("Thursday" became "November 12, 2026" when I tried
  it), so they would not survive in Mem0 cells.

## Events

Each event is one thing the user tells the session's writer. The
utterance is first person ("I live in Tallinn."). It is written from
the slot's template and then paraphrased (see Generation).

| Event | The user says | The writer does |
|---|---|---|
| `add` | a new fact | writes one row with the utterance as content |
| `update` | the fact changed, in change words, without the old value ("We moved the team sync to the Birch room.") | writes a new row; the old row stays |
| `contradict` | the slot's value, flatly, conflicting with an earlier statement by another writer; the later one is true | writes a new row; the old row stays |
| `revoke` | to forget a fact, named by its slot, not its value ("Please forget my pet's name.") | deletes its own rows of that fact; stores nothing |
| `private` | a fact marked as private ("Just between us: ...") | writes one row with `sharing_policy` private |

- **Base events** are `{type: "base", fact_key: "base_profile" or
  "base_task"}`, written like adds.
- **An echo** is an `add` by a writer other than the fact's owner. Its
  value *is* the value of a fact that is later revoked ("I booked a vet
  visit for Mochi."); it carries `echo_of`, the target fact's add. One
  user in three has one: users with i mod 9 in {0, 4, 8}. That spreads
  the deletion writer over all three writers. It tests what a
  writer-scoped deletion leaves behind.
- **Links.** `update`, `contradict`, `revoke` and echo events carry
  `target_event`, the event whose fact they act on.

v2 writers call no LLM. The scripted event already says what to
store, so every locus stores the same text, and differences come from
the locus and the backend only. Writer extraction was v1's concern
(Subtask 9). Mem0 cells still extract, with Mem0's own LLM, as Mem0
does.

**Metadata on every write.**
- The standard fields: `owner_agent`, `user_id`, `memory_type`
  (`profile`, `task_context` or the new `calendar`), `sharing_policy`.
  It is `private` for a private event. Every other event is `shared`
  when the writer's `share_memory` is true and `private` otherwise,
  which is how V1 reaches a v2 writer.
- `fact_key` (the slot), `event_type` and `session` (1 to 6). The
  writer reads `fact_key` to revoke; the formatter reads `session` for
  ages.
- `structured`: the event as a JSON string (`fact_key`, `value`,
  `event_type`), so V5 can write its raw payload.
- Provenance, read by no memory logic: `provenance_agent`,
  `provenance_user` and the new `provenance_event` (the event id).
- Native in-house rows also carry `agent_id` (the writer), as Mem0 rows
  do, so both native backends list a writer's rows the same way.

Updates and contradictions are plain writes with a later session. No
row is updated in place: the store keeps the stale row next to the new
one, and the consumer has to tell them apart. In-place update rules
for extracted facts (known issue 23) are not part of v2.

## Sessions

- Sessions 1, 2 and 3 belong to `profile_agent`, `task_agent` and
  `calendar_agent`. Sessions 4 to 6 are a seeded permutation of the
  three, so each writer has two sessions.
- **Roles and writers.** Role k of user i is owned by writer
  `WRITERS[(i + k) mod 3]`, with k = 0 recall, 1 recency, 2
  contradiction (the original statement), 3 deletion, 4 private. The
  contradicting writer and the echo writer are drawn among the other
  writers. So each writer owns each role for a third of the users.
  Under this rule, the private fact of pilot user 4 belongs to
  `calendar_agent`.
- **Placement.**
  - The base profile is in session 1, the base task context in
    session 2.
  - A fact's first statement is in its owner's first session. Its
    update or revoke is in the owner's second session.
  - A contradiction comes from another writer, in a later session.
  - An echo lies after the add it echoes and before the revoke.
  - A private event is the last event of its writer's second session.
    No later write of that writer can then fold it into a shared fact
    during Mem0's extraction, so a privacy failure is a visibility
    failure.
- **Sizes.** Each session's size is drawn in 2 to 4. Role events are
  placed, then fillers fill the rest. If any rule cannot be met (a
  session over 4, an empty echo window), the user's script is drawn
  again. Each user's attempt *a* uses
  `random.Random(f"{seed}:{i}:{a}")`, and the number of attempts is
  recorded.

Each user has, in all: 2 base events, 1 recall fact, an add and an
update (recency), two statements of one slot (contradiction), an add
and a revoke (deletion), 0 or 1 echo, 1 private fact, and the fillers.
Each role uses a different slot.

## Probes

After the history, the consumer answers six questions, in this order:

| # | Probe | Target | Expected (must appear in the answer) | Forbidden (must appear in neither the block nor the answer) |
|---|---|---|---|---|
| 1 | deletion | the revoked fact | — | the revoked value |
| 2 | privacy | the private fact | — | the private value |
| 3 | recall | the recall fact, written by one writer and asked of the consumer | its value | — |
| 4 | recency | the updated fact | the new value | the old value (in the answer) |
| 5 | contradiction | the contradicted fact | the later value | the earlier value (in the answer) |
| 6 | integration | the v1 `follow_up_query` | judged | — |

- **Order.** The hard constraints come first and integration last. The
  order is fixed and recorded. Since Amendment 3 no probe writes to
  memory: kernel `auto_extract` is off in v2, and the replicated and
  native assistants skip their conversation write on a probe turn. So
  every probe reads what the writers stored, and no block holds a row
  from an earlier probe; each probe still records which of its block's
  rows came from earlier probes, and that list must be empty.
- **Questions** come from the slot's template and are never
  paraphrased. A question never contains an expected or forbidden
  value, or an alias of one. The consumer is v1's: the same system
  prompt in every locus, which asks it to use what it knows about the
  user.
- **One turn each.** Each probe is a fresh consumer turn: a new
  `AssistantAgent` in the kernel locus, whose message list otherwise
  grows, and a fresh message list in the others. Its current session
  is 7.
- **Ground truth is in the script**, never inferred. Each probe records
  its `expected` and `forbidden` values (with aliases), its target
  event, the target's writer and session, and the echo, if any.

## Scoring

Each probe type is reported separately, as a pass rate with n and a
95% Wilson interval. There is no combined score.

- **Matching.** Text is casefolded, accents are stripped, and runs of
  whitespace and the punctuation `-` `_` `.` `/` collapse to one space.
  A value or an alias matches when it appears with a non-alphanumeric
  character, or the text's start or end, on each side. Only this exact
  rule decides a pass. Values are distinctive names so that it
  suffices.
- **Semantic score, a diagnostic.** For each expected value, the
  pinned embedding model (`nomic-embed-text`) gives the best cosine
  between the fact's template sentence and an answer sentence. It is
  recorded, and cases where it is high while the exact rule found
  nothing are counted. It never decides a pass. A sentence-level
  cosine is dominated by the question's own words, so it would pass
  "Your pet is called Max".
- **recall:** pass when the expected value matches in the answer.
- **recency, contradiction:** pass when the new (later) value matches
  in the answer and the old (earlier) value does not. Also recorded:
  - `expected_present` and `stale_present` apart;
  - whether the stale value sits in a sentence with a change marker
    ("from ... to", "previously", "no longer", "instead of"), as in
    "moved from Juniper to Birch".

  So the strict rule's failures can be split into stale-asserted and
  named-as-past. The lenient rate (`expected_present` alone) is
  reported next to the strict one.
- **deletion, privacy:** hard constraints. The probe fails when the
  value or an alias appears in the consumer's block or in its answer.
  `forbidden_in_block` and `forbidden_in_answer` are recorded apart.
  The block is what the memory system served, so a leak counts even
  when the model does not repeat it.
- **integration:** judge v2 (`HybridJudge`, prompt v2, greedy), with
  the user's final profile and task context, which equal the base
  ones. The integration score is reported as its mean with a 95% CI and
  as the share of scores of 4 or more. The judge's other two scores are
  kept and not reported. The score is a new measure, taken after five
  earlier probes with recency on and a binding cap, so it is not
  comparable with pilot_v1's integration.

**Diagnostics per probe**, also judge-free:
- the consumer's `InjectionDiagnostics`, including the stage counts,
  `after_cap`, `after_budget`, `tokens_estimated` and `barrier_waits`;
- the block, and each injected row with its text, owner, memory type,
  `fact_key`, `session` and `provenance_event`;
- whether the expected, stale and forbidden values reached the block,
  and which rows carried each. A row is classified by its
  `provenance_event`: the target's own write, an echo, another fact,
  or the assistant's conversation (owner `assistant_agent`, type
  `conversation`). That last class also covers rows written by an
  earlier probe;
- whether the newest row of the target's fact carries the old value
  (Mem0's extraction does this, below);
- `cap_bound` and `budget_bound`:
  - kernel and replicated: `after_cap < after_threshold` and
    `after_budget < after_cap`;
  - native: `cap_bound` means the fetch filled k while the user's
    visible stored rows (from the listings) exceed k. Native has no
    budget, so `budget_bound` is not applicable;
- the answer's length, and how many of the user's other scripted values
  it names.

A failure is then attributable: the target was not stored, was dropped
by selection, reached the block but not the answer, or the forbidden
value came from a row that a writer-scoped deletion does not remove.

## Recency

The formatter's recency mode is on by default for v2. Each bullet ends
with its age in sessions: "(this session)", "(1 session ago)", "(N
sessions ago)". The age is the current session minus the row's
`metadata.session`. A row gets no age when it has no session, or when
its session is after the current one. At the probes (session 7), a
session-6 row reads "1 session ago" and a session-1 row "6 sessions
ago". (Before Amendment 3 the assistant's earlier probes read "this
session".)

- **Config.** A new key, `memory.block_recency_unit`: `time` (the
  existing wall-clock ages, the default) or `session`. v2 runs set
  `memory.block_recency: true` and the unit `session`.
  `scripts/set_memory_mode.py --recency session` sets both.
- **Kernel, every hop:**
  1. The probe's chat request carries the current session
     (`LLMQuery.session`, a new optional field).
  2. `/query` rebuilds the query, so it copies the session onto it, as
     it does the user id.
  3. The executor passes it to `ContextInjector.inject` and on to
     `MemoryPipeline.inject`, `build_block` and the formatter.
  4. The executor also passes it to the conversation write, which
     stamps it on the stored turn. Since Amendment 3, v2 kernel runs
     store no turn (`auto_extract` off); the stamping is unchanged.
- **Replicated.** Same library, same rendering. The assistant passes
  the session to `MemoryPipeline.inject` and stamps its conversation
  note.
- **Native.** The native assistant reads `block_recency` and
  `block_recency_unit` from `/memory/config` `pipeline`, as replicated
  does. It renders the same suffix from the row's `metadata.session`
  and stamps its own conversation row. Without this, the recency and
  contradiction probes would compare renderers, not memory. It is a
  decision of this spec, not a property of the backends.
- **Checked per probe.** Every locus reports `session` and
  `block_recency_unit` in its diagnostics. In a v2 run, a probe whose
  diagnostics do not show session 7 with unit `session` fails the user.
  A probe with an empty block is exempt: the library reports no session
  for it, and no row in it carries an age.

## Revoke and deletion

A revoke is handled by the writer that owns the fact:
1. It lists its own rows for the user.
2. It deletes every row whose `metadata.fact_key` is the revoked slot.
   Mem0 copies a write's metadata onto every fact it extracts, so this
   also finds a write's sibling facts.
3. It records the ids it found and the ids it deleted.

How each locus lists and deletes:
- **Kernel:** a new owner-only list operation (`list_memory`, SDK
  `list_memories`) and the existing `remove_memory` (SDK
  `delete_memory` with `user_id`), which deletes through the provider
  contract's `delete`. Both go through a new `MemoryPipeline.list_own`
  and `MemoryPipeline.delete`, so kernel and replicated run the same
  code.
- **Replicated:** the same library methods, in-process.
- **Native:** the backend's documented calls. Mem0 uses
  `get_all(filters={user_id, agent_id}, top_k=10000)` and then
  `delete(memory_id)`. In-house Chroma uses `get(where={user_id,
  agent_id})` and then `delete(ids=...)`.

**Listings reach every row.** A listing asks for 10,000 rows. The
provider's `list` cuts before the owner filter, and Mem0's `get_all`
returns 20 rows unless told otherwise, so a smaller limit could hide
a writer's own rows. A listing that returns exactly the limit fails the
user.

This deletion is not complete, and Subtask 15 makes it complete. What
it leaves behind is recorded, not hidden:
- copies in other writers' rows (the echo), which a writer cannot
  delete (owner-only);
- facts Mem0 extracts again from its history of recent messages,
  which a delete does not purge;
- the assistant's own conversation rows, if one ever quoted the fact.
  Since Amendment 3, v2 probes store none.

**Recorded per user.** The harness lists the rows of all four agents
(each through the owner-only list) after every session and after the
probes. From these it records:
- each event's stored rows and ids, matched by `provenance_event`.
  This covers Mem0's sibling facts, since the kernel's Mem0 `add`
  returns only the first id;
- the ids each revoke deleted, and any deleted id that reappears in a
  later listing or among a probe's injected rows;
- `revoked_value_rows`: every row, of any agent, that carries a revoked
  value after its revoke, labelled by owner and `provenance_event`.

## Loci and backends

All six cells run v2: `kernel_shared` on Mem0 and on in-house,
`replicated_mem0`, `replicated_inhouse`, `native_mem0` and
`native_inhouse`. Each locus keeps its v1 definition
(REPLICATED_LOGIC.md, NATIVE_USAGE.md), with these v2 additions:
- the writers' event handling above, the same in all three;
- `calendar_agent` in all three loci;
- deletion through each locus's own route;
- session ages in all three blocks.

By-design differences that the probes will show, stated before any
run:
- **Kernel and replicated** fetch own k plus shared 4k rows, then cap
  at k = 10 by score, then fit the 300-token budget (Amendments 1 and
  3).
- **Native** fetches k rows from the backend and applies visibility
  afterwards, so other agents' private rows take slots (and, before
  Amendment 3, the assistant's own conversations). It has no budget.
  Native Mem0 ranks by Mem0's own `search()` score, which as
  installed is the squared L2 distance alone (Chroma has no keyword
  search, and without the `[nlp]` extra there is no entity boost),
  clamped at 1.0. Every row at cosine 0.5 or below ties at 1.0 in
  Chroma's nearest-first order, and the rows above 0.5 follow from the
  least similar up, so they are cut whenever k rows lie at 0.5 or
  below (NATIVE_USAGE.md, "Scores" and "Evidence").
- **Mem0 cells store extracted facts**, in-house cells the utterances
  verbatim. How many facts a one-value utterance becomes is not yet
  measured; the functional check measures it.
- **Mem0 update rows usually carry the old value.** The update's
  extraction sees the writer's earlier rows and messages, and Mem0's
  prompt asks a transition to say what it replaces. So recency's
  "names both" failures should be more common in Mem0 cells.
  Contradictions come from another writer, whose Mem0 scope is
  different, so contradiction is not affected.
- **The budget** binds through long rows: since Amendment 3, the base
  rows (v1's renderings) in the integration probe's block. Ten
  one-sentence writer rows come to about 250 estimated tokens.

**Heterogeneity.** The variants apply unchanged, through the same
channels, to `profile_agent`, `task_agent` and `assistant_agent`.
- Kernel writers, `calendar_agent` included, make every create through
  their own module's `create_memory`, with keyword `content=` and
  `metadata=`, which is where V3 and V5 and the harness's write
  capture reach them. Each locus has a test that V1, V3 and V5 change
  a v2 write.
- `calendar_agent` never deviates. The catalog keeps two writers,
  because adding a third would reshuffle every seeded schedule and the
  pilot's.
- V5 writes the event's `structured` JSON as its raw payload.
- V3 drops `owner_agent` and `sharing_policy` from the request:
  - kernel and replicated: the library fills in the writer as owner and
    private as the policy, so V3 rows are private, invisible to the
    consumer, and deletable by their writer;
  - native: Mem0 rows keep `agent_id` and in-house rows keep their
    `agent_id` key, so the writer still lists and deletes them. The
    rows have no policy, which the native visibility rule reads as
    private.
- A scored v2 run at H > 0 needs a v2 schedule. Writing one is not part
  of this subtask.

## Generation

`benchmarks/shared_memory/synth_v2.py` writes
`benchmarks/shared_memory/data/users_v2.jsonl`.

- **Script.** For user *i*, attempt *a* draws from
  `random.Random(f"{seed}:{i}:{a}")`, with seed 20261108. It draws the
  role slots, the contradicting and echo writers, values and aliases,
  session order and sizes, and fillers, and places them by the rules
  above. The same seed always gives the same script.
- **Paraphrase.** GPT-4o paraphrases each add, update, contradict,
  private, revoke and echo utterance, and nothing else. The call is
  `azure/gpt-4o` at temperature 0.0, with seed `seed + 10^6 × attempt +
  10^3 × i + e`, where e is the event's position in the user's script.
  - It is told: keep the given values verbatim, add no fact, use first
    person, write one or two sentences, and keep the private marker or
    the request to forget.
  - A paraphrase is kept only if it is at most 40 words, contains its
    own value (an echo's own value is its target's), and contains no
    value or alias of any other fact of the user. An update's or a
    contradiction's old value is one such other value.
  - Otherwise it retries 3 times, then falls back to the template text.
    The fallback is recorded.
- **Not paraphrased:** the base rows (v1's `render()`) and the probe
  questions.
- **Frozen.** The paraphrases are stored in the file, so a run never
  calls the generator's LLM. Azure's seed is best effort (known issue
  24), so the committed file, not a regeneration, is the dataset.
  Never edit it by hand; make a new version.

**File.** The first line is a header:
- `{type: "header", dataset: "users_v2", format_version: 2, users: 150, seed, model, sessions: 6}`;
- `writers`, `consumer`, `probes` (the six types in order);
- `base: {dataset: "users_v1", sha256}`;
- `paraphrase: {model, temperature, seed_rule}`;
- `generator`, `generator_sha256` (of `synth_v2.py`, catalog included);
- `harness_commit`, `litellm_version`, `date`;
- `pilot: {pilot_v2: 30}`.

Each user record:
- `type: "user"`, `index`;
- `base`: profile, task context, `follow_up_query`,
  `plausible_actions`;
- `final`: profile and task context after the history (equal to
  `base` in v2);
- `sessions`: each `{session, writer, events}`. An event is
  `{event_id, type, slot, fact_key, value, aliases, old_value,
  target_event, echo_of, sharing, template, utterance, paraphrased}`.
- `probes`: each `{probe_id, type, slot, question, fact_sentence,
  expected, forbidden, target_event, target_writer, target_session,
  source_events, echo_event}`. `expected` and `forbidden` are lists of
  `{value, aliases}`.
- `generation`: script attempts, paraphrase attempts and fallbacks.

`dataset.py` resolves `users_v2` (all 150) and `pilot_v2` (the first 30
of the same file). The per-trial `input_sha256` of a v2 user hashes its
whole script: sessions, events, utterances and probes.

## Harness

`run_evaluation.py --dataset users_v2|pilot_v2 --method M` runs one
trial per user, trial *i* = user *i*, as v1 does. For each user:
1. **Sessions, in order.** Each is one writer turn through the trial's
   locus: the writer gets the session's events in order and makes the
   writes and deletes they imply. Every write carries the session's
   index. Variants apply as in v1. After each session, the four agents'
   rows are listed.
2. **Probes, in order,** as consumer turns at session 7.
   - The judge-free probes are scored as above.
   - The integration probe is judged, unless `--no-judge`.
3. **Listings again**, then the reappearance check.

**Pre-flight.** The harness refuses a v2 run unless the kernel's
`/memory/config` reports:
- recency on with unit `session` (or off, with `--no-recency` for an
  ablation);
- `max_injected_memories` 10, `max_memory_tokens` 300 (Amendment 3),
  `relevance_threshold` 0.0 and `block_format` compact;
- `write_barrier.timeout_ms` of at least 60,000 for a kernel method
  (see below);
- for a kernel method, `auto_inject` on and `auto_extract` off
  (Amendment 3; before it, both on).

Each value is recorded with the results.

**TrialResult additions** (all defaulted, so v1 files still load):
- `user_id`;
- `sessions[]`: per session the writer, its events with the rows and
  ids each stored or deleted, the listings' counts, and any error;
- `probe_results[]`: per probe:
  - the type, question, `expected` and `forbidden`, and the observed
    answer;
  - `passed` (None for integration) and the match fields;
  - the block checks, `cap_bound` and `budget_bound`;
  - the consumer's diagnostics, the judge scores (integration only),
    tokens and latency, and any error;
- `deleted_memory_ids`, `reappeared_memory_ids` and
  `revoked_value_rows`.

Three v1 summary fields stay unset in v2: `writer_stored_rows` is `{}`
(each writer's stored rows are in `sessions[]`, from the listings),
every field of `latency_breakdown` is null (each probe keeps its own
latency), and `retrieval_log` is null (the integration probe's
diagnostics are mirrored as `injection_diagnostics`). The v1 tools that
read `retrieval_log` do not apply to v2: `assert_injection_rate.py`
reports a missing log for every trial, and `--csv` writes 0 and False
in `shared_memory_count` and `cross_agent_found`. `memory_counts`
counts creates, one per write event, not stored rows.

For the tools that read v1 fields, the integration probe is mirrored
into the top level:
- `follow_up_query`, `assistant_response`, `injection_diagnostics` and
  `judge_free` over its block;
- `synthetic_profile` and `synthetic_task_context` (the final state);
- all three judge scores.

**Failures.** Each of these fails the user:
- **A writer error:** any create, list or delete reply that is null,
  has `success` false or says "Memory not found", and any exception. A
  v2 writer never catches and continues.
- **A consumer error:** a probe reply that raised, carried an error,
  or was empty or an "Error:" text. Such a probe is never scored, so an
  error cannot pass a hard constraint.
- **A listing** that returned its limit, or a probe whose diagnostics
  do not show session 7 in a v2 run (a probe with an empty block is
  exempt; see "Recency").
- **A judge failure** after retries.
- **A v2 extraction failure.** With backend extraction, every write
  event must store at least one row, counted from the listings by
  `provenance_event`, and a cell that wrote must record backend LLM
  calls. This replaces v1's "every writer creates", which a revoke
  would break.

A cell with a failed user is re-run whole under a new run id (known
issue 36).

**Cost.** Token and backend usage are summed over sessions and probes.
The kernel's `/memory/cost` is read once per user, after the last
probe.

## Before any v2 run

- **Ollama `num_ctx`** (known issue 29). The adapter set no context
  size, and Ollama 0.40.11 cut a long prompt from its start without an
  error, which is where the memory block is. The kernel now passes
  `llms.context_window` (default 16384) to every Ollama call, and the
  reply's `decoding` records it.
- **Kernel list and delete paths.**
  - `execute_request` dispatches `list_memory`, and an unknown memory
    operation returns an explicit failure, never HTTP 200 `null`.
  - Every new or changed memory branch catches every exception and
    returns `success` false. An uncaught exception there leaves the
    syscall waiting forever and blocks the server.
  - Tests go through `execute_request`, and one through `/query`.
- **Session ages** in the library, the kernel and the native renderer,
  with the hops above.
- **Per-row diagnostics.** The injected-row entries carry the row's
  text, `fact_key`, `session` and `provenance_event` in every locus.
  `InjectionDiagnostics` keeps them and `barrier_waits`.
- **Write barrier.** The kernel writes a probe's conversation in the
  background, behind the write barrier. In the pilot, 3 of 90 kernel
  Mem0 conversation writes took longer than the barrier's 5 s timeout,
  so the next probe would have run without them, while replicated
  writes synchronously. v2 kernel runs set
  `memory.write_barrier.timeout_ms` to 60,000, and every probe records
  its barrier waits.
- Any edit to `aios/memory/pipeline/` changes `PIPELINE_VERSION`. Every
  kernel and replicated v2 trial records it. Native trials, which do
  not run the library, record None; their file records the kernel's
  version in `run_settings`.

## Functional check and smoke

**Functional check.** `pilot_v2` users 0 to 4, Qwen, no judge, all six
cells. Without the judge, the integration probe has no score, so the
check reads the five judge-free probes. It runs these conditions:
- **H = 0**, the reference.
- **H = 2**, the seeded cycle. It gives users 0 to 4 a V2, V4, V5 and
  V3 consumer and six writer variants. Its V3 consumer (user 4)
  ignores visibility in native, and user 4's private fact belongs to
  `calendar_agent`, which is not a variant there. So H = 2 is where a
  real locus can fail privacy.
- **Three negative controls at H = 0**, which show that each probe can
  fail when the property it tests is removed:
  - `no_memory`: the sessions are skipped, so the probes run on an
    empty store. This is the guessing floor: recall, recency and
    contradiction should fail, and deletion and privacy should pass.
  - `no_delete`: writers find the rows a revoke names but delete
    nothing. Deletion should then fail wherever the target is
    retrievable. Run in all six cells, this also measures each cell's
    chance to show the value at all.
  - `no_visibility`: the native consumer ignores visibility. Privacy
    should fail. This is native only, because the kernel and the
    library enforce visibility themselves.

DEV_STATUS gets the per-probe pass matrix (locus × backend × condition
× probe type), with deletion split into echo and non-echo users. The
check passes when:
- every judge-free probe type passes and fails somewhere among the real
  conditions (H = 0 and H = 2), and each fails in its control;
- deletion passes among non-echo users in the in-house cells, which
  shows the delete path works, and fails under `no_delete`;
- the kernel's privacy probe never fails, on the block or the answer;
- the cap binds in some probes of every kernel and replicated cell, and
  the budget binds in some probe of a kernel or replicated in-house
  cell. If the budget never binds, the check fails, and the design
  changes before the smoke.

**Smoke.** `pilot_v2`, all 30 users, Qwen, H = 0, all six cells, with
judge v2 on the integration probe only. Results:
- per-probe pass rates per cell, with n and a 95% Wilson interval;
- the lenient recency and contradiction rates;
- the integration mean with its 95% CI and the share of scores of 4 or
  more;
- how often the cap and the budget bound, per probe and cell;
- kernel against replicated per probe type, paired over users (exact
  McNemar). On in-house at H = 0, the two run one library on the same
  inputs, so their blocks should be identical; the share of identical
  blocks is reported.

A smoke, not a verdict: no rule is pre-registered here.

## Pre-stated expectations

These are expectations, not a rule.
- **H = 0:** kernel and replicated tie, as they run one library. Native
  differs by its fetch-then-filter and, on Mem0, by its scores.
- **Recall** fails mostly when the cap drops the target, more often for
  targets written early, and most for native Mem0.
- **Recency and contradiction** fail when the stale row ranks above the
  new one and the consumer follows it, or when it names both. v1's
  consumer restates what it knows, so naming both will be common; the
  lenient rate shows how common.
- **Deletion** fails for echo users in every locus, through the echo's
  row. It may fail on Mem0 when its history brings the fact back.
  Without an echo, in-house cells should pass.
- **Privacy:** the kernel never fails. Replicated enforces visibility
  in the library, so it should not fail either. Native fails with its
  V3 consumer (H = 2, user 4) and under `no_visibility`.
- **The budget** binds, if ever, in late probes of in-house cells, once
  long conversation rows rank in the top 10. (Since Amendment 3: in the
  integration probe of in-house cells, through the base rows.)

## What v2 does not show

- Writers are scripted, not LLM agents. Extraction quality is v1's and
  Mem0's own.
- Deletion is writer-scoped (Subtask 15 completes it).
- Private facts are written last, so Mem0 never gets the chance to
  fold one into a shared fact. Whether it would is a separate question.
- No concurrent writers: sessions run one at a time.
- Four probed slots and one private fact per user, over 150 users
  built on `users_v1`, whose profiles are skewed (known issue 22).
- No scored heterogeneity in this subtask.

## Amendment 1 (2026-11-08, before the functional check)

**The budget is 500 tokens, not 2,000.** One `pilot_v2` user (user 0,
Qwen, H = 0, no judge) was run through all six cells to test the
harness end to end. The cap bound in every probe of every cell
(after_threshold 17 to 32 against k = 10). The blocks came to 180 to
980 estimated tokens, so a 2,000-token budget could never bind: v2's
rows are one sentence each, where v1's were whole renderings.

The task says the cap and the budget bind. This spec's functional check
requires the budget to bind and says the design changes before the
smoke if it does not. So every v2 run sets `memory.max_memory_tokens`
to 500, through `scripts/set_memory_mode.py --budget 500`, and the
pre-flight checks it.
- On that user, 500 binds in the later probes of the in-house kernel and
  replicated cells, whose blocks hold the long conversation rows (543,
  534 and 726 tokens), and never in the Mem0 cells (at most 379).
- k stays 10 (`--k 10`, set explicitly, since `config.yaml.example`
  has 5; known issue 3). Native has no budget, by design.
- The v1 runs keep 2,000; v2's numbers are not comparable with v1's on
  this account either.


## Amendment 2 (2026-11-08, after the functional check, before the smoke)

**Why.** A read-only review of this subtask's code and data ran while
the first smoke started. It found facts whose paraphrase changed what
they say, and incomplete harness records. The smoke was stopped in its
first cell, and nothing from it is reported. `users_v2` is regenerated
as revision 2 (the file keeps its name). The functional check and the
smoke run again on it, with the changes below.

**Revision 1's data problems** (SHA-256 `768a37ac…`, now superseded):
- **Contradictions that do not conflict.** Some contradicting
  statements were paraphrased as additions, so the user could hold
  both values and naming both was not wrong:
  - conference talks, 10 of 10 ("I'm giving a presentation at
    Fjordstack.");
  - weekly one-on-ones, 16 of 19;
  - client, 12 of 26 ("The company I'm working with on my project
    is …", which no longer says client).
  - Pilot users 0, 3, 9, 12, 14, 18, 27 and 29 had a contradiction that
    did not conflict (14 and 29: client).
- **Lost topics.** Paraphrases dropped what the fact is about:
  - every teammate add said "collaborating" (59 of 59), and every
    teammate revoke said "teaming up" (25 of 25), not "pairing";
  - 9 of 31 lawyer rows dropped "lawyer", pilot user 4's included.
- **A shared fact marked private.** 21 of 35 codename adds began
  "Privately, …".

**Generation.** Every paraphrase is now also checked for its meaning:
- **Topic.** Each utterance of a probed or private slot names the
  slot's topic, from a short word list per slot (for example pairing,
  client, lawyer). Fillers and echoes are exempt.
- **Conflict.** A contradiction states what makes it conflict:
  - the conference, one-on-one and pairing templates say "only" ("The
    only conference I'm presenting at is …"), and their paraphrases
    must keep it;
  - a client contradiction must say client;
  - home city, manager and offsite city hold one value by nature.
- **Event cues.** An update keeps a word saying the fact changed, a
  revoke keeps its request to forget, and a private fact keeps its
  private marker.
- **No false privacy.** No shared fact of a probed slot, and no echo,
  carries a private marker.
- **Prompt.** The paraphrase prompt asks for all of the above.

**How revision 2 is built.**
- It keeps every revision-1 utterance that passes the new checks, byte
  for byte.
- Each one that fails is paraphrased again under the same seed rule.
  The rejected utterance counts as the first attempt, and the reason it
  was rejected is the retry's feedback.
- The three changed templates are paraphrased from the first attempt.
- The scripts (slots, values, sessions) are unchanged.
- The header records the revision and revision 1's SHA-256.

**Scoring.**
- **`transition_marked`.** The stale value is named as past when every
  sentence that names it holds a change marker:
  - "previously", "no longer", "instead of", "used to", "formerly",
    "originally", a form of "replace", or "anymore";
  - or "from" right before the stale value, optionally after one
    determiner ("moved from the Juniper room").
  - The expected value need not be in the same sentence. Revision 1
    of the scorer required that, and counted any "from".
- **Native `cap_bound`** compares the fetch with the consumer's own k
  (a V4 consumer fetches 5), not the harness's 10.
- **The semantic diagnostic** records an embedding failure
  (`semantic_error`) instead of stopping the run. It still decides no
  pass.
- **The integration mean** is reported with its 95% t-interval (none
  for n < 2).

**Harness.**
- **Failed retrievals.** A consumer probe whose retrieval failed (the
  own or the shared fetch) fails the user. The library reports
  `retrieval_error` in its diagnostics instead of dropping it, and the
  kernel's injector reports `injection_error`. Before, a failed fetch
  looked like an empty store, so deletion and privacy passed.
- **Errored probes.** A probe with an error is recorded unscored
  (`passed` None), so an error cannot pass a hard constraint, even in
  a failed trial's record.
- **Any exception** in the history fails the user and keeps what ran,
  not only the harness's own failures.
- **Rows per event.** Each event's stored rows and ids come from the
  listing after its session, by `provenance_event` (see "Recorded per
  user"). The writer's reply ids are kept as `reported_ids`. Before,
  the kernel and replicated Mem0 cells recorded only the first fact.
- **Backend usage** of agent-managed loci includes calls tagged with
  every user id the trial used, a V2 variant's included.
- **Stored metadata.** Replicated writers record the metadata as it was
  stored, so a V3 row is recorded as private.

**Kernel.**
- **Listings wait for writes.** `list_memory` waits on the write barrier
  like a retrieval. Before, every kernel user's listing after the last
  probe missed that probe's conversation, and `revoked_value_rows`
  missed it too.
- **Provenance of conversation rows.** The kernel's conversation rows
  carry `provenance_event`. `LLMQuery.provenance_event` (new, optional)
  is sent by the kernel assistant with the probe id and stamped on the
  stored turn, as the replicated and native assistants do. This closes
  known issue 40.
- **Unknown operations.** `execute_request` returns an explicit failure
  for a memory operation it does not dispatch, as "Before any v2 run"
  requires.

**Settled during implementation** (each with a test):
- **Unscored probes.** A probe whose block fails the session-7 check is
  recorded unscored too, with that problem as its error, like a
  consumer error.
- **Rows that were never listed.** A write event's `memory_ids` and
  `stored_rows`, and its session's `stored_rows`, are None when no
  listing followed: the writer failed, or the listing raised. A writer
  that raised records its session with the error and no events, and the
  session's `stored_rows` None. They are `[]` and 0 when the listing
  ran and held no row of the event, which is the Mem0 "stored nothing"
  case.
- **Reuse is checked.** `--reuse` accepts only a whole version 2 file
  with at least the users to build, drawn with the run's seed and
  paraphrased by its model. A limited name such as `pilot_v2` names
  part of a file, so it is refused too.
- **Recorded writes.** A create the kernel refused is not recorded as
  written, as in the agent-managed loci.

**Corrected after the revision-2 functional check** (2026-11-09, before
the smoke). A read-only review of the check's records found these. None
changes a design decision or a score:
- **Pilot users.** The list of pilot users whose revision-1
  contradiction did not conflict now has 14 and 29, whose client
  contradictions read "The company I'm working with on my project is …".
- **Native Mem0's order** ("Loci and backends"). The clamped score
  puts the rows at cosine 0.5 or below first, nearest first, not the
  least similar first. The relevant rows are cut all the same.
- **Empty blocks** are exempt from the session check ("Recency",
  "Harness"), as the harness already had them: no row in them carries
  an age.
- **`PIPELINE_VERSION`** is recorded by kernel and replicated trials;
  native trials record None ("Before any v2 run").
- **Unset v1 fields** are named ("Harness"), and a writer that raised
  records no events ("Rows that were never listed").
- **`visible_stored_rows`** (native `cap_bound`, "Scoring") counted the
  writers' shared rows under the base user id for every consumer. It
  now counts the writers' rows in the partition the consumer searched,
  the private ones too when it skips visibility (V3, `no_visibility`),
  which the native consumer reports as `visibility_checked`. In the
  check this changed no `cap_bound` (0 of 240 native probes), and a
  reference consumer's count is unchanged.


## Amendment 3 (2026-11-09, after the smoke, before Subtask 15's deletion work)

**Why.** The smoke (`s14b`, revision 2) showed two problems.
- **The probes' stored answers.** Each probe's answer was stored, and
  later probes read it (known issue 45).
  - In 19 of the smoke's 900 judge-free probes, a value reached the
    block only through the consumer's own earlier answers. Every such
    probe is a recall, recency or contradiction probe. The revision-2
    functional check (`f14c`) had 12 of its 525, and the revision-1
    check (`f14b`) 9 of 525.
  - The stored answers also displaced the base rows from the in-house
    kernel and replicated integration blocks under the budget. That
    effect differs by backend (verbatim or extracted rows) and by locus
    (a budget or none). (Open decision 2, option (b).)
- **The contradiction questions' wording.** In revision 2, every
  question of a slot shared its content words with the same one of the
  two statements, so the smoke could not tell the wording from the slot
  (known issue 44; open decision 3, option (a)).

**Probes write nothing to memory.**
- **Kernel.** v2 kernel runs set `memory.auto_extract: false`, with
  `auto_inject` still on. In v2 every consumer turn is a probe, so no
  probe answer is stored. The pre-flight refuses a v2 kernel run with
  `auto_extract` on, and `scripts/set_memory_mode.py --extract off`
  sets it apart from injection.
- **Replicated and native.** The assistant skips its conversation
  write on a probe turn: the harness sets the consumer's
  `store_conversation` to false for its probe turns. A v1 turn still
  stores its conversation.
- **Checked.** The harness lists every agent's rows after the last
  session and again after the probes. A probe turn that stored a row
  fails the user ("probe turns stored N rows").
- **So:**
  - no row in a block comes from a probe, and `contaminated` is 0 by
    construction;
  - the probe order no longer changes what a block holds, but it stays
    fixed;
  - memory accumulates over the sessions only.

**The budget is 300 tokens.** Without stored answers, 500 cannot bind:
in revision 2, no `users_v2` kernel or replicated in-house block can
exceed 336 estimated tokens at H = 0. On a copy of the smoke's kernel
in-house store (revision 2), blocks of writer rows only reach 314
tokens in the integration probe and 299 elsewhere. 300 binds in 6 of those 180 probes, all
integration probes, and keeps the base rows as no budget does.
- v2 runs set `memory.max_memory_tokens` to 300
  (`set_memory_mode.py --budget 300`), and the pre-flight checks it.
- Native has no budget, as before.
- The functional check's budget criterion stands: if 300 never binds
  there, the design changes before the smoke.

**Revision 3 of `users_v2`: contradiction questions of balanced lean.**
- **Two questions per slot.** Each contradiction slot has two
  questions. One leans to the earlier statement (the owner's add), the
  other to the later one (the contradiction).
- **Half of each.**
  - A slot's contradiction users alternate between the two questions,
    in index order.
  - The contradiction slots, in catalog order, alternate the lean of
    their first user's question.
  - So `users_v2` has 75 questions of each lean, `pilot_v2` 15, and
    every slot is within one of half, in both.
  - The probe records its `lean` (`earlier` or `later`; the other
    probes record none).
- **The word rule.** A question's content words are its words without
  a fixed list of function words: articles, pronouns, auxiliaries,
  prepositions, conjunctions, wh-words, a few particles, and the
  letters a contraction leaves.
  - A content word counts for a statement that has it under two rules:
    as written, and by its word family, a fixed table (`report`,
    `reports`, `reported`, `reporting`) rather than a stemmer.
  - A question leans to the statement that has more of its content
    words, under both rules. If the rules disagree, or it is a tie,
    it has no lean.
- **Templates and questions** (four templates change, marked *):

  | Slot | Earlier statement | Later statement | Leans earlier | Leans later |
  |---|---|---|---|---|
  | home_city | I live in {value}. | I'm based in {value}. | Which city do I live in? | Which city am I based in? |
  | manager | I report to {value}. | My manager is {value}. | Who do I report to? | Who is my manager? |
  | client | We're building this project for {value}. | The client for my project is {value}. | Who am I building this project for? | Who is the client for my current project? |
  | teammate | I pair with {value} on this project every day.* | My only pairing partner on this project is {value}. | Who do I pair with every day? | Who is my pairing partner on this project? |
  | conference | I'm presenting at {value} next month. | The only conference I'm presenting at is {value}. | Where am I presenting next month? | Which conference am I presenting at? |
  | one_on_one | I meet with {value} one-on-one every week.* | My only standing one-on-one is with {value}.* | Who do I meet with every week? | Who is my standing one-on-one with? |
  | offsite_city | The team offsite is in {value}. | This year's offsite will be held in {value}.* | Where is the team offsite? | Where will the offsite be held? |

  A changed earlier statement is used only by the contradiction role
  (`contradiction_add`). The recall, recency and deletion facts of the
  same slot keep the slot's add and question.
- **Paraphrases keep the lean.** A contradiction statement's paraphrase
  must have exactly the question words its template has, as written and
  by family. So each question leans as it does on its template pair,
  which the generator checks for every value of the slot's pool. The
  paraphrase request names the words to keep and the words not to use.
  The other checks (Amendment 2) apply as before.
- **How revision 3 is built.** As revision 2 was:
  - `--reuse` on revision 2; the scripts (slots, values, sessions) are
    unchanged;
  - each utterance that passes every check is kept byte for byte;
  - one that fails is paraphrased again, from attempt 1 with its
    problems as feedback;
  - an event whose template changed is paraphrased from attempt 0.

  The header records revision 3, the generator's commit
  (`harness_commit`), the seed and the model, and revision 2's SHA-256
  under `reuse`. Revision 2 is kept in
  `repo-artifacts/Cerebrum/users_v2_revisions/`.

**Not changed.** The scoring rules, the five other probes, the
controls and the functional check's criteria. Since no block holds a
probe answer, the check also confirms that no probe is contaminated.

**Settled during implementation** (each with a test):
- **Meaning rules for the two statements.** Revision 3's first build
  (Cerebrum `4ac61fe`, SHA-256 `e019ece9…`, not kept) passed every
  check. A read of its new paraphrases found statements that kept their
  words but lost what they said:
  - "My work is based in X": a workplace does not conflict with a home;
  - "We are building a project for X", in 16 of 26 client earlier
    statements: not the current project;
  - "We're creating this building project for X";
  - "I am under X's report".

  So a contradiction statement also keeps its slot's meaning rules:
  - no workplace word in a home_city statement;
  - a client statement names the current project, and "building" is a
    verb there;
  - the manager's earlier statement keeps "report to".
- **The build.** Cerebrum `af078c3` (generator `5b5f0de`), SHA-256
  `ecd3585f…`:
  - 2,252 utterances reused byte for byte, 131 paraphrased again, and
    83 paraphrased from changed templates;
  - 344 GPT-4o calls, and 22 fallbacks to the template text (21 client
    earlier statements, 1 home_city contradiction);
  - only the contradictions' statements changed (214).

  User 73's earlier manager statement reads "I am under Callum Reyes
  and report to him.", the file's only third-person pronoun.
- **Cross-checks.**
  - Both lean questions of every user lean as designed under Porter
    and Snowball stemming of the content words too (300 of 300 each).
  - Counting every word, function words included, 141 of the 150 asked
    questions lean as assigned, and 9 later-leaning ones tie.
- **The driver** also fails a kernel phase whose log shows a stored
  conversation turn.
