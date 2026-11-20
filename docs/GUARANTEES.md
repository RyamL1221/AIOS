# Memory guarantees and their audit

What the kernel's memory guarantees, stated as the code at `d49afc9`
(branch `feature/NeurIPS-2027-changes`) enforces them, and an
adversarial audit of every path that reads or writes memory. For each
property the paper would claim: a precise statement, its assumptions,
the code that enforces it, the tests that pin it, and the paths that
could bypass it. The audit then gives a verdict for each property on
each path, and the gaps found close the file. Written 2026-11-20. It
reports gaps and fixes none: no code or test was changed.

## How to read this file

**Method.** Every module of `aios/memory/` (the manager, the pipeline
library, the injector, the extractor, the providers), `aios/syscall/`,
`runtime/launch.py`, the scheduler's memory thread,
`aios/utils/request_pool.py` and the tests under `tests/modules/memory/`
and `tests/modules/syscall/` were read at `d49afc9`. `aios/storage/`
and `aios/tool/` were read only to rule them out. Nothing was
executed: no kernel, provider, model or test. A test named below was
read, not run, and what it would catch is taken from its text. One
command computed something: a standard-library replica of two regular
expressions of the Mem0 provider (gap G4).

**Verdicts.** "Holds": on that path the code enforces the statement,
given the common assumptions below. "Holds under assumption": it also
needs the assumption the gap names. "Does not hold": the code allows a
path that violates the statement. Every verdict is by reading; not
executed.

**Statements.** Each statement is the rule the code implements, not a
stronger one. Where a document claims more, "Documents the code
contradicts" says so.

**References.** `file:line` at `d49afc9`. Short names: `facade.py`,
`selector.py`, `deletion.py`, `tombstones.py`, `identity.py`,
`quota.py`, `barrier.py`, `visibility.py`, `settings.py` and
`ablation.py` are in `aios/memory/pipeline/`; `manager.py`,
`context_injector.py` and `conversation_extractor.py` in
`aios/memory/`; `base.py`, `chroma_inhouse.py`, `in_house.py`,
`mem0.py`, `graphiti.py` and `amem.py` in `aios/memory/providers/`;
`syscall.py` is `aios/syscall/syscall.py`; `launch.py` is
`runtime/launch.py`. A test is named `file::test`, its file under
`tests/modules/`.

## What every guarantee assumes

**Trusted.**
- The kernel process and its configuration as read at startup. This
  audit did not open `config.yaml`. The values a v2 run uses are known
  only from the pre-flight's requirements (`BENCHMARK_V2.md:528-545`):
  `write_barrier.timeout_ms` at least 60,000, `auto_extract` off,
  `supersession: exclude` (or off under its control), a
  `tombstones_path`.
- The provider contract (`PROVIDER_CONTRACT.md`): a provider stores
  and returns each row's metadata as written; `search`, `list` and
  `get` stay in the named user's scope; `delete` deletes; and a row
  can be searched and listed once `add` returns. Where a provider
  falls short, a gap names it.
- The agents' own claims. The kernel authenticates no agent:
  `QueryRequest.agent_name` is whatever the client sends
  (`launch.py:134-146`). A write keeps any `metadata.owner_agent` it
  names and fills the writer's name only when it names none
  (`facade.py:258-259`; `test_add_memory_keeps_an_explicit_owner` in
  `memory/test_retrieve_for_agent.py` pins it). The statement labels
  (`fact_key`, `structured`, `value_aliases`, `provenance_event`) and
  a note's id (`id` or `memory_id`, `facade.py:59-77`) are the
  writer's too.
- The transport. No route authenticates its caller, and CORS allows
  every origin (`launch.py:63-69`, commented "Modify this in
  production!"). Every guarantee assumes that only the deployment's
  own clients reach the kernel's port and that agents use only the
  SDK's memory and chat calls.
- The clock. No guarantee reads the wall clock. The barrier's timeout
  runs on the monotonic clock (`barrier.py:314`, `:340`);
  `committed_at` and `fetch_started_at` are diagnostics.

**Out of scope.**
- An agent that reaches a backend directly: a Chroma directory, Neo4j,
  Mem0's files. Agents started by `/agents/submit` run in the kernel's
  own process (`aios/hooks/modules/agent.py:18-60`). Their requests go
  over HTTP like any agent's (the in-process hook is commented out,
  `:58`), but nothing stops their code from importing kernel modules.
- The native conditions: the agents manage their own memory and the
  library does not run (`NATIVE_USAGE.md`).
- The replicated loci: the same library runs inside each agent, with
  its own barrier, resolver and quota (`REPLICATED_LOGIC.md:67-89`).
  The kernel's cross-agent guarantees (one barrier, one quota, session
  binding) do not carry over.
- Retention outside the memory system: logs, the model providers, what
  an agent already said (`DELETION_AND_SUPERSESSION.md:634-657`).

## The paths

`launch.py` has 19 routes (`grep -c "^@app\."`). Those that read or
write memory or identity, with the operations `/query` serves:

| ID | Path | Code | Runs on |
|---|---|---|---|
| R1 | Chat injection: `POST /query`, `llm`, action `chat` or `chat_with_tool_call_output` | `launch.py:958-1021` (binding `:984`); `syscall.py:786-851`; `context_injector.py:63-239`; `facade.py:631-708`; `selector.py:139-371` | a request-pool thread (`aios/utils/request_pool.py:19-33`) |
| R2 | SDK search: `retrieve_memory` | `launch.py:1035-1068`; `syscall.py:140-163`; `manager.py:713-753`; `selector.py:139-371` | the memory thread |
| R3 | Agentic retrieval: `retrieve_memory_raw` inside `add_agentic_memory` (sent alone, it is refused: `syscall.py:950-961`) | `syscall.py:916-921`; `manager.py:755-794` | the memory thread |
| R4 | Read by id: `get_memory` | `manager.py:689-711`; `facade.py:334-349`, `:499-526` | the memory thread |
| R5 | Owner listing: `list_memory` | `manager.py:898-935`; `facade.py:436-491` | the memory thread |
| R6 | Audit: `GET /memory/audit?user_id=` | `launch.py:671-688`; `manager.py:937-957` | a request-pool thread |
| R7 | Cost: `GET /memory/cost?user_id=`; usage records (tag, purpose, model, token counts: Cerebrum `cerebrum/utils/usage.py:68-83`), no rows | `launch.py:691-724`; `manager.py:340-345` | a request-pool thread |
| R8 | Settings: `GET /memory/config`; no rows | `launch.py:527-573` | the event loop |
| W1 | `add_memory` | `syscall.py:87-126`; `manager.py:620-675`; `facade.py:210-332`; `deletion.py:281-377` | the memory thread |
| W2 | `update_memory` | `manager.py:808-838`; `facade.py:351-405` | the memory thread |
| W3 | `remove_memory` | `manager.py:880-896`; `facade.py:407-421` | the memory thread |
| W4 | `forget_memory` | `manager.py:959-985`; `facade.py:528-582`; `deletion.py:82-224` | the memory thread |
| W5 | The kernel's conversation turn, after a chat (action `chat`, `auto_extract` on) | `syscall.py:864-889`; `conversation_extractor.py:49-184`; then W1's branch of `manager.py` | a daemon thread, off the queue |
| W6 | `add_agentic_memory`: an analysis model call, R3, an evolution model call, `update_memory` sub-requests, then an `add_memory` | `syscall.py:153-154`, `:407-731`, `:916-932` | a request-pool thread, then the memory thread |
| A1 | `POST /session/open`, `POST /session/close` | `launch.py:584-609`; `identity.py:152-196` | the event loop |
| A2 | `POST /core/refresh`, and `POST /core/config/update`, which calls it (`launch.py:1108`) | `launch.py:425-445`, `:498-516` | the event loop |
| A3 | `POST /core/cleanup` | `launch.py:919-952` | the event loop |
| A4 | `POST /agents/submit` | `launch.py:828-870`; `aios/hooks/modules/agent.py:18-60` | a factory thread |

