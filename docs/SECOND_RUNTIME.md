# A second runtime: the memory library in LangGraph

NeurIPS Subtask 22, which `REPLICATED_LOGIC.md` names ("The LangGraph
reproduction (Subtask 22) uses the same library"). A spec, written
before any code, on 2026-11-20. It proposes how `aios.memory.pipeline`
becomes the shared memory layer of a LangGraph app, what the
replicated-logic baseline is there, and the smallest run that would
show, on a runtime that is not AIOS, what the pilot found between the
kernel and the replicated locus. It changes no code and no file of the
library.

**Commits.** Our code and docs are read at AIOS `d49afc9`; a path that
names no repository is AIOS's. Cerebrum is read at `968029a`. Its next
commit, `de12cbf` (2026-11-20 16:35 EST, made while this was written),
changes only results files: it adds the decision check's Mem0 cells.
The figures taken from it say so.

**What was read and run.** LangGraph's and LangChain's documentation
pages (as markdown) and source (at the release tag `1.2.24`, or the
`master` branch where its `pyproject.toml` names the released version)
were downloaded on 2026-11-20, and every name and quote used here was
searched for in them ("Sources"). No model, kernel, test or benchmark
was run. The counts and times below come from stored results files and
cell logs, read by scripts kept outside the repositories. LangGraph is
installed in neither venv; both run Python 3.11.15. Names that are not
in the code today are proposals: `MemoryLayer`, `AgentMemory`, the
conditions `lg_shared_*` and `lg_replicated_*`, and a `runtime` field
on the records.

## What is reproduced

**The library.** `aios/memory/pipeline/` (14 modules) is the kernel's
memory logic, importable without the kernel
(`aios/memory/pipeline/__init__.py:4-10`): identity resolution and
sessions, the write barrier, visibility, selection, the forget and its
tombstones, supersession, the write quota, the memory block, and the
`MemoryPipeline` facade over them. `PIPELINE_VERSION` is a hash of the
package's modules (`__init__.py:74-88`), recorded on every trial.

**The two loci.** A locus is where that logic runs. In the kernel
locus one process holds the shared parts for every agent: one barrier,
one registry of users with one set of identity rules, one session
registry, one quota and one tombstone file
(`aios/memory/manager.py:121-126`, `:146-219`), and it builds a
pipeline over them for each request (`manager.py:296-311`). In the
replicated locus every agent builds its own `MemoryPipeline` over the
same backend, from a copy of the kernel's settings (Cerebrum
`cerebrum/example/agents/replicated/agents.py:99-163`). By design the
two differ in three ways and no other: no shared write barrier, no
shared identity resolution, no single policy instance
(`REPLICATED_LOGIC.md`, "The three inherent differences").

**The finding.** The pre-registered pilot (`PILOT.md`) ran the 30
fixed users of `pilot_v1`: two writers store a profile and a task
context, a consumer answers one question, and a judge scores the
answer on Profile and Integration (1 to 5). H is how many of the three
agents are built differently from the reference, each by one of five
variants (`HETEROGENEITY.md`). Kernel − replicated was a tie at H = 0
and a gap at H = 2, and the gap grew with H. On the in-house backend
alone, on the judged metric as `METRICS.md` defines it since Subtask 20
(the primary judge's LLM score at k = 1, its k by the rule in Cerebrum
`results/judge_reliability_s20/PROVENANCE.md:88`; `FULL_GRID.md`'s k
table at `d49afc9` still lists it as open), kernel − replicated,
mean [95% CI] over the 30 paired users (Cerebrum
`results/s20_rejudge/pilot_report/llm_gpt-5.4.md:58-74`):

| Model | Dimension | H = 0 | H = 2 | H2 − H0 |
|---|---|---|---|---|
| Qwen | Profile | −0.17 [−0.51, +0.17] | +1.10 [+0.55, +1.65] | +1.27 [+0.66, +1.87] |
| Qwen | Integration | −0.07 [−0.38, +0.24] | +1.03 [+0.52, +1.55] | +1.10 [+0.50, +1.70] |
| GPT-4o | Profile | −0.10 [−0.28, +0.08] | +1.17 [+0.52, +1.82] | +1.27 [+0.59, +1.95] |
| GPT-4o | Integration | −0.07 [−0.23, +0.10] | +1.17 [+0.54, +1.80] | +1.23 [+0.55, +1.92] |

`PILOT.md` holds the registered numbers: the hybrid score, pooled over
Mem0 and in-house. Judge-free, the share of trials with a missing
memory at H = 2 was 0.53 in the kernel and 0.87 in replicated, both
backends pooled and the same on both models, because the variants
decide it; the kernel leaked in 0 of 180 trials per model (`PILOT.md`,
"Judge-free").

Benchmark v2 (`BENCHMARK_V2.md`) gives each user six sessions written
by three writers, then six probes (deletion, privacy, recall, recency,
contradiction, integration) and, since revision 4, two multiple-choice
decision items (Amendment 10). At H = 0 the two loci tie by design:
- In the 30-user smoke (revision 3, Qwen; Cerebrum
  `results/bench_v2_smoke_s17/analysis.md`), none of the five
  judge-free in-house probes passed in one locus and failed in the
  other, 180 of 180 in-house blocks were byte-identical, and deletion
  passed for 30 of 30 users in both.
- In the 5-user decision check (revision 4, Qwen; Cerebrum
  `results/decision_functional_s20/analysis.md` at `de12cbf`), the
  decision items were 10 of 10 in both loci on both backends, and
  in-house deletion was 4 of 5 in both, the failure an answer that
  named a value no block held ("Deletion failures by carrier",
  `answer only`).

The loci part under stress: with concurrent writers, where only a
shared barrier makes a read wait, and with a writer that tags another
user's id, where only a session held outside the agent binds the
request (`STRESS_DIMENSIONS.md`).

**What a second runtime adds.** The claim is about where the memory
logic runs, not about AIOS. If it holds, it holds wherever one policy
instance sits between the agents and the store. The reproduction keeps
the library, the datasets, the schedule, the variants and the scorer.
It replaces everything else AIOS provides: the kernel process, its
scheduler and syscalls, its HTTP API and the SDK calls. No kernel runs
during a LangGraph cell: the cells run without the judge, which is
called through a kernel afterwards (risk 9).

## LangGraph, as read on 2026-11-20

**Versions.** `langgraph` 1.2.24, uploaded to PyPI on 2026-11-20 at
01:10 UTC; it needs Python 3.10 or later, `langchain-core` 1.4.7 or
later and `langgraph-checkpoint` from 4.3.0 to below 5.0.0 (P1). The
checkpointers and the store live in `langgraph-checkpoint` 4.3.2 (P3).
The repository's tag `1.2.24` carries both versions (R17).
`langchain`, which holds `create_agent` and its middleware, is 1.5.2;
it needs Python 3.11 or later and `langgraph` from 1.2.12 to below
1.3.0 (P2). `langchain-core` is 1.8.4 (Python 3.11 or later, P4) and
`langchain-ollama` 1.1.0 (P5). The documentation pages carry no
version and no date.

