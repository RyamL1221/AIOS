# NeurIPS 2027 Development Status

Branch: `feature/NeurIPS-2027-changes` in both repos, based on `main`.
Baseline tag: `workshop-postrun` (AIOS `44529a4`, Cerebrum `e7898fa`).
`feature/self-improving-memory` is a separate project: its docs,
`.kiro/steering` text on gating, `scripts/e2e_smoke.py` and subtask tags
do not describe this branch.

## Rules

1. Every fix or feature includes a test that fails without it.
2. Update this file at the end of each subtask.
3. Tag subtasks `neurips-subtask-NN`. The `subtask-NN` names are taken by
   the self-improving project.
4. After any edit to `../Cerebrum`, run
   `.venv/bin/python -m pip install ../Cerebrum --no-deps --force-reinstall`.
   The venv is shared across branches, so reinstall after switching too.
5. Never run the Cerebrum suite while a kernel listens on port 8000.
6. From Subtask 15 on, at most two review passes per subtask: one
   adversarial review of the code and the write-up, then one
   verification pass of the fixes. A third pass only if the second
   found an error (a wrong value, a wrong claim, a bug), not an
   imprecision. Mutation testing runs once per subtask, on the final
   code, not per reviewer. This file states what the tests pin and no
   more: where a claim outruns the tests, weaken the claim rather than
   add tests, unless the untested rule affects a reported number.
