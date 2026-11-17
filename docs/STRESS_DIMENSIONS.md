# Stress dimensions: agent count, concurrency, a faulty agent

NeurIPS Subtask 18. This spec was committed before the code. It
defines three stress dimensions beyond heterogeneity
(`HETEROGENEITY.md`), the kernel and library additions they need, and
what the design predicts each locus does at each level. Every
measurement it names is judge-free. No scored trial runs under these
dimensions in this subtask: the scored runs wait for the full grid
(`FULL_GRID.md`).

## Why these dimensions

Heterogeneity asks what happens when agents are built differently. For
some of its variants the kernel's advantage is close to definitional:
the kernel ignores a consumer's own retrieval settings (V4), so of
course it is immune to them. The dimensions here are different. Each
asks whether a property holds that only a layer seeing every writer
can provide:

- **Agent count.** Does anything change as the same facts are written
  by more agents?
- **Concurrency.** A shared write barrier makes a read wait for every
  write accepted before it. A barrier of one agent's own covers only
  that agent's writes.
- **A faulty agent.** The kernel can bind a request to the session's
  user instead of trusting the agent's claim, and can bound how many
  rows one writer stores. An agent cannot enforce either on itself if
  it is the faulty one.

## Common ground

- **Benchmark v2 only.** Every condition runs `pilot_v2` (users 0 to 29
  of `users_v2`) or an agent-count version of it (below). The probes,
  their scoring and the failure rules are `BENCHMARK_V2.md`'s, as
  amended.
- **Paired.** Every schedule here is a pure function of a seed, the
  dimension's level, the agent count and the trial index: which agents
  deviate, which agent is faulty, whose id a wrong-user writer uses. It
  never depends on the locus, backend, model or run, so user i meets
  the same condition in every cell.
- **Predictions** compare a trial with the same user's reference trial
  in the same cell type: the same locus and backend at the dimension's
  base level (N's H = 0 trial, the sequential trial, the trial without
  a fault).
- **Not crossed in this subtask.** Concurrency and the load mode run at
  H = 0 without a fault: a variant patches an agent module's functions
  while it runs, which concurrent runs of agents of one module would
  share. The harness refuses those combinations.

## Agent count

### Definition and levels

N is the number of agents: N − 1 writers and the consumer,
`assistant_agent`. Levels N ∈ {3, 6, 12}. `users_v2` itself is N = 4
(three writers).

The facts stay constant. User i of the agent-count datasets has
exactly the history of user i of `users_v2`: the same events,
utterances, sessions and probes. Only the writer of each event changes,
so the store holds the same text at every N. A difference between
levels is then a difference in how many agents wrote the facts, not in
what was written. A generator that drew new facts per N would change
both at once.

### The writers

Each writer has its own slots: every slot of the v2 catalog
(`synth_v2.py`) belongs to exactly one writer at each N. A slot's own
events (its add, update, revoke or private statement) stay with one
writer, so the writer that states a fact first also updates and
revokes it, as v2 requires. Contradictions and echoes are made by a
writer other than the fact's owner at every N.

**N = 12** (11 writers). Each v2 writer's slots are split among new
writers by topic:

| v2 writer | Writer at N = 12 | Its slots (role, private, filler, and the echoes and contradictions it states) |
|---|---|---|
| profile | `profile_agent` | base profile; home city, pet; side business (private); board game, coffee roaster, podcast, swim club; echo: conference nerves; contradicts: conference, offsite city |
| profile | `people_agent` | manager; job interview (private); echo: teammate lunch; contradicts: teammate, one-on-one |
| profile | `standup_agent` | team chat app; echo: codename pride; contradicts: client |
| profile | `workstation_agent` | shell, keyboard layout, editor theme, terminal font |
| task | `task_agent` | base task context; staging host; poaching (private); CI, database, secrets store, feature flags, log platform; echoes: home-city shipping, pet groomer; contradicts: home city |
| task | `docs_agent` | codename; docs wiki, tracker; echo: conference demo; contradicts: conference |
| task | `code_review_agent` | pairing teammate; error tracker; echo: chat standup; contradicts: one-on-one, offsite city |
| task | `project_health_agent` | client; acquisition (private); echo: manager sign-off; contradicts: manager |
| calendar | `calendar_agent` | team-sync room, one-on-one; doctor (private); yoga studio, running club, choir, game night; echoes: chat retro, manager review, teammate session, codename review; contradicts: client, teammate, manager |
| calendar | `travel_agent` | conference, offsite city; echoes: home-city flight, pet sitter; contradicts: home city |
| calendar | `expenses_agent` | lawyer (private); book club, evening course, lunch talk, food bank |

