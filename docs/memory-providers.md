# Memory Providers

AIOS supports pluggable memory providers, allowing you to choose between different memory backends without changing application code.

## Available Providers

| Provider | Backend | Persistence | Requirements |
|----------|---------|-------------|--------------|
| `in-house` (default) | ChromaDB / Qdrant | Local disk | None (built-in) |
| `mem0` | Mem0 + Ollama + ChromaDB | In-memory only* | `pip install mem0ai`, Ollama running |
| `graphiti` | graphiti-core + Neo4j | Neo4j | `graphiti-core==0.31.2` (in `requirements.txt`), Neo4j 5.26, Azure gpt-4o, Ollama embedder |
| `in-memory` | Python dict | None | None (tests only) |

\* Mem0's ChromaDB adapter uses a deprecated API that doesn't persist across restarts.

## Quick Start

### 1. Choose a provider

Edit `aios/config/config.yaml`:

```yaml
memory:
  provider: "in-house"  # or "mem0" or "graphiti"
```

### 2. Install dependencies (if needed)

```bash
# For Mem0
pip install mem0ai
ollama pull nomic-embed-text

# For Graphiti (and a Neo4j 5.26 server; docs/GRAPHITI_BACKEND.md)
pip install graphiti-core==0.31.2
```

### 3. Start AIOS

```bash
python -m runtime.launch
```

## Configuration

### InHouse (default)

No additional configuration needed. Uses the `storage` section in config.yaml:

```yaml
memory:
  provider: "in-house"

storage:
  vector_db_backend: "chroma"  # or "qdrant"
```

### Mem0

Requires Ollama running locally with an LLM and embedding model:

```yaml
memory:
  provider: "mem0"
  mem0:
    user_id: "default"
    llm:
      provider: "ollama"
      config:
        model: "qwen2.5:7b"
        ollama_base_url: "http://localhost:11434"
    embedder:
      provider: "ollama"
      config:
        model: "nomic-embed-text"
        ollama_base_url: "http://localhost:11434"
    vector_store:
      provider: "chroma"
      config:
        collection_name: "mem0_memories"
```

Prerequisites:
- Ollama running at `localhost:11434`
- Models pulled: `ollama pull qwen2.5:7b` and `ollama pull nomic-embed-text`

### Graphiti

Zep's open-source temporal knowledge graph on Neo4j (NeurIPS Subtask
16; it replaced the Zep Cloud provider). Neo4j comes from `NEO4J_URI`,
`NEO4J_USER` and `NEO4J_PASSWORD` in the environment (`AIOS/.env`);
the LLM is `memory.backend_llm` and the embedder `memory.embedding`:

```yaml
memory:
  provider: "graphiti"
  graphiti:
    user_id: "default"
```

Setup, design and what it stores: `docs/GRAPHITI_BACKEND.md`.

## Switching Providers at Runtime

You can switch providers without restarting AIOS:

1. Edit `config.yaml` to change `memory.provider`
2. Call the refresh endpoint:
```bash
curl -X POST http://localhost:8000/core/refresh
```

## Testing Memory via API

Store a memory:
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "test_agent",
    "query_type": "memory",
    "query_data": {
      "operation_type": "add_memory",
      "params": {
        "content": "The user prefers Python.",
        "tags": ["preferences"],
        "category": "User Preferences"
      }
    }
  }'
```

Search memories:
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "test_agent",
    "query_type": "memory",
    "query_data": {
      "operation_type": "retrieve_memory",
      "params": {
        "content": "programming language preference",
        "k": 3
      }
    }
  }'
```

## Running Provider Tests

Each provider has a standalone test script in `tests/modules/memory/`:

```bash
# Test Mem0 (requires Ollama + nomic-embed-text, config set to mem0)
python tests/modules/memory/test_mem0_provider.py

# Test Graphiti (requires the local Neo4j; the LLM is scripted)
.venv/bin/python -m pytest tests/modules/memory/test_graphiti_provider.py
```

Tests run directly against the provider layer without needing the full AIOS
server. Each script includes preflight checks that verify prerequisites before
running.

## Architecture

```
MemoryManager
     |
ProviderFactory
     |
  +--+--+--+
  |  |  |  |
InHouse Mem0 Graphiti  (your custom provider)
  |     |    |
ChromaDB Ollama+ChromaDB  Neo4j
```

All providers implement the `MemoryProvider` abstract base class
(`aios/memory/providers/base.py`). Since NeurIPS Subtask 5 the
contract is `docs/PROVIDER_CONTRACT.md` (`add`, `search`, `list`,
`get`, `update`, `delete`, `capabilities`); the six methods below are
the earlier interface:

- `add_memory(memory_note)` — store a memory
- `get_memory(memory_id)` — retrieve by ID
- `retrieve_memory(query)` — semantic search
- `update_memory(memory_note)` — update existing memory
- `retrieve_memory_raw(query)` — search returning raw MemoryNote objects
- `remove_memory(memory_id)` — delete a memory

## Adding a Custom Provider

1. Create `aios/memory/providers/my_provider.py` implementing `MemoryProvider`
2. Register it in `aios/memory/providers/factory.py`
3. Export it in `aios/memory/providers/__init__.py`
4. Add config section under `memory.my_provider` in `config.yaml`

See the steering doc at `.kiro/steering/memory-providers.md` for detailed
implementation examples.

## Provider-Specific Behavior

### Mem0
- Stores raw text and retrieves it as-is
- Semantic search via embeddings (nomic-embed-text)
- In-memory only — data lost on restart (upstream ChromaDB adapter limitation)

### Graphiti
- Extracts facts (graph edges) from each write with its LLM: one row
  per fact and write, the write's metadata on every row
- `search()` is unscored (`scored_search: false`)
- About 4 to 6 LLM calls and 6 seconds a write
  (`docs/GRAPHITI_BACKEND.md`, "Measured in the smokes")

## Known Issues

| Issue | Provider | Status |
|-------|----------|--------|
| No persistence across restarts | Mem0 | Upstream — Mem0 uses deprecated `chromadb.Client()` |
| `protobuf` must be < 6.0 | Mem0 | `qdrant-client` dependency needs `protobuf 5.x` |