7. From Subtask 17 on, nothing goes into `../repo-artifacts/` but
   through `scripts/archive_artifacts.py` (a driver's `ARCHIVE`, or by
   hand for a mutation run's outputs), which refuses a copy when any
   file holds a configured key value or a fragment of one.

## Subtasks

| # | Subtask | Status |
|---|---------|--------|
| 1 | Single kernel retrieval path | Done |
| 2 | Conversation writes through the kernel; owner-only by-id writes | Done |
| 3 | Re-validate `kernel_shared` and `mem0_default` | Done |
| 4 | Rename `mem0_default` to `kernel_private`; judge prompt v2; re-judge | Done |
| 4b | Judge retries, then fails the trial (no keyword-only fallback) | Done |
| 5 | Provider contract; Chroma in-house provider; update stamping | Done |
| 6 | Native agent-managed conditions (Mem0, in-house) | Done |
| 7 | Cost instrumentation | Done |
| 8 | Memory pipeline library; replicated-logic locus condition | Done |
| 9 | Fixed paired dataset; stored-content parity; writer validation | Done |
| 9c | Explain the `kernel_shared` deficit (investigation) | Done |
| 9d | Shared compact block; fixed decoding; mem0ai pinned; greedy judge; re-baseline | Done |
| 10 | Heterogeneity stress dimension (variants V1-V5, judge-free measures) | Done |
| 11 | Pre-registered locus × heterogeneity pilot on pilot_v1: GO | Done |
| 14 | Accumulating multi-session benchmark (v2) | Done |
| 15 | Complete deletion and supersession | Done |
| 16 | Graphiti backend and native condition | Done |
| 17 | A-MEM backend and native condition | Done |
| 18 | Agent count, concurrency and faulty-agent stress dimensions; event-driven scheduler | Done |
| 19 | Kernel ablation switches | Done |
| 20 | Judge reliability, second judge, decision probe, metrics | Done |

### Subtask 1

`MemoryManager.retrieve_for_agent` now serves injection and SDK search.
Details, behavior changes and the before/after result are in
`docs/RETRIEVAL_PATH.md`. Smoke: `scripts/retrieval_smoke.py` against a
running kernel.

### Subtask 2

Every write reaches the store through `address_request`. The extractor
stamps its write on the request thread, and by-id update and delete are
owner-only. See "Writes" in `docs/RETRIEVAL_PATH.md`.

### Subtask 3

900 trials, 0 failed. `kernel_shared` reproduces (8 of 9 cells, largest
shift 0.20); `mem0_default` shows zero assistant-visible memories in all
450 trials. Both GPT-4o cells were re-run after fenced JSON replies broke
synthetic data generation. See `docs/REVALIDATION.md`. Re-runs need a new
`RUN_PREFIX` for `scripts/run_revalidation.sh`.

### Subtask 4

- `mem0_default` is now `kernel_private`. The old name is a deprecated
  alias with a warning (Cerebrum `benchmarks/shared_memory/conditions.py`,
  the only alias table), and `results_path` reads old result directories,
  which keep their names. Remaining `mem0_default` matches in Cerebrum:
  the alias table, the notes explaining the rename, historical docs, and
  `benchmarks/human_rating`, a frozen workshop-era study whose committed
  ratings key on the old name.
- Judge prompt v2 (`JUDGE_PROMPT_VERSION = 2`): the system prompt names
  no mechanism, and the plausible-actions section is gone, because
  results files never stored the actions and a re-judge could not show
  them. The rubric and the rest of the user prompt are byte-identical.
  New results record `judge_prompt_version` and `judge_prompt_sha256`;
  files without them used v1. New results also store `plausible_actions`.
- The 900 Subtask 3 responses were re-judged with v2
  (`benchmarks/shared_memory/rejudge.py`, judge calls only). Comparison:
  "Judge prompt v2" in `docs/REVALIDATION.md`. The v2 numbers are the
  paper's baseline. No cell's mean moved more than 0.25 (largest
  -0.153), but Spearman rho was below the expected 0.8 in 7 of the 8
  `kernel_shared` cells where it is defined (0.571-0.870): scores sit on
  4 and 5, so per-trial v1 and v2 scores are not interchangeable.
- `written_memories` was empty in every trial ever run: the harness
  patched `cerebrum.memory.apis.create_memory`, but the agents import it
  by name. The pipeline now patches the agents' modules too, and
  `memory_counts` is derived from `written_memories`. The 900 stored
  trials keep their empty values.
- Mem0 LLM sync on Azure works: the Mem0 Azure client takes the kernel's
  `AZURE_API_*` variables, and the synced LLM now reaches the per-user
  clients, which do the writes (before, only the default client got it).
  Since Subtask 7 the synced LLM is Mem0's `litellm` provider instead.
  `scripts/retrieval_smoke.py --kernel-log <log>` checks a GPT-4o chat.
- Paper (Subtask 12): §4.1's TODO is now resolvable. The condition is
  `kernel_private`, the kernel pipeline with sharing off, with
  `after_visibility` = 0 in all 450 trials, and the "Second" results
  point can use the v2 numbers. paper_v2 is in neither repo, so the
  edit itself waits for Subtask 12.

### Subtask 4b

`HybridJudge.evaluate` (Cerebrum `benchmarks/shared_memory/judge.py`)
calls the LLM judge up to `JUDGE_RETRIES` (3) times and raises
`JudgeFailed` if none gives all three scores; `combine` refuses missing
LLM scores. `run_evaluation.py` marks such a trial failed, with no
scores and the response kept for a later re-judge; `rejudge.py` uses
the same path. `TrialResult` records `scorer` (`hybrid_keyword_llm`:
the keyword score averaged with the LLM's, rounded) and
`judge_attempts`. `keyword_score` stays: it is the keyword half of
every score, not only the fallback. Closes known issue 9. Tests:
Cerebrum `tests/agents/test_judge_retry.py`.

### Subtask 5

- Provider contract: `docs/PROVIDER_CONTRACT.md`, `MemoryProvider` in
  `aios/memory/providers/base.py` (`add` / `search` / `list` / `get` /
  `update` / `delete` / `capabilities`, `Candidate` rows, five required
  metadata keys stamped by the kernel). The old `MemoryResponse` provider
  methods are gone. Visibility moved to `aios/memory/visibility.py`; no
  provider filters by it, and `retrieve_memory_raw` now goes through
  `retrieve_for_agent`. Contract suite:
  `tests/modules/memory/test_provider_contract.py` over `chroma_inhouse`,
  `mem0` (both real stores, local Ollama) and `in_house` (29 tests).
- `provider: "in-house"` is `ChromaInHouseProvider`: persistent Chroma,
  one cosine collection per user, verbatim, no LLM. The old dict
  provider is `in-memory`, for tests. The injector and extractor are
  wired for `mem0` and `in-house` (`PERSONALIZATION_PROVIDERS`).
- Mem0 `search` is scored, but not with Mem0's `search()`: its Chroma
  adapter returns the squared L2 distance as `score`, clamped at 1.0, so
  the rows at cosine 0.5 or below tie in nearest-first order and the
  relevant rows above 0.5 follow from the least similar up (verified on
  a real store; wording corrected in Subtask 14). The provider queries
  Mem0's own vector store and converts the distance to cosine. Why the
  kernel used `get_all` since June, and why `threshold=0.0` was never the
  fix: "Mem0" in `docs/PROVIDER_CONTRACT.md`.
- `memory.embedding` pins `ollama` / `nomic-embed-text` / 768 for both
  backends; `/memory/config` reports it with the provider and its
  capabilities, so every results file records them.
- `relevance_threshold` defaults to 0.0 (config and code); diagnostics add
  `threshold_used`. The Subtask 19 ablation varies the threshold.
- `update_memory` is stamped against the write barrier
  (`test_update_stamping.py`); known issue 5 is fixed.
- Harness: `run_evaluation.py --provider <name>` refuses to run against a
  kernel serving another provider; `InjectionDiagnostics.threshold_used`.
- Tests retired, replaced by `test_mem0_contract_unit.py` (fake Mem0
  client, no Ollama) and the contract suite: `test_mem0_provider_user_filter`,
  `test_mem0_cross_user_retrieval`, `test_mem0_cross_agent_retrieval`, and
  the `get_all` / polling classes of `test_mem0_cross_user_isolation` and
  `test_mem0_provider_searchability`. They tested the removed `get_all`
  retrieval path. Doubles written against the old methods subclass the
  test-only shim `tests/modules/memory/_doubles/legacy.py`.

**Behavior check** (Cerebrum `results/provider_smoke/`, 30
`kernel_shared` trials per cell, judge v2; a smoke, not a verdict). All
180 trials completed with diagnostics; `scores_present` true and
`threshold_used` 0.0 in every trial; every trial injected one profile and
one task context, as in Subtask 3. Means (v2 revalidation cell in
brackets):

| Backend | Model | Profile | Task | Integration |
|---|---|---:|---:|---:|
| Mem0 | GPT-4o | 4.70 (4.63) | 5.00 (5.00) | 4.67 (4.57) |
| Mem0 | Llama-3.1:8B | 3.57 (3.77) | 4.43 (4.46) | **3.27 (3.57)** |
| Mem0 | Qwen-2.5:7B | 3.87 (3.69) | 4.73 (4.74) | 3.77 (3.55) |
| In-house | GPT-4o | 4.70 (4.63) | 5.00 (5.00) | 4.67 (4.57) |
| In-house | Llama-3.1:8B | 3.83 (3.77) | 4.57 (4.46) | 3.53 (3.57) |
| In-house | Qwen-2.5:7B | **4.27 (3.69)** | 4.60 (4.74) | **3.97 (3.55)** |

Flagged (off by more than 0.25): Mem0 Llama integration -0.31, in-house
Qwen profile +0.57 and integration +0.41. Qwen also moved most on Mem0,
and was the cell that changed between the workshop and Subtask 3 (known
issue 8).

One prompt change: the injected set is the same, but its order is not.
Rows are now sorted by similarity, and the task context outscores the
profile, so it comes first in 177 of 180 trials; in every Subtask 3
trial the profile came first (storage order). Open decision 1.

### Subtask 6

- Spec first: `docs/NATIVE_USAGE.md` (committed `e29e9da`, before the
  agents), citing the Mem0 and Chroma documentation pages it follows,
  with the Mem0 extraction check. Evidence: Cerebrum
  `results/native_extraction_check/`.
- Extraction check: 20 real writer outputs under gpt-4o, qwen2.5:7b and
  llama3.1:8b, as JSON and as natural language. None stored nothing or
  mangled the JSON; only gpt-4o kept every fact (the local models lost
  some, qwen with JSON usually the user's name) and it was 7-10x faster.
  Choices: `memory.backend_llm` = Azure gpt-4o, writers send natural
  language (Mem0's documented input; 4 of the 20 real outputs used other
  keys than the schema, so `native/render.py` maps aliases). 5-user
  writer-to-consumer check: a `user_id`-only search returns both writers'
  memories, and the sharing convention removed the private note each
  time.
- Code: Cerebrum `cerebrum/example/agents/native/` (agents, the shared
  sharing filter, backend setup, renderer); conditions `native_mem0`,
  `native_inhouse` (`conditions.NATIVE_CONDITIONS`, not part of
  `--method all`). The kernel serves the LLM calls only. The
  AssistantAgent records kernel-shaped `injection_diagnostics`
  (`injection_status` = `agent_reported`).
- Pre-flight (`run_evaluation.check_kernel_mode`): a native condition
  needs `auto_inject` and `auto_extract` false, `kernel_shared` /
  `kernel_private` need `auto_inject` true; `/memory/config` now reports
  both and `backend_llm`.
- Latency for native trials is the assistant's retrieval plus its LLM
  call; its conversation write after the response is excluded.
- The Cerebrum venv needs `azure-identity` (Mem0's Azure LLM); added to
  `requirements.txt`. The driver exports the Azure variables from
  `AIOS/.env` to the harness only.

**30-trial smoke** (Cerebrum `results/native_smoke/`, judge v2, Mem0's
internal LLM gpt-4o for every cell). 180 trials, 0 failed, 0 memory
operations in every kernel log. Means, with v2 `kernel_shared` and
`kernel_private` in brackets:

| Condition | Model | Profile | Task | Integration | Injected (median) |
|---|---|---:|---:|---:|---:|
| native_mem0 | GPT-4o | 4.70 (4.63 / 1.07) | 5.00 (5.00 / 1.02) | 4.53 (4.57 / 1.01) | 7.5 |
| native_mem0 | Llama-3.1:8B | 3.90 (3.77 / 1.09) | 4.73 (4.46 / 1.27) | 3.80 (3.57 / 1.02) | 7 |
| native_mem0 | Qwen-2.5:7B | 4.03 (3.69 / 1.18) | 4.87 (4.74 / 1.30) | 3.90 (3.55 / 1.09) | 7 |
| native_inhouse | GPT-4o | 4.73 (4.63 / 1.07) | 5.00 (5.00 / 1.02) | 4.73 (4.57 / 1.01) | 2 |
| native_inhouse | Llama-3.1:8B | 3.90 (3.77 / 1.09) | 4.60 (4.46 / 1.27) | 3.67 (3.57 / 1.02) | 2 |
| native_inhouse | Qwen-2.5:7B | 3.40 (3.69 / 1.18) | 4.87 (4.74 / 1.30) | 3.43 (3.55 / 1.09) | 2 |

As the design expects, both native conditions sit at `kernel_shared`
level on this single-interaction benchmark, far above
`kernel_private`. `native_mem0` is higher than `kernel_shared` for the
small models (+0.13 to +0.35); its block is about 7 short facts that
gpt-4o extracted, against the kernel's two formatted records, so the
block's content differs, not only who manages it. Mem0's scores were its
inverted ones: 83-87% of injected memories scored exactly 1.0, so its
scores carry no similarity information (the tied rows keep Chroma's
nearest-first order). One Llama `native_mem0` trial
injected no task context. `native_inhouse` injects the same two memories
as the kernel, ordered by cosine similarity (profile first in 27 of 90
trials).

### Subtask 7

Every `TrialResult` now records `token_usage` (the assistant's call),
`writer_tokens` (the two writers' extraction calls), `backend_llm_tokens`
and `embedding_tokens` (the memory backend's own calls), each
`{calls, prompt_tokens, completion_tokens, total_tokens, models}`, and a
`latency_breakdown`. This holds for kernel and native conditions alike.
Nothing here changes what is stored, retrieved or sent to a model.

- **Assistant tokens.** The kernel captures `response.usage` at the
  LiteLLM call site (`adapter.py`), ported by hand from
  `feature/self-improving-memory`. It returns `token_usage` and
  `llm_timing` (`llm_ms`, the model call; `schedule_wait_ms`, the
  scheduler's wait before it) as siblings of `response`, the same shape
  as `injection_diagnostics`. The writers return the usage of their
  extraction call. The four `PipelineResult` sites fill the fields
  through `pipeline.cost_fields`.
- **Backend tokens.** Cerebrum `cerebrum/utils/usage.py`, shared by the
  kernel and the harness:
  - Backend calls are tagged with the trial's user id (`tagged`; each
    trial has a unique user).
  - A LiteLLM success callback records each tagged call (purpose
    `backend_extraction`). A pre-call hook marks the call in flight, so
    a read waits for callbacks still running on LiteLLM's thread.
  - A wrapper on the Ollama `embed` client records each tagged call
    (purpose `embedding`, Ollama's `prompt_eval_count`). Mem0 has no
    LiteLLM embedder.
  - Untagged calls are ignored; these include the kernel's own
    assistant calls.

  The kernel tags in `address_request` and `retrieve_for_agent`, and
  `GET /memory/cost?user_id=` returns and clears the trial's records.
  The harness reads it after judging, so the background conversation
  write has finished. The native agents tag their own backend calls,
  and the AssistantAgent reads the accumulator in-process.

  Mem0's LLM is now Mem0's `litellm` provider in both places:
  - native: `azure/gpt-4o`, previously Mem0's `azure_openai` provider
    for the same deployment;
  - kernel sync: `<backend>/<model>`.

  The Cerebrum venv needs `litellm==1.83.0`, the kernel's version,
  added to `requirements.txt`.
- **Latency.** The harness records these keys in `latency_breakdown`:
  - `barrier_wait_ms`, `search_ms` (the provider calls) and `select_ms`
    (partition through cap), timed in `retrieve_for_agent`;
  - `format_ms` (formatting, budget and block), timed in the injector;
  - `schedule_wait_ms` and `llm_ms`, from the syscall path.

  The kernel adds them to the chat `injection_diagnostics`, and the
  native AssistantAgent records the same keys itself (its
  `barrier_wait_ms` is 0).

  `kernel_overhead_ms` is the four memory stages **plus
  `schedule_wait_ms`**. This departs from the spec, which named only the
  four stages. The FIFO scheduler sleeps `batch_interval` (1.0 s)
  before collecting LLM requests, so the assistant's request waited
  975 ms on average. That is 14% of latency, against 40 ms for all
  four memory stages. Without the wait, the four stages plus `llm_ms`
  fall 1-30% short of measured latency (7-24% in `kernel_shared`).
  With it, the sum reconciles within 0.1% in every trial. The wait is
  time the kernel adds, so it belongs in the overhead. The wait and the
  four stages are each also recorded on their own.
- **Cost model.** Cerebrum `benchmarks/shared_memory/cost.py` prices
  trials from `prices.yaml` (dated 2026-11-03; gpt-4o 2.50 / 10.00 USD
  per 1M input / output tokens from price aggregators, since
  Microsoft's page was not checked directly; local models 0). It splits
  the cost into assistant, writers, backend and embedding.
  `python -m benchmarks.shared_memory.cost <dir> --csv ...` writes one
  row per cell: means of every token and latency field, the cost split,
  and `tokens_per_quality` (mean total tokens divided by the mean of
  the three judge scores).
- **Tests.**
  - AIOS `tests/modules/syscall/test_cost_instrumentation.py`:
    - adapter usage capture with a mocked LiteLLM response;
    - partial usage;
    - the scheduler wait;
    - that the latency fields sum;
    - the retrieval stage timers;
    - backend attribution under two interleaved users, through real
      LiteLLM callbacks (`mock_response`), with the untagged call
      ignored;
    - the wait for in-flight callbacks;
    - embedding attribution.
  - Cerebrum `tests/agents/test_cost_instrumentation.py`:
    - the price table loads and prices a known usage;
    - the summary columns;
    - `cost_fields`;
    - native trials record every field, with 3 backend calls attributed
      to the trial's user;
    - the `/memory/cost` read.

  `test_mem0_llm_sync.py` now tests the LiteLLM route.

**10-trial check** (Cerebrum `results/cost_check/`, GPT-4o, judge v2;
`scripts/cost_check.py`: 0 problems in either cell). Every trial has
non-zero assistant, writer and embedding tokens. `kernel_shared` made 0
backend LLM calls in every trial (writes use `infer=False`);
`native_mem0` made 3 per trial (profile, task, conversation).
`kernel_overhead_ms + llm_ms` matches `latency_seconds × 1000` within
0.1% in all 20 trials. Means per trial:

| | kernel_shared | native_mem0 |
|---|---:|---:|
| Assistant tokens (in / out) | 866 (322 / 544) | 724 (314 / 410) |
| Writer tokens (2 calls) | 495 | 488 |
| Backend LLM tokens (calls) | 0 (0) | 24,271 (3) |
| Embedding tokens (calls) | 912 (6) | 1,102 (16.3) |
| Total tokens | 2,273 | 26,586 |
| Estimated USD (backend share) | 0.0090 (0%) | 0.0735 (90%) |
| Latency, ms | 6,944 | 5,045 |
| = memory stages + scheduler wait + `llm_ms` | 40 + 975 + 5,925 | 14 + 501 + 4,526 |
| Scores (profile / task / integration) | 4.5 / 5.0 / 4.5 | 4.6 / 5.0 / 4.6 |
| `tokens_per_quality` | 487 | 5,617 |

At similar scores on 10 trials, native Mem0 spends about 11× the tokens
and 8× the money per trial; Mem0's extraction prompt (about 7,900
prompt tokens per call) is 90% of the cost. Embeddings are local, so
they cost nothing in money, only time. The kernel's memory stages are
under 1% of latency; the scheduler's wait is most of the kernel's
overhead. In `native_mem0` that wait is shorter and varies (111-1,063
ms), because the writers' Mem0 calls run outside the kernel, so the
assistant's request arrives at a random point in the scheduler's 1 s
cycle.

### Subtask 8

- Spec first: `docs/REPLICATED_LOGIC.md` (committed `99d9c70`, before
  any agent code): the condition, its three inherent differences (no
  shared write barrier, no shared identity resolution, no single policy
  instance), the non-logic differences, and the predicted tie.
- **Library** `aios/memory/pipeline/`, depending only on the provider
  contract and the `memory:` settings:
  - `IdentityResolver` (`identity.py`);
  - `WriteBarrier` (`barrier.py`, moved from `write_barrier.py`);
  - `Visibility` (`visibility.py`, moved);
  - `Selector` (`selector.py`, the former `retrieve_for_agent` body);
  - `Formatter` (`formatter.py`; `memory_formatter.py` moved);
  - `PipelineSettings`;
  - the `MemoryPipeline` facade (`write`, `update`, `retrieve`,
    `build_block`, `inject`).

  The old module paths are shims. `PIPELINE_VERSION` is the first 16 hex
  digits of a sha256 over `pipeline/*.py`. Whether a backend commits
  synchronously is now the provider attribute `synchronous_commit` (True
  for in-house and Zep), not an isinstance check in the manager.
- **Kernel as a thin client.** `MemoryManager.memory_pipeline()` builds
  a `MemoryPipeline` over the kernel's provider, its one shared barrier
  and its registry (`_KernelIdentity`). The add, update and retrieve
  branches and `ContextInjector.inject` call it; the log lines are
  unchanged. `/memory/config` also reports `pipeline` (the settings) and
  `pipeline_version`.
- **Decision 1 resolved (closes open decision 1).** Rank by score for
  threshold, cap and budget, then print in type order: profile, task
  context, conversation, other. `kernel_shared` is re-run under it below.
- **Replicated agents.** Cerebrum
  `cerebrum/example/agents/replicated/`, conditions `replicated_mem0` and
  `replicated_inhouse` (`conditions.REPLICATED_CONDITIONS`):
  - Each agent builds its own provider client and `MemoryPipeline`, with
    its own barrier and resolver, from `/memory/config`.
  - The writers upsert as the kernel writers' SDK calls do.
  - The assistant injects the library's block and writes the
    conversation turn itself.
  - Kernel memory must be off; the Subtask 6 pre-flight enforces it.
  - Every `TrialResult` records `locus` (`kernel`, `replicated`,
    `native`, `none`) and `pipeline_version`.
  - `library.load()` puts AIOS on `sys.path` (`AIOS_ROOT`, default the
    sibling checkout).
- **Tests.**
  - AIOS `tests/modules/memory/test_pipeline_library.py`:
    - injector ≡ library for 20 seeded users (byte-identical prompts,
      identical diagnostics without timings);
    - SDK search ≡ library over agents × sharing policies;
    - kernel writes ≡ library writes;
    - type order after ranking, and the budget dropping the
      lowest-ranked memory;
    - the library imports and runs in a fresh interpreter without the
      manager, syscalls, config, scheduler or server.
  - Cerebrum `tests/agents/test_replicated_agents.py` runs
    `_replicated_checks.py` in a fresh interpreter (see known issue 18):
    - zero kernel memory calls in both conditions;
    - writers update on a second trial;
    - separate pipeline, barrier and resolver per agent, and no shared
      registry (difference 2);
    - the difference-1 demonstration: with local barriers a read during
      another agent's accepted write misses it; with one shared barrier
      it waits (≈0.3 s) and sees it.

    The same file also tests the pre-flight and `locus`.
- Drivers: `scripts/run_locus_smoke.sh` (it restores `config.yaml` on
  exit) and `scripts/set_memory_mode.py` (byte-preserving
  provider / kernel-memory switch). Analysis:
  `python -m benchmarks.shared_memory.locus_compare <dir> --csv ...`.

**30-trial smoke** (Cerebrum `results/locus_smoke/`, judge v2).
390 trials, 0 failed:

- 0 memory operations in every replicated kernel log;
- `locus` correct and `pipeline_version` `72185008bbe22f83` on every
  trial, kernel and replicated;
- profile first in every block;
- 6 embedding calls per trial in every cell.

Means (profile / task / integration), replicated − kernel and the
pre-registered cell rule (`locus_compare.py`, `summary.csv`):

| Backend | Model | kernel_shared | replicated | Diff | Rule |
|---|---|---|---|---|---|
| Mem0 | GPT-4o | 4.77 / 5.00 / 4.73 | 4.63 / 4.97 / 4.60 | −0.13 / −0.03 / −0.13 | pass |
| Mem0 | Llama-3.1:8B | 3.93 / 4.53 / 3.87 | 3.73 / 4.60 / 3.53 | −0.20 / +0.07 / −0.33 | integration fails |
| Mem0 | Qwen-2.5:7B | 3.77 / 4.70 / 3.63 | 3.43 / 4.83 / 3.37 | −0.33 / +0.13 / −0.27 | pass |
| In-house | GPT-4o | 4.73 / 5.00 / 4.57 | 4.77 / 5.00 / 4.73 | +0.03 / 0.00 / +0.17 | pass |
| In-house | Llama-3.1:8B | 3.50 / 4.37 / 3.40 | 3.97 / 4.60 / 3.93 | **+0.47** / +0.23 / **+0.53** | profile, integration fail |
| In-house | Qwen-2.5:7B | 3.63 / 4.90 / 3.53 | 3.53 / 4.67 / 3.47 | −0.10 / −0.23 / −0.07 | task fails |

16 of 18 judge cells are within 0.25 (the two flagged ones are below).
The mean replicated − kernel difference over all 18 is −0.01 (Mem0
−0.14, in-house +0.12). Latency is the same within model noise. The
memory stages take 35-67 ms in every cell, and the scheduler wait
710-980 ms.

`kernel_shared` under the type-ordered block, against the v2 baseline
(Subtask 6 brackets, storage order):

- within 0.16 on every score, except Llama;
- Llama: Mem0 +0.16 / +0.07 / +0.30, in-house −0.27 / −0.09 / −0.17.

The Llama shifts go in opposite directions on the two backends, so they
are not an effect of the block order.

**The two flagged cells (in-house Llama, replicated above kernel by
+0.47 profile, +0.53 integration).** Investigated as the design
requires. No logic difference was found:

- The code is the same. Kernel and replicated ran the same
  `pipeline_version`, and the equivalence test proves kernel ≡ library
  byte for byte.
- The blocks look the same. They were rebuilt from both stores with the
  library (`repo-artifacts/Cerebrum/locus_smoke/rebuild_blocks.py`).
  Every trial on both sides injected exactly profile + task context, in
  that order, of 137-172 tokens. The mix of clean and nested writer
  JSON is the same on both sides.
- User ids are unique per run, so there were no stale rows.
- The cells are unpaired: users are generated per trial, so the two
  cells score different users (known issue 20).
- The low kernel trials injected both memories. Llama used the name
  and ignored the preferences.
- A re-draw of the kernel cell (`kernel_inhouse_redraw/`) gave 3.57 /
  3.83 / 2.93. Its task and integration drop is upstream of memory:
  in 10 of its 30 trials the Llama TaskAgent's extraction returned no
  task fields (e.g. `status: success. message: Task context extracted
  successfully.`), against 1 of 30 in the first draw and 2 of 30 in
  replicated (known issue 21). Without those trials its task score is
  4.75.
- The direction is not consistent across backends. On Mem0 the same
  model goes the other way (−0.20 / −0.33). Pooled over both backends,
  the Llama locus difference is +0.13 / +0.15 / +0.10 (Welch p 0.37 /
  0.29 / 0.53), under 0.25.

**Not explained.** The profile gap on in-house Llama holds across both
kernel draws: 3.50 and 3.57 against 3.97, Welch p = 0.012 against the
pooled 60 kernel trials. That is one of 18 cells chosen after the fact
(Bonferroni p ≈ 0.2). I found no mechanism that differs between the
two paths. A paired run on fixed users would settle it; this branch
has no fixed dataset (known issue 20). Until then the clean condition
is read as a tie with one unexplained small-model cell, and the
difference-1 demonstration test shows where the two loci actually
differ.

### Subtask 9

Goal: every cell of the locus × backend grid scores the same users with
the same stored content on a given backend, and no writer failure is
stored silently, so a difference between two cells can only come from
locus, backend or model.

- **Fixed dataset.** Cerebrum `benchmarks/shared_memory/data/users_v1.jsonl`:
  150 users (profile, task context, plausible actions, follow-up query)
  generated once with `synth.py`'s prompts and GPT-4o
  (`gpt-4o-2024-11-20`), seed 20261104, on 2026-11-04. The first record
  is the header (seed, model, date, a hash of the generator's source,
  LiteLLM version, seed rule). `dataset.py generate` calls LiteLLM
  directly, because the kernel's chat API carries no seed; a duplicate
  name or a query naming a profile or task literal is regenerated with
  the next seed (17 profiles needed a second attempt, 3 a third; no
  query still named a literal). 150 distinct names. `pilot_v1` is the first 30
  users. `run_evaluation.py --dataset users_v1|pilot_v1|<file>` scores
  user `i` as trial `i`, so every cell is paired by construction;
  `--dataset random` keeps per-trial generation and is never used for
  reported results. `--trials` defaults to the dataset's size. Every
  trial records `dataset` and `input_sha256` (a hash of the two writers'
  inputs and the query), every results file the dataset's name, sha256,
  seed, model and date.
- **Paired analysis.** `benchmarks/shared_memory/compare.py`: per-user
  differences between two cells of the same dataset, with mean, 95% t
  CI, paired t, Wilcoxon signed-rank (zeros dropped; `n_nonzero`
  reported) and paired TOST against ±0.25. A user failed in either cell
  is dropped and counted by reason; cells of different datasets, or a
  user whose `input_sha256` differs, are an error.
  `pilot_report.py` builds the table below from `results/pilot_v1`.
- **One stored content across loci.** The native renderer is now the
  single shared one (`shared_memory_utils.render`; `native/render.py`
  is removed). Kernel, replicated and native writers all store the same
  plain-language text, and keep the validated fields as JSON in
  `metadata["structured"]`. The kernel's formatter passes plain text
  through unchanged, so the kernel block now shows the writers'
  first-person sentences ("My name is ...") instead of the formatter's
  "User profile: ..." rendering of JSON.
- **Mem0 extraction in the kernel (`memory.mem0.infer: true`).** The
  kernel's Mem0 now writes with `infer=True` and its internal LLM pinned
  to `memory.backend_llm` (Azure gpt-4o through LiteLLM, temperature
  0.1; `cerebrum.utils.usage.mem0_llm_config`, shared with the native
  agents), passing the writer as `agent_id` and a conversation turn as
  two role-tagged messages, as the native agents do. The assistant model
  no longer replaces that LLM. The replicated Mem0 agents follow the
  kernel's setting (`/memory/config` `backend_extraction`). Before
  switching, verified that Mem0 2.0.0 copies the full metadata dict to
  every extracted fact (`deepcopy(metadata)` per record): a test against
  a real Mem0 + Chroma store (`tests/modules/memory/test_mem0_infer.py`)
  and a 5-user live check (`scripts/check_fact_metadata.py`) on the
  kernel, replicated and native Mem0 stores: every one of 56 / 49 / 55
  fact rows had `owner_agent`, `user_id`, `memory_type`,
  `sharing_policy` and `structured`; 3-4 profile facts and 3-4 task
  facts per user. In-house has no extraction; nothing changes there.
  Every trial records `backend_extraction` (true on every Mem0 cell,
  false on in-house, none for the two memory-less baselines).
- **Writer validation (closes known issue 21).** Writers validate their
  extraction against the profile / task schema (aliases and one nested
  object accepted, `blockers` may be empty, every other field required
  and non-empty; `shared_memory_utils.validate_extraction`), retry up
  to two times, and on final failure store nothing: the trial records
  `writer_failed` (e.g. `["task_agent"]`), is marked failed and is not
  run past the writers or judged. Every trial records `writer_retries`
  per writer; `writer_tokens` counts every attempt.
- **Models.** `docs/MODELS.md`: GPT-4o, Qwen-2.5:7B and Llama-3.1:8B
  (the workshop's, kept for comparability), with Ollama digests; the
  stress-sweep pair is GPT-4o and Qwen-2.5:7B.
- **Driver.** AIOS `scripts/run_pilot_baseline.sh`: phase `kmem0`
  (Mem0, kernel memory on), `kinh` (in-house), `agent` (kernel memory
  off: replicated, native, and the two baselines, which with kernel
  memory on would have their chat turn stored and extracted by the
  kernel); one fresh kernel per phase and model, `config.yaml` restored
  at exit, resumable (`scripts/pilot_cell_done.py`: only writer failures
  may be failed).
- **Tests.** Cerebrum `test_writer_parity.py` (validation, retries, the
  same text and fields from all three loci, failures stored nowhere,
  writer tokens per attempt, the failed trial not judged),
  `test_dataset_paired.py` (the committed dataset, pilot_v1, two runs of
  a cell see identical users and inputs, paired statistics, exclusions),
  `_replicated_checks.py` (replicated Mem0 follows the kernel's
  extraction and counts its LiteLLM calls). AIOS `test_mem0_infer.py`.

**pilot_v1 re-baseline** (`Cerebrum/results/pilot_v1/`, PROVENANCE
there): 10 cells × 3 models × 30 users, 900 trials, judge v2. 3 trials
failed, all Llama writer failures after two retries (Mem0
`kernel_shared`, in-house `kernel_shared`, in-house native; one each),
stored nothing and were not judged. Llama retried a writer in 5-11
trials per cell, GPT-4o and Qwen in none. **Superseded by Subtask 9d**,
which re-runs it under fixed decoding and the shared block renderer;
use the Subtask 9d table (greedy judge), not this one.

Paired, other − `kernel_shared` on the same users, 95% t CI (bold: CI
excludes 0):

| Model | Backend | Other | n | Profile | Task | Integration |
|---|---|---|---|---|---|---|
| GPT-4o | Mem0 | replicated | 30 | +0.17 [−0.05, +0.39] | +0.00 [−0.10, +0.10] | +0.13 [−0.10, +0.37] |
| GPT-4o | Mem0 | native | 30 | +0.17 [−0.11, +0.45] | −0.03 [−0.10, +0.03] | +0.17 [−0.11, +0.45] |
| GPT-4o | in-house | replicated | 30 | +0.03 [−0.22, +0.28] | +0.00 | +0.17 [−0.08, +0.41] |
| GPT-4o | in-house | native | 30 | +0.17 [−0.03, +0.36] | +0.00 | +0.20 [−0.01, +0.41] |
| Qwen | Mem0 | replicated | 30 | +0.27 [−0.19, +0.73] | −0.17 [−0.34, +0.01] | +0.20 [−0.21, +0.61] |
| Qwen | Mem0 | native | 30 | **+0.63 [+0.18, +1.09]** | −0.03 [−0.15, +0.09] | **+0.53 [+0.13, +0.93]** |
| Qwen | in-house | replicated | 30 | +0.23 [−0.32, +0.79] | +0.03 [−0.12, +0.19] | +0.27 [−0.26, +0.79] |
| Qwen | in-house | native | 30 | +0.43 [−0.12, +0.99] | +0.07 [−0.07, +0.20] | +0.47 [−0.04, +0.97] |
| Llama | Mem0 | replicated | 29 | −0.10 [−0.54, +0.33] | −0.10 [−0.26, +0.05] | −0.14 [−0.50, +0.22] |
| Llama | Mem0 | native | 29 | +0.28 [−0.06, +0.61] | −0.10 [−0.32, +0.11] | +0.24 [−0.09, +0.57] |
| Llama | in-house | replicated | 29 | +0.03 [−0.43, +0.49] | +0.03 [−0.13, +0.19] | +0.14 [−0.28, +0.55] |
| Llama | in-house | native | 28 | +0.14 [−0.38, +0.67] | +0.00 [−0.18, +0.18] | +0.32 [−0.19, +0.83] |

Task usage is within ±0.25 everywhere. The Subtask 8 in-house Llama gap
(+0.47 profile, unpaired) is +0.03 paired (closes known issue 20).
`kernel_private` scores 1.07-1.20 on profile in every cell, as designed.
Cost per trial: Mem0 cells 0.062-0.073 USD (almost all Mem0's GPT-4o
extraction, ~24,000 tokens), in-house GPT-4o ~0.007 USD, local models
0 USD in API calls. Per-cell means, tokens, latency and cost:
`results/pilot_v1/cells.csv`; the paired table with p-values and TOST:
`paired.csv` (`pilot_report.py`).

### Subtask 9c (investigation, no code change)

Why Qwen/Mem0 native beat `kernel_shared` by +0.63 profile. Scripts and
outputs in `repo-artifacts/Cerebrum/s9c/`.

- The kernel injects every fact it stored (≤ 8, so the cap of 10 never
  binds), as native does; on all 60 Qwen and GPT-4o users both blocks
  hold the name, language, style and every tool. No pipeline stage
  drops a fact: dedupe removes only the shared fetch's copy of each own
  row; threshold, cap and budget keep n.
- Extraction: fact counts per user differ (25/30) but not on average
  (Qwen 7.23 vs 7.30, GPT-4o 7.2 vs 7.0); the extraction prompts and
  LLM settings are byte-identical, so it is GPT-4o sampling. The same
  locus re-run gives the same profile fact set in only 11-17 of 30 users.
- The kernel block costs more prompt tokens (Qwen 437 vs 314): header,
  instruction line, footer and a 12-digit timestamp per line. It always
  puts profile first; native's Mem0 order does in 7-9 of 30 users.
- The judge never sees the block; its reasoning cites the kernel-side
  answers omitting tools and language.
- 2×2 ablation on Qwen (format × facts+order, 2 answers per user):
  kernel 3.60 / native 3.87 profile; neither factor alone moves it
  (+0.03, +0.00); total +0.27 [−0.05, +0.58], integration +0.30
  [+0.04, +0.56].

Verdict: not fewer facts (a), not the judge (c); mostly answer noise
(temperature 1.0, one answer per user), with a residual ~0.3 that needs
the whole native block (b). Fix: Subtask 9d.

### Subtask 9d

- **Shared block renderer.** `aios/memory/pipeline/formatter.py`
  `format_block` renders the block for the kernel and the replicated
  agents: `compact` (default) is the line "Known about this user:" and
  one bullet per memory, with no delimiters, instruction line or
  per-line timestamp (timestamps stay in metadata). `legacy` is the
  pre-9d kernel block, kept for the Subtask 19 ablation. Optional
  `block_recency` appends a relative age ("(2 hours ago)"), off by
  default. Config `memory.block_format` / `memory.block_recency`,
  validated at startup, reported in `/memory/config` `pipeline`, copied
  by the replicated agents and recorded per trial in
  `injection_diagnostics` (`native` on native trials, which keep their
  own renderer). `is_memory_block` / `block_contents` parse both
  formats.
- **Fixed decoding.** Temperature 0.0 and seed 20261105 on every
  assistant and writer call in every condition. `/query` drops
  `LLMQuery.temperature`, so the harness puts both on each `llms` entry
  (`with_decoding`); the adapter applies them (`decoding_for`), LiteLLM
  forwards the seed to Ollama and Azure, and the reply envelope carries
  `decoding`. Recorded in `ExperimentMetadata.decoding` and per trial.
  `--temperature`, `--seed none`, `--sampled` override it.
- **Determinism, 5 users, two runs each:** Qwen gave byte-identical
  answers on 5/5. GPT-4o got identical prompts, but its answers
  differed on every user (similarity 0.22-0.69): Azure treats the seed
  as best effort.
- **Writer retries sample** (follow-up). With greedy decoding a retry
  would repeat the failed first attempt. Attempt 0 keeps the run's
  decoding; attempt n uses temperature 0.3 and seed + n
  (`attempt_llms`). Each trial records `writer_attempt_settings`.
- **Greedy judge** (follow-up). The judge runs at temperature 0.0 and
  seed 20261105 (`JUDGE_TEMPERATURE`, `JUDGE_SEED`), recorded as
  `judge_temperature` / `judge_seed`. The prompt is unchanged, so it
  stays judge v2. `rejudge.py` also records the source judge's
  decoding. Every later run uses this judge.
- **mem0ai 2.0.2** pinned in both venvs and both `requirements.txt`
  (closes known issue 17). `tests/environment/test_mem0_pin.py`.
- **Tests.**
  - AIOS: `test_block_renderer.py`, `test_decoding.py` (decoding
    reaches the LiteLLM call and the envelope), `test_mem0_pin.py`.
  - AIOS: `test_pipeline_library.py` is now parametrized over both
    formats: the kernel and the library build byte-identical blocks.
  - Cerebrum: `test_fixed_decoding.py`, `test_retry_and_judge_decoding.py`
    and `_replicated_checks.py` (the replicated block is compact and
    follows the kernel's `legacy` flag).
- **Smoke.** `scripts/retrieval_smoke.py` checks the block format. Its
  verbatim-storage checks are skipped when `backend_extraction` is on.
- **Docs.** `docs/MODELS.md` covers decoding, the writer-failure rule
  and the judge decoding.

**pilot_v1 re-baseline** (`Cerebrum/results/pilot_v1_9d/`, PROVENANCE
there): 10 cells × 3 models × 30 users, fixed decoding, compact block,
run 2026-11-05 17:06 to 2026-11-06 00:41. All 900 trials completed. No
writer failed or retried in any cell; pilot_v1 had 3 Llama failures and
5-11 retried trials per Llama cell. So no Llama cell breaks the
writer-failure rule (more than 6 of 30) and none was re-run.

The Qwen Mem0 `kernel_shared` cell was re-run. I ran the Cerebrum suite
against the live kernel during its first run (known issue 25). The
re-run used run id `p9dr-...` and the same code; the original is in
`repo-artifacts/Cerebrum/pilot_v1_9d_contaminated/`.

The re-judge with the greedy judge (`results/pilot_v1_9d_greedy/`)
covered the same 900 responses: judge calls only, none failed.
Agreement with the run's sampled judge, pooled over the 720
non-`kernel_private` trials:

| Dimension | Sampled mean | Greedy mean | Spearman ρ | Changed > 1 pt | Exact |
|---|---|---|---|---|---|
| Profile | 3.783 | 3.774 | 0.893 | 0.8% | 84.0% |
| Task | 4.789 | 4.786 | 0.974 | 0.0% | 99.2% |
| Integration | 3.761 | 3.754 | 0.929 | 0.3% | 88.8% |

Only one cell mean moved by more than 0.25: Qwen in-house
`kernel_shared` profile, 3.27 → 3.00 (exact agreement 46.7%). Per
cell: `results/pilot_v1_9d_greedy/judge_agreement.csv`.

The greedy judge is not fully repeatable. Re-judging the 90 Mem0
`kernel_shared` trials a second time gave exact agreement of 92.2%
(profile), 100% (task) and 94.4% (integration); sampled vs greedy on
those cells was about 84% on profile. Greedy decoding about halves the
judge noise.

**This table replaces Subtask 9's.** Greedy judge, paired on the same
users, other − `kernel_shared`, 95% t CI. No CI excludes 0.
Equivalence is TOST at ±0.25 with p < 0.05.

| Model | Backend | Other | n | Profile | Task | Integration |
|---|---|---|---|---|---|---|
| GPT-4o | Mem0 | replicated | 30 | +0.00 [−0.20, +0.20] | +0.00 | +0.03 [−0.15, +0.22] |
| GPT-4o | Mem0 | native | 30 | +0.03 [−0.15, +0.22] | +0.00 | +0.00 [−0.17, +0.17] |
| GPT-4o | in-house | replicated | 30 | +0.20 [−0.03, +0.43] | +0.00 | +0.20 [−0.01, +0.41] |
| GPT-4o | in-house | native | 30 | +0.23 [−0.04, +0.51] | +0.00 | +0.13 [−0.12, +0.39] |
| Qwen | Mem0 | replicated | 30 | −0.27 [−0.59, +0.06] | +0.07 [−0.10, +0.23] | −0.10 [−0.40, +0.20] |
| Qwen | Mem0 | native | 30 | −0.10 [−0.54, +0.34] | −0.03 [−0.15, +0.09] | −0.07 [−0.47, +0.34] |
| Qwen | in-house | replicated | 30 | +0.17 [−0.08, +0.41] | +0.00 | +0.13 [−0.03, +0.30] |
| Qwen | in-house | native | 30 | +0.20 [−0.33, +0.73] | −0.07 [−0.16, +0.03] | +0.13 [−0.32, +0.59] |
| Llama | Mem0 | replicated | 30 | +0.13 [−0.06, +0.32] | +0.00 [−0.20, +0.20] | +0.03 [−0.12, +0.19] |
| Llama | Mem0 | native | 30 | −0.03 [−0.30, +0.23] | −0.03 [−0.22, +0.15] | +0.00 [−0.28, +0.28] |
| Llama | in-house | replicated | 30 | +0.00 [−0.14, +0.14] | +0.03 [−0.03, +0.10] | +0.10 [−0.01, +0.21] |
| Llama | in-house | native | 30 | −0.17 [−0.62, +0.28] | +0.03 [−0.12, +0.19] | −0.07 [−0.48, +0.35] |

- **The Qwen Mem0 native gap is gone:** +0.63 [+0.18, +1.09] profile in
  Subtask 9, −0.10 [−0.54, +0.34] now.
- **Equivalent within ±0.25** (TOST):
  - GPT-4o Mem0 replicated and native, on every dimension.
  - Llama Mem0 replicated, task and integration.
  - Llama in-house replicated, every dimension.
- **Not shown equivalent at n = 30:** the in-house and Qwen comparisons
  are inconclusive, with wide CIs.
- **Cell means** (profile / integration):
  - GPT-4o: 4.53-4.77 / 4.57-4.77.
  - Qwen: Mem0 3.53-3.80 / 3.60-3.70; in-house 3.00-3.20 / 3.07-3.20.
  - Llama: 3.87-4.20 / 3.90-4.10.
  - `kernel_private`: 1.00-1.03 / 1.00, as designed.
  - Baselines: naive_concat 2.93-4.67 profile; vanilla_rag 1.90-2.30.
- **Cost per trial** (unchanged from Subtask 9):
  - Mem0 cells: 0.062-0.073 USD.
  - In-house GPT-4o: about 0.007 USD.
  - Local models: 0 USD in API calls.
- **Files:**
  - Per-cell means, tokens, latency and cost:
    `results/pilot_v1_9d_greedy/cells.csv`.
  - Paired table with p-values and TOST: `paired.csv`.
  - The sampled-judge versions are in `results/pilot_v1_9d/`.

### Subtask 10

Spec: `docs/HETEROGENEITY.md`, written before the variant code (AIOS
`3ca7d2c`).

- **Housekeeping**, each its own commit:
  - The live-kernel guard is ported to Cerebrum `tests/conftest.py`
    (Cerebrum `8ed13d5`; closes known issue 25). The 4
    `test_kernel_private_unit.py` tests that passed only because the
    connection failed are now marked `live_kernel`.
  - Mem0's extraction runs at temperature 0.0, seed 20261105, in both
    loci (AIOS `cf7a082`, Cerebrum `2ca7fc7`; issue 26).
  - `chromadb==1.5.9` is pinned in both repos (issue 30).
- **Variants**: `cerebrum/example/agents/variants/`, one module per
  variant. `apply_variant` applies a variant to any agent in any locus
  and restores the agent afterwards. An aspect the locus has no channel
  for is recorded in `variants_not_applied`; for example, the kernel
  ignores a consumer's own retrieval settings.
  - V1: stale version (legacy block, private writes).
  - V2: identity convention (mixed case plus an email domain).
  - V3: missing sharing metadata on writes; a V3 consumer ignores
    visibility.
  - V4: tuned consumer (k 5, threshold 0.5, budget 1500).
  - V5: raw-payload writer (JSON with off-schema keys).
- **Schedule**: `variants/schedule.py`, seeded and identical across
  loci, so cells pair by trial index. CLI flags: `--heterogeneity
  0|1|2`, `--variant-seed` (default 20261106). H > 0 requires
  `--no-judge` and `--method`. Every trial records
  `variants_applied`.
- **Kernel identity canonicalization**: config `memory.identity`
  (`casefold`, `email_domains`). It is applied at syscall acceptance
  (before the barrier) and in `address_request`. The pipeline library
  defaults to no rules, so replicated and native agents resolve ids as
  given.
- **Judge-free measures** on every trial (`benchmarks/shared_memory/
  judge_free.py`): `profile_facts_in_block`, `cross_user_rows`,
  `private_rows_from_others`, `memories_missing`, `raw_payload_rows`.
  They are computed from the block text and per-row provenance
  (`provenance_agent` / `provenance_user`, added by the harness to
  every write and read by no memory logic).
- **Silent backend failure guard** (Cerebrum `04631f6`, AIOS
  `da25e2c`). Mem0 logs and swallows its extraction LLM's errors. From
  a network Azure refused, a native Mem0 cell ran 5 trials with 0
  backend calls and 0 injected rows, and every trial "completed".
  - Every writer now reports `stored_rows`.
  - A trial whose backend extracts fails as `backend_extraction_failed`
    when a successful writer stored no row, or when the backend
    recorded no LLM call.
  - The drivers' `pilot_cell_done.py` then stops instead of moving on.

  This is the project's third silent failure, after the keyword judge
  fallback (4b) and stored writer status payloads (9): real memory
  systems fail quietly, and only a layer that sees every write
  notices. It belongs in the paper's motivation.
- **Functional check**: Qwen, the first 5 `pilot_v1` users, judge off,
  every locus × backend × H = 18 cells, 90 trials. None failed or was
  scored; 0 leaked rows anywhere. Files are in
  `Cerebrum/results/heterogeneity_check/` (`trials.csv`, `table.md`,
  PROVENANCE).

| Variant | Kernel (in-house / Mem0) | Replicated (in-house / Mem0) | Native (in-house / Mem0) | Verdict |
|---|---|---|---|---|
| V1 task writer (H1 t0) | 1 missing / 1 missing | 1 / 1 missing | 1 / 1 missing | as predicted: private writes are missed everywhere |
| V1 consumer (H1 t2) | no change (kernel renders) | legacy block, +31 / +38 tokens | legacy block, +30 / +42 tokens | as predicted |
| V2 task writer (H1 t3) | 0 missing / 0 missing | 1 / 1 missing | 1 / 1 missing | as predicted: only the kernel resolves the alias |
| V2 consumer (H2 t0) | 0 missing / 0 missing | 2 / 2 missing | 2 / 2 missing | as predicted |
| V3 profile writer (H1 t4) | 1 missing / 1 missing | 1 / 1 missing | 1 / 1 missing | as predicted: private default; no leaks |
| V3 consumer (H2 t4) | 0 leaks (not applied) | 0 leaks (not applied: the library enforces) | 0 leaks | no leak opportunity: its writer pair was V2 (schedule) |
| V4 profile writer (H1 t1) | no change | no change / −2 rows | no change / −1 row | Mem0 noise only |
| V4 consumer (H2 t1) | kernel keeps 0.0 / k 10, not applied | threshold 0.5: 0 rows (in-house), 1 row (Mem0) | 0 rows / −2 rows | finding: at 0.5 the in-house block is empty |
| V5 writer (H2 t0, t1) | +1 raw row / 0 raw rows | 0 raw rows | 0 raw rows | finding: see below |
| V5 consumer (H2 t3) | no change | no change | no change | as predicted: its JSON write lands after the read |

- **Design checks.**
  - V2, V3: zero kernel leaks, and missing or leak in another locus in
    12 of 12 trials: PASS.
  - V4: the kernel keeps its own settings, and replicated after_cap
    changes: PASS.
  - V5 raw rows rise: PASS under kernel in-house; FINDING in the other
    five cells.
- **Findings** (recorded, not tuned away):
  - Mem0 extraction re-renders V5's JSON into facts, so no raw row
    reaches the block, in any locus.
  - Outside the kernel, the 5-user schedule places V5 writers only at
    H2, next to a V2 or V4 consumer, and those consumers empty the
    block first. The V5 writer is therefore not isolated outside the
    kernel. The replicated unit check (`_heterogeneity_checks.py`)
    shows it raises raw rows when isolated.
  - A V4 consumer on in-house at threshold 0.5 injects nothing, since
    relevant rows score 0.32-0.60. Native Mem0 is barely affected,
    because its scores saturate near 1.0.
  - Mem0 cells move by ±2 rows with no variant effect: Azure treats
    the seed as best effort.
- **Tests**:
  - AIOS: `test_identity_rules.py` (20), `test_pilot_cell_done.py`.
  - Cerebrum: `test_live_kernel_guard.py` (7), `test_heterogeneity.py`
    (40, including `_heterogeneity_checks.py` in a subprocess),
    `test_extraction_guard.py` (14), and extraction-seed tests in
    `test_fixed_decoding.py`.

### Subtask 11

Pre-registration, design, rule and result: `docs/PILOT.md`. The design
was committed and tagged `pilot-v1-code` (AIOS `ef05d66`, Cerebrum
`7fc5769`) before the first scored trial.

- **Before the pilot**, each its own commit:
  - Known issue 31 fixed (AIOS `d3370f4`): long user ids are hashed
    into the kernel's Mem0 collection names.
  - Balanced variant schedule (`pilot_schedule.py`,
    `data/pilot_v1_schedule.json`, SHA-256 `f4f2c8fe…`). It replaces
    the seeded cycle, which closes issue 34. `--schedule` is required
    for a scored run at H > 0.
  - The driver `scripts/run_pilot_v1.sh` refuses to start unless both
    repos are at the tag with no tracked changes. A cell is done only
    if every trial completed at exactly the tagged commits
    (`pilot_cell_done.py --strict --commit --kernel-commit`).
- **Run** (2026-11-07 17:23 to 2026-11-08 02:45):
  - 36 cells, 1,080 trials, 0 failed, 0 kernel leaks, one commit pair
    and one schedule across all cells.
  - One cell (Qwen `native_mem0` H0) was re-run whole after the Subtask
    10 guard caught an Azure connection drop. Mem0 had stored nothing
    for trial 5. The re-run used a distinct run id (`…-h0-r1`), because
    the native store is shared and never reset. Recorded in the results'
    PROVENANCE; the failed attempt is in `repo-artifacts`.
- **Analysis**: `benchmarks/shared_memory/pilot_analysis.py` (cells,
  paired gaps per backend and pooled, DiD, judge-free rates, H = 1 by
  variant, verdict) and `pilot_figure.py` (SVG gap vs. H). Results are
  in `Cerebrum/results/pilot_v1_hetero/`.
- **Verdict: GO.** Pooled kernel − replicated at H = 2:
  - Qwen: Profile +0.73 [+0.26, +1.20], Integration +0.82 [+0.43, +1.21].
  - GPT-4o: Profile +1.15 [+0.62, +1.68], Integration +1.18 [+0.63, +1.74].

  The H2 − H0 DiDs are +0.75 to +1.15, all with the CI above 0. Kernel
  leak rate is 0. Kernel `memories_missing` at H ≥ 1 is 0.37, against
  replicated's 0.68. H = 0 ties.
- **What drives it**: V2 (identity) and the V4 consumer, the latter by
  construction, since the kernel has no channel for a consumer's
  settings. V1, V3 and V5 add about 0. V5 showed no effect on any gap.
  Native leaks (0.10 at H = 2) only for a V3 consumer paired with a
  private writer.
- **Tests**:
  - AIOS: `test_mem0_collection_names.py` (4), `test_pilot_cell_done.py`.
  - Cerebrum: `test_pilot_schedule.py`, `test_pilot_analysis.py` (7).

### Subtask 14

Subtasks 12 and 13 are not started; 14 comes first.

- **`memories_missing` split** (its own commit). A missing writer is
  *withheld* when every row it stored was private or had no policy (the
  private default): the visibility rule kept it from the consumer, as
  it should. It is *lost* when it stored a shared row and none reached
  the block (another user id, or dropped by the threshold, the dedupe,
  the cap or the budget). `memories_missing == memories_withheld +
  memories_lost`. The split is in `JudgeFreeMeasures`
  (`judge_free.split_missing`). `pilot_analysis.py --missing-split`
  recomputes it for the pilot's files, which predate it:
  `Cerebrum/results/pilot_v1_hetero/missing_split.md`, plus CSVs. The
  pre-registered outputs reproduce byte for byte.
- **The pilot's split**, the share of trials with a missing writer,
  both backends pooled. The figures are identical on both models:

  | Locus | H1 withheld / lost | H2 withheld / lost | H ≥ 1 missing (withheld, lost) |
  |---|---|---|---|
  | kernel | 0.20 / 0.00 | 0.53 / 0.00 | 0.37 (0.37, 0.00) |
  | replicated | 0.20 / 0.30 | 0.53 / 0.43 | 0.68 (0.37, 0.37) |
  | native | 0.20 / 0.25 | 0.43 / 0.42 | 0.60 (0.32, 0.33) |

  A trial can have one withheld and one lost writer, so the two parts
  can sum to more than the missing rate.
- **The kernel's misses, by variant.** Missing writer instances, both
  models and both backends (2 × 2 × the variant's users). Every one is
  withheld; none is lost.

  | Missing writer | H1 | H2 | Withheld | Lost |
  |---|---|---|---|---|
  | V1 profile writer (stale version, private) | 8 | 20 | 28 | 0 |
  | V3 profile writer (no sharing metadata) | 8 | 20 | 28 | 0 |
  | V1 task writer | 4 | 16 | 20 | 0 |
  | V3 task writer | 4 | 16 | 20 | 0 |
  | Any other variant or reference writer | 0 | 0 | 0 | 0 |

  The H2 rows include each writer's pairings with a V1, V2 or V3
  consumer, which change nothing in the kernel. The kernel's whole
  `memories_missing` advantage is therefore in *lost*: 0.00 against
  0.37 (replicated) and 0.33 (native). Its remaining misses are
  writes the writer did not share. Withheld is the same in the kernel
  and replicated (0.37). Native is lower (0.32), because its V3
  consumer leaks the private row instead (users 5, 15 and 25). Outside
  the kernel, rows are lost to the V2 writer and consumer (identity)
  and the V4 consumer (threshold 0.5).

Spec: `docs/BENCHMARK_V2.md`. It was committed before the generator
code (AIOS `a0ebe26`) and revised after a four-lens review. Amendment 1
(a 500-token budget) was committed before the first functional check
(`51bd5f9`). Amendment 2 (revision 2 of the data, and the scorer and
harness records) came after that check and the stopped smoke `s14`,
before its code and the revision-2 check `f14c` (`d0441c2`). The
corrections made after `f14c` end Amendment 2 ("Corrected after the
revision-2 functional check").

- **Known issue 29 fixed** (AIOS `50567bf`, its own commit): the
  adapter passes Ollama `num_ctx` from `llms.context_window` (default
  16384) and records it in the reply's `decoding`. Ollama 0.40.11 had
  cut an 8,354-token prompt to 2,050 tokens, from the end, with no
  error. This is the project's fourth silent failure, after:
  - the keyword judge fallback (4b);
  - stored writer status payloads (9);
  - Mem0 swallowing Azure errors (10).
- **Dataset** `users_v2` revision 2 (Cerebrum `data/users_v2.jsonl`,
  seed 20261108, SHA-256 `35f68c78…`); `pilot_v2` is its first 30
  users.
  - 150 users built on `users_v1`'s base users. Each has 15 to 23
    events (mean 18.4) and 14 to 22 writer rows (mean 17.4).
  - Sessions hold 2, 3 or 4 events, 252 / 330 / 318 times. 12 users
    needed a script redraw.
  - Each writer owns each role for exactly 50 users, and 50 users are
    echo users.
  - Revision 1 (SHA-256 `768a37ac…`, superseded): GPT-4o
    (temperature 0.0, seeded) paraphrased 2,466 utterances, all
    accepted on the first attempt, with 0 fallbacks.
  - Revision 2 (Cerebrum `1eb5ede`) keeps the scripts and 2,287 of
    revision 1's utterances byte for byte. The 126 that failed the new
    meaning checks were paraphrased again, and the 53 of the three
    changed templates (pairing 24, one-on-one 19, conference 10) from a
    first attempt: 179 GPT-4o calls, 0 fallbacks. `synth_v2.py check
    users_v2` reports 0 problems.
  - A read-only review of revision 2 found no ground-truth problem:
    all 150 contradictions conflict, and the recency, privacy,
    deletion and echo facts hold for all 150 users. Its wording
    findings are known issue 41.
- **Kernel and library** (AIOS `828fde0`):
  - Session ages (`memory.block_recency_unit: session`, "(N sessions
    ago)"). The current session is threaded from `LLMQuery.session`
    through `/query`, the executor, the injector and the conversation
    write.
  - Owner-only `MemoryPipeline.list_own` and `delete`, the kernel's
    `list_memory` operation, and `remove_memory` through the library.
    Every new branch returns a failure instead of raising.
  - Injected rows carry their text, `fact_key`, `session` and
    `provenance_event`. Calendar rows print before conversation rows.
  - Amendment 2 (AIOS `554a408`): listings wait for the write barrier;
    a failed own or shared fetch is reported as `retrieval_error`, and
    an injector failure as `injection_error`, where before both looked
    like an empty store; the kernel's conversation rows carry
    `provenance_event` (known issue 40); an unknown memory operation
    gets an explicit failure.
  - `PIPELINE_VERSION` is now `46e28207…` (`521a05c9…` before
    Amendment 2).
  - After the revision-2 check (AIOS `e3cdc52`): the kernel's
    startup print of its memory configuration redacts secrets
    (`aios/utils/redact.py`). It had printed `memory.zep.api_key` in
    full into every kernel log, and repo-artifacts archives those logs.
    Two log lines that could print a key (the `/core/config/update`
    body and an incomplete `llms.models` entry) are redacted too. The
    logs written before the fix still hold the key: rotate it before
    sharing them.
- **Harness and agents** (Cerebrum `b5c43fe`):
  - New modules: `synth_v2.py`, `probes.py` (the matcher and the
    scorer) and `history.py` (the v2 trial).
  - `run_evaluation.py --dataset users_v2|pilot_v2 [--control]
    [--no-recency]`, with a pre-flight check of the kernel's settings.
  - v2 writers in all three loci: no LLM, one row per event; a revoke
    lists the writer's own rows and deletes by `fact_key`.
  - A `calendar_agent` in each locus, and session-aware consumers.
  - SDK: `list_memories` and `LLMQuery.session`.
  - The driver is AIOS `scripts/run_bench_v2.sh` (`MODE=functional`
    or `smoke`).
  - Amendment 2 (Cerebrum `4fd6bd0`):
    - meaning checks on paraphrases, and `--reuse` checks its source;
    - the `transition_marked` rule, native `cap_bound` against the
      consumer's own k, `semantic_error`, the integration t-interval;
    - a failed retrieval, an errored probe or any exception fails the
      user and keeps what ran; an errored probe is recorded unscored;
    - rows per event come from the listings; backend usage covers every
      user id; replicated writers record the metadata as stored; only
      creates the kernel accepted are recorded as written;
    - `LLMQuery.provenance_event`.
  - After the revision-2 check (Cerebrum `9946612`):
    `visible_stored_rows` (native `cap_bound`) counts the writers' rows
    in the partition the consumer searched, the private ones too when
    it skips visibility; the native consumer reports
    `visibility_checked`.
- **Found by the first functional check** (`f14`, fixed in Cerebrum
  `7d759ec`): V5 replaced a base row with the event's fact-less stub,
  from which Mem0 extracted nothing, so the extraction guard failed
  two H = 2 users. Base events now carry their fields, and V5 writes
  them as JSON, as in v1. The check was re-run whole as `f14b`.
- **`f14b` and the review (Amendment 2).** `f14b`, on revision 1,
  passed all nine conditions, and the smoke started (`s14`). A
  read-only review of the code and data, run meanwhile, found
  contradictions that did not conflict, paraphrases that changed what a
  fact says, a shared fact marked private, and incomplete harness
  records. The smoke was stopped in its first cell. Nothing from it or
  from `f14b` is reported as a result; `f14b` serves only as the
  comparison below. Their files are in `repo-artifacts/Cerebrum/`
  (`bench_v2_smoke/failed_attempts/s14/` and
  `bench_v2_functional/superseded_r1/`).
- **Functional check on revision 2 (`f14c`): passes.** `pilot_v2`
  users 0 to 4, Qwen, no judge. 21 cells and 105 user-trials, 0 failed
  (Cerebrum `results/bench_v2_functional/`, with its provenance). All
  nine pass conditions hold. Passes over users (recency and
  contradiction: lenient in brackets, the new value named, stale or
  not):

  | Locus | Backend | Condition | Deletion, no echo | Deletion, echo | Privacy | Recall | Recency | Contradiction |
  |---|---|---|---|---|---|---|---|---|
  | kernel | mem0 | H = 0 | 3/3 | 1/2 | 5/5 | 5/5 | 2/5 (5/5) | 2/5 (2/5) |
  | kernel | mem0 | H = 2 | 3/3 | 1/2 | 5/5 | 5/5 | 2/5 (3/5) | 2/5 (2/5) |
  | kernel | mem0 | no_delete | 0/3 | 0/2 | 5/5 | 5/5 | 1/5 (5/5) | 2/5 (2/5) |
  | kernel | inhouse | H = 0 | 3/3 | 0/2 | 5/5 | 5/5 | 2/5 (5/5) | 4/5 (4/5) |
  | kernel | inhouse | H = 2 | 3/3 | 1/2 | 5/5 | 5/5 | 4/5 (4/5) | 3/5 (3/5) |
  | kernel | inhouse | no_memory | 3/3 | 2/2 | 5/5 | 0/5 | 0/5 (0/5) | 0/5 (0/5) |
  | kernel | inhouse | no_delete | 0/3 | 0/2 | 5/5 | 5/5 | 1/5 (5/5) | 3/5 (4/5) |
  | replicated | mem0 | H = 0 | 3/3 | 1/2 | 5/5 | 5/5 | 2/5 (5/5) | 2/5 (4/5) |
  | replicated | mem0 | H = 2 | 3/3 | 1/2 | 5/5 | 4/5 | 1/5 (3/5) | 1/5 (1/5) |
  | replicated | mem0 | no_delete | 0/3 | 0/2 | 5/5 | 5/5 | 1/5 (5/5) | 2/5 (3/5) |
  | replicated | inhouse | H = 0 | 3/3 | 0/2 | 5/5 | 5/5 | 2/5 (5/5) | 4/5 (4/5) |
  | replicated | inhouse | H = 2 | 3/3 | 1/2 | 5/5 | 4/5 | 2/5 (3/5) | 1/5 (2/5) |
  | replicated | inhouse | no_delete | 0/3 | 0/2 | 5/5 | 5/5 | 1/5 (5/5) | 3/5 (4/5) |
  | native | mem0 | H = 0 | 3/3 | 1/2 | 5/5 | 0/5 | 0/5 (0/5) | 0/5 (1/5) |
  | native | mem0 | H = 2 | 3/3 | 2/2 | 5/5 | 0/5 | 0/5 (0/5) | 1/5 (1/5) |
  | native | mem0 | no_delete | 3/3 | 2/2 | 5/5 | 0/5 | 0/5 (1/5) | 0/5 (0/5) |
  | native | mem0 | no_visibility | 3/3 | 2/2 | 4/5 | 1/5 | 0/5 (0/5) | 1/5 (1/5) |
  | native | inhouse | H = 0 | 3/3 | 1/2 | 5/5 | 5/5 | 2/5 (5/5) | 2/5 (3/5) |
  | native | inhouse | H = 2 | 3/3 | 1/2 | 4/5 | 4/5 | 2/5 (3/5) | 1/5 (1/5) |
  | native | inhouse | no_delete | 0/3 | 0/2 | 5/5 | 5/5 | 3/5 (4/5) | 2/5 (2/5) |
  | native | inhouse | no_visibility | 3/3 | 1/2 | 0/5 | 5/5 | 3/5 (5/5) | 3/5 (3/5) |

  The full matrix (Wilson intervals, where the forbidden value
  appeared, cap and budget counts) is in that directory's
  `analysis.md`. With n = 5 per cell (known issue 37), the per-cell
  rates are not comparisons.
  - **Privacy.** The kernel never failed (0 of 35 probes, block or
    answer), and no kernel or replicated block of any probe held a
    private value. The one failure in a real condition is the one the
    spec predicted: native in-house, H = 2, user 4, whose V3 consumer
    ignores visibility. `calendar_agent`'s private row reached the
    block, and Qwen named the lawyer. Under `no_visibility`, the
    private value reached the probe's block for 5 of 5 native in-house
    users and 1 of 5 native Mem0 users. Exposure is wider than the
    probe shows (known issue 43).
  - **Deletion.** No deleted row came back in any cell.
    - Every deletion failure outside `no_delete` is an echo user (14 of
      14). In 13 the value came back through the echo row in another
      writer's rows (known issue 38). In one (native Mem0, H = 0, user
      0) no row in the block carried it (the surviving echo row was not
      among the 10 fetched): Qwen listed Mattermost among popular chat
      apps, and a guess fails the probe. Echo-user passes hide the echo
      row too: 7 of the 11 had it in a later probe's block (known issue
      43).
    - Non-echo users pass in every in-house cell at H = 0 and H = 2 (18
      of 18).
    - Under `no_delete`, every kernel, replicated and native in-house
      user fails through the undeleted target row. Native Mem0's
      deletion probe passes 5 of 5, though later probes showed the
      value (known issue 43).
  - **Native Mem0 shows little.** At H = 0 recall, recency and
    contradiction pass 0 of 5 each, and at H = 2 recall passes 0 of 5.
    At both levels every recall and recency failure (20 of 20) had the
    value missing from the block. Its search keeps Mem0's own score,
    clamped at 1.0 (known and kept, `docs/NATIVE_USAGE.md`): the fetch
    holds the nearest rows at cosine 0.5 or below, and the relevant
    rows, above 0.5, are cut. Of its 1,030 injected rows, 1,024 scored
    exactly 1.0. So its deletion and privacy passes are not evidence of
    anything.
  - **Recency fails mostly by naming both values**, as the spec
    expected. Outside native Mem0, at H = 0 and H = 2:
    - 21 of 50 pass strictly, and 41 of 50 name the new value;
    - 20 answers name both values, and 15 of those name the stale one
      as past (`named_as_past` is approximate: 45 of the check's 48
      such verdicts matched a plain reading);
    - some answers reverse the two ("we currently use the `tern-02`
      staging server ... previously relocated to `bittern-06`").
  - **Contradiction fails differently.** Outside native Mem0, 22 of 50
    pass and 26 of 50 name the new value. Only 4 name both: 13 failing
    answers keep the stale value alone, and 11 name neither. The
    manager slot favors the stale value (known issue 44).
  - **Kernel against replicated, H = 0.**
    - In-house: the blocks are identical in 30 of 30 probes, with no
      discordant pair.
    - Mem0: the blocks differ in all 30 probes, and the pass results
      differ only on recency, with 2 discordant pairs, one each way
      (p = 1.00). Mem0's extraction varies between runs (known issue
      42).
  - **Cap and budget**, over H = 0 and H = 2:
    - The cap bound in 54 of 60 probes for kernel in-house, 54 for
      kernel Mem0, and 42 for each replicated cell.
    - The budget bound in 44 in-house probes and never in Mem0, whose
      blocks reach at most 455 estimated tokens, as Amendment 1
      expected.
  - **Contamination.** In 12 of 525 probes, a value reached the block
    only through the consumer's own earlier conversation rows: 6
    in-house contradiction probes (users 1 and 2, the same 3 in the
    kernel and replicated) and 6 native Mem0 probes. None is a
    deletion or privacy probe.
  - **Mem0 facts per write.** Every one-value utterance became one Mem0
    row in all three Mem0 loci (800 of 800); a base event became 1 to
    4 rows. Of the update rows that reached a block, 15 of 45 carried
    the old value (kernel 5 of 14, replicated 4 of 13, native 6 of 18),
    against the spec's "usually"; native Mem0's never reached a
    recency probe's block.
  - **Recall failures.** Of the 13 in real conditions, 4 are H = 2
    user 0's V2 consumer, in all four agent-managed cells: its
    partition holds no writer row (the kernel resolves the id and
    passes). The other 9 are native Mem0's. In each, the target was
    stored and visible but outside the consumer's fetch (10 rows; 5 for
    H = 2 user 1's V4 consumer), which the clamped score fills with rows
    at cosine 0.5 or below; the same target texts score 0.55 to 0.83 in
    the other Mem0 cells. The cap bound in 8 of the 9; in H = 2 user
    2's, 9 of the 10 fetched rows were rows it could not see. So, as the
    spec expected, recall fails mostly when the cap drops the target (8
    of 13), and most for native Mem0. Outside native Mem0 the cap cost
    no recall: every other H = 0 cell passes 5 of 5 while the cap
    binds.
  - **Against revision 1** (`f14b`): of the 525 scored probes, 39
    changed pass, lenient pass, or whether the forbidden value reached
    the block or the answer; 26 of them changed pass or fail (17 to
    fail, 9 to pass). The 11 in-house changes (8 in pass or fail) all
    come from revised utterances, the 28 Mem0 changes (18 in pass or
    fail) from Mem0's extraction, which differed between the runs (6 of
    them also involve a revised utterance); none comes from the code.
    Where a block was identical (169 of all 630 probes), Qwen gave the
    same answer in 168. The revision did not raise contradiction scores
    (strict 23 to 22 of 50).
- **Verification of the `f14c` records.** A read-only review in five
  parts (hard constraints, the other probes, the records, kernel
  against replicated and native, revision 1 against 2), with an
  adversarial check of each defect, recomputed the records with its
  own code:
  - 0 mismatches: the block and answer checks of all 210 deletion and
    privacy probes, the scores of all 315 recall, recency and
    contradiction probes, the bounds, the session ages, and the
    Amendment 2 fields (`retrieval_error` and `injection_error` on
    every probe, all None; `provenance_event` on 382 of 382 kernel
    conversation rows).
  - One defect, confirmed: `visible_stored_rows` counted the writers'
    shared rows under the base id for every native consumer. In
    `f14c` it is wrong in 14 trials (84 probes): too high for the V2
    consumer (H = 2, user 0), and one low for the V3 consumer (H = 2,
    user 4) and every `no_visibility` trial. Fixed (above).
    Recomputed, it changes 0 of the 240 native `cap_bound` values, and
    a reference consumer counts as before, so the smoke is unaffected.
  - The Zep key in the kernel log (fixed above).
  - The rest were descriptions, now corrected: the spec ("Corrected
    after the revision-2 functional check"), `NATIVE_USAGE.md`,
    `PROVIDER_CONTRACT.md`, two docstrings in `providers/mem0.py`, the
    `MemoryCounts` docstring and a `config.yaml.example` comment. The
    local `config.yaml`'s `mem0.mode` comment belongs to the other
    branch and is left. A second read-only review, of these fixes and
    this text, confirmed errors in the text only, now corrected, and
    minor gaps in the code, also fixed: two more log lines, a list or
    mapping under a secret-named key, and a test that now checks the
    consumer's own rows.
- **Analysis changes after `f14b`** (Cerebrum `65cdc52`,
  `bench_v2_analysis.py`, with tests that fail without them). No score
  changed.
  - The cap criterion had treated each condition as its own cell, so it
    also checked `no_memory`, whose store is empty by design. The spec's
    cells are locus × backend, over H = 0 and H = 2, and the criterion
    now follows it.
  - The matrix gained `contaminated` and `named_as_past`.
- **Smoke (`s14b`): complete.** `pilot_v2`, 30 users, Qwen, H = 0,
  the six cells, judge v2 (gpt-5.4) on the integration probe. 180
  user-trials, 0 failed (Cerebrum `results/bench_v2_smoke/`, with its
  provenance). It ran 2026-11-09 08:31 to 12:51 UTC, so every Mem0
  phase saw one date (known issue 42). Passes over users (recency and
  contradiction: lenient in brackets, the new value named, stale or
  not):

  | Locus | Backend | Deletion, no echo | Deletion, echo | Privacy | Recall | Recency | Contradiction | Integration, mean [95% CI] | Share ≥ 4 |
  |---|---|---|---|---|---|---|---|---|---|
  | kernel | mem0 | 18/20 | 4/10 | 30/30 | 29/30 | 9/30 (29/30) | 15/30 (21/30) | 3.33 [2.98, 3.69] | 0.63 |
  | kernel | inhouse | 20/20 | 1/10 | 30/30 | 30/30 | 8/30 (30/30) | 14/30 (17/30) | 1.77 [1.48, 2.06] | 0.07 |
  | replicated | mem0 | 18/20 | 4/10 | 30/30 | 30/30 | 9/30 (28/30) | 14/30 (22/30) | 3.13 [2.76, 3.51] | 0.53 |
  | replicated | inhouse | 20/20 | 1/10 | 30/30 | 30/30 | 8/30 (30/30) | 14/30 (17/30) | 1.80 [1.50, 2.10] | 0.07 |
  | native | mem0 | 20/20 | 8/10 | 30/30 | 5/30 | 0/30 (2/30) | 1/30 (2/30) | 2.93 [2.59, 3.27] | 0.37 |
  | native | inhouse | 20/20 | 2/10 | 30/30 | 30/30 | 13/30 (30/30) | 11/30 (14/30) | 2.90 [2.50, 3.30] | 0.43 |

  The full matrix (Wilson intervals, cap and budget counts), the
  integration means, kernel against replicated paired over users on the
  judge-free probes, and the per-cell readings (exposure, carriers, what
  the store kept, where the expected value was, contradiction per slot,
  earlier answers with a stale value, the integration block and its
  score by base rows) are in that directory's `analysis.md`. Not there:
  the users, quotes and rows named below; the wording groups (their
  pass counts are sums of its slot rows), and the earlier-answer split
  by wording and within users, with its odds ratios other than the
  pooled 0.29; the block-order and rank counts; the store reproduction;
  when the rows that kept a revoked value were written, and which
  selection stage left a stored row out; the integration comparisons
  paired over users (kernel and replicated against native Mem0, native
  Mem0 against native in-house);
  the base task rows per Mem0 block and the scores by their number;
  native Mem0's recall by session, its recency answers that name
  neither value and how often its later answers named the deleted
  value; and that the in-house answers are identical, with the one the
  judge scored differently. A smoke, not a verdict: n = 30 per cell
  (known issue 37).
  - **Privacy.** 180 of 180 probes pass, and no private value reached
    any block or answer of any probe, in any cell. The kernel's privacy
    probe never failed.
  - **Deletion.** No deleted row came back.
    - In-house, every failure is an echo user's, through the echo row:
      9 of 10 echo users in kernel and replicated, 8 in native.
      Non-echo users pass 20 of 20 in every in-house cell.
    - In Mem0, a fold carries 3 failures in kernel and in replicated
      Mem0 (users 13, 19 and 25) and 1 in native Mem0 (user 13): the
      same writer's next row took the value, and a revoke by `fact_key`
      leaves it (known issue 38). Native Mem0 also kept user 25's fold,
      but its fetch missed it at the deletion probe. These are the
      first folds outside `no_delete`; users 19 and 25 are not echo
      users.
    - Some passes had the value in another probe's block or answer:
      kernel and replicated Mem0 3 of 22, native in-house 2 of 22,
      native Mem0 8 of 28 (7 echo users, and user 25 through its fold;
      later answers named the value 9 times, 2 of them user 25's),
      in-house kernel and replicated 0 of 21 (known issue 43). Native
      Mem0's 28 of 30 says little: in 9 of its passes the store still
      held the value (the echo row for 8 echo users, the fold for user
      25), and its fetch missed it at the deletion probe. In every cell
      the store kept the echo row of all 10 echo users.
  - **Recall.** Native Mem0 passes 5 of 30, and all 25 misses had the
    value outside the block (its clamped score, `NATIVE_USAGE.md`).
    Every other cell passes 29 or 30 of 30, though the cap binds in
    every probe. The one kernel Mem0 miss (user 24) had "Emily Carter's
    home is in Bologna." in the block; Qwen answered with the stale
    offsite city, Tartu, which the privacy probe's stored answer had
    restated as current ("User's team is currently in Tartu for an
    offsite.", this session; known issue 45). Earlier answers also
    carried three passes whose writer row was not in the block: user
    13 in in-house kernel and replicated (the budget left only the
    privacy answer) and user 0 in native Mem0.
  - **Recency fails by naming both values**, as the spec expected.
    Outside native Mem0, 47 of 150 pass and 147 of 150 name the new
    value; 100 of the 103 failures name both values. In in-house kernel
    and replicated (identical answers), each cell's 22 failures all
    name both, 19 of them with the old one as past (`named_as_past`
    counts 18: user 13's "initially planned for Lausanne but has since
    been relocated to Galway" has no listed marker). Native Mem0's
    failures name neither value in 26 of 30, with neither in the block.
  - **Contradiction goes with the question's wording** (known issue 44).
    Outside native Mem0, 68 of 150 pass. Of `pilot_v2`'s 30
    contradiction questions, 10 share more content words (function
    words dropped, word forms as written) with the earlier statement
    than with the later one (the four manager and six teammate users),
    16 with the later one (the home_city, client, one_on_one and
    conference users), and 4 tie (offsite_city, whose two statements
    differ only in the city). Pooled over those five cells, they pass 9
    of 50, 59 of 80 and 0 of 20; in kernel in-house, 1 of 10, 13 of 16
    and 0 of 4. Each group is whole slots, and the pool counts the same
    30 users five times (in-house kernel and replicated are
    identical). Counting every word gives 9, 13 and 8 (the conference
    questions and user 5's tie), Porter stemming makes the teammate
    questions tie ("pairing", "paired") and Snowball stemming the
    one_on_one questions too ("weekly", "week"), but under every count
    the later-leaning questions pass far more often (50 of 65 to 59 of
    80, against 9 of 70 to 18 of 85 for the other questions, the
    earlier-leaning ones and the ties together). Within a slot the
    rows' words may count too: in kernel and replicated Mem0, where
    Mem0 reworded a teammate's stale row without "pairing" (all 7 from
    known issue 41's awkward adds, users 8, 17, 20 and 26), 5 of 7
    passed and all 7 named the new value, against 0 of 5 and 1 of 5
    where the row kept it. These are 12 probes of 6 users: 17, 20 and
    26 reworded in both cells, 5 and 11 kept in both, and user 8
    reworded in kernel only, failing both times and naming the new
    value only there; the stale row also outscored the new one in 3 of
    the 5 kept and 1 of the 7 reworded.
    - Block order does not explain it. Kernel and replicated print rows
      by writer type (profile first), so the order is the writers'. Of
      the 13 kernel in-house failures that named only the earlier value,
      12 held both rows (user 1's later row was not in the block), and
      in 9 of them the later value's row was listed above the earlier
      one, against 3 of the 10 passes that held both; the six home_city
      users, whose earlier (profile) row is listed first, passed 6 of 6.
      By retrieval score, the later row ranked higher in all 10 of those
      passes and in 8 of the 12 failures; in the other 4 (users 11, 19,
      25 and 28) the earlier row outscored it. Each of these 4 questions
      and user 1's leans to the earlier statement.
  - **Earlier answers restate stale values** (known issue 45). Each
    probe's answer is stored, and later probes read it as "(this
    session)". Qwen's answers restate other facts, stale ones included.
    User 27's contradiction question ("Who do I have a weekly
    one-on-one with?") leans to the later statement. In kernel Mem0 the
    deletion answer pointed to Sofia Lindqvist, the stale value, "whom
    you meet with one-on-one every week", and Mem0 stored it ("User has
    weekly one-on-one meetings with Sofia Lindqvist, who may be able to
    provide guidance or direct them to the appropriate person …", this
    session). The contradiction answer named Sofia Lindqvist first,
    then Nadia Farouk ("Additionally, you also have a weekly one-on-one
    meeting with Nadia Farouk, though that was 2 sessions ago."), and
    repeated the stored row ("Sofia Lindqvist may be able to provide
    guidance or direct you to the appropriate person …"). Replicated
    Mem0 went the same way: it stored "… suggesting she might be a key
    stakeholder or mentor for the project", and the answer named both
    and said "Sofia Lindqvist might be a key stakeholder or mentor for
    your project". In in-house kernel and replicated, whose deletion
    answer named Nadia Farouk, the contradiction answer named only Nadia
    Farouk and passed. Native in-house had the same two verbatim rows,
    but its stored deletion and privacy answers named Sofia Lindqvist,
    and its contradiction answer named only her. The stale writer row
    was in all five blocks, but Mem0 also stored the later statement
    without "only" ("Natalie Green has a weekly one-on-one meeting with
    Nadia Farouk.", known issue 42). User 12, with the same question,
    went the other way: kernel and replicated Mem0 passed, though its
    later statement also lost "only", and in-house kernel and
    replicated failed, naming only the stale value, though their block
    held a stored deletion answer that named the new one (native
    in-house failed too, without such an answer). So the example shows
    answers repeating a stored answer, not what decided the outcome.
    - Outside native Mem0, such an answer sat in 66 of 150
      contradiction blocks, which passed 19 of 66, against 49 of 84
      without one. By the question's wording: leaning to the later
      statement, 14 of 28 against 45 of 52 (within client, conference
      and one_on_one, 14 of 28 against 18 of 22; home_city never had
      one); to the earlier statement, 5 of 20 against 4 of 30, four of
      the five passes user 20's, whose stored answers name both values
      (without user 20, 1 of 15 against 4 of 30); ties, 0 of 18 against
      0 of 2. Nearly every tie has such an answer (18 of 20, against 20
      of the 50 earlier-leaning and 28 of the 80 later-leaning), and no
      tie passed: without the ties, 19 of 48 against 49 of 82 (odds
      ratio 0.44, against 0.29 pooled), but compared within each user
      across the cells it is 0.26 (from the 9 users whose cells differ
      both in having such an answer and in passing). These are 30 users
      in five cells, and in-house kernel and replicated are identical.
      Recency: 1 of 16 with one, 46 of 134 without. No run yet scores
      the probes without the stored answers (open decision 2).
  - **Integration.** Mem0 cells score 2.93 to 3.33 and native in-house
    2.90, but in-house kernel and replicated 1.77 and 1.80. Their
    integration block, the last probe's, holds 4.6 rows, 2.8 of them
    earlier answers stored verbatim, and the 500-token budget binds in
    27 of 30. The judge scores the answer against the base profile and
    the base task context (its keyword half is the lower of the two).
    The base task row reached the block for 9 of 30 users (mean score
    2.11 in both cells, against 1.62 without in kernel and 1.67 in
    replicated) and the base profile row for 5, both for 1 (user 25,
    score 4). In kernel in-house the score rises with the base rows in
    the block: 1.53, 1.92 and 4 for 0, 1 and 2 of them (n = 17, 12 and
    1).
    - Reproduced on a copy of the kernel's store (the reproduction
      matches all 30 blocks), the budget cut the base task row for 14
      users and the cap for 7, and the base profile row for 17 and 8;
      all five earlier answers ranked above the base task row for 15
      users and above the base profile row for 22. With the earlier
      answers removed, the same selection keeps the base profile row
      for all 30 users and the base task row for 28 (blocks of 196 to
      314 tokens); with the budget removed instead, it keeps the base
      task row for the same 23 users as native in-house.
    - Native in-house has no budget: its blocks hold 9.6 rows, 4.7 of
      them earlier answers, the base task row for 23 users and both
      base rows for 13 (mean score 2.35 and 3.62 with 1 and 2 base
      rows, n = 17 and 13). Mem0 splits each base event into short
      rows; a base task row reached 28 to 30 of 30 blocks and rows of
      both base events 22 to 24, and the budget never binds there.
      Without a budget the backends' means are close (native Mem0 2.93,
      native in-house 2.90), but the paired data do not show a tie:
      Mem0 minus in-house is 0.03 (95% CI -0.54 to 0.61), and 22 of 30
      users scored differently.
    - So the in-house kernel and replicated blocks mostly lack the base
      rows, which the earlier answers, stored verbatim, displace under
      the budget (the base task row for 14 users, the base profile row
      for 17) and past the cap (5 and 8 more users, who get them back
      without the answers) (known issue 45); no judged run yet scores
      the probe without them (open decision 2).
    - Kernel against native on Mem0 (3.33 and 2.93; paired t p = 0.05,
      Wilcoxon p = 0.07) is not a budget effect: the budget never binds
      there. Native Mem0's blocks, ranked by its clamped score, also
      hold fewer base task rows (1.3 per block against 2.3). Paired by
      user, the score difference goes with the direction of the row
      difference: 0.64 where the kernel's block held more (22 users; 13
      higher, 2 lower), 0 where it held as many (4 users, all tied),
      -0.50 where it held fewer (4 users; 2 lower). It does not go with
      its size (0.86, 0.20 and 0.33 for 1, 2 and 3 more rows; n = 14, 5
      and 3); within each Mem0 cell the score hardly changes with their
      number (across users, at equal counts native scores lower: one
      row 2.95 against 3.17, n = 19 and 6; two rows 2.71 against 3.38,
      n = 7 and 13); and replicated against native, with the same
      difference in rows (2.3 against 1.3), does not show it (of the
      users where both differ, the signs agree for 10 of 16, against 15
      of 17). An association in one pair of cells; the smoke does not
      explain this gap. Kernel against replicated is unaffected: one
      library, one order.
  - **Kernel against replicated.** In-house: identical blocks and
    identical answers in 180 of 180 probes, no discordant pair. The
    judge scored one of the 30 identical integration answers
    differently (2 and 3; known issue 24). Mem0: discordant pairs on
    recall (0 and 1), recency (3 and 3) and contradiction (2 and 1),
    all p = 1.00; Mem0's extraction varies between runs (known issue
    42).
  - **Cap and budget.** The cap bound in all 180 probes of every cell.
    The budget bound in 82 of 180 probes of in-house kernel and
    replicated (by probe, in order: 0, 3, 15, 16, 21 and 27 of 30) and
    never in Mem0 (at most 475 estimated tokens). Native in-house
    blocks reach 1,164 tokens (no budget, by design).
  - **Against the pre-stated expectations.** Kernel and replicated tie
    on in-house.
    - Recall fails most for native Mem0 (25 of 30, the value never in
      the block) and elsewhere once (kernel Mem0, user 24, with the
      value in the block). Outside native Mem0 the cap binds in every
      probe but dropped no recall target; the budget cut one (user 13,
      in in-house kernel and replicated), whose value reached the block
      through the stored privacy answer. The spec expected more
      failures for targets written early; native Mem0 shows the
      reverse: it passed 5 of the 10 targets written in session 1 and
      none of the 20 written in sessions 2 and 3. The session need not
      be the cause: the target's row reached the recall block for 4 of
      the 6 home_city targets (all six written in session 1) and none of
      the other 24, and the fifth pass, user 0, came through the stored
      privacy answer.
    - Recency fails by naming both values outside native Mem0 (100 of
      103 failures); native Mem0's failures name neither (26 of 30).
    - Deletion fails through the echo row where that row reaches the
      block: the store kept it for all 10 echo users in every cell, and
      it reached the deletion block for 9 of 10 in in-house kernel and
      replicated, 8 in native in-house, 5 in kernel and replicated Mem0
      and 1 in native Mem0. On Mem0, folds failed 3, 3 and 1 users,
      each made by the writer's next write before the revoke; no writer
      row written after a revoke holds the value, so no failure came
      from Mem0's history after a delete. Privacy holds.
    - The budget binds in in-house kernel and replicated from the
      second probe on, more often later (above).
    - Contradiction does not fail by block order. By score, the stale
      row outranked the new one, or the new one was not in the block,
      in 26 of the 59 failures outside native Mem0 that named only the
      stale value, each with a question that leans to the stale
      statement or ties, so rank and wording go together (in kernel
      Mem0 the stale row outscored the new one in 7 of its 9 such
      failures, against 1 of 15 passes). Where the question leans to
      the later statement, contradiction also passes less often with a
      stale earlier answer in the block (14 of 28 against 45 of 52);
      where it leans to the earlier one, the split turns on one user,
      and no tie passed (above).
  - **Verification.** An independent re-score of the records found no
    wrong value (ground truth, block and answer checks, passes, bounds,
    judge scores, and the pass counts and integration means in
    `analysis.json`; the provenance lists them). A read-only review in
    six parts, each of its 36 error or imprecise findings checked by an
    adversarial verifier (its two style findings were not), then
    recounted all 991 values `analysis.json` held before its fixes, the
    readings included, with its own code and found none wrong; the 121
    values its fixes added (1,112 in all) match its counts, and an
    independent recount of them found none wrong. It found errors and
    overstatements in this write-up, now corrected (the stale-answer
    example quoted user 6's deletion answer as its recall answer;
    recall failed once outside native Mem0, not never; native Mem0 kept
    a second fold), gaps in the analysis's descriptions and tests, now
    fixed (below), and the Zep key in the earlier attempt's kernel log,
    which predates the redaction (the provenance says so). A second
    review, in five parts with the same checks, read the corrected text
    and code. It found overstatements and gaps, now corrected: user
    27's contradiction answers in kernel and replicated Mem0 named both
    values, and the example did not show what decided the outcome; the
    stored answers split by wording; what the smoke shows about the
    integration gap and the wording, known issue 41's "changes no
    score" included; open decision 2's bounds held only at H = 0, and
    it left out that a budget on writer rows alone, below about 293
    tokens, brings back part of the difference between the loci on
    integration; and smaller points (the recency answers that name the
    old value as past, native Mem0's recall by session, what
    `analysis.md` holds, the count of values the first review
    recounted, the test baseline at the end of the subtask). It also
    found a note that held only for native cells, and tests that missed
    some mutants or caught one only on some hash seeds, now fixed. A
    third review, in three parts, of the second round's corrections
    found no error. It found imprecisions, now corrected (what
    `analysis.md` holds, the summary of the second review, the
    stemmer, the split within users, kernel against native Mem0 paired
    by user), and tests that still missed a few mutants, now fixed. A
    fourth review, in two parts, of the third round's corrections found
    no error. It found that the list of what `analysis.md` does not hold
    left out replicated against native Mem0 paired by user and the split
    within users, now added, and that the tests did not pin every rule
    this file said they did, nor two rules this file did not state, each
    behind values in the readings (an integration probe without a score
    still counts; a probe type with no failure in a cell gets no misses
    row), now pinned (below). A fifth review, in three parts, found no
    error either. It found rules behind values in the readings that the
    tests did not pin, now pinned (below): in the earlier-answer split,
    recency, an earlier answer beside a writer row, and strict passes;
    the slots' lenient count; calendar rows as writer rows; the deletion
    probes of users with and without an echo event; sources joined from
    a set that does not hold them in reverse sorted order; a
    probes-listing row on a failure; and mean integration scores, not
    medians (two of its mutants showed this one when run on the
    corrected tests). It also found that this file claimed more than the
    tests pin of the rows' order, the headings and the notes' text, and
    the tests' comments more than they check of the notes, now narrowed.
    It was the last review (rule 6).
    None of this run's results files or logs holds the Zep or the Azure
    key, so the redaction (AIOS `e3cdc52`) holds in a live run.
- **Analysis readings after the smoke** (Cerebrum `8dbea1e`,
  with tests that fail without them). `bench_v2_analysis.py` also
  reports trial-level exposure for deletion and privacy, each deletion
  failure's carrier and what the store kept behind each deletion probe
  (`revoked_value_rows`, passes included), where the expected value was
  in each failure, contradiction per slot, recency and contradiction
  split by an earlier answer with the stale value, and the integration
  probe's block with its score by the base rows it holds (known issues
  38 and 43 to 45). After the reviews: a failure whose value is in the
  block text but in no row is its own class (it was filed under
  `conversation_only`; no `s14b` or `f14c` probe is one), `named`
  counts the failures that named the expected value too (it was
  described as a miss), the carrier labels and the note on what the
  store kept say what the code does, and the tests pin these rules of
  the readings: the failed trials, unscored probes and trials without
  the probe that they skip; rows only for what occurs, and a cell's
  labels, slots and base-row counts in sorted order; every label
  (`unknown` included; sources join in sorted order whether a set holds
  them in that order, in its reverse or in neither, checked on three
  pairs and a triple); what `named` counts; a probe's own block and
  answer, and an earlier probe's block; the deletion probes of users
  with and without an echo event alike; in the earlier-answer split,
  recency as well as contradiction, an earlier answer with the stale
  value beside a writer row that has it too, and strict passes only;
  the slots' lenient count (passes and answers that name both values,
  not answers that name only the earlier value or neither); calendar
  rows as writer rows; base events in a later session; later task and
  profile rows (beside a base task row too); integration probes without
  a score (all 105 of `f14c`'s); an integration probe's own score
  before the trial's, and its own budget, not another probe's; mean
  integration scores, not medians; and the report `main` writes, with
  each reading's title and columns, in order, the phrases of its note
  that give its definitions, and nothing for a reading without rows.
  On the final tests, of 309 mutants of the module (the author's 52,
  the fourth review's 71, 3 more and the fifth review's 183), 199 fail
  the tests under each of ten hash seeds and the other 110 pass under
  each. Of those 110, 62 only reorder rows, 16 change only a heading's
  level or a note's text outside its pinned phrases, and 32 change no
  output on `s14b` or `f14c` (two of them are equivalent). The sections
  it reported before are unchanged, byte for byte on `f14c` and `s14b`.

### Subtask 15

Step 0 settles two items before the deletion and supersession work.

- **A. Native Mem0's ranking is Mem0's own.** The reference native
  consumer uses Mem0's results in the order returned and acts on no
  score: `NativeMemory._search` keeps Mem0's order, and `_select`
  filters by metadata only (partition, visibility). Its threshold and
  budget steps run only when set, and only the H = 2 V4 consumer sets
  them. Two new tests pin this (Cerebrum
  `tests/agents/test_native_conditions.py`): for generated rows, scores
  and k, the consumer's selection (`_select`) keeps the rows it may
  see, in the backend's order, cut at k by position; and the native
  Mem0 block follows Mem0's order and records its scores as returned.
  Both fail if `_select` sorts by score or applies Mem0's 0.1
  threshold; the first calls `_select` alone, so a sort or that
  threshold in `NativeMemory._search` fails only the second. No
  consumer change was needed, so nothing was re-run.
  - **Evidence** (`NATIVE_USAGE.md`, "Evidence"). Cerebrum
    `results/native_mem0_ranking/replay.py` (`7d4224a`) replays the
    smoke's (`s14b`) native Mem0 searches with Mem0's own `search` and
    the consumer's own selection, on a copy of the cell's store as it
    stood at each probe. It reproduced all 90 recorded fetches (the
    recall, recency and contradiction probes of 30 users): the row
    count, and the rows the block showed, in the same order with the
    same scores. In 42 of them the sharing rule hid one row, which the
    record gives only as a count: the user's one private row, whose
    place in the fetch and score come from the replay. Every row's
    score was its squared L2
    distance to the question capped at 1.0, so the rows at cosine 0.5
    or below come first, and those above follow, least similar first.
  - The recall target was the user's nearest row by cosine for 26 of
    30 users. Mem0 ranked it a median 24.5th, and it reached the
    10-row fetch for 4 users, the four whose recall passed on its row.
    The fifth recall pass (user 0) came through an earlier probe's
    stored answer. The recency target reached the fetch for 1 user.
    For users 0 to 4 the section lists every row Mem0 ranked above the
    target. In all ten of their recall and recency probes, the target
    is the user's first to third row by cosine, and Mem0 ranks it last
    or within two of last.
- **B. Benchmark v2 Amendment 3** (`BENCHMARK_V2.md`; the spec AIOS
  `458b040`, before the code; its implementation notes `773077f`).
  - **Probes write nothing to memory.** v2 kernel runs set
    `auto_extract` off with injection on (`set_memory_mode.py
    --extract off`, the driver, and the pre-flight, which refuses
    anything else). The replicated and native assistants skip their
    conversation write when the locus sets `store_conversation` false,
    which it does for every probe turn. A probe turn that stored a row
    fails the user (`probe_writes`, from the listings before and after
    the probes), and the driver fails a kernel phase whose log shows a
    stored conversation turn. One test per locus shows that a probe
    turn writes nothing and that the same turn, stored, writes its row:
    native in-house and Mem0 (`test_v2_writers.py`), replicated
    (`_v2_replicated_checks.py`), the kernel through the executor with
    a real extractor and manager (`test_v2_requests.py`), and the
    harness over all three loci (`test_history_v2.py`), which also
    checks the failure. The pre-flight has its first tests
    (`test_v2_preflight.py`).
  - **The rationale's figure.** The task gave "9 of 525 smoke probes";
    9 of 525 is the revision-1 functional check (`f14b`). The spec
    gives the revision-2 figures: 19 of the smoke's 900 judge-free
    probes, and 12 of the revision-2 check's 525.
  - **Budget 300** (the pre-flight's `V2_SETTINGS`, the driver).
  - **`users_v2` revision 3** (Cerebrum `af078c3`, SHA-256
    `ecd3585f…`; the generator `5b5f0de`; revision 2 kept in
    `repo-artifacts/Cerebrum/users_v2_revisions/`). Each contradiction
    slot has a question that leans to each statement, alternated within
    the slot: 75 of each lean in `users_v2`, 15 in `pilot_v2`, every
    slot within one of half. The lean counts content words as written
    and by word family. Four templates changed; the scripts and every
    utterance but the contradictions' statements (214 changed) are
    revision 2's.
    - The first build (Cerebrum `4ac61fe`, SHA-256 `e019ece9…`) passed
      every check, but reading its new paraphrases found statements
      that lost their meaning ("My work is based in X"; 16 client
      statements about "a project", not this one; "I am under X's
      report"). It was not kept; meaning rules per slot reject those
      (`LEAN_MEANING`), and the build was made again.
    - The final build: 344 GPT-4o calls, 22 fallbacks to the template
      text (21 client earlier statements, 1 home_city contradiction).
      Both lean questions of every user lean as designed under the rule
      and under Porter and Snowball stemming (300 of 300 each); counting
      every word, 141 of the 150 asked questions lean as assigned and 9
      tie. Some new paraphrases read awkwardly, and 18 home_city
      earlier statements gained "currently" (known issue 41).
  - **Open decisions 2 and 3 are resolved**, as (b) and (a), by this
    amendment.
  - **Functional check under Amendment 3** (`f15a`; Cerebrum
    `results/bench_v2_functional_a3/`, `596451c`): `pilot_v2` users 0
    to 4, Qwen, no judge, Subtask 14's 21 cells with its three
    controls, on Cerebrum `af078c3` and AIOS `38696f3`. 105
    user-trials, 0 failed: no user failed `probe_writes`, neither
    kernel phase's log shows a stored conversation turn, and the agent
    phase made no kernel memory operation. 0 of the 525 judge-free
    probes are contaminated, and no block held a probe answer.
    - Eight of the nine criteria hold. In the real conditions (H = 0
      and 2), with the control: deletion passed 46 and failed 14, and
      `no_delete` failed 25 of 30; privacy 59 and 1 (native in-house's
      V3 consumer), `no_visibility` 5 of 10; recall 47 and 13, recency
      15 and 45, contradiction 23 and 37, each failing 5 of 5 under
      `no_memory`. Non-echo in-house deletion passed 18 of 18, the
      kernel's privacy probe never failed (35 probes), and the cap
      bound in 54 of 60 kernel probes per backend and 42 of 60
      replicated.
    - **The budget criterion fails.** 300 bound in no probe of a
      kernel or replicated in-house cell; their largest block was 291
      estimated tokens. It bound in 3 Mem0 probes (kernel `no_delete`
      recall and integration, replicated H = 0 recency), so the budget
      step ran in both loci. The spec says the design changes before
      the smoke: open decision 4.
    - Kernel against replicated at H = 0: 30 of 30 in-house blocks are
      identical; on Mem0, 3 of the 25 paired probe outcomes differ.
    - Deletion failed in the real conditions through the echo row of
      users 0 and 4, and once through a Mem0 fold (replicated Mem0,
      H = 0, user 1; known issue 38).
    - In every kernel and replicated cell at H = 0, the stale row
      reached the block in all 5 recency and all 5 contradiction
      probes. Every failing recency answer named both values (14 of
      14, the stale one as past in 12); 6 of the 8 failing
      contradiction answers did not name the later value.
    - Users 0 to 4 have one contradiction each, 3 leaning to the
      earlier statement (client, conference, home_city) and 2 to the
      later (manager, one_on_one), so the check cannot tell the lean
      from the slot: in the real conditions, 10 of 36 and 13 of 24
      passed. The smoke's 30 users have 15 of each.
    - Against the revision-2 check (`f14c`: stored answers, budget
      500), the real-condition passes are deletion 46 (47), privacy 59
      (59), recall 47 (47), recency 15 (21) and contradiction 23 (23).
      The data and settings differ, so the runs are not paired, and no
      cause of the recency difference is established.
  - **Reviews.** Reviewed with step 1 (step 1, "Review").
- **Step 1: complete deletion and supersession**
  (`DELETION_AND_SUPERSESSION.md`; `BENCHMARK_V2.md`, Amendment 4).
  - **Reviews of the design.** The spec was reviewed before any code,
    and its decisions were settled on 2026-11-10 (open decisions 4 and
    5), with two changes to its proposals: carriers are matched with
    the scorer's own matcher, aliases included, and the budget gets no
    criterion (its binding is reported, not required, in the check and
    the smoke; the writer-only replay was dropped). A second review,
    before the first commit, made three more changes:
    - the matcher moved into the library
      (`aios/memory/pipeline/matching.py`; Cerebrum's `probes.py` loads
      it by path);
    - no module of the library imports `cerebrum` (a test scans each
      file; the usage tag is passed in; importing the library still
      loads `cerebrum.utils.usage`, through the providers package's
      Mem0 provider);
    - the audits read the raw store, not the owner-only listings the
      read guard now filters.
  - **Code** (AIOS `a610dcd`, `9b3e1db`, `210aa58`; Cerebrum `059e5a5`):
    - the library's `forget`: the tombstone first, then every row of
      the slot and every carrier of a value or alias, of any agent,
      deleted, and Mem0's messages and history records scrubbed;
    - the sweep after every write and update; the read guard on
      injection, SDK search, `get_memory` and `list_own`;
    - supersession (`memory.supersession: exclude`), with
      metadata-only marks;
    - the kernel's `forget_memory` and `GET /memory/audit`, and each
      Mem0 store's own history file (known issue 46);
    - the writers' revoke through the forget (native and
      `writer_scoped`: the owner's list and delete), and
      `value_aliases` on every statement;
    - in the harness, the raw-store listings in kernel and replicated,
      `retired_rows` and `retired_in_block`, the controls
      `writer_scoped` and `no_supersession` (the driver's `_ns`
      phases), and the pre-flight's new checks;
    - the analysis's new criteria, with the budget's binding reported,
      not required.
  - **Found by the test agents and fixed before the first commit:**
    - a forget's report could spell a value as another agent's private
      row spells it, and a restatement's `lifted` named the
      tombstone's spelling;
    - a refused forget, an update without a `memory_id` and an add
      whose note could not be built kept the barrier sequence stamped
      at acceptance, so every later retrieval of the user waited out
      the barrier's timeout;
    - Mem0's scrub found nothing to scrub in a store without a history
      path of its own;
    - `revoked_value_rows` did not carry the carrier's text.

    The spec's claim that a write during a forget is swept was
    narrowed: one that commits between the forget's listing and its
    tombstone stays stored, and the read guard drops it from every
    read.
  - **Tests:** AIOS 606 passed and the 14 errors (136 new); Cerebrum
    1050 passed, 4 skipped, the same 19 failures and 2 errors, by name.
    The test agents checked their tests against mutants of the rules
    they pin; the subtask's review, its verification pass and the
    mutation run on the final code follow ("Review" and "Mutation
    run", below).
  - **Functional check under Amendment 4** (`f15b`; Cerebrum
    `results/bench_v2_functional_a4/`, `5b3295e`): `pilot_v2` users 0
    to 4, Qwen, no judge, 29 cells (Subtask 14's 21, plus
    `writer_scoped` and `no_supersession` in the kernel and replicated
    cells of both backends), on Cerebrum `059e5a5` and AIOS `945548e`.
    145 user-trials, 0 failed: no user failed `probe_writes`, no kernel
    phase's log shows a stored conversation turn or a guard warning,
    and the agent phases made no kernel memory operation. 0 of the 725
    judge-free probes are contaminated, and no block held a probe
    answer. The first launch's first agent cell (replicated Mem0,
    H = 0) was to be stopped before the Mac slept, but it ran on
    through the sleep's dark wakes and was stopped at 17:28:39, after
    the wake, while it wrote its fifth user. It wrote no results file,
    but its store (`.replicated_memory/f15b`) keeps 89 rows of its 5
    users, 4 tombstones, 99 history records and 67 messages, so that
    cell ran again, and the 19 cells after it ran, under a new run
    prefix, `f15b2` (known issue 36; the results' `PROVENANCE.md`).
    - **Every criterion holds.** Amendment 4's, at H = 0 in the kernel
      and replicated cells on both backends:
      - all 20 deletion probes passed, no audit kept a carrier
        (`revoked_value_rows`), and all 20 revokes went through the
        forget. Each cell's 5 forgets deleted 7 rows: the revoking
        writer's row by `fact_key` for every user, and for users 0 and
        4 another agent's echo, by value;
      - `writer_scoped` failed 6 of its 8 echo-user deletion probes:
        users 0 and 4 in-house, user 4 on Mem0. User 0's Mem0 echo rows
        stayed in the store and out of the deletion probe's block, but
        reached its privacy, contradiction and integration blocks in
        both loci, and replicated's privacy answer named Mattermost (a
        pass: its forbidden value is another). The value showed in all
        8 echo-user trials (known issue 43);
      - every earlier statement's row was marked (10 of 10 per cell),
        and no block held one (0 of 120 probes); `no_supersession`
        marked none and put one in 109 of its 120 probes;
      - the guard reported its stage in all 510 probes of the 17 cells
        built on H = 0, was armed in every probe after a forget, and
        dropped nothing;
      - every Mem0 forget scrubbed a message: 7 messages and 14 history
        records per cell, in the store's own history file.
    - Subtask 14's, in the real conditions (H = 0 and 2), with the
      control: deletion passed 57 and failed 3 (native in-house, the
      echo rows of users 0 and 4), and `no_delete` failed 25 of 30;
      privacy 59 and 1 (native in-house's V3 consumer, H = 2),
      `no_visibility` 6 of 10; recall 47 and 13, recency 34 and 26,
      contradiction 38 and 22, each failing 5 of 5 under `no_memory`.
      Non-echo in-house deletion passed 18 of 18, the kernel's privacy
      probe never failed (55 probes), and the cap bound in 54 of 60
      kernel probes per backend, 36 of 60 replicated in-house and 42 of
      60 replicated Mem0.
    - **The budget** bound in no in-house probe (the largest kernel or
      replicated in-house block was 296 estimated tokens) and in 10
      Mem0 probes, 5 per locus: 6 recency, 2 integration, 1 deletion
      and 1 recall (`f15a`: 3). Reported, not required (Amendment 4).
    - **Against `f15a`** (step 0's code, which had no supersession;
      the same data, users and other settings), the real-condition
      passes are deletion 57 (46),
      privacy 59 (59), recall 47 (47), recency 34 (15) and
      contradiction 38 (23). With supersession off, the in-house cells
      repeat `f15a`'s H = 0 rates in both loci (recency 1 of 5,
      contradiction 3 of 5), and their blocks are `f15a`'s in 19 of 30
      probes; the other 11 are users 0 and 4's, whose echo rows the
      forget now deletes. The Mem0 `no_supersession` cells do not
      repeat `f15a` (kernel recency 4 of 5, `f15a` 1 of 5): Mem0's
      extraction varies between runs (known issue 42).
    - **What supersession leaves**, as `DELETION_AND_SUPERSESSION.md`
      says it would. At H = 0, with supersession on, no kernel or
      replicated in-house block held a stale value; native in-house's
      held one in all 30 of its recency and contradiction probes, and
      the in-house `no_supersession` cells' in all 20.
      Kernel Mem0 failed 2 recency probes (users 1 and 2) through the
      new statement's own row, which Mem0's extraction wrote as a
      transition ("relocated to Kaunas from Utrecht"); both answers
      named the old value as past. Replicated Mem0's rows of those
      events name only the new value, so the loci differ in those 2 of
      25 paired Mem0 outcomes (in-house: 30 of 30 blocks identical).
      In replicated Mem0, user 2's earlier client reached a
      contradiction block through two task rows of other facts into
      which Mem0 folded it; the answer passed.
    - **H = 2** (reported, not required): replicated leaves user 4's
      first `home_city` row unmarked on both backends. Its V2 profile
      writer stores it under `…@users.example`, and the later
      statement, under the canonical id, does not reach that partition
      (the spec's "rows another identity convention puts in another
      partition"). The kernel folds the domain into the canonical id
      and marks the row.
    - **UTC dates** (known issue 42): the run crossed 00:00 UTC. The
      kernel Mem0 cells other than `no_supersession` (H = 0, H = 2,
      `no_delete` and `writer_scoped`) and the agent phase's Mem0
      cells through `no_visibility` ran on 2026-11-10 UTC,
      `writer_scoped` replicated Mem0's users 0 to 2 on 2026-11-10 and
      users 3 and 4 on 2026-11-11, and both `no_supersession` Mem0
      cells (kernel and replicated) on 2026-11-11.
  - **Smoke, first attempt** (`s15`; Cerebrum `5b3295e`, AIOS
    `52bf922`; started 2026-11-10 19:52 EST). Its first cell, kernel
    Mem0 at H = 0, ran its 30 users, and the driver stopped on one
    failed trial: the extraction check failed user 19
    (`backend_extraction_failed: stored no rows: u019-e08`). Mem0 had
    folded the revoked codename into the only row of `u019-e08`, the
    task writer's write just before the revoke, and the forget deleted
    that row by value, as Amendment 4 requires. All five of user 19's
    judge-free probes passed, and its audit kept no carrier.
    - Fixed in Cerebrum `64da5f7` (`BENCHMARK_V2.md`, Amendment 4,
      "Corrected during the smoke"; known issues 32 and 38). Replayed
      on the saved records, the fixed check excuses only `u019-e08`
      and flags nothing in `f15a`, `f15b` or the attempt's cell.
    - A read-only sweep of the harness, the analysis, the library and
      the documents for the same assumption found no other check that
      a same-session forget breaks, and one reading to correct: the
      analysis files a failed recall whose target's only row a forget
      deleted under `not_in_block` ("never stored, or selection lost
      it"). In the attempt's cell those were users 13 and 25, the only
      recall failures (28 of 30 passed): Mem0 had folded a revoked
      value into each target's row ("Not pre-stated",
      `DELETION_AND_SUPERSESSION.md`).
    - The attempt's results and run log are in
      `repo-artifacts/Cerebrum/bench_v2_smoke_a4_s15/`.
  - **Smoke** (`s15b`; Cerebrum `results/bench_v2_smoke_a4/`,
    `8245e5f`, with its provenance): `pilot_v2`'s 30 users, Qwen, the
    six cells at H = 0, judge v2 (gpt-5.4) on the integration probe, on
    Cerebrum `64da5f7` and AIOS `ef3fdc9` (the kernel's code is
    `945548e`'s). It ran 2026-11-10 21:28 to 2026-11-11 01:46 EST, all
    on 2026-11-11 UTC (known issue 42). 180 user-trials, 0 failed: no
    user failed `probe_writes`, neither kernel phase's log shows a
    stored conversation turn or a guard warning, and the agent phase
    made no kernel memory operation. 0 of the 900 judge-free probes are
    contaminated, and no injected row is a conversation row. Passes
    over users (recency and contradiction: lenient in brackets):

    | Locus | Backend | Deletion, no echo | Deletion, echo | Privacy | Recall | Recency | Contradiction | Integration, mean [95% CI] | Share ≥ 4 |
    |---|---|---|---|---|---|---|---|---|---|
    | kernel | mem0 | 20/20 | 10/10 | 30/30 | 28/30 | 22/30 (30/30) | 30/30 (30/30) | 3.57 [3.25, 3.89] | 0.73 |
    | kernel | inhouse | 20/20 | 10/10 | 30/30 | 30/30 | 30/30 (30/30) | 30/30 (30/30) | 2.87 [2.50, 3.23] | 0.40 |
    | replicated | mem0 | 20/20 | 10/10 | 30/30 | 28/30 | 23/30 (30/30) | 30/30 (30/30) | 3.60 [3.31, 3.89] | 0.77 |
    | replicated | inhouse | 20/20 | 10/10 | 30/30 | 30/30 | 30/30 (30/30) | 30/30 (30/30) | 2.87 [2.50, 3.23] | 0.40 |
    | native | mem0 | 19/20 | 7/10 | 30/30 | 5/30 | 0/30 (0/30) | 0/30 (0/30) | 3.00 [2.62, 3.38] | 0.47 |
    | native | inhouse | 20/20 | 1/10 | 30/30 | 30/30 | 10/30 (30/30) | 18/30 (20/30) | 3.10 [2.73, 3.47] | 0.50 |

    A smoke, not a verdict: n = 30 per cell (known issue 37).
    - **Deletion and supersession, in the four kernel and replicated
      cells.** Amendment 4's criteria that need no control hold: all
      120 deletion probes pass, no audit kept a carrier, and all 120
      revokes went through the forget; no block of their 720 probes
      holds a retired row (each cell's 60 earlier statements' rows are
      all marked); the guard was armed in every probe after a forget
      and dropped nothing; all 60 Mem0 forgets scrubbed a message. Each
      cell's 30 forgets deleted every slot's row by `fact_key` and the
      10 echo users' echo rows by value; on Mem0 also two folds.
    - **What a fold costs.** In both Mem0 cells the forget deleted, by
      the value, a row of the revoking writer's other fact: Mem0 had
      folded user 13's codename into its client row and user 25's
      teammate into its codename row, in both loci. Each was its
      user's recall target and its only row, so both users failed
      recall (the analysis's `target_forgotten`); these are the only
      recall failures outside native Mem0. User 19's fold, deleted in
      the first attempt, did not recur in kernel or replicated Mem0.
      Native Mem0 kept three folds: users 13's and 19's (the codename
      in the same write's row, `u019-e08`, as in the first attempt's
      kernel cell), through which their deletion probes failed, and
      user 25's, which the deletion probe's fetch missed.
    - **What supersession leaves** (as in `f15b`): every Mem0 recency
      failure (8 kernel, 7 replicated) came through the target's own
      row, which Mem0 wrote as a transition ("moved from Ryver to
      Brosix"). Each answer named the new value, and 14 of the 15 named
      the old one as past. No kernel or replicated in-house block held
      a stale value (native in-house's held one in all 60 of its
      recency and contradiction probes).
    - **Kernel against replicated:** the in-house blocks are identical
      in 180 of 180 probes; on Mem0, 1 of the 150 paired judge-free
      outcomes differs (user 8's recency; known issue 42).
    - **The budget** bound in 3 probes per in-house cell and 5 per Mem0
      cell of the kernel and replicated loci (reported, not required).
    - **Native** runs neither the forget nor supersession: deletion
      failed through 9 in-house and 2 Mem0 echo rows and 2 Mem0 folds,
      a retired row reached 168 of 180 in-house and 131 Mem0 probe
      blocks, and Mem0's ranking kept most targets out of its fetch
      (recall 5 of 30, as in `s14b`; step 0, A).
    - **Contradiction by the question's lean** (known issue 44; joined
      from `users_v2` by `probe_id`, since the results do not record
      `lean`). Kernel and replicated passed 15 of 15 of each lean on
      both backends, with no stale row in any block; native Mem0
      passed none of either, the new value in no block. Native
      in-house, with both values in all 30 blocks, passed 13 of 15
      later-leaning questions and 5 of 15 earlier-leaning ones (lenient
      14 and 6); outside home_city, 12 of 12 and 4 of 12, and home_city
      1 of 3 each. The row of the statement the question leans to also
      came first and scored higher in 29 of 30 of those blocks, so the
      smoke tells the lean from the slot but not from the rank. n = 15
      per lean, between users.
    - **Against `s14b`** (revision 2, budget 500, no forget or
      supersession), the kernel and replicated cells' passes rose from
      deletion 22 to 30 per cell on Mem0 and 21 to 30 in-house, recency
      8 or 9 to 22 to 30, and contradiction 14 or 15 to 30, and Mem0
      recall fell from 29 and 30 to 28. Their integration means rose
      in-house from 1.77 and 1.80 to 2.87, and on Mem0 from 3.33 and
      3.13 to 3.57 and 3.60. The data, the budget and the library all
      changed, so the runs are not paired, and no difference is
      attributed to one change.
    - The analysis gained two readings after the run (Cerebrum
      `0995994`): a failure whose target's rows the trial's forgets or
      sweeps all deleted is `target_forgotten`, no longer
      `not_in_block`, and the forget reading counts `same_writer` rows.
  - **Review** (rule 6; the code and the write-up of steps 0 and 1).
    Eight scoped reviewers: 78 findings. Each of the 66 error or
    imprecision findings was checked by an adversarial verifier (the 12
    style findings were not), and none was refuted (55 confirmed, 11
    partly); the verifiers rated 13 errors and 53 imprecisions, and the
    12 style ratings are the reviewers' own. The numbers the
    corrections quote were then re-derived from the raw results, the
    dataset and the logs.
    - **Code fixes** (AIOS `c814a5d`, Cerebrum `ec623ab`), each with a
      test that fails without it. None changes a recorded result: in
      `f15b` and `s15b` no write lifted, swept or was suppressed (5,724
      writes), every write's reply named rows, no retire came from a
      write that stored nothing (398 retiring writes), and no forget
      reported a row it did not delete (180 forgets, 248 rows; the
      other 140 of the 320 revokes took the owner path); no run used
      `retrieve_memory_raw` or `--kernel-url`, and the one kernel log
      the old driver never checked (`f15b`'s first agent phase) has no
      memory operation.
      - a lift deleted the slot's forgotten statements with its
        tombstone, so after a restatement and a second forget a replay
        of the first forgotten statement lifted the new tombstone; they
        are now kept apart, per slot;
      - a statement without a `provenance_event`, and an update with
        no event of its own (it used the stored row's), lifted a
        tombstone; neither does now;
      - a write's own rows were those of its `provenance_event`, or the
        one id the provider returned: a Mem0 write that stored several
        rows could return a swept row's id, or be reported suppressed
        with a row still stored, and a write that stored nothing
        retired the slot's rows when another row carried its event.
        They are now the rows that carry its note's id;
      - `Mem0Provider.get` read every exception as a missing row, so a
        forget filed a row it failed to read under `not_found` and
        succeeded. Only `IndexError` (Mem0's missing id) is "not found"
        now, and a v2 writer fails a forget whose report lists one;
      - the kernel's `retrieve_memory_raw` branch caught nothing (an
        error left its syscall unanswered) and answered a failed fetch
        with an empty list, and an operation no branch serves raised;
        both answer `success` false now;
      - the driver's end-of-phase checks read only its own launch's
        kernel log, so a resumed phase's earlier logs, and a phase
        found finished, went unchecked; it reads every kernel log of
        the phase now, and requires `RUN_PREFIX` (and, since the
        verification pass, `OUTROOT`);
      - a v2 run with `--kernel-url` naming another kernel ran the
        pre-flight on that one, while its agents used the configured
        one; it refuses now;
      - the analysis printed an integration mean of a whole number as
        an integer (the smoke's analysis is regenerated: native Mem0's
        3 prints as 3.00).

      Two tests now pin the supersession stage before dedupe and the
      threshold, which the cap and budget readings depend on.
    - **The write-up**, corrected in place:
      - `f15b`'s stopped cell wrote rows, and was stopped after the
        Mac woke, not before it slept;
      - the smoke's dates (Mem0 also wrote "as of November 2026",
        "2026" and "December 2026"; four privacy answers dated
        made-up events);
      - native Mem0's third fold, the in-house stale-value statements
        (kernel and replicated only), user 0's echo exposure under
        `writer_scoped`, the pre-flight's recorded paths;
      - `lifted` holds values, not ids; the tombstone file is one per
        kernel, whichever provider runs; known issue 36 names the
        kernel's stores and the tombstones; the library's no-`cerebrum`
        claim is about its files (importing it loads
        `cerebrum.utils.usage`); the matcher's boundary is ASCII; Mem0's
        scrub covers the rows the forget and the sweep are given;
      - the restatement rule (a new statement as its writer labels it,
        not the user as such), the supersession rule (the latest write
        wins), a private later statement, and an own-only search's
        room;
      - revision 3's wordings (four new ones and the time cue
        "currently"; known issue 41), the pronoun claim, the lean
        balance (true of these files, not guaranteed), the lean split,
        now reported (known issue 44);
      - the native ranking evidence (what the replay compared, the
        unit-vector bound, what each consumer test catches);
      - open decision 4's label, and the SDK catalog in the local
        steering (`sdk-and-api.md`, gitignored).

      `synth_v2.py`'s `lean_start` docstring overstates the balance
      but is left: editing it would break the match between the
      generator's SHA-256 and revision 3's header.
    - **Verification pass** (rule 6's second pass, on AIOS `b15f2dc`
      and Cerebrum `80a3c7a`): six checkers over the review's 78
      findings and the fix commits, each remaining error they claimed
      confirmed by an adversarial agent. 70 findings were fixed as
      made and 6 partly; 2 fixes were wrong, and the fix commits added
      2 false sentences and made a third false. Fixed in AIOS `8db0b35`
      and Cerebrum `ca91a13`, and the documents after them. No recorded
      result changes.
      - **Errors.** The driver's new check reads every kernel log in
        `$OUTROOT/logs`, and the default `OUTROOT`s hold Subtask 14's
        runs (`f14c`'s kernel logs hold 90 and 120 stored turns), so
        the documented invocation would have stopped after its first
        phase, and a new run there would have overwritten those runs'
        cells (none did): `OUTROOT` is now required, and a test pins
        it. The `--kernel-url` help said the backend usage reads follow
        the flag; they use the configured kernel. Two sentences the
        fixes added were false: a forget that finds no value
        "scrubbed nothing" (on Mem0 it clears the history records of
        the rows it deleted), and the review's "each finding checked
        by an adversarial verifier" (the 12 style findings were not);
        and `c814a5d` made `address_request` answer an unserved
        operation while its docstring still said it raises.
      - **Two tests** the review's verification asked for were
        missing, and mutants of exactly those rules survived: a
        restatement whose value is the alias (a per-value-key record
        of the forgotten statements) and a replay that stored nothing
        (an event-and-slot gate). Both are added; each fails on its
        mutant.
      - **Wording:** a failed shared fetch is not reported, only a
        failed own fetch; `listed` is a count; a restatement needs an
        event (the SDK docstring); known issue 36's Mem0 consequence;
        the counts above; the smoke's dates; the pre-flight records
        the kernel's paths in every cell; the example config names
        `history_db_path`; the Mem0 scrub test's scope; `slot_rows`'
        docstring and four others.
    - **Third verification pass** (rule 6: the second found errors;
      on AIOS `72324e8` and Cerebrum `05e5cb7`): three checkers over
      the second pass's open items and this round's commits. Of those
      items 22 were fixed and 3 only partly (`address_request`'s
      docstring, twice, and the pre-flight's paths). It found no
      error: the one it claimed, "every cell
      records the kernel's two paths" (7 in-house kernel cells record
      a null history path), its adversarial confirmation rated an
      imprecision. Corrected in the text, with no code change (rule
      6): `address_request`'s "never raised" (a request whose
      `params.metadata` is not a dict still raises; over `/query` it
      fails with HTTP 500 before it is queued), and the same in the
      spec's "Every branch answers"; `OUTROOT` credited to the
      review's commit; two tense slips ("overwrote"); the false
      sentences' verb above; a reused `OUTROOT`'s finished cells are
      counted, not overwritten; the scrub test's bullet; the own
      fetch's rows; the smoke's December rows. Rule 6 allows no
      fourth pass.
    - **Not decided here** (the user's call): a forget deletes a Mem0
      fold row whole, so the row's own fact goes with it (the smoke's
      users 13 and 25 lost their recall targets). Rewriting the row
      without the forgotten value would keep that fact, at the cost of
      a write the forget makes on another agent's behalf.
  - **Mutation run** (rule 6, once, on the final code: AIOS `28ac914`,
    Cerebrum `e1e1ff7`). Eight module owners wrote 319 mutants of rules
    the documents state and ran each on a scratch copy against their
    area's tests; 249 were killed. Each survivor was then rerun, with a
    local Ollama allowed, until a test killed it or the full suite of
    every repo whose tests load its file (the AIOS library's: both)
    passed on it. Of the 70:
    - 8 are killed by tests outside their area's run: 3 by tests that
      need Ollama, which the run's network guard skipped (the Mem0
      provider's history path in its store, `/memory/config` reporting
      it, an in-house mark making no embedding call); 2 of the
      matcher's rules (casefolding; `_` and `/` as separators) by
      Cerebrum's matcher tests, which load the library's file; and 3
      by the rest of Cerebrum's suite: the scorer importing the `aios`
      package instead of loading the matcher by path (five test
      modules then fail to import), the library dropping the usage tag
      it is given (the replicated checks), and the `--kernel-url`
      refusal applied to a v1 run (a `main` test of a v1 run).
    - 8 could change a reported number; each now fails a test
      (Cerebrum `c2f1ed3`): a v2 trial's `retired_rows` (the field, and
      the orchestrator's argument), without which the supersession
      reading's `earlier_rows` and `marked` read 0 (`f15b`'s 10 of 10
      per cell, the smoke's 60 marked rows per cell); `retired_in_block`
      in the native locus (the smoke's native 168 and 131 would read
      0); the budget reading's in-house cells (`f15b`'s 0 would read
      2); a guard stage that kept no row (`f15b`'s guard criterion
      would fail on kernel in-house `no_memory`'s 30 probes); the scrub
      criterion's H = 0 (`f15b`'s 10 forgets would read 20); and the
      supersession reading's probes and rows (the smoke's native
      in-house 168 would read 246, and the 360 excluded rows of each
      kernel and replicated cell 180).
    - 14 are in `synth_v2.py`; six would have changed a request
      revision 3's build sent, so its counts (344 calls, 22 fallbacks)
      could differ. A test now checks `users_v2`'s `generator_sha256`
      against the generator's own hash, and fails on all 14. It pins
      that this file built revision 3, not each rule: no test of its
      own pins `generate`'s alternation past a slot's first user,
      `check`'s assignment check, the word-family rule, the family
      table's week and report forms, the family forms a request names
      as words not to use, the lean rules on a retry and on reuse,
      home_city's workplace words past "work", client's "building
      project" and "project we", the catalog check of every pool value,
      or the new contradiction templates in the catalog check.
    - 40 can change no reported result: none acts in `f15b` or `s15b`,
      or nothing reported reads it (three would change what a new run
      records of its pre-flight, which the runs' `PROVENANCE.md`
      describe). Each holds in the code (its area's owner checked it),
      but no test of either repo pins it, so this file claims no more:
      - the library: a forget's forms from its own slot's tombstones
        only; a value's aliases from every row stating it; the
        matcher's ASCII boundary (a value beside Chinese text); a
        restatement lifting by its value, not its own aliases; the
        post-write scrub after any write of a user with tombstones,
        not only after a sweep; a write that stored nothing not
        suppressed; a forget that found no value still scrubbing its
        deleted rows' history; a row retired without a session
        excluded; the guard reading a row's formatted text with its
        metadata; the sweep inside the write's barrier hold; a forget
        without a stamped sequence holding its own; "Exclude" refused
        as a setting;
      - the kernel: the audit's listing limit; the usage tag it passes
        the library (injection's embedding calls would count to no
        user; no report gives cost);
      - the harness: `forgotten_ids` only for rows its own session
        removed; a session's `stored_rows` without later deletions;
        `probe_writes` over other agents' rows (the consumer's are
        pinned); a private statement among its slot's statements;
        `revoked_value_rows` for rows outside the four agents;
      - the scorer and the run: the matcher found through `AIOS_ROOT`;
        `deleted_ids_in_block` in every probe and over every owner (no
        reading uses it); a source event's row without a `fact_key`;
        `main` passing the control to the pre-flight; the history check
        for kernel methods only; the paths returned for every method;
        the barrier timeout and the session unit; a `--kernel-url` with
        a trailing slash; `run_settings`' pre-flight, and `main`
        handing it on;
      - the writers: an empty reply recorded as not suppressed; a
        replicated store's own tombstone file when `/memory/config`
        reports the kernel's;
      - the analysis: a revoke without a `revoke_path`; an unscored
        `writer_scoped` echo probe; an owner's revoke in the scrub
        criterion; `swept` and `retired` counting rows; the
        supersession reading leaving failed trials out; a target's
        listed rows.

    Corrected with it: the spec's Tests section (the forget's hold on
    later retrievals is tested with a stamped sequence; the selector's
    exclusion, with rows that carry both marks), the analysis's
    `library_criteria` docstring (only the deletion criterion counts a
    failed trial or an unscored probe against itself; it now says
    which conditions each criterion reads) and two tests' docstrings.
    In the code only tests and docstrings changed, and no recorded
    result changes. The mutants, their results and the reruns are in
    `repo-artifacts/AIOS/mutation15/`.

### Subtask 16

Graphiti (Zep's open-source temporal knowledge graph) as the third
backend, in all three loci; the Zep Cloud provider is retired. Design:
`GRAPHITI_BACKEND.md`; the native condition: `NATIVE_USAGE.md`,
"native_graphiti". Both were written and committed before any provider
code.

- **Setup** (2026-11-11). `graphiti-core==0.31.2` in both venvs (with
  `neo4j==6.4.1`; `certifi` 2026.10.23); Neo4j `5.26.33-community` in
  Docker (`aios-graphiti-neo4j`, digest `sha256:ec10d705…`, bolt on
  127.0.0.1:7687), credentials in `AIOS/.env`, telemetry off. The AIOS
  venv's `tenacity` went from 8.5.0 to 9.2.1, which `llama-index-core`
  0.10.19 declares it does not accept (`<9`); every name it imports from
  `tenacity` exists in 9.2.1.
- **Decisions from the user** (2026-11-11): Graphiti's extraction LLM is
  Azure gpt-4o, as Mem0's, and every call a write makes is a
  `backend_extraction` record of its trial; search is Graphiti's
  documented `search()`, unscored (`scored_search: false`) in every
  locus, with no reranker unless the native agents get the same; the
  benchmark measures the kernel's slot supersession, and Graphiti's own
  invalidations are recorded apart and credited to no locus.
- **Exploration** (five writes of one user, Azure gpt-4o, before the
  spec). As `text` episodes, first-person statements gave no fact; as
  `user:` messages, every write gave one or more. A restatement was
  merged onto an earlier fact and gave no fact of its own, so rows are
  per fact and write. Graphiti invalidated the newer of two
  contradicting facts ("moved to Mattermost last week" against "chat
  tool is Slack"). Deleting an episode left a fact another episode
  shared, with the deleted episode's sentence. 3.6 LLM calls and 6,656
  prompt tokens a write, 4 to 7 s. The deployment ignores
  `json_object` (API version 2024-02-15-preview): JSON is schema-guided.
  The usage logger counts synchronous LiteLLM calls only, so Graphiti's
  client calls `litellm.completion` in a worker thread with the trial's
  tag carried into Graphiti's event loop; the counts above came through
  that path.
- **Functional check, writes with no fact** (`f16b`, `f16c`). Graphiti
  sometimes extracted a write's entities but no fact (the statement in
  an entity's summary, no edge), and its `search()` returns facts
  only: 3 of 720 writes, 3 of 40 users, all in replicated at H = 2
  (two V5 raw-JSON payloads and one plain statement; each write gave a
  fact in another run). The extraction rule failed each trial and the
  cell twice. Decision from the user (2026-11-11): on Graphiti, whose
  extraction errors raise, such a write is a lost memory, recorded in
  `writes_without_fact`, and the trial is scored (BENCHMARK_V2.md
  Amendment 5; v1 and v2). The two failed attempts are in
  `repo-artifacts/Cerebrum/bench_v2_functional_graphiti_failed_cell*`.
- **Native Graphiti listed a V3 writer's rows by `owner_agent`**
  (`f16d`). V3 omits it, so in native at H = 2 one user's V3 task agent
  listed none of its six writes, which Amendment 5 then read as lost
  (Neo4j held every fact; before the amendment the trial would have
  failed). Its revokes would have found nothing. Fixed: the listing
  filters by `agent_id`, as native Mem0 and in-house do; and Amendment
  5 now covers only a write whose reply named no fact: a write whose
  reply named rows that its writer does not list fails the trial
  (`backend_rows_unlisted`). Every other write without a row named
  none. The two H = 2 agent cells were re-run (`f16e`).
- **Review (one pass, during the first pilot_v1 smoke launch).** Four
  findings, each verified in code and fixed with a test that fails
  without it; the smoke (`pg16`, started 19:37) was stopped at 20:01,
  in its first cell, so it runs on the fixed code:
  1. Native Graphiti's `search()` wrote its `num_results` into the
     shared recipe Graphiti's ingestion reads; a V4 consumer's k 5
     stayed for the next users' writes (native, H = 2: the functional
     check's `f16e` native H = 2 cell ran with it). The agents put the
     limit back after each call.
  2. The selector never deduped the own fetch: two claims of one
     Graphiti fact both reached the block (functional `no_delete`
     replicated: 12 extra rows in 10 of 30 probes). The exact-content
     dedupe now covers own rows; no Mem0 or in-house block of the
     Subtask 15 runs held two rows with one text.
  3. The Graphiti scrub's `DETACH DELETE` of an entity a form names
     deleted the facts attached to it unreported. They are now reported
     (`detached`; forget reason `entity`, or swept), so the harness
     counts them as removed and the analysis shows them.
  4. v1 kernel cost: the kernel's chat turn is written in the
     background, and `/memory/cost` waited only for calls in flight, so
     a Graphiti turn's later calls were lost (the 1-user v1 try: kernel
     17 and 12 backend calls, replicated 24 and 15). The read now waits
     on the user's write barrier first; the harness's read timeout
     (120 s) outlasts the barrier's (60 s). In v1 Mem0 kernel cells
     (Subtask 11) the same race could drop the turn's embedding calls.
  The functional check ran before these fixes; its criteria do not
  depend on them, and the two smokes run after.
- **Verification pass.** All six fixes since the review began verified
  (static). Two follow-ups, fixed with tests that fail without them:
  - Rows of one Graphiti fact came oldest claim first, so the dedupe
    kept the fact as first stated (its oldest session age); under
    `no_supersession` a restatement after a change lost its newer age.
    They now come newest claim first.
  - The pilot_v1 driver left the config's 5 s write barrier: the
    relaunched smoke (`pg16b`, 20:26) had 7 of its first 12 cost reads
    time out (the kernel's WARNING), so it was stopped at 20:40, in its
    first cell. The driver now sets 60 s, as the v2 driver does.
  Not changed: the harness does not record the cost read's
  `barrier_wait`; a timed-out read is in the kernel log, which the
  smoke's audit checks.
- **Functional check** (Cerebrum `results/bench_v2_functional_graphiti`,
  14 cells over three result folders, users 0 to 4, 70 user-trials, 0
  failed). Every criterion that applies to the Graphiti cells holds:
  deletion and privacy pass and fail in real conditions and fail under
  `no_delete` (15 of 15) and `no_visibility` (5 of 5); kernel and
  replicated delete completely at H = 0; `writer_scoped` fails 2 of 4
  echo users; no block holds a retired row at H = 0 and
  `no_supersession` puts one in 48 probes; the guard was armed and
  dropped nothing; every Graphiti forget scrubbed an episode; the cap
  binds. The others need the in-house, Mem0 or `no_memory` cells
  (Subtask 15's).
- **pilot_v1 smoke** (Cerebrum `results/pilot_v1_graphiti`, `pg16e`,
  qwen, H = 0 and 2, 180 user-trials, 0 failed). Kernel 3.90 / 4.17 /
  3.83 (profile / task / integration) at H = 0 and 3.20 / 3.40 / 2.77
  at H = 2; replicated 3.70 / 4.10 / 3.70 and 2.47 / 2.63 / 1.77;
  native 4.00 / 4.17 / 3.90 and 2.63 / 2.77 / 2.07. Kernel minus
  replicated: H = 0 profile +0.20 [-0.03, +0.43], integration +0.13
  [-0.12, +0.39]; H = 2 profile +0.73 [+0.23, +1.23], integration +1.00
  [+0.57, +1.43]. Kernel minus native: H = 0 -0.10 and -0.07, H = 2
  +0.57 [+0.03, +1.10] and +0.70 [+0.20, +1.20]. Both readings (the
  H = 0 tie, an H = 2 gap in Subtask 11's direction) hold for both
  contrasts; reported, not required.
- **A V2 agent's backend calls were not counted in v1** (Cerebrum
  `a836d69`, with a test that fails without it). A V2 agent tags its
  calls with its rewritten user id, and the v1 agent-managed trial read
  only the assistant's id (v2's harness reads every id, Amendment 2).
  The pilot_v1 smoke's H = 2 agent cells recorded 338 of 393
  (replicated) and 394 of 439 (native) logged calls, exactly their 12
  V2 trials; not re-run, reported as lower bounds (`v2_trials` in its
  cost table). The same holds for `pilot_v1_hetero`'s H = 1 and H = 2
  Mem0 agent cells (Subtask 11): their V2 trials record 1.5 to 1.75
  backend calls against 3 for the others. No report gave agent-locus
  backend cost at H > 0. The kernel reads usage under canonical ids
  and is unaffected.
- **Benchmark v2 smoke** (Cerebrum `results/bench_v2_smoke_graphiti`,
  `s16`, pilot_v2, H = 0, 90 user-trials, 0 failed; beside
  `bench_v2_smoke_a4`). Kernel and replicated pass every judge-free
  probe (30 of 30 each for deletion, privacy, recall, recency and
  contradiction) and agree on all 150 pairs; Amendment 4's criteria that
  need no control hold; no write gave no fact. Native: deletion 23 of
  30 (7 echoes), recall 30, recency 11, contradiction 13; in 32 of its
  36 recency and contradiction failures the stale fact was one Graphiti
  had marked invalid, which `search()` returns. Integration is low in
  every Graphiti cell: 2.20 kernel, 1.97 replicated, 2.00 native,
  against 2.87 in-house and 3.57 to 3.60 Mem0. Graphiti splits the base
  profile into 3 to 5 facts (about 23 facts per user), the cap (10)
  binds in every probe and the budget in none, and the integration
  block held 37% of the profile's values (100% in-house, about 80%
  Mem0). Graphiti marked invalid 52 of the kernel's 60 retired rows,
  and 1 to 3 latest statements per cell.
- **Cost and latency** (`GRAPHITI_BACKEND.md`, "Measured in the
  smokes"): Graphiti makes about 4 backend calls a v2 write and 6 a v1
  write, against Mem0's 1; per v2 user $0.41 to 0.43 against $0.36,
  and 182 to 191 s against 95 to 102 s (in-house 73 to 77 s);
  `add_episode` 6.3 to 6.5 s a write (median). Every trial's recorded
  calls match its logs, the pilot_v1 H = 2 agent cells' V2 trials
  excepted (above).
- **Native Graphiti's evidence**: `NATIVE_USAGE.md`, "Evidence: native
  Graphiti's search as returned" (order, no score, no score filtering,
  invalidated facts included).
- **Zep retired.** `aios/memory/providers/zep.py` and
  `test_zep_provider.py` are deleted; the factory offers `in-house`,
  `in-memory`, `mem0` and `graphiti`. Known issues 4 and 11 (Zep's
  contract gaps) are closed with it.
- **Mutation run** (rule 6, once, on the final code: AIOS `2bbf567`,
  Cerebrum `3a6bf98`). Five module owners (the AIOS Graphiti provider;
  the AIOS selector, deletion, manager, launch and drivers; Cerebrum's
  Graphiti clients and native and replicated agents; its harness; its
  analysis tools) wrote 200 mutants of rules the documents state and
  ran each on a scratch copy against their area's tests, with the
  local Neo4j and Ollama, behind a loopback-only network guard; 96
  were killed. Each survivor was then rerun against the full suite of
  every repo whose tests load its file (the AIOS library's and
  `cerebrum/`'s: both). Of the 104:
  - 9 are killed by AIOS tests: Graphiti's LLM and embedder clients,
    shared from `cerebrum/utils/graphiti.py`, are tested only in AIOS
    (`test_graphiti_cost.py`, the group id in
    `test_graphiti_provider.py`).
  - 5 are equivalent: an edge marked expired is also marked invalid in
    `graphiti-core` 0.31.2; `add_episode` returns invalidated edges
    only beside resolved ones; `run_coroutine_threadsafe` carries the
    caller's usage tag already; nothing calls the cross-encoder; the
    factory's embedder defaults equal `memory.embedding`'s.
  - 23 could change a reported number, and the records cannot show
    the rule held; each now fails a test (AIOS `789eb67`, Cerebrum
    `6a29089`): the analysis reading the `kgra`, `kgra_ns` and
    `agent_gra` cells as Graphiti and pairing kernel with replicated
    on it (the smoke's 150 agreeing pairs), the Graphiti scrub
    criterion at H = 0 only (the functional check's 10 forgets would
    read 20); the
    pilot_v1 report's cell paths, `latency_s` in seconds, the pilot
    reference of the same model and contrast, and its gap columns;
    Graphiti's own marks kept out of `retired_in_block` and
    `retired_rows` (the smoke's replicated 0 would read 5, native's 0
    marked rows 53); native Graphiti's UTC reference time, its order
    for dated facts, the first visible episode's metadata, and the
    assistant's own search passing its name; the selector's
    exact-content dedupe; the provider's update split and
    re-embedding, the scrub blanking a deleted row's episode, counting
    an entity once and matching forms as the scorer does (the
    `messages` and `history` counts), a conversation turn as its two
    messages (pilot_v1's 33 and 32 turns with no fact), and an episode
    dated by its note.
  - 67 hold in the code (their owners checked each) but no test of
    either repo pins them, so this file claims no more. None changes a
    reported number: the condition never arises in the runs, nothing
    reported reads it, a broken rule would fail the trial or the run,
    or the records show it held:
    - the provider: an episode's id for a write with no fact (the
      Amendment 5 writes were scored as lost); the search limit (shared
      fetches above Graphiti's default 10 in 736 of 840 kernel and
      replicated fetches) and the cut at k (never over k); invalidated
      facts kept in search (5 replicated blocks held one); a row's
      changes merged, not replaced; a fact-less blank episode deleted;
      `backend_versions` (every cell recorded them); the group lock; a
      read outside the user's group; `graphiti_invalid_at` and
      `graphiti_expired_at` read from their own fields (all 214
      recorded invalidated rows carry both);
    - the kernel: a scrub-detached row of the writing note counted as
      gone (no forget detached a fact); `/memory/cost` canonicalizing
      before it waits (every run's ids are canonical); the Graphiti
      kernel's injector (its blocks held rows);
    - the drivers: `run_bench_v2.sh`'s `_ns` phases' methods and
      checks, extraction off, agent-phase memory off and the provider
      check; `run_pilot_v1_graphiti.sh`'s native cells, levels,
      extraction on, `--schedule`, `--kernel-commit`, `--strict`, the
      clean-repo and provider checks, the memory-ops check over every
      log, and the config restore (each cell records both commits, the
      schedule's hash, 0 failed trials and its stored turns; the
      functional check ran every `_ns` cell it reports);
    - the harness: embedding tokens of a V2 agent's id (no report gives
      embedding cost); a v1 kernel trial's backend (no v1 kernel writer
      stored no fact); `native_graphiti` and `replicated_graphiti`
      dispatched to Graphiti in v1 (17.7 to 19.3 backend calls a trial,
      Mem0's 3); a v2 Graphiti trial with no backend call failing; the
      two conditions' membership (the CLI would refuse them);
      `heterogeneity_report.py` on Graphiti cells (no report runs it on
      them);
    - the agents: one shared client; the episode name; the native
      search's group (the partition dropped nothing in 390 native
      fetches), `num_results` (never over k), the unscored row under a
      threshold (`after_threshold` equals `after_visibility`, the V4
      consumers' included) and the tagging of `remove_episode` (every
      trial's calls match its logs); the search's embedding tag (no
      report gives embedding cost); `agent_id` on native v2 rows and
      the rows a write names (a trial would fail); recorded
      `invalid_at` and `expired_at` values (the counts read either);
      the conversation rows' `agent_id`; the group lock; replicated
      Graphiti's backend (a run would fail);
    - the analysis: the Graphiti scrub criterion over no forgets,
      failed trials or owner revokes, `same_writer` with `entity`
      deletions, an unscored probe on a lost write (none in the runs);
      the forget note's `entity` clause; `backend_usd` against
      `total_usd` (equal in every committed cell); `same_direction`
      over every scope (each pilot scope has one sign); the cost CSV
      (not committed).

    The mutants, their results and the reruns are in
    `repo-artifacts/AIOS/mutation16/` (one replay log, which had
    captured the Azure key in a LiteLLM traceback, redacted; the
    network guard had blocked the call). One test is flaky under load
    (known issue 47).

### Subtask 17

A-MEM (agentic notes) as the fourth backend, in all three loci, after
three decisions on the Graphiti smoke's findings. Design:
`AMEM_BACKEND.md`; the native condition: `NATIVE_USAGE.md`,
"native_amem". Both were committed before any provider code.

- **Decisions from the user** (2026-11-12):
  1. **The budget limits the v2 block.** Kernel and replicated run
     k 30 with the 300-token budget; native consumers keep k 10
     (`BENCHMARK_V2.md`, Amendment 6; AIOS `1c575bd`, Cerebrum
     `7f554d2`). The six kernel and replicated smoke cells were re-run.
  2. **Native Graphiti uses only the facts it holds true now**, through
     `search()`'s own `invalid_at` filter: our reading of Graphiti's
     documented intent, quoted with its README line in
     `NATIVE_USAGE.md` ("Validity"; Cerebrum `e2d4b1f`, AIOS `649b78d`,
     `612c989`). Native Graphiti was re-run in v2 and in pilot_v1.
  3. **No key value in logs or test reports** (AIOS `2c671bd`, Cerebrum
     `2b9a776`): log records and pytest reports redacted. Extended
     below.
- **Re-verification** (`s17`, `results/bench_v2_smoke_s17`; `pg17n`,
  `results/pilot_v1_graphiti_native_filter`; both at Cerebrum
  `2b9a776`, AIOS `612c989`). Results in `BENCHMARK_V2.md`,
  Amendment 7, and `NATIVE_USAGE.md` ("With the filter"):
  - The budget bound in 96 to 180 of each kernel and replicated cell's
    180 probes, the cap in 6 (all replicated Graphiti); blocks held
    11.6 to 11.8 rows in-house and on Mem0 and 17.3 to 17.5 on Graphiti
    (10 at k = 10). Judge-free pass rates as at k = 10 but for recency
    on Mem0 (kernel 22 to 23, replicated 23 to 21 of 30) and one
    kernel Graphiti recency probe. Integration, paired: in-house −0.30
    and −0.27, Mem0 −0.17 and −0.03, Graphiti +0.30 and +0.20 (kernel
    and replicated); no 95% interval excludes 0. In-house kernel and
    replicated blocks are identical in all 180 paired probes.
  - Native Graphiti with the filter: recency 30 and contradiction 26 of
    30 (11 and 13 before), no invalidated fact in any block (132 of 180
    before). In pilot_v1 Graphiti invalidated no fact in any trial, so
    the filter removed nothing; the re-run moved the native scores by
    −0.17 to −0.03 (intervals hold 0), and the kernel − native readings
    hold (H = 0 tie, H = 2 gap in the pilot's direction).
  - Stopped by the user on 2026-11-12 at 16:03 (the laptop was to shut)
    in the Mem0 replicated cell, after the in-house and Mem0 kernel
    cells; resumed at 21:12 as `s17b` (a new prefix, known issue 36),
    which kept the two finished cells and re-ran the interrupted one
    whole (its first log kept as
    `logs/qwen_agent_replicated_mem0_h0.killed_s17.log`).
  - Every recorded backend call matches the logs one for one (534 per
    Mem0 cell; 2,195, 2,187 and 2,215 on Graphiti; 541 and 411 in
    pilot_v1); no traceback, ERROR record or barrier TIMEOUT in any
    log; no writer failure or retry.
  - Time per user did not measure k: the in-house and Mem0 kernel cells
    took 99 and 133 s against 77 and 95 because Qwen generated about
    1.3 and 1.6 times slower that afternoon (known issue 48). k 30
    itself costs about 0.03 s of injection and 40 prompt tokens a probe
    (116 to 118 on Graphiti), and no backend cost.
- **Key hygiene** (the user's follow-up, 2026-11-12; AIOS `ca8d307`,
  Cerebrum `e8af5e8`):
  - **History.** No commit of any branch or tag of either repo, and no
    tracked file, holds the Azure key, the Neo4j password or the
    retired Zep key, nor any 8 consecutive characters of the first two
    (`git log --all -S`, and `git grep` over every revision).
  - **Fragments.** Decision 3 matched whole values only, but key
    material leaves in pieces: LiteLLM 1.83.0 logs the Azure key's
    first 8 characters at DEBUG (`llms/azure/common_utils.py:617-623`),
    and pytest shortens a long value (a local's repr at 240 characters,
    an assertion's operands as "head...tail": 25 of a synthetic key's 31
    characters reached the terminal and the JUnit XML through the
    committed filter). `redact_text` (both repos' `redact.py`, one rule)
    now also replaces any 8 consecutive characters of a secret of 20 or
    more, and a head or tail of 4 to 7 beside a mask (`**`, `...`, `…`).
    No ordinary text of the 2.4 GB of archives, results and local logs
    matches it.
  - **Every sink.** The kernel and the harness redact log records (and
    their tracebacks) and the standard streams (`print`, uncaught
    exceptions of every thread, tracebacks written to stderr); both
    suites' `conftest.py` load the report hooks for tests and for
    collection errors. Tests leak a synthetic key in a raised exception
    through each sink (a process's log, a test's terminal report and
    JUnit XML, an unmocked LiteLLM call, a collection error, LiteLLM's
    own debug line) and fail with the redaction off.
  - **Archive.** `scripts/archive_artifacts.py` copies into
    `repo-artifacts` only when no file (compressed ones read through)
    holds a configured key or a fragment of one, and copies nothing
    otherwise (rule 7). The drivers' `ARCHIVE` runs it on the whole
    OUTROOT at the end. A one-off `--check` of all of `repo-artifacts`
    (1,256 files) found nothing.
  - **Local logs** (known issue 49): the only matches anywhere are 118
    of LiteLLM's 8-character heads in 39 gitignored logs of the other
    branch's runs.
- **Reporting** (no behavior change): every v2 analysis table ends with
  `block_tokens` and `block_rows` (per locus in the contrast table;
  Cerebrum `f74b1b9`); the full grid adds a native k = 30 cell on
  Graphiti (Amendment 7).
- **A-MEM: decisions from the user** (2026-11-12): pin WujiangXu/A-mem-sys
  at `f303dfc`, not agiresearch/A-mem, whose `add_note` generates no
  attributes and whose evolution's links never resolve (the
  exploration, `AMEM_BACKEND.md`, "Which A-MEM"); A-MEM's `search()` in
  every locus (the README's first search; first decided as
  `search_agentic`, which returns the same notes, then changed the same
  day).
- **A-MEM: spec before code** (AIOS `2bd7b2e`): `AMEM_BACKEND.md`,
  `NATIVE_USAGE.md` ("native_amem"), `BENCHMARK_V2.md` Amendment 8, the
  A-MEM entry of `PROVIDER_CONTRACT.md`. Before its commit, a fact check
  of its store sections against the pinned source found four errors (the
  Chroma client, the native stores' collection names, the writes per
  user, when a Chroma copy is rewritten), and a check of the exploration
  two more (the repeat run's search differed from its third hit on;
  "Slack" was absent from both runs' residue); all were corrected.
- **A-MEM: install.** `agentic-memory` 0.0.1 at `f303dfc`, `--no-deps`,
  in both venvs; beside it the packages a venv lacked, pip choosing
  versions that change nothing installed: AIOS `rank-bm25` 0.2.2;
  Cerebrum `rank-bm25` 0.2.2, `nltk` 3.9.4, `sentence-transformers`
  6.3.0, `transformers` 5.17.0, `torch` 2.15.0 and their new
  dependencies `mpmath` 1.3.0, `networkx` 3.6.1, `safetensors` 0.8.0,
  `sympy` 1.14.0. Cerebrum pins them in `requirements-amem.txt`, not in
  `requirements.txt`, the SDK package's dependency list: with the git
  reference there, `pip install ../Cerebrum` failed (hatch refuses a
  direct reference, and a published package could not carry one), and
  a test now keeps it out. A-MEM's own sentence-transformers model is
  never loaded.
- **A-MEM: provider and agents.** `AMemProvider` (`provider: amem`) and
  the native and replicated agents build their stores with
  `cerebrum/utils/amem.py`: one `AgenticMemorySystem` per user in a
  Chroma `PersistentClient` of the stores' own, A-MEM's default
  retriever and controller bypassed during construction; a controller
  calling the pinned `memory.backend_llm` through the synchronous
  `litellm.completion` (temperature 0, seed), so each call is a
  `backend_extraction` record of the trial; the pinned Ollama embedder.
  Metadata in the note's `category`; `search()` scored `1 - d/2`; the
  forget's scrub deletes carriers by derived text (reason `derived`,
  `pipeline/deletion.py`); each write logs the notes its evolution
  changed. The drivers' A-MEM phases (`kamem`, `agent_amem`, `_ns`) and
  `scripts/run_pilot_v1_amem.sh`; the analysis's A-MEM cells and
  `derived` column; `PERSONALIZATION_PROVIDERS` must name every factory
  provider but `in-memory` (a test).
- **A-MEM: functional check** (`f17`, Cerebrum
  `results/bench_v2_functional_amem`, 14 cells, users 0 to 4, 70
  user-trials, 0 failed; Cerebrum `56f0573`, AIOS `13708ee`). Every
  criterion that applies to the A-MEM cells holds: deletion and privacy
  pass and fail in real conditions and fail under `no_delete` (15 of 15)
  and `no_visibility` (5 of 5); no kernel privacy probe leaks (25); the
  budget binds in every kernel and replicated cell, the cap in none;
  kernel and replicated delete completely at H = 0 (10 forgets; no
  stored row's content holds a revoked value: the runs do not read
  A-MEM's derived text); `writer_scoped` fails 4 of 4 echo users; no block
  holds a retired row at H = 0 and `no_supersession` puts one in 59
  probes; the guard was armed and dropped nothing. The others need the
  in-house, Mem0 or `no_memory` cells (Subtask 15's), and A-MEM keeps
  no messages to scrub (Amendment 8).
  - Kernel and replicated pass all 25 judge-free probes at H = 0 and
    agree on every pair. At H = 2 each locus's judge-free results equal
    in-house's and Graphiti's probe for probe (kernel recency and
    contradiction 4 of 5; replicated recall 4, recency and
    contradiction 3; native privacy and recall 4, recency 2,
    contradiction 1): they come from the H = 2 agents, not the backend
    (one native consumer fetches nothing at H = 2 on every backend).
    Native at H = 0: deletion 3 of 5 (2 echoes), recency 4,
    contradiction 2, as native A-MEM keeps every statement.
  - Each kernel cell's 5 forgets deleted 8 rows, one of them a note
    whose derived text alone carried the value (`derived`); the
    replicated H = 0 cell's 7 held none.
  - Every write logged one `A-MEM evolved` line (1,260 of 1,260, all
    three loci); a write's evolution changed 1.12 to 1.70 existing
    notes on average per cell, at most 5 (A-MEM's neighbours); no
    A-MEM failure line. 1.94 backend calls per write (a store's first
    note has no evolution call), about 670 prompt tokens a call, $0.10
    a user; 112 to 132 s a user at 49 to 57 ms per token.
- **iCloud's copies split the functional check's library version**
  (fixed in AIOS `34833e7`). Its `kamem` cells record
  `PIPELINE_VERSION` `565e7d5b…`, the later cells `138e9bd8…`, for the
  same code: the second hash includes iCloud's untracked conflict copy
  `aios/memory/pipeline/deletion 2.py`, which no import loads; the
  `kamem` kernel (15:59) hashed the package without it, every process
  from 16:40 on with it. iCloud writes such copies (`<name> 2.<ext>`)
  beside files changed in two places, 13 in AIOS and 11 in Cerebrum
  now. The hash now leaves out every `.py` whose name is not a module
  name. pytest collected the test files' copies the same way: in the
  first suite run on the review's fixes, a stale copy of
  `test_bench_v2_analysis.py` (53 tests) failed as a new failure. Both
  `tests/conftest.py` now leave them out (`test_icloud_copies.py`;
  Cerebrum `1d7d99f`). Of the earlier totals, AIOS's 743 + 7 is exactly
  `13708ee`'s 750 tests; Cerebrum's 1,190 held 7 tests beyond
  `56f0573`'s 1,183, from untracked files. The copies are kept (nothing
  that discards files).
- **A test left its copies of three modules in `sys.modules`** (fixed
  in AIOS `34833e7`). `test_mem0_provider_shared_metadata.py` loads its
  own `aios.memory.providers.base`, `mem0` and `visibility` at
  collection and left them registered, so a later test importing
  `ProviderError` at call time got the copy's class while `amem.py`
  raised the real one: the review's failed-write test failed in the
  full suite only. The file now puts back what `sys.modules` held.
- **Review** (one pass over AIOS `612c989..13708ee` and Cerebrum
  `2b9a776..56f0573`, 11 findings; fixed in AIOS `34833e7` and Cerebrum
  `1d7d99f`, each fix with a test that fails without it). No number the
  functional check reports changes; `bench_v2_smoke_s17`'s analysis was
  regenerated for finding 8's label (Cerebrum `f6d2646`; no number
  changed).
  1. config.yaml keeps provider keys under `api_keys.<provider>`, which
     the key rule did not match (all empty today, so no key was
     missed): both `redact.py` take every string directly under
     `api_keys` as a secret, and the printed config hides them.
  2. A V4 consumer at H = 2 applies its 0.5 threshold to native A-MEM's
     distance, keeping farther notes: documented (`NATIVE_USAGE.md`,
     "native_amem"; `AMEM_BACKEND.md`, "Search"), as on native Mem0. It
     can lower native A-MEM's H = 2 scores.
  3. A-MEM catches its LLM failures and stores the note without
     attributes: claim weakened; the runs count A-MEM's failure lines
     (none in `f17`).
  4. Kernel rows carried A-MEM's derived text (keywords, context,
     tags), which evolution writes from the user's other notes, another
     agent's private ones included: a path past the visibility rule.
     Rows now carry only `amem_note_id` and `amem_links`.
  5. The scrub's tags branch was untested, and `json.dumps` escaped
     non-ASCII forms, so a tag "Zürich" was missed: fixed (tested with
     "Utrecht" and "Zürich").
  6. No A-MEM run measures the store's completeness after a forget
     (the audit reads content): claim weakened.
  7. "Notes changed per write" had no code and two log lines per
     write: the docs name the store helper's line, counted from the
     logs (one per write in every locus).
  8. The block columns of split readings were cell means labelled as
     the row's probes: relabelled.
  9. `_RedactingStream` deadlocked on a write from inside a write and
     could hang at exit: a re-entrant lock, a bounded wait while the
     interpreter finalizes (no test exercises it), `writelines` (both
     repos).
  10. A failed write left a note A-MEM listed but Chroma did not hold:
      removed on failure, under the user's lock. The provider's add
      only: a failed update's re-add, a failed write's evolution edits
      and native writes are not cleaned up (`AMEM_BACKEND.md`, "One
      note per write").
  11. Citations (Amendment 8), a Cerebrum-side pin test, doc wording.
- **Verification** (one pass over AIOS `34833e7` and Cerebrum
  `1d7d99f`, the 11 findings and the two fixes found with the
  functional check): 9 fixed, 4 fixed with a gap, now narrowed in the
  docs (6: the runs read content only; 9 and 10 above; 8 below). One
  error, from finding 8's fix: the block columns' label was wrong for
  the pass matrix's echo rows (their split's mean) and the integration
  table (its integration probes). Relabelled per table (Cerebrum
  `a83cf8e`, AIOS `f313180`) and checked mechanically instead of by
  a third pass: all 607 rows of the two reports match the label,
  recomputed from the trials, and the old label's rule misses 49; no
  number changed. Documented, not changed: the scrub reads tags and
  keywords as one text, so a value split over adjacent tags counts as
  carried; the live risk check tests its two ASCII forget values by
  substring; the docs now list "Error in find_related_memories" among
  the A-MEM failure lines (the counts included it); any string directly
  under `api_keys` counts as a secret (known issue 50).
- **A-MEM: pilot_v1 smoke** (Cerebrum `results/pilot_v1_amem`, `pa17`,
  qwen, H = 0 and 2, 180 user-trials, 0 failed; Cerebrum `f6d2646`,
  AIOS `a145a26`). Kernel 3.07 / 5.00 / 3.07 (profile / task /
  integration) at H = 0 and 3.10 / 4.10 / 2.67 at H = 2; replicated
  3.07 / 5.00 / 3.07 and 2.43 / 2.97 / 1.97; native 3.13 / 4.93 / 3.20
  and 2.60 / 3.27 / 2.17. Kernel minus replicated: H = 0 profile +0.00
  [-0.26, +0.26], integration +0.00 [-0.24, +0.24]; H = 2 profile
  +0.67 [+0.11, +1.22], integration +0.70 [+0.26, +1.14]. Kernel minus
  native: H = 0 -0.07 [-0.49, +0.36] and -0.13 [-0.48, +0.22], H = 2
  +0.50 [-0.08, +1.08] and +0.50 [+0.00, +1.00]. Both readings (the
  H = 0 tie, an H = 2 gap in Subtask 11's direction) hold for both
  contrasts; reported, not required.
  - A-MEM stores each write verbatim, as in-house does, and with 3 notes
    a user and k 10 every note is in the block. The answers equal
    in-house's (Subtask 11, `pilot_v1_hetero`), trial for trial, in all
    30 kernel and 30 replicated trials at H = 0 (30 and 28 at H = 2;
    native 24 and 23); the kernel and replicated cell means are within
    0.07 of in-house's, native's within 0.30.
  - The judge on identical answers (known issue 24): over the 165
    trials whose answer equals in-house's, judged a week apart with the
    same prompt, seed and temperature, the same profile score in 75.8%,
    task 98.8%, integration 83.6%; mean differences within 0.03.
  - Calls: 5 a user (3 notes, each one analysis call, and an evolution
    call for all but a store's first note), $0.012 to $0.014 a user
    (Graphiti's pilot: 15.7 to 19.3 calls, $0.085 to $0.10, its
    lower-bound H = 2 agent rows aside); every cell's records match its
    logs. At H = 2 each agent cell's 12 V2 trials made 4: the V2 agent's
    note opened a second store for the user. The harness counts those
    calls since Cerebrum `a836d69`, so these rows are complete.
  - Time: a kernel write took a median 3.05 s (1.03 s for a store's
    first note, one call; 3.0 to 3.7 s with evolution; longest 10.8 s);
    34 to 42 s a user per cell, at 43 to 48 ms per Qwen completion
    token (Graphiti's pilot: 50 to 65 s at 44 to 63 ms).
  - Notes changed: an evolution call changed 0.73 to 0.88 existing
    notes per cell on average, at most 2 (a user has at most 2 earlier
    notes); no A-MEM failure line.
- **A-MEM: benchmark v2 smoke** (Cerebrum `results/bench_v2_smoke_amem`,
  `s17a`, qwen, H = 0, 90 user-trials, 0 failed; Cerebrum `f6d2646`,
  AIOS `a145a26`), beside `bench_v2_smoke_s17`'s k = 30 cells (same
  users and inputs). Kernel and replicated pass all 150 judge-free
  probes each and agree on every pair. Native: deletion 20 of 30 (each
  failure an echo, and all 10 kept echoes reached the block), privacy
  and recall 30, recency and contradiction 17 (an earlier statement's
  row in 170 of 180 blocks; native Graphiti with its filter: 30 and 26,
  27 blocks). Integration: kernel 2.57 [2.20, 2.93], replicated 2.63
  [2.22, 3.04], native 2.73 [2.32, 3.15] (s17: in-house 2.57 and 2.60,
  Mem0 3.40 and 3.57, Graphiti 2.50, 2.17 and 2.07). The budget bound in
  156 of 180 kernel and replicated probes (in-house's 156), the cap in
  none.
  - The runs' first `derived` deletion: the kernel's forget of user 2's
    `conference` also deleted the user's base task context, whose
    derived text A-MEM's evolution had made carry the value, so that
    user's integration block held no base task row (the replicated and
    native blocks did; the probe scored 2 in all three cells). The
    replicated store's evolution had not carried the value there.
  - Ranked, not stored, differently from in-house: A-MEM keeps each
    write verbatim, but its blocks hold the same writes as in-house's
    in 67 of 180 probes per locus, and the kernel's and the replicated
    store's blocks the same writes in 106 (A-MEM's LLM text enters each
    note's embedding). The judge-free results and the integration means
    are in-house's.
  - Calls: 34.6 a user, 1.94 a write (1,038 per cell; each cell's logs
    hold exactly twice its recorded count), about 23,200 prompt tokens,
    $0.10 a user (s17: Graphiti 72.9 to 73.8 calls, $0.42; Mem0 17.8,
    $0.36).
  - Time: a kernel write took a median 3.33 s (p90 3.94 s, longest
    16.3 s), about 60 s of each user's time; 118 to 123 s a user at 52
    to 54 ms per Qwen completion token (Graphiti at k = 30: 179 to
    187 s at 49 to 52 ms).
  - Notes changed: 1.39 to 1.46 per write on average per cell, 1.47 to
    1.54 per evolution call, at most 5. One A-MEM failure line, native:
    "Error in memory evolution: 'tags_to_update'", an evolution reply
    without that key; the note was stored, its evolution changed
    nothing, and the trial passed its judge-free probes.
  - No traceback, WARNING record or barrier TIMEOUT in any log; no
    writer failure or retry; no write without a note.
- **Mutation run** (rule 6, once, on the final code: AIOS `1492954`,
  Cerebrum `28fe584`). Five module owners (the AIOS A-MEM provider and
  library; the AIOS key hygiene, archive and drivers; Cerebrum's A-MEM
  clients and native and replicated agents; its analysis tools; its
  redaction and collection hook) wrote 240 mutants of rules the
  documents state and ran each on a scratch copy against their area's
  tests, with Ollama, behind a loopback-only network guard; 115 were
  killed. Each survivor was then rerun against the full suite of every
  repo whose tests load its file (the AIOS library's and
  `cerebrum/utils/amem.py`: both), and native Graphiti's three, whose
  tests skip in a copy without Neo4j's password, with the local Neo4j.
  Of the 125:
  - 5 are killed by those reruns: the stores' `has` by an AIOS test
    (`test_amem_provider.py`); native Graphiti's `invalid_at` filter
    (Decision 2) by `test_native_graphiti.py`; and a second install of
    Cerebrum's redaction keeping the old values, only through the
    session's order (`test_benchmark_metrics.py` runs
    `run_evaluation.main()`, which installs it).
  - 2 are equivalent: a note in a user's store always names that user
    (the stores are per user, by digest); building a replicated
    provider's stores installs the usage logger before any A-MEM call.
  - 53 now fail a test (AIOS `6333719`, Cerebrum `062d12c`), each
    checked against its mutant on a clean copy: those that could change
    a reported number or a committed report's text where the records
    cannot show the rule held, and the few the same tests catch with
    them (A-MEM's `scored_search` and `versions`, fence stripping, the
    archive reading `config.yaml`, the pilot archive's SHA256SUMS):
    - the A-MEM provider: providers of one configuration share the
      stores (every replicated A-MEM number); `synchronous_commit`
      false (pilot_v1's kernel cost reads wait for the background
      turn), `backend_extraction` (Amendment 8's checks), its
      capabilities and `versions`; its log line worded apart from the
      helper's counted one (the notes-changed counts); the scrub
      reading the stale Chroma copy (its test had passed without it:
      the note's keywords still held the value) and tags joined by
      spaces; a `derived` deletion's owner; a failed search raising,
      through `search`, not `search_agentic` (which returns [] on an
      error); A-MEM's time format, which its evolution prompt shows;
      the factory's A-MEM config;
    - A-MEM's clients and agents: the pinned model's LiteLLM route,
      temperature 0 whatever A-MEM asks, the seed, `response_format`,
      A-MEM's system message, fences stripped, and the usage logger (a
      native process installs it nowhere else); one set of stores per
      configuration and namespace; the pinned embedder (not Chroma's
      default) and consolidation every 100 evolutions; the
      notes-changed count (changed notes only, tags alone included)
      and its INFO line; collection names keeping the id's digest
      (pilot_v1's V2 agents opened stores of their own); replicated
      A-MEM on the A-MEM provider (on in-house's its cells would run
      with in-house's numbers, and nothing would fail); native A-MEM's
      time format; a V4 native consumer's own k (pilot_v1's H = 2
      native cells, `pg17n`'s included);
    - the analysis: the integration readings' block columns over the
      integration probes (every `integration_blocks` and
      `integration_base_rows` row of the three v2 reports), a deletion
      row split by echo over its split's probes (28 of f17's 98 rows),
      `identical blocks` over all probes, A-MEM in the contrast (f17's
      and s17a's A-MEM rows), the contrast table's per-locus block
      columns, the note naming the integration probes, no Graphiti
      scrub criterion and no Mem0 scrub count from A-MEM cells (f17's
      13 criteria and "0 of 0 forgets"), and `derived` kept out of
      `same_writer` (its test had passed under any rule: the fixture
      put the writer on the event, which `_events` overwrites with the
      session's); the pilot report's `--backend amem` (without it
      `pilot_v1_amem`'s gaps and readings are empty);
    - the drivers and the archive: `run_pilot_v1_amem.sh` setting
      `BACKEND=amem` (the pilot ran through it); the pilot driver's
      archive copying the whole OUTROOT with SHA256SUMS (pa17's 15
      files); a key kept only in the checkout's `.env` or `config.yaml`
      looked for (the drivers source `.env` only into the harness's
      subshell); a head or tail under 4 characters beside a mask not
      key material; a `test_x 3.py` copy not collected (the suite
      counts).
  - 65 hold in the code (their owners checked each) but no test of
    either repo pins them, so this file claims no more. None changes a
    reported number: the condition never arises in the runs, a broken
    rule would fail the trial, the run or the kernel's start, or the
    records show it held:
    - the A-MEM provider: a failed write's Chroma copy deleted (only
      consolidation, every 100 evolutions, fails after the Chroma
      add); the per-user lock (memory syscalls are serial); launch's
      redaction import (the kernel would fail at import); the
      package's re-export (nothing imports it from there);
      `PIPELINE_VERSION` leaving out every non-module name (no such
      file);
    - A-MEM's clients and agents: native v2 rows' `agent_id` (every
      native v2 trial would fail); embedding counts (no report gives
      embedding cost); the stores' and native search's locks (one call
      at a time per user); native stores apart from the provider's
      (cells run in separate processes); Chroma's telemetry; the
      cleanup at exit (the run's mutant left 35 `aios_amem_*` stores
      in the system's temporary directory); consolidation's delete
      (never reached); the 768-dimension check (the pinned model's
      vectors are 768); the default temperature (every config sets 0);
      the conversation
      row's `agent_id` (v2 probes store nothing); listing in write
      order (revokes and audits do not depend on it);
    - the drivers' guards: the agent phases' memory-ops check reading
      the backend's logs, the `_ns` zero-ops list and `--provider` on
      the kernel phases (every agent-phase kernel log of f17, pa17 and
      s17a holds thousands of lines and no memory operation; every
      A-MEM kernel cell recorded `provider: amem`); an existing ARCHIVE
      stopping the pilot driver before the run (the archive refuses
      the copy at the end);
    - the archive, the redaction and collection (17 in AIOS, 23 in
      Cerebrum): secret names beyond the tested ones; values of exactly
      8, or 20 to 24, characters; keys in config lists; the fragment
      rule's edges (8-character runs away from a mask, the last 8, `**`,
      `...` and `…`, 7-character ends, a masked tail without its head,
      repeated values and fragments); two reads' overlap; compressed
      files other than gzip, and a zip's later members; `exc_info`
      dropped; a record whose arguments do not fit; values replaced
      longest first; the stream lock, partial lines and the bounded
      wait at exit; the report hooks' reads of the environment, `.env`
      and `config.yaml`; Cerebrum's hook leaving out every non-module
      name (its 10 such names hold a space). The six Subtask 17
      archives' 54 logs hold no `<redacted>` marker and no traceback,
      so the redaction replaced nothing in them and no archive
      refused; `repo-artifacts` holds no compressed file;
    - the analysis: `_block_size`'s None for no probe (no report has an
      empty set), the limit criterion with no cell (f17 has them), the
      v2 pipeline's A-MEM backend check (a run would fail).

  Three kills are conditional: the redaction install above; the
  environment default of `secret_values`, killed only when the
  environment holds a secret-named variable; and an A-MEM store
  mutant killed only in the full run, by an earlier test's Chroma
  client. A first rerun of the new tests read a restored module from
  its stale bytecode (a mutant restored within the second at the same
  size); the reruns delete the caches and write none. The mutants,
  their results and the reruns are in `repo-artifacts/AIOS/mutation17/`
  (without the repos' copies).
- **Suites** at AIOS `34833e7` and Cerebrum `1d7d99f`: AIOS 754 passed
  and the 7 known errors (761 collected; 750 at `13708ee`, so the 11
  new tests); Cerebrum 1,162 passed, 4 skipped, the 19 known failures
  and 2 errors by name, and `test_summary_props.py`'s
  `test_delta_equals_arithmetic_difference` on Hypothesis's deadline
  (273.65 ms against 200; alone it passed 3 of 3; known issue 35);
  1,188 collected, 1,183 at `56f0573` (the 5 new tests). At the end
  (AIOS `ec3c467`, Cerebrum `062d12c`): AIOS 764 passed and the 7 known
  errors (771 collected: the mutation run's 10 tests); Cerebrum 1,173
  passed, 4 skipped, the 19 known failures and 2 errors by name, both
  of known issue 35's deadline tests passing (1,198 collected: its 10).
  In the first AIOS run, one of the new tests, building A-MEM providers
  through the real LLM controller, had installed the process's LiteLLM
  usage logger, and `test_cost_instrumentation.py`'s own, installed
  later, then recorded nothing; the test patches the install out
  (`ec3c467`).

### Subtask 18

**Housekeeping** (2026-11-16, before the subtask's spec):
- Open decision 6 is resolved (below).
- Known issue 49: the 118 key heads in the 39 local logs are masked in
  place with the redaction's own rule (`Api Key:<redacted>` and the
  asterisks); afterwards no file holds a value or a fragment of one.
- Known issue 51 is fixed: the AIOS suite's conftest sets
  `LITELLM_MODE` to `PRODUCTION` before anything imports LiteLLM, and
  both repos' `_graphiti_script.load_env` copy the `NEO4J_*` lines of
  `AIOS/.env` and no other. Tests:
  `tests/environment/test_dotenv_isolation.py` (a pytest of the suite,
  started without any name of `.env`, imports LiteLLM and gets none;
  `load_env` copies `NEO4J_*` only) and Cerebrum
  `tests/agents/test_graphiti_script_env.py`; each fails without its
  fix. The kernel still loads `.env` itself (`runtime/launch.py`).
- The system's temporary directory held 66 `aios_amem_*` stores, all
  deleted (87 MB, no process held them): 58 written during Subtask
  17's mutation run (35 when Subtask 17 counted them) and 8 during its
  runs of 2026-11-15 (cause not looked into).
- `docs/FULL_GRID.md`, a stub for Subtask 23, holds the judge-window
  plan and the native k = 30 sensitivity cell.

**Spec before code** (AIOS `67bc226`; one correction before any code,
`23b97d1`: a flood copy keeps its source event): `STRESS_DIMENSIONS.md`,
the three dimensions, their levels, what each locus is predicted to do
and why, the measures and the grounding.

**Code** (AIOS `c389539`, Cerebrum `d876f0f`):
- **Agent count.** `agents_v1.py` derives `agents_n3`, `agents_n6` and
  `agents_n12` (and `pilot_agents_nN`) from `users_v2`: the same
  events, utterances, sessions and probes, written by N − 1 writers
  (one writer turn per writer active in a session; each event keeps its
  v2 memory type). `--agents N`; at H > 0, round(H·N/3) agents deviate
  (`schedule_for`, Subtask 10's schedule at N = 3).
- **Concurrency.** `--concurrency concurrent`: each write of a session
  its own task, the probes issued at once when every write task of the
  last session has begun. In the kernel, a memory request is now
  accepted on the event loop (stamped against the barrier and queued,
  in arrival order) and awaited off it, and a chat request's barrier
  snapshot is taken on arrival. Before, the `/query` handler served a
  memory request on the event loop, so concurrent writers were
  serialized at the HTTP layer and no probe could race a write.
- **Load mode.** `--load M`: M users at a time against one kernel.
- **Faulty agent.** `--fault wrong_user | missing_metadata | flood10 |
  flood50`, one writer (or the consumer, for `missing_metadata`) per
  user by a seeded rotation, paired across loci; the wrong-user victim
  is the next user. Kernel sessions (`POST /session/open`,
  `/session/close`, `session_token`): a request is served for the
  session's user, the claim it overrode recorded
  (`identity_overridden`). WriteQuota (`memory.write_quota`, off by
  default, on under the floods): at most `max_writes` (4) writes per
  writer, user and session, duplicates (normalized text) rejected
  first.
- **Scheduler.** Event-driven (known issue 15).
- **Measures.** `stress.measures` on every trial (`TrialResult.stress`);
  `stress_report.py` pairs each trial with its reference.

**One-user tries** (in-house, user 0; not recorded, their flood
numbers match the functional check's user 0): N = 12 ran end to end,
and the user's blocks and answers were byte-identical at N = 4 and 12;
concurrency: no late write in the kernel, 3 in replicated, 2 in native;
wrong user: no kernel row misfiled, 7 to 8 rows misfiled by replicated
and by native, held in the victim's blocks; flooding: no kernel flood
row stored, 19 and 20 by replicated and native, and native's
integration block lost the whole profile.

**Scheduler check** (`results/scheduler_check_s18`, its
`PROVENANCE.md`): pilot_v1, users 0 to 9, H = 0, kernel in-house, Qwen,
before (AIOS `7053e0a`, from a worktree) and after (`c389539`), one
`config.yaml`. Blocks, writes and answers identical for all 10 users.
`schedule_wait_ms` median 845 ms (409 to 925) before, 1.0 ms (0.7 to
3.4) after; the kernel's overhead median 906 ms before, 77 ms after.
Judged together in one pass, the identical answers' scores agree for 5
of 10 profile, 10 of 10 task and 6 of 10 integration scores: the
judge's own variation (known issue 24, extended), not the scheduler's.
A first "before" run was invalid (Azure refused the network after a
router restart, then its re-run reused the run id, known issue 36);
excluded, recorded in the provenance.

**Review** (one adversarial pass over the code and the spec, while a
first functional attempt, `f18`, ran; that attempt was stopped after
about 30 minutes for the fixes, and its partial results are neither
used nor archived) and its fixes (AIOS `d451801`, Cerebrum `8ef6d6f`),
each with a test that fails without it:
1. **wrong_user outside the kernel failed every Mem0 trial.** The
   faulty writer's rows were in the victim's partition, which no
   per-session listing read, so `extraction_failure` took its writes for
   writes that stored nothing. Each session's listing now lists the
   user's rows in the victim's partition (`misfiled`) and credits them
   to the writes that stored them.
2. **A forget's reply had no commit time.** The harness fell back on
   its own reply time, so a revoke the kernel served last could look
   late although the probe's barrier covered it. A forget's report now
   carries `committed_at` and `barrier_seq`, as a write's outcome does.
3. **Uncovered writes counted as misses.** A write the kernel accepted
   after the probe is outside its guarantee; the misses now count
   `late_covered` (the late writes that are not uncovered).
4. **`reappeared_ids` read only a session's last writer turn.**
5. **Concurrent probes' latency and completion** were taken in the
   dataset's order; now in each probe's own thread.
6. **Load mode:** a request could wait, unmeasured, for one of the
   default pool's 12 workers; the server now awaits every chat and
   memory request on a 64-worker pool of its own
   (`aios/utils/request_pool.py`; storage and tool requests are still
   served on the event loop).
7. **Probes issued before a last-session writer failed** ran on into
   the next trial; they are drained and their session closed.
8. **The flood check** counted rows (a Mem0 write can leave none or
   several), "its events" had to mean write events (a revoke-only turn
   is flooded too), and the create capture counted quota-rejected
   creates. The check now counts each flooding turn's accepted flood
   writes against `max_writes` less its write events
   (`flood_sessions_over_bound`), with the kernel's quota from the
   pre-flight.
9. **Four tests would have passed with their rule broken:** the bound
   injection (now a kernel-vs-library equivalence over 20 users whose
   writes and chats claim the next user), the chat's arrival snapshot
   (untested), the quota's lock (now under forced interleaving), and
   the agent-count check's "private fact not its writer's last", which
   read a flag hard-coded False at N = 6 and 12 (now computed from the
   file's own turns; the data files' headers record the new generator
   hash, no user changes).
10. **Minor:** `--agents` with another dataset ran it as N agents (now
    refused); spec wording (`stop()`, the generator's checks, when the
    probes are issued, where `identity_overridden` sits).

**Functional check** (`f18b`, Cerebrum
`results/stress_functional_f18b`, its `PROVENANCE.md` and
`analysis.md`; AIOS `d451801`, Cerebrum `8ef6d6f`): judge-free, Qwen,
users 0 to 4 of the pilot (16 in the load cells), all 72 cells:
kernel in-house and Mem0 at every level, the four agent-managed cells
at every level but the load mode. Every check that must hold held
(the report's "Checks that must hold"):
- **Agent count.** N = 12 ran end to end in every cell; 5 of its 60
  trials failed by the extraction check, all on Mem0 (below). In-house
  at H = 0, every judge-free outcome (25 of 25 per locus) and every
  block, byte for byte (30 of 30), was the same at N = 3, 6 and 12 in
  all three loci. On Mem0 the judge-free outcomes agreed in 24 of 25
  (kernel), 17 of 20 (replicated) and 15 of 15 (native; the users with
  a failed trial left out) and no block was byte-equal: Mem0's
  extraction words each row anew. At H = 2, against H = 0 at the same
  N, `memories_missing` rose by 0.4 to 2.4 in every locus and N, with
  no cross-user row; five users are too few to test the spec's
  prediction that the per-probe effect is flat in N.
- **Concurrency.** Every probe was issued with writes in flight. The
  kernel's waited for them (median 99 ms in-house, 3.7 s on Mem0,
  where a write is a GPT-4o call; no timeout) and had no late write.
  In-house its outcomes were as sequential; on Mem0 some moved with no
  late write (deletion −1: user 0, whose answer named the value;
  recency −2 and +1), Mem0's run-to-run variation (known issue 42) or
  its changed extraction context (known issue 53), which five users
  cannot separate. Replicated and native read at once: 72 to 90 late
  writes over their 24 to 30 probes, every probe, and two late forgets
  (a deletion probe whose block held the value its revoke, still in
  flight, was removing: replicated Mem0 and native in-house). No
  timing miss or stale read was possible: none of the five users'
  recall, recency or contradiction targets is written in the last
  session (in the smoke's 30 users, 6 recency and 4 contradiction
  targets are).
- **Wrong user.** The kernel misfiled no row and recorded
  `identity_overridden` on each of the faulty writer's 27 requests;
  every outcome as without the fault in-house (on Mem0 one recency
  probe passed that had failed). Replicated and native misfiled 27 to
  34 rows into the next user's partition, which reached that user's
  blocks 65 to 88 times, and their users missed about one more fact
  (`memories_missing` +0.80 to +1.20, every interval above 0).
- **Missing metadata.** As Subtask 10's V3: native shows private rows
  of other agents (2 in-house, 1 on Mem0); the kernel and replicated
  none.
- **Floods.** The kernel accepted at most `4 − (its write events)` of
  the flooder's writes in every turn (9 at F = 10 and at F = 50; on
  Mem0 they left 7 rows), rejected none of a reference writer's, and
  `memories_missing` did not move (+0.20 to +0.40, every interval
  across 0). In-house no outcome moved; on Mem0 at F = 10 one recency
  probe passed (one flood row in its block) and one contradiction
  probe failed (none) that had not. Replicated and native accepted
  every flood write
  (90 and 450; on Mem0 its extraction merged them into 30 to 340
  rows), which reached the blocks 71 to 295 times; in-house, their
  users missed 1.0 to 1.6 more facts (at F = 50 replicated +1.20
  [+0.16, +2.24], native +1.60 [+0.92, +2.28]).
- **Load** (kernel only, 16 users at M at a time): in-house
  throughput rose by about a quarter from M = 1 to 4 and held at
  M = 16 (0.75, 0.96 and 1.00 users a minute; Mem0 0.66, 0.69 and
  0.61); probe latency grew (in-house median 8.9, 34 and 80 s); the
  barrier wait did not (p95 under 2 ms, no timeout). Most of the
  growth is the model's: a probe's LLM call waits at Ollama behind its
  batch-mates (`llm_ms` median 8.8, 13 and 47 s in-house; 76, 112 and
  441 ms per completion token), and a request arriving while a batch
  runs waits for that batch (`schedule_wait_ms` median 1 ms, 8.8 s and
  12 s; known issue 54). `search_ms` grew too (in-house median 138,
  136 and 344 ms; Mem0 115, 290 and 949 ms). Writes queued on the
  kernel's one memory thread, as the spec said: a Mem0 write took a
  median 1.3, 3.2 and 24 s at M = 1, 4 and 16 (in-house 0.05, 0.16 and
  0.67 s), consistent with Mem0's throughput falling at M = 16. But the
  spec's prediction that a probe's barrier wait would grow with them
  did not hold: in the load mode a user's probes start after its own
  writes have completed, so no write of the user is in flight at a
  probe.
- **Deviation: Mem0 stores nothing for one vague sentence when its
  writer has written little** (known issue 53). Six trials failed, all
  by the extraction check, all on the same two writes, users 0's and
  4's "Issues are sent to Rollbar." (a paraphrase of "Errors get
  reported to Rollbar."); every other trial of every cell passed.
  Mem0 2.0.2 shows its extraction LLM up to 10 of the user's memories
  with the same `agent_id` (the most similar to the write) and the last
  10 messages of that agent for that user, and every locus passes the
  writer as `agent_id`. At N = 3
  and 6 the sentence's writer is the task agent, with the user's task
  facts already stored; at N = 12 it is `code_review_agent`, with
  almost nothing; under concurrency its writer's earlier writes of the
  session were still in flight. Over every Mem0 attempt: stored 54 of
  54 times at N = 3 and 6 with one write at a time per user; nothing 7
  of 16 times at N = 12 (kernel 1 of 6, replicated 3 of 6, native 3 of
  4) and 1 of 6 under concurrency (native). No log holds Mem0's "LLM
  extraction failed": these were empty extractions, not swallowed
  errors. The trial fails, as any Mem0 write that stores nothing does
  (known issue 32). Two cells were re-run once each under a new prefix
  for it: the kernel's passed, the replicated cell failed again the
  same way and was not re-run further; the kernel Mem0 `n6conc` cell,
  killed in flight when the run was stopped, was re-run whole; every
  other cell ran once. So "the kernel is unaffected
  except cost" holds for the kernel's own path but not for a backend
  that extracts per writer.

**Smoke** (`s18`, Cerebrum `results/stress_smoke_s18`, its
`PROVENANCE.md` and `analysis.md`; AIOS `d451801`, Cerebrum `8ef6d6f`):
judge-free, Qwen, all 30 pilot users at N = 6 and H = 0, in-house,
the sequential reference, `concurrent`, `flood10` and `flood50` in the
three loci; one attempt, no failed trial. Every check that must hold
held. Paired against the same users' sequential trial (exact McNemar
for outcomes, a t interval for means; pass rates with 95% Wilson
intervals in the report):
- **Concurrency.** 6 users have a recency target, 4 a contradiction
  target, 6 a private event and 14 a revoke in the last session. The
  kernel's 180 probes waited (median 114 ms, at most 248) and read no
  late write; every outcome as sequential. Replicated's had 552 late
  writes, native's 498 (366 and 210 of them were in the same probe's
  block: committed during the search, or for native, whose time is
  an upper bound, returned during it). The timing cost, paired:
  replicated lost 2 contradiction probes (both stale reads: the
  earlier statement not yet retired), native 1 (a timing miss, also a
  stale read); no other outcome moved, and `memories_missing` did not
  (replicated +0.00 [+0.00, +0.00], native −0.03 [−0.10, +0.03]).
  Native's other 9 stale reads changed no outcome (5 in probes that
  fail in both runs, 4 in probes that pass in both with the stale
  value in the block), nor did its 6 late forgets (all in probes that
  fail in both). `memories_missing_timing` counted 4 and 5 writers
  (replicated, native), each also missing from the user's sequential
  block (replicated: the 300-token budget; native: its 10-row cap), so
  the measure is read paired (`STRESS_DIMENSIONS.md`, corrected).
- **Floods.** The kernel accepted at most `4 − (its write events)` per
  flooding turn (94 flood writes at F = 10, 98 at F = 50, over 30
  users), rejected no reference writer's write, and moved nothing:
  `memories_missing` −0.03 [−0.24, +0.17] at both levels, profile facts
  in the integration block +0.00, every outcome as sequential; its
  accepted flood rows reached a block 1.7 to 1.8 times a probe.
  Replicated and native accepted all 530 and 2,650 flood writes, every
  flooding turn over the bound, 4.3 to 10 flood rows in a probe's
  block: `memories_missing` +0.60 [+0.21, +0.99] and +1.03 [+0.57,
  +1.50] (replicated, F = 10 and 50), +0.60 [+0.23, +0.97] and +1.47
  [+1.03, +1.90] (native); profile facts in the block −0.23 [−0.38,
  −0.07] and −0.53 [−0.72, −0.34] (replicated), −0.36 [−0.54, −0.18]
  and −0.69 [−0.86, −0.52] (native). Native's recency answers changed
  (11 users gained, 1 lost at F = 50, p 0.006; 10 of 30 sequentially),
  not which recency values its blocks held (4 to 8 of their 10 rows
  were flood rows): none of the 11 gained users' flooders wrote the
  recency target, each block held one row of the update with and
  without the flood, and both values were in the block both times; with
  the flood rows around them Qwen's answer stopped naming the stale
  value. Not read as the flood helping.

**After the runs.** The report (Cerebrum `4279ce6`) prints the checks
that must hold first, each write a backend stored nothing for
(`writes_without_row`), the pass rates with their Wilson intervals,
the paired `memories_missing` beside the concurrency measures, and the
H = 2 rows in a table of their own (computed before, but printed as
dashes); each with a test that fails without it. `STRESS_DIMENSIONS.md`
(this commit) now says, as the code does, that a `timing_miss` needs
the target's value missing from the block; that a late write can still
be read (`fetch_started_at` precedes the search's query embedding, so
a write committing during the search is found: in-house, never on
Mem0; native's commit time is an upper bound); that
`memories_missing_timing` is read paired; and, under the agent count's predictions, what the functional
check found on Mem0. The runs' records: Cerebrum `060cb9d`.

**Review of the write-up** (the same pass, its second half): the code
fixes closed all ten findings. The write-up had 8 errors and 16
imprecisions, corrected here (this commit): among them the late-write
counts on Mem0, the kernel's flood outcomes on Mem0, what grows under
load (the LLM call at Ollama, more than the batch wait), native's
stale reads (none changed an outcome but the one timing miss), native's
recency under floods (its answers changed, not the recency values
its blocks held), and open
decision 7 (the provider's log does not tell an empty extraction from
a swallowed error). With them (Cerebrum `7a149ab`, each with a test
that fails without it): the "stored nothing" check matches that
failure only; the agent-count outcomes count the five judge-free
probes (the unscored integration probe always agreed, so 30 of 30 read
for 25); an agent-count dataset runs only at its own N.

**Verification pass** (rule 6's second pass, over the write-up's
corrections and the report's fixes): all 26 corrections and the
report's fixes confirmed; five wordings corrected (AIOS `7655628`): the
in-house throughput's rise (about a quarter, not a third), native's
late-write times (an upper bound), native's blocks under floods (they
changed; the recency values they held did not), known issue 52's scope
(in-house cells) and known issue 54 (a batch already held a later
request before Subtask 18).

**Mutation run** (rule 6, once, on the final code: AIOS `17a9f95`,
Cerebrum `7a149ab`). Four module owners (the kernel's Subtask 18
changes; the memory library's; Cerebrum's history and writers; its
stress measures, report, orchestrator flags and agent-count data)
wrote 199 mutants of rules the documents state and ran each on a
scratch copy against their area's tests, with Ollama, behind a
loopback-only network guard; 102 were killed, six of them (every
`agents_v1.py` mutant) only by the data files' generator hash: with
the data regenerated by the mutated module, one is killed by a rule
test, one is equivalent (a v2 session has one writer) and four
survive. Each survivor was then rerun against the full suite of every
repo whose tests load its file (the library's: both). Of the 97
survivors:
- 1 is killed by those reruns: the memory getter waiting 30 s, by
  `test_write_barrier_integration.py` (a stopped scheduler's thread,
  still blocked in it, takes the next test's writes).
- 2 are equivalent: `SessionRegistry` left out of the library's
  `__all__` (nothing star-imports it); the concurrent consumer's
  message-list reset (the replicated and native assistants keep no
  list).
- 72 now fail a test, and with them three of the four hash-only
  `agents_v1` ones (AIOS `49f5323`, Cerebrum `0e459fe`), each checked
  against its mutant on a clean copy: every one whose rule a reported
  number, or a check that must hold, depends on, in the runs made or
  on a re-run:
  - the kernel: a memory request, writes and forgets included,
    accepted (stamped and queued) on the event loop in arrival order
    (accepted off it, 199 or 200 of 200 writes were stamped after the
    chat that arrived after them: the kernel's `uncovered_writes`, 0
    in every run); the LLM thread's drain taking what is queued
    without waiting, through the hooks' getters (a drain that waits
    adds about 100 ms to every `schedule_wait_ms`, 1.0 ms at the
    median in the scheduler check); every getter waiting on its queue,
    not polling, and giving up after 0.1 s;
  - the library: `fetch_started_at` on the wall clock, after the
    barrier wait and before the search (stamped before the wait, every
    write a kernel probe waited for reads as late; after the search,
    366 of the smoke's 552 replicated late writes would not); a
    write's `committed_at` when the provider returned, and a forget's
    after its deletes (else replicated late writes and forgets are
    undercounted); an over-quota text resent still a quota rejection,
    not a duplicate (the flood50 reason split); session tokens never
    reissued (sequential sessions reusing a counter token would count
    a writer's writes across the whole history against one quota);
  - the harness: a quota rejection, of a write or a flood write,
    recorded with its reason, and an override read beside `response`
    (else the kernel's flood bound check and its wrong_user
    `identity_overridden`, 27, fail); a flood near-duplicate typed as
    its source event; a turn with only a revoke flooded (the smoke has
    12); an event's completion when its last call returned (else no
    write is in flight: native's 498 late writes); each fault's own
    rotation, flood50 never on the consumer, and the N-agent
    schedule's construction (the H = 2 offset, the start positions,
    the seeded shuffle); a session record keeping its flood writes
    (replicated and native `flood_sessions_over_bound`, 53);
    concurrent probes issued once every write has begun, at a
    wall-clock time (the smoke's 552 and 498 late writes); every
    writer turn's listed rows (`late_rows`, 432); the kernel locus's
    task writer writing `task_context`; native listings over the
    dataset's writers (every native N = 3 trial would fail) and native
    misfiled rows whichever writer is faulty;
  - the analysis: a write's commit time the store's own, else its
    completion; a write at the probe's snapshot covered; `timing_miss`,
    `stale_read` and `late_forget` read from the block, `stale_read`
    for contradiction probes too; `late_rows` the rows the consumer
    may see, private rows out; overridden requests and chats, and
    quota rejections by writer, counted; `memories_missing_timing`
    naming writers whose late writes (not revokes) left no row; in the
    report, `writes_without_row` over failed trials too, the across-N
    users those with no failed trial, H = 2 paired at its own N, the
    concurrency table over the passing trials' probes with writes in
    flight, the load table's throughput per minute, quantiles and ms
    per completion token, flood rows per block averaged, the checks
    read from kernel cells only, `kinh_q` kept in-house, privacy among
    the judge-free probes, the across-N check in-house only; in the
    orchestrator, the quota pre-flight for both flood levels, the
    N-agent schedule over writers and consumer, the faulty agent in
    the dataset's order (the consumer only for missing_metadata), a
    fault trial's agent, victim and timing recorded, a concurrent
    trial run concurrently, `TrialResult`'s `stress` field; in
    `agents_v1.py`, N = 3's parity writer, each derived event's memory
    type and the order of writer turns, as rules.
- 22, and the fourth hash-only `agents_v1` one, hold in the code
  (their owners checked each) but no test of either repo pins them, so
  this file claims no more. None changes a reported number:
  - the kernel (11): the executor passing the chat's arrival snapshot
    to the injector (no kernel write was late in any run); a chat's
    claim canonicalized, a chat with no claim no override, a chat
    reading the session's user (harness ids are canonical, the
    consumer always claims its user, and the library canonicalizes
    later); the quota keyed by the kernel session (every write carries
    `metadata.session` too); a token refused without a memory manager;
    `/session/close` (the harness never reuses a token); a session
    opened for a non-canonical id; a write's `params.user_id` claim
    rewritten (the SDK sends none); `retrieve_memory_raw` refused over
    `/query`; the tool getter's timeout (shutdown time only);
  - the library (5): `--write-quota off` (a phase left on would be
    refused by the pre-flight); a bad `write_quota` block refused
    where `PipelineSettings` is built (the kernel and agents build it
    through `from_config`); the quota keyed by the stored user (every
    kernel request carries a session); `barrier_snapshot` None, or 0,
    when no wait could run (only the test-only provider commits
    synchronously; no report reads a replicated snapshot);
  - the harness (2): the victim's id kept out of user i's listings
    (no stress number reads them: the agent-managed wrong_user cells'
    per-trial listing counts and token attribution); concurrent
    writers tolerating a swept row a forget had listed (no run had
    one; the trial would fail);
  - the analysis (5): `late_forget` counting any revoke (every v2 user
    has one, the deletion target's); the flood bound counting
    quota-rejected own write events (a writer's own events come first,
    at most 4); the flood check passing on None (every kernel flood
    cell ran with the quota on); the agent-count pilots capped at 30
    users (the driver passes `--trials`); `MAX_SESSION_EVENTS` (no
    session holds 5).

  The stress measures and the report were the weakest area: 40 of
  their 50 mutants survived the area's tests, 36 of them changing a
  number in the smoke's or the functional check's analysis (the
  mutated measures recomputed from each trial's records, which with
  the pristine module reproduces the smoke's analysis byte for byte
  and the functional check's but for replicated Mem0's
  `flood_rows_stored`; the mutated report run on copies of both).

  One defect, found by the harness's owner: the extraction check
  (`_empty_writes`) counted a flood near-duplicate's row as a row of
  its source event, so on Mem0 a write that stored nothing could pass
  on its copy's row (`STRESS_DIMENSIONS.md`, "flood10, flood50", keeps
  flood rows out). Fixed (Cerebrum `251d0ab`), with a test that fails
  without it; the fixed check agrees with the old on all 796 archived
  trials (listings rebuilt from each trial's records reproduce the 8
  trials that failed by it), so no reported number changes. The
  mutants, their results and logs are in
  `repo-artifacts/AIOS/mutation18/` (without the repos' copies).

**Suites** at the end (AIOS `49f5323`, Cerebrum `251d0ab`): AIOS 831
passed and the 7 known errors (839 collected; 828 at `d451801`, so the
mutation run's 11 tests), and once `test_write_barrier_pbt.py`'s
`test_disjoint_user_retrieval_is_not_delayed`, which Hypothesis called
flaky (it passed 3 of 3 alone; known issue 35); Cerebrum 1,285 passed,
4 skipped, the 19 known failures and 2 errors by name, and known issue
35's `test_delta_equals_arithmetic_difference` (1,311 collected; 1,257
at `7a149ab`, so the mutation run's 54).

### Subtask 19

Kernel ablation switches (`ABLATION.md`): one switch per kernel
responsibility, each removable alone in the kernel locus and paired with
the measurement that should move, to answer where the kernel's gains
come from (Jg94; claim C4).

- **Amendment 9 first** (open decision 7, resolved as (b); AIOS
  `4a6062d`, Cerebrum `b8b0f9b`). Mem0 2.0.2 logs and swallows four
  failures of a write (its extraction call, parsing that call's reply,
  embedding, inserting). Every locus's Mem0 write now collects those
  lines while it runs (Cerebrum `cerebrum/utils/mem0_errors.py`; the add
  runs on the caller's thread) and raises when it stored nothing after
  one, so a Mem0 write that returned and stored nothing found no fact:
  in v2 it is a lost memory (`writes_without_fact`), as Graphiti's and
  A-MEM's are, and the trial is scored. Numbered 9: `BENCHMARK_V2.md`
  already had Amendments 7 and 8. v2 only (corrected on review): a v1
  kernel writer reads a refused create as an empty one, so v1 keeps
  Mem0's old rule (`EMPTY_WRITE_IS_LOSS_V1`). Tested against a real Mem0
  store whose extraction call raises or answers unparseable JSON.
- **The spec before the code** (AIOS `a5661f6`): the mechanism, the
  table (component, switch, what it removes, condition, measurement,
  prediction), the conditions, the functional check's rules and the
  smoke's.
- **The mechanism** (AIOS `894ee06`, Cerebrum `440e705`):
  - `memory.ablate` (`aios/memory/pipeline/ablation.py`): `barrier`,
    `identity`, `visibility`, `supersession`, `forget_scope`, `quota`,
    `block_format`, `block_order`, `budget`, `threshold`,
    `consumer_config`; every one the full kernel by default; unknown
    keys or values fail startup; YAML's bare on/off read as booleans
    are accepted. A pipeline setting (`PipelineSettings.ablate`,
    `/memory/config` `pipeline.ablate`, copied by the replicated
    agents); a switch never rewrites another setting (the library reads
    `effective_*` values).
  - The four controls are aliases (`ALIASES`): `no_visibility` →
    `visibility: off`, `no_delete` → `forget_scope: none`,
    `writer_scoped` → `forget_scope: writer`, `no_supersession` →
    `supersession: off`. Kernel and replicated writers now call the
    user's forget under every control, and the forget scopes itself;
    native keeps its own switches. `run_bench_v2.sh` runs each
    control's cells on a fresh kernel with its switch, in the same
    phase directories (the analysis reads them unchanged).
  - Harness: `--ablate SWITCH[=VALUE]` (and an aliased `--control`);
    the pre-flight requires the kernel's `pipeline.ablate` to equal the
    run's in every switch, whatever the locus; a switch the locus lacks
    is refused; every `TrialResult` records `ablation` (`{}` for the
    full kernel), the run settings too. `--variants AGENT=CODE` gives
    every user the same variant (an ablation's condition: V2, V3, V4).
  - `LLMQuery.retrieval` carries a consumer's own k, threshold and
    budget; the kernel applies them only under `consumer_config:
    honor`, through a pipeline built as a replicated V4 consumer builds
    its own; the injection diagnostics record `consumer_config: {sent,
    applied}`.
  - `scripts/run_ablation.sh` (each switch against the full kernel on
    the same users under its row's condition, kernel locus only, one
    fresh kernel per write-quota setting; the replicated V4 cell for
    `consumer_config`); `benchmarks/shared_memory/ablation_report.py`
    and `ablation_figure.py` (the table, the functional and smoke
    rules, the per-trial record check, the contribution figure: one
    bar per primary measure (switch and condition) on its own axis, an
    SVG drawn by hand since neither venv has matplotlib).
- **Code review** (one pass; fixes AIOS `64bbbee`, Cerebrum `bb7e845`;
  `ABLATION.md` "Corrected on review" lists what changed after the
  spec's commit):
  - The v2 analysis's guard criterion ("the guard armed after a
    forget") would have failed every `no_delete` and `writer_scoped`
    cell, whose forget now records no tombstone by design: a scoped
    forget is recorded on the session event, left out of the criterion
    and counted in a column of its own (`scoped`).
  - Amendment 9 would have scored a v1 kernel Mem0 write that hit a
    swallowed failure as a lost memory, though a v1 kernel writer cannot
    tell a refused create from an empty one: v1 keeps the old rule.
  - `barrier: off` dropped the barrier's bookkeeping, so every late
    write (one accepted after the read included) read as covered, and
    the harness's audit and cost reads stopped waiting. The barrier now
    keeps its sequences and snapshots and skips only the waits an agent
    sees (`waits`); the audit and cost reads wait (`required`).
  - `identity: claim` dropped the session token from the write quota's
    bucket key; the token keys it again (the binding is what the switch
    removes). A dead method went.
  - The full kernel's block diagnostics gained a `block_order` key; it
    is reported only for `similarity`.
  - The report: quota's profile facts made a primary measure (as the
    spec names it); the echo-user split, flood writes accepted and
    V4's `memories_missing` added; one pair confirms nothing (n >= 2);
    the threshold rule compares probe by probe; each trial's recorded
    ablation is checked against its cell's; a cell whose trials all
    failed is reported, not dropped.
  - Tests: the identity tests go through the request handler; the
    kernel-V4-equals-replicated-V4 test compared two empty blocks (no
    row reached V4's 0.5 threshold) and now uses rows V4's threshold
    and k both bind, the replicated side built by Cerebrum's own
    variant code, loaded by path.
- **Functional check** (judge-free, users 0-4, in-house, N = 6, Qwen;
  `results/ablation_functional_f19b`, archived to
  `repo-artifacts/Cerebrum/ablation_functional_f19b`; 22 cells, 110
  trials, none failed, each trial's recorded ablation its cell's). The
  first run (`f19`) was stopped after three full-kernel cells when the
  review changed the code; its partial output is left in
  `results/ablation_functional_f19` and used nowhere. 13 of the 14
  rules held:
  - barrier: 85 covered late writes over 5 users (17 per user), the full
    kernel none. No stale read or timing miss (the spec predicted a
    few; s18's replicated cell had 2 stale reads over 30 users), and
    one late forget: user 4's deletion probe read before its forget ran
    and was lost, the value in the block (user 0's passed, so deletion
    -1 +1).
  - identity, wrong_user: 27 misfiled rows, 88 cross-user rows in
    blocks, `memories_missing` +0.80; the full kernel none. s18's
    functional check's replicated in-house cell had the same three
    numbers (the spec's "27 to 34" took native Mem0's 34; replicated
    Mem0 had 32).
  - identity, V2: the rule (profile facts in the block 0 for every user)
    did not hold as written: one user's block had 1 of 6 profile facts.
    That fact ("Python") was in the task agent's row; no profile-writer
    row reached any user's block (0 of 5; the full kernel 3 to 4 per
    user), and `profile_agent` was a missing writer for every user. The
    mechanism is confirmed; the rule counted a value carried by another
    writer. Recorded as a deviation; the rule is left as registered.
  - visibility: the privacy probe failed in 5 of 5 users with its value
    in the block; the full kernel's never.
  - supersession: an earlier statement in 10 of 10 recency and
    contradiction blocks; recency passed 0 of 5 and contradiction 3 of
    5 (the spec: 1 of 5 and 3 of 5).
  - forget_scope: echo users 0 and 4 kept 2 carriers each and failed
    deletion; users 1-3 passed. The full kernel failed one echo user's
    deletion probe without the value in the block: Qwen listed
    "Mattermost" among popular chat apps (`forbidden_in_block` false).
  - quota: no quota rejection; flood rows per probe 1.3 to 6.5 (F = 10)
    and 9.8 (F = 50); flood writes accepted 18 and 90 per user against
    1.8; `memories_missing` +0.8 and +1.0. Profile facts did not fall at
    F = 10 (0.00) and fell 0.37 at F = 50 with an interval across 0
    (the spec: -0.23 and -0.53); the smoke decides.
  - block_format, block_order: blocks differ in 30 of 30 probes; legacy
    adds 3 tokens per probe (the budget binds).
  - budget off: binds in no probe (4.8 of 6 per user on the full
    kernel), +73 block tokens per probe. threshold 0.3: after_threshold
    never above the full kernel's, -0.27 rows per probe.
  - consumer_config honor: the kernel's V4 block equals the replicated
    V4 block in 30 of 30 probes; on the full kernel the V4 consumer's
    block equals the H = 0 block in 30 of 30; under honor, 13.6 to 1.2
    rows per probe, profile facts 1.0 to 0.0, `memories_missing` +3.6.
- **Smoke** (`s19`, Cerebrum `results/ablation_smoke_s19`, its
  `PROVENANCE.md` and `analysis.md`; AIOS `64bbbee`, Cerebrum
  `bb7e845`): judge-free, Qwen, users 0 to 29, N = 6, in-house; the
  four non-definitional switches, 10 cells, 300 trials, one attempt,
  none failed, each trial's recorded ablation its cell's. Paired by
  trial index (ablated minus the full kernel; a 95% t interval for
  means, exact McNemar for outcomes). Every primary interval excludes
  0 in the predicted direction, so the four predictions are confirmed;
  where a secondary measure departs from the spec it is said below.
  - `barrier: off` (`n6conc`): covered late writes +18.10 [+16.37,
    +19.83] per user (543 over 180 probes; the full kernel's probes
    waited, median 146 ms, at most 373, and read none). s18's
    replicated cell on the same users: 552. Of the 543, 240 were in
    the same probe's block (committed during the search), against
    replicated's 366. Misses: 7 stale reads (+0.23 [-0.00, +0.47] per
    user), 3 timing misses (among the stale reads) and 3 late forgets,
    10 probes in all, where replicated had 2 stale reads and nothing
    else; 2 deletion, 3 recency and 3
    contradiction probes lost (p 0.50, 0.25, 0.25; replicated lost 2
    contradiction probes), each with a stale read or a late forget.
    `memories_missing` -0.10 [-0.25, +0.05]. So the kernel without its
    barrier missed more than "a few, as replicated's": more of its late
    writes landed after the search; why was not looked into. The
    tombstone guard dropped 12 rows 46 times in this phase (8 users;
    none in any other phase): reads that met a forget's rows after it
    recorded its tombstone and before it deleted them (user 0's trace:
    the forget accepted at .084 s behind two of the profile writer's
    writes, its tombstone recorded between .270 and .319, guard drops
    from .319 to .377, the deletes logged at .373). Three deletion
    probes read after their forget was accepted (11 to 18 ms before the
    fetch) and before it ran (users 0, 4 and 15; 4 and 15 lost the
    probe, user 0 failed in both runs).
  - `identity: claim` (`n6wrong_user`): misfiled rows +4.03 [+3.22,
    +4.85] per user (121; users 0 to 4: 27, as in the functional
    check), where the full kernel overrode 133 faulty requests;
    cross-user rows in the blocks +12.23 [+8.43, +16.04];
    `memories_missing` +0.67 [+0.49, +0.85], below the spec's "about
    1": the faulty writer was missing from its user's block in 30 of
    30 trials, but already in 5 on the full kernel (the budget), and in
    5 others the budget let in a writer it had cut. Recall lost 5 (p
    0.06), recency 6 (p 0.03), contradiction 6 (p 0.03); one deletion
    probe lost (user 13: the faulty writer's own forget went to the
    claimed user, so the echo row stayed) and one privacy probe (user
    28: user 27's misfiled calendar row carried the same name); user
    0's deletion probe passed (below). No replicated `wrong_user` cell
    at 30 users to compare with (s18's functional check, replicated: 27
    misfiled rows in-house, 32 on Mem0, over 5 users; the in-house
    cell's 27, 88 cross-user rows and +0.80 equal `f19b`'s).
  - `quota: off` (`n6flood10`, `n6flood50`): flood rows in the block
    per probe +4.72 [+4.10, +5.34] (1.71 to 6.43) and +8.21 [+7.50,
    +8.92] (1.82 to 10.03); profile facts -0.23 [-0.38, -0.07] and
    -0.53 [-0.72, -0.34] (at F = 10 the functional check's 0.00 does
    not recur); `memories_missing` +0.63 [+0.32, +0.95] and +1.07
    [+0.68, +1.46]; flood writes accepted 530 and 2,650 (the full
    kernel 94 and 98). s18's replicated cells on the same users: 6.43
    and 10 flood rows per probe, profile facts -0.23 and -0.53 with the
    same intervals, `memories_missing` +0.60 and +1.03, 530 and 2,650
    accepted. No probe lost; user 0's deletion probe passed at both
    levels.
  - `forget_scope: writer` (`n6h0`): carriers left +0.67 [+0.31,
    +1.02] per user: each of the 10 echo users kept 2 carriers and
    failed the deletion probe (Subtask 15's `writer_scoped`: 4 of 4
    in-house, 2 of 4 on Mem0);
    the 20 others passed in both runs; deletion lost 9 (p 0.004). The
    full kernel failed one echo user, user 0, without the value in the
    block: Qwen named Mattermost, as in the functional check and in
    every s18 kernel cell (29 of 30); its answer did not name it under
    `identity: claim` and `quota: off`.
  - The figure (`contribution.svg`): one bar per primary measure,
    seven, each on its own axis with its interval.
- **Review of the write-up** (the review's second half, over
  `ABLATION.md`, this section, `BENCHMARK_V2.md` Amendment 9, the runs'
  provenance and the steering text; corrected in AIOS `81199aa`,
  Cerebrum `17b4cb9`): 6 errors and 6 imprecisions. The errors: the
  barrier smoke's trace put the tombstone at the forget's arrival (it
  was recorded about 0.2 s later, after two queued writes) and said the
  three late-forget probes read before their forget began (they read
  11 to 18 ms after it was accepted, before it ran); the functional
  check's one late forget (user 4, its deletion probe lost) was left
  out; the guard dropped 12 rows 46 times, not 46 rows; s18's
  replicated `wrong_user` reference was given as 27 to 34 (34 was
  native Mem0's); two steering lines, with the ablation module's
  docstring, still described `barrier: off` and `identity: claim`
  before the code review. The imprecisions: the identity explanation in
  `ABLATION.md` (now with the 5 users whose block regained a writer),
  the Results' summary line (three functional primary intervals
  included 0 at n = 5), the smoke rule's n >= 2 and sign rule missing
  from "Corrected on review", Subtask 15's `writer_scoped` reference
  (4 of 4 in-house), the figure's "one bar per component" (one per
  primary measure) and the timing misses counted apart from the stale
  reads they are among. No number in a report changed.
- **Verification pass** (rule 6's second pass, over the code review's
  fixes and the write-up's corrections): every fix and correction
  confirmed, no error, so no third pass. Each code fix's new tests were
  run against the code with the fix reverse-applied on a scratch copy
  (AIOS 7 failed, Cerebrum 12; one, the quota-bucket test under
  `claim`, fails by a `NameError` rather than its assertion, but
  fails). The data behind each corrected sentence was recomputed, the
  user 0 trace from the kernel log (forget accepted at .084, the reads
  at .268 to .270 with no drop, drops .319 to .377, the forget logged at
  .373). Six imprecisions, corrected (this commit): `ABLATION.md`'s
  figure sentence (one bar per primary measure, now also under
  "Corrected on review"), the sign rule (a zero-width interval, as
  before the review; also `confirmed`'s docstring), "three predicted
  primary intervals", the table's "27 to 34" explained in Results;
  Subtask 15's `writer_scoped` reference here (2 of 4 on Mem0), s18's
  one replicated cell; `BENCHMARK_V2.md`'s guard criterion (a scoped
  forget arms no guard). The report's "flood writes accepted" and V4
  `memories_missing` rows, added on the code review, have no test of
  their own; left to the mutation run.
- **Mutation run** (rule 6, once, on the final code: AIOS `94c2385`,
  Cerebrum `8953e28`). Four owners wrote 200 mutants of rules the
  documents state, 50 each:
  - the memory library's switches (`ablation.py`, `settings.py`, the
    selector, the forget, the facade);
  - the kernel's (the executor, the injector's honored pipeline, the
    manager, `launch.py`, `run_ablation.sh`, Mem0's partial-store
    rule);
  - Cerebrum's harness (the flag, `main()`'s pre-flight, the history,
    the variants, the trial record);
  - its analysis (`ablation_report.py`, `ablation_figure.py`,
    `bench_v2_analysis.py`'s Subtask 19 changes).

  Each ran on a scratch copy against its area's tests, with Ollama,
  behind the loopback-only network guard: 106 killed. Each survivor was
  then rerun against every suite that loads its file: 1 more killed
  (the bare `quota` switch's value, by Cerebrum's
  `test_ablation_harness.py`), none equivalent. Of the 93 left:
  - 62 now fail a test (Cerebrum `7d19bf4`, AIOS this commit). Each
    was run against its mutant on a clean copy, the unmutated copy
    passing:
    - the report (43, every survivor of its area): f19b's and s19's
      records, trimmed to the fields the report reads
      (`tests/agents/fixtures/ablation_runs/`, 79 KB, with the script
      that makes them), must give the committed `analysis.md` and
      `contribution.svg` byte for byte and `analysis.json` to a
      relative 1e-9 (its last digits move with numpy's and scipy's
      versions). 36 of the 43 changed a number, an interval, a
      verdict, a row or a bar of f19b's or s19's analysis. Among them:
      the V2 rule's "every user"; a zero-width interval at 0
      confirming nothing; the block, budget and threshold rules; seven
      predicted directions and two primaries; the stale-read,
      misfiled-row, carrier, flood-row, block-token and budget-bound
      measures; the paired mean and the interval's upper end; the
      "flood writes accepted" and V4 `memories_missing` rows the
      verification pass left here; the figure's one bar per primary
      measure. The other 7 hold on both runs and have cases of their
      own: one covered late write; misfiled rows without a cross-user
      row; a privacy failure without its value in the block; an echo
      user failing with no carrier left; a quota still rejecting; a
      `kmem0` phase read as Mem0; `after_threshold` read apart from
      `after_cap`.
    - the kernel (16):
      - the executor handing the chat's `_request_retrieval` to the
        injector (without it `consumer_config: honor` applies nothing
        while the harness records V4 as applied);
      - the honored pipeline keeping the kernel's barrier, resolver,
        tombstones, usage tag and quota and taking the consumer's
        budget (without the tombstones the honor cells'
        `tombstoned_forms` read 0; without the usage tag their
        embedding tokens go);
      - Mem0's write that stored some facts after a swallowed failure
        passing (Amendment 9; a Mem0 cell of the grid would fail);
      - the driver (9): every cell's condition arguments (the barrier
        under concurrency, six switches at H = 0, V2, V3, V4, the
        faults), users 0 to 4, Qwen, `pilot_v2`, and the kernel's
        recency, barrier timeout, k, budget and supersession. The
        pre-flight would have refused 4 of these 9 mutants.
    - the harness (2): `main()` giving the pre-flight the run's
      `--ablate` switches and an aliased `--control`'s (without
      either, every ablated or control cell is refused, and one
      pointed at a full kernel admitted).
    - the library (1): each bare switch's ablated value, all eleven
      now (`block_order` bare would have run the full kernel under its
      ablated name).
  - 31 hold in the code but no test pins them, so this file claims no
    more. None changes a reported number:
    - the library (14):
      - `changed()` and `effective_threshold` with a threshold of 0
        (no cell uses 0);
      - `full` and `ablation_of` (no caller);
      - `PipelineSettings` filling the block's defaults (every caller
        passes a full block);
      - under `visibility: off`, the shared fetch unfiltered and an
        SDK caller's policy narrowing skipped (no partition exceeds k;
        no caller narrows), and a read by id still guarded (no v2
        agent reads by id);
      - under `supersession: off`, marked rows selected (marks are
        written only under `exclude`);
      - a `none` forget's `listed` (nothing reads it); a `writer`
        forget on a slot with a second writer, or already tombstoned
        (none in the data);
      - under `barrier: off`, a forget's and a listing's waits skipped
        (requests are served one at a time, with `--extract off`).

      `effective_write_quota` has no caller: the write reads
      `ablation.quota_on`.
    - the kernel (9):
      - `/memory/config`'s `write_barrier` gaining `waits: false` under
        `barrier: off` (the pre-flight reads `timeout_ms`);
      - the quota bucket's session token at `accept_memory_request`'s
        call site under `claim` (no condition combines the two);
      - `/memory/config`'s `identity` reporting the configured rules
        (nothing reads it);
      - a token refused without a memory manager;
      - `_truncate_by_token_budget`'s block format (off the request
        path);
      - in the driver: the agent phase's memory-op refusal, an archive
        refusal's exit status, the replicated store per `RUN_PREFIX`,
        and a kernel log name per second.
    - the harness (8):
      - the native writers and the native consumer reading
        `forget_scope` and `visibility` only through their aliases, and
        `run_history_trial` not passing the ablation (no driver passes
        `--ablate` to a native cell);
      - `VariantRunner` losing the ablation (only n6v4 honor's
        `variants_not_applied` record changes; no report reads it);
      - `TrialResult.ablation`'s default (every v2 trial sets it);
      - V1 under `honor` recorded as applied (no condition runs it);
      - Mem0's logger level on the error collector's first install
        (its test pins it only as the process's first install; only
        Mem0's INFO lines would go).

  The report was the weakest area: 43 of its 50 mutants survived its
  tests, 36 of them changing what f19b or s19 reported. No defect in
  the code. Two owners found one stale comment:
  `config.yaml(.example)`'s `barrier: "off"` still read "no write
  stamped" (now "no read waits (writes still stamped)"). The mutants,
  their results and logs, and the follow-up's checks are in
  `repo-artifacts/AIOS/mutation19/` (without the repos' copies).
- **Suites** at the end (AIOS this commit, Cerebrum `7d19bf4`): AIOS
  904 passed and the 7 known errors (893 before the mutation run, so
  its 11 tests); Cerebrum 1,373 passed, 4 skipped, the 19 known
  failures and 2 errors by name, and known issue 35's
  `test_kernel_shared_delta_is_zero` (1,360 at `8953e28`, so the
  mutation run's 13 tests; on a run just before the JSON comparison
  was given its tolerance, the flaky test passed: 1,374).

### Subtask 20

Judge reliability, a second judge, a judge-free decision probe, and the
metrics in one module (`METRICS.md`, `BENCHMARK_V2.md` Amendment 10,
`FULL_GRID.md` "The two judges" and "The decision items").

- **Specs before code**: `METRICS.md` (AIOS `433e422`), with the k rule
  written before the reliability study ran; Amendment 10 (AIOS
  `ed9d955`) before the decision probe's code.
- **The hybrid** (found here; "Notes for the paper" 1): every stored
  judge score before this subtask is round((keyword + LLM) / 2), and the
  stored results keep neither half. From here the LLM score (median of
  k) is the judged metric, the keyword score a judge-free metric of its
  own, the hybrid a continuity column (`METRICS.md`, with the formula).
  The keyword score was recomputed from the records: 3,240 of 3,240
  stored scores are consistent with it.
- **Subtask 11's verdict on each score** (the registered verdict
  stands): hybrid GO (as registered); keyword-only GO (qwen H2
  integration +0.95 [+0.46, +1.44], gpt4o +1.33 [+0.71, +1.96]); the
  second judge's LLM-only score GO (qwen +0.73 [+0.39, +1.08], DiD
  +0.63 [+0.22, +1.04]; gpt4o +0.97 [+0.48, +1.45], DiD +1.02 [+0.54,
  +1.49]); the primary judge's LLM-only score GO (qwen +0.97 [+0.54,
  +1.40], DiD +0.93 [+0.47, +1.39]; gpt4o +1.20 [+0.60, +1.80], DiD
  +1.13 [+0.49, +1.77]). Condition (iii) is judge-free and unchanged.
  GO on all four scores.
- **The second judge**: Claude Sonnet 5.5 through the Message Batches
  API, an OAuth token from `ant auth print-credentials` at call time
  (verified: a 1-token call, a 2-request batch submitted and fetched
  with fresh tokens; billed to the profile's workspace). Default
  sampling (the API takes no sampling parameter), thinking
  `between_tools`, `max_tokens` 1024. Neither judge is claimed
  deterministic; each judge's k comes from its own repeats.
- **Reliability** (`calibration_v1`, 200 answers, 10 repeats): the
  second judge's k is 1 by the rule (median-of-1 interval alpha Profile
  0.966 [0.951, 0.977], Integration 0.963 [0.947, 0.975]; exact
  self-agreement 0.939 on both, within-1 1.000). The primary judge's k
  is 1 too (2,000 judgments through the kernel, none failed,
  2026-11-20: Profile 0.864 [0.827, 0.893], Integration 0.906 [0.876,
  0.929]; exact self-agreement 0.815 and 0.841, within-1 0.924 and
  0.960; Task alpha 0.989). It passes with less room: 46 of the 200
  answers have Profile repeats 2 or more points apart (the second
  judge: none, on any dimension), and at its first repeat it gives
  Profile 3 to 6 of the 200 answers (the second judge to 66).
- **Agreement between the judges** (`calibration_v1`, each at k = 1):
  alpha Profile 0.498 [0.382, 0.597], Task 0.876 [0.822, 0.911],
  Integration 0.683 [0.608, 0.741]; Spearman 0.69, 0.76, 0.76; the
  second judge lower by 0.69 [0.56, 0.81], 0.36 [0.29, 0.43] and 0.34
  [0.23, 0.46]. Each judge is steady and they rank answers alike, but
  they do not use the scale alike: where the primary judge gives
  Profile 4, the second gives 2 or 3 on 89 of 101 answers. So a judged
  score's level is its judge's ("Notes for the paper" 4).
- **Re-judge** of `pilot_v1_hetero`, `pilot_v1_amem`,
  `bench_v2_smoke_amem` by the second judge (1,350 answers, one batch,
  none failed) and by the primary judge at its k (1,350 answers
  through the kernel, none failed, 2026-11-20).
- **Direction agreement** (Cerebrum
  `results/s20_rejudge/directions.md`): the two judges give the same
  direction on 139 of 164 paired differences, and on 116 of 116 where
  either judge's 95% interval excludes 0. Every difference at H = 1 or
  2 and every H2 − H0 difference agrees (120 of 120); the 25
  disagreements are all at H = 0, both intervals including 0 in each.
- **Spend.** On the second judge, whose budget the user set ($200 for
  the project, $30 for this subtask): checks and measurement about
  $0.19, calibration $7.57, re-judge $4.95: about $12.71. On Azure, the
  kernel's deployment, for which this subtask set no budget (each run's
  cost stated before it ran): the primary judge about $19.62
  (measurement $0.28, calibration $11.65, re-judge $7.69; 3,400 calls,
  none failed; priced at OpenAI's list $2.50 / $15 per million tokens,
  Azure's own price not read), and the decision check's Mem0 cells about
  $18.01 of gpt-4o (Mem0's extraction). In all about $50.34.
- **Metrics in one module** (Cerebrum `metrics.py`): the reports'
  shared measures moved there; the 15 report renderings of 14 stored
  runs (every v2, stress, ablation, heterogeneity and pilot report)
  byte-identical before and after; `profile_facts_in_answer` recorded
  (`judge_free.measure`) and reported (pilot report, `facts_in_answer`,
  recomputed from the record for stored runs).
- **Harness**: `--judge`, `--judge-repeats k` (median, every repeat
  recorded), a judgment's model, timestamps and tokens recorded;
  `rejudge.py` for both judges, repeats and v2 probes;
  `judge_reliability.py`; `pilot_analysis --score`.
- **The second judge's grid subset** (`FULL_GRID.md`): 30% of users by
  index and echo status, fixed now (45 users at 150).
- **The decision probe** (Amendment 10): revision 4 of `users_v2`
  (Cerebrum `87e5aa0`, from revision 3 with no LLM call, check 0
  problems; revision 3 in `repo-artifacts`); `agents_n*` derived again.
- **Functional check** (Amendment 10, in-house, Qwen, users 0-4, 13
  cells, judge-free; `results/decision_functional_s20`): D1 met (23 of
  30), D3 (10 stale of 20 vs 0 of 20), D4 (2 of 4 vs 0 of 4), D5 (6
  foreign of 20 vs 0 of 10); **D2 not met** (0 of 30: the three
  no_memory cells gave the same ten answers, one sample of ten items; 0
  of 10 has probability 0.056 under uniform guessing), recorded as a
  deviation. Native in-house at H = 0 with no fault: 3 of 10 correct,
  7 stale picks (kernel and replicated 10 of 10): supersession's value,
  measured without a judge.
- **The functional check's Mem0 cells** (2026-11-20; harness `968029a`,
  kernel `d49afc9`; 13 cells, 65 of 65 trials, the driver's checks
  passed; gpt-4o for Mem0's extraction, about $18.01): with both
  backends D1 met (47 of 60), D2 not met (0 of 60: six `no_memory`
  cells, one set of answers), D3 (22 of 40 vs 0 of 40), D4 (4 of 8 vs 0
  of 8), D5 (10 of 40 vs 0 of 20). The kernel's and replicated Mem0
  cells score as the in-house ones but for `no_supersession` (4 of 10, 6
  stale) and replicated `wrong_user` (6 of 10). Native Mem0: 4 of 10 at
  H = 0, 1 of 10 under `wrong_user`; its search (k 10) put the correct
  value in none of its 20 blocks, so its right answers and 12 of its 15
  errors were guesses, which the error kinds do not name (its
  `wrong_user` blocks did hold user i − 1's rows: Amendment 10, "The
  functional check's Mem0 cells").
- **The no-memory check over every user** (Amendment 10, added after
  D2 failed, its reading written before it ran; kernel, in-house, Qwen,
  `no_memory`, 150 users, 300 items, `results/decision_nomemory150_s20`):
  accuracy 0.18 [0.14, 0.23], below chance: the correct option is the
  least plausible-sounding without memory (recorded in `METRICS.md`,
  "The items without memory"), and no cue toward the answer by
  Amendment 10's line (0.45). The `foreign` option is picked most (`d1`
  0.35, `d2` 0.39, intervals above 0.25), at a similar rate at every
  letter; `d1`'s stale and `d2`'s correct and private options less than
  chance. A lean to B, the two items pooled (p = 0.03), the letter
  correct least often there; it costs under 0.01 of accuracy (the letter
  rule, below). So this model's accuracy without memory is 0.18, and an
  error names a memory failure only with its value in the block
  (`options_in_block`; 26 of 26 errors of the functional check's
  in-house cells with memory had it, 19 of 33 of its Mem0 cells'). No
  `no_letter`, `multiple_letters` or turn error. Reported by
  `metrics.decision_picks` and the v2 analysis's "Picks by option kind
  and letter".
- **The option shuffle**, checked after D2 (prompted by `d2`'s
  correct letters A 48, B 29, C 46, D 27, p = 0.021): fair (Amendment
  10, "The option shuffle"); revision 4 stands.
- **The grid's letter rule** (decided by the user, 2026-11-20;
  `FULL_GRID.md`, "The decision items"): in the grid a decision
  accuracy is reported with its model's letter distribution beside it.
  The section fixes that and no more. How it is met is proposed there
  for Subtask 23 (open decision 8): each model's `no_memory` cell, the
  accuracy by correct letter with the correct letters evened out, the
  letters of the items an accuracy is computed over, and the share of
  a `no_memory` cell's picks that are the shortest statement. Readings
  added for it, from `users_v2` and the no-memory record (checks added
  in reading; `METRICS.md`, "The items without memory"; Amendment 10,
  "The letters' size"; the script is archived with the run's records):
  - Qwen's lean to B costs under 0.01 (its letters alone would score
    0.247), and 300 items do not settle the sign;
  - one letter throughout scores 0.22 to 0.28 on the 150 users and
    0.13 to 0.37 on `pilot_v2`, whose correct letters are an uneven
    draw (known issue 56);
  - the correct option is alone the shortest statement on 111 of 300
    items (the shortest throughout would score 0.38); Qwen does not
    favor it;
  - the options' subjects carry their kinds by construction: a rule
    that knew each slot's role would score 0.47, and 0.97 knowing the
    item; one prompt does not show the roles;
  - two sentences were too strong and are now exact: "paired
    comparisons are unaffected" holds between cells whose blocks are
    the same, and the p of the letters picked tests a lean in a
    `no_memory` cell only.
  Independent readers checked the text twice before it was committed;
  each check found errors, now fixed. No code changed: the per-model
  rows and the evened-out accuracy are Subtask 23's.
- **Review** (one pass, `a24b6ec`, and one verify pass): 9 findings, 8
  confirmed and fixed (Cerebrum `692319c`, AIOS `20f2447`), one (the
  primary judge's `response_format`) refuted, its doc sharpened:
  1. the inter-judge offset's sign: `report()` paired the judges by
     name, so the offset was primary - second (fixed: primary first);
  2. a decision turn's error failed the user (now recorded, fails
     nothing; no stored run had one);
  3. a v2 trial's assistant tokens and latency left out its decision
     turns (now included, the scope of its backend usage);
  4. the ordinal median-of-k alpha averaged a subsample of the splits
     (now all; the second judge's JSON moved by at most 0.0006, its k
     unchanged);
  5. the decision fields' names and error shares in the docs; 6. a
     failed second judgment and the calibration rows' recording in the
     docs; 7. `directions`' usage line, and nothing checked each
     root's k (now recorded and checked); 8. a resumed second-judge
     calibration's discarded judgments (docstring limit).
  The same 15 renderings are byte-identical after the fixes.
- **Mutation run** (rule 6, once, on the final code: AIOS `9f7f109`,
  Cerebrum `fae6ce1`). Three owners wrote 148 mutants of rules the
  documents state:
  - the judges (`judge.py`, `rejudge.py`, `judge_reliability.py`,
    `pilot_analysis.py`'s scores);
  - the decision probe (`synth_v2.py`'s items, the history's decision
    turns, their scoring and analysis, the driver's decision mode);
  - the metrics module and the reports moved onto it.

  Each ran on a scratch copy against its area's tests, with Ollama,
  behind the loopback-only network guard: 62 killed, 6 of them only by
  `users_v2`'s generator hash (one of those equivalent; no test of its
  own pins the other five: the foreign candidates' and the pool's
  collision filters, `decision_problems`' collision check, `check`
  reading the items, `revised_from`'s hash; no stored item changes
  under any). Each survivor was then rerun against every suite that
  loads its file (Cerebrum `tests/agents`, and `tests/integration` for
  the judges; no AIOS test loads these): 4 more killed, 1 equivalent
  (the primary judge's json_schema `strict`: the kernel's `/query`
  rebuilds the query without `response_format`, and the adapter asks
  for `json_object`). Of the 81 left:
  - 78 now fail a test (Cerebrum `6e912d1`, AIOS `d49afc9`). Each
    was run against its mutant on a clean copy, the unmutated copy
    passing:
    - 31 changed a stored rendering (no verdict). Four golden tests now
      regenerate those renderings from the runs' records, trimmed to
      the fields each report reads (`tests/agents/fixtures/`, 486 KB,
      with the scripts that make them): the functional check's and the
      no-memory check's v2 analyses; Subtask 11's pilot on each score
      (`results/s20_rejudge/pilot_report/`, now committed); and the
      second judge's reliability report. Each must match byte for byte,
      the JSON to a relative 1e-9. The 31, each failing a golden test:
      - the decision probe (9): accuracy's interval (of the passes, low
        then high); the chi-square's degrees of freedom; the `private`
        and `turn_errors` columns; a pick's interval; D2's lower bound;
        D3's and D4's same loci;
      - the metrics (12): the pass matrix's rate; a missing block size
        counted as 0; eight of the keyword score's rules; a private row
        of another agent as a leak; the pilot's facts_in_answer column;
      - the judges (10): the study's seed; bootstrap percentiles and
        resamples; the median-of-k alpha over every split; exact and
        within-1 agreement; the repeats' ordinal alpha; calls with
        failed attempts; the interval's printed upper end; the keyword
        check's LLM scores 1-5.
    - 47 could change a number of a run still to come (the grid,
      Mem0's decision cells, the primary judge's calibration and
      re-judge; all but the grid have since run) and have cases of
      their own:
      - the decision scoring: a letter named twice, a statement in
        another case, a letter beside a letter, an option in the block
        by an alias (519 of `users_v2`'s 1,200 options have one); a
        kind's interval over the items that named one letter;
      - D1-D5 at their edges;
      - the decision turns' backend usage, a write, latency, any
        exception, `options_in_block` and block ages; the driver's
        default phases;
      - the keyword score's name parts and no-keyword cases; the shared
        measures' None rules (an unscored outcome, a missing value
        left out); a write without a row; `profile_facts_in_answer`
        recorded on v1 and v2 trials;
      - the second judge's request (`max_tokens` 1024, thinking
        `between_tools`); a collected batch's id on its first round
        only; the grid's 45-user subset (`FULL_GRID.md`'s list);
        `rejudge`'s batch path; another judge's record kept; a
        re-judged file with a failed trial incomplete; a judged v2
        trial's record, on the trial and its probe;
      - agreement at each judge's median of k; the directions' pooled
        backends, H2 − H0, a zero mean's sign, either interval
        deciding; the pilot report's defaults (the hybrid, the primary
        judge).
  - 3 hold in the code but no test pins them, so this file claims no
    more. None changes a reported number:
    - an answer with some, not all, repeats failed is not returned
      as failed: at the second judge's k (1) it cannot happen, and at
      k > 1 the re-judge raises;
    - a failed second judgment's record on a v2 probe (no report
      reads it);
    - `build`'s seeded cell order (only a rebuild of the committed
      `calibration_v1` would differ).
- **Records**: the runs' provenance and analyses are committed (Cerebrum
  `3716e02`: `decision_functional_s20`, `decision_nomemory150_s20`,
  `judge_reliability_s20`, `s20_rejudge` with `pilot_report/`;
  `968029a`: the primary judge's calibration, its re-judge and the
  direction agreement;
  `de12cbf`: the functional check's Mem0 cells and its analysis over
  both backends, the letter readings' record; `3b9c923`: the
  provenance corrected on the closing check); their raw
  records are in `repo-artifacts/Cerebrum/` (key-scanned).
- **Suites**: at Cerebrum `fae6ce1`, AIOS `9f7f109`, Cerebrum
  `tests/agents` 1,448 passed, 4 skipped, the 19 known failures and 2
  errors by name; AIOS 906 passed, the 7 known `test_mem0_provider`
  errors. With the mutation run's tests (Cerebrum `6e912d1`, AIOS
  `d49afc9`): Cerebrum 1,477 passed, 4 skipped, the 19 known failures
  and 2 errors by name, and known issue 35's two Hypothesis deadline
  failures (`test_summary_props.py`); AIOS 907 passed, the 7 known
  errors. The AIOS set is `tests/modules/memory` (without
  `test_memory.py`), `tests/modules/syscall`,
  `tests/modules/llm/test_decoding.py`, `tests/environment` and
  `tests/modules/scheduler` (this branch has no
  `test_ollama_context_window.py`).
  At Subtask 20's last commits (Cerebrum `de12cbf`, with the AIOS docs
  that close it), the same: Cerebrum 1,477 passed, 4 skipped, the 19
  known failures and 2 errors by name, and known issue 35's two
  Hypothesis deadline failures; AIOS 907 passed, the 7 known errors.
- **Closing check** (2026-11-20, before the tag): two readers, one
  recounting every new figure from the records and one reading the
  claims against the other documents, found 6 errors, all fixed: the
  Azure refusals' start (12:38, not 17:20); two sentences left from the
  in-house half (26 of 26; the 18 and 17 picks of the earlier and the
  later option); a "floor" the new text calls no bound; a lowest cell
  that left out the `no_memory` cells; and a note for the paper that
  settled what is proposed. Also fixed: native Mem0's right answers were
  guesses too, and its `wrong_user` blocks held user i − 1's rows; the
  spend's budgets and their scopes; and the smaller points both readers
  raised (wording and scope; Cerebrum `3b9c923` for the provenance).
- **The Azure refusals** (2026-11-19 12:38 to 2026-11-20 12:00 EST)
  were not Azure's rules changing, and not the key or the calls: a
  second VPN held this machine's default route, so every call left
  from an address outside the allowed network, while the university
  tunnel was up and carried nothing. With it off both deployments
  answered at once. A keyless request gets 401 either way, so the
  check is one authenticated call and the owner of the address the
  traffic leaves from.
- **Open**: each model's `no_memory` cell in the grid (open decision
  8).

## Notes for the paper

What the paper must say, collected as found (Subtask 20 on; earlier
notes stay where they were written, listed here):

1. **The judge score was a hybrid** (found in Subtask 20). The workshop
   paper's "judge score", and every stored score before Subtask 20, is
   round((keyword + LLM) / 2) per dimension (`METRICS.md`, "The three
   scores of a judgment"). The main-track paper states the formula or
   reports the components apart: from Subtask 20 the LLM score (median
   of k) is the judged metric, the keyword score a judge-free metric of
   its own, and the hybrid a continuity column only.
2. **Silent failures**, the motivation's evidence that real memory
   systems fail quietly: the keyword judge fallback (Subtask 4b), stored
   writer status payloads (Subtask 9), Mem0 swallowing extraction errors
   (Subtask 10, Amendment 9), Ollama truncating prompts (known issue
   29), the library dropping retrieval errors and a listing missing an
   acknowledged write (Amendment 2), Mem0's clamped search
   (`NATIVE_USAGE.md`), Mem0 folding a revoked value into another fact
   (known issue 38).
3. **`kernel_private`** resolves §4.1's TODO (Subtask 4 notes).
4. **A judged score's level is its judge's** (Subtask 20). Each judge
   repeats itself well enough for one judgment per answer (k = 1 by
   the rule, both), and the two give the same direction for every
   paired difference either can tell from zero (116 of 116). They do
   not agree on the level: the second judge scores Profile 0.69 and
   Integration 0.34 lower, with inter-judge alpha 0.50 and 0.68. So
   a judged claim holds as a paired difference, which both judges can
   be shown to give one direction, and a judged mean's level is its
   judge's, not comparable with another paper's.
5. **A decision accuracy is reported with its model's letters beside
   it** (the user's rule, 2026-11-20; `FULL_GRID.md`, "The decision
   items"). Without memory Qwen scores 0.18, not 0.25; one letter
   throughout scores 0.22 to 0.28 on the 150 users and 0.13 to 0.37 on
   the pilot's 30; the shortest statement throughout scores 0.38.
   Reading an accuracy against the model's accuracy without memory, and
   comparing accuracies within a model, paired, are proposed there (open
   decision 8). And an error is a recency, deletion or identity failure
   only with its value in the block: native Mem0's blocks held the
   correct value on none of its 20 items in the functional check, so its
   answers there were guesses.

## Open decisions

1. **Native Mem0's install.** The agents run the pinned `mem0ai` 2.0.2
   without its `[nlp]` extra, so spaCy is absent: Mem0 logs "Failed to
   load spaCy" and its search adds no entity boosts. This is Mem0's
   default install. The extra would not repair the ranking: Mem0 keeps
   its entities in a second collection read through the same Chroma
   adapter, so its entity code reads a distance as a similarity too. A
   search skips entity matches nearer than distance 0.5 (cosine above
   0.75) and boosts farther ones in proportion to their distance, and
   any boost divides every score by 1.5 (`mem0/memory/main.py`,
   `_compute_entity_boosts`; `mem0/utils/scoring.py`). The functional
   check and the smoke use the default. Decide before the final runs
   whether native Mem0 is the default install or the full one
   (`NATIVE_USAGE.md`, "Install").
2. **The probes' stored answers** (known issue 45). Resolved in
   Subtask 15: (b), by Amendment 3 (`BENCHMARK_V2.md`). The analysis
   that led to it is in this file's history (AIOS `78c073c`).
3. **Contradiction wording** (known issue 44). Resolved in Subtask 15:
   (a), revision 3 of `users_v2` (Amendment 3).
4. **The v2 budget** (Subtask 15, `f15a`). Resolved on review
   (2026-11-10): 300 kept, but not as option (a), which moved the
   budget criterion to the smoke after a writer-only replay: there is
   no budget criterion in the functional check or the smoke (its
   binding is reported, not required: "cap binds; budget binding is
   reported, not required"; Amendment 4), and the replay was not run.
   It bound in the smoke (`s15b`): in 3 integration probes per
   in-house cell and in 5 probes per Mem0 cell of the kernel and
   replicated loci (known issue 39). The analysis that led to it is in
   this file's history (AIOS `cf7c42f`).
5. **Deletion and supersession** (Subtask 15, step 1). Resolved on
   review (2026-11-10): `DELETION_AND_SUPERSESSION.md`, "Decisions".
   Every proposal was taken except matching, which uses the scorer's
   own matcher with aliases, so that whatever counts as exposure is
   what revocation removes, and the budget (open decision 4). Added on
   review: a tombstone suppresses a later re-write of the value by any
   agent until the user states it again (a new statement of the slot,
   as its writer labels it: `DELETION_AND_SUPERSESSION.md`, "A
   restatement lifts it"), and no read path returns a tombstoned row.
6. **Three choices of Subtask 17**, resolved 2026-11-16 (Subtask 18
   housekeeping): (a) changed, the 118 key heads are masked in place
   (known issue 49); (b) confirmed, and recorded in `FULL_GRID.md`;
   (c) confirmed: a V4 consumer applies its own documented threshold
   to whatever its backend scores, which is the variant's premise, and
   native Mem0's consumer already does. The choices as taken
   (2026-11-12 to 15, not asked):
   (a) known issue 49's 39 local logs are left as they are (gitignored,
   never archived or committed); masking the 118 key heads in place is
   the alternative;
   (b) the full grid's native k = 30 sensitivity cell (Amendment 7) is
   on Graphiti, whose cap of 10 bound in every probe of Subtask 16's
   smoke (about 23 facts per user);
   (c) the review's finding 2, a V4 consumer's 0.5 threshold applied to
   native A-MEM's distance at H = 2, is documented, not changed, as on
   native Mem0 (`NATIVE_USAGE.md`, "native_amem").
7. **Mem0 writes stored as nothing under the stress dimensions**
   (Subtask 18, known issue 53). Resolved 2026-11-18 (Subtask 19):
   (b), `BENCHMARK_V2.md` Amendment 9. Every locus's Mem0 write now
   raises when Mem0 logged and swallowed a failure of it and stored
   nothing (Cerebrum `cerebrum/utils/mem0_errors.py`), so a Mem0 write
   that returned and stored nothing found no fact, and is a lost
   memory (`writes_without_fact`), not a failed trial. The options were
   (a) keep failing the trial, (b) this, (c) leave N = 12 and
   `concurrent` out of the Mem0 cells.
8. **Each model's `no_memory` cell in the grid** (Subtask 20;
   `FULL_GRID.md`, "The decision items"). The user's rule (2026-11-20):
   a decision accuracy is reported with its model's letter distribution
   beside it. A model's letters show its lean only where its picks are
   guesses (a reading there). Options: (a) one `no_memory` cell per
   model over the grid's users, judge-free (Qwen's exists and took 78
   minutes; GPT-4o's about $1.30 at Qwen's token counts); (b) no new
   cell: each cell's
   own letters and the accuracy with the correct letters evened out,
   which Subtask 23 would add to the report; (c) both. Recommended:
   (c).

## Spend to date

API spend of the NeurIPS-2027 work to 2026-11-23 (Subtasks 3 to 20),
from the token counts the runs recorded; no run was made for it. In
all $667.83: $615.08 from runs archived in `repo-artifacts` (both
repos), $52.75 from runs recorded in Cerebrum `results/` and never
archived (marked \* below). By model: gpt-4o $590.40 (of which the
memory backends' extraction $574.12), GPT-5.4 $64.71, Claude Sonnet
5.5 $12.71. The runs under "Not priced" spent more, by amounts not
recorded.

**Method.**
- Sources, each counted once across every copy: the trials' token
  fields (`token_usage`, `writer_tokens`, `backend_llm_tokens` from
  Subtask 7; `judges[*].token_usage` from Subtask 20); the kernel
  logs' usage line for every call the kernel's LLM adapter served,
  tied to its model by its batch and to the judge, the harness or the
  agents by who queued it; the judge study's judgment files; and
  `graphiti_risks.json`.
- The assistant's, the writers' and the judge's calls are taken from
  the kernel logs. Where the trial records hold them too they agree
  exactly (`pilot_v1`, `pilot_v1_9d`, `pilot_v1_hetero`,
  `s9d_determinism`; the Subtask 20 judge log's 3,400 calls equal the
  judgment files and the re-judge records). The memory backends call
  LiteLLM directly, so their extraction is taken from the records.
- "User generation" is the harness's own synthetic users (`synth.py`,
  through the kernel), before the fixed dataset of Subtask 9.
- Stopped, failed and superseded runs are included, as far as their
  records or logs were kept. Local models (Ollama) cost 0. The
  mutation runs made no Azure or Anthropic call.
- Prices per million tokens in / out, the ones used above: gpt-4o
  $2.50 / $10 (`prices.yaml`), GPT-5.4 $2.50 / $15 (OpenAI's list;
  Azure's own not read), Claude Sonnet 5.5 $1 / $5 (the Batch API).
  No cached-input discount is applied.

| Subtask | Run (results folder; run-id prefixes) | Model, use | Tokens in | Tokens out | Cost |
|---|---|---|--:|--:|--:|
| 3 | `revalidation` | gpt-4o assistant, writers | 200,440 | 203,097 | $2.53 |
| 3 | `revalidation` | gpt-4o user generation | 357,773 | 160,361 | $2.50 |
| 3 | `revalidation` | GPT-5.4 judge | 999,374 | 204,674 | $5.57 |
| 4 | AIOS `subtask04` (a) | gpt-4o assistant, writers | 8 | 10 | $0.00 |
| 4 | AIOS `subtask04` (a) | GPT-5.4 judge | 817,413 | 176,871 | $4.70 |
| 5 | `provider_smoke` | gpt-4o assistant, writers | 36,541 | 44,097 | $0.53 |
| 5 | `provider_smoke` | gpt-4o user generation | 47,413 | 19,749 | $0.32 |
| 5 | `provider_smoke` | GPT-5.4 judge | 185,419 | 40,271 | $1.07 |
| 6 | `native_smoke` | gpt-4o assistant, writers | 34,941 | 45,192 | $0.54 |
| 6 | `native_smoke` | gpt-4o user generation | 47,239 | 19,658 | $0.31 |
| 6 | `native_smoke` | GPT-5.4 judge | 191,504 | 40,608 | $1.09 |
| 7 | `cost_check` | gpt-4o assistant, writers | 12,082 | 13,643 | $0.17 |
| 7 | `cost_check` | gpt-4o extraction | 235,801 | 6,912 | $0.66 |
| 7 | `cost_check` | gpt-4o user generation | 15,765 | 6,541 | $0.10 |
| 7 | `cost_check` | GPT-5.4 judge | 22,842 | 4,540 | $0.13 |
| 8 | `locus_smoke` | gpt-4o assistant, writers | 72,287 | 88,656 | $1.07 |
| 8 | `locus_smoke` | gpt-4o user generation | 94,437 | 38,636 | $0.62 |
| 8 | `locus_smoke` | GPT-5.4 judge | 394,074 | 86,612 | $2.28 |
| 8 | `locus_dry` \* | gpt-4o assistant, writers | 1,776 | 2,135 | $0.03 |
| 8 | `locus_dry` \* | gpt-4o user generation | 2,339 | 990 | $0.02 |
| 8 | `locus_dry` \* | GPT-5.4 judge | 8,880 | 1,908 | $0.05 |
| 9 | `fact_check_s9_first` (f) | gpt-4o assistant, writers | 5,150 | 6,376 | $0.08 |
| 9 | `fact_check_s9_first` (f) | gpt-4o extraction | 81,706 | 2,946 | $0.23 |
| 9 | `pilot_v1` | gpt-4o assistant, writers | 139,706 | 145,237 | $1.80 |
| 9 | `pilot_v1` | gpt-4o extraction | 8,412,528 | 197,962 | $23.01 |
| 9 | `pilot_v1` | GPT-5.4 judge | 839,473 | 188,546 | $4.93 |
| 9 | `fact_check_s9` \* (d) | gpt-4o assistant, writers | 18,203 | 17,780 | $0.22 |
| 9 | `fact_check_s9` \* (d) | gpt-4o extraction | 468,393 | 10,301 | $1.27 |
| 9 | `fact_check_s9` \* (d) | GPT-5.4 judge | 33,387 | 7,378 | $0.19 |
| 9d | AIOS `s9d` (f) | gpt-4o assistant, writers | 16 | 20 | $0.00 |
| 9d | `pilot_v1_9d` | gpt-4o assistant, writers | 133,311 | 146,122 | $1.79 |
| 9d | `pilot_v1_9d` | gpt-4o extraction | 8,440,395 | 200,328 | $23.10 |
| 9d | `pilot_v1_9d` | GPT-5.4 judge | 825,723 | 180,877 | $4.78 |
| 9d | `pilot_v1_9d_contaminated` (b) | gpt-4o extraction | 707,674 | 17,822 | $1.95 |
| 9d | `pilot_v1_9d_contaminated` (b) | GPT-5.4 agents | 2,843 | 749 | $0.02 |
| 9d | `pilot_v1_9d_contaminated` (b) | GPT-5.4 judge | 52,156 | 11,253 | $0.30 |
| 9d | `pilot_v1_9d_greedy` (c) | GPT-5.4 judge | 1,006,301 | 219,023 | $5.80 |
| 9d | `s9d_determinism` \* | gpt-4o assistant, writers | 5,184 | 5,706 | $0.07 |
| 9d | `s9d_determinism` \* | GPT-5.4 judge | 20,068 | 4,201 | $0.11 |
| 10 | `heterogeneity_check` | gpt-4o extraction | 876,258 | 19,400 | $2.38 |
| 10 | `heterogeneity_check_interrupted` (f) | gpt-4o extraction | 23,602 | 513 | $0.06 |
| 11 | `pilot_v1_hetero` | gpt-4o assistant, writers | 273,987 | 289,685 | $3.58 |
| 11 | `pilot_v1_hetero` | gpt-4o extraction | 12,634,672 | 320,977 | $34.80 |
| 11 | `pilot_v1_hetero` | GPT-5.4 judge | 1,125,795 | 234,883 | $6.34 |
| 14 | `bench_v2_functional`; f14, f14b, f14c | gpt-4o extraction | 20,552,785 | 192,913 | $53.31 |
| 14 | `bench_v2_smoke`; s14b | gpt-4o extraction | 17,012,678 | 163,156 | $44.16 |
| 14 | `bench_v2_smoke`; s14b | GPT-5.4 judge | 224,945 | 45,433 | $1.24 |
| 15 | `bench_v2_functional_a3`; f15a | gpt-4o extraction | 7,066,646 | 54,413 | $18.21 |
| 15 | `bench_v2_functional_a4`; f15b, f15b2 | gpt-4o extraction | 9,892,269 | 76,552 | $25.50 |
| 15 | `bench_v2_smoke_a4`; s15b | gpt-4o extraction | 12,573,830 | 99,582 | $32.43 |
| 15 | `bench_v2_smoke_a4`; s15b | GPT-5.4 judge | 193,735 | 40,039 | $1.08 |
| 15 | `bench_v2_smoke_a4_s15`; s15 | gpt-4o extraction | 4,191,376 | 33,152 | $10.81 |
| 15 | `bench_v2_smoke_a4_s15`; s15 | GPT-5.4 judge | 32,660 | 6,738 | $0.18 |
| 15 | `bench_v2_try` \*; f15b | gpt-4o extraction | 447,639 | 3,412 | $1.15 |
| 16 | AIOS `s16` | gpt-4o extraction | 46,808 | 1,116 | $0.13 |
| 16 | `bench_v2_functional_graphiti_attempt1`; f16 | gpt-4o extraction | 1,487,231 | 31,536 | $4.03 |
| 16 | `bench_v2_functional_graphiti_failed_cell`; f16b | gpt-4o extraction | 748,325 | 16,015 | $2.03 |
| 16 | `bench_v2_functional_graphiti_failed_cell2`; f16c | gpt-4o extraction | 749,482 | 15,943 | $2.03 |
| 16 | `bench_v2_smoke_graphiti`; s16 | gpt-4o extraction | 13,831,749 | 314,191 | $37.72 |
| 16 | `bench_v2_smoke_graphiti`; s16 | GPT-5.4 judge | 100,392 | 20,176 | $0.55 |
| 16 | `pilot_v1_graphiti_aborted_pg16` (f) | GPT-5.4 judge | 25,473 | 5,199 | $0.14 |
| 16 | `pilot_v1_graphiti_aborted_pg16b` (f) | GPT-5.4 judge | 13,449 | 2,630 | $0.07 |
| 16 | `pilot_v1_graphiti_costcheck`; pg16c | gpt-4o extraction | 31,912 | 1,693 | $0.10 |
| 16 | `pilot_v1_graphiti_costcheck`; pg16c | GPT-5.4 judge | 1,160 | 292 | $0.01 |
| 16 | `pilot_v1_graphiti_try`; pg16t | gpt-4o extraction | 198,626 | 11,943 | $0.62 |
| 16 | `pilot_v1_graphiti_try`; pg16t | GPT-5.4 judge | 6,825 | 1,446 | $0.04 |
| 16 | `s16_try`; g16try1 | gpt-4o extraction | 484,771 | 10,356 | $1.32 |
| 16 | `bench_v2_functional_graphiti` \*; f16b, f16c | gpt-4o extraction | 4,604,266 | 100,475 | $12.52 |
| 16 | `bench_v2_functional_graphiti_a5` \*; f16d | gpt-4o extraction | 6,087,107 | 132,028 | $16.54 |
| 16 | `bench_v2_functional_graphiti_a5b` \*; f16e | gpt-4o extraction | 1,512,106 | 33,531 | $4.12 |
| 16 | `pilot_v1_graphiti` \*; pg16e | gpt-4o extraction | 5,127,720 | 255,831 | $15.38 |
| 16 | `pilot_v1_graphiti` \*; pg16e | GPT-5.4 judge | 195,542 | 39,469 | $1.08 |
| 17 | `bench_v2_functional_amem`; f17 | gpt-4o extraction | 1,636,642 | 311,170 | $7.20 |
| 17 | `bench_v2_smoke_amem`; s17a | gpt-4o extraction | 2,089,295 | 399,641 | $9.22 |
| 17 | `bench_v2_smoke_amem`; s17a | GPT-5.4 judge | 93,212 | 19,236 | $0.52 |
| 17 | `bench_v2_smoke_s17`; s17, s17b | gpt-4o extraction | 22,210,572 | 381,265 | $59.34 |
| 17 | `bench_v2_smoke_s17`; s17, s17b | GPT-5.4 judge | 239,407 | 49,223 | $1.34 |
| 17 | `pilot_v1_amem`; pa17 | gpt-4o extraction | 608,117 | 93,832 | $2.46 |
| 17 | `pilot_v1_amem`; pa17 | GPT-5.4 judge | 182,285 | 37,032 | $1.01 |
| 17 | `pilot_v1_graphiti_native_filter`; pg17n | gpt-4o extraction | 1,707,706 | 86,678 | $5.14 |
| 17 | `pilot_v1_graphiti_native_filter`; pg17n | GPT-5.4 judge | 64,246 | 12,978 | $0.36 |
| 18 | `scheduler_check_s18`; s18sched | GPT-5.4 judge | 19,998 | 4,187 | $0.11 |
| 18 | `stress_functional_f18b`; f18b to f18e, f18r1 to f18r31 | gpt-4o extraction | 40,148,211 | 280,649 | $103.18 |
| 20 | `decision_functional_s20_mem0`; d20a, d20m | gpt-4o extraction | 6,982,522 | 55,668 | $18.01 |
| 20 | `judge_reliability_s20` (e) | Claude second judge | 3,505,382 | 850,628 | $7.76 |
| 20 | `judge_reliability_s20` (e) | GPT-5.4 judge | 2,125,847 | 440,848 | $11.93 |
| 20 | `s20_rejudge` (e); pa17, s17a | Claude second judge | 2,261,458 | 538,502 | $4.95 |
| 20 | `s20_rejudge` (e); pa17, s17a | GPT-5.4 judge | 1,370,502 | 284,410 | $7.69 |

(a) The re-judge of Subtask 3's 900 responses (Cerebrum
`revalidation_v2`, whose folder holds no kernel log).
(b) Its kernel log also holds `pilot_v1_9d`'s kmem0 `kernel_private`
Qwen cell (30 judge calls), whose log in `pilot_v1_9d` the rerun
replaced. The GPT-5.4 agents' calls are the contamination (4 of them
batched with the judge).
(c) The greedy judge's re-judge and retest of `pilot_v1_9d`.
(d) The agents' calls are from the trial records (100 calls; the
kernel logs hold 65).
(e) From the judgment files (`judge_reliability_s20`) and the trial
records (`s20_rejudge`).
(f) Incomplete: see "Not priced".

**Totals** (from the unrounded row costs; the rounded rows above
sum to $667.82).

| Model, use | Tokens in | Tokens out | Archived | Not archived | Cost |
|---|--:|--:|--:|--:|--:|
| gpt-4o extraction | 213,911,420 | 3,933,902 | $523.14 | $50.97 | $574.12 |
| gpt-4o assistant, writers | 933,632 | 1,007,756 | $12.09 | $0.32 | $12.41 |
| gpt-4o user generation | 564,966 | 245,935 | $3.86 | $0.02 | $3.87 |
| **gpt-4o, all uses** | 215,410,018 | 5,187,593 | $539.09 | $51.31 | $590.40 |
| GPT-5.4 judge | 11,412,087 | 2,410,981 | $63.26 | $1.44 | $64.69 |
| GPT-5.4 agents | 2,843 | 749 | $0.02 | $0.00 | $0.02 |
| **GPT-5.4, all uses** | 11,414,930 | 2,411,730 | $63.27 | $1.44 | $64.71 |
| **Claude Sonnet 5.5** | 5,766,840 | 1,389,130 | $12.71 | $0.00 | $12.71 |
| **Overall** | 232,591,788 | 8,988,453 | $615.08 | $52.75 | $667.83 |

**Not priced** (no usage recorded, or records incomplete; not
estimated). Call counts are from the LiteLLM log, two lines per call.
- `users_v1` generation (Subtask 9, `users_v1_generate.log`): 623
  gpt-4o calls, no usage logged.
- `users_v2` revisions 1 to 3 (Subtasks 14 and 15,
  `users_v2_revisions/`): 179 gpt-4o calls (r2), 304 (r3 draft) and
  344 (r3); r1's log was not archived. Revision 4 made no LLM call.
- `bench_v2_functional_a4_killed_f15b` (15): 73 Mem0 gpt-4o calls,
  killed before a trial was written.
- `pilot_v1_graphiti_aborted_pg16` and `_pg16b` (16): 452 and 230
  Graphiti gpt-4o calls; their 23 and 12 judge calls are priced.
- AIOS `s9d` (9d): 39 Mem0 gpt-4o calls in the kernel smokes; its 2
  assistant calls are priced.
- `heterogeneity_check_interrupted` (10): 15 gpt-4o calls in its log,
  3 of them in finished trials' records and priced.
- `fact_check_s9_first` (9): the judge calls of its 15 judged trials
  (no kernel log archived); its agents' and extraction calls are
  priced from the records.
- `fact_check_s9` \* (9): 5 of its 40 judge calls are missing from its
  kernel logs.
- `pilot_v1_9d_contaminated` (9d): 12 calls in batches that mixed
  GPT-5.4 and Qwen (1,647 in, 1,257 out), not tied to one model.
- Subtask 9c (`s9c/`): its scripts' direct GPT-5.4 judge calls (240
  ablation answers and the top-5 re-judges), no usage recorded.
- Subtask 20: the Claude one-token check, the two-request batch and
  the Azure probes have no record in the archive.
- A cell killed and rerun is counted only as far as its partial
  results or logs were archived.
- Subtasks 1, 2 and 4b archived no run; Subtask 19's runs called only
  local models.

## Test baselines

These fail on `workshop-postrun` too and are not caused by later work.

- AIOS: `tests/modules/memory/test_memory.py` fails at collection, and 14
  tests in `test_mem0_provider.py` / `test_zep_provider.py` error (their
  `manager` argument is collected as a missing fixture); 7 since Subtask
  16, which deleted `test_zep_provider.py`.
- Cerebrum `tests/agents`: 19 failures, 2 errors at
  `neurips-subtask-03` (one flaky test makes it 19 or 20); unchanged at
  `neurips-subtask-07` (AIOS 310 passed, Cerebrum 303 passed) and
  `neurips-subtask-08` (AIOS 315 passed, Cerebrum 307 passed) and
  `neurips-subtask-09` (AIOS 321 passed, Cerebrum 340 passed) and
  `neurips-subtask-09d` (AIOS 349 passed, Cerebrum 353 passed; run with
  no kernel listening, see known issue 25) and `neurips-subtask-10`
  (AIOS 373 passed; Cerebrum `tests/test_live_kernel_guard.py
  tests/agents` 412 passed, 4 skipped, the same 19 failures and 2
  errors) and `neurips-subtask-11` (AIOS `tests/modules/memory`
  without `test_memory.py`, `tests/modules/syscall`,
  `tests/modules/llm/test_decoding.py`, `tests/environment`: 379
  passed, the 14 errors; Cerebrum 428 passed, 4 skipped, the same 19
  failures and 2 errors) and Subtask 14's fixes (AIOS `e3cdc52`,
  Cerebrum `9946612`; AIOS the same set: 468 passed,
  the 14 errors; Cerebrum 860 passed, 4 skipped, the same
  19 failures and 2 errors, by name) and the end of Subtask 14
  (Cerebrum `8dbea1e`, which adds 8 tests; AIOS unchanged:
  468 passed, the 14 errors; Cerebrum 868 passed, 4 skipped, the same
  19 failures and 2 errors, by name) and Subtask 15's step 0 (Cerebrum
  `596451c`, AIOS `38696f3`: AIOS 470 passed, the 14 errors; Cerebrum
  900 passed, 4 skipped, the same 19 failures and 2 errors, by name)
  and Subtask 15's step 1 code (AIOS `210aa58`, Cerebrum `059e5a5`:
  AIOS 606 passed, the 14 errors; Cerebrum 1050 passed, 4 skipped, the
  same 19 failures and 2 errors, by name) and its smoke's fixes
  (Cerebrum `64da5f7`: 1056 passed; `0995994`: 1062 passed; 4 skipped,
  the same 19 failures and 2 errors, by name; AIOS unchanged) and the
  review's fixes (AIOS `c814a5d`, Cerebrum `ec623ab`: AIOS 632 passed,
  the 14 errors; Cerebrum 1064 passed, 4 skipped, the same 19 failures
  and 2 errors, by name) and the verification pass's (AIOS `8db0b35`,
  Cerebrum `ca91a13`: AIOS 635 passed, the 14 errors; Cerebrum 1064
  passed, 4 skipped, the same 19 failures and 2 errors, by name) and
  the mutation run's tests (Cerebrum `c2f1ed3`: 1082 passed, 4
  skipped, the same 19 failures and 2 errors, by name; AIOS unchanged:
  635 passed, the 14 errors) and the end of Subtask 16 (AIOS
  `789eb67`, the same set: 677 passed, the 7 errors; Cerebrum
  `6a29089`: 1133 passed, 4 skipped, the same 19 failures and 2
  errors, by name; known issues 6 and 47 are flaky under load) and
  Subtask 17's review fixes (AIOS `34833e7`, Cerebrum `1d7d99f`; iCloud's
  copies no longer collected: AIOS 754 passed, the 7 errors; Cerebrum
  1162 passed, 4 skipped, the same 19 failures and 2 errors, by name,
  and one of known issue 35's two deadline tests) and the end of
  Subtask 17 (AIOS `ec3c467`, Cerebrum `062d12c`: AIOS 764 passed, the
  7 errors; Cerebrum 1173 passed, 4 skipped, the same 19 failures and 2
  errors, by name) and Subtask 18's code (AIOS `c389539`, the set now
  with `tests/modules/scheduler`: 816 passed, the 7 errors; Cerebrum
  `d876f0f`, `tests/agents`: 1208 passed, 4 skipped, the same 19
  failures and 2 errors, by name) and its review fixes (AIOS `d451801`:
  821 passed, the 7 errors; Cerebrum `8ef6d6f`, with
  `tests/test_live_kernel_guard.py`: 1226 passed, 4 skipped, the 19
  failures, one of known issue 35's two and the 2 errors) and the
  report (Cerebrum `4279ce6`: 1231 passed, 4 skipped, the 19 failures
  and 2 errors, and once
  `test_write_barrier_determinism.py::test_determinism_under_latency_permutation`,
  known issue 35) and the write-up review's fixes (Cerebrum `7a149ab`:
  1231 passed, 4 skipped, the 19 failures, one of known issue 35's two
  and the 2 errors; AIOS unchanged) and Subtask 19's verification pass
  (AIOS `94c2385`, Cerebrum `8953e28`: AIOS 893 passed, the 7 errors;
  Cerebrum 1,360 passed, 4 skipped, the 19 failures and 2 errors, by
  name, and known issue 35's `test_kernel_shared_delta_is_zero`) and
  its mutation run's tests (Cerebrum `7d19bf4`: 1,373 passed, 4
  skipped, the 19 failures and 2 errors, by name, and known issue 35's
  `test_kernel_shared_delta_is_zero`; AIOS 904 passed, the 7 errors) and
  Subtask 20 (AIOS `9f7f109`, Cerebrum `fae6ce1`: AIOS 906 passed, the 7
  errors; Cerebrum 1,448 passed, 4 skipped, the 19 failures and 2
  errors, by name) and its mutation run's tests (Cerebrum `6e912d1`:
  1,477 passed, 4 skipped, the 19 failures and 2 errors, by name, and
  known issue 35's two; AIOS 907 passed, the 7 errors; the AIOS set
  since Subtask 18 adds `tests/modules/scheduler`) and
  Subtask 20's last commits (Cerebrum `de12cbf`, with the AIOS docs that
  close it: the same counts, known issue 35's two).
  The names
  are in the Subtask 4 notes: the 4 `test_kernel_private_unit.py`
  failures test a removed local-Mem0 path.

## Known issues

1. Fixed in Subtask 5: Mem0 and in-house search are scored, so
   `relevance_threshold` applies (default 0.0).
2. Workshop provenance: the 1,800 trials span several code states and
   recorded no commit, config or injected sets. See the `mem0_default`
   note: gpt-4o ran before Cerebrum `6255bee`, llama and qwen after.
3. `config.yaml` (10 / 2000) and `config.yaml.example` (5 / 1500) still
   differ on `max_injected_memories` / `max_memory_tokens`; both set
   `relevance_threshold` 0.0 since Subtask 5.
4. Closed in Subtask 16 (the Zep provider is removed): `get_memory`,
   `update_memory` and `remove_memory` on Zep always answered "not
   found", Zep episodes carrying no owner. Any row stored without an
   `owner_agent` still fails closed.
5. Fixed in Subtask 5: `update_memory` is stamped against the barrier.
6. `test_write_barrier_stress.py::Scenario2DisjointUsersTests` is flaky:
   it compares sub-millisecond medians. It failed 5 of 8 runs at
   `workshop-postrun`, 3 of 8 at `neurips-subtask-01`, 6 of 8 at
   Subtask 2. Treat a failure of it alone as noise.

7. Azure gpt-4o does not honor the requested JSON response format: about
   a third of replies arrive fenced. Harness parsers now tolerate it
   (`parse_json_reply`); other agents' `json.loads` calls do not.
8. Qwen's replies changed between the workshop and Subtask 3 (median
   `mem0_default` reply 2,010 to 859 characters). Cause unknown; the
   workshop recorded no Ollama or model version. Record both from here on.
9. Fixed in Subtask 4b: a judge failure after retries fails the trial;
   there is no keyword-only fallback.
10. The harness's post-ProfileAgent diagnostic (`pipeline.py`) searches
    without a `user_id`, so it looks in the agent's own scope and warns
    "0 results" on every trial (also in all of Subtask 3). Noise only.
11. Closed in Subtask 16 (the Zep provider is removed): Zep did not
    conform to the provider contract (no metadata, no `list` /
    `update`); Graphiti does (`docs/GRAPHITI_BACKEND.md`).
12. Mem0's collections use Chroma's default squared-L2 space; the cosine
    conversion assumes unit vectors, which the pinned model returns. A
    model that does not would need its collections created in cosine
    space.
13. The two native conditions differ from the kernel conditions in
    what they store, not only in who stores it: natural-language
    renderings (and, for Mem0, gpt-4o-extracted facts) rather than the
    writers' JSON with the kernel's formatter at injection. Compare them
    with that in mind.
14. Fixed in Subtask 7: native Mem0's extraction cost is recorded
    (`backend_llm_tokens`), about 24,000 tokens and 0.066 USD per GPT-4o
    trial.
15. Fixed in Subtask 18 (AIOS `c389539`): the FIFO scheduler's LLM
    thread blocks on its queue and runs what is queued as one batch, in
    arrival order, with no `batch_interval`. Before: it waited up to
    `batch_interval` (1.0 s) before running an LLM request, so
    sequential requests waited about the full second (14% of
    `kernel_shared` latency on GPT-4o). Measured on pilot_v1, 10 users:
    `schedule_wait_ms` median 845 ms before, 1.0 ms after, blocks and
    answers identical (`results/scheduler_check_s18`).
16. The harness's user-less post-ProfileAgent diagnostic search (known
    issue 10) is tagged with the agent name, not the trial's user, so
    its embedding call is not counted in the trial. It is harness
    instrumentation, not part of any condition.
17. Fixed in Subtask 9d: `mem0ai` is 2.0.2 in both venvs, pinned in
    both `requirements.txt`. (2.0.2 builds its default OpenAI LLM when
    constructed, so the replicated Mem0 agents still give it
    `memory.backend_llm` through LiteLLM.)
18. Cerebrum has a tracked `aios/` stub, imported by some of its tests,
    that shadows the kernel's `aios` package in the same interpreter.
    The replicated agents' checks therefore run in a subprocess, and
    `library.load()` fails with a clear message if the stub is already
    imported.
19. The kernel's conversation write runs on a background thread after
    the reply; the replicated assistant's runs synchronously after it.
    Both are outside measured latency, and the next trial is a new user,
    so neither can affect a score here (docs/REPLICATED_LOGIC.md).
20. Fixed in Subtask 9: cells are paired on the fixed dataset
    `users_v1` (`pilot_v1` = its first 30 users).
21. Fixed in Subtask 9: writers validate their extraction, retry twice,
    and on failure store nothing and fail the trial (`writer_failed`).
22. `users_v1` is skewed: 122 of 150 users prefer Python (the rest
    JavaScript), and Visual Studio Code, Docker, Git and Postman make up
    most tools; 104 distinct queries, one asked 17 times. Fine for
    paired locus comparisons; a limit on any claim about attribute
    coverage.
23. With `memory.mem0.infer` one write can store several Mem0 facts but
    returns only the first id, so a later `update_memory` by that id
    replaces one fact and leaves the others. Harmless in single-write
    trials (pilot_v1); the accumulating benchmark needs an update rule
    for extracted facts.
24. Azure GPT-4o treats the seed as best effort. Under fixed decoding,
    GPT-4o answers differ between runs (5 of 5 users), as do the greedy
    judge's scores (8% of profile scores differ on a test-retest). In
    Subtask 17's natural test-retest (165 pilot_v1 answers identical to
    Subtask 11's, judged a week apart by the same prompt, seed and
    temperature), 24% of profile, 1% of task and 16% of integration
    scores differ, with mean differences within 0.03. Qwen and Llama on
    Ollama are deterministic. GPT-4o and judge noise remain, so compare
    cells paired and with CIs. Within one pass too: in Subtask 18's
    scheduler check, 20 identical answers judged one after the other
    got different scores in 5 of 10 profile and 4 of 10 integration
    pairs, so a behavior-preserving change is shown by identical blocks
    and answers, not by equal scores.
25. Fixed in Subtask 10 (Cerebrum `8ed13d5`): the guard is ported;
    tests that need a kernel are marked `live_kernel`. Before: Cerebrum on this branch had no `tests/conftest.py` kernel guard (it
    exists only on `feature/self-improving-memory`), so `pytest
    tests/agents` sends real requests to any kernel on port 8000. On
    2026-11-05 it did so during the 9d re-baseline: test user
    `eve_davis__kernel_private`, 17:22-17:24, during Qwen Mem0
    `kernel_shared` trials 0-2. That cell was re-run; two suite
    failures in that run came from the live kernel. Rule 5 is the only
    protection. Porting the guard (by hand) is a candidate for
    Subtask 10.
26. Fixed in Subtask 10: Mem0's extraction runs at temperature 0.0 and
    seed 20261105 in both loci. Azure treats the seed as best effort,
    so Mem0 cells still vary by about ±2 injected rows. Before: Mem0's own extraction (`memory.backend_llm`, Azure gpt-4o,
    temperature 0.1, no seed) is outside the fixed decoding, so a Mem0
    cell is not repeatable. In the re-run Qwen `kernel_shared` cell the
    injected count differed from the first run in 14 of 30 users and no
    answer matched. In-house cells do not have this. Putting it under
    fixed decoding is an open choice and would need the Mem0 cells
    re-run.
