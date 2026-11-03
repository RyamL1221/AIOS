# Memory Provider Contract

What every memory backend implements, so that in-house, Mem0, Graphiti
and A-MEM plug into the kernel the same way. The kernel owns selection:
visibility, the user partition, dedupe, the relevance threshold and the
count cap all run in `MemoryManager.retrieve_for_agent`
(`docs/RETRIEVAL_PATH.md`). A provider stores and finds; it never decides
what an agent may see.

Code: `MemoryProvider` in `aios/memory/providers/base.py`. Tests:
`tests/modules/memory/test_provider_contract.py`, run against every
conforming provider.

## Methods

Every method takes the user scope explicitly. `None` means the
provider's default scope (`default_user_id`, usually `"default"`).

| Method | Returns | Rules |
|---|---|---|
| `add(note)` | memory id | Store `note.content` verbatim with `note_metadata(note)`. Raise `ProviderError` on failure. `note.metadata["user_id"]` is the scope. |
| `search(query_text, user_id, top_k)` | `list[Candidate]` | Up to `top_k` of the user's memories, closest first. Scored when `scored_search`. No visibility filter, no threshold. |
| `list(user_id, top_k)` | `list[Candidate]` | Up to `top_k` of the user's memories in storage order, `score=None`. |
| `get(memory_id, user_id)` | `Candidate` or `None` | One memory in the user's scope. |
| `update(memory_id, user_id, content, metadata)` | `bool` | Replace content when not `None`; merge `metadata` over the stored metadata; never remove a required key. `False` if missing. |
| `delete(memory_id, user_id)` | `bool` | `False` if missing. |
| `capabilities()` | `dict` | See below. |

`Candidate` is `(memory_id, content, metadata, score)`. `score` is a
similarity, higher is closer, or `None`. The kernel turns candidates into
rows with `Candidate.to_row()`; rows also repeat `keywords`, `tags`,
`category` and `timestamp` at the top level, as before the contract,
because SDK search returns them and the injected memory block prints
`timestamp`.

## Capabilities

| Key | Meaning |
|---|---|
| `scored_search` | `search` returns a float score on every row. |
| `semantic_search` | `search` ranks by meaning, not shared words. |
| `internal_llm` | The backend has its own LLM, whether or not the kernel uses it. |
| `native_sdk` | The backend is a third-party memory SDK. |

The contract tests check honesty: `scored_search` true means every
`search` row has a float score in [-1, 1], in descending order.

## Commit timing

`synchronous_commit` (class attribute, default `False`): `True` when a
write is durable once `add` returns. The write barrier is skipped for
such providers, since a wait would only add latency. The in-memory and
Zep providers set it; Mem0 and the Chroma in-house provider do not.

## Required metadata

Every stored item carries `owner_agent`, `user_id`, `memory_type`,
`sharing_policy` and `created_at`. The kernel fills them in
`address_request` before `add`: `owner_agent` and `user_id` default to
the writing agent, `sharing_policy` to `"private"`, `memory_type` to `""`
and `created_at` to the UTC time. A provider must return all five from
`get`, `list` and `search`; Mem0 replaces `created_at` with its own time.
The rules fail closed: a row without `owner_agent` is visible to nobody,
and one without the scope's `user_id` fails the user partition.

An update may not change `owner_agent`, `user_id` or `created_at`; the
kernel strips them from update metadata.

## No visibility in providers

The visibility rule (`aios/memory/visibility.py`, `apply_sharing_filter`)
is applied by the kernel only. No provider imports it; a contract test
checks that agent B's private memory comes back from `search`, and that
`retrieve_for_agent` removes it for agent A. `retrieve_memory_raw` goes
through `retrieve_for_agent` too.

## Embedding model

