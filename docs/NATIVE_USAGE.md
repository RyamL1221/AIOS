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

**Conversation memory.** After the response, the AssistantAgent writes
the user/assistant turn to the backend as a private `conversation`
memory, as Mem0's documentation shows for chat. This happens after the
response and is excluded from the trial's latency (the kernel
conditions write theirs on a background thread). In a single-interaction
trial it is written after retrieval, so it cannot change that trial.

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
(`owner_agent`, `memory_type`, `match_score`).

## native_mem0

Follows the Mem0 open-source documentation for `mem0ai` 2.0
(installed: 2.0.2):

- Configuration: `Memory.from_config` with an `llm`, an `embedder` and
  a `chroma` `vector_store` (`collection_name`, `path`)
  ([configuration](https://docs.mem0.ai/open-source/configuration),
  [Chroma](https://docs.mem0.ai/components/vectordbs/dbs/chroma),
  [Ollama LLM](https://docs.mem0.ai/components/llms/models/ollama)).
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
  order and with its default `threshold`. That includes the inverted
  score found in Subtask 5 (Mem0's Chroma adapter reports the raw L2
  distance as a similarity), because that is what a user of Mem0 gets.
  `scores_present` records whether Mem0 returned scores.
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
  kept every fact. Its cost is reported separately (Subtask 7). The
  agents read the Azure credentials from the same `AZURE_API_KEY`,
  `AZURE_API_BASE` and `AZURE_API_VERSION` variables as the kernel.
- **Input: natural language.** JSON passed with gpt-4o too, but Mem0's
  documentation shows conversational messages, natural language held up
  better on weaker extractors, and it lets both native conditions store
  the same text. 2 of the 20 profiles and 2 of the 20 task contexts used
  other keys than the schema's (`username`, `tools`, `project_name`,
  `next_actions`, or everything nested under one key), so the renderer
  maps those aliases, unwraps a single nested object and keeps unknown
  keys as `<key>: <value>` sentences (`native/render.py`).

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