27. Judge retries repeat at greedy decoding: a retry after an
    unparseable reply gets the same reply, so only transport errors
    benefit. No re-judge trial needed a retry (900 of 900 in one
    attempt). A sampled retry schedule like the writers' is an option.
28. `retrieval_smoke.py`'s verbatim-storage checks are skipped when
    Mem0 `infer` is on (extracted facts are not the written text). They
    run, and pass, with `infer` off.
29. Fixed in Subtask 14: the adapter passes `num_ctx` to every
    `ollama/*` call, from `llms.context_window` (default 16384), and
    the reply's `decoding` records it. Before: no `num_ctx` was set,
    and Ollama 0.40.11 cut a long prompt silently. A prompt of 8,354
    tokens with a code in its first line came back as 2,050 prompt
    tokens and a wrong code; with `num_ctx` 16384, all 8,354 were read
    and the code was right. A 3,154-token prompt was read whole either
    way. The pilot's largest Qwen prompt was 456 tokens, never cut.
30. Fixed in Subtask 10: `chromadb==1.5.9` is pinned in both repos.
31. Fixed in Subtask 11 (AIOS `d3370f4`): an id longer than the limit
    keeps its head plus a 10-character SHA-256 digest. The sanitizer
    still maps characters it drops to `_`, so ids differing only there
    (`a.b`, `a_b`) share a collection. The user filter keeps them
    apart, as before. Before: the kernel's Mem0 per-user collection names keep only the first 49
    characters of the user id (`_collection_name_for_user`, prefix
    `mem0_memories`), with no hash, so two long ids can share a
    collection. The user filter and the partition check keep their
    rows apart, so this is not a leak, but a shared collection mixes
    stores. The native backend adds a hash. Not fixed here.
