# Memory guarantees and their audit

What the kernel's memory guarantees, stated as the code at `d49afc9`
(branch `feature/NeurIPS-2027-changes`) enforces them, and an
adversarial audit of every path that reads or writes memory. For each
property the paper would claim: a precise statement, its assumptions,
the code that enforces it, the tests that pin it, and the paths that
could bypass it. The audit then gives a verdict for each property on
each path, and the gaps found close the file. Written 2026-11-20 and
revised the same day after a review. It reports gaps and fixes none:
no code or test was changed.

## How to read this file

**Method.** Every module of `aios/memory/` (the manager, the pipeline
library, the injector, the extractor, the providers), `aios/syscall/`,
`runtime/launch.py`, the scheduler's memory thread,
`aios/utils/request_pool.py` and the tests under `tests/modules/memory/`
and `tests/modules/syscall/` were read at `d49afc9`. `aios/storage/`
and `aios/tool/` were read to rule them in or out as paths to memory:
both are paths (S1, T1). Nothing was executed: no kernel, provider,
model or test. A test named below was read, not run, and what it would
catch is taken from its text: its name says it, or a phrase after a
colon does. A test marked as needing Ollama, Neo4j or A-MEM is skipped
where the service is missing, and pins nothing there. One computation
was run, twice: a standard-library replica of the Mem0 provider's
collection-name sanitizer (`mem0.py:370-390`; gap G4), with
`python3 -I`, importing only `re`.

**Verdicts.** "Holds": on that path the code enforces the statement,
given the common assumptions below. "Holds under assumption": it also
needs the assumption the gap names. "Does not hold": the code allows a
path that violates the statement. A verdict may be split by path or
case, each part one of the three; the audit table also uses "n/a"
where a property does not apply. Every verdict is by reading; not
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
`runtime/launch.py`; `fifo_scheduler.py` and `rr_scheduler.py` are in
`aios/scheduler/`; `lsfs.py` is `aios/storage/filesystem/lsfs.py`.
"Installed" means the copy in the AIOS `.venv`'s `site-packages`. A
test is named `file::test`, its file under `tests/modules/`.

## What every guarantee assumes

**Trusted.**
- The kernel process and its configuration as read at startup. This
  audit did not open `config.yaml`. The values a v2 run uses are known
  only from the pre-flight's requirements (`BENCHMARK_V2.md:528-545`):
  `write_barrier.timeout_ms` at least 60,000, `auto_extract` off,
  `supersession: exclude` (or off under its control), a
  `tombstones_path`.
- The provider contract (`PROVIDER_CONTRACT.md:19-29`, `:58-70`): a
  provider stores and returns the metadata `note_metadata` keeps
  (scalars and non-empty lists; `None`, empty lists and nested dicts
  are dropped, `base.py:71-89`, so a label sent as a JSON object is
  lost), and Mem0 replaces `created_at` (`PROVIDER_CONTRACT.md:64-65`);
  `search`, `list` and `get` stay in the named user's scope; `delete`
  deletes. Where a provider falls short, a gap names it.
- Two things the contract does not say (`PROVIDER_CONTRACT.md` has no
  word on threads or concurrency). A provider is safe under concurrent
  calls: R1 and R6 call it from request-pool threads and W5 from a
  daemon thread while the memory thread serves the queue
  (`launch.py:684`, `:1015`; `conversation_extractor.py:97-102`). A
  row can be searched and listed once `add` returns (read-after-write,
  assumption 2).
- One kernel process serves a store at a time. The barrier, the quota
  and the sessions live in the process (`manager.py:171-187`), while
  the stores persist across runs (DEV_STATUS known issue 36). Two
  kernels on one store share its rows and, with one `tombstones_path`,
  its tombstones (`memory/test_forget_kernel.py`:
  `test_two_kernels_on_one_tombstones_file_share_a_forget`), but no
  barrier, quota or session.
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
  own clients reach the kernel's port, that agents use only the SDK's
  memory and chat calls, and that no client's storage or tool request
  touches the stores' files or the kernel's objects (S1, T1; G25).
- The clock. No guarantee reads the wall clock. The barrier's timeout
  runs on the monotonic clock (`barrier.py:314`, `:340`);
  `committed_at` and `fetch_started_at` are diagnostics.

**Out of scope.**
- An agent that reaches a backend directly: a Chroma directory, Neo4j,
  Mem0's files. Agents started by `/agents/submit` run in the kernel's
  own process (`aios/hooks/modules/agent.py:18-60`). Their requests go
  over HTTP like any agent's (the in-process hook is commented out,
  `:58`), but nothing stops their code from importing kernel modules.
  The kernel's own storage and tool routes reach the same files and
  run code in the same process; they are in scope, as S1 and T1.
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
| W6 | `add_agentic_memory`: an analysis model call, R3, an evolution model call, then an `add_memory` (no `update_memory` is ever built; when evolution fails early the request fails with HTTP 500 and no add: "Session-bound identity", Bypasses) | `syscall.py:153-154`, `:407-731`, `:916-932` | a request-pool thread, then the memory thread |
| A1 | `POST /session/open`, `POST /session/close` | `launch.py:584-609`; `identity.py:152-196` | the event loop |
| A2 | `POST /core/refresh`, and `POST /core/config/update`, which calls it (`launch.py:1108`) | `launch.py:425-445`, `:498-516` | the event loop |
| A3 | `POST /core/cleanup` | `launch.py:919-952` | the event loop |
| A4 | `POST /agents/submit` | `launch.py:828-870`; `aios/hooks/modules/agent.py:18-60` | a factory thread |
| S1 | Storage: `POST /query`, `storage`, any `operation_type` (`StorageQuery.operation_type` is a free string: installed Cerebrum `cerebrum/storage/apis.py:35`); and `llm` with action `operate_file`, whose model call names the storage operation and its parameters | `launch.py:1023-1028`; `syscall.py:341-381`, `:911-912`, `:962-963`; `aios/storage/storage.py:20-21`; `lsfs.py:189-269` | the scheduler's storage thread (`fifo_scheduler.py:277-297`), while the handler waits on the event loop |
| T1 | Tools: `POST /query`, `tool`; and `llm` with action `call_tool`, whose model call names the tools | `launch.py:1029-1034`; `syscall.py:897-909`, `:913-914`; `aios/tool/manager.py:85-118` | the scheduler's tool thread (`fifo_scheduler.py:303-325`), while the handler waits on the event loop |

**Storage and tools.** Neither route goes through the memory library:
no module under `aios/storage/`, `aios/tool/`, `aios/llm_core/`,
`aios/context/` or `aios/terminal/` names `aios.memory`,
`MemoryManager`, `mem0` or a tombstone (grep at `d49afc9`). Both are
still paths to memory, through the kernel's own permissions, with no
session check (`launch.py:1023-1034`). LSFS writes or creates a file
at any path a request names: an absolute path is kept, and a relative
one is joined to its root (`root` unless configured: `launch.py:217`),
so `..` escapes it (`lsfs.py:271-279`, `:319-331`). With a Redis
server answering at startup (`lsfs.py:43-58`), `share` reads any file
the kernel can read and puts its bytes to `https://transfer.sh/`,
returning the link (`lsfs.py:393-447`, `:449-476`). `/memory/config`
names the tombstone file and Mem0's history file
(`launch.py:566-568`). A tool call runs code the tool hub serves by
name, in the kernel's process (`aios/tool/manager.py:98-101`,
`:116-118`; installed Cerebrum `cerebrum/interface/__init__.py:33-55`).
Gap G25 says what follows. Whether Redis runs in the deployment was
not checked.

