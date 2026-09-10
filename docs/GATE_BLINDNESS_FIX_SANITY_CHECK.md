# Gate-Blindness Fix — Sanity Check Results

Validation of the `retrieve_memory` similarity fix (commit
`05772c0`, `feat(aios): fix retrieve_memory to compute real similarity
via distance_to_similarity`). Run against the fixed code with the real
`MemoryManager` + real `Mem0Provider` and real `config.yaml`
(`provider: "mem0"`, `adaptive_policy.enabled: true`), in-process, no
mocking. Script: `scratch_gate_fix_sanity.py` (uncommitted diagnostic).

Setup: 6 varied memories accumulated under one fresh `user_id`
(profile, task_context, and 4 conversation turns spanning TLS, pandas,
Rust, and an unrelated houseplants topic).

## Results — all four checks PASS

### 1. `similarity` is now non-null
Every retrieval returned non-null `similarity` for 4/4 results, across
all three test queries. (Before the fix: 28/28 `None`.)

### 2. `similarity` values are differentiated
Each query produced 4 distinct similarity values — not a single
saturated ceiling. Examples:
- Query "How do I configure TLS certificates on the load balancer?":
  `[0.4785, 0.7779, 0.4216, 0.4353]`
- Query "pandas pivot dataframe by region":
  `[0.4973, 0.4239, 0.7652, 0.4390]`
- Query (irrelevant) "What is the surface temperature of Venus?":
  `[0.4577, 0.4248, 0.4378, 0.4481]` — all low, none elevated (correct:
  nothing in the store is relevant).

### 3. `_filter_by_similarity` now discriminates (not fail-open-all)
For the TLS query, ranked similarities were TLS memory `0.7042`,
profile `0.4705`, houseplants `0.4272`, pandas `0.4153`. The gate's
keep count now varies with the threshold:
- `thr=0.30` → kept 4/4
- `thr=0.45` → kept **2/4**
- `thr=0.55` → kept **1/4** (only the on-topic TLS memory)

(Before the fix: 7/7 kept at every threshold — universal fail-open.)

### 4. `_candidate_max_similarity` (novelty probe) now varies with candidate
- Near-duplicate candidate ("...set up TLS certificates...load balancer
  on port 8443") → `max_sim = 0.9795`
- Unrelated candidate ("The mitochondria is the powerhouse of the
  cell...") → `max_sim = 0.4644`

Real, differentiated, and correctly ordered (near-dup ≫ unrelated).
(Before the fix: always `0.000`, admit-everything.)

## Verdict

`OVERALL: PASS`. The two previously-inert gates (`novelty_threshold`,
`similarity_threshold`) now receive real, differentiated similarity and
demonstrably change their admit/reject decisions based on content. The
consumer functions (`_candidate_max_similarity`, `_filter_by_similarity`,
`_dedupe_by_redundancy`) were not modified — they simply began receiving
usable values. `retrieve_memory_raw` was left untouched (no gate
dependency; agentic-evolution flow only).