32. Mem0 swallows extraction LLM errors (Azure firewall refusals
    included) and stores nothing. Since Subtask 10 the harness fails
    such trials (`backend_extraction_failed`). In v2 the check reads
    each write's rows in the listing after its session, so until
    Cerebrum `64da5f7` it also failed a write whose rows a forget later
    in that session deleted: the smoke's first attempt (`s15`), kernel
    Mem0, user 19 (`u019-e08`, a fold of the revoked codename; known
    issue 38). It now excuses a write whose reply named rows that its
    own session removed, every one, and a suppressed write; any other
    write whose reply named no row still fails. Any other caller of
    Mem0, including the kernel's own conversation writes, still gets an
    empty result with no error.
33. Two Subtask 10 native Mem0 H0 runs were excluded: one was cut off
    by a laptop shutdown, the other ran from a network Azure refused.
    Both are in `repo-artifacts/Cerebrum/heterogeneity_check_interrupted/`.
    The resumed driver also overwrote the first `kernel_agent.log`; the
    log from the 2026-11-07 resume was archived before the second run.
34. Fixed in Subtask 11 by the balanced schedule
    (`pilot_v1_schedule.json`). Before: the heterogeneity schedule's first 5 users never pair a V3 consumer
    with a V1 or V3 writer, so they give no native leak opportunity,
    and they place V5 writers outside the kernel only next to a V2 or
    V4 consumer. A scored heterogeneity run needs more users, or a
    schedule that guarantees those pairings.

