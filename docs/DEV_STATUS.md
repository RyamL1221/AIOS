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
  adapter returns the raw L2 distance as `score` and ranks least similar
  first, clamped at 1.0 (verified on a real store). The provider queries
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
inverted ones: 83-87% of injected memories scored exactly 1.0, and its
order carries no similarity information. One Llama `native_mem0` trial
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

## Open decisions

None.

## Test baselines

These fail on `workshop-postrun` too and are not caused by later work.

- AIOS: `tests/modules/memory/test_memory.py` fails at collection, and 14
  tests in `test_mem0_provider.py` / `test_zep_provider.py` error (their
  `manager` argument is collected as a missing fixture).
- Cerebrum `tests/agents`: 19 failures, 2 errors at
  `neurips-subtask-03` (one flaky test makes it 19 or 20); unchanged at
  `neurips-subtask-07` (AIOS 310 passed, Cerebrum 303 passed) and
  `neurips-subtask-08` (AIOS 315 passed, Cerebrum 307 passed). The names
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
17. The harness venv has `mem0ai` 2.0.2, the kernel 2.0.0. 2.0.2 builds
    its default OpenAI LLM when constructed and fails without a key, so
    the replicated Mem0 agents give it `memory.backend_llm` through
    LiteLLM. Writes are verbatim (`infer=False`), so it is never called;
    the stored rows and search are the same code as the kernel's.
18. Cerebrum has a tracked `aios/` stub, imported by some of its tests,
    that shadows the kernel's `aios` package in the same interpreter.
    The replicated agents' checks therefore run in a subprocess, and
    `library.load()` fails with a clear message if the stub is already
    imported.
19. The kernel's conversation write runs on a background thread after
    the reply; the replicated assistant's runs synchronously after it.
    Both are outside measured latency, and the next trial is a new user,
    so neither can affect a score here (docs/REPLICATED_LOGIC.md).
20. Comparisons between conditions are unpaired: the harness generates
    each trial's user with an LLM, without a seed, so two cells never
    score the same users. A 30-trial Llama cell moved by up to 0.53
    between two draws of the same condition (Subtask 8). Paired
    comparisons need a fixed dataset on this branch, ported by hand,
    not cherry-picked from `feature/self-improving-memory`.
21. Llama's writers sometimes return a status payload instead of the
    schema (`{"status": "success", "message": ...}`), and it is stored
    as the memory: 1-10 of 30 task-context writes per Llama cell in
    Subtask 8, in every locus. The writers do not validate their
    extraction.

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