Deriving a user fails when the map lacks one of its slots, echoes or
contradictions; a test checks that no writer of the map straddles two
v2 writers.

**N = 6** (5 writers) merges the N = 12 writers within each v2 writer:
`profile_agent` = all of v2 profile; `task_agent` = task, code review
and project health; `docs_agent` = docs; `calendar_agent` = calendar
and expenses; `travel_agent` = travel.

Because every writer at N = 6 and N = 12 lies inside one v2 writer, a
contradiction or an echo, which v2 makes across writers, stays across
writers. A private event stays its writer's last event: it is the last
event of its v2 writer's last session.

**N = 3** (2 writers, `profile_agent` and `task_agent`, as in v1)
merges the v2 writers, per user. v2 profile goes to `profile_agent`,
v2 task to `task_agent`. Each of v2 calendar's units (a slot with its
own events, a contradiction it states, an echo it states, a filler)
goes, first, to whichever of the two keeps contradictions and echoes
across writers; then, where that leaves a choice, away from the writer
holding the private fact if the unit comes after the private event;
then to `profile_agent` for even i and to `task_agent` for odd i. One
v2 rule cannot always hold at N = 3: for 32 of the 150 users (a check
against `users_v2`), the writer holding the private fact writes again
in a later session (16 because a contradiction or an echo forces a
later unit onto it, 16 because the private fact is calendar's and
calendar's second session is session 4, before both others'). On Mem0,
whose extraction sees a writer's earlier rows, that later write could
fold the private fact into a shared row. The derived file names these
users (`private_not_last`); a privacy failure there is attributed by
its carrier rows. In-house stores verbatim, so it is not affected.

**Memory types** stay the v2 event's (`profile`, `task_context`,
`calendar`), whoever writes it. The block prints rows in type order and
shows no writer, so at H = 0 the in-house blocks should be byte-equal
at every N.

**Datasets.** `benchmarks/shared_memory/agents_v1.py` derives
`data/agents_n3.jsonl`, `agents_n6.jsonl` and `agents_n12.jsonl` from
`users_v2.jsonl`, offline and with no LLM call (the paraphrases are
`users_v2`'s). Each header records `agents`, `writers`, the writer map,
`derived_from` (`users_v2` and its sha256) and the deriving module's
sha256; a test pins that the committed files are what the module
derives. A session of a derived user is a list of writer turns, one per
writer active in it, in the order of each writer's first event there.
`run_evaluation.py --dataset pilot_v2 --agents N` runs the first 30
users of `agents_nN`; `--agents 4`, the default, runs `pilot_v2` itself.

### Heterogeneity scales with N

H keeps its levels {0, 1, 2}, now as a fraction: d = round(H·N/3) of
the N agents deviate (N = 3: 0, 1, 2; N = 6: 0, 2, 4; N = 12: 0, 4, 8).
The schedule generalizes `HETEROGENEITY.md`'s: the 5N (agent, variant)
pairs sit on a cycle whose position k belongs to agent `order[k mod
N]`, each agent's five positions carrying the five variants in a
seeded order; user i gets the d consecutive positions starting at
`offset_H + d·i`, with offset 0 at H = 1 and 5·d(N, 1) at H = 2. At
N = 3, with the agents in the same order, this is the existing schedule,
pair for pair. Every writer can deviate, the new ones included (v2's
`calendar_agent` never does, because the pilot's schedule had to stay
fixed; the agent-count schedules are new). A variant reaches a new
writer through the same channels as a v2 writer.

### Predictions

**At H = 0, no locus changes with N on in-house, beyond cost.** The
store holds the same rows with only `owner_agent` changed. Selection
reads the owner only for visibility, and every row a consumer may see
is shared. So every judge-free outcome of a user is the same at every N,
in every locus, and the kernel and replicated in-house blocks should be
byte-equal across N. What grows with N is cost: writer turns, write
requests per turn and the harness's listings.

**At H = 0 on Mem0, small differences without a direction.** Mem0's
extraction sees the writer's own earlier rows, so the same write can be
extracted differently when the writer holds fewer of the user's facts.
A recency update stays with its owner, so the "update names both"
failures should not change.

Found in the functional check (`DEV_STATUS.md`, Subtask 18, known issue
53): the difference can be no row at all. Mem0 shows its extraction LLM
up to 10 of the user's memories with the same `agent_id` (the most
similar to the write) and the last 10 messages of that agent for that
user, and every locus passes the writer as `agent_id`. One vague
sentence, "Issues are sent to Rollbar.", was stored as nothing 7 of 16
times at N = 12, where its writer had stored almost nothing for the
user yet, and never in the 54 writes at N = 3 or 6 made one at a time
per user (once in 6 under concurrency); the trial then fails by the
extraction check, as any Mem0 write that stores nothing does.