35. `test_summary_props.py`'s two Hypothesis tests,
    `test_kernel_shared_delta_is_zero` and
    `test_delta_equals_arithmetic_difference`, sometimes hit
    Hypothesis's deadline (timing, not logic, 200 ms; more often under
    load); they make the Cerebrum failure count 19, 20 or 21. So can
    `test_write_barrier_determinism.py::test_determinism_under_latency_permutation`
    (Subtask 18, once in the suite: its barrier stand-in waited 611 ms
    against a 500 ms timeout for two 370 ms writes; it passes alone, and
    Hypothesis calls it flaky), and
    `test_write_barrier_bounded_wait.py::test_bounded_wait_property`
    (once in Subtask 18's mutation run, 399 ms against 160 under
    load). In AIOS, so can `test_write_barrier_pbt.py`'s
    `test_disjoint_user_retrieval_is_not_delayed` (once, in Subtask
    18's final suite: its first call failed and Hypothesis's repeat
    passed; it passes alone), making the AIOS failure count 0 or 1.
36. Nothing resets the memory stores between runs. The kernel keeps
    one set for every run and prefix: its Chroma stores
    (`.mem0/chroma`, `.aios_state/chroma_inhouse`), its tombstones
    (`memory.tombstones_path`, `.aios_state/tombstones.sqlite`) and its
    Mem0 history (`.mem0/history.db`). The native and replicated stores
    are one per run prefix (`.native_memory/<prefix>`,
    `.replicated_memory/<prefix>`, each replicated backend with its own
    `tombstones.sqlite` and Mem0 `history.db`). Isolation rests on run
    ids in user ids, so re-running a cell under the same run id sees
    the earlier attempt's rows and, since Subtask 15 step 1, its
    tombstones: the re-run's statement of a fact the earlier attempt
    forgot replays a forgotten event, so the sweep deletes it and every
    echo of the value as soon as they are written, and its deletion
    probe passes without testing the forget. The forgets reading shows
    it: in a clean cell `suppressed` and `swept` are 0 and each forget
    deletes the slot's row. On Mem0 the sweeps have already deleted the
    value's messages, so the forget scrubs none, and the functional
    check's "every Mem0 forget at H = 0 scrubbed a message" fails;
    in-house, and in the smoke, which runs no criteria, nothing fails.
    Give a re-run its own run id (as Subtask 11 and `f15b2` and `s15b`
    did); the driver now requires `RUN_PREFIX` and `OUTROOT`. For a
    kernel cell a fresh store is not enough: the tombstone file is
    outside it.