| Topic | What the documentation or the source says | Sources |
|---|---|---|
| Graph and state | A `StateGraph` over a state schema. A node is a sync or async function that returns a partial update, which each key's reducer applies; the default reducer "replaces the left value with the right". Message reducers "deserialize common wire formats into LangChain message objects". `compile()` gives the runnable (`invoke`, `stream`) | D1:80, :143, :199, :225; R10:1177-1182 |
| Execution | Message passing "in the style of Google's Pregel system", in super-steps: nodes that run in parallel share one, nodes in sequence use separate ones. A step plans, runs its nodes in parallel, then updates the channels; "channel updates are invisible to actors until the next step" | D1:27-34; D3:18-24 |
| Order and atomicity of state | "updates from a parallel superstep may not be ordered consistently". A superstep is transactional: if a branch raises, "none of that superstep's updates apply to state". The source sorts a step's tasks by path "to ensure deterministic order for update application" | D2:270, :274; R5:256-257 |
| Routing | `add_edge`, `add_conditional_edges`, `Command` (a state update and a `goto` in one return), and `Send` from a conditional edge, whose invocations "LangGraph runs ... in parallel" | D1:313-362, :400, :442-447 |
| Multi-agent apps | Five patterns: subagents, handoffs, skills, router, custom workflow. In a custom workflow each node "can be a simple function, an LLM call, or an entire agent". `create_agent(model=..., tools=...)` builds a tool-calling agent | D13:30-36; D14:37; D11:26 |
| Tools and middleware | A tool's `runtime: ToolRuntime` parameter "is hidden from the model". Agent middleware has node-style hooks (`before_agent`, `before_model`, `after_model`, `after_agent`) and wrap-style hooks (`wrap_model_call`, `wrap_tool_call`), whose handler may be called "zero times (short-circuit), once (normal flow), or multiple times". A `ModelRequest` holds `model`, `messages` ("excluding system message"), `system_message`, `state` and `runtime`, and `override` may replace the first four; the agent sends `[system_message, *messages]` to its model | D9:242; D12:21-41, :100, :697; R16:76-106; R15:1504-1508 |
| Checkpointers and threads | Short-term memory per thread (`{"configurable": {"thread_id": ...}}`). A checkpoint is "saved at each super-step"; when a node fails, the writes of the nodes that finished in that step are kept as pending writes. Durability `"exit"`, `"async"` (the default: persisted "while the next step executes") or `"sync"`. `InMemorySaver`, `SqliteSaver`, `PostgresSaver` | D4:31, :68, :294-309; R2:2714-2715; D11:531-539; D19:36-39 |
| The store | Long-term memory, "shared *across* conversational threads", key-value data "accessible from any thread": JSON values under a namespace tuple and a key. `put` returns `None`; `search(namespace_prefix, *, query, filter, limit=10, offset)`; also `get`, `delete`, `list_namespaces`, their async forms and `batch`. In the source the only abstract methods are `batch` and `abatch`; the Stores page instead names five async methods as required. A namespace label "cannot contain periods". `InMemoryStore` (an `index` turns on semantic search), `PostgresStore`; given as `compile(store=...)` | D7:12; D5:9, :312; R11:708-745, :784-794, :866-874, :1325-1336; D15:52-56, :98; D19:514 |
| Reaching the store and the run's context | A node may take `runtime: Runtime[Context]`. `Runtime` is a frozen dataclass of `context`, `store`, `stream_writer`, `heartbeat`, `previous`, `execution_info`, `server_info` and `control`. `context` is what the caller passes as `invoke(..., context=...)` under the graph's `context_schema`: "Immutable data that doesn't change during execution". A tool gets the same through `ToolRuntime`. `get_runtime()` and `get_store()` read the run's config from a context variable | R7:124-233; R9:425; R10:216-219; R2:3895-3906; D1:552-566; D8:10; R7:296-307; R8:17-56 |
| Reaching the model | Nothing injects one: `Runtime` has no model field. A node calls a chat model it holds (`init_chat_model`, `AzureChatOpenAI`, `ChatOllama`, `ChatLiteLLM`); `create_agent` takes one. In an agent, middleware is the only code between it and its model | R7:198-233; D16:63, :133-139; D17:74; D18:76; D12:21-41 |
| Who the caller is | `runtime.execution_info` holds the thread and run ids. `runtime.server_info` holds the assistant id and the authenticated user "when running on Agent Server", and is `None` otherwise, "e.g., during local development" | R7:26-75; D10:86, :108 |
| Concurrency, sync | A step's lone task with no timeout runs in the calling thread. Otherwise each task goes to a thread pool, `ContextThreadPoolExecutor(max_workers=config.get("max_concurrency"))`, in a copy of the caller's context variables | R3:206-210; R4:48-72; R13:660-673 |
| Concurrency, async | Coroutines run on the event loop, gated by a semaphore when `max_concurrency` is set. A sync node in an async run is called through `run_in_executor(None, ...)`, in the loop's default thread pool. Node timeouts apply to async nodes only. Below Python 3.11, `get_store()` does not work in an async run | R4:143-146; R6:598-608; R13:678-712; D6:240; R8:53-56 |
| Side effects | The compiled store reaches every task's `Runtime` unchanged, so a store call acts when the node makes it, not at the step's update. "Side effects during the node (payments, emails, external writes) are outside that boundary. Application code must make those effects idempotent." A retry "re-runs the entire node function from the start": at-least-once "when a policy matches" | R1:341, :631; R5:689-700; R2:2706-2709; D6:152, :159 |
| Memory written in the background | The documented ways to write memories: "in the hot path", before the reply, or "in the background", where "infrequent updates may leave other threads without new context" | D7:128-144 |

**Not verified.**
- No package was installed and no API was called: every name is as the
  pages and the source print it.
- Whether `langgraph` 1.2.24 and `langchain` 1.5.2 install beside what
  both venvs hold (`mem0ai` 2.0.2, `chromadb` 1.5.9, `litellm` 1.83.0,
  `graphiti-core` 0.31.2, `openai` 2.32.0 and 2.37.0, read from the
  venvs' package records). Neither venv holds a `langchain` or
  `langgraph` package today.
- No page says that a store write stays outside a super-step's
  transaction. This spec takes it from the source, where the store
  reaches each task unchanged (R1:631, R5:689-700), and from D6:159.
- `ChatOllama`'s token usage. The integration page's feature table
  marks it unsupported (D17:29-33); the source fills `usage_metadata`
  from Ollama's `prompt_eval_count` and `eval_count` (R14:103-117).
- `server_info.user` beyond its docstring and the runtime page: the
  Agent Server's own pages were not read.
- Whether a chat model class accepts a second system message after
  index 0 (the middleware route, below).

## The shared layer: where the single policy instance lives

**One object per app process.** The deployment builds a `MemoryLayer`
once, before it compiles the graph. It holds what `MemoryManager`
holds for the kernel (`manager.py:146-219`):
- one provider (`ProviderFactory.create`,
  `aios/memory/providers/factory.py:105`, configured by
  `provider_config`, `factory.py:23-77`);
- one `PipelineSettings`;
- one `MemoryWriteBarrier`;
- one `IdentityResolver` over one registry of users, with the
  deployment's `IdentityRules`, as the kernel's `_KernelIdentity`
  (`manager.py:53-73`);
- one `SessionRegistry`, one `TombstoneStore` on a file and one
  `WriteQuota`;
- the usage tag, and the app's one chat model.

For each request it builds a `MemoryPipeline` over those parts, as
`MemoryManager.memory_pipeline` does (`manager.py:296-311`). That is
the single policy instance: one set of settings, one barrier, one
resolver, one session registry, one quota, one tombstone file and one
model, whatever the number of agents.

**How an agent reaches it.** The app is one `StateGraph`: a node per
agent, and a router from `START` that sends a turn to its agent (the
docs' router and custom-workflow patterns, D13:30-36; here the dataset
names each turn's agent, so the router is scripted). Each node is made
by a factory that closes over an `AgentMemory` handle. The handle
fixes the agent's name and offers these calls and no other:

| Handle call | Library call behind it | What the layer adds |
|---|---|---|
| `write` | `MemoryPipeline.write` (`facade.py:210-332`) | binds the user and canonicalizes it, stamps the barrier under that id, passes the sequence as `barrier_seq` and the session as `session_key`; returns the id and the outcome |
| `update` | `MemoryPipeline.update` (`facade.py:351-405`) | binds, stamps |
| `search` | `MemoryPipeline.retrieve` (`facade.py:584-606`) | binds, takes the barrier snapshot |
| `list_own` | `MemoryPipeline.list_own_report` (`facade.py:436-491`) | binds, takes the snapshot; returns the withheld ids too |
| `read`, `delete` | `MemoryPipeline.read`, `delete` (`facade.py:499-526`, `:407-421`) | binds |
| `forget` | `MemoryPipeline.forget` (`facade.py:528-582`) | binds, stamps |
| `chat` | `MemoryPipeline.inject` (`facade.py:631-708`), then the model | binds, takes the snapshot when the call arrives, calls the one model, then stamps and stores the turn when the cell stores turns (v1; no v2 probe stores one, `BENCHMARK_V2.md`, "Probes") |
| `chat_json` | none | calls the one model with no block, as the kernel does for a JSON-output call (`aios/syscall/syscall.py:893-895`) |

"Binds" is the session binding of "Identity binding" below,
canonicalization included; "stamps" and "takes the snapshot" are the
barrier's acquire and snapshot ("Write before read").

The harness, not an agent, also gets `open_session` and
`close_session`, an audit of a user's raw rows and a cost read (both
wait for the user's writes first, as `manager.py:340-345` and
`:937-957` do), and the settings report the replicated agents copy.

**The model.** Only the layer constructs the chat model. An agent that
wants an answer calls `chat`: the layer binds the user, injects the
block the kernel would inject (the same `inject`, the same settings),
calls the model, and returns the reply with the injection diagnostics.
The message list goes to the model as the kernel sends it: the block
as a system message at index 0, before the agent's own system prompt
(`facade.py:704`; Cerebrum
`cerebrum/example/agents/assistant_agent/agent.py:63-67`).
`MemoryPipeline.inject` works on message dicts; the layer converts at
its edge if the graph's state holds LangChain message objects.

**What stops an agent from going around it.** In AIOS an agent is an
SDK client of another process, and the harness checks that an
agent-managed cell's kernel log shows 0 memory operations (`PILOT.md`,
"Procedure" and "Completeness"). In LangGraph the agents and the layer
share one Python process, and nothing read in LangGraph separates a
node from the process's files, sockets or modules: the docs describe
what a node is given, not what it is kept from (D1:552-566, D8, D10).
So the answer is construction and checks, not a wall:
1. **Construction.** An agent's factory receives its handle and
   nothing else: no provider, no store path, no model object, no
   settings. The store's directory and the model's credentials are
   read by the layer's builder only. The graph is compiled with no
   `store=`, so `runtime.store` is `None` in every node (R7:203), and
   no LangGraph store exists beside the layer. The layer returns
   answers and diagnostics, never the injected message list, so no
   channel holds a block.
2. **A static check.** A test scans the agents' modules for imports of
   a backend (`mem0`, `chromadb`, `graphiti_core`, `neo4j`), of
   `aios.memory`, of a chat model or its client (`langchain_ollama`,
   `langchain_openai`, `langchain_litellm`, `langchain.chat_models`,
   `litellm`, `ollama`, `openai`) and of `langgraph.store`, with a
   planted import to show the scan finds one: the form of
   `tests/modules/memory/test_pipeline_imports.py:24-77`.
3. **A runtime count.** A shared cell constructs one provider client
   and one chat model, both inside the layer, and the layer counts
   every call it makes to each. Each trial records those counts beside
   its own (writes issued, turns answered), and a cell whose counts
   disagree fails. This catches a leaked reference or a forgotten code
   path. It does not see a client an agent builds for itself; the
   static check covers that.
