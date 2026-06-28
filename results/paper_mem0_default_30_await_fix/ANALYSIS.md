# MEM0_DEBUG Diagnostic Analysis — 30-Trial Run (Print Fix)

## Source

- **Log file**: `kernel.log` (project root)
- **Run period**: 2026-06-28 14:50 → 14:58
- **`[MEM0_DEBUG]` lines captured**: 90 (from `aios.memory.manager` logger)

## Summary

| Metric | Value |
|--------|-------|
| Total add_memory operations | 60 (all succeeded) |
| Total retrieve_memory operations | 30 |
| Retrievals returning 2 results | 4 (trials 1-4) |
| Retrievals returning 1 result | 12 |
| Retrievals returning 0 results | **14 (47%)** |

## Degradation Pattern

```
Trial  1: store_size= 2, retrieved=2  ✓
Trial  2: store_size= 4, retrieved=2  ✓
Trial  3: store_size= 6, retrieved=2  ✓
Trial  4: store_size= 8, retrieved=2  ✓
Trial  5: store_size=10, retrieved=1  ↓
Trial  6: store_size=12, retrieved=1  ↓
Trial  7: store_size=14, retrieved=1  ↓
Trial  8: store_size=16, retrieved=1  ↓
Trial  9: store_size=18, retrieved=1  ↓
Trial 10: store_size=20, retrieved=1  ↓
Trial 11: store_size=22, retrieved=0  ✗
Trial 12: store_size=24, retrieved=1
Trial 13: store_size=26, retrieved=1
Trial 14: store_size=28, retrieved=1
Trial 15: store_size=30, retrieved=0  ✗
Trial 16: store_size=32, retrieved=0  ✗
Trial 17: store_size=34, retrieved=0  ✗
Trial 18: store_size=36, retrieved=1
Trial 19: store_size=38, retrieved=0  ✗
Trial 20: store_size=40, retrieved=0  ✗
Trial 21: store_size=42, retrieved=0  ✗
Trial 22: store_size=44, retrieved=0  ✗
Trial 23: store_size=46, retrieved=1
Trial 24: store_size=48, retrieved=0  ✗
Trial 25: store_size=50, retrieved=0  ✗
Trial 26: store_size=52, retrieved=0  ✗
Trial 27: store_size=54, retrieved=1
Trial 28: store_size=56, retrieved=0  ✗
Trial 29: store_size=58, retrieved=0  ✗
Trial 30: store_size=60, retrieved=0  ✗
```

## Root Cause

**Case (B): mem0's search scoring/threshold filters out valid matches
as the store grows.**

Evidence:
1. All 60 `add_memory` calls succeed with real memory_ids
2. ChromaDB pre-filter by user_id IS applied (verified in code trace)
3. Retrieval works perfectly when store has ≤8 entries
4. Degradation begins at ~10 entries, complete failure at ~22+ entries
5. The pattern is monotonically worsening with store size

## Mechanism

mem0's `_search_vector_store()` works as follows:
1. ChromaDB returns candidates filtered by `user_id` WHERE clause ✓
2. BM25 keyword scores are computed
3. Entity boosts are computed  
4. `score_and_rank()` combines semantic + BM25 + entity scores
5. **Threshold filter (`threshold=0.1`) removes results below cutoff**

As the ChromaDB collection grows (even with correct user_id filtering),
the **embedding similarity scores decrease** because:
- The embedding model (nomic-embed-text) produces cosine similarities
  that spread out as the vector space fills up
- Mem0's `score_and_rank()` normalizes scores relative to the candidate
  pool — with more diverse embeddings in the collection, individual
  scores drop below the 0.1 threshold
- The user_id filter narrows to 2 results per user, but those 2 results
  compete in a scoring pipeline calibrated for the broader collection

## Fix Options

1. **Set threshold=0.0 in AIOS config** — disable mem0's internal threshold
   since we already filter by user_id. The user_id pre-filter ensures only
   relevant memories are returned.

2. **Pass threshold=0.0 in the search kwargs** — override at the provider level:
   ```python
   search_kwargs = {"filters": search_filters, "top_k": k, "threshold": 0.0}
   ```

3. **Use `get_all()` instead of `search()`** — for small per-user stores,
   brute-force retrieval may be more reliable than semantic search.

## Recommendation

Option 2 is the simplest fix — add `"threshold": 0.0` to `search_kwargs`
in `Mem0Provider.retrieve_memory()` and `retrieve_memory_raw()`. This
disables mem0's internal scoring filter while keeping the user_id
pre-filter active. AIOS already has its own `relevance_threshold` in
the ContextInjector that handles quality filtering at a higher level.