37. Every v2 user has one probe of each type, so a cell's per-probe
    rate rests on n = 30 users in the smoke and 5 in the functional
    check. Report Wilson intervals and compare cells paired over users.
38. Fixed in Subtask 15, step 1, for the kernel and replicated loci
    (AIOS `a610dcd`, Cerebrum `059e5a5`): a revoke there is a forget,
    which deletes every carrier of the value, of any agent, folds
    included; in `f15b` no
    audit at H = 0 kept one. `f15b`'s forgets deleted no fold (each
    cell's value deletions were users 0 and 4's echoes). The smoke's
    first attempt (`s15`, kernel Mem0) deleted the folds of users 13,
    19 and 25, `s14b`'s three. A fold row also states its own fact, so
    users 13 and 25 lost their recall targets' only rows and failed
    recall, which `s14b` passed; user 19's fold was in a write just
    before the revoke in its session, which the extraction check then
    misread (known issue 32). The smoke (`s15b`) deleted the folds of
    users 13 and 25 in kernel and replicated Mem0, at the same cost;
    user 19's did not recur there. Native Mem0 kept all three folds
    (users 13, 19 and 25): 13's and 19's failed deletion through the
    fold (19's in `u019-e08`), and 25's fetch missed its fold. Native
    deletion stays writer-scoped
    (`DELETION_AND_SUPERSESSION.md`, Decision 4). There, under the
    `writer_scoped` control, and in every locus before step 1, a
    revoke leaves in place:
    - an echo of the value in another writer's rows;
    - any assistant conversation row that quoted the value;
    - in Mem0 cells, another fact's row by the same writer into which
      Mem0's extraction folded the value. A revoke deletes by
      `fact_key`, so it misses the fold. The extraction sees the fact
      while its row exists and in the writer's last 10 messages, which
      a delete leaves, so a write before or after the revoke can fold
      it. `f14c` showed a fold only under `no_delete` (user 1's database
      row, written after the no-op revoke, took the codename). 27 of
      the 30 `pilot_v2` users have a same-writer write between an add
      and its revoke, and all 30 counting writes after it.
      `bench_v2_analysis.py` classifies each deletion failure by the
      sources of its block's rows that hold the value
      (`rows_with_forbidden`), and each deletion probe, failed or
      passed, by what the store kept (`revoked_value_rows`, after the
      history). The smoke (`s14b`, H = 0) showed folds in real
      conditions, each in the task writer's next write after the add,
      before the revoke: users 13, 19 and 25 in kernel and replicated
      Mem0, all three failing through the fold, and users 13 and 25 in
      native Mem0, where user 25 passed because its fetch missed the
      fold; the fold then reached its recency and contradiction
      blocks, and both answers named the value. User 13's store also
      kept the echo row, which did not reach its deletion block. The
      store kept a carrier behind 21 passes: all 20 echo-user passes
      across the six cells, and native Mem0 user 25's. Native's fetch
      left the carrier out in 11 of them; in the 10 in kernel and
      replicated, whose fetch returned every stored row, the cap did.
      Under Amendment 3 (`f15a`, users 0 to 4), the real conditions'
      deletion failures came through the echo rows of users 0 and 4,
      and once through a fold (replicated Mem0, H = 0, user 1). Under
      Amendment 4 (`f15b`), they were native in-house's, through the
      same echo rows.
39. `config.yaml` keeps `max_memory_tokens: 2000` for v1. v2 runs set
    300 through the driver (`BENCHMARK_V2.md`, Amendment 3; 500 under
    Amendment 1), and the pre-flight check refuses anything else. In
    `f15a` and `f15b` it bound in no in-house probe (open decision 4);
    in the smoke (`s15b`), in 3 integration probes per in-house cell of
    the kernel and replicated loci.
40. Fixed in Subtask 14 (Amendment 2, AIOS `554a408`): the kernel's
    conversation rows carry `provenance_event`, the probe that wrote
    them, as the replicated and native assistants' do. In `f14c`, 382
    of 382 injected kernel conversation rows carry it (`f14b`: 0 of
    371). They still carry no `provenance_agent` or `provenance_user`.
    Scoring reads those (`probes.row_source`, `judge_free.measure`) and
    otherwise uses `owner_agent` and `user_id`, which these rows carry
    (`assistant_agent` and the trial's user id, 382 of 382), so no
    kernel score depends on them.
41. Revision 2's wording (from its review, which found that it changes
    no score; the smoke suggests the second item can change a
    contradiction score):
    - 23 of the 25 pairing revokes read "Please forget the pairing I'm
      involved in." A revoke's text is never stored or shown to a
      model.
    - 14 of the 59 pairing adds read awkwardly ("I'm working in a
      pairing with …"). Three are recall targets (users 43, 100 and
      145), stored verbatim in in-house cells. Seven are a
      contradiction's earlier statement, four of them in `pilot_v2`
      (users 8, 17, 20 and 26). In the smoke, kernel and replicated
      Mem0 stored 7 of those 8 rows without "pairing" ("in
      collaboration with", "collaborating with"), and those 7
      contradiction probes passed 5; the other 5 teammate rows kept
      "pairing" (user 8's in replicated Mem0, and all 4 of users 5 and
      11, whose adds read "I'm pairing with …") and passed none
      (Subtask 14, "Smoke").
    - User 75's contradiction reads "I'm only presenting at Bytewave
      Forum for a conference."
    Revision 3 keeps these, except the contradictions' earlier
    teammate statements, whose template changed (users 8, 17, 20 and
    26 now read "I pair with … each day" or "I work on this project
    with … each day as a pair"). It adds others, none of them in
    revision 2, all in contradiction statements: 20 of the 31 home_city
    later statements read "My location is based in X." (10 per lean;
    `pilot_v2` users 7, 10, 13 and 16); six home_city earlier statements
    read "My home is where I live, in X." (user 133's without the comma;
    `pilot_v2` user 13) and three "My home is in X, where I live."
    (users 16, 37 and 103); two client earlier statements read "We're
    creating and building this project for X." (users 23 and 116); and
    user 73's earlier manager statement reads "I am under Callum Reyes
    and report to him.", the only gendered pronoun in the file's
    utterances and the only third-person pronoun among the 214
    statements revision 3 changed (56 choir statements use "them" and
    63 offsite statements "its").
    - 18 of the 31 home_city earlier statements read "I currently live
      in X." (revision 2: "My home is in X."), the only time word any
      contradiction statement adds to its template; neither the lean
      rule nor `LEAN_MEANING` sees it. `users_v2` has 9 per lean;
      `pilot_v2` has 1 earlier-leaning (user 4) and 2 later-leaning
      (users 7 and 22). In `s15b` native in-house, whose blocks held
      both values, all three failed and their answers repeat
      "currently"; users 7 and 22 are that cell's only later-leaning
      failures. In `f15b`'s `no_supersession` cells user 4's stale row
      came first in all four kernel and replicated blocks; three passed
      ("You currently live in Dunedin") and replicated Mem0 named both
      values. A later revision should reject a time word a statement's
      template lacks.
42. Mem0's extraction (gpt-4o) changes what is stored from run to run:
    - Its prompt holds the current UTC date, which it writes into facts
      ("relocated to bittern-06 on November 9, 2026"). `f14b`'s
      kernel Mem0 phase ran before 00:00 UTC and its agent phase after,
      so its kernel Mem0 cells were extracted under November 8 and its
      replicated and native Mem0 cells under November 9; all of `f14c`
      ran on 2026-11-09 UTC. Keep a run's Mem0 phases on one UTC date
      (00:00 UTC is 19:00 EST), or report the date per cell, as
      `f15b`, which crossed it, does in its `PROVENANCE.md`.
    - It can drop a conflict cue: user 0's "the only person I have a
      weekly one-on-one with" was stored without "only", as an addition
      ("User has a weekly one-on-one meeting with Sofia Lindqvist."),
      in 7 of 7 cells that sent Mem0 the utterance. At H = 2 user 0's
      task writer is V5 and sends the event's fields instead; in kernel
      Mem0 that row states the change.
    - It can fold a value into another fact's row (known issue 38).
    All 28 Mem0 probes whose pass, lenient pass or forbidden-value
    checks changed between `f14b` and `f14c` (18 in pass or fail)
    changed through extraction differences (6 of them also involve a
    revised utterance). Read kernel against replicated on Mem0 as
    paired runs of an extractor that varies.
43. A privacy or deletion probe checks only its own block and answer,
    so a pass can hide the value in the trial's other probes:
    - Privacy, where the consumer ignores visibility. Native in-house,
      H = 2, user 4 (V3) had the private row in 5 of 6 blocks. Native
      Mem0's V3 consumer (H = 2, user 4) passed privacy, but the row
      reached 3 other blocks and its integration answer named the
      lawyer. Under `no_visibility`, native Mem0 had it in some block
      for 5 of 5 users, while its privacy probe failed for 1. No kernel
      or replicated block held a private value.
    - Deletion, for echo users wherever a revoke is writer-scoped
      (native, the `writer_scoped` control, and every locus before
      Subtask 15 step 1): the echo row survives the revoke (known
      issue 38). In `f14c`, at H = 0 and 2, 7 of the 11
      echo-user deletion passes had it in a later block (kernel and
      replicated 4 of 6, native 3 of 5); the other 4 are H = 2 user 0's
      V2 consumer, whose blocks held no writer row. In kernel Mem0 at
      H = 2, 4 of user 0's later answers named Mattermost.
    - Under `no_delete`, native Mem0's deletion probe passes for 5 of 5
      users, but the undeleted row reached later blocks for all 5, and
      later answers named its value for 3 of them (6 answers).
    Report trial-level exposure (the value in any block or answer) next
    to the per-probe rate, for deletion and privacy, in every cell;
    `bench_v2_analysis.py` does since the smoke `s14b`. In `s14b` no
    private value showed anywhere, and deletion passes hid the value in
    kernel and replicated Mem0 3 of 22, native in-house 2 of 22 and
    native Mem0 8 of 28 times (7 echo users, and user 25 through a
    fold). In `s15b` no private value showed either, no kernel or
    replicated deletion trial was exposed (0 of 30 per cell), and
    passes hid the value in native in-house 1 of 21 and native Mem0 7
    of 26 times (Cerebrum `results/bench_v2_smoke_a4/analysis.md`,
    "Trial-level exposure").
44. Contradictions whose question repeats the stale statement's words
    favor the stale value. The manager add says "I report to {value}",
    the contradiction "My manager is {value}", and the question is "Who
    do I report to?". In `f14c`, 12 cells' blocks held user 1's stale
    row. In the 11 where it kept the "report to" wording, every answer
    named it (in 2, kernel and replicated in-house at H = 0, the
    contradiction row was not in the block). In the twelfth, kernel
    Mem0 at H = 2, the V5 writer's fields made Mem0 store "Alex Carter's
    manager is Lena Fischbach.", and the answer named only the new
    value. The teammate templates tie (both say "pairing"), but every
    teammate contradiction was paraphrased to "the only person I'm
    paired with" (6 of 6 in `pilot_v2`, 24 of 24 in `users_v2`), so in
    `pilot_v2` the teammate question ("Who am I pairing with") shares
    "pairing" with the stale add only. In `pilot_v2`'s paraphrases, the
    home_city, client and one_on_one questions repeat the later
    statement's words: the home_city templates lean the other way ("I
    live in" against "I'm based in"), but every add became "My home is
    in …" and every contradiction "I live in …"; the one_on_one
    templates tie, but every add became "I meet with … one-on-one every
    week", without "weekly". The conference question ("Which
    conference am I presenting at?") shares one content word with the
    later statement ("conference") and none with the earlier one.
    Report the four manager users (1,
    19, 25 and 28) and the six teammate users (5, 8, 11, 17, 20 and
    26) apart. In the smoke, outside native Mem0, those ten users'
    questions passed 9 of 50, the 16 that lean to the later statement
    (home_city, client, one_on_one and conference) 59 of 80
    (conference 8 of 15), and the 4 offsite_city ties 0 of 20 (18 of
    them with a stale earlier answer in the block, known issue 45). The
    lean counts content words (function words dropped, word forms as
    written); counting every word gives 9, 13 and 8. `pilot_v2` asks
    one question per slot, so the smoke can hardly tell the lean from
    the slot; only Mem0's reworded rows vary the wording within one
    (Subtask 14, "Smoke"). The analysis reports contradiction per slot.
    Asking with the contradiction's words would only lean the other
    way: a later dataset version should ask with words that favor
    neither statement (open decision 3).
    Addressed by revision 3 (Amendment 3), in another way: each slot
    asks a question that leans to each statement, half of each, so the
    lean can be measured rather than avoided. In the smoke (`s15b`) only
    native in-house can show it: supersession kept every stale row out
    of the kernel and replicated blocks (each passed 15 of 15 of each
    lean), and native Mem0's later value reached no block. Native
    in-house, with both values in all 30 blocks, passed 13 of 15
    later-leaning questions and 5 of 15 earlier-leaning ones (lenient
    14 and 6); the later lean passed more often in 6 of the 7 slots,
    and home_city tied, 1 of 3 each (known issue 41: its "currently").
    The leaned-to row also came first in 29 of the 30 blocks, so the
    lean is not told from the rank (Subtask 15, "Smoke"). The results
    do not record `lean`: the split joins `users_v2` by `probe_id`.
45. Fixed in Subtask 15 (Amendment 3; Cerebrum `4ac61fe`, AIOS
    `ea1a309`): probes write nothing, and in `f15a` no block held a
    probe answer (0 of 525 probes contaminated). The record follows.
    The probes' stored answers shape the later probes' blocks. The six
    probes are asked in session 7 and each answer is stored (kernel
    `auto_extract`; the replicated and native assistants write
    theirs), so later probes read the earlier answers as "(this
    session)". In the smoke:
    - Integration, the last probe: in in-house kernel and replicated,
      the earlier answers, stored verbatim, fill most of the 500-token
      budget (2.8 of 4.6 rows; the budget binds in 27 of 30), and the
      base task and base profile rows reached the block for 9 and 5 of
      30 users (both for 1). These cells score below the others (1.77
      and 1.80 against 2.90 to 3.33). On a copy of the kernel's store,
      the same selection keeps the base task row for 28 users without
      the earlier answers, and for native in-house's 23 users without
      the budget; without a budget the backends' means are close (2.93
      and 2.90), though the paired data do not show a tie. No judged
      run yet scores the probe without the stored answers. Kernel
      against native on Mem0 (3.33 and 2.93) is not a budget effect.
    - Recency and contradiction: an earlier answer can restate a stale
      value as current, and a later answer can repeat it (user 27,
      Subtask 14, "Smoke"). Contradiction passed 19 of 66 with an
      earlier answer in the block that names the stale value (in 21 of
      them every such answer names the new value too) and 49 of 84
      without (outside native Mem0), but nearly every tie has one (18 of
      20, against 20 of the 50 probes whose question leans to the
      earlier statement and 28 of the 80 whose question leans to the
      later one), and no tie passed. Where the wording leans to the
      later statement, 14 of 28 against 45 of 52 (within client,
      conference and one_on_one, 14 of 28 against 18 of 22); to the
      earlier one, 5 of 20 against 4 of 30, four of the five passes
      user 20's, whose stored answers name both values (without user
      20, 1 of 15 against 4 of 30). This is an association; no run yet
      tests it (open decision 2 (b) would).
    Kernel against replicated is unaffected (one library, one order).
    `bench_v2_analysis.py` reports both. Open decision 2.
