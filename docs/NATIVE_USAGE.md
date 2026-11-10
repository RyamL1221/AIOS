# Native Usage: agent-managed memory conditions

The conditions `native_mem0` and `native_inhouse` are the first locus
condition of the design: the agents manage memory themselves, using each
backend the way its documentation says to, and the kernel takes no part
in memory. This is how people deploy these backends today. This document
fixes, before any code, exactly what each agent does, so a reviewer can
check the agent code against it.

Code: Cerebrum `cerebrum/example/agents/native/`. Harness:
`run_evaluation.py --method native_mem0|native_inhouse`.

## What "agent-managed" rules out

- **No kernel injection.** The kernel runs with `memory.auto_inject:
  false` and `memory.auto_extract: false`. The harness pre-flight reads
  `/memory/config` and refuses to run a native condition otherwise, and
  refuses a kernel condition (`kernel_shared`, `kernel_private`) when
  injection is off.
- **No memory syscalls.** No agent calls `create_memory`,
  `search_memories`, `update_memory` or any other kernel memory API; the
  kernel log of a native run has no memory operation in it.
- **No write barrier.** Writes are synchronous calls into the backend
  made by the writer before it returns, so there is nothing to wait for.
- **No kernel identity resolution.** Each agent is given the user's id
  and passes it to the backend itself.
- **No kernel formatting or token budget.** The AssistantAgent builds
  and prepends its own memory block.

The kernel still serves every LLM call (`llm_chat`,
`llm_chat_with_json_output`): only memory is agent-managed.

## Shared by both conditions

**Agents.** `NativeProfileAgent`, `NativeTaskAgent` and
`NativeAssistantAgent`. The writers extract exactly as the kernel
conditions' `ProfileAgent` and `TaskAgent` do (same prompts, same JSON
schemas, through the kernel's `llm_chat_with_json_output`), then write
to the backend instead of calling `create_memory`.

**Memory text.** Each writer stores one natural-language rendering of
its extraction, written by the agent:

- profile: `My name is <name>. I prefer to use <tools>. My preferred
  programming language is <language>. I like <style> responses.`
- task context: `I'm working on <project>. My current experiment is
  <experiment>. My goals are: <goals>. My blockers are: <blockers>. My
  next steps are: <next steps>.`

See "Mem0 extraction check" for why natural language and not the JSON
the kernel conditions store.

**Metadata.** Every write carries `owner_agent`, `user_id`,
`memory_type` (`profile`, `task_context` or `conversation`),
`sharing_policy` and `created_at`: the same keys as the kernel's
provider contract. Profile and task-context memories are `shared`;
conversation memories are `private`, as in `kernel_shared`.

**Sharing convention** (Figure 1a, per-agent convention). The three
agents share one filter function in the agent package
(`native/sharing.py`), as a developer writing the three agents would:
a memory is visible to agent A when it is A's own (`owner_agent == A`)
or its `sharing_policy` is exactly `"shared"`, and it belongs to the
user being served (`user_id` matches). A memory missing either key is
not visible. This is the same rule the kernel enforces, implemented
here by the agents themselves and nowhere else.

**Retrieval size.** The AssistantAgent asks for `k` results, where `k`
is the kernel's `max_injected_memories` (read once from `/memory/config`,
10 in the shipped config), so native and kernel retrieve the same number
of candidates. There is no separate shared fetch and no token budget.

**The block.** The AssistantAgent prepends one system message:

    Relevant memories about this user:
    - <memory text>
    - ...

in the order the backend returned them, then its usual system prompt
and the user's query, and calls `llm_chat` with the user's id. With no
visible memories it sends no block.

Since Subtask 9d the kernel and replicated conditions use the same
shape (the library's `compact` block: `Known about this user:` and a
bullet per memory, no delimiters, instruction line or timestamps), so
the loci differ only in the header's wording and in the order (backend
order here, profile / task context / conversation in the kernel). The
native renderer stays the agents' own by design.

**Conversation memory.** After the response, the AssistantAgent writes
the user/assistant turn to the backend as a private `conversation`
memory, as Mem0's documentation shows for chat. This happens after the
response and is excluded from the trial's latency (the kernel
conditions write theirs on a background thread). In a single-interaction
trial it is written after retrieval, so it cannot change that trial. A
benchmark v2 probe turn writes nothing (`store_conversation` false;
BENCHMARK_V2.md, Amendment 3).

**Configuration.** One pinned embedding model for both conditions,
`memory.embedding` (Subtask 5), and one pinned internal LLM for Mem0's
extraction, `memory.backend_llm`, separate from the assistant's model.
The AssistantAgent and writers read both from the kernel's
`/memory/config`, so every results file records them in
`config_snapshot`. Stores live under the harness's working directory
(`.native_memory/<condition>/`), apart from the kernel's stores.

**Diagnostics parity.** The AssistantAgent records its own
`injection_diagnostics` with the kernel's keys, so the harness stores
comparable records: `resolved_user_id` (the id it was given),
`own_fetched` (rows the backend returned), `shared_fetched` (0: one
fetch), `after_partition` (rows whose `user_id` matches),
`after_visibility` (after the sharing filter), `after_dedupe`,
`after_threshold` and `after_cap` (no dedupe, threshold or cap beyond
`k`: equal to `after_visibility`), `scores_present`, `threshold_used`
(`None`: no agent threshold), `top_k_used`, `after_budget`,
`injected_count`, `tokens_estimated` and `injected_memories`
(`owner_agent`, `memory_type`, `match_score`). It also records
`visibility_checked`, which is not a kernel key: False when it skips the
sharing convention (a V3 consumer, the `no_visibility` control). The
harness's native `visible_stored_rows` reads it (`history.visible_rows`);
the kernel and the library do not send it.

**Cost parity (Subtask 7).** The AssistantAgent also records the
kernel's latency keys: `barrier_wait_ms` (0: no barrier), `search_ms`
(the backend call), `select_ms` (partition, sharing filter, `k`),
`format_ms` (the block), the kernel scheduler's `schedule_wait_ms` and
the model call's `llm_ms` (both from the kernel's `llm_chat` reply), and
`kernel_overhead_ms`, their sum without `llm_ms`. The backend's own LLM
and embedding calls are tagged with the trial's user id
(`cerebrum.utils.usage.tagged`) and counted in the harness process; the
AssistantAgent reads the trial's records after its conversation write.

## native_mem0

Follows the Mem0 open-source documentation for `mem0ai` 2.0
(installed: 2.0.2):

