# Models

The models every reported NeurIPS 2027 result uses (decided in
Subtask 9, 2026-11-04). A run records its assistant and judge model in
the results file. Changing an entry here needs a new baseline.

## Assistant models

The assistant model also runs the two writers' extraction calls in
every condition.

| Short name | Harness `--assistant-model` | Served by | Exact version |
|---|---|---|---|
| `gpt4o` | `gpt-4o:azure` | Azure OpenAI deployment `gpt-4o` | `gpt-4o-2024-11-20` (the `model` field of a reply on 2026-11-04) |
| `qwen` | `qwen2.5:7b:ollama` | Ollama 0.40.11 | digest `845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e`, 7.6B, Q4_K_M |
| `llama` | `llama3.1:8b:ollama` | Ollama 0.40.11 | digest `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`, 8.0B, Q4_K_M |

All three are the workshop's models and those of NeurIPS Subtasks 3-8,
so the earlier cells stay comparable. Llama is kept although its
writers sometimes return a status payload instead of the schema (known
issue 21): since Subtask 9 such an extraction is retried, and a writer
that still fails stores nothing and its trial is counted, not scored.

## Stress-sweep pair

**GPT-4o and Qwen-2.5:7B.** One API model and the local model whose
writers fail least often, so a sweep measures the memory system rather
than writer failures.

## Other models

| Role | Model | Version |
|---|---|---|
| Judge | `gpt-5.4:azure` | `gpt-5.4-2026-03-05`, judge prompt v2 |
| Mem0's internal LLM (`memory.backend_llm`), every Mem0 condition | Azure `gpt-4o` through LiteLLM | as above, temperature 0.1 |
| Embedding (`memory.embedding`), every backend | `nomic-embed-text` on Ollama | digest `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`, 768 dimensions |
| Dataset generation (`users_v1`) | Azure `gpt-4o` through LiteLLM | as above, seed 20261104 |

Ollama digests are from `GET /api/tags` on 2026-11-04. Before a run
that reports results, check them again:

```bash
curl -s localhost:11434/api/tags | python3 -c "import json,sys; \
[print(m['name'], m['digest']) for m in json.load(sys.stdin)['models']]"
```