46. Fixed in Subtask 15, step 1 (AIOS `a610dcd`): each kernel and
    replicated Mem0 store keeps its history in its own file
    (`history.db` next to its `chroma` directory; the kernel's
    `.mem0/history.db`), and a forget scrubs it. Before: the kernel's
    and the replicated loci's Mem0 kept its message
    history in `~/.mem0/history.db`, Mem0's default: neither set
    `history_db_path`, so every run and store shared one file (about
    84 MB on 2026-11-10), which no store reset clears. Mem0 reads the
    scope's last 10 messages into each extraction; v2 user ids carry
    the run id, so runs do not read each other's messages, but a
    deleted value stays there (`DELETION_AND_SUPERSESSION.md`,
    Decision 3). Native Mem0 keeps its history in its own store
    directory (`cerebrum/example/agents/native/backends.py`).
47. `test_forget_kernel.py::test_a_kernel_forget_on_a_real_store[graphiti]`
    is flaky under load: in the Subtask 16 mutation run it failed in 5
    of about 70 full AIOS runs while other suites used the same Neo4j
    (none of 3 baselines, nor any run of the suite alone). Each time
    the forget listed no row of the slot (`values=0, deleted=0`), once
    after a Neo4j `DeadlockDetected` retry during the seed writes. Not
    investigated; no benchmark run shares its Neo4j with a test run.