**Not paths to memory.** Storage and tool requests
(`launch.py:1023-1034`): no module under `aios/storage/`, `aios/tool/`,
`aios/llm_core/`, `aios/context/` or `aios/terminal/` names
`aios.memory`, `MemoryManager`, `mem0` or a tombstone (grep at
`d49afc9`). LLM actions other than the two chat actions inject nothing
(`syscall.py:893-912`). The agentic path's own model calls go to
`execute_llm_syscall` directly (`syscall.py:489`, `:680`), so they are
neither injected nor stored. The only provider call outside the
library is the audit's `list` (`manager.py:952`);
`MemoryManager._locate_memory` and `_fetch_candidates`
(`manager.py:506-526`) have no caller in `aios/` or `runtime/`.

**One memory thread.** The scheduler serves queued memory requests one
at a time, in queue order (`fifo_scheduler.py:266-273`, and the same in
`rr_scheduler.py:199-206`, both in `aios/scheduler/`), and `/query`
queues them in arrival order on the event loop (`launch.py:1062-1064`).
Off the queue run R1, R6, R7 and W5. Every race below needs one of
them, or the second memory thread of gap G12.

## Visibility

**Statement.** For a request made under agent name A, a row whose
stored `owner_agent` is not A is returned only when its stored
`sharing_policy` is exactly `"shared"`. This holds for every selection
(R1, R2, R3) and for a read by id (R4). The owner listing (R5) returns
only A's own rows, and an update or delete by id (W2, W3) changes only
A's own rows; another agent's row, shared or not, gets the same
"Memory not found" as a missing one (`manager.py:700-705`, `:834-835`,
`:894-895`). An SDK `sharing_policy` other than `"shared"` narrows the
rule further (`selector.py:272`). A row with no `owner_agent` is no
agent's own: it is returned only if shared, except to a request whose
agent name is the empty string, which selection takes for its owner
(`visibility.py:49-53`). Every write through the library names an
owner (`facade.py:258-259`), so such rows come only from outside it.

Two operations act on other agents' rows by design, as the user's
(Decision 1, `DELETION_AND_SUPERSESSION.md:297-302`): a forget deletes
them, and a write's sweep and supersession marks delete or mark them.
Their replies name ids, owners and reasons, never another agent's
text; a forget's `values` holds only values from rows A may read
(`deletion.py:128-145`, `:210-221`).

**Assumptions.**
1. Agent names are truthful, in the request and in a written row's
   `owner_agent` (gap G1).
2. The provider returns each row's stored `owner_agent` and
   `sharing_policy` (the contract; Mem0 merges the keys it promotes
   back into the metadata, `mem0.py:562-574`).
3. A row's text comes from its own write. In-house stores it verbatim
   (`chroma_inhouse.py:154-168`), as Mem0 does with `infer` off. With
   `infer` on, Mem0's extraction reads the writer's own memories and
   messages only, scoped by `agent_id` (DEV_STATUS known issue 53;
   `mem0.py:787-791`). A-MEM keeps the content verbatim and withholds
   the keywords, context and tags its evolution writes from other
   notes (`amem.py:140-154`). Graphiti does not meet it (gap G3).

**Enforced by.** `apply_sharing_filter` (`visibility.py:11-108`; the
invariant at `:53-57`), the only visibility rule, applied by the
selector after the user partition (`selector.py:270-289`);
`Visibility.can_read` for a read by id (`visibility.py:116-124`,
`facade.py:511-514`); `Visibility.can_write` for the owner listing,
update and delete (`visibility.py:126-130`; `facade.py:472-476`,
`:374-378`, `:414-418`). No provider filters by visibility
(`base.py:117-124`). The kernel's conversation turn is written private
to the assistant (`facade.py:98-103`).

**Pinned by.** Each test is listed under its file; after a colon,
what it would catch.
- `memory/test_retrieve_for_agent.py`:
  `test_sdk_search_without_policy_hides_other_agents_private`,
  `test_injection_hides_other_agents_private`: a selection that
  returns another agent's private row;
  `test_get_memory_hides_another_agents_private_memory`,
  `test_get_memory_allows_owner_and_shared`,
  `test_get_memory_fails_closed_without_an_owner`: a read by id that
  ignores the owner.
- `memory/test_context_injector_access_matrix.py`: `TestAccessMatrix`,
  the eight cases of user, owner and policy.
- `memory/test_provider_contract.py`:
  `test_provider_never_filters_by_visibility`,
  `test_no_provider_module_has_a_visibility_filter`,
  `test_retrieve_memory_raw_goes_through_the_kernel_rule`: a
  provider-side filter, and R3 skipping the rule.
- `memory/test_conversation_write_path.py`:
  `test_conversation_is_never_injected_into_another_agent`,
  `test_other_agent_cannot_change_a_private_memory`,
  `test_other_agent_cannot_change_a_shared_memory`.
- `memory/test_list_and_delete.py`:
  `test_list_own_returns_the_agents_rows_for_the_user_only`,
  `test_delete_is_owner_only`.
- `memory/test_forget_and_supersession.py`:
  `test_forget_reports_only_values_the_caller_may_read`.
- `memory/test_amem_provider.py`: `test_rows_carry_no_derived_text`.
- `memory/test_ablation.py`:
  `test_without_visibility_another_agents_private_row_is_selected`,
  `test_without_visibility_writes_stay_owner_only`: the switch.

No test writes a Graphiti row whose text came from another agent's
private write.

**Bypasses.** A client that sends another agent's name (G1); the
audit route, which returns every agent's rows (G2); Graphiti's derived
text (G3); counts and ids in diagnostics and replies, which the
statement does not cover (G24); `visibility: off`; an agent in the
kernel's process.

## User partition

**Statement.** A request is served for one scope S: its user id in
canonical form (`identity.py:54-65`; the session's user when a token
is honored), or the agent's own name when it names no user or names
the agent itself (`identity.py:115-140`, `selector.py:189-192`).
- A selection (R1, R2, R3) returns only rows whose stored `user_id` is
  S exactly, failing closed on a missing one (`selector.py:259-268`).
- The owner listing (R5) does the same (`facade.py:472-476`); the
  forget, the sweep and supersession act only on such rows
  (`deletion.py:54-66`).
- A write is filed under its `metadata.user_id` in canonical form,
  else the agent's name (`facade.py:252-255`; the add branch passes no
  other user, `manager.py:651-652`).
- A read, update or delete by id (R4, W2, W3) fetches the row from the
  provider's scope for S, or, when the request names no user, from the
  agent's scope and then the provider's default scope
  (`facade.py:343-348`). It does not check the row's `user_id` again
  (`facade.py:499-526`, `:374-378`, `:414-418`).

Without a session, S is the client's claim: any client can read and
write any user's partition by naming its id. "Another user" therefore
means a user other than the one the request is served for.

**Assumptions.**
1. A provider's `search` and `list` return only S's rows. The kernel
   re-checks selections, listings and the forget, so a mis-scoped row
   is dropped there, not shown.
2. A provider's `get(id, S)` finds only S's rows; nothing re-checks
   it. In-house keeps one collection per user, named with a SHA-256
   digest of the id (`base.py:107-114`, `chroma_inhouse.py:112-137`).
   Graphiti keeps one group per user with a digest (Cerebrum
   `cerebrum/utils/graphiti.py:46-57`), and every query matches the
   group. A-MEM keeps one store per user (`amem.py:129-135`). Mem0
   does not meet it for some pairs of ids (G4).
3. Every row carries its `user_id`, and no real user's id is the
   provider's default scope, `"default"` (G5).

**Enforced by.** The partition check in the selector
(`selector.py:259-268`), the listing filter (`facade.py:472-476`),
`partition` (`deletion.py:54-66`), canonical ids at acceptance and at
service (`manager.py:367`, `:477-491`, `:600`, `:617`), and per-user
scopes in every provider.