**Not paths to memory.** LLM actions other than the two chat actions
inject nothing (`syscall.py:893-912`). The agentic path's own model
calls go to `execute_llm_syscall` directly (`syscall.py:489`, `:680`),
so they are neither injected nor stored. The only provider call
outside the library is the audit's `list` (`manager.py:952`);
`MemoryManager._locate_memory` and `_fetch_candidates`
(`manager.py:506-526`) have no caller in `aios/` or `runtime/`.

**One memory thread.** The scheduler serves queued memory requests one
at a time, in queue order (`fifo_scheduler.py:266-273`, and the same in
`rr_scheduler.py:199-206`), and `/query` stamps and queues them in
arrival order on the event loop (`launch.py:1062-1064`). Two kinds are
stamped and queued on a request-pool thread instead, by `_submit`
(`syscall.py:87-126`): W6's sub-requests (`syscall.py:916-932`), and a
retry. The waiting thread resubmits any request whose syscall is not
marked done when its thread ends (`syscall.py:199-211`), and the
scheduler sets the syscall's event, which ends that thread
(`aios/syscall/__init__.py:340-354`), before it marks it done
(`fifo_scheduler.py:141-142`; `rr_scheduler.py:98-99`), so one request
can be served twice (G26). No lock covers a stamp and its enqueue
together (`syscall.py:113`, `:123`), so a read accepted on the loop can
be queued between them (G27). Off the queue run R1, R6, R7 and W5.
Every race below needs one of them, a pool-thread submit, or the second
memory thread of gap G12.

## Visibility

**Statement.** For a request made under agent name A, a row whose
stored `owner_agent` is not A is returned only when its stored
`sharing_policy` is exactly `"shared"`. This holds for every selection
(R1, R2, R3) and for a read by id (R4). The owner listing (R5) returns
only A's own rows, and an update or delete by id (W2, W3) changes only
A's own rows. A read by id answers another agent's private row with
the same "Memory not found" as a missing one (`manager.py:699-705`);
an update or a delete answers so for any row A does not own, shared or
not (`:834-835`, `:894-895`). An SDK `sharing_policy` other than
`"shared"` narrows the rule further (`selector.py:272`). A row with a
missing or empty `owner_agent` is no named agent's own: it is returned
only if shared, except to a request whose agent name is the empty
string, which selection takes for the owner of both
(`visibility.py:49-53`) and a read by id for the owner of an empty one
(`:121-123`). Every write through the library names its agent as owner
(`facade.py:258-259`), so an empty `owner_agent` comes from an agent
named the empty string, which `QueryRequest` accepts (`launch.py:135`),
and a missing one only from outside the library.

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

**Pinned by.**
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
  `test_provider_never_filters_by_visibility` (its dict in-house case
  always runs; the Chroma in-house and Mem0 cases need Ollama, the
  Graphiti case also Neo4j, the A-MEM case also A-MEM),
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
- `memory/test_amem_provider.py`: `test_rows_carry_no_derived_text`
  (the file needs Ollama and A-MEM: `test_amem_provider.py:13`).
- `memory/test_ablation.py`:
  `test_without_visibility_another_agents_private_row_is_selected`,
  `test_without_visibility_writes_stay_owner_only`: the switch.

No test writes a Graphiti row whose text came from another agent's
private write.

**Bypasses.** A client that sends another agent's name (G1); the
audit route, which returns every agent's rows (G2); Graphiti's derived
text (G3); counts and ids in diagnostics and replies, which the
statement does not cover (G24); the storage and tool routes, which
can read the stores' files (G25); `visibility: off`; an agent in the
kernel's process.

## User partition

**Statement.** A request is served for one scope S: its user id in
canonical form (`identity.py:54-65`; the session's user when a token
is honored), or the agent's own name, as sent, when it names no user
or names the agent itself (`identity.py:115-140`, `selector.py:189-192`;
`facade.py:344`, `:467`).
- A selection (R1, R2, R3) returns only rows whose stored `user_id` is
  S exactly, failing closed on a missing one (`selector.py:259-268`).
- The owner listing (R5) does the same (`facade.py:472-476`); the
  forget, the sweep and supersession act only on such rows
  (`deletion.py:54-66`).
- A write is filed under its `metadata.user_id` in canonical form,
  else under the agent's name in canonical form (`facade.py:252-255`;
  the add branch passes no other user, `manager.py:651-652`; a W5
  turn's `metadata.user_id` is canonicalized at its stamp,
  `manager.py:367`, `:477-491`). The rules strip surrounding
  whitespace always, and with `memory.identity` set may casefold or
  drop a listed email domain (`identity.py:54-65`). Where they change
  an agent's name, its no-user rows are filed in a scope its no-user
  reads, scoped to the name as sent, never search. Whether any agent's
  name changes under the kernel's rules was not checked.
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
   does not meet it for ids whose collection names coincide, among
   them every id with no ASCII letter or digit, which gets the default
   scope's collection (G4).