**At H > 0, the per-probe effect is flat in N; the number of deviating
agents grows.** With H a fraction, a probe's target writer deviates with
about the same probability at every N, and so does the consumer (2/3 at
H = 2 for every N). So the expected share of probes a variant affects
is about the same at N = 3 and N = 12, in every locus, while the number
of agents whose configuration must be kept in step grows as H·N/3. Per
locus, as `HETEROGENEITY.md` predicts per variant:
- **kernel:** unchanged from its H = 0 trial except where a V1 or V3
  writer writes private rows, which every locus loses;
- **replicated:** V2 agents read and write the alias's partition, V4
  consumers drop rows, on top of the V1 and V3 losses;
- **native:** as replicated, and a V3 consumer that ignores visibility
  can inject another writer's private row.

This differs from the brief's expectation that more writers bring more
identity and visibility slips in replicated and native. They do, in
count of deviating agents and of slip events per trial at a fixed
fraction; the per-probe rate is predicted flat. A fixed number of
deviating agents would instead make the per-probe rate fall with N.

### What is measured

Per probe type and cell: the pass rate (with n and a 95% Wilson
interval), paired against the same user at H = 0 and the same N, and
across N at H = 0 (in-house: identical outcomes and blocks expected).
Also per trial: `memories_missing` and its split, `cross_user_rows`,
`private_rows_from_others`, the writers active, write requests, agent
turns and listing calls. Cost: backend tokens and calls; wall time only
with the cell's milliseconds per completion token (known issue 48).

### Grounding

Assistant deployments route one user's requests through several
specialized agents (a calendar agent, a travel agent, a code-review
agent), each writing what it learns. The question a deployment faces is
not whether two agents can share memory but whether the guarantees
still hold when ten do. In this codebase, every identity and visibility
bug so far came from one agent's own handling of a shared convention
(known issue 10, the `latest_user_id` contamination fixed before
Subtask 1, the user-less searches); more agents are more places for
such a bug.

## Concurrency

### Definition and levels