**Pinned by.**
- `memory/test_retrieve_for_agent.py`: `test_partition_fails_closed`,
  rows of another user and of none dropped;
  `test_no_identity_skips_shared_retrieval`.
- `memory/test_context_injector_access_matrix.py`:
  `TestNamespacedIdentities`, `TestMalformedMetadata`,
  `TestRelevanceDoesNotOverrideIsolation`,
  `TestLegacyUnscopedMemories`.
- `memory/test_mem0_cross_user_isolation.py`:
  `TestContextInjectorCrossUserIsolation`, a provider that returns
  another user's rows, which the kernel drops.
- `memory/test_memory_user_identity_isolation.py`: six regression
  tests of the old `latest_user_id` fallback, which served a request
  with no user id from the last writer's partition.
- `memory/test_provider_contract.py`:
  `test_search_and_list_stay_in_the_user_scope`: search and list
  only, not `get`.
- `memory/test_identity_rules.py`:
  `test_kernel_stores_a_v2_writer_under_the_canonical_id`,
  `test_kernel_serves_a_v2_consumer_the_canonical_partition`.
- `memory/test_graphiti_provider.py`:
  `test_groups_are_valid_and_one_per_user`;
  `memory/test_amem_provider.py`:
  `test_each_user_has_a_store_of_their_own`.
- Two tests pin behavior a gap rests on:
  `memory/test_mem0_collection_names.py`:
  `test_ids_that_fit_keep_their_name` (G4);
  `memory/test_conversation_write_path.py`:
  `test_lookup_without_user_id_tries_agent_scope_then_default` (G5).

No test reads, updates or deletes by id across users.

**Bypasses.** Mem0 ids that share a collection (G4); a read by id of a
row with no `user_id` or in the default scope (G5); the audit route,
which serves any user named in its query string (G2); without a
session, any claim (G6); `identity: claim`, which serves the raw
claim.

## Session-bound identity

**Statement.** Under `identity: session` (the default), a request over
`POST /query` that carries a session token the registry holds is served
for the session's user, whatever user it claims:
- A memory request is rewritten before it is stamped and queued
  (`launch.py:1054-1064`; `manager.py:394-437`): its
  `metadata.user_id` for an add (`add_memory`, `add_agentic_memory`),
  its `params.user_id` for every other operation and for an add that
  names one, and any other operation's `metadata.user_id` when it
  names one.
- A chat request's injection is for the session's user
  (`launch.py:650-668`; `manager.py:439-456`), and so is its
  conversation turn, which takes the injection's resolved user
  (`syscall.py:875-889`).
- The claim it overrode is reported as `identity_overridden` beside the
  reply (`launch.py:1066-1067`) or in the injection diagnostics
  (`syscall.py:846-847`), with a WARNING (`manager.py:430-436`,
  `:450-455`).
- An unknown or closed token is refused: a memory request is answered
  `success` false and not queued (`launch.py:1058-1061`), a chat gets
  HTTP 400 (`launch.py:985-986`).
- A request without a token is served for its claim
  (`manager.py:408-409`, `:446-447`).

**Assumptions.**
1. The token binds; it does not authenticate. `/session/open` takes any
   user id from any caller (`launch.py:584-599`), and a client that
   leaves the token out is served for the user it names (G6). The
   property is built for an agent that mis-tags the user inside a
   session the deployment opened, the `wrong_user` fault
   (`STRESS_DIMENSIONS.md:379-432`), where "the fault is a bug, not an
   attack" (`:539-543`).
2. A token cannot be guessed: 32 hex characters from
   `secrets.token_hex(16)` (`identity.py:176`).
3. Sessions live in the process's memory (`identity.py:163-167`). A
   restart forgets them, and a request with an old token is then
   refused: the property fails closed.

**Enforced by.** `MemoryManager.bind_session` and `bind_chat_user`
(`manager.py:394-456`), called by the handler before acceptance
(`launch.py:625-668`); `SessionRegistry` (`identity.py:152-196`).

**Pinned by.**
- `memory/test_kernel_sessions.py`:
  `test_a_session_maps_its_token_to_its_user_until_closed`,
  `test_a_token_differs_from_every_earlier_token`,
  `test_a_write_claiming_another_user_is_bound_to_the_session`,
  `test_every_request_is_bound` (list, forget, get, remove, retrieve,
  update),
  `test_an_unknown_session_is_refused_and_no_session_changes_nothing`,
  `test_the_handler_files_a_wrong_user_write_under_the_session`,
  `test_the_handler_refuses_an_unknown_session`,
  `test_without_a_session_the_claim_is_served_as_before`,
  `test_a_chat_request_reads_the_sessions_user_and_records_the_claim`,
  `test_a_chat_request_with_an_unknown_session_is_refused`,
  `test_bound_requests_equal_the_library_for_the_sessions_user`: a
  request served for its claim inside a session, or an unknown token
  accepted.
- `memory/test_ablation.py`: `test_under_claim_a_session_binds_nothing`,
  `test_the_handler_ignores_a_session_under_claim`: the switch.

No test sends `add_agentic_memory` with a token, or a chat with a
token while `auto_inject` is off.

**Bypasses.** A request without a token, and anyone opening a session
(G6); the audit and cost routes, which take a bare `user_id` (G2); the
conversation turn when injection is off (G7); `identity: claim`
(`launch.py:612-622`). The agentic path holds by reading: the request
is bound before it is served (`manager.py:420`), its sub-requests
reuse the bound parameters, and its evolution's `update_memory`
requests, built afresh (`syscall.py:926-931`), carry `id` but no
`memory_id` (`syscall.py:719-722`), so each is refused
(`manager.py:815-821`).

## Read-after-write across writers

**Statement.** The kernel has one barrier for every agent
(`manager.py:184-187`). Each accepted write of user U gets a sequence
number, increasing across all users (`barrier.py:105-142`); each
accepted read of U gets a snapshot, the counter at acceptance
(`barrier.py:233-262`). Before its provider fetch, a read waits until
every write of U with a sequence at or below its snapshot has been
released, or until `timeout_ms` has passed (`barrier.py:264-365`). A
write is released when its provider call and its `after_write` (the
lift, the sweep, the supersession marks) have returned or raised
(`facade.py:329-332`). So a read of U sees every write of U accepted
before it, whichever agent wrote it, unless its wait timed out. A
failed write is released too, and there is nothing of it to see.

What "accepted" means:
- a memory request over `/query`: when `accept_memory` stamps and
  queues it on the event loop, in arrival order (`launch.py:1062-1064`;
  `syscall.py:103-123`, `:140-163`);
- a chat: when the handler takes its arrival snapshot on the event
  loop (`launch.py:667-668`; `manager.py:458-470`);
- the kernel's conversation turn: when `extract_async` stamps it on the
  request thread, after the model's reply and before the chat response
  returns (`conversation_extractor.py:92-96`);
- `add_agentic_memory`: when its final `add_memory` is submitted, after
  two model calls (`syscall.py:916-932`), not when the request arrived
  (G9).

Writes that are stamped (`manager.py:368-379`): an add naming
`metadata.user_id`; an update naming `params.user_id` or
`metadata.user_id`; a forget naming `params.user_id`; every
conversation turn. Not stamped: `remove_memory` (G8); an add or update
that names no user (G10).

Reads that wait: R1; R2 and R5 naming `params.user_id`
(`manager.py:380-387`); R3; a forget, for the writes through its own
sequence − 1 (`facade.py:566-567`); R6 and R7, for every write
accepted before them, even under `barrier: off`
(`manager.py:340-345`, `:950`). Reads that do not wait: R4, which takes
no snapshot, and R2 or R5 naming no user (G10). Among queued requests
the order holds without the barrier, since one thread serves them in
queue order ("The paths"); the barrier is what orders R1, W5, R6 and
R7 (as `ABLATION.md:113` says of `barrier: off`).