`memory.embedding` (`provider`, `model`, `dimension`, `ollama_base_url`)
pins one model for every backend: `aios/memory/embedding.py`. Mem0's
embedder config is built from it (`mem0.embedder` is ignored with a
warning), and the Chroma provider embeds with the same Ollama call Mem0
makes (`Client.embed`). A vector of the wrong length fails the write. The
block is reported by `/memory/config`, so every results file records it
in `config_snapshot`. Default: `ollama` / `nomic-embed-text` / 768.
Changing the model needs fresh stores; the Chroma provider refuses a
collection created with a different model.

## Threshold

With scored search, `relevance_threshold` applies for the first time:
rows scoring below it are dropped before the sort and cap. The default is
0.0, which ranks and drops nothing, so `kernel_shared` selects what it
selected before scores existed. The Subtask 19 ablation varies it.
Diagnostics report `scores_present` and `threshold_used` (`None` when no
row was scored).

## Providers

| Provider | Config name | Conforms | scored | semantic | internal LLM | native SDK |
|---|---|---|---|---|---|---|
| `ChromaInHouseProvider` | `in-house` | yes | yes | yes | no | no |
| `Mem0Provider` | `mem0` | yes | yes | yes | yes | yes |
| `InHouseProvider` (dict, tests only) | `in-memory` | yes | yes | no | no | no |
| `ZepProvider` | `zep` | no | yes | yes | yes | yes |

### In-house (Chroma)

`aios/memory/providers/chroma_inhouse.py`. One persistent Chroma
collection per user (`memory.chroma_inhouse.path`, default
`.aios_state/chroma_inhouse`), named with the user id and a hash of it,
in cosine space, so the score is `1 - distance`. Content is stored
verbatim; there is no extraction and no LLM. Scalar metadata is stored as
Chroma metadata so `where` filters work, and the whole dict as JSON so
lists round-trip.

### Mem0

Kernel mode stores verbatim (`infer=False`) in one Mem0 store per user.
`list` is `get_all`. `search` queries the user's Chroma collection through
Mem0's own vector store and embedder, and converts the raw distance to a
cosine similarity (`1 - d/2`: Mem0's collections use Chroma's default
squared L2, and the pinned model returns unit vectors).

It does not use Mem0's `search()`. Mem0 2.0.0's Chroma adapter puts the
raw distance in the `score` field, and `score_and_rank` treats that as a
similarity: results come back least similar first, the fused score is
clamped at 1.0, and `threshold` (default 0.1) drops the closest
matches, whose distance is below it. Measured on a real store with
the pinned model: the most relevant of four memories ranked last, at
0.647, and two unrelated ones ranked first, at 1.0.

Why the kernel used `get_all` until Subtask 5: on 2026-06-28 commit
`7793943` set Mem0's search `threshold` to 0.0 after retrieval counts fell
as the store grew (`results/paper_mem0_default_30_await_fix/ANALYSIS.md` in that commit, since removed: 2
results at 8 stored memories, 0 in 14 of 30 trials); the analysis blamed
`score_and_rank`. The same day `3ceea6c` switched retrieval to `get_all`
and changed the tests to match, and also set `infer=False`, because with
`infer=True` Mem0's fact extraction deduplicated writes and stored
nothing while `add()` reported success. Neither commit tested
`threshold=0.0` on its own, and the write loss alone explains a retrieved
count that falls as the store grows. With the inverted score above, a
search could not have been trusted either way.

Native mode (Subtask 6) is Mem0 used as shipped, so it calls Mem0's own
`search()` and keeps its scores, bugs included.

### Zep

Does not conform. Zep stores text only, so the required metadata is lost,
and every row it returns fails the user partition and the visibility
rule, which fail closed. `list` and `update` raise `ProviderError`. It
loads and runs so existing configs keep working; it is not one of the
paper's backends.

## Adding a provider

Subclass `MemoryProvider`, implement every abstract method, register it
in `ProviderFactory.PROVIDERS`, add its config block to `config.yaml`
and `config.yaml.example`, and add it to the `provider` fixture of
`test_provider_contract.py`. If the backend needs the kernel's
personalization (context injector and conversation extractor), add its
name to `PERSONALIZATION_PROVIDERS` in `runtime/launch.py`.