4. **What neither stops.** Code in the same process that opens the
   Chroma directory, or builds a model client, on purpose. Only a
   process boundary stops that: the layer served from a process of its
   own, which is the kernel's memory half again. The reproduction's
   faults are writers' bugs (a wrong user id, missing metadata, a
   flood), and no adversarial agent is tested (`STRESS_DIMENSIONS.md`,
   "What this does not show"), so 1 to 3 cover them.

**Not LangGraph's store interface.** `compile(store=...)` and
`runtime.store` are LangGraph's own seam for long-term memory, and a
`BaseStore` over the pipeline would look most native. It loses too
much:
- `put` returns `None` (R11:866-874), so a write could not return its
  id, `suppressed`, `quota_rejected`, or what it swept and retired.
- No operation exists for a forget, a listing that reports withheld
  ids, or injection.
- The store's methods receive no `Runtime` (`batch(ops)`, R11:733). A
  store could read the session only from the run's context variable
  (`get_runtime()`, R7:296-307), which the interface does not promise.
- A namespace label cannot contain a period (R11:1325-1336), so the V2
  variant's `<user_id>@users.example` (`HETEROGENEITY.md`, V2) could
  not be a label as it is.

The layer could still offer such a facade to apps that know only
`runtime.store`; the reproduction would not use it.

**Not agent middleware, for the minimal run.** With `create_agent`, a
`wrap_model_call` hook is where the layer would inject the block and
put its model: the hook gets the `ModelRequest` with its `runtime`,
may replace the model, the messages and the system message, and may
skip the call (D12:100; R16:76-106). The agent sends
`[system_message, *messages]` (R15:1504-1508), and `messages` is
documented as "excluding system message" (R16:100). The kernel's
prompt has two system messages, the block before the agent's own
prompt (`facade.py:704`; the equivalence test's prompt,
`tests/modules/memory/test_pipeline_library.py:155-158`). A hook can
match it only by putting the block in `system_message` and the agent's
prompt into `messages`, against that field's description. Plain nodes
send the kernel's list as it is (open decision 2).

Open: whether construction and checks are enough for the paper, or the
layer must run as its own process (open decision 7).

## Write before read without the AIOS scheduler

**What the kernel does.** A memory request is bound to its session,
canonicalized, stamped against the barrier and queued on the server's
event loop, in arrival order, then served by one memory thread
(`runtime/launch.py:1054-1065`; `aios/syscall/syscall.py:103-113`;
`manager.py:347-387`). The id is canonicalized before the stamp so that
a write and a read of one user key the barrier alike
(`manager.py:365-367`); the write releases under the same canonical id
(`facade.py:255`, `:329-332`). A write holds its sequence until the
provider has committed and `after_write` is done (`facade.py:302-332`).
A read waits for every write of its user stamped at or before its
snapshot, and for none stamped after (`barrier.py:233-262`,
`:333-338`; `selector.py:220-222`). A chat's snapshot is taken when the
request arrives (`launch.py:665-668`; `manager.py:458-470`). The wait
is skipped only for a provider that commits synchronously
(`selector.py:35-39`, `:94-99`): the test store `in-memory`
(`aios/memory/providers/in_house.py:37`). The in-house Chroma store and
Mem0 wait (`aios/memory/providers/base.py:126-128`).

**What LangGraph's own order gives.** Inside one run, a node that
follows another by an edge starts after the first has returned: they
are in different super-steps (D1:27-34; D3:18-24). If every writer
stores inside its node and the consumer comes after the writers, the
consumer reads after their commits, with no barrier. A step's state
updates are also applied together and are all-or-nothing (D2:274);
that covers graph state only.

**What it does not give.**
1. **Nodes of one super-step.** A consumer and a writer started
   together (two edges out of one node, or `Send`) run at the same
   time (D1:400). The store is not a channel: a write acts when the
   node makes it, and a read sees what the backend holds at that
   instant (R1:631, R5:689-700). Nothing orders the two.
2. **Two runs.** The store is shared across threads by design (D7:12,
   D5:9). A writer's run and a consumer's run for one user are ordered
   by nothing in LangGraph.
3. **A write that outlives its node.** The docs' background pattern
   (D7:128-144), and the kernel's own conversation write. An edge after
   the node no longer helps.
4. **Slow commits.** On an extracting backend a write takes seconds:
   in the pilot, 3 of 90 kernel Mem0 conversation writes took longer
   than the barrier's 5 s timeout (`BENCHMARK_V2.md`, "Before any v2
   run"). Each window above is then seconds wide.

**The race this closes.** A cross-agent read of an accepted,
uncommitted write. Agent A's write for user U has entered the memory
layer and is still in the backend's commit path. Agent B's retrieval
for U begins in that window, in a sibling node or in another run, and
is served a store without it. B then answers from the old value (a
stale read), misses the fact (a timing miss), or still sees a value a
revoke was removing (a late forget): the measures of `METRICS.md`,
"Timing (stress dimensions)". A barrier of B's own cannot help, since
it does not know A's pending write (`REPLICATED_LOGIC.md`, difference
1). The harness runs each agent turn as its own graph run, so case 2
is the one the reproduction exercises; case 1 is the same race inside
one run (open decision 8).

**What plays the barrier's part.** The library's own barrier, one
instance in the layer. Nothing of LangGraph's is used for the
ordering.

| Part | In the AIOS kernel | In the LangGraph layer |
|---|---|---|
| Acceptance | The `/query` handler binds the request, then stamps and queues its syscall on the event loop (`launch.py:1054-1065`) | The call's entry into the layer: bind, canonicalize, then stamp, in the calling thread, before any provider call. The barrier's lock orders two entries (`barrier.py:131-142`, `:261-262`) |
| Acquire | `barrier.acquire(user)` for a write, an update and a forget (`manager.py:368-379`) | The same call; `MemoryPipeline.write` takes the sequence as `barrier_seq` (`facade.py:271-274`) |
| Commit and release | The memory thread runs `MemoryPipeline.write`, which releases in a `finally` after `provider.add` and `after_write` (`facade.py:302-332`) | The same method, in the node's own thread; for a turn stored after the reply, in a thread of the layer's |
| A read's snapshot | `barrier.snapshot(user)` at acceptance (`manager.py:380-387`), or at arrival for a chat (`manager.py:458-470`) | `barrier.snapshot(user)` at the entry of `chat`, `search` and `list_own` |
| A read's wait | `wait_until_drained(user, snapshot)` before the fetch, bounded by `timeout_ms` (`selector.py:84-108`, `:220-222`) | The same code, in the calling thread |
| A forget | Stamped like a write; it waits for the writes before it, through its sequence minus one (`facade.py:549-567`) | The same |
| Measurement reads | The audit and the cost read wait with `required` (`manager.py:340-345`, `:937-957`) | The layer's audit and cost reads, the same |

Acceptance on LangGraph is therefore the instant a call enters the
layer. For two nodes of one super-step that order is the thread
scheduler's, not the graph's. The guarantee is the kernel's,
unchanged: a read waits for every write accepted before it, and for
none accepted after. An app that needs "the consumer after this turn's
writers" says so with an edge, which LangGraph does give; the barrier
covers what an edge cannot.

**Threads and the event loop.**
- The library is synchronous: a wait blocks its thread on a condition
  variable (`barrier.py:322-365`). The minimal reproduction uses sync
  nodes and `invoke`. LangGraph runs a lone node in the calling thread
  and parallel nodes on a thread pool, each in a copy of the caller's
  context variables (R3:206-210; R4:48-72), so a waiting reader holds
  one thread while the writer it waits for commits in its own.
- A write that outlives its node is stamped before the reply returns
  and stored in a thread the layer owns, never in LangGraph's pool: a
  pool full of waiting readers then cannot hold back the commit they
  wait for. The kernel's extractor stamps on the request thread and
  stores on a daemon thread
  (`aios/memory/conversation_extractor.py:92-102`).
- A stamped sequence is released on every path that does not reach
  `MemoryPipeline.write`, as the kernel does (`manager.py:854-860`;
  `conversation_extractor.py:147-156`).