**Assumptions.**
1. Every write accepted before the read commits within `timeout_ms`;
   otherwise the read proceeds without it (G11). The default is
   5,000 ms (`barrier.py:85-86`); v2 kernel runs set at least 60,000
   (`BENCHMARK_V2.md:534`). In the pilot, 3 of 90 kernel Mem0
   conversation writes took longer than 5 s (`BENCHMARK_V2.md:636-640`).
2. A row is visible to `search` and `list` once `add` returns. Mem0's
   `add` waits until each new row reads back by id, up to 10 s, and
   then returns with a WARNING (`mem0.py:758-771`, `:813-815`).
3. The barrier is enabled (`write_barrier.enabled`, default true:
   `barrier.py:83`), `barrier: on`, and the provider does not commit
   synchronously. Only the in-memory test provider does
   (`in_house.py:37`); with it the kernel wires no injector, extractor
   or stamping (`launch.py:35`, `:352-389`), so every read and write
   goes through the memory thread, except R6, which then does not wait
   for queued writes.
4. One kernel per process: no `/core/refresh` since startup (G12).

**Enforced by.** `MemoryWriteBarrier` (`barrier.py`); the one stamping
site, `MemoryManager.stamp_syscall` (`manager.py:347-387`), called
before a request is queued (`syscall.py:107-113`) and by the extractor
on the request thread (`conversation_extractor.py:96`); the waits in
the selector (`selector.py:84-108`, `:220-227`), the listing
(`facade.py:469`) and the forget (`facade.py:566-567`); releases on
every path (`facade.py:329-332`, `:403-405`, `:580-582`;
`manager.py:628-632`, `:818`, `:854-860`;
`conversation_extractor.py:147-156`, `:184`).

**Pinned by.**
- `memory/test_write_barrier_unit.py`: monotonic acquire, release on a
  failed write, snapshots, bypasses, the timeout's WARNING, disjoint
  users.
- `memory/test_write_barrier_integration.py`, scenarios 1 to 5
  (cross-agent personalization through the executor, restart, the kill
  switch), and the property and stress files beside it.
  `test_write_barrier_stress.py::Scenario2DisjointUsersTests` is flaky
  (known issue 6).
- `syscall/test_memory_requests_off_loop.py`:
  `test_two_memory_requests_are_accepted_while_both_are_in_flight`,
  `test_a_request_is_stamped_before_a_chat_that_arrives_after_it`,
  `test_a_chat_waits_for_the_writes_accepted_before_it_only` (a chat
  waits for the write accepted before it, and not for the one after),
  `test_no_snapshot_without_a_user_or_with_a_synchronous_store`.
- `memory/test_conversation_write_path.py`:
  `test_stamped_before_extract_async_returns_then_released`,
  `test_released_when_the_provider_fails`,
  `test_released_when_the_thread_cannot_start`,
  `test_retrieval_right_after_extraction_observes_the_write`.
- `memory/test_update_stamping.py`:
  `test_retrieval_after_an_update_reads_the_new_content`.
- `memory/test_list_and_delete.py`:
  `test_list_memory_is_stamped_like_a_retrieval`,
  `test_kernel_listing_right_after_a_chat_turn_includes_the_turn`.
- `memory/test_forget_and_supersession.py`:
  `test_a_forget_waits_for_a_write_accepted_before_it`,
  `test_a_retrieval_accepted_after_a_forget_waits_for_it`,
  `test_a_forget_never_waits_on_its_own_sequence`.
- `memory/test_identity_rules.py`:
  `test_kernel_canonicalizes_at_acceptance_so_barrier_keys_agree`.
- `memory/test_ablation.py`:
  `test_without_the_barrier_a_chat_reads_before_a_write_accepted_first`,
  `test_without_the_barrier_the_harness_reads_still_wait`: the switch.

No test orders a read after a `remove_memory`, or after an
`add_agentic_memory`.

**Bypasses.** A delete (G8); agentic memory's late stamp (G9); writes
and reads that name no user (G10); the timeout, a disabled barrier,
`barrier: off` and a synchronous provider (G11); a refreshed kernel
(G12).

## Complete deletion with tombstones

**Terms.** A forget of slot k for user U collects k's forms: the
`structured` value and `value_aliases` of every row of U's partition
whose `fact_key` is k, and those of k's existing tombstones
(`deletion.py:128-149`; `tombstones.py:63-82`). A row carries a form
when the matcher finds it in the row's stored content or in its
formatted text (`tombstones.py:85-102`): text casefolded, accents
stripped, `- _ . /` and whitespace collapsed, and the form bounded by
anything but an ASCII letter or digit (`matching.py:28-42`).

**Statement.** Under `forget_scope: user` (the default) with a
tombstone store, when `forget_memory(U, k)` returns success:
1. every row of U's partition that the forget's listing returned and
   that has `fact_key` k or carries a form of k is deleted, whoever
   owns it (`deletion.py:163-192`);
2. k's forms are tombstoned for U, after the listing and before the
   first delete (`deletion.py:109`, `:151-155`), unless the slot had no
   labelled value, when nothing is recorded (G14);
3. the provider's history scrub ran (`deletion.py:194-202`): Mem0
   deletes the user's stored messages that carry a form and clears the
   text of the deleted rows' history records, and of other rows'
   records that carry one (`mem0.py:966-1051`); Graphiti blanks
   episode texts, deletes entities named by a form and blanks
   summaries (`graphiti.py:488-602`); A-MEM deletes the notes whose
   derived text carries a form (`amem.py:316-387`).

From the moment the tombstone is recorded:
4. no selection (R1, R2, R3), read by id (R4) or owner listing (R5)
   returns a row of U that carries a tombstoned form. Each drops it
   with a WARNING (`selector.py:315-339`; `facade.py:515-525`,
   `:477-490`), and the listing reports its id as `withheld`;