3. Every row carries its `user_id`; no agent is named the empty
   string, whose writes that name no user are stored with an empty
   `user_id` in the provider's default scope (`facade.py:252-255`;
   `base.py:84-89`; `chroma_inhouse.py:109-110`, `:158`); and no real
   user's id is the provider's default scope, `"default"`, or on Mem0
   an id with no ASCII letter or digit (G4, G5).

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
  only, not `get` (its dict in-house case always runs; the other
  providers' cases need Ollama, and Neo4j or A-MEM).
- `memory/test_identity_rules.py`:
  `test_kernel_stores_a_v2_writer_under_the_canonical_id`,
  `test_kernel_serves_a_v2_consumer_the_canonical_partition`.
- `memory/test_graphiti_provider.py`:
  `test_groups_are_valid_and_one_per_user` (the file needs Ollama and
  Neo4j: `test_graphiti_provider.py:17`);
  `memory/test_amem_provider.py`:
  `test_each_user_has_a_store_of_their_own` (Ollama and A-MEM).
- Three tests pin behavior a gap rests on:
  `memory/test_mem0_collection_names.py`:
  `test_ids_that_fit_keep_their_name` (G4);
  `memory/test_conversation_write_path.py`:
  `test_lookup_without_user_id_tries_agent_scope_then_default`, the
  fallback to the default scope, and
  `test_update_routes_to_the_collection_the_memory_was_found_in`: an
  update that names no user, whose row is found with the stored
  `user_id` `"alice"`, goes to alice's collection, not to S
  (`test_conversation_write_path.py:349-361`) (G5).

No other test this audit found reads, updates or deletes by id across
users, with or without a named user.

**Bypasses.** Mem0 ids that share a collection (G4); a read by id of a
row with no `user_id` or in the default scope (G5); the audit route,
which serves any user named in its query string (G2); without a
session, any claim (G6); the storage and tool routes, which can read
the stores' files (G25); `identity: claim`, which serves the raw
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
  (`syscall.py:875-889`), when injection is on and returns without
  raising (G7).
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
conversation turn when injection is off or raised (G7); the storage
and tool routes, which take no token (G25); `identity: claim`
(`launch.py:612-622`).

The agentic path is bound only in part. Its final add is bound,
through `metadata.user_id` (`manager.py:420-425`). Its R3 is bound only
when the request names `params.user_id`, which the SDK's
`create_agentic_memory` never sends (installed Cerebrum
`cerebrum/memory/apis.py:155-158`), so R3 runs in the agent's own scope
(`manager.py:763-773`; `selector.py:189-192`; G9). R3's rows reach no
agent and no model: the evolution step iterates R3's result dict as if
it held notes and swallows the error (`syscall.py:565-571`). The
evolution step builds no `update_memory`. With `should_evolve` "true",
its loop calls `range()` on `new_context_neighborhood`, which the
response schema makes a list (`syscall.py:630-638`), so it raises at
`syscall.py:721` and returns the empty list set just before (`:719`,
`:726-731`); otherwise it returns an empty list (`:710`, `:715`,
`:724`). When the step fails before `:719` (for example, a reply that
parses to a JSON array fails at `:717`), it returns R3's result dict
instead. `syscall.py:927` then iterates the dict's keys, and
`MemoryQuery()` at `:928` raises a validation error, since
`operation_type` is required (installed Cerebrum
`cerebrum/memory/apis.py:48`; pydantic 2.13.2): the request fails with
HTTP 500 (`launch.py:1071-1072`) and its add is never submitted.

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
(`facade.py:329-332`). So a read of U that waits sees every stamped
write of U accepted before it, whichever agent wrote it, unless its
wait timed out. A write whose provider call failed is released too and
stored nothing. A write whose `after_write` raised is released and
answered `success` false, but its row is stored and a read accepted
after it can see it (`facade.py:302-318`; G20). Which writes are
stamped and which reads wait is listed below.

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
  (G9); it is stamped and queued on a request-pool thread, where a
  read accepted between the two steps overtakes it (G27);
- a retry: when the executor resubmits it, on a request-pool thread
  (`syscall.py:199-211`; G26, G27).

Writes that are stamped (`manager.py:368-379`): an add naming
`metadata.user_id`; an update naming `params.user_id` or
`metadata.user_id`; a forget naming `params.user_id`; every
conversation turn. Not stamped: `remove_memory` (G8); an add or update
that names no user (G10).

Reads that wait: R1; R2, R3 and R5 naming `params.user_id`
(`manager.py:380-387`), which an R3 sent through the SDK never does
(G9); a forget, for the writes through its own sequence − 1
(`facade.py:566-567`); R6 and R7, for every write accepted before
them, even under `barrier: off` (`manager.py:340-345`, `:950`), within
the same bounds as the others: the timeout, a disabled barrier and a
synchronous provider (G11). Reads that do not wait: R4, which takes no
snapshot, and R2, R3 or R5 naming no user (G10). Among requests
accepted on the event loop the order holds without the barrier, since
one thread serves them in queue order ("The paths"); a request stamped
on a pool thread can be overtaken (G27). The barrier is what orders
R1, W5, R6 and R7 (as `ABLATION.md:113` says of `barrier: off`).

**Assumptions.**
1. Every write accepted before the read commits within `timeout_ms`;
   otherwise the read proceeds without it (G11). The default is
   5,000 ms (`barrier.py:85-86`); v2 kernel runs set at least 60,000
   (`BENCHMARK_V2.md:534`). In the pilot, 3 of 90 kernel Mem0
   conversation writes took longer than 5 s (`BENCHMARK_V2.md:636-640`).
2. A row is visible to `search` and `list` once `add` returns. This is
   the kernel's assumption, not the contract's, whose commit-timing
   rule speaks only of durability (`PROVIDER_CONTRACT.md:50-56`).
   Mem0's `add` waits until each new row reads back by id, up to 10 s,
   and then returns with a WARNING (`mem0.py:758-771`, `:813-815`).
   The Chroma in-house `add` returns after its Chroma call, with no
   such wait (`chroma_inhouse.py:154-168`); whether Chroma, Graphiti
   and A-MEM make a row searchable by then was not verified.
3. The barrier is enabled (`write_barrier.enabled`, default true:
   `barrier.py:83`), `barrier: on`, and the provider does not commit
   synchronously. Only the in-memory test provider does
   (`in_house.py:37`); with it the kernel wires no injector, extractor
   or stamping (`launch.py:35`, `:352-389`), so every read and write
   goes through the memory thread, except R6 and R7, which then do not
   wait for queued writes.
4. One kernel per process: no `/core/refresh` since startup (G12).
5. Each accepted request is served once (G26), and no read is
   accepted between a pool-thread write's stamp and its enqueue (G27).

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
`add_agentic_memory`. No test serves a request twice, or queues a read
between a pool-thread write's stamp and its enqueue.

**Bypasses.** A delete (G8); agentic memory's late stamp and its R3
(G9); writes and reads that name no user (G10); the timeout, a
disabled barrier, `barrier: off` and a synchronous provider (G11); a
refreshed kernel (G12); a pool-thread submit that a read overtakes,
which then stalls every memory request until its timeout (G27).

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
5. every later add or update for U (W1, W2, W5, W6's add) whose
   provider call and `after_write` complete (G20) deletes every
   carrier of a tombstoned form in U's partition, of any owner, before
   its barrier sequence is released, and a write whose own rows were
   all deleted is reported `suppressed` (`deletion.py:327-371`;
   `facade.py:314-332`, `:388-401`);
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
7. Every carrier of U's fact is filed in U's partition: the statement
   covers rows of U only, and a carrier filed elsewhere is beyond the
   forget, the sweeps and the guards (G28).

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
  `test_a_kernel_forget_on_a_real_store` (it needs Ollama, its Graphiti
  case also Neo4j: `test_forget_kernel.py:937-940`; that case is
  flaky: known issue 47).
- `memory/test_mem0_history_scrub.py`:
  `test_scrub_removes_the_forms_from_the_users_messages_and_history`,
  `test_a_forget_keeps_the_value_out_of_mem0s_next_extraction` (needs
  Ollama: `test_mem0_history_scrub.py:606`).
- `memory/test_graphiti_provider.py`:
  `test_the_scrub_reaches_episodes_names_and_summaries` (Ollama and
  Neo4j).
- `memory/test_amem_provider.py`:
  `test_the_scrub_deletes_notes_whose_derived_text_carries_a_form`
  (Ollama and A-MEM).
- `memory/test_memory_audit.py`:
  `test_the_audit_lists_every_row_the_guard_hides_from_the_agents`:
  the audit sees what the guard hides.
- `memory/test_ablation.py`:
  `test_a_writer_scoped_forget_leaves_other_agents_carriers`,
  `test_a_forget_scoped_to_none_deletes_and_records_nothing`: the
  switch.

No test commits a write between a forget's listing and its tombstone
(G13).

**Bypasses.** The audit route returns carriers, by design (G2); the
listing-to-tombstone window (G13); unlabelled facts (G14); rewordings
(G15); copies outside the rows (G16); a restart without a tombstone
path, or a refreshed kernel without one (G17, G12); a writer's
restatement label (G18); a row without a `user_id`, which a read by id
returns unguarded and an update of which is not swept (G5); a write
whose `after_write` raised, stored and not swept, among them a write
that lists a partition of 10,000 rows or more (G20); a carrier
of U's fact filed outside U's partition, by a write that named no user
or another user, or by the conversation turn of G7, which no forget,
sweep or guard of U reaches (G28); the storage and tool routes, which
can truncate the tombstone file or upload the stores' files (G25);
`forget_scope: writer` and `none`. `remove_memory` is not a forget: it
deletes one row, records nothing and scrubs nothing
(`facade.py:407-421`).

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
  mark (`facade.py:436-526`). The owner listing does so by design, so
  a writer's revoke finds its own retired rows (`facade.py:445-447`).
  A forget does not use it: it lists the partition itself
  (`deletion.py:54-66`, `:109`), which also returns retired rows, so
  "a forget finds and deletes them too"
  (`DELETION_AND_SUPERSESSION.md:376-377`).
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
(`facade.py:276-277`; `quota.py:86-91`). A retry carries no token
(G26), and under `identity: claim` the token is not checked (G21). The
kernel holds one quota for every request (`manager.py:174-176`,
`:310`), and the check and the count are one locked step
(`quota.py:100-109`).

**Assumptions.**
1. The writer's `owner_agent` is its own name; for writes without a
   kernel session, its `metadata.session` is the real session; and
   under `identity: claim`, its token is its session's (G21).
2. One write is one row. A Mem0 write with `infer` can store several
   facts, and a Graphiti write one row per fact (`mem0.py:773-815`,
   `graphiti.py:265-276`), as `STRESS_DIMENSIONS.md:499-500` says:
   "the quota bounds writes, not rows" (G22).
3. The buckets survive: they live in memory and a restart, or a
   refresh, starts them again (G23).
4. Each accepted write is served once (G26).

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

`test_the_quota_counts_per_user_writer_and_session`
(`test_write_quota.py:68-77`) and
`test_a_rejected_write_stores_nothing_and_says_why` (`:182-202`) pin
that a new `metadata.session`, or another `owner_agent`, gets a bucket
of its own: the bypass of G21, as designed. In `test_write_quota.py`
the writing agent is always the owner it claims, and no test this
audit found sends a quota through W5, W6 or a retry.

**Bypasses.** A new `owner_agent` or `metadata.session` per write, a
new token per write under `identity: claim`, and W5 and W6, which
carry no token (G21); rows per write (G22); `update_memory`, which the
quota does not count, a restart and a refresh (G23); a retry, counted
again without its token (G26); `quota: off`. The flood the stress
dimension measures is benign (`STRESS_DIMENSIONS.md:658-660`); the
quota is no defense against writes made to be retrieved.

## Ablation switches

`memory.ablate` is read once at startup, an unknown key or value
fails it (`manager.py:165-168`; `ablation.py:119-135`), and
`/memory/config` reports the whole block (`launch.py:553`). A switch
left on changes behavior with no other sign; the harness's pre-flight
compares the block with the run's (`ABLATION.md:62-70`).

| Switch | What it removes | Property it voids | Code |
|---|---|---|---|
| `barrier: off` | every agent read's wait (chat, SDK read, listing, forget); stamps kept; audit and cost reads still wait | read-after-write for R1, W5 and the forget's wait; queued requests keep their order | `barrier.py:301-302`; `manager.py:184-187` |
| `identity: claim` | session binding, the token check and the canonical rules (whitespace is still stripped); the token, unchecked, still keys the quota | session-bound identity; the partition becomes the raw claim; the quota, against a writer that sends a new token per write (G21) | `launch.py:612-622`, `:629-631`, `:1062-1064`; `manager.py:167-168`; `identity.py:58` |
| `visibility: off` | the sharing rule in selection and in a read by id; writes stay owner-only | visibility | `selector.py:286-288`; `facade.py:511` |
| `supersession: off` | marks and the exclusion | supersession | `settings.py:129-132` |
| `forget_scope: writer` | other agents' rows, the tombstone, and every scrub but of what it deleted | deletion: other agents' carriers stay, nothing is guarded or swept | `deletion.py:124-127`, `:146`, `:151`, `:195-197` |
| `forget_scope: none` | the forget's deletes and its tombstone | deletion | `deletion.py:111-123` |
| `quota: off` | the quota | the quota | `facade.py:282-283` |
| `consumer_config: honor` | the kernel's k, threshold and token budget, in favor of the consumer's; barrier, resolver, tombstones and quota kept | none of the seven, except that a consumer config with an unknown key or a non-numeric value raises in the injector (`context_injector.py:258-273`), which moves the chat's conversation turn to the agent's own scope (G7) | `context_injector.py:251-281` |
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
| Tombstones | the file at `memory.tombstones_path` (`tombstones.py:134-143`) | kept; without a path, gone (G17); truncated through the storage route, empty tables made afresh (G25) | shared through the file; without a path, two stores (G12) |
| Rows and marks | Chroma, Mem0's store, Neo4j | kept | shared, except A-MEM |
| A-MEM rows | a temporary directory per process (`AMEM_BACKEND.md:221`, `:234`) | gone, while tombstones stay | the second manager starts with empty stores |

## The audit, path by path

Each cell is a verdict: "holds"; "holds under assumption (Gn)", the
assumption gap Gn names; "does not hold (Gn)", the violation gap Gn
describes; or "n/a", the property does not apply to the path. A cell
may split by case, and a short qualifier may follow. Two gaps bear on
every path and have rows of their own instead of a place in each cell:
a refreshed kernel (G12, row A2) and the storage and tool routes (G25,
rows S1 and T1).

| Path | Visibility | Partition | Session | Read-after-write | Deletion | Supersession | Quota |
|---|---|---|---|---|---|---|---|
| R1 chat | holds under assumption (G1, G3); its diagnostics disclose counts (G24) | holds | holds (G6: without a token, the claim) | holds under assumption (G11); does not hold naming no user, for a write that named none (G10) | holds under assumption (G17); does not hold for a carrier outside U's partition, which a chat naming no user can select (G28) | holds (write order: G19) | n/a |
| R2 SDK search | holds under assumption (G1, G3) | holds | holds (G6) | holds under assumption (G11, G27); does not hold naming no user (G10) | holds under assumption (G17); does not hold for a carrier outside U's partition (G28) | holds (write order: G19) | n/a |
| R3 agentic retrieval | holds under assumption (G1, G3); its rows reach no agent or model | holds (the agent's own scope) | does not hold (G9): served for the agent's own scope, not the session's user, unless the request names `params.user_id` | does not hold (G9, G10): no wait without `params.user_id`; queued writes are seen by queue order | holds under assumption (G17); does not hold for a carrier in the agent's own scope (G28) | holds (write order: G19) | n/a |
| R4 read by id | holds under assumption (G1, G3) | does not hold on Mem0 (G4); holds under assumption elsewhere (G5) | holds (G6) | holds: no wait, but every row it can name was served before it ("More checks") | holds under assumption (G5, G17); does not hold for a carrier outside U's partition (G28) | does not hold (G19): returns a retired row with no flag | n/a |
| R5 owner listing | holds (owner-only) | holds | holds (G6) | holds under assumption (G11, G27); does not hold naming no user (G10) | holds under assumption (G17), with `withheld`; does not hold for a carrier outside U's partition (G28) | does not hold, by design (G19): returns retired rows | n/a |
| R6 audit | does not hold, by design (G2) | does not hold, by design (G2): any user | does not hold, by design (G2): no session | holds under assumption (G11): waits even under `barrier: off` | does not hold, by design (G2): returns carriers | does not hold, by design (G2): returns retired rows | n/a |
| R7 cost | n/a (no rows) | n/a | does not hold, by design (G2): no session | holds under assumption (G11): waits even under `barrier: off` | n/a | n/a | n/a |
| W1 add | holds under assumption (G1): the owner is claimed | holds | holds (G6) | holds under assumption (G11); does not hold naming no user (G10) | holds under assumption (G20): sweeps before release; does not hold for a carrier it files outside U's partition (G28) | holds under assumption (G20): marks before release, in write order (G19) | holds under assumption (G21, G22, G26) |
| W2 update | holds (owner-only) | does not hold on Mem0 (G4); holds under assumption elsewhere (G5) | holds (G6) | holds under assumption (G11); does not hold naming no user (G10) | holds under assumption (G5, G20): sweeps before release | n/a: retires nothing, by design | does not hold: not counted (G23) |
| W3 remove | holds (owner-only) | does not hold on Mem0 (G4); holds under assumption elsewhere (G5) | holds (G6) | does not hold (G8) | n/a: not a forget | n/a | n/a |
| W4 forget | holds (ids and owners only) | holds | holds (G6) | holds under assumption (G11, G27): it waits for earlier writes, and later reads wait for it | holds under assumption (G13 to G15, G18, G20); does not hold across a restart without a tombstone path (G17), or for a carrier outside U's partition (G28) | n/a: deletes retired rows too | n/a |
| W5 conversation turn | holds (private to the assistant) | holds | holds under assumption (G7): injection on and returned without raising | holds under assumption (G11) | holds under assumption (G13, G20): sweeps before release; does not hold under G7, which files U's text outside U's partition (G28) | n/a (no slot) | holds under assumption (G21, G23) |
| W6 agentic add | holds under assumption (G1) | holds | holds: the add is bound through `metadata.user_id`; its R3 is not (row R3) | holds under assumption (G9, G27): accepted when its final add is submitted | holds under assumption (G20); does not hold for a carrier it files outside U's partition (G28) | holds under assumption (G20), as W1 | holds under assumption (G21, G26): counts by `metadata.session` |
| A1 sessions | n/a | n/a | holds (G6): it binds, it does not authenticate | n/a | n/a | n/a | n/a |
| A2 refresh | holds | holds | holds | does not hold (G12) | does not hold without a tombstone path, and opens G13's window (G12) | does not hold (G12) | does not hold (G12) |
| S1 storage | holds under assumption (G25) | holds under assumption (G25) | n/a (takes no user) | n/a | holds under assumption (G25) | holds under assumption (G25) | n/a |
| T1 tools | holds under assumption (G25) | holds under assumption (G25) | n/a (takes no user) | n/a | holds under assumption (G25) | holds under assumption (G25) | n/a |

A3 and A4 have no row. After `/core/cleanup` the scheduler is stopped
and the memory manager unset (`launch.py:924-938`): a memory request
with a token is then refused, and one without is stamped and queued
with no thread left to serve it, so it never returns (by reading).
That is availability, not one of the seven properties. A4 is out of
scope ("What every guarantee assumes").

More checks:
- **Reads by id and the barrier.** R4 takes no snapshot
  (`manager.py:380-387` stamps no `get_memory`), yet it cannot read
  around a write it names. A row's id reaches a client only once the
  row is stored: in its write's reply, sent after `after_write`
  (`facade.py:302-328`), or in a later listing or selection. Updates,
  deletes and forgets are queued, so one accepted before R4 is served
  before it; a retry of one (G26) serves it again, after its first
  service. Off the queue the only writes are W5's turns, which set no
  mark and whose sweep R4's guard backs up (`facade.py:515-525`).
  Holds, by reading.
- **Update against add.** An update is stamped like an add when it
  names a user, and runs the same sweep, but the quota does not count
  it (G23) and it retires nothing (`facade.py:397`). It is owner-only,
  cannot move a row to another owner or user or set a mark
  (`facade.py:31-36`, `:379-382`), and finds its row by id with no
  partition re-check (G4, G5).
- **Malformed metadata.** A request whose `params.metadata` is not a
  dict and whose `params.user_id` is empty fails with HTTP 500 at the
  handler's log line (`launch.py:1037-1045`). With `params.user_id`
  set, an add with such metadata fails at its stamp, on the event
  loop, before it is queued (`manager.py:369`), and an update with it
  is answered `success` false with its sequence released
  (`facade.py:379-382`, `:403-405`; `manager.py:822-833`). With a
  token, an add's metadata is replaced by a dict first
  (`manager.py:421-422`). No path found queues a request that
  `address_request` would then raise on, which would leave it
  unanswered (`fifo_scheduler.py:153-156`). Holds, by reading.
- **Unknown and closed tokens.** Refused before anything is queued;
  under `identity: claim` not checked at all (`launch.py:612-622`),
  while the token sent still keys the quota's bucket
  (`launch.py:1062-1064`; `syscall.py:110`), so an invented token per
  write is a new bucket per write (G21).
- **Provider caches.** Mem0 caches one client per exact user id
  (`mem0.py:470-474`) but two ids can share its collection (G4); the
  in-house provider caches collections by scope
  (`chroma_inhouse.py:112-137`). Neither cache holds row text. The
  backends' own copies of text are G16.

## Documents the code contradicts

- `SHARED_MEMORY_SYSTEM.md:242-246` says each user maps to a separate
  ChromaDB collection, so "a query against Alice's collection
  physically cannot return Bob's vectors", and that any one of three
  layers is sufficient. For ids that sanitize alike, among them every
  id with no ASCII letter or digit, Mem0's users share one collection
  (G4), and a read by id has only that layer. The
  section's second layer is `get_all` with a user filter and its third
  `context_injector.py` line 360; retrieval now goes through `search`
  (`mem0.py:836-870`) and the selector's partition check
  (`selector.py:259-268`), and `context_injector.py` has 298 lines.
- `PROVIDER_CONTRACT.md:66`: "a row without `owner_agent` is visible
  to nobody"; so say `Visibility.can_read`'s docstring ("Fails closed:
  a memory with no owner is not readable", `visibility.py:118-119`)
  and `apply_sharing_filter`'s ("never matches any agent",
  `visibility.py:27`). An ownerless row whose `sharing_policy` is
  `"shared"` is selected and read by every agent
  (`visibility.py:53-57`, `:122-123`), and selection takes an
  ownerless row for the own row of an agent whose name is the empty
  string (`visibility.py:49-53`). The library names the writing agent
  as owner on every write, so an agent named the empty string writes
  rows with an empty `owner_agent`, which act as its own
  (`launch.py:135`; `facade.py:258-259`), and a row with no
  `owner_agent` needs a write outside the library (G1).
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
| G1 | Visibility; quota | every `/query` request (`agent_name`); W1, W6 (`owner_agent`) | holds under assumption: agents name themselves truthfully; does not hold against a client that names another agent | `launch.py:134-146`; `facade.py:258-259`; `test_add_memory_keeps_an_explicit_owner`; an agent named the empty string writes rows with an empty `owner_agent` and, when it names no user, an empty `user_id`, filed in the provider's default scope (`facade.py:252-259`; `base.py:84-89`; `chroma_inhouse.py:109-110`, `:158`); selection takes rows with a missing or empty owner for that agent's own (`visibility.py:49-53`) and matches rows with no `user_id` when it names no user (`selector.py:192`, `:262-264`) | bind the agent as a session binds the user (a token per agent), set `owner_agent` to the writer on every add, and refuse an empty agent name; or claim visibility "between agents that name themselves truthfully" |
| G2 | Visibility; partition; session; deletion; supersession | R6 | does not hold, by design: any caller lists any user's rows of every agent, carriers and retired rows included, with no session | `launch.py:671-688`; `manager.py:937-957`; `test_the_audit_lists_every_row_the_guard_hides_from_the_agents` | serve the route only when a benchmark flag is set, or only to a local harness; or claim the properties "for the SDK's operations" |
| G3 | Visibility | R1 to R4 on Graphiti | holds under assumption: a row's text comes from its own write; Graphiti does not meet it, by design | each extraction reads the group's ten latest episodes of its source type, of any agent (`GRAPHITI_BACKEND.md:66-69`); a restated fact keeps the first write's sentence (`:123-127`); not measured | claim row-level visibility only; measure whether a private value reaches a shared Graphiti row (the trial-level exposure of known issue 43, on Graphiti cells) |
| G4 | Partition | R4, W2, W3 on Mem0 | does not hold for user ids whose collection names coincide: ids that differ only in characters the name replaces, and every id with no ASCII letter or digit, which gets the default scope's collection | a short id keeps its sanitized name with no digest (`mem0.py:359-443`; `test_ids_that_fit_keep_their_name`); a stand-alone replica of `mem0.py:370-390` (run with `python3 -I`, importing only `re`) gives the component `alice_smith` for `alice.smith`, `alice_smith`, `alice smith` and `alice@smith`, and `default` for `张三`, `李四`, `@@@` and `---`; `default` is the default scope's own component, since `default_user_id` is `"default"` unless configured (`mem0.py:63`, `:120`, `:350-357`), and `locate` reads the default scope for a request that names no user (`facade.py:344-348`); Mem0 2.0.2's `Memory.get` reads by id alone (installed `mem0/memory/main.py:973-995`); `get` is not re-checked (`facade.py:499-526`); no test; whether any dataset id shares a name or lacks an ASCII letter or digit was not checked | re-check `found.metadata["user_id"]` against the scope in `MemoryPipeline.locate` (every provider at once; it changes what two tests pin, G5); and digest every Mem0 collection name (renames existing collections: a migration or fresh stores, known issue 36) |
| G5 | Partition; deletion | R4, W2, W3 | holds under assumption: a provider's `get` stays in scope, every row has a `user_id`, no agent is named the empty string, and no user's id is `default` or, on Mem0, lacks an ASCII letter or digit (G4) | with no user named, `locate` tries the agent's scope, then the provider default (`facade.py:343-348`); a row with no `user_id` is read with no tombstone guard (`facade.py:515-516`) and updated with no sweep (`:383-389`); `test_lookup_without_user_id_tries_agent_scope_then_default` pins the fallback, and `test_update_routes_to_the_collection_the_memory_was_found_in` pins that a by-id update follows the found row's stored `user_id`, not S (`test_conversation_write_path.py:331-361`) | the same re-check as G4, failing closed on a missing `user_id`; it changes what both tests pin |
| G6 | Session | every request without a token; A1 | holds for requests that carry a token; it binds, it does not authenticate | `manager.py:408-409`, `:446-447`; `launch.py:584-599`; `STRESS_DIMENSIONS.md:539-543` | claim "a request the deployment runs in a session is served for the session's user", not "an agent cannot act for another user" |
| G7 | Session; deletion | W5 when injection is off or raised (`injection_error`) | holds under assumption: injection on and returned without raising. Otherwise the turn is filed under the agent's name, not the session's user, so U's text sits outside U's partition, beyond U's forget (G28) | the turn takes the injection's `resolved_user_id` (`syscall.py:875-886`), which the disabled injector reports as None (`context_injector.py:115-135`), as a raising one does, since it returns its initial diagnostics (`:137-145`, `:220-239`); triggers by reading: a tombstone store that raises in selection (`selector.py:318-320`), and under `consumer_config: honor` a consumer config with an unknown key or a non-numeric value (`context_injector.py:258-273`; the first pinned as an injection error by `test_a_consumer_config_with_an_unknown_key_is_an_injection_error` in `memory/test_ablation.py`); then `facade.py:98-99`; v2 kernel runs set `auto_extract` off (`BENCHMARK_V2.md:944-948`); no test checks the turn's user after an injection error | pass the chat's bound user to `extract_async` directly |
| G8 | Read-after-write | W3, then R1 | does not hold for deletes: a chat accepted after a delete was accepted can read the row while the delete waits in the queue | `stamp_syscall` has no `remove_memory` branch (`manager.py:368-387`); `facade.py:407-421`; no test. v2 kernel revokes call the forget, which is stamped (`ABLATION.md:88-92`) | stamp `remove_memory` like a write; or claim read-after-write for writes, updates and forgets |
| G9 | Read-after-write; session; quota | W6 and its R3 | holds under assumption for the add: "accepted" means when its final add is submitted, after two model calls, and no read of the user is accepted in G27's window; does not hold for R3, served for the agent's own scope and without a wait unless the request names `params.user_id`, which the SDK never sends | `syscall.py:153-154`, `:916-932`; `manager.py:368` is never reached through `/query`; sub-requests are submitted without the token (`syscall.py:921`, `:932`; `:87-110`); the SDK sends only `content` and `metadata` (installed Cerebrum `cerebrum/memory/apis.py:155-158`); a session binds an add's `params.user_id` only when it is named (`manager.py:420-425`), and R3 is stamped and selects by it (`manager.py:380-387`, `:763-773`); R3's rows reach no agent or model (`syscall.py:565-571`); no test of W6 over `/query` | stamp at acceptance, bind and stamp R3 by `metadata.user_id`, and pass the token to the sub-requests; or leave `add_agentic_memory` out of the claim |
| G10 | Read-after-write | W1 and W2 naming no user, then R1 naming no user; R2, R3, R5 naming no user | does not hold for requests that name no user: a write that names none is not stamped, so a chat for the agent's own scope (R1 naming no user, which waits on a snapshot taken at injection: `selector.py:100-101`) can miss it; a read that names none does not wait, so it can miss a W5 turn filed in the agent's scope (after a chat that named no user, or under G7) that is still being written; queued requests are still served in queue order | `manager.py:368-387`; a sequence of 0 acquires nothing (`facade.py:271-274`, `:367-371`); a snapshot of 0 skips the wait (`selector.py:100-103`); every turn is stamped under the user it is filed for (`conversation_extractor.py:96`; `facade.py:98-99`) | claim it "for requests that name the user" |
| G11 | Read-after-write; deletion and supersession for reads during a write | R1, R2, R5, R6, R7, the forget's wait (W4), and the readers of an update (W2) | holds under assumption: each earlier write commits within `timeout_ms`, the barrier is enabled, and the provider is not synchronous; for every read but R6 and R7, also `barrier: on` | fails open after the timeout (`barrier.py:340-359`), whether or not the wait is `required` (R6, R7: `manager.py:345`, `:950`); default 5,000 ms (`:85-86`); 3 of 90 kernel Mem0 conversation writes took longer than 5 s in the pilot (`BENCHMARK_V2.md:636-640`); bypasses at `barrier.py:124-125`, `:252-253`, `:298-302`, `selector.py:94-103`; Mem0's 10 s readability wait (`mem0.py:758-771`) | claim "unless the wait times out", and report every `TIMEOUT` (the diagnostics carry `barrier_waits`) |
| G12 | Read-after-write; deletion; supersession; quota | A2 | does not hold after a refresh, until a restart (by reading; not executed; no test) | `restart_kernel` assigns `active_components` as a local (`launch.py:425-445`), so the routes keep the first manager, while `initialize_components` points the shared executor's injector, extractor and stamping at a second one (`launch.py:358-376`) and starts a second scheduler (`:403`) on the same global queues (`aios/hooks/stores/_global.py:23`). Two memory threads then serve queued requests at once; a write stamped on the second barrier and served by the first is released on the first, so the second keeps it pending and every later read of that user there waits out its timeout; chat snapshots come from the first barrier and are compared with the second's sequences; two quotas; without a tombstone path, two tombstone stores; on A-MEM the second provider starts empty | declare `global active_components` and stop the old scheduler, or refuse `/core/refresh` while memory is served; or claim the properties "for a kernel not refreshed since startup" |
| G13 | Deletion | W4 with W5, or after A2 | holds under assumption: no off-queue write during a forget. A write that commits between the forget's listing and its tombstone is neither deleted nor swept; the guard still hides it, and the store and the audit keep it | `deletion.py:109`, `:151-155`, `:163`; `DELETION_AND_SUPERSESSION.md:179-183`, `:648-650`; in the kernel only W5 runs off the queue, and v2 kernel runs turn it off (`BENCHMARK_V2.md:944-948`); no test | list the partition again after recording the tombstone and delete what the second listing adds |
| G14 | Deletion | W4 | holds under assumption: writers label each statement | forms come only from the slot's `structured` rows and its tombstones (`deletion.py:134-149`); with none, no tombstone and deletes by `fact_key` only (`:151-155`; `DELETION_AND_SUPERSESSION.md:196-202`) | claim "the fact as its writers labelled it" |
| G15 | Deletion | W4 and every sweep | holds under assumption: the matcher defines a carrier | lexical matching (`matching.py:28-59`); paraphrases survive (`DELETION_AND_SUPERSESSION.md:637`); Graphiti facts extracted with forgotten text in their context and no form in their sentence survive (`GRAPHITI_BACKEND.md:276-277`) | as stated: "no row whose text carries the value or an alias" |
| G16 | Deletion, in the store | the store's files | holds under assumption (G25) for memory reads through the kernel; the files keep text | Chroma's write-ahead log kept every deleted row's ADD record (kernel Mem0 111 of 111, kernel in-house 65 of 65, measured 2026-11-10: `DELETION_AND_SUPERSESSION.md:638-645`); Mem0 history records of rows deleted earlier by `remove_memory` keep their text (`:651-654`); Neo4j's own logs not checked; the tombstone file holds every forgotten value and alias in plain text, by design (`tombstones.py:113-124`, `:211-217`); the storage route's `share` can upload any of these files (G25) | claim "no memory read through the kernel returns it"; do not claim erasure from disk |
| G17 | Deletion | any restart; A2 | does not hold across a restart without `memory.tombstones_path` | in-memory store (`manager.py:217-224`; `tombstones.py:134-143`); the v2 pre-flight refuses a kernel without a path (`BENCHMARK_V2.md:541-542`) | refuse to start without a path when `forget_memory` is served; or claim it "with a tombstone path" |
| G18 | Deletion | W1, W2 | holds under assumption: a write labelled as a new statement is the user's | any agent's write with the slot, the value and an unseen event lifts the tombstone for all (`tombstones.py:259-291`; `DELETION_AND_SUPERSESSION.md:235-242`) | claim "until a write labelled as the user's restatement" |
| G19 | Supersession | R4, R5; the setting; write order | does not hold for R4, which returns a retired row with no flag, nor, by design, for R5, so a writer's revoke finds its own retired rows; holds under assumption for selection: `supersession: exclude`, "later" read as write order, and one slot per `fact_key` | `read` and the listing check no mark (`facade.py:436-526`); default `off` (`settings.py:50`); replays win (`DELETION_AND_SUPERSESSION.md:379-384`); own rows by a request-settable note id (`deletion.py:336-340`; `facade.py:65-67`); no test reads a retired row by id | hide or flag retired rows in `get_memory`; claim "never selected" |
| G20 | Deletion; supersession; read-after-write | W1, W2, W5 and W6's add when `after_write` raises: a failing tombstone store, a delete, scrub or mark that raises, or a listing at its limit; W4 at the limit | holds under assumption: `after_write` completes. Otherwise the reply is `success` false while the row is stored, released and readable, with no sweep and no marks after the failing step; the guards still hide a carrier | `success` is set after `provider.add` and before `after_write` (`facade.py:302-318`), the barrier released either way (`:329-332`; the update at `:385-405`); the manager answers the exception `success` false (`manager.py:650-665`); the steps that can raise (`deletion.py:319-327`, `:335`, `:348`, `:357`, `:376`); a listing at the limit raises (`deletion.py:54-62`): the forget fails cleanly (`test_a_listing_at_its_limit_fails_the_forget`); `test_every_branch_answers_a_failing_tombstone_store[add_memory]` (`test_forget_kernel.py:647-662`) answers such an add `success` false and does not check the store | page the listing; on a failed `after_write`, delete the write's rows or say in the reply that they are stored; or claim the bound |
| G21 | Quota | W1 with a varied `owner_agent` or `metadata.session`; under `identity: claim`, a new token per write; W5; W6; a retry (G26) | does not hold against a writer that varies its claims; W5, W6 and retries always count by `metadata.session` | the bucket is the claimed owner and, without a token, the claimed session (`facade.py:276-277`, `:282-287`; `quota.py:86-91`); under `identity: claim` a token is not checked but still keys the bucket (`launch.py:612-622`, `:629-631`, `:1062-1064`; `syscall.py:110`), as `test_under_claim_the_quota_still_buckets_by_the_session` pins; the extractor's syscall has no token (`conversation_extractor.py:131-145`); `test_the_quota_counts_per_user_writer_and_session` and `test_a_rejected_write_stores_nothing_and_says_why` pin that a new `metadata.session`, or another `owner_agent`, gets its own bucket, as designed | key the bucket on the bound agent and the kernel session, carry the token into W5, W6 and retries, and check the token under `identity: claim`; keying on the kernel session alone changes what `test_a_rejected_write_stores_nothing_and_says_why` pins (its write with a new `metadata.session` and no kernel session is admitted) |
| G22 | Quota | W1 on Mem0 with `infer`, on Graphiti | does not hold for rows: one write can store several; holds for writes, as `STRESS_DIMENSIONS.md:499-500` states the bound | `mem0.py:773-815`; `graphiti.py:265-276`; `STRESS_DIMENSIONS.md:499-500` | claim "`max_writes` writes per bucket" |
| G23 | Quota | W2; W5; a restart | does not hold for updates, which are not counted, nor across a restart or a refresh, which empty the buckets; holds for adds within one process | updates are not counted (`facade.py:351-405`); buckets live in memory (`quota.py:76-80`); a quota-rejected or suppressed turn is logged as stored, since the extractor checks only `success` (`conversation_extractor.py:162-176`) | claim "adds, per process"; log a rejected turn as rejected |
| G24 | Visibility | R1's diagnostics; W1, W2, W4 replies | holds for rows; the statement does not cover counts and ids, and those of other agents' rows are disclosed, by design | `own_fetched`, `shared_fetched` and `after_partition` are counted before visibility (`selector.py:256-268`) and reach the chat caller (`syscall.py:856-862`); `swept`, `retired` and a forget's `deleted` name other agents' ids and owners (`deletion.py:176-181`, `:351-354`) | claim visibility "of row text and metadata", or drop the pre-visibility counts from replies |
| G25 | Visibility; partition; deletion; supersession | S1 (storage, and `operate_file` chats); T1 (tools, and `call_tool` chats) | holds under assumption: no client's storage or tool request touches the stores' files or the kernel's objects. Against a client that sends one, the properties do not hold: the routes take no session and check no path | `launch.py:1023-1034` (no binding); LSFS keeps an absolute path and joins a relative one to its root, so `..` escapes it (`lsfs.py:271-279`, `:319-331`; `launch.py:217`); `/memory/config` names the tombstone file and Mem0's history file (`launch.py:566-568`); a `write` of `""` to the tombstone file empties it, after which every tombstone read raises (the table is read on every call, `tombstones.py:224-230`), and after a restart the store makes empty tables (`tombstones.py:144-146`), so every forgotten value is unguarded and a later write of it is not swept; with Redis answering at startup (`lsfs.py:43-58`), `share` puts any readable file's bytes (a Chroma file, Mem0's history file, the tombstone file) to `https://transfer.sh/` and returns the link (`lsfs.py:404`, `:415-421`, `:449-476`); a tool call runs hub-loaded code in the kernel's process (`aios/tool/manager.py:98-101`, `:116-118`); by reading; not executed; whether Redis runs in the deployment was not checked; no test | confine LSFS paths to its root and remove or gate `share`; serve tools out of the kernel's process; or state the assumption |
| G26 | Quota; the replies of a forget and a remove | every memory request served through `_execute_syscall` (W1 to W4, R2, R4, R5, and W6's sub-requests) | holds under assumption: each accepted request is served once. Otherwise a retried write counts twice or is rejected as its own duplicate, and a retried forget or remove answers wrongly | the scheduler sets the event before the status (`fifo_scheduler.py:141-142`; `rr_scheduler.py:98-99`), the syscall's thread only waits on the event (`aios/syscall/__init__.py:340-354`), and the waiting thread resubmits any syscall not marked done (`syscall.py:199-211`): the same query is stamped, queued and served again, on a request-pool thread, without its token (`syscall.py:202`, `:110`), and the first reply is discarded; a retried add is stored again (in-house gives every add a new id: `chroma_inhouse.py:156`) and, with the quota on, counts in the bucket of `metadata.session`: with a token, a second bucket whose duplicate check does not see the first write; without one, the same bucket, where `dedupe` rejects it as a duplicate (reply `""`, though the first write is stored); a retried forget answers with the second run's report, which leaves out the rows the first run deleted; a retried remove answers "Memory not found" after deleting; the model calls set the status first (`aios/llm_core/adapter.py:577-583`); by reading; not executed; how often the two statements interleave was not measured; no test | set the status before the event in both schedulers, never resubmit a memory syscall, or keep its token on resubmission; or state the assumption |
| G27 | Read-after-write | W6's final add, and every retry (G26), stamped and queued on a request-pool thread, against a read of the same user accepted on the event loop | does not hold in a window: a read accepted between such a write's stamp and its enqueue (R2 or R5 naming the user, or a forget's wait) is queued first, waits on the memory thread for a sequence only that thread can serve, stalls every memory request for `timeout_ms`, then proceeds without the write | `syscall.py:113` then `:123`, with no common lock; `syscall.py:153-154` and `launch.py:1062-1065` (the loop accepts plain requests; `add_agentic_memory` is served off it); `syscall.py:202`, `:916-932`; the waits run on the memory thread (`manager.py:734-736`, `:770-772`, `:915-917`; `selector.py:220-222`; `facade.py:566-567`; `barrier.py:333-365`); v2 kernel runs set `timeout_ms` to at least 60,000 (`BENCHMARK_V2.md:534`); by reading; not executed; the window is the few statements between `syscall.py:113` and `:123`; no test | stamp and enqueue under one lock, or submit sub-requests and retries through `accept_memory` on the loop; or claim read-after-write "for requests accepted on the event loop" |
| G28 | Deletion | a carrier of U's fact filed outside U's partition: W1, W2 or W6 naming no user (the agent's own scope) or another user; W5 under G7; then a read in that scope (R1, R2, R4, R5 naming no user or that user) | does not hold: U's forget and the sweeps after U's writes list only U's partition, and each guard checks the tombstones of the read's own scope or of the row's own user, so a read in that scope returns the carrier | `deletion.py:54-66`, `:109`, `:335`; `selector.py:318-321`; `facade.py:467`, `:477`, `:515-516`; tombstones are stored per user (`tombstones.py:220-230`); a write that names no user is filed under the agent's name (`facade.py:252-255`; `manager.py:651-652`); without a session a write can name any user (G6); no test | claim deletion "within the user's partition"; bind writes to sessions (G6) and the turn to the chat's user (G7) |

## Open decisions

1. **Agent identity.** Bears on visibility and the quota (G1, G21).
   Options: (a) keep the code and claim both "for agents that name
   themselves truthfully"; (b) bind each agent to a token as sessions
   bind the user, set `owner_agent` to the writer on every add, and
   refuse an empty agent name, which changes what
   `test_add_memory_keeps_an_explicit_owner` pins; (c) for the quota
   alone, carry the kernel token into W5, W6 and retries, key the
   bucket on the bound agent, and check the token under
   `identity: claim`, which may change what
   `test_a_rejected_write_stores_nothing_and_says_why` pins.
2. **Reads by id.** Bears on the user partition (G4, G5). Options: (a)
   re-check the row's `user_id` in `MemoryPipeline.locate`, failing
   closed, which changes what
   `test_update_routes_to_the_collection_the_memory_was_found_in` and
   `test_lookup_without_user_id_tries_agent_scope_then_default` pin;
   (b) also digest every Mem0 collection name, which renames existing
   collections and ends the sharing of the default scope's collection
   by ids with no ASCII letter or digit; (c) narrow the claim to
   selections and listings.
3. **Deletes and agentic writes under the barrier.** Bears on
   read-after-write and session binding (G8, G9). Options: (a) stamp
   `remove_memory` like a write, stamp `add_agentic_memory` at
   acceptance, and bind and stamp its R3 by `metadata.user_id`; (b)
   narrow the claim to `add_memory`, `update_memory` and
   `forget_memory`; (c) leave `add_agentic_memory` out of the paper
   (no test exercises it over `/query`, its evolution step never
   updates a row, and R3's rows reach no agent).
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
11. **The storage and tool routes.** Bears on visibility, the
    partition, deletion and supersession (G25, G16). Options: (a)
    confine LSFS paths to its root and remove or gate `share`; (b)
    serve storage and tools only to the deployment's own clients and
    state the assumption; (c) serve them from a process that cannot
    reach the memory stores, or not beside memory at all.
12. **Serving a request once, in order.** Bears on read-after-write
    and the quota (G26, G27). Options: (a) set the status before the
    event in both schedulers, and never resubmit a memory syscall;
    (b) stamp and enqueue under one lock, or submit W6's sub-requests
    and retries through `accept_memory` on the event loop; (c) narrow
    the claims: read-after-write "for requests accepted on the event
    loop", with "each accepted request is served once" stated as an
    assumption.
13. **Carriers outside the user's partition.** Bears on deletion and
    session binding (G28, G7). Options: (a) claim deletion "within
    the user's partition"; (b) pass the chat's bound user to the
    conversation turn and bind every write to a session, so U's text
    lands in U's partition when the agents run in U's session.

Open: whether any pair of user ids in the v2 datasets sanitize to one
Mem0 collection name, or any id lacks an ASCII letter or digit (G4);
whether Redis runs in the deployment (G25); how often the retry of
G26 happens; and whether any agent's name changes under the kernel's
identity rules were not checked. None of the gaps was reproduced by
running code.