- In an async graph a sync node is called in the loop's default thread
  pool (R6:598-608; R13:678-712), so the layer blocks a worker there,
  not the loop. An async node that called the layer directly would
  block the loop, and a commit that needs the loop (an async writer's)
  could not run until the wait timed out. An async entry would stamp
  on the loop and run the library call in a worker thread, as
  `runtime/launch.py` does (`launch.py:1062-1065`;
  `aios/utils/request_pool.py:25-33`). LangGraph's own batched store
  refuses a synchronous call made on its event loop: "This can lead to
  deadlocks or performance issues" (R12:33-53). Not built for the
  minimal reproduction.
- A wait is bounded by `memory.write_barrier.timeout_ms`: 5,000 by
  default (`barrier.py:85`), 60,000 in v2 kernel runs
  (`BENCHMARK_V2.md`, "Before any v2 run"). On a timeout the read goes
  on without the write, and `barrier_waits` says so.

**What is recorded.** As in the kernel and replicated loci, by the
library: a write's and a forget's `barrier_seq` and `committed_at`, a
retrieval's `barrier_snapshot`, `fetch_started_at` and `barrier_waits`.
The harness derives `late_covered`, `uncovered_writes`, `timing_miss`,
`stale_read` and `late_forget` from them (`METRICS.md`, "Timing
(stress dimensions)").

**Retries and resumes.** With a retry policy a node runs at least once
(D6:152), and each attempt repeats its writes. A resumed run re-runs
the failed step's unfinished nodes; the nodes that finished keep their
pending writes (D4:31), but their store calls have already happened.
The reproduction sets no `RetryPolicy`, compiles no checkpointer and
resumes no run. The library has no idempotency key: only the quota's
duplicate rule, when the quota is on, rejects an exact repeat
(`quota.py:93-109`).

## Identity binding

**The session's user against the claimed user.** The layer holds one
`SessionRegistry` (`identity.py:152-196`) and the deployment's identity
rules (`identity.py:20-71`; the kernel's, as `HETEROGENEITY.md` gives
them: `casefold` and `email_domains: ["users.example"]`).
1. The deployment, here the harness, opens a session for a user. The
   layer canonicalizes the id, as `MemoryManager.open_session` does
   (`manager.py:389-392`), and the registry returns a random token
   (`identity.py:169-179`). The harness opens one per v2 session and
   one for the probes, and closes each after it, as it does with the
   kernel (Cerebrum `benchmarks/shared_memory/history.py:282-309`,
   `:1031`, `:1092`).
2. The token travels as the run's static context: the graph has a
   `context_schema` with a `session_token` field, declared as a frozen
   dataclass, and the harness's adapter passes `context=` on `invoke`
   (D1:552-566; R2:3895-3906). `Runtime` is itself frozen (R9:425), so
   a node cannot replace the context it was given.
3. The node's wrapper, which is the deployment's code, reads
   `runtime.context.session_token` and hands the agent's logic a
   handle already bound to that turn. The agent's own code never
   touches the token, as with the SDK's `kernel_session` context
   (Cerebrum `cerebrum/utils/communication.py:61-84`, `:119-122`).
4. At each entry the layer takes the user from the session
   (`identity.py:186-192`). What the agent supplied (its write's
   `metadata.user_id`, its request's `user_id`) is the claim. The layer
   canonicalizes the claim, rewrites the request to the session's
   user, and, when the claim named another user, records
   `identity_overridden` (the claimed and the bound id) beside the
   reply or in the injection diagnostics, with a WARNING. This is what
   `bind_session` and `bind_chat_user` do (`manager.py:394-456`).
5. An unknown or closed token is refused. A request with no token is
   served for the id it claims, canonicalized.
6. The token also keys the write quota's bucket, as the kernel passes
   it (`manager.py:657`; `facade.py:276-277`).
7. Under the ablation `identity: claim` the layer binds nothing and
   applies no rule, as the kernel does (`manager.py:159-168`;
   `launch.py:612-622`).

**Replicated.** No session exists. Each agent's resolver takes the id
its agent claims, with no rules (`identity.py:74-97`;
`HETEROGENEITY.md`, "The kernel's identity resolution").

**On an Agent Server.** The bound user would come from
`runtime.server_info.user`, the authenticated caller (R7:60-75;
D10:86). An open-source run has none (D10:108), so the reproduction's
sessions are opened by the harness.

## The replicated-logic baseline

**What it is.** The same graph, nodes, prompts, model settings,
datasets and schedule. Each agent's node closes over a memory of its
own, a `ReplicatedMemory` as today (Cerebrum
`replicated/agents.py:99-163`): its own provider client over the cell's
store directory, its own `MemoryPipeline` with its own barrier,
resolver and quota (the library's defaults, `facade.py:191-202`), and
the store's tombstone file, shared through the file. Each agent also
does for itself what the layer does in the shared locus: inject, call
the model, write the turn (as `replicated/agents.py:404-447` does).
In AIOS a replicated agent still calls the model through the kernel
(`llm_chat`), with the kernel's injection and extraction off, which
the harness checks (`REPLICATED_LOGIC.md`, "The condition",
"Inference"; `replicated/agents.py:423-429`). On LangGraph each agent
calls its model client itself: the same class, model and decoding as
the layer's, built from the same settings. A replicated cell builds no
`MemoryLayer`.

**The three differences, on LangGraph.** They are those of
`REPLICATED_LOGIC.md`:
1. A barrier per agent: a consumer's read cannot wait for a writer's
   accepted write.
2. A resolver per agent: no rules and no session, so the claimed id is
   used.
3. A copy of the settings per agent: a consumer's own k, threshold and
   budget apply (V4), and a flooding writer builds its pipeline without
   the quota (Cerebrum `variants/base.py:231-249`).

**What keeps it at parity.**
1. **One library, one version.** Both loci import
   `aios.memory.pipeline` from the same checkout through the same
   loader (Cerebrum `replicated/library.py:15-40`). Every trial records
   `PIPELINE_VERSION`, and a cell whose layer or agents report two
   values fails.
2. **One settings source.** A `memory:` block in the reproduction's
   settings file, with the keys `PipelineSettings.from_memory_config`
   reads (`settings.py:82-118`) and the provider's sections. The layer
   is built from it. Each replicated agent is built from the builder's
   report of it, a dict of the shape of the kernel's `/memory/config`
   (`launch.py:527-573`), which `ReplicatedMemory` already reads
   (`replicated/agents.py:128-142`). No setting is typed twice.
3. **One agent logic.** Both loci run the same writer and consumer
   functions with different calls behind them, as the AIOS loci do:
   `run_v2_session` takes its write, list, delete and forget as
   arguments (Cerebrum
   `cerebrum/example/agents/shared_memory_utils.py:742-952`).
4. **One model path.** The same chat model class and decoding in both.
   In the shared locus the layer holds it; in the replicated one each
   agent does.
5. **An equivalence test**, as `test_pipeline_library.py:149-184` has
   for the kernel: for 20 seeded users, the layer's injected messages
   equal a direct `MemoryPipeline.inject`'s, byte for byte, its
   diagnostics without timings (`:140-146`) are equal too, and its
   writes store the same rows (`:222`).
6. **A measured tie.** At H = 0 the paired differences include 0, and
   on in-house the share of byte-identical blocks between the two loci
   is reported (expected: all of them, as in AIOS's smoke, 180 of 180).

**Not memory logic.** The layer stores a v1 turn after the reply, in
its own thread; the replicated assistant stores it synchronously after
the reply. Both are outside the latency measure, as in AIOS
(`REPLICATED_LOGIC.md`, "Differences that are not memory logic").

## What the library assumes of AIOS

**How it was found.** `git grep -nE` over `aios/memory/` at `d49afc9`
for: imports of `cerebrum` at any indentation; `config_manager` and
`global_config`; imports of `aios.syscall`, `aios.scheduler`,
`aios.hooks`, `aios.llm_core`, `aios.config` and `runtime`;
`getLogger`; `usage_tag` and `tagged`; `threading` and `asyncio`;
`os.environ`, `getcwd`, default paths and `localhost`; and, read by
hand, the words `MemoryQuery`, `MemoryResponse`, `LLMQuery`, `syscall`,
`SDK`, `/memory/config`, `MemoryManager` and "the kernel" in the
package's code and docstrings. Two tests already bound the answer. No
module of `aios/memory/pipeline/` imports `cerebrum`
(`tests/modules/memory/test_pipeline_imports.py:48-53`). And a fresh
interpreter that writes and injects through the library must load none
of `aios.syscall`, `aios.memory.manager`,
`aios.memory.context_injector`, `aios.config`, `aios.scheduler`,
`aios.llm_core` or `runtime`
(`tests/modules/memory/test_pipeline_library.py:391-417`). The grep
agrees: the package imports the standard library and its own modules
only, with the provider contract and `note.py` beside it. What it
assumes is in three tables: inside the package, in what the package
imports, and in the kernel modules whose logic a second runtime has to
supply. Two older modules beside the library read the kernel's config
(`aios/memory/base.py:8`, `aios/memory/retrievers.py:10`); the library
imports neither.

**Inside `aios/memory/pipeline/`.**

| Where | What it assumes | What would have to change |
|---|---|---|
| `facade.py:17-18`, `selector.py:21`, `deletion.py:20` | Relative imports of `..note` and `..providers.base`: the package imports only as `aios.memory.pipeline`, inside the `aios` package of an AIOS checkout. Importing it runs `aios/memory/providers/__init__.py:44-50`, which imports every backend | Nothing for a run from the Cerebrum checkout: its loader puts `AIOS_ROOT` first (Cerebrum `replicated/library.py:15-40`), because Cerebrum's own `aios/` stub would shadow the package. A package of its own would need the contract, `note.py` and the library split from the backends |
| `__init__.py:17-22` | Importing the library still loads `cerebrum.utils.usage`, through the Mem0 provider: the SDK must be installed, even for an in-house store | Lazy backend imports, or the helpers moved beside the providers. Not needed while the app lives beside the SDK |
| `__init__.py:74-88` | `PIPELINE_VERSION` hashes the package's own modules. It covers neither `providers/`, `note.py` and `embedding.py` nor any host code (the kernel's `MemoryManager`, a LangGraph layer) | The harness records the host's and the providers' hashes beside it, or the hash is widened |
| `facade.py:47-56`, `:185-189`; `selector.py:52-57` | The usage tag is the host's to pass. The kernel and the replicated agents pass `cerebrum.utils.usage.tagged` (`manager.py:309`; Cerebrum `replicated/agents.py:155-158`); without one nothing is counted | Nothing: the layer passes the same tag. The cost records then still come from the SDK's accumulator (Cerebrum `cerebrum/utils/usage.py:25-99`) |
| `settings.py:82-118` | Settings come as a `memory:` block or a `/memory/config` `pipeline` report: a dict, never a file. Error texts name `memory.<key>` (`settings.py:66-80`, `quota.py:42-62`, `ablation.py:84-134`, `identity.py:42`) | Nothing: the layer passes the same block |
| `barrier.py:74-86` | The barrier reads a `memory.write_barrier` dict (`enabled`, `timeout_ms`, `waits`) | Nothing |
| `barrier.py:27`, `memory_formatter.py:20` | Loggers named `aios.memory.write_barrier` and `aios.memory.memory_formatter`, "so the kernel's log lines keep their logger". The other modules log as `aios.memory.pipeline.<module>` (`facade.py:29`, `selector.py:28`, `deletion.py:26`, `formatter.py:28`, `identity.py:17`) | Nothing needed: the app puts a handler on `aios.memory`. A name argument would be optional |
| `barrier.py:91-103`, `:322-365` | A `threading.Lock` and a `threading.Condition` per user; a wait blocks its thread. One process, threads | Nothing for a sync graph. An async graph must call it from a worker thread; an awaitable wait would be an addition |
| `quota.py:78-80`; `identity.py:163-167`, `:88-90` | The quota's counts, the sessions and the registry of users live in the process's memory | Nothing for one process. An app of several processes needs them shared: not in the minimal reproduction |
| `tombstones.py:134-172` | A SQLite file with a connection per call: already shared by every pipeline and process over one store | Nothing |
| `facade.py:38-43`, `:59-77` | `note_from_request` takes the `params` of an SDK `create_memory` request | Nothing: the layer builds the same dict, or a `MemoryNote` |
| `facade.py:125-135`, `:631-708` | `inject` takes and returns message dicts with `role` and `content`, and prepends the block as a system message dict (`:704`). LangGraph's message reducers hold LangChain message objects (D1:199) | Nothing in the library: the layer converts at its edge, or calls `retrieve` and `build_block` and builds the message itself |
| `facade.py:212`, `:224-226`, `:271-274`, `:530`, `:540-544`, `:594`; `selector.py:63-108` | `barrier_seq` and `barrier_snapshot` exist so that a host can stamp at acceptance and commit later ("the kernel stamps it when the syscall is accepted") | Nothing: this is the seam the layer uses |
| `facade.py:214`, `:239-240`, `:276-277` | `session_key` is "the kernel's session", the quota's bucket key | Nothing: the layer passes its session token |
| `ablation.py:16-20`, `:36-38` | Two switches act outside the library: `identity` ("the kernel only: `MemoryManager`, `runtime/launch.py`") and `consumer_config` ("the kernel's injector") | The layer applies both itself, or their code moves into the library ("What must change in the library") |

**In what the package imports.**

| Where | What it assumes | What would have to change |
|---|---|---|
| `aios/memory/providers/__init__.py:44-50`; `aios/memory/providers/factory.py:11-18` | Every backend module is imported with the contract and with the factory, so `provider_config` alone loads the Mem0 provider | Lazy imports, for an app without the SDK |
| `aios/memory/providers/mem0.py:26-27` | Top-level imports of `cerebrum.utils.mem0_errors` and of `count_embeddings` and `seed_mem0_llm` from `cerebrum.utils.usage` | As above |
| `aios/memory/providers/mem0.py:299-324` | `_get_api_key` reaches for the kernel's `ConfigManager` (`aios.config.config_manager`, `:309-310`), inside a `try` with an environment fallback, and only for Mem0's `openai` and `anthropic` providers (`mem0.py:266-296`) | Nothing for the reproduction (Mem0's LLM is its `litellm` provider, `mem0.py:590-595`). A clean library drops the import |
| `aios/memory/providers/mem0.py:143-146`; `aios/memory/providers/chroma_inhouse.py:68`, `:77-78` | Default store paths under the working directory (`<cwd>/.mem0/chroma`, `.aios_state/chroma_inhouse`) | Nothing: the layer passes explicit paths, as the replicated agents do (Cerebrum `replicated/agents.py:60-96`) |
| `aios/memory/providers/factory.py:23-77` | `provider_config` reads the `memory:` block's sections; with Mem0's `infer` it imports `cerebrum.utils.usage.mem0_llm_config` (`:60`) | Nothing |
| `aios/memory/embedding.py:11-16`, `:39-43`, `:71-80` | One embedder only, Ollama's (`nomic-embed-text`, 768 dimensions, `http://localhost:11434` by default), through the `ollama` client wrapped by `cerebrum.utils.usage.count_embeddings` | Nothing. A LangGraph cell on in-house needs Ollama for its embeddings whatever its chat model |
| `aios/memory/providers/graphiti.py:125`, `:184-191`; `aios/memory/providers/amem.py:97` | Graphiti's and A-MEM's clients come from `cerebrum.utils.graphiti` and `cerebrum.utils.amem`; Graphiti runs on a runner's own event loop | Not in the minimal reproduction |
| `aios/memory/providers/base.py:55-68`, `:223-225` | `Candidate.to_row` is "the kernel's row shape, which SDK search returns"; `sync_llm_from_query` takes the SDK's `LLMQuery.llms` | Nothing: the layer never calls the second, which returns at once with backend extraction on (`mem0.py:611-612`) |

**In the kernel modules a second runtime has to stand in for.** None
of this is library code, and all of it is part of what the kernel
locus does.

| Where | What it does | In the LangGraph layer |
|---|---|---|
| `manager.py:14-17`, `:129-130`, `:595` | `MemoryManager` imports the SDK's `MemoryQuery` and `MemoryResponse`, the usage tag and the kernel's `ConfigManager` (read at construction), and checks for a `MemorySyscall` | It cannot be the layer without AIOS's config and syscall types. Its logic below is written again or moved |
| `manager.py:53-73`, `:146-219`, `:296-311` | Builds the one barrier, resolver and registry, rules, sessions, quota and tombstones, and a pipeline per request over them | The layer's composition |
| `manager.py:347-387`, `:472-491` | `stamp_syscall`: which operations acquire (add, update, forget) and which snapshot (retrieve, list), with canonical ids first | Per handle call |
| `manager.py:389-470`; `launch.py:612-668` | Session open and binding, the override record, `honored_session` under `identity: claim`, the arrival snapshot | Per handle call |
| `manager.py:340-345`, `:937-957` | `await_writes` and `audit_rows`: the measurement reads | The layer's cost and audit reads |
| `manager.py:854-860`; `aios/memory/conversation_extractor.py:147-156` | Release a stamped sequence on a path that never reaches `write` | The same care |
| `aios/memory/context_injector.py:147-173`, `:251-281` | Injection through the pipeline; a consumer's own config under `consumer_config: honor` | `chat` |
| `aios/memory/conversation_extractor.py:92-102`, `:131-145` | Stamps on the request thread and stores on a daemon thread; the write is an SDK `MemoryQuery` in a `MemorySyscall` that is never started | `chat` stamps, then stores with `conversation_note` in the layer's thread |
| `aios/syscall/syscall.py:87-126`, `:140-163` | Acceptance: the stamp before the queue, in arrival order | No queue: a call's entry is its acceptance |
| `aios/syscall/syscall.py:786-895` | The chat flow: inject, the model call, the turn's write; no injection for a JSON-output call | `chat` and `chat_json` |
| `runtime/launch.py:527-573` | `/memory/config`: the settings report the replicated agents copy | The builder's report, read in process |
| `runtime/launch.py:1035-1068`; `aios/utils/request_pool.py:18-33` | Memory requests accepted on the event loop and awaited on a pool of 64 workers | Not needed in a sync graph; the same pattern in an async one |

## Sources

Every URL was read on 2026-11-20. D is a documentation page (its
markdown), R a source file, P a package index record. `D1:27` is line
27 of D1 as downloaded; `R5:257` line 257 of R5.

| Id | What | URL | Accessed |
|---|---|---|---|
| P1 | `langgraph` on PyPI (1.2.24) | https://pypi.org/pypi/langgraph/json | 2026-11-20 |
| P2 | `langchain` on PyPI (1.5.2) | https://pypi.org/pypi/langchain/json | 2026-11-20 |
| P3 | `langgraph-checkpoint` on PyPI (4.3.2) | https://pypi.org/pypi/langgraph-checkpoint/json | 2026-11-20 |
| P4 | `langchain-core` on PyPI (1.8.4) | https://pypi.org/pypi/langchain-core/json | 2026-11-20 |
| P5 | `langchain-ollama` on PyPI (1.1.0) | https://pypi.org/pypi/langchain-ollama/json | 2026-11-20 |
| D1 | Graph API overview | https://docs.langchain.com/oss/python/langgraph/graph-api.md | 2026-11-20 |
| D2 | Sequences, branches and loops | https://docs.langchain.com/oss/python/langgraph/graph-api-control-flow.md | 2026-11-20 |
| D3 | LangGraph runtime (Pregel) | https://docs.langchain.com/oss/python/langgraph/pregel.md | 2026-11-20 |
| D4 | Checkpointers | https://docs.langchain.com/oss/python/langgraph/checkpointers.md | 2026-11-20 |
| D5 | Stores | https://docs.langchain.com/oss/python/langgraph/stores.md | 2026-11-20 |
| D6 | Fault tolerance | https://docs.langchain.com/oss/python/langgraph/fault-tolerance.md | 2026-11-20 |
| D7 | Memory overview | https://docs.langchain.com/oss/python/concepts/memory.md | 2026-11-20 |
| D8 | Context overview | https://docs.langchain.com/oss/python/concepts/context.md | 2026-11-20 |
| D9 | Tools | https://docs.langchain.com/oss/python/langchain/tools.md | 2026-11-20 |
| D10 | Runtime (LangChain) | https://docs.langchain.com/oss/python/langchain/runtime.md | 2026-11-20 |
| D11 | Agents (`create_agent`) | https://docs.langchain.com/oss/python/langchain/agents.md | 2026-11-20 |
| D12 | Custom middleware | https://docs.langchain.com/oss/python/langchain/middleware/custom.md | 2026-11-20 |
| D13 | Multi-agent | https://docs.langchain.com/oss/python/langchain/multi-agent/index.md | 2026-11-20 |
| D14 | Custom workflow | https://docs.langchain.com/oss/python/langchain/multi-agent/custom-workflow.md | 2026-11-20 |
| D15 | Long-term memory | https://docs.langchain.com/oss/python/langchain/long-term-memory.md | 2026-11-20 |
| D16 | Models | https://docs.langchain.com/oss/python/langchain/models.md | 2026-11-20 |
| D17 | `ChatOllama` integration | https://docs.langchain.com/oss/python/integrations/chat/ollama.md | 2026-11-20 |
| D18 | `ChatLiteLLM` integration | https://docs.langchain.com/oss/python/integrations/chat/litellm.md | 2026-11-20 |
| D19 | Add memory (LangGraph) | https://docs.langchain.com/oss/python/langgraph/add-memory.md | 2026-11-20 |
| R1 | `pregel/_loop.py`, tag 1.2.24 | https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.24/libs/langgraph/langgraph/pregel/_loop.py | 2026-11-20 |
| R2 | `pregel/main.py`, tag 1.2.24 | https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.24/libs/langgraph/langgraph/pregel/main.py | 2026-11-20 |
| R3 | `pregel/_runner.py`, tag 1.2.24 | https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.24/libs/langgraph/langgraph/pregel/_runner.py | 2026-11-20 |
| R4 | `pregel/_executor.py`, tag 1.2.24 | https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.24/libs/langgraph/langgraph/pregel/_executor.py | 2026-11-20 |
| R5 | `pregel/_algo.py`, tag 1.2.24 | https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.24/libs/langgraph/langgraph/pregel/_algo.py | 2026-11-20 |
| R6 | `_internal/_runnable.py`, tag 1.2.24 | https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.24/libs/langgraph/langgraph/_internal/_runnable.py | 2026-11-20 |
| R7 | `runtime.py`, tag 1.2.24 | https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.24/libs/langgraph/langgraph/runtime.py | 2026-11-20 |
| R8 | `config.py`, tag 1.2.24 | https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.24/libs/langgraph/langgraph/config.py | 2026-11-20 |
| R9 | `types.py`, tag 1.2.24 | https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.24/libs/langgraph/langgraph/types.py | 2026-11-20 |
| R10 | `graph/state.py`, tag 1.2.24 | https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.24/libs/langgraph/langgraph/graph/state.py | 2026-11-20 |
| R11 | `store/base/__init__.py`, tag 1.2.24 | https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.24/libs/checkpoint/langgraph/store/base/__init__.py | 2026-11-20 |
| R12 | `store/base/batch.py`, tag 1.2.24 | https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.24/libs/checkpoint/langgraph/store/base/batch.py | 2026-11-20 |
| R13 | `langchain_core/runnables/config.py`, `master` (1.8.4) | https://raw.githubusercontent.com/langchain-ai/langchain/master/libs/core/langchain_core/runnables/config.py | 2026-11-20 |
| R14 | `langchain_ollama/chat_models.py`, `master` (1.1.0) | https://raw.githubusercontent.com/langchain-ai/langchain/master/libs/partners/ollama/langchain_ollama/chat_models.py | 2026-11-20 |
| R15 | `langchain/agents/factory.py`, `master` (1.5.2) | https://raw.githubusercontent.com/langchain-ai/langchain/master/libs/langchain_v1/langchain/agents/factory.py | 2026-11-20 |
| R16 | `langchain/agents/middleware/types.py`, `master` (1.5.2) | https://raw.githubusercontent.com/langchain-ai/langchain/master/libs/langchain_v1/langchain/agents/middleware/types.py | 2026-11-20 |
| R17 | The `pyproject.toml` versions: `langgraph` 1.2.24 (line 7) and `langgraph-checkpoint` 4.3.2 (line 7) at the tag; `langchain-core` 1.8.4 (23), `langchain` 1.5.2 (23) and `langchain-ollama` 1.1.0 (22) on `master` | https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.24/libs/langgraph/pyproject.toml, https://raw.githubusercontent.com/langchain-ai/langgraph/1.2.24/libs/checkpoint/pyproject.toml, https://raw.githubusercontent.com/langchain-ai/langchain/master/libs/core/pyproject.toml, https://raw.githubusercontent.com/langchain-ai/langchain/master/libs/langchain_v1/pyproject.toml, https://raw.githubusercontent.com/langchain-ai/langchain/master/libs/partners/ollama/pyproject.toml | 2026-11-20 |

## What must change in the library

**For the minimal reproduction: nothing**, if the layer is written as
a client of the library (open decision 1, option a). Every seam it
needs exists. The barrier, the resolver, the tombstones, the quota and
the usage tag are constructor arguments (`facade.py:177-206`).
`barrier_seq` and `barrier_snapshot` separate acceptance from commit.
`retrieve` and `build_block` serve a host with its own message type.

**For "the same code on both runtimes".** The rules of acceptance are
kernel code today, not library code:
- which operations acquire and which snapshot (`manager.py:347-387`);
- session binding and the override record (`manager.py:394-456`);
- the arrival snapshot (`manager.py:458-470`);
- canonical ids at acceptance (`manager.py:472-491`);
- the release of a stamp that never reaches `write`
  (`manager.py:854-860`);
- the audit's and the cost read's wait (`manager.py:340-345`,
  `:937-957`);
- the switches `identity` and `consumer_config` (`ablation.py:16-20`,
  `:36-38`; `aios/memory/context_injector.py:251-281`).

A layer written beside them is a second copy, and a difference between
the runtimes could then be the copy's. Moved into the library as one
host object that `MemoryManager` and the layer both call, they would
make the claim literal. The move changes `PIPELINE_VERSION` and touches
the kernel's request path, so it would land with the equivalence test
unchanged and passing, before the full grid's code is frozen, or after
the grid.

**For an app without the AIOS SDK.** Not the reproduction, which lives
beside the SDK:
- import the backends lazily (`providers/__init__.py:44-50`,
  `providers/factory.py:13-18`);
- move the SDK helpers the providers import beside the providers, or
  make them optional: the usage counters and Mem0's seed
  (`mem0.py:26-27`, `embedding.py:74`, `factory.py:60`), Mem0's error
  capture, and the Graphiti and A-MEM client builders
  (`graphiti.py:125`, `amem.py:97`);
- drop the import of the kernel's `ConfigManager` (`mem0.py:309`).

**Optional.** A logger name argument (`barrier.py:27`,
`memory_formatter.py:20`); an awaitable barrier wait for async hosts;
a version hash that covers the providers.

**Not changed, by design.** The provider contract, the settings' keys,
the diagnostics' keys and every decision the library makes. The
reproduction's point is that they are the same.

## Minimal reproduction

**What is built.** All of it in Cerebrum, beside the harness; nothing
in AIOS unless open decision 1 says so.
1. **The layer.** `MemoryLayer` and `AgentMemory`, as above.
2. **The graph.** One `StateGraph` with a `context_schema`, a node per
   agent of the dataset, and a scripted router from `START`, compiled
   with no checkpointer and no store. Each agent turn is its own run
   with a fresh message list (`BENCHMARK_V2.md`, "Probes": "a fresh
   message list"), so nothing is carried from turn to turn.
3. **The agents.** Writer and consumer node functions for both loci,
   over the agents' shared logic and prompts, and one model function
   over a LangChain chat model with the runs' decoding (temperature
   0.0, seed 20261105; for Ollama, the context window the kernel sets,
   16384, passed as `num_ctx`, whose Ollama default is 2048,
   R14:577-581).
4. **Two loci for the harness.** Classes beside `KernelLocus` and
   `AgentManagedLocus` (Cerebrum `history.py:253-553`), with the same
   methods (`start_user`, `writer`, `consumer`, `lister`,
   `session_scope`, `audit_rows`, `capture`, `backend_usage`,
   `finish_user`), and the v1 path's counterpart in `pipeline.py`.
   Each agent they return is an adapter: its `run` starts one graph run
   and returns the node's result. The adapters keep the attributes and
   the seams `apply_variant` patches (Cerebrum
   `cerebrum/example/agents/variants/base.py`, from line 269):
   `user_id`, `share_memory`, `retrieval`, a module-level
   `create_memory` and `update_memory` for a shared writer
   (`base.py:156-176`), and `memory.pipeline` for a replicated agent
   (`base.py:179-201`). The variants and the faults then reach a
   LangGraph agent through the channels they use today.
   `apply_variant` knows the loci `kernel`,
   `replicated` and `native` only (`base.py:38`), so the adapters
   report `kernel` for the shared locus.
5. **Harness seams.** Four condition names with their loci (Cerebrum
   `benchmarks/shared_memory/conditions.py:13-45`); a `runtime` field on
   every results file and trial (`aios` or `langgraph`), with the locus
   still `kernel` or `replicated` so the analyses read the cells as
   they are; and the pre-flight read from the builder's report in place
   of `GET /memory/config` (Cerebrum `run_evaluation.py:182-357`,
   `pipeline.py:634-642`).
6. **Tests.** The equivalence test. The static scan. The difference-1
   demonstration on LangGraph: with a barrier per agent a read during
   another agent's accepted write misses it; through the layer it waits
   and sees it (as Cerebrum `tests/agents/_replicated_checks.py:198-245`
   shows for the library). A session test: a write that claims another
   user lands in the session's user's partition with
   `identity_overridden`. A test that no SDK request is sent during a
   LangGraph trial.

**What is reused, unchanged.** The library, the providers and
`provider_config`; `ReplicatedMemory`; `run_v2_session`,
`extract_validated` and the agents' prompts; the datasets (`pilot_v1`;
`pilot_v2`, the first 30 users of `users_v2` revision 4; `agents_n6`
for option C) and `pilot_v1_schedule.json`; the variants and the
faults; `run_history` and the trial records; the scorer (`probes.py`,
`judge_free.py`, `metrics.py`) and the analyses (`pilot_analysis.py`,
`bench_v2_analysis.py`, `stress_report.py`); `rejudge.py` for the
judged scores.

**The cells.** Per backend; "shared" is the layer's locus.

| Part | Benchmark | Loci | Conditions | Cells | Users per cell |
|---|---|---|---|---|---|
| Core | v1: `pilot_v1`, the pilot's schedule | shared, replicated | H = 0, H = 2 | 4 | 30 |
| Core | v2: `pilot_v2`, revision 4 | shared, replicated | H = 0 | 2 | 30 |
| Option A | v2 | shared, replicated | `writer_scoped` | 2 | 30 |
| Option B | v2 | shared, replicated | `wrong_user` | 2 | 30 |
| Option C | v2 at six agents (`agents_n6`, revision 4) | shared, replicated | sequential, `concurrent` | 4 | 30 |
| Option D | v2 | shared, replicated | H = 2, the seeded cycle | 2 | 30 |

The core is what was asked: v1 at H = 0 and 2, and v2's decision items
and deletion probe. At H = 0 the v2 cells are predicted to tie, so on
their own they show that the library's deletion, supersession and
selection carry over, not that placement matters. Each option adds a v2
condition where the loci are predicted to part or a probe to fail:
- A: the deletion probe can fail on this runtime: for the 10 echo
  users of users 0 to 29, whose revoked value another writer also
  wrote (an echo, `BENCHMARK_V2.md:107-112`), once the revoke is the
  writer's own list and delete instead of the forget.
- B: the identity binding, read by `misfiled_rows` (`METRICS.md:322`)
  and by the decision items' `foreign` picks.
- C: the barrier, read by `late_covered`, `stale_read` and
  `late_forget`. AIOS's concurrent cells ran at six agents (Cerebrum
  `results/stress_smoke_s18`), so the pair needs its own sequential
  cells.
- D: a V2 writer's rows lie outside a forget's reach in replicated
  (`BENCHMARK_V2.md`, Amendment 4: "H = 2 is reported, not required").
  A scored v2 run at H > 0 "needs a v2 schedule", and none exists
  (`BENCHMARK_V2.md`, "Loci and backends"), so D is reported only.

**What is measured.** By the harness's own modules, from the same
diagnostics the library gives in AIOS:
- v1: `memories_missing` and its split, `cross_user_rows`,
  `private_rows_from_others`, `profile_facts_in_block`,
  `profile_facts_in_answer`, `raw_payload_rows`, the keyword score,
  `variants_applied` and `variants_not_applied` (`HETEROGENEITY.md`,
  "Schedule"), the block; later the judged LLM score.
- v2: the six probes' outcomes with their block checks; for deletion,
  the split by echo user, `revoked_value_rows`, each revoke's path and
  report, the guard's stages and each failure's carrier; the decision
  items' accuracy, error kinds and `options_in_block`; under an
  option, the stress measures.
- Both: tokens (model, backend, embeddings), wall time per turn,
  `pipeline_version`, the layer's call counts, `barrier_waits`.
- Not on LangGraph: `schedule_wait_ms` (no scheduler) and the
  kernel-log checks.

**Runs and calls.** One trial is one user. Counts per cell of 30
users:

| Per cell | v1 | v2 |
|---|---|---|
| Agent turns (graph runs) | 90: two writers and the consumer per user | 420: 6 writer turns (one per session, `history.py:893-902`), 6 probes and 2 decision items per user |
| Calls to the cell's model | 90: 2 extractions and 1 answer per user. A writer's retry adds one; the pilot's 24 kernel and replicated cells had none (2.00 writer calls per trial) | 240: 6 probes and 2 decision items per user (a trial's `token_usage` counts the probes' 6.00 calls, and each decision item records its own). A v2 writer calls no model (0 writer calls in `decision_functional_s20`) |
| Memory writes | 90: 2 writer rows and the turn per user | 534 writes and 30 forgets (counted in `users_v2.jsonl`, users 0 to 29) |
| Embedding calls, in-house (Ollama) | 180 at H = 0 (6.00 per trial in the pilot; 4.90 in replicated at H = 2) | about 1,020 (34.0 per user in `decision_functional_s20`) |
| Mem0 extraction calls (Azure GPT-4o), on Mem0 only | about 90 (2.50 to 3.00 per trial in the pilot) | 534 (17.80 per user in `bench_v2_smoke_s17`) |
| Primary judge calls at k = 1 | 30 | 30, if the integration probe is judged |
| Second judge calls at k = 1 | 9 (`FULL_GRID.md`'s subset rule on users 0 to 29: 3 of the 10 echo users and 6 of the other 20) | 9 |

- **The core on one backend:** 6 cells, 180 trials, 1,200 graph runs,
  840 model calls, 120 primary judge calls (180 with v2's integration
  probes) and 36 second-judge calls (54).
- **Options A, B and D**, each two cells: 60 trials, 840 graph runs,
  480 model calls.
- **Option C**, four cells: 120 trials and 960 model calls. `agents_n6`
  holds 246 writer turns for users 0 to 29 and the same 564 events, so
  a sequential cell has 486 graph runs and a concurrent one 804, where
  each write event is its own run (`STRESS_DIMENSIONS.md`,
  "Concurrency"; `history.py:964-980`): 2,580 in all.
- **A second backend** doubles the cells. Mem0 adds its extraction:
  about 1,430 calls in the core.

**Time and cost, extrapolated.** The rule: the seconds per user of the
stored AIOS cell of the same benchmark, locus, backend and H, from the
first and last timestamp of the cell's log, times 30 users.
LangGraph's own overhead is taken as zero, which nothing measures.
- **Qwen, in-house.** v1: 49.2 and 44.5 s per user in the kernel (H =
  0, 2) and 38.3 and 37.2 in replicated (`pilot_v1_hetero`, whose cells
  were judged in their run, so their logs include the judge's calls):
  5,076 s, 1.4 hours. v2: 73.8 and 76.6 s per user
  (`decision_functional_s20`, 5 users per cell, judge-free, revision
  4): 4,512 s, 1.3 hours; at the 30-user judged smoke's 98.9 and 99.6
  (`bench_v2_smoke_s17`, revision 3, six turns), 1.7 hours. The core:
  about 2.7 to 3.1 hours, and no model cost.
- **GPT-4o, in-house.** v1: 13.9, 13.4, 14.0 and 12.4 s per user:
  1,611 s, 0.45 hours; 0.0054 to 0.0075 USD per trial without the
  judge (Cerebrum `llm_gpt-5.4.md`, "Cells"; `cost.py:25-30`, `:65-76`
  sums the assistant, writers, backend and embeddings), so 0.6 to 0.9
  USD for 120 trials. v2: no stored v2 cell used GPT-4o as its
  assistant. Qwen's tokens priced as GPT-4o give 0.0173 USD per user
  (`decision_functional_s20`, decision items included), about 1.0 USD
  for 60 users: a guess at scale, not a measure.
- **Mem0.** v1: 0.054 to 0.073 USD per trial without the judge, 6.5 to
  8.8 USD for 120 trials. v2: 0.361 USD of extraction per user (139,721
  prompt and 1,123 completion tokens at `prices.yaml:11-13`'s 2.50 and
  10.00 USD per million), 21.7 USD for 60 users.
- **The judges.** About 0.0057 USD per answer for the primary judge at
  k = 1 (7.69 USD for 1,350 answers, at OpenAI's list price for
  GPT-5.4; Azure's own price was not read) and 0.0037 for the second
  (4.95 USD for 1,350; Cerebrum `results/s20_rejudge/PROVENANCE.md`):
  about 1.0 and 0.2 USD for the core.
- Qwen's speed varies about twofold with the laptop's heat and power
  (`DEV_STATUS.md`, known issue 48).

**Before any scored run.** In this order: the tests; a functional
check, judge-free, on users 0 to 4 of every cell; then the cells with
`--no-judge`. The functional check must show that the two loci's
in-house blocks are equal at H = 0, that `variants_applied` and
`variants_not_applied` equal the AIOS cells' user by user on the same
schedule, that no SDK request was sent and no kernel was listening,
and that the layer's counts agree with the trials'.

**What would count as the same finding.** Written before any run; the
thresholds are open decision 5. "Shared" stands where the pilot says
kernel.

Preconditions, judge-free: the library carried over.
- P-a. The equivalence test passes, and `PIPELINE_VERSION` is one value
  over both loci.
- P-b. v2, H = 0, in-house, in both loci: no deletion block holds the
  revoked value, `revoked_value_rows` is empty for every user, every
  revoke went through `forget`, and the guard was armed and dropped
  nothing (Amendment 4's functional-check criteria). The deletion
  probe's pass rate is reported and compared between the loci, each
  failure with its carrier; an `answer only` failure (the value in the
  answer and in no block) is the model's. In AIOS, revision 3's smoke
  passed deletion for 30 of 30 users in both loci, every revoke
  through the forget and no stored carrier (`bench_v2_smoke_s17`);
  revision 4's check passed 4 of 5 in both in-house loci, one `answer
  only` failure each (`decision_functional_s20`).
- P-c. v2, H = 0: decision accuracy does not differ between the loci
  (exact McNemar over the 60 paired items), and every `stale`,
  `revoked` or `foreign` error has its option's value in the block.
  AIOS's cells with memory have 5 users: 10 of 10 in both loci, on
  in-house and on Mem0 (`decision_functional_s20` at `de12cbf`). The
  floor without memory is 0.18 [0.14, 0.23] for Qwen (`METRICS.md`,
  "Decision probe") and unmeasured for any other model.

The finding: v1, shared − replicated, 30 paired users, on the judged
metric of `METRICS.md`, with the keyword score and the hybrid beside
it.
- F-a. H = 0 is a tie: the 95% interval includes 0 on Profile and on
  Integration.
- F-b. H = 2 is a gap: at least +0.25 on Profile or Integration, the
  interval above 0 (the pilot's condition (i), on one backend).
- F-c. The gap grows: H2 − H0 on that dimension is positive, its
  interval above 0 (condition (ii)).
- F-d. Judge-free (condition (iii)): the shared locus's leak rate is 0,
  and its `memories_missing` rate at H = 2 is below the replicated
  locus's. Sharper, and expected to hold exactly since the schedule
  decides it: each user's `memories_missing` equals the AIOS cell's (16
  of 30 trials in the kernel, 26 of 30 in replicated, from the
  pilot's 0.53 and 0.87).

Reproduced: P-a to P-c and F-a to F-d hold. Not reproduced: F-b's mean
is at or below 0, or F-d fails. Anything else is reported as mixed and
goes back to the user, as `PILOT.md` does with "no rule outcome".

Under an option, the same prediction as AIOS's:
- A: the echo users fail deletion in both loci (AIOS, 5 users: 0 of
  the 2 echo users passed in either locus on in-house, 1 of 2 on Mem0,
  `decision_functional_s20` at `de12cbf`).
- B: shared has no misfiled row, `identity_overridden` on every
  request of the faulty writer, and no `foreign` pick. Replicated has
  misfiled rows and at least one such pick (AIOS, 5 users: 0 `foreign`
  picks of 10 in the kernel against 3 of 10 in replicated, on in-house
  and on Mem0, `decision_functional_s20` at `de12cbf`).
- C: shared reads no covered late write; replicated reads some (AIOS,
  six agents, 30 users, in-house: the kernel's 180 probes waited and
  read none; replicated read 552 late writes and lost 2 contradiction
  probes to stale reads, `DEV_STATUS.md`, Subtask 18, "Smoke").

Not required: equal scores across the runtimes. The model is reached
through another client, so the answers differ. The difference of the
two gaps (LangGraph's minus AIOS's, same users, one judging window) is
reported, not tested.

**What this would not show.** A native LangGraph locus (agents using
LangGraph's own store as its docs show) is not part of it. Nor is an
async graph, a deployment of several processes, a retried node, or an
agent that attacks the layer.

## Risks

1. **A second copy of the acceptance rules.** Under open decision 1,
   option a, the layer re-implements `manager.py:347-491`. A difference
   between the runtimes could be the copy's. The equivalence test
   bounds it for the paths it covers; the move into the library removes
   it.
2. **No wall around the layer.** An agent in the same process can
   reach the store and the model. Construction and two checks are what
   stands in the way.
3. **A blocking wait in an event loop.** Called from an async node, the
   barrier's wait stops the loop. The minimal run is sync; an async app
   needs the thread hop.
4. **Timeouts read as passes.** A wait that times out lets the read go
   on. `barrier_waits` and the timing measures must be read with every
   v2 outcome, as in the kernel.
5. **At-least-once nodes.** A retry or a resume repeats a node's
   writes, and the library has no idempotency key. The reproduction
   runs without retries; a deployment could not.
6. **Another route to the model.** The kernel calls LiteLLM with its
   own `num_ctx`, seed and message list (Ollama truncates a long prompt
   silently, known issue 29). A LangChain model class sends its own
   request, and `ChatOllama` leaves `num_ctx` to Ollama's 2048 unless
   it is set (R14:577-581). Its token counts come from another counter.
   Answers and costs are comparable within the runtime, not across.
7. **Dependencies.** LangGraph is installed nowhere here, and nothing
   shows it installs beside the pins. A third venv may also differ in
   numerics: a report's last digits already move with numpy's and
   scipy's versions (`DEV_STATUS.md:3721-3722`, Subtask 19). Whether
   that reaches a block's ranking was not checked; byte-equal blocks
   would show it.
8. **Variants through new agents.** A variant reaches an agent through
   seams of the agent's module and attributes. If the LangGraph
   adapters miss one, H = 2 means something else. The check on
   `variants_applied` and `variants_not_applied` against the AIOS cells
   is what catches it.
9. **The judge window.** The primary judge is called through a kernel
   (Cerebrum `benchmarks/shared_memory/judge.py:303`, `:380`), and
   scores from two windows are not compared (`FULL_GRID.md`, "The judge
   window"). The LangGraph answers must be judged with the AIOS cells
   they are set against.
10. **Thirty users, one backend, one model.** The pilot's in-house
    intervals at H = 2 start at +0.52 or above; a smaller effect on
    LangGraph could miss F-b without being absent.
11. **The decision items' reference is thin.** With memory, AIOS has 5
    users per cell, Qwen only; its Mem0 cells were committed while
    this was written (`de12cbf`).
12. **Deletion failures that are not the memory's.** Revision 4's
    check had an `answer only` deletion failure in each in-house locus
    (the value in no block). P-b therefore rests on the block and store
    criteria, with the answer-level rate reported.
13. **Checkpointed blocks.** A deployment with a checkpointer keeps
    each thread's state (D4:68). An app that put the injected block
    into state would keep a copy that a forget does not reach. The
    layer keeps blocks out of state, and the reproduction compiles no
    checkpointer.
14. **A moving target.** `langgraph` 1.2.24 was uploaded on the day this
    was written. The reproduction pins its versions.
15. **Cost counters.** Backend usage is counted by the SDK's LiteLLM
    callback and its Ollama wrapper; the model's usage would come from
    LangChain's metadata. The two must be reconciled before a cost is
    reported.
16. **Wall time.** Extrapolated from AIOS cells and a laptop whose
    speed varies twofold.

## Open decisions

1. **Where the acceptance rules live.**
   (a) In the layer, written in Cerebrum as a client of the library: no
   library change, a second copy.
   (b) Moved into the library first, as one host object the kernel and
   the layer share: one copy, a new `PIPELINE_VERSION`, a change to the
   kernel's request path.
   (c) `MemoryManager` itself, built with a patched config and fed
   syscall carriers: the most reuse, and the syscall and SDK types come
   along.
   Bears on: whether the paper may say "the same code", on risk 1, and
   on when the library is frozen for the full grid.
2. **The agents' form.**
   (a) Plain `StateGraph` nodes: the model request as the kernel sends
   it.
   (b) `create_agent` with a `wrap_model_call` hook: the idiom
   LangChain's docs lead with, and a prompt that matches the kernel's
   only by using `messages` against its description.
   Bears on: prompt parity with AIOS against how native the app looks
   to a reviewer.
3. **The one model and its route.**
   (a) Qwen-2.5:7B through `ChatOllama`: no cost, about 3 hours, the
   only model with a no-memory floor for the decision items.
   (b) GPT-4o through `AzureChatOpenAI`: for v1, 0.6 to 0.9 USD and
   about 0.45 hours before the judges; for v2, about 1.0 USD by a
   guess, its time unmeasured.
   (c) Either through `ChatLiteLLM`, the client library the kernel's
   adapter uses.
   Bears on: cost and time, risk 6, and P-c's reading.
4. **One backend or two.**
   (a) In-house only: verbatim rows, no extraction cost, short writes
   (under concurrency the kernel's in-house probes waited a median 114
   ms, `DEV_STATUS.md`, Subtask 18, "Smoke").
   (b) In-house and Mem0: about 28 to 31 USD of extraction for the
   core, Mem0's extraction noise, and writes that take seconds, which
   is where a barrier matters most.
   Bears on: cost, and on how strong option C's contrast can be.
5. **The rule.**
   (a) The pilot's thresholds on one backend, as F-a to F-d.
   (b) A directional rule (the sign of the H = 2 gap and of H2 − H0).
   (c) The judge-free F-d alone as the criterion, the scores reported.
   Bears on: what the paper may claim from 30 users, and risk 10.
6. **v2 beyond H = 0.** None, or any of options A to D. Without one, v2
   shows that the library carries over; with B or C it tests the two
   mechanisms this spec is about. Each pair costs 480 model calls (C:
   960).
7. **How strong the wall is.**
   (a) One process: construction, the scan and the counts.
   (b) The layer in a process of its own.
   Bears on: a reviewer's "what stops an agent", against rebuilding the
   kernel's memory half.
8. **The form of concurrency**, if option C runs.
   (a) The harness's threads, one graph run per event: comparable with
   AIOS's cells.
   (b) One run that fans out with `Send`: the race inside a super-step,
   which only LangGraph has.
   (c) Both.
9. **Where the code lives and which venv runs it.** Cerebrum, in its
   venv; Cerebrum, in a third venv; or a repository of its own. Bears
   on: risk 7 and on how separate from AIOS the reproduction reads.
10. **When it is judged.** In the full grid's window, with the AIOS
    cells it is compared with (it then waits for Subtask 23's
    `rejudge.py`), or in a window of its own, with scores that are not
    set beside the grid's.