Levels: `sequential` (today's harness) and `concurrent`.

**Concurrent.** Sessions still follow each other: a session starts
after every write of the previous one has completed, as sessions are
days apart. Within a session, every write event (and every revoke) is
its own task, issued in script order without waiting for the earlier
ones, so the session's writers, and each writer's writes, run at the
same time. No event of a v2 session depends on another event of the
same session (an update, a revoke, a contradiction and an echo always
come in a later session than the statement they act on), so issuing
them together changes no fact's history. Once every write task of the
last session has begun (its request may not have reached the store
yet), the consumer's six probes are issued at once, each its own turn
(probes write nothing since Amendment 3, so their order does not
matter), and each probe's latency and completion are taken in its own
thread. A writer of the last session that fails after the probes were
issued fails the user; the probes still finish, and their kernel
session is closed, before the next trial. The
tasks are threads, each running in a copy of the issuing context (the
usage tag and the kernel session are context variables): the agents,
the SDK and the library are synchronous. The listing after the last
session is taken once its writes have completed, while the probes may
still run.

A probe issued while writes are in flight can race them only if the
kernel accepts it while they are in flight. Today it cannot: the
kernel's `/query` handler serves a memory request on the server's event
loop, so the loop accepts nothing else until that request completes,
and every request queues behind it at the HTTP layer. The kernel would
then show no timing miss for a reason that has nothing to do with its
barrier. So this subtask changes the kernel (below): a memory request
is accepted on the event loop (its syscall stamped against the barrier
and queued, in arrival order) and awaited off it, and a chat request's
barrier snapshot is taken when it arrives. One request at a time, the
kernel behaves as before.

### Predictions

- **Kernel:** a probe waits for every write the kernel accepted before
  it, whoever wrote it, so no write accepted before the probe is
  missing from its fetch, and none of its outcomes differs from the
  sequential trial for a timing reason. Its `barrier_wait_ms` is
  positive when writes are in flight, and no wait times out (60 s).
  A write accepted after the probe is not covered by design; the kernel
  reports both sides' barrier sequences, so such a write is counted as
  uncovered, not as a miss.
- **Replicated:** the consumer's barrier is its own and covers only its
  own writes, none of which a probe makes. A probe reads at once, so a
  write still in flight is missing from its fetch: a timing miss.
  Stale reads follow when the in-flight write is a recency update or a
  contradiction (the block holds the old value and not the new one),
  and a deletion failure when it is a revoke (the block holds the value
  the revoke was removing). On Mem0, where a write takes seconds (its
  extraction is a GPT-4o call), this should happen whenever a probe's
  target was written in the last session. On in-house, a write is one
  embedding and one insert (about 0.1 s) and the probe's own query
  embedding queues behind the writes' at Ollama, so the race may be
  lost rarely; how often is the measurement.
- **Native:** no barrier at all: as replicated.

Only the last session's writes can be in flight at the probes, so only
facts written there can be missed: in v2, a recency update, a revoke,
a contradiction or a private event in its writer's second session, for
about a third of the users each. Recall facts and the base rows are
written earlier and are never at risk.

### What is measured

Per probe:
- `writes_in_flight`: writes issued before the probe that had not
  completed when it was issued (harness clock);
- `late_writes`: writes issued before the probe that committed after
  the probe's fetch began. The fetch time is the library's (kernel and
  replicated) or the native consumer's own wall clock
  (`fetch_started_at`); the commit time is the write's own
  (`committed_at`, kernel and replicated, a forget's included) or the
  harness's completion time (native, an upper bound). A late write can
  still be read: `fetch_started_at` precedes the search's query
  embedding, so a write committing during the search is found (seen
  in-house; never on Mem0, whose writes take seconds), and the misses
  below also look at what the block held;
- `late_covered`: the late writes that are not uncovered (below), the
  ones a miss counts: every late write outside the kernel. `late_rows`
  are their rows the consumer may see;
- `timing_miss`: the probe's target statement was a covered late
  write and the block lacks its value;
- `stale_read`: a recency or contradiction probe whose newest
  statement was a covered late write and whose block held the stale
  value;
- `late_forget`: a deletion probe whose revoke was a covered late
  write and whose block held the revoked value;
- `barrier_wait_ms`, the barrier's outcomes (`DRAINED`, `TIMEOUT`) and,
  in the kernel, `uncovered_writes`: writes whose barrier sequence is
  above the probe's snapshot (accepted after it).

Per trial, `memories_missing_timing`: writers with a covered late
write none of whose rows reached the integration probe's block. A
writer the budget or a cap keeps out of the sequential trial's block
too is counted, so what timing cost is the paired `memories_missing`
(and the probes' judge-free outcomes), against the sequential trial.

### The load mode

`--load M` runs M users at a time against one kernel, M ∈ {1, 4, 16},
kernel locus only (the agent-managed loci keep one set of agents per
cell). Each user's trial runs as in the sequential mode; the M users'
trials overlap. Measured: throughput (users per minute), each probe's
latency (p50 and p95), and the kernel's share of it, split as the
diagnostics split it (`barrier_wait_ms`, `search_ms`, `select_ms`,
`format_ms`, `schedule_wait_ms`, `llm_ms`), with barrier timeouts and
the cell's milliseconds per completion token. The server awaits each
chat and memory request (and the audit and cost reads) off its event
loop on a pool of its own (64 workers, `aios/utils/request_pool.py`),
so none waits for a worker under the load mode; the loop's default
pool (12 workers here) would have held a request for a time no
diagnostic covers. Storage and tool requests are still served on the
loop.

Prediction: the local model bounds throughput (Ollama serves one
completion at a time here), so users per minute grows little with M and
latency grows about linearly. The kernel's own overhead should stay a
small share of a probe's latency, but grow with M: the kernel serves
memory writes one at a time on one thread, so a user's barrier wait
includes other users' writes queued ahead of its own. No barrier wait
should time out.

### Grounding

Read-your-writes and monotonic reads are the classic session guarantees
of replicated stores (Terry et al. 1994, "Session guarantees for weakly
consistent replicated data"); a consumer that reads before a writer's
acknowledged write lands is the cross-agent version. In this codebase,
3 of 90 kernel Mem0 conversation writes in the pilot took longer than
the barrier's 5 s timeout (`BENCHMARK_V2.md`, "Write barrier"): writes
that take seconds are the normal case on an extracting backend, and
the barrier is what makes a read wait for them.

## A faulty agent

### Definition and levels

Levels: `none`, `wrong_user`, `missing_metadata`, `flood10`,
`flood50`. In each, one agent of user i is faulty. It is chosen by the
seeded schedule among the agents the fault applies to that have
something to do in user i's history: for `wrong_user` and the floods, a
writer with at least one write event; for `missing_metadata`, any
writer with one, or the consumer. The candidates are taken in the
dataset's agent order, rotated by a seeded offset per fault, and user i
gets candidate `i mod (number of candidates)`. Every other agent is the
reference. The faults run at H = 0, sequentially.

### `wrong_user`

**What it does.** The faulty writer tags every memory request it makes
(its writes, its listings, its revokes) with another user's id: that of
the next user in the cell's run order (user i + 1; the last user tags
user 0's). Its provenance fields keep the true user, as variants never
change them.

**The kernel binds identity from the session.** Today the kernel takes
the user from the request's claim (`metadata.user_id`,
`params.user_id`), canonicalized, so a wrong id would file the write
under the other user. This subtask makes the kernel bind a request to
its session instead. The deployment, here the harness, opens a kernel
session for a user (`POST /session/open`, which returns a session
token) and runs the agents inside it; the SDK attaches the token to
every request, and the agent's own code never handles it. For a request
with a token, the kernel's resolver takes the user from the session,
rewrites the request's user ids to it, and records when the agent's
claim (canonicalized) disagreed: `identity_overridden` (the claimed and
bound ids) beside the response in the reply to a memory request and in
the injection diagnostics for a chat request, with a WARNING. An unknown or
closed token is refused. A request without one is served as today. The
harness opens one session per v2 session of a user and one for the
probes, and closes each after it.

The premise, stated for a reviewer to weigh: in the replicated locus the
library sits inside the agent and trusts its caller, which is the faulty
agent; a replicated deployment could hand each agent's library the
session's user too, but the faulty agent is the one that would have to
use it. Binding identity outside the agent is the coordination the
kernel provides.

**Predictions.**

| | Kernel | Replicated | Native |
|---|---|---|---|
| the faulty writer's rows | stored under user i: no row misfiled; `identity_overridden` on each of its requests | stored under user i + 1: misfiled | stored under user i + 1: misfiled |
| user i's probes | unchanged | the faulty writer's facts missing: its probes fail as with an empty write; its revokes forget nothing of user i's | as replicated |
| user i + 1's probes | unchanged | the misfiled rows are in user i + 1's partition: `cross_user_rows` in its blocks (a leak), and a slot user i + 1 also has can be answered with user i's value | as replicated |

The victim's leak shows only if it runs after the faulty trial, so the
last user's victim (user 0) shows its misfiled rows only in the store.

**Measured.** `misfiled_rows`: rows whose `provenance_user` is user i
stored under the victim's id, from a listing of the victim's partition
at the end of user i's trial. The victim's id is not added to user i's
own listings, whose audits would otherwise read the victim's rows; each
session's listing lists user i's rows in the victim's partition apart
(`misfiled`), and they are credited to the writes that stored them, so
a backend that extracts (Mem0) does not read the faulty writer's
writes as writes that stored nothing.
Also `cross_user_rows` in each probe's block, `identity_overridden`
counts, and the judge-free outcomes of users i and i + 1 against their
no-fault trials.

### `missing_metadata`

**What it does.** V3 of `HETEROGENEITY.md`, unchanged, on the one
faulty agent: a writer omits `owner_agent` and `sharing_policy`; a
consumer applies no visibility rule of its own.

**Predictions.** As `HETEROGENEITY.md` predicts for V3, and a control:
the kernel is not immune. A V3 writer's rows default to private in
every locus (the kernel and the library fill the owner and the private
policy; native rows have no policy, which its consumer reads as
private), so its facts are missing everywhere, and the kernel loses
them like the others. A V3 consumer changes nothing in the kernel and
replicated loci (visibility is enforced for it) and, in native, injects
another writer's private row only if one is retrievable (the private
fact, or a V3 writer's rows).

**Measured.** `memories_missing` and its split, `private_rows_from_others`
and the judge-free outcomes against the no-fault trial.

### `flood10`, `flood50`

**What it does.** In each session where it writes, after its own events,
the faulty writer stores F more rows (F = 10 or 50): odd-numbered ones
are near-duplicates of one of its session's utterances (cycling through
the utterance re-cased or re-punctuated, which normalizes to the
original, and the utterance with a prefix such as "Again:" or
"Reminder:", which does not), even-numbered ones are irrelevant notes
from a fixed list. A near-duplicate carries its source event's metadata
(`fact_key`, `session`, `memory_type`, `provenance_event`), as a
retried write would; an irrelevant note carries none of the fact
fields and the `provenance_event` `flood:<session>:<k>`. Every flood
row carries `metadata.flood` (k), by which the harness counts it and
keeps it out of its source event's stored rows.

(Corrected before the code, 2026-11-16: this paragraph first gave each
flood row the provenance event `<event>#flood<k>`. A copy with a new
event is a new statement of its slot, so under supersession each copy
would retire the slot's earlier rows, the original included, and the
flood would be absorbed by supersession in the kernel and replicated
loci alike instead of testing the quota. A retried write keeps its
event, and the library never lets a write retire rows of its own
event.)

**The quota.** A new library stage, `WriteQuota`, bounds what one writer
stores per user per session:
- it rejects a write whose normalized text (the scorer's normalization)
  equals a text the same writer already stored for the user in that
  session (`duplicate`); a rejected duplicate is not counted;
- it rejects a write once the writer has `max_writes` accepted writes
  for the user in that session (`quota`);
- a rejected write stores nothing, returns no id, releases its barrier
  sequence, and its reply says why (`quota_rejected`).

Settings: `memory.write_quota` with `enabled` (false), `max_writes` (4,
the most write events a writer has in one session of `pilot_v2` and its
agent-count versions; the harness checks this) and `dedupe` (true). The
session is the kernel session when the request has one, else the
write's `metadata.session`. It is off by default and on under the flood
levels. The kernel reports it in `/memory/config` `pipeline`, so the
replicated agents copy it like every pipeline setting.

**Predictions.**
- **Kernel:** the quota sits in the one write path every writer uses. The
  flooder's own write events (at most 4 a turn) are all accepted, and
  at most `4 − (its write events)` of its flood writes a turn: a revoke
  is no write, and the quota bounds writes, not rows (a Mem0 write can
  leave none or several). Duplicates that normalize to a stored text
  are rejected. The block changes little
  from the no-fault trial, and no reference writer's write is ever
  rejected (`quota_rejected` only on the flooder's).
- **Replicated:** the same library, but the quota runs in the writer's
  own pipeline, and the flooder is the agent that fails to apply it: its
  pipeline is built without the quota. All F rows a session are stored.
  The read-time dedupe drops exact duplicates only; near-duplicates of
  the flooder's facts crowd the count cap and the 300-token budget for
  probes about those facts, and long base rows lose budget to them, so
  `profile_facts_in_block` and the recall of other writers' facts fall
  in the integration probe and in probes near the flooder's topics.
  Supersession retires near-duplicates of a statement when a later
  statement of the slot replaces it (they carry its `fact_key` and its
  event), so recency is not hurt by them.
- **Native:** no quota, no dedupe and no supersession: all F rows a
  session are stored, the native fetch of k = 10 fills with flood rows
  for probes near the flooder's topics, and a near-duplicate of a fact
  that is later updated keeps its old value.
- On Mem0, the backend's own extraction merges some near-duplicates in
  every locus, so the effect is smaller than in-house.

A consumer can cap rows per writer at read time on its own, and a
replicated deployment could do that. It would not keep the flood out of
the store (each consumer pays for it at every fetch, and other
consumers see it), which is what the write-side quota does.

**Measured.** `flood_rows_stored` (from the listings), `flood_rows_in_block`
(rows with a `#flood` provenance event, per probe), `quota_rejected`
(by reason and writer), `profile_facts_in_block` (integration probe),
the judge-free outcomes against the no-fault trial.

### Grounding

Mis-tagged identity is the bug class behind every cross-user leak this
codebase has had (`HETEROGENEITY.md`, V2). Flooding has a precedent
here too: on the self-improving branch, an upsert whose existence check
always came back empty stored a new profile and task-context row at
every interaction (Cerebrum `0b217a9`, `memory-providers.md`, "One
profile and one task-context memory per user"). Poisoning or flooding a
shared memory store from one agent is the threat model of memory
poisoning attacks (for example AgentPoison, Chen et al. 2024); here the
fault is a bug, not an attack, and the defense measured is a quota, not
a detector.

## Kernel and library additions

1. **Session context.** `POST /session/open {"user_id"}` returns
   `{"session_token"}`; `POST /session/close {"session_token"}` ends
   it. The registry (`SessionRegistry`, `aios/memory/pipeline/identity.py`)
   maps a token to the canonical user. `QueryRequest` gains
   `session_token`; the SDK sends the token of the innermost
   `kernel_session(...)` context (a context variable, which the
   harness's worker threads copy). The binding, the refusal and
   `identity_overridden` are as above. Tests: a write claiming another
   user lands in the session's user's partition with
   `identity_overridden`; a chat request with a session reads the
   session's user; an unknown token is refused; without a token nothing
   changes; and the equivalence test, extended: a kernel write and
   injection under a session for user u equal the library's for u.
2. **WriteQuota** (`aios/memory/pipeline/quota.py`), a stage of
   `MemoryPipeline.write`, before the provider is called, with the
   settings above (`PipelineSettings.write_quota`). The kernel holds one
   quota for every per-request pipeline, as it holds one barrier.
   Thread-safe. Tests: the rules above, and the equivalence test,
   extended: with the quota on, the kernel and the library reject the
   same writes and store the same rows.
3. **Event-driven scheduler.** `FIFOScheduler`'s LLM thread slept
   `batch_interval` (1 s) before draining its queue (known issue 15).
   Now it blocks on the queue until a request arrives (the queue's own
   condition variable), takes every request already queued without
   waiting, and runs them as one batch, in arrival order; there is no
   fixed interval. Requests that arrive while a batch runs form the
   next batch, as before. The memory, storage and tool threads already
   block on their queues. After `stop()` an idle thread ends within its
   queue's 0.1 s get timeout. Tests: arrival order, a request queued
   while a batch runs, no idle wait, prompt stop. The equivalence test runs unchanged. And a 10-user
   before/after on `pilot_v1` (kernel in-house, Qwen, judged): the
   blocks and answers must be identical; the scores are compared, and a
   score that differs on an identical answer is the judge's noise
   (known issue 24). `schedule_wait_ms` is reported before and after.
4. **Memory requests off the event loop.** As described under
   Concurrency: accepted on the loop in arrival order (stamped and
   queued), awaited off it; a chat request's snapshot taken at arrival.
   Tests: two memory requests in flight at once both complete, and a
   chat request accepted while a write is in flight waits for it.
5. **Diagnostics.** The library's retrieval diagnostics gain
   `fetch_started_at` and `barrier_snapshot`; a write's outcome and a
   forget's report gain `committed_at` and `barrier_seq`;
   `quota_rejected` and `identity_overridden` as above.

Any change to a module of `aios/memory/pipeline/` changes
`PIPELINE_VERSION`, as always.

## Harness

`run_evaluation.py` gains:
- `--agents N` (3, 4, 6 or 12; default 4): the agent-count version of
  the v2 dataset;
- `--concurrency sequential|concurrent` (default sequential);
- `--load M` (default 1; kernel locus only);
- `--fault none|wrong_user|missing_metadata|flood10|flood50` and
  `--fault-seed S`.

H keeps `--heterogeneity` and `--variant-seed`. The combinations above
that are not crossed are refused. `TrialResult` records `agents`,
`concurrency`, `load`, `fault`, `faulty_agent`, `fault_victim`, and
`stress`: the measures above per probe and per trial. The results file
records the levels and seeds in `run_settings`. A stress report
(`benchmarks/shared_memory/stress_report.py`) pairs each trial with its
reference and tabulates the measures per dimension, level, locus and
backend.

## Functional check and smoke

**Functional check** (judge-free, Qwen, users 0 to 4 of `pilot_v2` or
its agent-count versions; kernel, replicated and native; in-house and
Mem0):
- agent count: N ∈ {3, 6, 12} at H ∈ {0, 2};
- concurrency: `concurrent` at N = 6, H = 0 (the reference is the
  sequential N = 6, H = 0 cell);
- faults: each of the four at N = 6, H = 0 (same reference);
- load: M ∈ {1, 4, 16} on users 0 to 15 at N = 6, kernel locus, both
  backends.

It checks each prediction above and records every deviation in
DEV_STATUS, as `HETEROGENEITY.md` did: a deviation is a finding, not
something to tune away. The checks that must hold, because the design
guarantees them:
- the run at N = 12 completes end to end in every cell;
- in-house at H = 0, every judge-free outcome is the same at N = 3, 6
  and 12 in every locus, and the kernel and replicated blocks are
  byte-equal across N;
- under `concurrent`, no kernel probe has a late write that the kernel
  accepted before it (`late_covered` is empty);
- under `wrong_user`, no kernel row is misfiled and every faulty
  kernel request records `identity_overridden`;
- under the floods, the kernel accepts at most `4 − (its write events)`
  flood writes per flooding writer turn (`flood_sessions_over_bound`
  is 0; the bound is `max_writes`, 4, less the turn's accepted write
  events), and no reference writer's write is rejected.

**Smoke** (judge-free, Qwen, all 30 users at N = 6, in-house only, H =
0): the sequential no-fault reference, `concurrent`, `flood10` and
`flood50`, each in the three loci. Reported per cell, with 95% CIs
(Wilson for rates; paired against the reference over users, with a t
interval for means and an exact McNemar test for paired outcomes):
`memories_missing` (and its timing part), the leak counts, the flooder
rows stored and in blocks, the judge-free pass rates.

## What this does not show

- **No scores.** Integration is not judged here; the scored runs are the
  grid's.
- **Not crossed.** Concurrency and load with heterogeneity or a fault,
  and two faults at once.
- **One faulty agent, one fault.** A writer that is faulty in two ways,
  or several faulty agents, is not tested.
- **The flood is benign.** Its rows restate the flooder's own facts or
  are irrelevant; adversarial rows written to be retrieved (poisoning)
  are not tested, and the quota is not a defense against them.
- **Concurrency inside one session only.** Overlapping sessions, where
  write order itself becomes a race, are not tested.
- **One machine.** The load mode measures one kernel and one local model
  on a laptop whose speed varies (known issue 48); it shows how the
  kernel's overhead scales, not a deployment's throughput.