48. Qwen's generation speed on this laptop moves more than twofold with
    its heat and power state (48 to 131 ms per completion token in
    10-minute windows of the `s17` run), so a cell's time per user is
    not comparable across
    runs: Subtask 17's in-house and Mem0 kernel cells took 99 and 133 s
    a user against 77 and 95 with k adding about 0.03 s a probe.
    Wall times are reported with the cell's milliseconds per
    completion token (`BENCHMARK_V2.md`, Amendment 7); cost notes use
    tokens and calls.
49. Fixed in Subtask 18 (housekeeping): the key heads are masked in
    place. Before: 39 gitignored logs in the AIOS checkout
    (`kernel.log` and files under `logs/`, from the other branch's
    runs, the newest of 2026-10-21) held 118 of LiteLLM's DEBUG lines
    "Api Key:" with the
    Azure key's first 8 characters and asterisks (litellm 1.83.0,
    `llms/azure/common_utils.py:617-623`). No full value; none of them
    was archived or committed. The redaction now masks the line.
50. `redact.py`'s rule for `api_keys` (both repos, Subtask 17) goes by
    position: every string directly under the section is a secret, and
    a mapping under it is read by key name. A string there that is no
    key (an endpoint URL) would be redacted wherever 8 of its
    characters appear, and the archive would refuse any file holding
    them; a list under `api_keys.<provider>` is not read. config.yaml
    holds neither today (every value under `api_keys` is empty).
51. Fixed in Subtask 18 (housekeeping): the AIOS suite sets
    `LITELLM_MODE` to `PRODUCTION` in its conftest and both
    `load_env` copy `NEO4J_*` only (the kernel loads `.env` itself).
    Before: a process of the AIOS venv loaded `AIOS/.env` when it
    imported LiteLLM (litellm 1.83.0, `litellm/__init__.py:19-20`:
    `load_dotenv()`
    unless `LITELLM_MODE` is set to something other than `DEV`; the
    search walks up from LiteLLM's package to the checkout). So the
    kernel, the AIOS suite and the mutation runs' AIOS test processes
    hold the Azure key and the Neo4j password in their environment,
    whatever their caller removed; and Cerebrum's
    `tests/agents/_graphiti_script.load_env` copies every line of
    `AIOS/.env` into the Cerebrum suite's (its docstring says `NEO4J_*`
    only). Reports are redacted and archives scanned for these values,
    and the mutation runs' network guard let no call out (Subtask 17);
    a test that called Azure unmocked elsewhere would reach it with the
    real key (Cerebrum's guard blocks only the kernel).
    `LITELLM_MODE=PRODUCTION` stops the load.
52. The embedding scores of the same row and query differ slightly
    between runs (Ollama, nomic-embed-text): up to 1.1e-6 between the
    in-house cells of Subtask 18's functional check and smoke (254 of 5,646
    rows). A difference that reorders two rows at a budget's or a
    cap's edge would change a block's tail row; no in-house block
    compared in Subtask 18 differed for it (across N, and kernel
    against replicated, all byte-equal).
53. Mem0 scopes its extraction context by `agent_id`: Mem0 2.0.2 shows
    its extraction LLM up to 10 of the user's memories with the same
    `agent_id` (the most similar to the write) and the last 10 messages
    of that agent for that user (`mem0/memory/main.py`, `add`'s phases
    0 and 1), and every locus passes the writer as `agent_id`. A vague sentence written by an agent that
    has stored little for the user yet can be stored as nothing: in
    Subtask 18's functional check, "Issues are sent to Rollbar." (users
    0 and 4) 7 of 16 times at N = 12 and 1 of 6 under concurrency,
    never in the 54 writes at N = 3 or 6 made one at a time per user;
    no log held Mem0's "LLM extraction failed". The trial then failed
    by the extraction check (known issue 32). How to count such writes
    in the full grid's N = 12 and concurrency cells on Mem0 was open
    decision 7: since Amendment 9 they are memories lost, as Graphiti's
    are (Amendment 5), and the trial is scored.
54. Under the load mode a probe is held by the LLM queue, not the
    barrier, and a write by the one memory thread. A probe's LLM call
    waits at Ollama behind its batch-mates (`llm_ms` median 47 s at
    M = 16 in-house), and a chat request that arrives while a batch
    runs waits for that batch (`schedule_wait_ms` median 12 s at M = 16
    in-house, 59 s on Mem0); a user's writes queue behind other users'
    on the memory thread (a Mem0 write's median 24 s at M = 16). The
    barrier wait does not grow. A request arriving during a batch
    waited for that batch before Subtask 18 too (which removed only the
    1 s collection wait); recorded so the load mode's latency is read
    as the model's and the memory thread's.
55. `rejudge.py`: when the primary judge fails on a v2 trial after its
    retries, the trial is marked failed and its three top-level scores
    are cleared, but its integration probe keeps the earlier
    `judge_scores`, `integration_score` and `judges`. No analysis reads
    a failed trial's probe, and no judgment failed in Subtask 20's
    re-judge (0 of 1,350). To fix with the grid's window tooling
    (`FULL_GRID.md`, "The judge window").
56. `pilot_v2`'s decision items have an uneven answer key: correct
    letters A 22, B 8, C 22, D 8 of 60 (`d2`: 13, 3, 12, 2; chi-square
    p = 0.0045; about 6% of fair shuffles of 60 items have as wide a
    gap between the most and the least frequent letter), where the
    other 120 users have 63, 58, 58, 61. One letter throughout scores
    0.13 to 0.37
    there, and the earlier of the correct and the stale option is the
    correct one on 37 of 60 items. So a decision accuracy on the
    pilot's 30 users (every functional check and smoke) is read with
    its letters; on the 150 users the range is 0.22 to 0.28. Revision 4
    stands (Amendment 10, "The option shuffle" and "The letters'
    size").

## Fixed

- `get_memory` visibility: an agent reads a memory by id only if it owns
  it or it is shared. Anything else gets the same "Memory not found" as
  a missing id.
- `get_memory` and `remove_memory` on Mem0 find rows in per-user
  collections (`*_for_user` provider methods).
- `update_memory` and `remove_memory` by id are owner-only.
- `ConversationExtractor` writes through the manager, inside the barrier.
- `/tmp/per_user_proof.txt` writes removed.
- Mem0 LLM sync on Azure (was known issue 9).
- `written_memories` capture, and `memory_counts` derived from it.
- `test_summary_props.py` matched rows by prefix, so a generated name
  such as `ke` took the `kernel_shared` row.
- `visible_stored_rows` for native V2, V3 and `no_visibility`
  consumers (Subtask 14, after the revision-2 check).
- The kernel's startup print included `memory.zep.api_key` (Subtask
  14, after the revision-2 check). Logs written before it still hold
  the key.