5. every later successful add or update for U (W1, W2, W5, W6's add)
   deletes every carrier of a tombstoned form in U's partition, of any
   owner, before its barrier sequence is released, and a write whose
   own rows were all deleted is reported `suppressed`
   (`deletion.py:327-371`; `facade.py:314-332`, `:388-401`);
6. until a write or update labelled as a new statement of k, with the
   value or an alias as its `structured` value and a
   `provenance_event` that is not among k's forgotten statements,
   lifts that value's tombstone before the sweep
   (`tombstones.py:259-291`; `deletion.py:319-326`). A statement with
   no event, a replay, and an update without an event of its own lift
   nothing.

A suppressed write is stored and then deleted inside its own barrier
hold: a read accepted after it never sees it, and the guard hides it
from a read that runs during the hold. Its text has reached the
provider, and on Graphiti, A-MEM and Mem0 with `infer` the provider's
model.

**Assumptions.**
1. Writers label every statement with `fact_key`, `structured` and
   `value_aliases` (G14).
2. The matcher decides what a carrier is: a paraphrase, or a value
   only a backend's own derived text reworded, is not one (G15).
3. The provider's `list` returns every row of the partition, under
   `LIST_TOP_K` = 10,000 (`deletion.py:31`, `:54-62`; G20), its
   `delete` deletes, and a failed read raises instead of reading as a
   missing row (Mem0: `mem0.py:885-900`).
4. The tombstones persist: `memory.tombstones_path` is set. Without
   it they live in memory and a restart loses them
   (`manager.py:217-224`; G17).
5. No write runs off the queue during a forget (G13).
6. A write labelled as a restatement is the user's (G18).

**Enforced by.** `MemoryPipeline.forget` and `forget_fact`
(`facade.py:528-582`; `deletion.py:82-224`), `after_write`
(`deletion.py:281-377`), the guards (`selector.py:315-339`;
`facade.py:477-490`, `:515-525`), `TombstoneStore`
(`tombstones.py:105-291`) and each provider's `scrub_history`.

**Pinned by.**
- `memory/test_forget_and_supersession.py`:
  `test_forget_deletes_every_carrier_of_the_fact`,
  `test_forget_records_the_tombstone_before_any_delete`,
  `test_a_listing_at_its_limit_fails_the_forget`,
  `test_a_forget_that_finds_no_value_deletes_by_fact_key_only`,
  `test_a_rewrite_of_a_forgotten_value_is_swept`,
  `test_a_write_sweeps_every_carrier_in_the_partition`,
  `test_a_restatement_lifts_the_tombstone`,
  `test_a_replay_or_another_value_lifts_nothing`,
  `test_a_replay_after_a_restatement_and_a_second_forget_is_swept`,
  `test_a_statement_without_an_event_is_swept`,
  `test_only_an_update_with_its_own_event_lifts`,
  `test_a_write_whose_rows_are_all_swept_is_suppressed`,
  `test_an_update_that_carries_a_forgotten_value_is_swept`, and the
  four guards: `test_retrieval_drops_an_escaped_carrier`,
  `test_injection_drops_an_escaped_carrier`,
  `test_the_owners_listing_withholds_an_escaped_carrier`,
  `test_a_read_by_id_refuses_an_escaped_carrier`.
- `memory/test_forget_kernel.py`: the same through the kernel
  (`test_injection_leaves_out_an_escaped_carrier`,
  `test_sdk_search_leaves_out_an_escaped_carrier`,
  `test_get_memory_refuses_an_escaped_carrier`,
  `test_list_memory_withholds_an_escaped_carrier`,
  `test_a_rewrite_after_a_forget_is_suppressed`),
  `test_every_branch_answers_a_failing_tombstone_store`,
  `test_two_kernels_on_one_tombstones_file_share_a_forget`,
  `test_tombstones_path_gives_a_file_store_there`, and
  `test_a_kernel_forget_on_a_real_store` (its Graphiti case is flaky:
  known issue 47).
- `memory/test_mem0_history_scrub.py`:
  `test_scrub_removes_the_forms_from_the_users_messages_and_history`,
  `test_a_forget_keeps_the_value_out_of_mem0s_next_extraction`.
- `memory/test_graphiti_provider.py`:
  `test_the_scrub_reaches_episodes_names_and_summaries`.
- `memory/test_amem_provider.py`:
  `test_the_scrub_deletes_notes_whose_derived_text_carries_a_form`.
- `memory/test_memory_audit.py`:
  `test_the_audit_lists_every_row_the_guard_hides_from_the_agents`:
  the audit sees what the guard hides.
- `memory/test_ablation.py`:
  `test_a_writer_scoped_forget_leaves_other_agents_carriers`,
  `test_a_forget_scoped_to_none_deletes_and_records_nothing`: the
  switch.

No test runs a write concurrently with a forget.

**Bypasses.** The audit route returns carriers, by design (G2); the
listing-to-tombstone window (G13); unlabelled facts (G14); rewordings
(G15); copies outside the rows (G16); a restart without a tombstone
path, or a refreshed kernel without one (G17, G12); a writer's
restatement label (G18); a row without a `user_id`, which a read by id
returns unguarded and an update of which is not swept (G5); a
partition of 10,000 rows or more (G20); `forget_scope: writer` and
`none`. `remove_memory` is not a forget: it deletes one row, records
nothing and scrubs nothing (`facade.py:407-421`).

## Supersession

**Statement.** With `memory.supersession: exclude` (the default is
`off`: `settings.py:50`) and `supersession: on`: after an add whose
note has a `fact_key` and a `provenance_event` and which kept at least
one row of its own (`deletion.py:328-331`, `:373-376`), every other row
of that `fact_key` in the user's partition, of any owner, whose
`provenance_event` differs from the write's and that is not yet
marked, is marked `superseded_by` (the write's event) and
`superseded_session` when the write has a session
(`deletion.py:250-278`). A selection (R1, R2, R3) never returns a
marked row (`selector.py:303-313`). The marks are written inside the
write's barrier hold, so a read accepted after the write never selects
the earlier rows.

What it does not cover, by the code:
- R4 and R5 return retired rows: `read` and `list_own_report` check no
  mark (`facade.py:436-526`). The listing does so by design, so a
  forget can find them (`DELETION_AND_SUPERSESSION.md:376-377`).
- "Later" is write order, not statement order: a replay of an earlier
  statement retires the later one
  (`DELETION_AND_SUPERSESSION.md:379-384`).
- Only rows of the same `fact_key` with an event are retired; a row of
  another slot, or a conversation row, that states the old value stays
  (`DELETION_AND_SUPERSESSION.md:394-404`).
- An update retires nothing (`facade.py:397`).
- A write's own rows are the rows that carry its note's id
  (`deletion.py:336-340`), and a request may set that id
  (`facade.py:65-67`). Two statements sent with one note id are judged
  as one write.

**Assumptions.**
1. Writers name a slot the same way and give each new statement its
   own `provenance_event`.
2. Every mark is written: a mark that raises, or a listing at its
   limit, fails the write's reply after its row is stored, leaving
   earlier rows unmarked (`deletion.py:276`, `:335`;
   `facade.py:312-318`; G20).
3. Reads are ordered after the write (read-after-write, above).
   Otherwise a read during the write can select both rows.

**Enforced by.** `after_write` and `_supersede` (`deletion.py:250-377`);
the selector's `after_supersession` stage (`selector.py:303-313`);
marks dropped from a write (`facade.py:248-251`) and from an update
(`facade.py:31-36`, `:379-382`); metadata-only marks
(`chroma_inhouse.py:234-254`, `mem0.py:925-950`).

**Pinned by.**
- `memory/test_forget_and_supersession.py`:
  `test_a_later_statement_retires_the_earlier_rows_of_its_slot`,
  `test_a_mark_is_a_metadata_only_update`,
  `test_supersession_off_marks_nothing`,
  `test_retired_rows_are_never_selected_but_listed_and_forgotten`,
  `test_a_same_text_restatement_is_selected_not_its_retired_twin`,
  `test_agents_cannot_set_or_clear_a_mark`,
  `test_a_write_that_stored_nothing_retires_nothing`,
  `test_a_write_without_an_event_or_a_suppressed_one_retires_nothing`,
  `test_an_update_never_retires_other_rows`.
- `memory/test_forget_kernel.py`:
  `test_a_later_statement_reports_the_rows_it_retired`,
  `test_the_supersession_setting_reaches_the_kernels_pipeline`.
- `memory/test_ablation.py`:
  `test_without_supersession_an_earlier_statement_stays_selected`: the
  switch.

No test reads a retired row by id.

**Bypasses.** A read by id (R4), which returns a retired row with no
flag (G19); the default setting, `off`; write order (G19); a failing
mark (G20); a refreshed kernel, where two memory threads can mark one
slot at once (G12); `supersession: off`.

## The write quota

**Statement.** With `memory.write_quota.enabled` true (default false:
`quota.py:36`) and `quota: on`, every write through
`MemoryPipeline.write` (W1, W5, W6's add), before the provider is
called, is rejected when its bucket already holds a write whose text
normalizes to the same form (`duplicate`, with `dedupe` on; not
counted) or holds `max_writes` admitted writes (`quota`)
(`quota.py:93-109`; `facade.py:282-301`). A rejected write stores
nothing, returns `""`, releases its barrier sequence and says why
(`quota_rejected`). A write the provider then fails is refunded
(`facade.py:305-311`). The bucket is (the canonical user, the write's
`metadata.owner_agent`, the session), the session being the kernel
session token the request carried, else `metadata.session`, else none
(`facade.py:276-277`; `quota.py:86-91`). The kernel holds one quota
for every request (`manager.py:174-176`, `:310`), and the check and
the count are one locked step (`quota.py:100-109`).

**Assumptions.**
1. The writer's `owner_agent` is its own name, and, for writes without
   a kernel session, its `metadata.session` is the real session (G21).
2. One write is one row. A Mem0 write with `infer` can store several
   facts, and a Graphiti write one row per fact (`mem0.py:773-815`,
   `graphiti.py:265-276`), as `STRESS_DIMENSIONS.md:499-500` says:
   "the quota bounds writes, not rows" (G22).
3. The buckets survive: they live in memory and a restart, or a
   refresh, starts them again (G23).

**Enforced by.** `WriteQuota` (`quota.py:71-126`), called from
`MemoryPipeline.write` (`facade.py:282-311`).

**Pinned by.** `memory/test_write_quota.py`: the bucket key
(`test_the_quota_counts_per_user_writer_and_session`), duplicates,
refunds, `test_concurrent_writes_are_counted_once_each`,
`test_a_rejected_write_stores_nothing_and_says_why`,
`test_a_rejected_write_releases_its_barrier_sequence`,
`test_the_session_key_wins_over_the_notes_session`,
`test_the_kernel_holds_one_quota_for_every_request`,
`test_the_kernel_counts_per_kernel_session`,
`test_the_kernel_quota_is_off_by_default`; and
`memory/test_ablation.py`:
`test_without_the_quota_a_flood_is_stored_whole`,
`test_under_claim_the_quota_still_buckets_by_the_session`.

No test varies `owner_agent` or `metadata.session` to reach a new
bucket, or sends a quota through W5 or W6.

**Bypasses.** A new `owner_agent` or `metadata.session` per write, and
W5 and W6, which carry no token (G21); rows per write (G22);
`update_memory`, which the quota does not count, a restart and a
refresh (G23); `quota: off`. The flood the stress dimension measures
is benign (`STRESS_DIMENSIONS.md:658-660`); the quota is no defense
against writes made to be retrieved.

## Ablation switches

`memory.ablate` is read once at startup, an unknown key or value
fails it (`manager.py:165-168`; `ablation.py:119-135`), and
`/memory/config` reports the whole block (`launch.py:553`). A switch
left on changes behavior with no other sign; the harness's pre-flight
compares the block with the run's (`ABLATION.md:62-70`).

| Switch | What it removes | Property it voids | Code |
|---|---|---|---|
| `barrier: off` | every agent read's wait (chat, SDK read, listing, forget); stamps kept; audit and cost reads still wait | read-after-write for R1, W5 and the forget's wait; queued requests keep their order | `barrier.py:301-302`; `manager.py:184-187` |
| `identity: claim` | session binding and the canonical rules (whitespace is still stripped); the token still keys the quota | session-bound identity; the partition becomes the raw claim | `launch.py:612-622`; `manager.py:167-168`; `identity.py:58` |
| `visibility: off` | the sharing rule in selection and in a read by id; writes stay owner-only | visibility | `selector.py:286-288`; `facade.py:511` |
| `supersession: off` | marks and the exclusion | supersession | `settings.py:129-132` |
| `forget_scope: writer` | other agents' rows, the tombstone, and every scrub but of what it deleted | deletion: other agents' carriers stay, nothing is guarded or swept | `deletion.py:124-127`, `:146`, `:151`, `:195-197` |
| `forget_scope: none` | the forget's deletes and its tombstone | deletion | `deletion.py:111-123` |
| `quota: off` | the quota | the quota | `facade.py:282-283` |
| `consumer_config: honor` | the kernel's k, threshold and token budget, in favor of the consumer's; barrier, resolver, tombstones and quota kept | none of the seven | `context_injector.py:251-281` |
| `block_format`, `block_order`, `budget`, `threshold` | formatting and ranking | none of the seven | `facade.py:608-629`; `settings.py:142-146` |

## Restart and refresh

What lives only in the process's memory, and what a restart or
`/core/refresh` does to it (by reading; not executed):

| State | Where | After a restart | After `/core/refresh` |
|---|---|---|---|
| Sessions | `SessionRegistry` (`identity.py:163-167`) | gone; an old token is refused | the routes keep the first manager's registry |
| Quota buckets | `WriteQuota` (`quota.py:76-80`) | every bucket starts at 0 | a second quota; a write counts in the quota of whichever manager serves it (G12) |
| Barrier | pending set (`barrier.py:88-103`) | gone, with the writes in flight | two barriers (G12) |
| Known user ids | `MemoryManager._known_user_ids` (`manager.py:126`) | gone; no guarantee reads them: the resolver never does (`identity.py:115-140`) | two registries; unused |
| Tombstones | the file at `memory.tombstones_path` (`tombstones.py:134-143`) | kept; without a path, gone (G17) | shared through the file; without a path, two stores (G12) |
| Rows and marks | Chroma, Mem0's store, Neo4j | kept | shared, except A-MEM |
| A-MEM rows | a temporary directory per process (`AMEM_BACKEND.md:221`, `:234`) | gone, while tombstones stay | the second manager starts with empty stores |

## The audit, path by path

"holds" means the statement holds on that path; "Gn" means it holds
only under, or fails as, gap Gn says; "n/a" means the property does
not apply to the path.

| Path | Visibility | Partition | Session | Read-after-write | Deletion | Supersession | Quota |
|---|---|---|---|---|---|---|---|
| R1 chat | holds; G1, G3, G24 | holds | holds with a token; G6 | holds; G11, G12 | holds; G13, G17 | holds; G19 | n/a |
| R2 SDK search | holds; G1, G3 | holds | holds; G6 | holds; G10, G11 | holds | holds | n/a |
| R3 agentic retrieval | holds; G1, G3 | holds | holds | holds from its own submit | holds | holds | n/a |
| R4 read by id | holds; G1, G3 | G4 fails on Mem0; G5 | holds; G6 | no wait; queue order only | holds; G5 | G19: returns retired rows | n/a |
| R5 owner listing | holds (owner-only) | holds | holds; G6 | holds; G10, G11 | holds (`withheld`) | returns retired rows, by design | n/a |
| R6 audit | G2 fails | G2: any user | G2: no session | holds (always waits) | G2: returns carriers | returns retired rows | n/a |
| R7 cost | n/a (no rows) | n/a | no session | holds (always waits) | n/a | n/a | n/a |
| W1 add | G1 (owner claimed) | holds | holds; G6 | holds; G10, G11 | sweeps; G13, G20 | marks; G19, G20 | G21, G22 |
| W2 update | holds (owner-only) | G4, G5 | holds; G6 | holds; G10 | sweeps; G5 | retires nothing, by design | not counted (G23) |
| W3 remove | holds (owner-only) | G4, G5 | holds; G6 | G8 fails | not a forget | n/a | n/a |
| W4 forget | holds (ids and owners only) | holds | holds; G6 | holds: it waits for earlier writes, and later reads wait for it | G13 to G18, G20 | deletes retired rows too | n/a |
| W5 conversation turn | holds (private) | holds | G7 | holds; G11 | sweeps; G13 | none (no slot) | G21, G23 |
| W6 agentic add | G1 | holds | holds (by reading) | G9 | sweeps | as W1 | G21 |
| A1 sessions | n/a | n/a | G6 | n/a | n/a | n/a | n/a |
| A2 refresh | holds | holds | holds | G12 fails | G12 | G12 | G12 |

A3 and A4 have no row. After `/core/cleanup` the scheduler is stopped
and the memory manager unset (`launch.py:924-938`): a memory request
with a token is then refused, and one without is stamped and queued
with no thread left to serve it, so it never returns (by reading).
That is availability, not one of the seven properties. A4 is out of
scope ("What every guarantee assumes").

Three more checks:
- **Malformed metadata.** A request whose `params.metadata` is not a
  dict and whose `params.user_id` is empty fails with HTTP 500 at the
  handler's log line (`launch.py:1037-1045`). An add with such
  metadata fails at its stamp, on the event loop, before it is queued
  (`manager.py:369`). An update with it is answered `success` false
  with its sequence released (`facade.py:379-382`, `:403-405`;
  `manager.py:822-833`). With a token, an add's metadata is replaced
  by a dict first (`manager.py:421-422`). No path found queues a
  request that `address_request` would then raise on, which would
  leave it unanswered (`fifo_scheduler.py:153-156`). Holds, by
  reading.
- **Unknown and closed tokens.** Refused before anything is queued;
  under `identity: claim` not checked at all (`launch.py:612-622`).
- **Provider caches.** Mem0 caches one client per exact user id
  (`mem0.py:470-474`) but two ids can share its collection (G4); the
  in-house provider caches collections by scope
  (`chroma_inhouse.py:112-137`). Neither cache holds row text. The
  backends' own copies of text are G16.

## Documents the code contradicts

- `SHARED_MEMORY_SYSTEM.md:242-246` says each user maps to a separate
  ChromaDB collection, so "a query against Alice's collection
  physically cannot return Bob's vectors", and that any one of three
  layers is sufficient. For ids that sanitize alike, Mem0's two users
  share one collection (G4), and a read by id has only that layer. The
  section's second layer is `get_all` with a user filter and its third
  `context_injector.py` line 360; retrieval now goes through `search`
  (`mem0.py:836-870`) and the selector's partition check
  (`selector.py:259-268`), and `context_injector.py` has 298 lines.
- `RETRIEVAL_PATH.md:115-117`: "`get_memory` applies the same
  owner-or-shared rule in `address_request` (`_can_read`)". The rule
  is the same, in `MemoryPipeline.read` (`facade.py:499-526`); the
  text does not say that the read checks no partition (G5).
- `manager.py:354-355`: `stamp_syscall` includes `add_agentic_memory`
  "because this can run before `execute_request` rewrites it". Over
  `/query` it never does: `accept_memory` sends the request to
  `execute_request` unstamped (`syscall.py:153-154`), and the add is
  stamped as a sub-request (G9).
- `quota.py:2-3` calls the quota "how many rows one writer may store";
  it counts writes (`STRESS_DIMENSIONS.md:499-500` says so; G22).

## Gaps

| ID | Property | Path | Verdict | Evidence | A fix, or a narrower claim |
|---|---|---|---|---|---|
| G1 | Visibility; quota | every `/query` request (`agent_name`); W1, W6 (`owner_agent`) | holds under assumption: agents name themselves truthfully; does not hold against a client that names another agent | `launch.py:134-146`; `facade.py:258-259`; `test_add_memory_keeps_an_explicit_owner`; an empty agent name owns ownerless rows in selection (`visibility.py:49-53`) and matches rows with no `user_id` when it names no user (`selector.py:192`, `:262-264`) | bind the agent as a session binds the user (a token per agent), and set `owner_agent` to the writer on every add; or claim visibility "between agents that name themselves truthfully" |
| G2 | Visibility; partition; session; deletion; supersession | R6 | does not hold, by design: any caller lists any user's rows of every agent, carriers and retired rows included, with no session | `launch.py:671-688`; `manager.py:937-957`; `test_the_audit_lists_every_row_the_guard_hides_from_the_agents` | serve the route only when a benchmark flag is set, or only to a local harness; or claim the properties "for the SDK's operations" |
| G3 | Visibility | R1 to R4 on Graphiti | holds under assumption: a row's text comes from its own write; Graphiti does not meet it, by design | each extraction reads the group's ten latest episodes of its source type, of any agent (`GRAPHITI_BACKEND.md:66-69`); a restated fact keeps the first write's sentence (`:123-127`); not measured | claim row-level visibility only; measure whether a private value reaches a shared Graphiti row (the trial-level exposure of known issue 43, on Graphiti cells) |
| G4 | Partition | R4, W2, W3 on Mem0 | does not hold for user ids that differ only in characters the collection name replaces | a short id keeps its sanitized name with no digest (`mem0.py:359-443`; `test_ids_that_fit_keep_their_name`); `alice.smith`, `alice_smith`, `alice smith` and `alice@smith` all give `mem0_memories_alice_smith` (replica of `mem0.py:373-377`, run in the scratch directory); Mem0 2.0.2's `Memory.get` reads by id alone (installed `mem0/memory/main.py:973-995`); `get` is not re-checked (`facade.py:499-526`); no test | re-check `found.metadata["user_id"]` against the scope in `MemoryPipeline.locate` (every provider at once); and digest every Mem0 collection name (renames existing collections: a migration or fresh stores, known issue 36) |
| G5 | Partition; deletion | R4, W2, W3 | holds under assumption: a provider's `get` stays in scope, every row has a `user_id`, and no user is called `default` | with no user named, `locate` tries the agent's scope, then the provider default (`facade.py:343-348`); a row with no `user_id` is read with no tombstone guard (`facade.py:515-516`) and updated with no sweep (`:383-389`); the fallback is pinned by `test_lookup_without_user_id_tries_agent_scope_then_default` | the same re-check as G4, failing closed on a missing `user_id` |
| G6 | Session | every request without a token; A1 | holds for requests that carry a token; it binds, it does not authenticate | `manager.py:408-409`, `:446-447`; `launch.py:584-599`; `STRESS_DIMENSIONS.md:539-543` | claim "a request the deployment runs in a session is served for the session's user", not "an agent cannot act for another user" |
| G7 | Session | W5 with `auto_inject` off and `auto_extract` on | holds under assumption: injection on. Otherwise the turn is filed under the agent's name, not the session's user (no other user's partition) | the turn takes the injection's `resolved_user_id` (`syscall.py:875-886`), which the disabled injector reports as None (`context_injector.py:115-135`); then `facade.py:98-99`; v2 kernel runs set `auto_extract` off (`BENCHMARK_V2.md:944-948`) | pass the chat's bound user to `extract_async` directly |
| G8 | Read-after-write | W3, then R1 | does not hold for deletes: a chat accepted after a delete was accepted can read the row while the delete waits in the queue | `stamp_syscall` has no `remove_memory` branch (`manager.py:368-387`); `facade.py:407-421`; no test. v2 kernel revokes call the forget, which is stamped (`ABLATION.md:88-92`) | stamp `remove_memory` like a write; or claim read-after-write for writes, updates and forgets |
| G9 | Read-after-write; quota | W6 | holds with a narrower "accepted": when its final add is submitted, after two model calls | `syscall.py:153-154`, `:916-932`; `manager.py:368` is never reached through `/query`; sub-requests are submitted without the token (`syscall.py:921`, `:932`; `:87-110`); no test of W6 over `/query` | stamp at acceptance and pass the token to the sub-requests; or leave `add_agentic_memory` out of the claim |
| G10 | Read-after-write | W1, W2, R2, R5 naming no user | not covered, by design: the agent's own scope is not stamped | `manager.py:368-387`; a sequence of 0 acquires nothing (`facade.py:271-274`, `:367-371`) | claim it "for requests that name the user" |
| G11 | Read-after-write; deletion and supersession for reads during a write | R1, R2, R5, the forget's wait | holds under assumption: each earlier write commits within `timeout_ms`, the barrier is enabled, `barrier: on`, and the provider is not synchronous | fails open after the timeout (`barrier.py:340-359`); default 5,000 ms (`:85-86`); 3 of 90 kernel Mem0 conversation writes took longer than 5 s in the pilot (`BENCHMARK_V2.md:636-640`); bypasses at `barrier.py:124-125`, `:301-302`, `selector.py:94-99`; Mem0's 10 s readability wait (`mem0.py:758-771`) | claim "unless the wait times out", and report every `TIMEOUT` (the diagnostics carry `barrier_waits`) |
| G12 | Read-after-write; deletion; supersession; quota | A2 | does not hold after a refresh, until a restart (by reading; not executed; no test) | `restart_kernel` assigns `active_components` as a local (`launch.py:425-445`), so the routes keep the first manager, while `initialize_components` points the shared executor's injector, extractor and stamping at a second one (`launch.py:358-376`) and starts a second scheduler (`:403`) on the same global queues (`aios/hooks/stores/_global.py:23`). Two memory threads then serve queued requests at once; a write stamped on the second barrier and served by the first is released on the first; chat snapshots come from the first barrier and are waited on against the second; two quotas; without a tombstone path, two tombstone stores; on A-MEM the second provider starts empty | declare `global active_components` and stop the old scheduler, or refuse `/core/refresh` while memory is served; or claim the properties "for a kernel not refreshed since startup" |
| G13 | Deletion | W4 with W5, or after A2 | holds under assumption: no off-queue write during a forget. A write that commits between the forget's listing and its tombstone is neither deleted nor swept; the guard still hides it, and the store and the audit keep it | `deletion.py:109`, `:151-155`, `:163`; `DELETION_AND_SUPERSESSION.md:179-183`, `:648-650`; in the kernel only W5 runs off the queue, and v2 kernel runs turn it off (`BENCHMARK_V2.md:944-948`); no test | list the partition again after recording the tombstone and delete what the second listing adds |
| G14 | Deletion | W4 | holds under assumption: writers label each statement | forms come only from the slot's `structured` rows and its tombstones (`deletion.py:134-149`); with none, no tombstone and deletes by `fact_key` only (`:151-155`; `DELETION_AND_SUPERSESSION.md:196-202`) | claim "the fact as its writers labelled it" |
| G15 | Deletion | W4 and every sweep | holds under assumption: the matcher defines a carrier | lexical matching (`matching.py:28-59`); paraphrases survive (`DELETION_AND_SUPERSESSION.md:637`); Graphiti facts extracted with forgotten text in their context and no form in their sentence survive (`GRAPHITI_BACKEND.md:276-277`) | as stated: "no row whose text carries the value or an alias" |
| G16 | Deletion, in the store | the store's files | holds for reads through the kernel; the files keep text | Chroma's write-ahead log kept every deleted row's ADD record (kernel Mem0 111 of 111, kernel in-house 65 of 65, measured 2026-11-10: `DELETION_AND_SUPERSESSION.md:638-645`); Mem0 history records of rows deleted earlier by `remove_memory` keep their text (`:651-654`); Neo4j's own logs not checked; the tombstone file holds every forgotten value and alias in plain text, by design (`tombstones.py:113-124`, `:211-217`) | claim "no read through the kernel returns it"; do not claim erasure from disk |
| G17 | Deletion | any restart; A2 | does not hold across a restart without `memory.tombstones_path` | in-memory store (`manager.py:217-224`; `tombstones.py:134-143`); the v2 pre-flight refuses a kernel without a path (`BENCHMARK_V2.md:541-542`) | refuse to start without a path when `forget_memory` is served; or claim it "with a tombstone path" |
| G18 | Deletion | W1, W2 | holds under assumption: a write labelled as a new statement is the user's | any agent's write with the slot, the value and an unseen event lifts the tombstone for all (`tombstones.py:259-291`; `DELETION_AND_SUPERSESSION.md:235-242`) | claim "until a write labelled as the user's restatement" |
| G19 | Supersession | R4, R5; the setting; write order | holds as narrowed: selection only, with `exclude`, in write order, by slot | `read` and the listing check no mark (`facade.py:436-526`); default `off` (`settings.py:50`); replays win (`DELETION_AND_SUPERSESSION.md:379-384`); own rows by a request-settable note id (`deletion.py:336-340`; `facade.py:65-67`); no test reads a retired row by id | hide or flag retired rows in `get_memory`; claim "never selected" |
| G20 | Deletion; supersession | W1, W2, W4 for a partition of 10,000 rows or more | holds under assumption: partitions under `LIST_TOP_K` | a listing at the limit raises (`deletion.py:54-62`): the forget fails cleanly (`test_a_listing_at_its_limit_fails_the_forget`), but a write's `after_write` raises after its row is stored, so its reply fails with no sweep and no marks (`facade.py:312-318`) | page the listing; or claim the bound |
| G21 | Quota | W1 with a varied `owner_agent` or `metadata.session`; W5; W6 | does not hold against a writer that varies its claims; W5 and W6 always count by `metadata.session` | the bucket is the claimed owner and, without a token, the claimed session (`facade.py:276-277`, `:282-287`; `quota.py:86-91`); the extractor's syscall has no token (`conversation_extractor.py:131-145`); no test | key the bucket on the bound agent and the kernel session, and carry the token into W5 and W6 |
| G22 | Quota | W1 on Mem0 with `infer`, on Graphiti | holds as narrowed: writes, not rows | `mem0.py:773-815`; `graphiti.py:265-276`; `STRESS_DIMENSIONS.md:499-500` | claim "`max_writes` writes per bucket" |
| G23 | Quota | W2; W5; a restart | holds as narrowed | updates are not counted (`facade.py:351-405`); buckets live in memory (`quota.py:76-80`); a quota-rejected or suppressed turn is logged as stored, since the extractor checks only `success` (`conversation_extractor.py:162-176`) | claim "adds, per process"; log a rejected turn as rejected |
| G24 | Visibility | R1's diagnostics; W1, W2, W4 replies | holds for row text; counts and ids of other agents' rows are disclosed, by design | `own_fetched`, `shared_fetched` and `after_partition` are counted before visibility (`selector.py:256-268`) and reach the chat caller (`syscall.py:856-862`); `swept`, `retired` and a forget's `deleted` name other agents' ids and owners (`deletion.py:176-181`, `:351-354`) | claim visibility "of row text and metadata", or drop the pre-visibility counts from replies |

## Open decisions

1. **Agent identity.** Bears on visibility and the quota (G1, G21).
   Options: (a) keep the code and claim both "for agents that name
   themselves truthfully"; (b) bind each agent to a token as sessions
   bind the user, and set `owner_agent` to the writer on every add,
   which changes what `test_add_memory_keeps_an_explicit_owner` pins;
   (c) for the quota alone, carry the kernel token into W5 and W6 and
   key the bucket on the bound agent.
2. **Reads by id.** Bears on the user partition (G4, G5). Options: (a)
   re-check the row's `user_id` in `MemoryPipeline.locate`, failing
   closed; (b) also digest every Mem0 collection name, which renames
   existing collections; (c) narrow the claim to selections and
   listings.
3. **Deletes and agentic writes under the barrier.** Bears on
   read-after-write (G8, G9). Options: (a) stamp `remove_memory` like
   a write and stamp `add_agentic_memory` at acceptance; (b) narrow
   the claim to `add_memory`, `update_memory` and `forget_memory`;
   (c) leave `add_agentic_memory` out of the paper (no test exercises
   it over `/query`, and its evolution step never updates a row).
4. **Graphiti's derived text.** Bears on visibility (G3). Options: (a)
   claim row-level visibility and say Graphiti's rows can carry text
   from other writes; (b) measure trial-level exposure of private
   values on the Graphiti cells before claiming more; (c) a Graphiti
   group per user and writer, which changes the partition design and
   Graphiti's consolidation.
5. **`/core/refresh`.** Bears on every cross-agent property (G12).
   Options: (a) fix `restart_kernel` (the global and the old
   scheduler); (b) refuse the route while memory is served; (c) state
   that the guarantees hold for a kernel not refreshed since startup.
6. **The audit and cost routes.** Bear on visibility, the partition
   and deletion (G2). Options: (a) keep them open, local and
   harness-only, and say so; (b) serve them only under a benchmark
   flag.
7. **The forget's window.** Bears on deletion (G13). Options: (a) a
   second listing after the tombstone; (b) keep the documented window,
   which needs an off-queue write (none in v2 kernel runs).
8. **Retired rows read by id.** Bears on supersession (G19). Options:
   (a) hide them in `get_memory`; (b) flag them in the reply; (c)
   keep the claim to selection.
9. **What session binding defends against.** Bears on how the paper
   states session-bound identity (G6). Options: (a) the stress
   dimension's framing, an agent that mis-tags the user inside a
   session the deployment opened; (b) a claim against a hostile agent,
   which would need sessions opened only by the deployment and a token
   on every request.
10. **Tombstones without a path.** Bears on deletion across restarts
    (G17). Options: (a) refuse to start without `tombstones_path`;
    (b) keep the v2 pre-flight as the only check and claim deletion
    "with a tombstone path".

Open: whether any pair of user ids in the v2 datasets sanitize to one
Mem0 collection name (G4) was not checked, and none of the gaps was
reproduced by running code.
