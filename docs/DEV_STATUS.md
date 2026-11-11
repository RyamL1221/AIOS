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
| 16 | Graphiti backend and native condition | In progress (spec) |

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

## Test baselines

These fail on `workshop-postrun` too and are not caused by later work.

- AIOS: `tests/modules/memory/test_memory.py` fails at collection, and 14
  tests in `test_mem0_provider.py` / `test_zep_provider.py` error (their
  `manager` argument is collected as a missing fixture).
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
  635 passed, the 14 errors). The names
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
4. `get_memory`, `update_memory` and `remove_memory` on Zep always
   answer "not found": Zep episodes carry no owner, so the rules fail
   closed. The same goes for any row stored without an `owner_agent`.
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
11. Zep does not conform to the provider contract (no metadata, no
    `list` / `update`); see `docs/PROVIDER_CONTRACT.md`.
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
15. The FIFO scheduler waits up to `batch_interval` (1.0 s, set in
    `useFIFOScheduler`) before running an LLM request; sequential
    requests wait about the full second. That is 14% of `kernel_shared`
    latency on GPT-4o and more on fast models. It is in
    `kernel_overhead_ms`; whether to shorten it is a question for the
    latency claims (Subtask 19 or later), not changed here.
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
    judge's scores (8% of profile scores differ on a test-retest). Qwen
    and Llama on Ollama are deterministic. GPT-4o and judge noise
    remain, so compare cells paired and with CIs.
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

35. `test_summary_props.py::test_kernel_shared_delta_is_zero` sometimes
    hits Hypothesis's deadline (timing, not logic); it is the flaky test
    that makes the Cerebrum failure count 19 or 20.
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
