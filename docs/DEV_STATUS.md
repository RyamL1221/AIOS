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
| 5 | Provider contract; Chroma in-house provider; update stamping | Done |
| 6 | Native agent-managed conditions (Mem0, in-house) | Done |

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
  `scripts/retrieval_smoke.py --kernel-log <log>` checks a GPT-4o chat.
- Paper (Subtask 12): §4.1's TODO is now resolvable. The condition is
  `kernel_private`, the kernel pipeline with sharing off, with
  `after_visibility` = 0 in all 450 trials, and the "Second" results
  point can use the v2 numbers. paper_v2 is in neither repo, so the
  edit itself waits for Subtask 12.

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

## Open decisions

1. Injected-block order. With scored search the block is in similarity
   order (task context first), not the storage order the v2 baseline was
   produced with (profile first). Either keep it and re-run the
   `kernel_shared` baseline under it before comparing new conditions to
   it, or rank for the cap but print the block in a fixed order.

## Test baselines

These fail on `workshop-postrun` too and are not caused by later work.

- AIOS: `tests/modules/memory/test_memory.py` fails at collection, and 14
  tests in `test_mem0_provider.py` / `test_zep_provider.py` error (their
  `manager` argument is collected as a missing fixture).
- Cerebrum `tests/agents`: 19 failures, 2 errors at
  `neurips-subtask-03` (one flaky test makes it 19 or 20). The names
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
9. `HybridJudge` falls back to the keyword score alone when the LLM
   judge call fails, without marking the trial. `rejudge.py` retries and
   fails the trial instead; `run_evaluation.py` still falls back.
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
14. Native Mem0 extraction (gpt-4o) runs on every write: two per trial
    plus the conversation, with no cost recorded yet (Subtask 7).

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
