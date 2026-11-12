# Graphiti backend (NeurIPS Subtask 16)

Graphiti is Zep's open-source temporal knowledge graph: each write is an
episode, its own LLM extracts entities and the facts between them, and
facts carry a validity interval it maintains. This document fixes,
before any provider code, how Graphiti plugs into the provider contract
(`PROVIDER_CONTRACT.md`) beneath the kernel and the replicated agents,
and what the forget and supersession can and cannot do on it. The
native condition is specified in `NATIVE_USAGE.md` ("native_graphiti").
It replaces the Zep Cloud provider (`zep.py`), which never conformed.

Facts below about Graphiti come from the installed source
(`graphiti_core`, cited as file:line) and from an exploration run on
2026-11-11 against the pinned stack (five writes of one user;
"Exploration" below). Graphiti's documentation is cited by URL where it
says something.

## Versions and setup

- `graphiti-core==0.31.2` in both venvs (released 2026-10-20), with the
  Neo4j driver it pulls, `neo4j==6.4.1`. Pinned in both requirements
  files and checked by a test, as `mem0ai` is.
- Neo4j `5.26.33-community` in Docker
  (`neo4j@sha256:ec10d705830a340c7438e125cb5c4f90522b85369d877c9a581c3de5974ab3d6`),
  container `aios-graphiti-neo4j`, bolt on `127.0.0.1:7687` only, data in
  the volume `aios-graphiti-neo4j-data`. Graphiti asks for Neo4j 5.26 or
  later ([Neo4j configuration](https://help.getzep.com/graphiti/configuration/neo4j-configuration)).
  It needs no plugin: the source calls no APOC or GDS procedure.
- Credentials: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` in
  `AIOS/.env` (gitignored), read by the kernel and the harness.
- Telemetry off everywhere: `GRAPHITI_TELEMETRY_ENABLED=false`. Graphiti
  otherwise sends one PostHog event per client construction
  (`telemetry/telemetry.py:18-62`).
- The AIOS venv's `llama-index-core` 0.10.19 declares `tenacity<9`;
  `graphiti-core` needs `tenacity>=9`, so the venv now has 9.2.1. Every
  name `llama_index` imports from `tenacity` exists in 9.2.1 (checked);
  kernel startup and the suites are the test.

Both versions and the image digest go into every run's `PROVENANCE.md`.

## What Graphiti stores

- An **episode** (`:Episodic` node) per `add_episode` call, holding the
  text verbatim in `content` (`nodes.py:318-332`), with `group_id`,
  `source`, `source_description` and `valid_at` (the call's
  `reference_time`).
- **Entities** (`:Entity` nodes) with a `name` and a `summary`; facts
  are appended to the summaries of the entities they touch, or the
  summary is rewritten by the LLM when it grows past 2,000 characters
  (`node_operations.py:1114-1169`).
- **Facts**: `RELATES_TO` edges with a `fact` sentence, an embedding,
  `episodes` (the uuids of the episodes that produced or restated it),
  and `valid_at`, `invalid_at`, `expired_at` (`edges.py:263-290`).

`add_episode` takes no metadata. Its `EpisodicNode.episode_metadata`
field is never written to the database (`nodes.py:341-351`), and nothing
given to `add_episode` reaches a fact except `group_id`, the reference
time and the episode's uuid (`edge_operations.py:350-373`). Typed edge
attributes are filled by the LLM, and an existing fact's attributes are
cleared when a later episode is merged onto it
(`edge_operations.py:1071-1076`), so they cannot carry ours.

A write runs, in order: node extraction (one LLM call), node resolution
(an LLM call when candidates exist), edge extraction (one call), edge
resolution per fact (a call when candidates exist; it also returns the
facts the new one contradicts), timestamps for undated facts, and
summaries (`graphiti.py:1435-1531`). Each call sees the ten most recent
episodes of the same group and source type as context
(`graphiti.py:1435-1445`).

## One episode per write

Every `add` is one `add_episode` call:

- `group_id`: the user partition (below).
- `episode_body` and `source`: a user's statement is a chat message,
  `"user: <content>"` with `source=EpisodeType.message`, the documented
  format for conversation ("{role/name}: {message}";
  [adding episodes](https://help.getzep.com/graphiti/core-concepts/adding-episodes)).
  A conversation memory (`User: ...\nAssistant: ...`) becomes the same
  turns as `user:` and `assistant:` lines. Anything else, JSON included,
  is one `user:` message, as Mem0 takes a write and the native agents
  write theirs. The exploration shows why not `text`: as `text`, "My
  team's chat tool is Slack." and "I live in Utrecht and work as a data
  engineer." each gave one entity and no fact, since the speaker is not
  an entity; as `user:` messages every write gave at least one fact
  ("user lives in Utrecht.", "user works as a data engineer."). JSON was
  first a `json` episode; the functional check's V5 writer (it stores
  its structured JSON) then stored no fact for 12 writes of two users,
  and two V5 payloads gave none as `json` and one each as `user:`
  messages ("user lives in Utrecht").
- `name`: `<owner_agent>:<memory_type>:<memory_note_id>`;
  `source_description`: `<owner_agent> <memory_type>`.
- `reference_time`: the note's `created_at` (UTC, set by the kernel at
  acceptance), so later writes have later reference times.

## Metadata: on the episode, given to every fact

Our metadata goes in a sidecar keyed by episode: the provider writes it
as a JSON property, `aios_metadata`, on the episode node right after
`add_episode` returns, in the same provider call. It is deleted with the
episode. Graphiti rewrites an episode node only when it processes that
episode again (`add_episode(uuid=...)`, which the provider never calls).

A fact's metadata, per episode that produced or restated it, is that
write's `aios_metadata`, merged with that fact's own changes (an
`aios_row_metadata` map on the episode, keyed by fact: supersession
marks and updates), plus read-only `graphiti_*` fields: the fact and
episode uuids, `graphiti_valid_at`, `graphiti_invalid_at`,
`graphiti_expired_at` and `graphiti_episode_count` (how many writes
claim the fact). So every fact a write produces carries all of its
keys, `owner_agent`, `user_id`, `sharing_policy`, `memory_type`,
`created_at`, `fact_key` (the slot), `provenance_event`, `value_aliases`
and `memory_note_id` included: a write split into several facts gives
each the write's slot.

## Rows: one per fact and write

A row is one fact as one write claims it: `memory_id` is
`<fact uuid>:<episode uuid>`, `content` is the fact sentence, and the
metadata is that write's (above).

This is where Graphiti's consolidation shows up. Graphiti merges a fact
that restates an existing one onto the existing edge and appends the new
episode to its `episodes` (`edge_operations.py:905-908`, `:954`,
`:1014-1015`); the fact's text stays the first write's. In the
exploration, "user: My team's chat tool is Mattermost." added no fact of
its own: it was merged onto "user's team moved their chat tool to
Mattermost last week", whose `episodes` became both writes. One row per
fact and write keeps the restating write's own row, with its own
metadata, so its extraction check, its supersession and visibility all
work as for any other write. A fact claimed by several writes appears as
several rows with the same text, newest claim first; the selector's
exact-content dedupe keeps the first, so the block shows the fact as
last stated (its session age and event). It covers the own fetch's rows
since the
Subtask 16 review: before, two claims of a fact in the own fetch both
reached the block (the functional check's replicated `no_delete` cell:
12 extra rows in 10 of 30 probes; no other Graphiti cell, and no Mem0
or in-house block of the Subtask 15 runs, held two rows with one
text).

- `add` returns the id of the write's first row, or `""` when the write
  gave no fact (as Mem0 does when it extracts nothing; a lost memory,
  BENCHMARK_V2.md Amendment 5). The facts the write merely invalidated
  are not its rows.
- `capabilities()`: `scored_search` **false**, `semantic_search` true,
  `internal_llm` true, `native_sdk` true. `backend_extraction` is true:
  there is no verbatim mode.
- `synchronous_commit` false: a write takes seconds, and the write
  barrier makes a retrieval accepted after it wait for it.

## Search: Graphiti's own, unscored

`search(query, user_id, top_k)` is Graphiti's documented `search()`:
BM25 and cosine over facts, fused by reciprocal rank
([searching](https://help.getzep.com/graphiti/working-with-data/searching);
recipe `EDGE_HYBRID_SEARCH_RRF`, `search_config_recipes.py`), filtered
to the user's group, in Graphiti's order. It returns no score, so every
row has `score=None` and the provider reports `scored_search: false`.
The kernel then ranks by Graphiti's order and drops nothing
(`PROVIDER_CONTRACT.md`, "Threshold"). Graphiti's lower-level
`search_` with a reranker would give scores, but it is not what the
documentation shows for search, and the native agents use `search()`;
the loci must not differ in retrieval by our choice.

The provider calls `search_` with a deep copy of that recipe and empty
`SearchFilters`; `search()` runs the same search on the recipe itself
(`graphiti.py:1913-1972`). The copy is needed because `search()` writes
its `num_results`
into the shared module-level recipe object (`graphiti.py:1958`), which
ingestion also uses to find duplicate and contradicted facts
(`edge_operations.py:532`, `:563`). A kernel fetch of 40 would change how
every later write is resolved. In the exploration both calls returned
the same facts in the same order; a test checks it. The native agents
call `search()` with `num_results` k, 10 except for a V4 consumer (5,
at H = 2), and put the recipe's limit back after each call, so one
user's consumer does not change how the next writes are ingested
(found by the Subtask 16 review; a test checks it).

Each fact becomes its rows (one per write claiming it), in Graphiti's
order, cut at `top_k` rows. Facts Graphiti has invalidated come back,
as `search()` returns them (`search_filters.py:55-73`), with their
validity in the metadata.

An empty group filter searches every group (`search.py:155-156`), so
the provider refuses an empty scope.

## list, get, update, delete

- `list(user_id, top_k)`: the user's rows in write order (episode
  `created_at`, then the order Graphiti returned the write's facts),
  unscored, through one Cypher query on the group. Graphiti's own
  listings order by random uuid (`nodes.py:421-466`).
- `get(memory_id, user_id)`: the row, if its fact and episode exist in
  the user's group (Graphiti's own getters check no group).
- `update(memory_id, user_id, content, metadata)`: new content replaces
  the row's fact sentence verbatim and re-embeds it, with no LLM call, as
  Mem0's update does with extraction on. A fact other writes also claim
  is split first: the others keep the old sentence on a copy, so their
  rows do not change. Metadata merges into the row's own changes;
  required keys are never removed.
- `update_metadata`: the row's own changes only, no embedding call.
- `delete(memory_id, user_id)`: removes the write's claim on the fact:
  the episode leaves the fact's `episodes`, the fact is deleted when no
  write claims it, and an episode left with no fact is deleted. No LLM
  call.

## What deleting an episode leaves

Graphiti deletes by episode: `remove_episode(uuid)`
(`graphiti.py:2174-2251`; not in the documentation, which shows no
episode delete, but used by Graphiti's MCP server). From the source,
confirmed in the exploration:

- A fact is deleted only when no other episode claims it. A fact that
  another episode restated survives with its sentence unchanged, though
  the sentence came from the deleted episode's extraction (exploration:
  "user's team moved their chat tool to Mattermost last week" stayed
  after its first episode was deleted).
- Facts the episode invalidated stay invalidated.
- Entities only that episode mentioned are deleted; every other entity
  it mentioned gets its summary rebuilt by the LLM from its remaining
  episodes (two calls in the exploration).
- Names, other episodes' texts and community or saga summaries are not
  touched (communities and sagas are off here).

So deleting an episode does not make all of its facts disappear: the
facts it shares with another write survive. Under the row model above,
deleting a write's rows does make all of them disappear from `search`
and `list`, and a fact disappears when its last row goes; a test checks
both on merged facts.

## The forget on Graphiti

The library's forget is unchanged: it lists every row of the user
(`list`), deletes the slot's rows and every carrier, a row whose fact
sentence carries a form of the value (the scorer's matcher), of any
agent, then calls `scrub_history`.

Graphiti keeps text besides its facts, and reads it back:

- **Episode texts.** Every later write's extraction reads the user's
  ten latest episodes of its source type as context, so a forgotten
  value left in an episode can be extracted again. This is the analogue
  of Mem0's stored messages.
- **Entity names and summaries.** The value is often an entity's name
  ("Mattermost"), and summaries collect the facts of their entity (in the
  exploration the `user` entity's summary held every fact of the user,
  Slack and Mattermost both). Node resolution and summaries read them.

`scrub_history(user_id, forms, deleted_ids, kept_ids)` for Graphiti,
with no LLM call:

1. blanks the `content` of the user's episodes that carry a form, and of
   the deleted rows' episodes whatever they hold;
2. deletes an episode left with no fact and no content;
3. deletes the user's entities whose name carries a form, with the
   facts still attached. The forget or the sweep deleted every carrier
   first, so none of those carries a form: they are returned as
   `detached` rows, which the library reports as deleted (reason
   `entity`) or swept, so the harness and the analysis count them;
4. blanks the summaries of the user's entities that carry a form.

It returns `{"messages": <episodes scrubbed or deleted>, "history":
<entity names and summaries scrubbed>}`, the keys Mem0's scrub reports,
and `detached` (`{memory_id, owner_agent}` per row) when step 3 deleted
facts.
The library calls it after every forget and every sweep.

What it does not reach, reported rather than hidden:

- Graphiti's invalidations caused by the forgotten statement stay: a
  fact it invalidated is still marked invalid after the statement is
  forgotten.
- Facts another write extracted with the forgotten text in its context,
  whose sentence does not carry a form.
- Facts attached to an entity a form names are deleted with it, though
  their sentences carry no form: reported (reason `entity`), not
  hidden.
- A blanked summary loses its entity's other facts too; summaries are
  rebuilt from later writes as Graphiti appends to them. Search does not
  return summaries.

## Supersession: two mechanisms, one measured

- **Graphiti's own.** When edge resolution judges that a new fact
  contradicts an older one, it sets the older fact's `invalid_at` and
  `expired_at`, or the new fact's, when the older one's `valid_at` is
  later (`edge_operations.py:715-783`). It needs both `valid_at`s and a
  strict order, and it skips merged and candidate-free facts. It is
  always on, in every locus, and drops nothing from `search()`. In the
  exploration it went the wrong way: "We moved our team chat to
  Mattermost last week" was dated a week back, before the Slack
  statement's reference time, so Graphiti invalidated the Mattermost
  fact and left Slack valid.
- **The kernel's** (`memory.supersession: exclude`;
  `DELETION_AND_SUPERSESSION.md`): a later statement of a slot marks the
  slot's earlier rows and the selector excludes them. Every fact of a
  write carries its slot, so the marks reach every fact of the earlier
  statement.

The benchmark measures the kernel's: in the kernel and replicated
cells, Amendment 4's supersession readings and criteria read only the
kernel's marks (`superseded_by`, `superseded_rows`, `retired_rows`,
`retired_in_block`), and `no_supersession` turns only the kernel's off.
Graphiti's invalidations are recorded separately and credited to no
locus: every row carries `graphiti_invalid_at` and
`graphiti_expired_at`; the harness records, per trial, the rows after
the history that Graphiti marked invalid (`backend_invalidated_rows`)
and, per probe, the injected rows Graphiti had marked
(`backend_invalidated_in_block`); the analysis reports them in their own
columns, and no criterion reads them.

## LLM, embedder and cost

- **LLM**: Azure gpt-4o, the model Mem0 extracts with
  (`memory.backend_llm`: `azure_openai` / `gpt-4o`, temperature 0, seed
  20261105), for both of Graphiti's model sizes, so the backend LLM is
  the same for every backend. Graphiti ships no LiteLLM client, so the
  backend uses one: an `LLMClient` whose `_generate_response` calls the
  synchronous `litellm.completion` (`azure/gpt-4o`, temperature 0, the
  seed) in a worker thread. The usage logger counts only synchronous
  LiteLLM calls (`cerebrum/utils/usage.py`; an `acompletion` call would
  be marked in flight and never counted). JSON is schema-guided
  (`response_format` with the response model's JSON schema): the
  deployment's API version, 2024-02-15-preview, ignores `json_object`
  and answered in fenced prose in the exploration. Code fences are
  stripped, as Graphiti's own `OpenAIGenericClient` does
  (`openai_generic_client.py:126-138`).
- **Embedder**: the pinned model (`memory.embedding`, Ollama
  `nomic-embed-text`, 768) through the same `ollama.Client.embed` call
  as the in-house and Mem0 backends, counted by `count_embeddings`, so
  Graphiti's vectors are the other backends'. It does not go through
  LiteLLM; its tokens are attributed the same way.
- **Cross-encoder**: none. `search()` and ingestion never call it
  (`search/search.py`); the provider passes one that raises.
- **Attribution.** Every LLM call a write makes (node extraction,
  resolution, edge extraction and resolution, timestamps, summaries) is
  a `backend_extraction` record of the trial: Graphiti runs on a
  background event loop, and each provider call carries the trial's tag
  (`cerebrum.utils.usage.tagged`) into it explicitly. The exploration
  counted 18 calls and 33,282 prompt tokens for five writes, 3.6 calls
  and 6,656 tokens a write, 4 to 7 seconds each, against Mem0's one
  extraction call a write. The prompts grow with the context window.
- The kernel, the replicated agents and the native agents use the same
  three client classes, in Cerebrum (`cerebrum/utils/graphiti.py`), as
  `mem0_llm_config` is shared today, so the loci share one
  configuration.

## Measured in the smokes

From the pilot_v1 smoke (Cerebrum `results/pilot_v1_graphiti`) and the
benchmark v2 smoke (`results/bench_v2_smoke_graphiti`), against the
Mem0 and in-house cells of `pilot_v1_hetero` and `bench_v2_smoke_a4`
(same users, inputs and settings). Per user, H = 0; USD is the
backend's (gpt-4o at the committed price table). Every trial's
recorded calls match the calls its logs show, except the H = 2 agent
cells of pilot_v1, which are lower bounds (`v2_trials`; Cerebrum
`a836d69`).

| | Graphiti calls | per write | USD | Mem0 calls | per write | USD |
|---|---:|---:|---:|---:|---:|---:|
| pilot_v1 (3 writes) | 17.7 to 19.3 | about 6 | 0.094 to 0.101 | 3.0 | 1 | 0.064 to 0.065 |
| v2 (17.8 writes) | 72.4 to 74.9 | 4.1 to 4.2 | 0.41 to 0.43 | 17.8 | 1 | 0.36 |

- **Latency.** `add_episode` took a median of 6.3 to 6.5 s a write in
  the v2 smoke (p90 7.1 to 7.6 s, longest 18.3 s), about 116 s per
  user. A v2 user took 182 to 191 s in the Graphiti cells, against 95 to
  102 s on Mem0 and 73 to 77 s in-house.
- **Granularity.** Graphiti stores a statement as about one fact, but
  the base profile as 3 to 5 facts and the base task context as 1 to
  11: about 23 facts per v2 user, of which a block holds k = 10. The v2
  integration block held 37% of the base profile's values (25% native),
  against 100% in-house and 76 to 80% on Mem0, and the budget never
  bound (longest block 197 of 300 estimated tokens). Integration scored
  2.20 (kernel) and 1.97 (replicated), against 2.87 in-house and 3.57
  to 3.60 on Mem0.
- **Graphiti's invalidations against the kernel's supersession.** In
  the v2 smoke Graphiti marked invalid 52 of the kernel cell's 60
  retired rows (replicated: 54 of 60), and 1 to 3 rows per cell that
  are a slot's latest statement. In native, which retires nothing, 32
  of the 36 recency and contradiction failures held the stale value in
  a fact Graphiti had marked invalid (`NATIVE_USAGE.md`, "Evidence:
  native Graphiti's search as returned").
- **Writes with no fact.** None in the v2 smoke (534 writes per cell).
  In the pilot_v1 smoke 33 of the kernel's and 32 of replicated's 60
  conversation turns gave no fact (no v1 score reads the turn), and one
  native task write stored none.

## Store and partition

One Neo4j database holds every store: Community edition has one, so the
kernel's, the replicated agents' and the native agents' stores are
separated by `group_id`. Graphiti accepts `[A-Za-z0-9_-]` only
(`helpers.py:145-168`), and a user id can hold `@` and `.` (the V2
variant's `…@users.example`), so the group id is a readable part of the
user id and the first 12 hex digits of its SHA-256, as Chroma
collection names are (`base.user_collection_name`). User ids carry the
run id and the method, so no two cells share a group; as for every
store, a new run needs a new `RUN_PREFIX` (known issue 36).

## Concurrency

Graphiti is async only; each provider runs one background event loop
and blocks on it per call. Graphiti requires a group's writes to be
added one at a time (`graphiti.py:1410-1413`), so writes to a group are
serialized by a lock.

## Tests

- The contract tests run unchanged against Graphiti on the real Neo4j
  and embedder with a scripted LLM, offline and deterministic, that
  makes each write one fact with the write's own text: the analogue of
  running Mem0's contract tests with extraction off.
- Graphiti-specific tests on the same stack, scripted: a write split
  into several facts gives every fact the write's metadata, the slot
  included; a restatement merged onto an existing fact gets its own row;
  deleting a write's rows removes them from `search` and `list`, and a
  merged fact survives with the other write's row; the scrub reaches
  episode texts, entity names and summaries; `search` equals Graphiti's
  `search()`; the trial's tag reaches every LLM and embedding call.
- A live check on real extraction (Azure gpt-4o, opt-in, like Mem0's
  `check_fact_metadata.py`) of the two risks below.

## Open risks, before code

1. **Metadata on every fact.** Graphiti carries none, so everything
   rests on the episode sidecar and on rows per fact and write. A
   restatement merged onto another write's fact must still give the
   restating write its own row, or its extraction check and its
   supersession fail.
2. **Deletion completeness.** Deleting an episode leaves facts it
   shares, text in summaries and invalidation marks. The forget
   compensates by deleting carrier facts and scrubbing episode texts,
   entity names and summaries; what stays is listed above.
3. **Writes with no fact.** A write Graphiti extracts nothing from
   stores no row. As messages, every write in the exploration gave a
   fact; the functional check found 3 of 720 that did not (entities,
   the statement in an entity's summary, no edge; the same writes gave
   a fact in other runs). The harness first failed such a trial, as for
   Mem0; since BENCHMARK_V2.md Amendment 5 a Graphiti write that stored
   no fact is a lost memory, recorded in `writes_without_fact`, and the
   trial is scored (Graphiti's extraction errors raise, Mem0's are
   swallowed).
4. **Graphiti's temporal reasoning** can invalidate the newer fact
   (exploration); recorded, credited to no locus.
5. **Schema-guided JSON** depends on LiteLLM's handling of
   `json_schema` for API version 2024-02-15-preview, which worked in the
   exploration.