- Configuration: `Memory.from_config` with an `llm`, an `embedder` and
  a `chroma` `vector_store` (`collection_name`, `path`)
  ([configuration](https://docs.mem0.ai/open-source/configuration),
  [Chroma](https://docs.mem0.ai/components/vectordbs/dbs/chroma),
  [Ollama LLM](https://docs.mem0.ai/components/llms/models/ollama)).
  Since Subtask 7 the `llm` is Mem0's `litellm` provider with the
  pinned model as `azure/gpt-4o`
  ([LiteLLM](https://docs.mem0.ai/components/llms/models/litellm)), so
  every extraction call reaches LiteLLM's success callback and its
  tokens are counted per trial. Subtask 6 used Mem0's `azure_openai`
  provider for the same deployment.
- Writing: `add(messages, user_id=..., agent_id=..., metadata=...,
  infer=True)`, where `infer=True` "extracts structured memories" with
  the LLM ([add](https://docs.mem0.ai/core-concepts/memory-operations/add)).
- Searching: `search(query, filters={"user_id": ...}, top_k=k)`; entity
  ids go in `filters`, and top-level ids raise `ValueError`
  ([search](https://docs.mem0.ai/core-concepts/memory-operations/search),
  [quickstart](https://docs.mem0.ai/open-source/python-quickstart)).

What the agents do:

- **Clients.** Each agent constructs its own `Memory` client from the
  same config: one Chroma collection (`native_mem0`) at
  `.native_memory/native_mem0/chroma`, with its history database next to
  it. This is Mem0's model: one store, scoped by entity ids, not one
  store per user.
- **Writers.** `memory.add([{"role": "user", "content": <memory text>}],
  user_id=<user>, agent_id=<self>, metadata={memory_type,
  sharing_policy, owner_agent, created_at}, infer=True)`. Mem0 extracts
  facts from the text; the stored memories are Mem0's, not the agent's
  text. Writers do not search before writing: Mem0's extraction decides
  what to keep.
- **Sharing.** The AssistantAgent searches with `filters={"user_id":
  <user>}` only, with no `agent_id`, which returns every agent's
  memories for that user (verified below; the documentation does not
  say so). It then applies the sharing convention to each result, reading
  `owner_agent` and `sharing_policy` from the result's `metadata`.
- **Scores.** Results and scores are used as Mem0 returns them, in its
  order and with its default `threshold` (0.1; the consumer passes
  none). That includes the inverted score found in Subtask 5 (Mem0's
  Chroma adapter reports the raw L2 distance as a similarity), because
  that is what a user of Mem0 gets. `scores_present` records whether
  Mem0 returned scores. The score is clamped at 1.0, so every row at
  cosine 0.5 or below ties at 1.0 in Chroma's nearest-first order, and
  the rows above 0.5 follow from the least similar up
  (`PROVIDER_CONTRACT.md`, "Mem0"). Mem0's default threshold applies to
  this distance, so it drops the rows nearest the question (cosine
  above 0.95). Once the store holds k rows at 0.5 or below, Mem0
  returns the k nearest of those and every more relevant row is cut.
  The block is the part of those k rows the sharing convention keeps,
  so a hidden row still takes a slot. "Evidence" (below) shows this in
  the v2 smoke.
- **Install.** The agents run the pinned `mem0ai` without its `[nlp]`
  extra, so spaCy is absent: Mem0 logs "Failed to load spaCy" and its
  search adds no entity boosts (BM25 is off either way, since Chroma has
  no keyword search). This is Mem0's default install; whether the
  native baseline should run with the extra is an open decision
  (`DEV_STATUS.md`). The extra would not fix the ranking above: Mem0's
  entity code reads Chroma distances as similarities too.
- **Conversation.** `memory.add([user turn, assistant turn],
  user_id=<user>, agent_id="assistant_agent", metadata={..., memory_type:
  "conversation", sharing_policy: "private"}, infer=True)`.

## native_inhouse

There is no vendor SDK for the in-house backend, so the convention is
the minimal one a careful developer would write on Chroma
([query and get](https://docs.trychroma.com/docs/querying-collections/query-and-get),
[add data](https://docs.trychroma.com/docs/collections/add-data),
[distance functions](https://docs.trychroma.com/docs/collections/configure)):

- **Store.** One `chromadb.PersistentClient` at
  `.native_memory/native_inhouse/chroma`; one collection per user,
  `native_<user>`, created with `{"hnsw": {"space": "cosine"}}`, the same
  partitioning as the kernel's in-house provider.
- **Embedding.** Each agent embeds with the pinned model by the same
  Ollama call as the kernel (`ollama.Client.embed`) and passes the
  vectors to Chroma.
- **Writers.** `collection.add(ids=[uuid], documents=[<memory text>],
  embeddings=[...], metadatas=[{owner_agent, user_id, memory_type,
  sharing_policy, created_at}])`. Stored verbatim: no extraction, no LLM.
- **AssistantAgent.** `collection.query(query_embeddings=[...],
  n_results=min(k, count), where={"user_id": <user>},
  include=["documents", "metadatas", "distances"])`, score `1 -
  distance` (cosine), then the sharing convention.
- **Conversation.** Written verbatim as `User: ... Assistant: ...`,
  private.

## Mem0 extraction check

Run before any agent code, 2026-11-02, on 20 real writer outputs: the
profile and task-context memories `ProfileAgent` and `TaskAgent` stored
for 10 random Subtask 3 users (read from the kernel's Mem0 store). Each
was added with `infer=True` to a fresh Mem0 store under each candidate
internal LLM, once as the stored JSON and once rendered as natural
language, and read back with `get_all`. Coverage is the share of the
writer's key values (name, each tool, language, style; project,
experiment, each goal, blocker and next step) found in what Mem0 stored.
Script and per-memory output: Cerebrum
`results/native_extraction_check/`.

| Internal LLM | Input | Stored nothing | Rows per write | Profile coverage | Task coverage | Seconds per write |
|---|---|---:|---:|---:|---:|---:|
| gpt-4o (Azure) | JSON | 0 / 20 | 3.7 | 1.00 | 1.00 | 1.9 |
| gpt-4o (Azure) | natural language | 0 / 20 | 3.5 | 1.00 | 1.00 | 1.9 |
| qwen2.5:7b | JSON | 0 / 20 | 3.8 | 0.85 | 0.80 | 13.0 |
| qwen2.5:7b | natural language | 0 / 20 | 5.1 | 0.98 | 0.91 | 16.3 |
| llama3.1:8b | JSON | 0 / 20 | 4.2 | 0.95 | 0.98 | 20.2 |
| llama3.1:8b | natural language | 0 / 20 | 4.5 | 1.00 | 0.92 | 18.7 |

Mem0 kept the `metadata` on every extracted memory in every
configuration. No configuration stored nothing and none mangled the
JSON; the local models lost facts (qwen2.5:7b with JSON input usually
dropped the user's name) and took 7-10 times longer.

Choices:

- **Internal LLM: gpt-4o** on Azure, pinned as `memory.backend_llm`,
  separate from the assistant model in every cell. The only model that
  kept every fact. Its cost is reported separately
  (`backend_llm_tokens`, Subtask 7). LiteLLM reads the Azure
  credentials from the same `AZURE_API_KEY`, `AZURE_API_BASE` and
  `AZURE_API_VERSION` variables as the kernel.
- **Input: natural language.** JSON passed with gpt-4o too, but Mem0's
  documentation shows conversational messages, natural language held up
  better on weaker extractors, and it lets both native conditions store
  the same text. 2 of the 20 profiles and 2 of the 20 task contexts used
  other keys than the schema's (`username`, `tools`, `project_name`,
  `next_actions`, or everything nested under one key), so the renderer
  maps those aliases, unwraps a single nested object and keeps unknown
  keys as `<key>: <value>` sentences (`native/render.py`). Since
  Subtask 9 this renderer is the one shared by every writer, kernel and
  replicated too (`shared_memory_utils.render`), applied after schema
  validation: unknown keys are dropped, and an extraction that does not
  validate after two retries is not stored at all.

**Writer to consumer, 5 users** (gpt-4o, natural language, Mem0 2.0.2,
three separate `Memory` clients on one store): for each user the profile
and task writers added their memories with their own `agent_id`, and the
task writer also added a private note. The assistant's search with
`filters={"user_id": ...}` only returned 8 memories per user, 4 from each
writer, so a `user_id`-only search does span agents. The private note
came back every time and the sharing convention removed it every time;
every user's name, tools, project and blockers were in the visible set.
Scores were Mem0's inverted ones: 5 to 7 of each user's 8 results scored
exactly 1.000.

Versions: the agents use `mem0ai` 2.0.2 (Cerebrum venv); the gpt-4o rows
above ran on 2.0.0 (AIOS venv) because the Cerebrum venv lacked
`azure-identity` at the time. The 5-user check ran on 2.0.2.

## Evidence: native Mem0's ranking

Added in Subtask 15 (step 0), from the benchmark v2 smoke (`s14b`,
H = 0; `BENCHMARK_V2.md`, `DEV_STATUS.md` Subtask 14), where native
Mem0 passed recall for 5 of 30 users and recency for none. It shows
that the consumer uses Mem0's results as Mem0 returns them, and that
Mem0's own order put each probe's relevant row below rows less similar
to the question.

**The consumer** keeps Mem0's order and acts on no score (Cerebrum
`cerebrum/example/agents/native/agents.py`):
- It asks Mem0 for k rows and keeps them in Mem0's order, each with its
  score (lines 196-211):

      results = self.mem0.search(
          query, filters={"user_id": user_id}, top_k=k
      )["results"]

- Its selection reads metadata only: the user's partition and the
  sharing convention (lines 473-480). The threshold and budget steps run
  only when `relevance_threshold` or `max_memory_tokens` is set (lines
  482 and 489), and both are None in the reference consumer (lines
  395-396). The cap is by position, `thresholded[:k]` (line 487).
- The block lists the kept rows in that order (lines 433-436). The
  diagnostics record each injected row's Mem0 score as `match_score`
  (line 640), and nothing acts on it.
- Only the V4 consumer, at H = 2, sets a threshold (0.5), by design
  (`variants/v4_tuned_consumer.py`, `HETEROGENEITY.md`). No H = 0 cell
  and no control sets one.
- Two tests pin this (Cerebrum `tests/agents/test_native_conditions.py`).
  `test_the_reference_consumer_keeps_the_backends_order` takes any rows,
  scores and k: the consumer keeps the rows it may see, in the backend's
  order, cut at k by position. `test_the_native_mem0_block_follows_mem0s_order`
  checks the block and the recorded scores. Both fail if the consumer
  sorts by score or applies Mem0's 0.1 threshold itself.

**Mem0's search**, as installed (`mem0ai` 2.0.2):
- `Memory.search(query, *, top_k=20, filters=None, threshold=0.1, ...)`
  (`mem0/memory/main.py:1126-1135`). The consumer passes no threshold,
  so Mem0 applies its default, 0.1.
- `_search_vector_store` takes the `max(limit * 4, 60)` rows nearest the
  question from Chroma (`main.py:1356-1359`). It adds no keyword score,
  since the Chroma adapter does not override `keyword_search`, whose
  base returns None (`vector_stores/base.py:60-75`). It adds no entity
  boost either: without spaCy, `extract_entities` returns `[]`
  (`utils/entity_extraction.py:137-141`).
- The Chroma adapter returns each row's distance as its score
  (`vector_stores/chroma.py:19`, `score: Optional[float]  # distance`,
  and line 102). It creates its collection without a distance space,
  so Chroma uses its default, squared L2 (lines 120-123).
- `score_and_rank` (`mem0/utils/scoring.py:60-121`) drops a row whose
  score is below the threshold (line 102). It caps the score at 1.0
  (line 110, `combined = min(raw_combined / max_possible, 1.0)`, with
  `max_possible` 1.0 here), sorts highest first (line 120) and returns
  the first `top_k` (line 121).

Ollama's embeddings are unit vectors: on every replayed row, the squared
distance equals 2 - 2 x cosine within 1e-6. So a row's Mem0 score is
min(2 - 2 x cosine, 1):
- every row at cosine 0.5 or below scores 1.0, and those rows come
  first, nearest first (the sort is stable, and Chroma returns rows
  nearest first);
- the rows above cosine 0.5 follow, least similar first;
- rows above cosine 0.95 score below 0.1, and the threshold drops them.

So the more similar a row is above cosine 0.5, the later Mem0 returns
it. Once k rows lie at 0.5 or below, Mem0 returns none of the rows
above it.

**Replay.** Cerebrum `results/native_mem0_ranking/replay.py` runs Mem0's
own search (through `NativeMemory.search`) and the consumer's own
selection. It runs them on a copy of the smoke's native Mem0 store,
rebuilt as it stood at each probe. Mem0's history holds only `ADD`
events and the revokes' `DELETE` events (1,020 and 30), so the store
at a probe is the final store without the rows written by that probe
and the later ones. Those are their conversation rows, which carry the
probe id as `provenance_event`.
- It replayed the recall, recency and contradiction probes of all 30
  users and reproduced the recorded fetch every time (90 of 90: the
  rows, their order and their scores).
- Every row's score was min(squared distance, 1). No row was near
  enough for the threshold to drop it.
- `replay.json` and `summary.md` are in the same folder.

The target row is the target event's own row, by `provenance_event`.

| Probe | n | Target nearest by cosine | Target in the fetch | Target's Mem0 rank, median (range) | Rows at 1.0 above it, median (range) | Target's cosine |
|---|---:|---:|---:|---|---|---|
| recall | 30 | 26 | 4 | 24.5 (1 to 29) | 21 (0 to 28) | 0.47 to 0.87 |
| recency | 30 | 15 | 1 | 26 (1 to 32) | 23 (0 to 30) | 0.50 to 0.85 |
| contradiction | 30 | 15 | 2 | 27.5 (2 to 34) | 23 (1 to 32) | 0.48 to 0.80 |

- **Recall.** The four users whose target reached the fetch (15, 21, 24
  and 27) passed. The fifth pass, user 0's, came through an earlier
  probe's stored answer (below).
- **Recency.** Only user 26's update row reached the fetch, and that
  probe failed too.

**Five users.** These are users 0 to 4, the first five, not chosen by
outcome. For each recall and recency probe, the table lists every row
Mem0 ranked above the target's row, with its rank, Mem0 score and
cosine, and what became of it:
- **in block:** the consumer showed it;
- **hidden:** fetched, but another agent's private row;
- **cut:** below the consumer's k.

In all ten probes, the target is the user's first, second or third row
by cosine, and Mem0 ranks it last or within two of last.

**User 0, recall** (`u000-p3-recall`): "Who do I report to?", expected
Greta Sandvik; passed, through an earlier probe's answer. 27 rows in the
store.

Target row: rank 27 of 27, Mem0 score 0.889, cosine 0.556 (rank 1 by
cosine): "Jordan McAllister reports to Greta Sandvik."

| Rank | Score | Cosine | Seen | Row |
|---:|---:|---:|---|---|
| 1 | 1.000 | 0.492 | in block | User sends issues related to their Weather Data API project to Rollbar for tracking and management. |
| 2 | 1.000 | 0.483 | in block | User is a member of the Ariamont choir and sings with them. |
| 3 | 1.000 | 0.476 | in block | User goes to a running club that gathers in Wychwood Park. |
| 4 | 1.000 | 0.465 | hidden | Ravelstone Security is attempting to recruit User's team lead, as mentioned off the record. |
| 5 | 1.000 | 0.464 | in block | User's team lead is Greta Sandvik, who supervises Jordan McAllister on the Weather Data API project. |
| 6 | 1.000 | 0.455 | in block | Jordan McAllister prefers formal responses in communication. |
| 7 | 1.000 | 0.450 | in block | User meets with Lena Fischbach one-on-one every week. |
| 8 | 1.000 | 0.450 | in block | User's name is Jordan McAllister. |
| 9 | 1.000 | 0.447 | in block | User was recommended Slack or Microsoft Teams for real-time communication and collaboration among team members, especially for complex projects like the Weather Data API. |
| 10 | 1.000 | 0.446 | in block | User's team is having a game night at Meeplehaus. |
| 11 | 1.000 | 0.444 | cut | User has a weekly one-on-one meeting with Sofia Lindqvist. |
| 12 | 1.000 | 0.444 | cut | User's team uses Rollbar for tracking and managing issues related to their Weather Data API project. |
| 13 | 1.000 | 0.436 | cut | User's next steps for their Weather Data API project are to investigate and fix preprocessing bugs, run the experiment on different weather datasets, collaborate with QA to validate data ingestion flows, and document findings from preprocessing tests. |
| 14 | 1.000 | 0.426 | cut | Jordan McAllister uses tools like Visual Studio Code, Docker, Git, and Postman for development and is focused on the Weather Data API project. His next steps include investigating preprocessing bugs, running experiments on weather datasets, collaborating with QA to validate data ingestion flows, and documenting findings from preprocessing tests. |
| 15 | 1.000 | 0.423 | cut | User's staging server for their Weather Data API project was relocated to bittern-06 as of November 9, 2026. |
| 16 | 1.000 | 0.416 | cut | User registered for the Brightnoon lunch talk series. |
| 17 | 1.000 | 0.413 | cut | User arranged the sprint retrospective to be held via a Mattermost call. |
| 18 | 1.000 | 0.409 | cut | User is enrolled in a nighttime class for calligraphy. |
| 19 | 1.000 | 0.406 | cut | User is working on a Weather Data API and is currently testing data preprocessing accuracy on hourly data ingestion. Their goals include ensuring the API handles large volumes of weather data efficiently, improving data preprocessing for better model predictions, and incorporating error handling for missing or corrupt data. |
| 20 | 1.000 | 0.404 | cut | User uses the tern-02 staging server for deployment in their Weather Data API project. |
| 21 | 1.000 | 0.398 | cut | User attends their book club gatherings at Hearth & Page. |
| 22 | 1.000 | 0.396 | cut | Jordan McAllister prefers to use Visual Studio Code, Docker, Git, and Postman for development. |
| 23 | 1.000 | 0.378 | cut | Jordan McAllister goes swimming at the Seabright club. |
| 24 | 1.000 | 0.377 | cut | Jordan McAllister's preferred programming language is Python. |
| 25 | 1.000 | 0.342 | cut | Jordan McAllister uses the Everforest color theme in their editor. |
| 26 | 1.000 | 0.328 | cut | User's current blockers in their Weather Data API project include an unexpected drop in predicted accuracy due to preprocessing bugs. |

**User 0, recency** (`u000-p4-recency`): "Which staging server do we
deploy to?", expected bittern-06, stale tern-02; failed. 28 rows in the
store.

Target row: rank 27 of 28, Mem0 score 0.724, cosine 0.638 (rank 2 by
cosine): "User's staging server for their Weather Data API project was
relocated to bittern-06 as of November 9, 2026."

| Rank | Score | Cosine | Seen | Row |
|---:|---:|---:|---|---|
| 1 | 1.000 | 0.475 | in block | Jordan McAllister prefers to use Visual Studio Code, Docker, Git, and Postman for development. |
| 2 | 1.000 | 0.461 | in block | User was recommended Slack or Microsoft Teams for real-time communication and collaboration among team members, especially for complex projects like the Weather Data API. |
| 3 | 1.000 | 0.461 | in block | User reports to Greta Sandvik, who is their team lead and supervises the Weather Data API project. |
| 4 | 1.000 | 0.460 | in block | User's team lead is Greta Sandvik, who supervises Jordan McAllister on the Weather Data API project. |
| 5 | 1.000 | 0.451 | hidden | Ravelstone Security is attempting to recruit User's team lead, as mentioned off the record. |
| 6 | 1.000 | 0.451 | in block | Jordan McAllister uses tools like Visual Studio Code, Docker, Git, and Postman for development and is focused on the Weather Data API project. His next steps include investigating preprocessing bugs, running experiments on weather datasets, collaborating with QA to validate data ingestion flows, and documenting findings from preprocessing tests. |
| 7 | 1.000 | 0.451 | in block | User's next steps for their Weather Data API project are to investigate and fix preprocessing bugs, run the experiment on different weather datasets, collaborate with QA to validate data ingestion flows, and document findings from preprocessing tests. |
| 8 | 1.000 | 0.444 | in block | User is working on a Weather Data API and is currently testing data preprocessing accuracy on hourly data ingestion. Their goals include ensuring the API handles large volumes of weather data efficiently, improving data preprocessing for better model predictions, and incorporating error handling for missing or corrupt data. |
| 9 | 1.000 | 0.439 | in block | User's team uses Rollbar for tracking and managing issues related to their Weather Data API project. |
| 10 | 1.000 | 0.437 | in block | User is a member of the Ariamont choir and sings with them. |
| 11 | 1.000 | 0.437 | cut | User sends issues related to their Weather Data API project to Rollbar for tracking and management. |
| 12 | 1.000 | 0.401 | cut | User's current blockers in their Weather Data API project include an unexpected drop in predicted accuracy due to preprocessing bugs. |
| 13 | 1.000 | 0.388 | cut | User's name is Jordan McAllister. |
| 14 | 1.000 | 0.383 | cut | Jordan McAllister reports to Greta Sandvik. |
| 15 | 1.000 | 0.372 | cut | Jordan McAllister uses the Everforest color theme in their editor. |
| 16 | 1.000 | 0.372 | cut | User goes to a running club that gathers in Wychwood Park. |
| 17 | 1.000 | 0.367 | cut | User has a weekly one-on-one meeting with Sofia Lindqvist. |
| 18 | 1.000 | 0.363 | cut | Jordan McAllister's preferred programming language is Python. |
| 19 | 1.000 | 0.362 | cut | User registered for the Brightnoon lunch talk series. |
| 20 | 1.000 | 0.362 | cut | User arranged the sprint retrospective to be held via a Mattermost call. |
| 21 | 1.000 | 0.352 | cut | Jordan McAllister prefers formal responses in communication. |
| 22 | 1.000 | 0.340 | cut | User attends their book club gatherings at Hearth & Page. |
| 23 | 1.000 | 0.338 | cut | User is enrolled in a nighttime class for calligraphy. |
| 24 | 1.000 | 0.319 | cut | User meets with Lena Fischbach one-on-one every week. |
| 25 | 1.000 | 0.307 | cut | Jordan McAllister goes swimming at the Seabright club. |
| 26 | 0.998 | 0.501 | cut | User's team is having a game night at Meeplehaus. |

**User 1, recall** (`u001-p3-recall`): "Who am I pairing with on my
project?", expected Jonas Albrecht; failed. 25 rows in the store.

Target row: rank 25 of 25, Mem0 score 0.754, cosine 0.623 (rank 1 by
cosine): "User is pairing with Jonas Albrecht for their Dynamic Website
Optimization project."

| Rank | Score | Cosine | Seen | Row |
|---:|---:|---:|---|---|
| 1 | 1.000 | 0.499 | in block | Alex Carter prefers to use Visual Studio Code, Docker, Git, and Postman for development. |
| 2 | 1.000 | 0.492 | in block | User's team stores their design documents in Slite. |
| 3 | 1.000 | 0.491 | in block | User is working on Dynamic Website Optimization and is currently experimenting with caching mechanisms using Flask and Redis. Their goals include improving website load times, ensuring caching implementation reduces server load, evaluating the scalability of the caching solution, and documenting all results for future reference. |
| 4 | 1.000 | 0.484 | in block | User's name is Alex Carter. |
| 5 | 1.000 | 0.472 | hidden | User needs to see Dr. Okafor for a confidential follow-up appointment. |
| 6 | 1.000 | 0.462 | in block | Alex Carter's preferred programming language is Python. |
| 7 | 1.000 | 0.449 | in block | Alex Carter spends weekends playing Everdell with their friends. |
| 8 | 1.000 | 0.446 | in block | User's team offsite has been relocated to Kaunas. |
| 9 | 1.000 | 0.444 | in block | User's Dynamic Website Optimization project stores service information in TimescaleDB. |
| 10 | 1.000 | 0.437 | in block | Alex Carter reports to Lena Fischbach. |
| 11 | 1.000 | 0.426 | cut | Alex Carter uses the Solarized color theme in their editor. |
| 12 | 1.000 | 0.423 | cut | User goes to Fernbrook Park for their running club meetings. |
| 13 | 1.000 | 0.415 | cut | User volunteers at the Oakwell food bank. |
| 14 | 1.000 | 0.391 | cut | Alex Carter gets their coffee beans from Cinderbean. |
| 15 | 1.000 | 0.390 | cut | Alex Carter's terminal font is set to Monospace. |
| 16 | 1.000 | 0.383 | cut | Alex Carter goes swimming at the Marlowe club. |
| 17 | 1.000 | 0.363 | cut | Alex Carter prefers formal responses in communication. |
| 18 | 0.990 | 0.505 | cut | User's next steps for Dynamic Website Optimization include debugging integration issues with Redis, assessing load time improvements using test cases, scaling the implementation for different user loads, and preparing documentation to share findings with their team. |
| 19 | 0.987 | 0.506 | cut | User was recommended potential codenames for the Dynamic Website Optimization project, including 'SpeedBoost,' 'CacheMaster,' and 'LoadLight,' reflecting optimization and caching themes. |
| 20 | 0.978 | 0.511 | cut | User's manager is named Elif Kaya. |
| 21 | 0.954 | 0.523 | cut | User's team is having its offsite in Utrecht. |
| 22 | 0.946 | 0.527 | cut | User is facing a blocker in integrating Redis with their existing Flask application while working on Dynamic Website Optimization. |
| 23 | 0.885 | 0.558 | cut | User is working on the Dynamic Website Optimization project with Jonas Albrecht and is currently focused on debugging integration issues with Redis, assessing load time improvements, scaling the implementation, and preparing documentation. |
| 24 | 0.868 | 0.566 | cut | User was suggested to discuss assigning an internal codename for the Dynamic Website Optimization project with Jonas Albrecht or Elif Kaya to streamline communication. |

**User 1, recency** (`u001-p4-recency`): "Where is the team offsite?",
expected Kaunas, stale Utrecht; failed. 28 rows in the store.

Target row: rank 28 of 28, Mem0 score 0.503, cosine 0.749 (rank 1 by
cosine): "User's team offsite has been relocated to Kaunas."

| Rank | Score | Cosine | Seen | Row |
|---:|---:|---:|---|---|
| 1 | 1.000 | 0.499 | in block | User goes to Fernbrook Park for their running club meetings. |
| 2 | 1.000 | 0.483 | in block | User was recommended to reach out to Lena Fischbach, who reports to them, for details about team composition or pairing arrangements for the Dynamic Website Optimization project. |
| 3 | 1.000 | 0.471 | in block | User's team stores their design documents in Slite. |
| 4 | 1.000 | 0.448 | in block | Alex Carter spends weekends playing Everdell with their friends. |
| 5 | 1.000 | 0.413 | in block | User is pairing with Jonas Albrecht for their Dynamic Website Optimization project. |
| 6 | 1.000 | 0.412 | in block | User's manager is named Elif Kaya. |
| 7 | 1.000 | 0.408 | in block | User volunteers at the Oakwell food bank. |
| 8 | 1.000 | 0.404 | in block | User is working on the Dynamic Website Optimization project and uses tools like Visual Studio Code, Docker, Git, and Postman, with design documents stored in Slite. |
| 9 | 1.000 | 0.398 | in block | User's Dynamic Website Optimization project stores service information in TimescaleDB. |
| 10 | 1.000 | 0.397 | in block | User's name is Alex Carter. |
| 11 | 1.000 | 0.395 | cut | Alex Carter goes swimming at the Marlowe club. |
| 12 | 1.000 | 0.392 | cut | User is working on the Dynamic Website Optimization project with Jonas Albrecht and is currently focused on debugging integration issues with Redis, assessing load time improvements, scaling the implementation, and preparing documentation. |
| 13 | 1.000 | 0.391 | cut | Alex Carter reports to Lena Fischbach. |
| 14 | 1.000 | 0.391 | cut | User's next steps for Dynamic Website Optimization include debugging integration issues with Redis, assessing load time improvements using test cases, scaling the implementation for different user loads, and preparing documentation to share findings with their team. |
| 15 | 1.000 | 0.381 | cut | User was suggested to discuss assigning an internal codename for the Dynamic Website Optimization project with Jonas Albrecht or Elif Kaya to streamline communication. |
| 16 | 1.000 | 0.378 | cut | Alex Carter gets their coffee beans from Cinderbean. |
| 17 | 1.000 | 0.370 | cut | User needs to see Dr. Okafor for a confidential follow-up appointment. |
| 18 | 1.000 | 0.370 | cut | Alex Carter's terminal font is set to Monospace. |
| 19 | 1.000 | 0.367 | cut | Alex Carter prefers to use Visual Studio Code, Docker, Git, and Postman for development. |
| 20 | 1.000 | 0.356 | cut | User is working on Dynamic Website Optimization and is currently experimenting with caching mechanisms using Flask and Redis. Their goals include improving website load times, ensuring caching implementation reduces server load, evaluating the scalability of the caching solution, and documenting all results for future reference. |
| 21 | 1.000 | 0.353 | cut | User is facing a blocker in integrating Redis with their existing Flask application while working on Dynamic Website Optimization. |
| 22 | 1.000 | 0.352 | cut | User was recommended potential codenames for the Dynamic Website Optimization project, including 'SpeedBoost,' 'CacheMaster,' and 'LoadLight,' reflecting optimization and caching themes. |
| 23 | 1.000 | 0.336 | cut | Alex Carter uses the Solarized color theme in their editor. |
| 24 | 1.000 | 0.314 | cut | Alex Carter's preferred programming language is Python. |
| 25 | 1.000 | 0.308 | cut | Alex Carter prefers formal responses in communication. |
| 26 | 0.936 | 0.532 | cut | User was suggested to check the project repository, team's communication channels like Slack or Microsoft Teams, or the project's issue tracker to identify team members or pairing arrangements for the Dynamic Website Optimization project. |
| 27 | 0.519 | 0.741 | cut | User's team is having its offsite in Utrecht. |

**User 2, recall** (`u002-p3-recall`): "Which room is my weekly team
sync in?", expected Larch; failed. 24 rows in the store.

Target row: rank 24 of 24, Mem0 score 0.481, cosine 0.760 (rank 1 by
cosine): "User's team holds their weekly sync meetings in the Larch
room"

| Rank | Score | Cosine | Seen | Row |
|---:|---:|---:|---|---|
| 1 | 1.000 | 0.485 | in block | User attends their book club gatherings at Bookhaven |
| 2 | 1.000 | 0.482 | in block | Elena Martinez spends her weekends playing Wingspan with her friends. |
| 3 | 1.000 | 0.455 | in block | User is focused on optimizing the Data Analysis Pipeline project for Vantrell Aerospace, which includes tasks such as investigating memory management solutions for Python, testing the pipeline's performance on diverse data sizes, and documenting optimization steps. |
| 4 | 1.000 | 0.448 | in block | User is working on the Data Analysis Pipeline project for Vantrell Aerospace. |
| 5 | 1.000 | 0.433 | in block | User works with DuckDB for storing service information. |
| 6 | 1.000 | 0.431 | in block | User's work is monitored using Taiga. |
| 7 | 1.000 | 0.426 | in block | User's name is Elena Martinez. |
| 8 | 1.000 | 0.420 | in block | User is facing unexpected memory issues during parallel processing as a blocker in their Data Analysis Pipeline project. |
| 9 | 1.000 | 0.417 | in block | User's Data Analysis Pipeline project stores service information in DuckDB. |
| 10 | 1.000 | 0.411 | in block | User's Data Analysis Pipeline project is being developed for Vantrell Aerospace. |
| 11 | 1.000 | 0.409 | cut | User's next steps for their Data Analysis Pipeline project include investigating memory management solutions for Python, testing pipeline performance on diverse data sizes, and documenting steps taken to optimize the code. |
| 12 | 1.000 | 0.406 | cut | Elena Martinez is working on a project for a client named Halcyon Robotics. |
| 13 | 1.000 | 0.403 | cut | Elena Martinez prefers to use Visual Studio Code, Docker, and GitHub for development. |
| 14 | 1.000 | 0.391 | cut | Elena Martinez's preferred programming language is Python. |
| 15 | 1.000 | 0.386 | cut | Elena Martinez is working on a startup named Thistledown as a side project and has requested to keep this information private. |
| 16 | 1.000 | 0.375 | cut | User is working on a Data Analysis Pipeline and is currently optimizing Python scripts for parallel processing. Their goals include improving data processing speed by 30%, ensuring compatibility with large datasets, and developing robust error handling in the pipeline. |
| 17 | 1.000 | 0.375 | cut | User's Data Analysis Pipeline project stores confidential information in Akeyless. |
| 18 | 1.000 | 0.359 | cut | Elena Martinez likes detailed responses. |
| 19 | 1.000 | 0.351 | cut | User's Data Analysis Pipeline project uses Buildkite for continuous integration (CI). |
| 20 | 0.993 | 0.503 | cut | Elena Martinez uses Ryver to chat with her team. |
| 21 | 0.923 | 0.539 | cut | User mentioned using Brosix for team chats and Visual Studio Code for development. |
| 22 | 0.919 | 0.541 | cut | User enjoys playing Wingspan with friends on weekends as a hobby. |
| 23 | 0.843 | 0.579 | cut | Elena Martinez's team chat has been moved to Brosix. |

**User 2, recency** (`u002-p4-recency`): "Which chat app does my team
use?", expected Brosix, stale Ryver; failed. 25 rows in the store.

Target row: rank 25 of 25, Mem0 score 0.638, cosine 0.681 (rank 1 by
cosine): "Elena Martinez's team chat has been moved to Brosix."

| Rank | Score | Cosine | Seen | Row |
|---:|---:|---:|---|---|
| 1 | 1.000 | 0.495 | in block | User enjoys playing Wingspan with friends on weekends as a hobby. |
| 2 | 1.000 | 0.487 | in block | User's name is Elena Martinez. |
| 3 | 1.000 | 0.481 | in block | Elena Martinez prefers to use Visual Studio Code, Docker, and GitHub for development. |
| 4 | 1.000 | 0.473 | in block | User is working on the Data Analysis Pipeline project for Vantrell Aerospace. |
| 5 | 1.000 | 0.471 | in block | User works with DuckDB for storing service information. |
| 6 | 1.000 | 0.469 | in block | User is focused on optimizing the Data Analysis Pipeline project for Vantrell Aerospace, which includes tasks such as investigating memory management solutions for Python, testing the pipeline's performance on diverse data sizes, and documenting optimization steps. |
| 7 | 1.000 | 0.468 | in block | User's work is monitored using Taiga. |
| 8 | 1.000 | 0.464 | in block | User's Data Analysis Pipeline project stores service information in DuckDB. |
| 9 | 1.000 | 0.464 | in block | Elena Martinez is working on a project for a client named Halcyon Robotics. |
| 10 | 1.000 | 0.457 | in block | Elena Martinez's preferred programming language is Python. |
| 11 | 1.000 | 0.456 | cut | Elena Martinez spends her weekends playing Wingspan with her friends. |
| 12 | 1.000 | 0.455 | cut | Elena Martinez is working on a startup named Thistledown as a side project and has requested to keep this information private. |
| 13 | 1.000 | 0.455 | cut | User's Data Analysis Pipeline project is being developed for Vantrell Aerospace. |
| 14 | 1.000 | 0.451 | cut | User attends their book club gatherings at Bookhaven |
| 15 | 1.000 | 0.440 | cut | User's Data Analysis Pipeline project stores confidential information in Akeyless. |
| 16 | 1.000 | 0.434 | cut | User's Data Analysis Pipeline project uses Buildkite for continuous integration (CI). |
| 17 | 1.000 | 0.429 | cut | User's next steps for their Data Analysis Pipeline project include investigating memory management solutions for Python, testing pipeline performance on diverse data sizes, and documenting steps taken to optimize the code. |
| 18 | 1.000 | 0.421 | cut | Elena Martinez likes detailed responses. |
| 19 | 1.000 | 0.401 | cut | User is working on a Data Analysis Pipeline and is currently optimizing Python scripts for parallel processing. Their goals include improving data processing speed by 30%, ensuring compatibility with large datasets, and developing robust error handling in the pipeline. |
| 20 | 1.000 | 0.376 | cut | User is facing unexpected memory issues during parallel processing as a blocker in their Data Analysis Pipeline project. |
| 21 | 0.883 | 0.558 | cut | User's team holds their weekly sync meetings in the Larch room |
| 22 | 0.811 | 0.595 | cut | User's weekly team sync details, including the room or virtual meeting link, are typically recorded in the Taiga project management tool. |
| 23 | 0.698 | 0.651 | cut | Elena Martinez uses Ryver to chat with her team. |
| 24 | 0.657 | 0.671 | cut | User mentioned using Brosix for team chats and Visual Studio Code for development. |

**User 3, recall** (`u003-p3-recall`): "Which city do I live in?",
expected Uppsala; failed. 29 rows in the store.

Target row: rank 29 of 29, Mem0 score 0.907, cosine 0.546 (rank 1 by
cosine): "User's home is in Uppsala."

| Rank | Score | Cosine | Seen | Row |
|---:|---:|---:|---|---|
| 1 | 1.000 | 0.466 | in block | User's name is Jordan Michaels. |
| 2 | 1.000 | 0.437 | in block | User is a member of the Lyrebird choir and sings with them. |
| 3 | 1.000 | 0.432 | in block | User prefers to use GitHub, Visual Studio Code, and Postman for development. |
| 4 | 1.000 | 0.424 | in block | User is giving a presentation at Fjordstack, which is the only conference where they are presenting. |
| 5 | 1.000 | 0.418 | in block | User's preferred programming language is JavaScript. |
| 6 | 1.000 | 0.417 | in block | User has a yoga session scheduled at the Lotusgate studio on November 9, 2026. |
| 7 | 1.000 | 0.411 | in block | User attends a running club that gathers in Wychwood Park. |
| 8 | 1.000 | 0.403 | in block | User is giving a presentation at Fjordstack in December 2026 and is currently focused on the Dynamic Form Builder project. |
| 9 | 1.000 | 0.400 | in block | User attends book club gatherings at Bookhaven. |
| 10 | 1.000 | 0.391 | in block | User spends weekends playing Carcassonne with their friends. |
| 11 | 1.000 | 0.389 | cut | User uses the Halmak layout for typing on their keyboard. |
| 12 | 1.000 | 0.387 | cut | User's staging server for deployment was relocated to wren-04 on November 9, 2026. |
| 13 | 1.000 | 0.370 | cut | The talk 'Real-Time Analytics for Dynamic Form Builder' will cover tools and techniques for real-time data collection, analysis, and visualization to optimize performance for real-time form rendering. |
| 14 | 1.000 | 0.368 | cut | User likes concise responses. |
| 15 | 1.000 | 0.367 | cut | User is working on a Dynamic Form Builder project and is currently experimenting with testing dynamic field rendering based on user inputs. |
| 16 | 1.000 | 0.366 | cut | User uses the avocet-06 staging server for deployment in their Dynamic Form Builder project. |
| 17 | 1.000 | 0.356 | cut | User volunteers at the Stonebridge food bank. |
| 18 | 1.000 | 0.352 | cut | User's goals for the Dynamic Form Builder project include developing a reusable component for dynamic form creation, ensuring seamless integration with backend APIs, and optimizing performance for real-time form rendering. |
| 19 | 1.000 | 0.350 | cut | User will be giving a presentation at Kernelcon in December 2026. |
| 20 | 1.000 | 0.340 | cut | User's next steps for the Dynamic Form Builder project are to refactor the dynamic rendering logic using React hooks, investigate and address API latency issues, and write unit tests for form validation rules. |
| 21 | 1.000 | 0.335 | cut | User's company is having preliminary discussions about being bought by Gannet Systems. |
| 22 | 1.000 | 0.334 | cut | User gets their coffee beans from Hollowpeak. |
| 23 | 1.000 | 0.333 | cut | User was recommended the following acquisition talks relevant to their Dynamic Form Builder project: 'Scaling User Acquisition with Data-Driven Strategies', 'User-Centric Acquisition: Building Trust and Engagement', 'Leveraging APIs for Seamless Integration and User Acquisition', and 'Real-Time Analytics for Dynamic Form Builder'. |
| 24 | 1.000 | 0.324 | cut | User sends their logs to Logtail for the Dynamic Form Builder project |
| 25 | 1.000 | 0.318 | cut | The talk 'User-Centric Acquisition: Building Trust and Engagement' will focus on creating engaging content, designing intuitive user interfaces, and fostering a community around a product or service. |
| 26 | 1.000 | 0.299 | cut | The talk 'Leveraging APIs for Seamless Integration and User Acquisition' will explore best practices for API design, security, and performance optimization to enhance user experience and drive acquisition. |
| 27 | 1.000 | 0.296 | cut | The talk 'Scaling User Acquisition with Data-Driven Strategies' will cover data analytics, A/B testing, user segmentation, and leveraging social media and SEO for effective user acquisition. |
| 28 | 1.000 | 0.294 | cut | User's blockers for the Dynamic Form Builder project include intermittent API response delays. |

**User 3, recency** (`u003-p4-recency`): "Which staging server do we
deploy to?", expected wren-04, stale avocet-06; failed. 29 rows in the
store.

Target row: rank 29 of 29, Mem0 score 0.535, cosine 0.733 (rank 1 by
cosine): "User's staging server for deployment was relocated to wren-04
on November 9, 2026."

| Rank | Score | Cosine | Seen | Row |
|---:|---:|---:|---|---|
| 1 | 1.000 | 0.486 | in block | User prefers to use GitHub, Visual Studio Code, and Postman for development. |
| 2 | 1.000 | 0.480 | in block | User's home is in Uppsala. |
| 3 | 1.000 | 0.469 | in block | User is giving a presentation at Fjordstack in December 2026 and is currently focused on the Dynamic Form Builder project. |
| 4 | 1.000 | 0.457 | hidden | User's company is having preliminary discussions about being bought by Gannet Systems. |
| 5 | 1.000 | 0.453 | in block | User has a yoga session scheduled at the Lotusgate studio on November 9, 2026. |
| 6 | 1.000 | 0.451 | in block | User's next steps for the Dynamic Form Builder project are to refactor the dynamic rendering logic using React hooks, investigate and address API latency issues, and write unit tests for form validation rules. |
| 7 | 1.000 | 0.445 | in block | User is a member of the Lyrebird choir and sings with them. |
| 8 | 1.000 | 0.445 | in block | The talk 'Leveraging APIs for Seamless Integration and User Acquisition' will explore best practices for API design, security, and performance optimization to enhance user experience and drive acquisition. |
| 9 | 1.000 | 0.432 | in block | User is working on a Dynamic Form Builder project and is currently experimenting with testing dynamic field rendering based on user inputs. |
| 10 | 1.000 | 0.421 | in block | The talk 'Real-Time Analytics for Dynamic Form Builder' will cover tools and techniques for real-time data collection, analysis, and visualization to optimize performance for real-time form rendering. |
| 11 | 1.000 | 0.417 | cut | The talk 'Scaling User Acquisition with Data-Driven Strategies' will cover data analytics, A/B testing, user segmentation, and leveraging social media and SEO for effective user acquisition. |
| 12 | 1.000 | 0.415 | cut | User will be giving a presentation at Kernelcon in December 2026. |
| 13 | 1.000 | 0.409 | cut | User's goals for the Dynamic Form Builder project include developing a reusable component for dynamic form creation, ensuring seamless integration with backend APIs, and optimizing performance for real-time form rendering. |
| 14 | 1.000 | 0.399 | cut | The talk 'User-Centric Acquisition: Building Trust and Engagement' will focus on creating engaging content, designing intuitive user interfaces, and fostering a community around a product or service. |
| 15 | 1.000 | 0.398 | cut | User's name is Jordan Michaels. |
| 16 | 1.000 | 0.393 | cut | User volunteers at the Stonebridge food bank. |
| 17 | 1.000 | 0.391 | cut | User's blockers for the Dynamic Form Builder project include intermittent API response delays. |
| 18 | 1.000 | 0.388 | cut | User was recommended the following acquisition talks relevant to their Dynamic Form Builder project: 'Scaling User Acquisition with Data-Driven Strategies', 'User-Centric Acquisition: Building Trust and Engagement', 'Leveraging APIs for Seamless Integration and User Acquisition', and 'Real-Time Analytics for Dynamic Form Builder'. |
| 19 | 1.000 | 0.387 | cut | User gets their coffee beans from Hollowpeak. |
| 20 | 1.000 | 0.386 | cut | User's preferred programming language is JavaScript. |
| 21 | 1.000 | 0.384 | cut | User uses the Halmak layout for typing on their keyboard. |
| 22 | 1.000 | 0.383 | cut | User spends weekends playing Carcassonne with their friends. |
| 23 | 1.000 | 0.383 | cut | User sends their logs to Logtail for the Dynamic Form Builder project |
| 24 | 1.000 | 0.348 | cut | User attends a running club that gathers in Wychwood Park. |
| 25 | 1.000 | 0.337 | cut | User attends book club gatherings at Bookhaven. |
| 26 | 1.000 | 0.328 | cut | User likes concise responses. |
| 27 | 0.996 | 0.502 | cut | User is giving a presentation at Fjordstack, which is the only conference where they are presenting. |
| 28 | 0.652 | 0.674 | cut | User uses the avocet-06 staging server for deployment in their Dynamic Form Builder project. |

**User 4, recall** (`u004-p3-recall`): "Who is the client for my current
project?", expected Gannet Systems; failed. 29 rows in the store.

Target row: rank 27 of 29, Mem0 score 0.817, cosine 0.592 (rank 3 by
cosine): "User is developing the SmartWeather project for Gannet
Systems."

| Rank | Score | Cosine | Seen | Row |
|---:|---:|---:|---|---|
| 1 | 1.000 | 0.498 | in block | User is enrolled in a nighttime class for calligraphy. |
| 2 | 1.000 | 0.488 | in block | Michael Peterson's preferred programming language is Python. |
| 3 | 1.000 | 0.480 | in block | User lives in Dunedin. |
| 4 | 1.000 | 0.467 | in block | User's weekly team sync is held in the Saffron room. |
| 5 | 1.000 | 0.456 | in block | User's weekly team sync has been relocated to the Larch room. |
| 6 | 1.000 | 0.451 | in block | Michael Peterson's home is in Leuven. |
| 7 | 1.000 | 0.446 | in block | User helps out at the Maplewood food bank. |
| 8 | 1.000 | 0.432 | in block | Michael Peterson prefers using Elvish as his shell. |
| 9 | 1.000 | 0.415 | in block | User attends running club gatherings in Larkfield Park. |
| 10 | 1.000 | 0.405 | in block | Michael Peterson goes swimming at Kingsmere. |
| 11 | 1.000 | 0.402 | cut | Michael Peterson gets his coffee beans from Mossgrove. |
| 12 | 1.000 | 0.378 | cut | Michael Peterson uses the Engram keyboard layout for typing. |
| 13 | 1.000 | 0.370 | cut | Michael Peterson prefers concise responses. |
| 14 | 0.993 | 0.503 | cut | User sends logs for the SmartWeather project to Papertrail for monitoring and analysis. |
| 15 | 0.978 | 0.511 | cut | User stores service information for the SmartWeather project in TimescaleDB. |
| 16 | 0.954 | 0.523 | cut | User's current blockers in the SmartWeather project include API inconsistencies in returned data formats. |
| 17 | 0.950 | 0.525 | cut | Michael Peterson prefers to use Visual Studio Code, JIRA, and Docker for development. |
| 18 | 0.944 | 0.528 | cut | User is working on SmartWeather, focusing on testing machine learning-based predictive models for hourly rainfall. Their goals include optimizing the accuracy of rainfall predictions, integrating real-time weather data APIs, and refining the model for lower latency calculations. |
| 19 | 0.931 | 0.535 | cut | User's issues in the SmartWeather project are sent to Rollbar for tracking and resolution. |
| 20 | 0.908 | 0.546 | cut | User's name is Michael Peterson. |
| 21 | 0.906 | 0.547 | cut | User's next steps for the SmartWeather project are analyzing model performance with historical weather data, resolving API inconsistencies through better exception handling, deploying the trial version for internal testing with real-time data, and documenting findings for stakeholder review. |
| 22 | 0.905 | 0.547 | cut | User's next steps for the SmartWeather project include analyzing model performance using tools like Jupyter Notebook, Pandas, and Scikit-learn, resolving API inconsistencies with tools like Postman and Rollbar, deploying a trial version for internal testing with real-time data, and documenting findings using tools like Confluence or Google Docs for stakeholder review. |
| 23 | 0.902 | 0.549 | cut | User's next steps for the SmartWeather project include analyzing model performance, deploying a trial version for internal testing, and documenting findings for stakeholder review. |
| 24 | 0.890 | 0.555 | cut | User's current project, SmartWeather, has API inconsistencies that need to be resolved through better exception handling and data validation processes. |
| 25 | 0.875 | 0.562 | cut | User is scheduled for a pairing session with Greta Sandvik during the week of November 9, 2026. |
| 26 | 0.819 | 0.590 | cut | User is meeting their lawyer, Ewan Calloway, in December 2026 and has requested this information to remain private. |

**User 4, recency** (`u004-p4-recency`): "Which room is my weekly team
sync in?", expected Larch, stale Saffron; failed. 29 rows in the store.

Target row: rank 28 of 29, Mem0 score 0.303, cosine 0.849 (rank 2 by
cosine): "User's weekly team sync has been relocated to the Larch room."

| Rank | Score | Cosine | Seen | Row |
|---:|---:|---:|---|---|
| 1 | 1.000 | 0.494 | in block | User is enrolled in a nighttime class for calligraphy. |
| 2 | 1.000 | 0.458 | in block | User's name is Michael Peterson and they are working on the SmartWeather project for Gannet Systems, which involves analyzing model performance with historical weather data, resolving API inconsistencies through better exception handling, deploying a trial version for internal testing with real-time data, and documenting findings for stakeholder review. |
| 3 | 1.000 | 0.455 | in block | User's issues in the SmartWeather project are sent to Rollbar for tracking and resolution. |
| 4 | 1.000 | 0.452 | in block | Michael Peterson uses the Engram keyboard layout for typing. |
| 5 | 1.000 | 0.447 | in block | User is developing the SmartWeather project for Gannet Systems. |
| 6 | 1.000 | 0.445 | in block | User is working on the SmartWeather project, which involves tasks such as analyzing model performance with historical weather data, resolving API inconsistencies through better exception handling, deploying a trial version for internal testing with real-time data, and documenting findings for stakeholder review. |
| 7 | 1.000 | 0.443 | in block | User's name is Michael Peterson. |
| 8 | 1.000 | 0.440 | in block | User stores service information for the SmartWeather project in TimescaleDB. |
| 9 | 1.000 | 0.440 | in block | User is working on SmartWeather, focusing on testing machine learning-based predictive models for hourly rainfall. Their goals include optimizing the accuracy of rainfall predictions, integrating real-time weather data APIs, and refining the model for lower latency calculations. |
| 10 | 1.000 | 0.437 | in block | Michael Peterson's home is in Leuven. |
| 11 | 1.000 | 0.431 | cut | User lives in Dunedin. |
| 12 | 1.000 | 0.426 | cut | User's next steps for the SmartWeather project include analyzing model performance using tools like Jupyter Notebook, Pandas, and Scikit-learn, resolving API inconsistencies with tools like Postman and Rollbar, deploying a trial version for internal testing with real-time data, and documenting findings using tools like Confluence or Google Docs for stakeholder review. |
| 13 | 1.000 | 0.426 | cut | Michael Peterson prefers to use Visual Studio Code, JIRA, and Docker for development. |
| 14 | 1.000 | 0.426 | cut | User's next steps for the SmartWeather project are analyzing model performance with historical weather data, resolving API inconsistencies through better exception handling, deploying the trial version for internal testing with real-time data, and documenting findings for stakeholder review. |
| 15 | 1.000 | 0.425 | cut | User helps out at the Maplewood food bank. |
| 16 | 1.000 | 0.423 | cut | User's current blockers in the SmartWeather project include API inconsistencies in returned data formats. |
| 17 | 1.000 | 0.411 | cut | User's next steps for the SmartWeather project include analyzing model performance, deploying a trial version for internal testing, and documenting findings for stakeholder review. |
| 18 | 1.000 | 0.404 | cut | User sends logs for the SmartWeather project to Papertrail for monitoring and analysis. |
| 19 | 1.000 | 0.399 | cut | User's current project, SmartWeather, has API inconsistencies that need to be resolved through better exception handling and data validation processes. |
| 20 | 1.000 | 0.397 | cut | Michael Peterson's preferred programming language is Python. |
| 21 | 1.000 | 0.391 | cut | Michael Peterson gets his coffee beans from Mossgrove. |
| 22 | 1.000 | 0.389 | cut | User is meeting their lawyer, Ewan Calloway, in December 2026 and has requested this information to remain private. |
| 23 | 1.000 | 0.371 | cut | Michael Peterson goes swimming at Kingsmere. |
| 24 | 1.000 | 0.348 | cut | Michael Peterson prefers concise responses. |
| 25 | 1.000 | 0.328 | cut | Michael Peterson prefers using Elvish as his shell. |
| 26 | 0.999 | 0.501 | cut | User attends running club gatherings in Larkfield Park. |
| 27 | 0.933 | 0.534 | cut | User is scheduled for a pairing session with Greta Sandvik during the week of November 9, 2026. |
