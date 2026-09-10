# Mem0 `search()` Score Saturation — Fix Synthesis & Chain Closeout

**Self-contained report.** Closes out the retrieve-time gate-blindness
investigation chain: it explains why Mem0's `search()` score is unusable
as a similarity signal, states the concrete low-risk fix, resolves the
`retrieve_memory_raw` scope question, and connects the whole chain back
to the flat-reward-trend and non-convergent-arm findings that motivated
it.

All findings below are from read-only source trace plus three
uncommitted in-process diagnostic scripts run against the real
`MemoryManager` + real `Mem0Provider` with the real `config.yaml`
(`provider: "mem0"`, `adaptive_policy.enabled: true`). No production code
was modified in any subtask of this chain.

---

## Verdict (plain)

Mem0's `search()` raw `score` is **unusable as a `similarity` signal**
for the `novelty_threshold` and `similarity_threshold` gates. On the
AIOS ChromaDB configuration it reduces to `min(raw_L2_distance, 1.0)`
(traced in `mem0/utils/scoring.py::score_and_rank`; confirmed
empirically with 0/96 formula mismatches). Because `nomic-embed-text`
L2 distances routinely exceed 1.0 for anything past the near-exact-match
tier, **~90% of retrieved results (86/96 in the probe) clamp to an
identical 1.0**, and that clamp is irreversible — a completely
irrelevant memory is indistinguishable from a moderately-relevant one
once both cross distance 1.0. The `get_all()`-based path AIOS currently
uses is even worse: it drops `score` entirely
(`.model_dump(exclude={"score"})`), so `similarity` is always `None`.

**A working, low-risk, already-proven fix exists.** Capture the raw
distance from the ChromaDB collection the Mem0 provider already owns
(via `self._persistent_client` + `_collection_name_for_user`), convert
it with the existing, provider-agnostic
`distance_to_similarity(distance, space)` helper
(`aios/memory/retrievers.py`; L2 branch `1/(1+d)`), and write the result
into the `similarity` field that `retrieve_memory` builds. Tested
against the probe's real distances, this produces sane, bounded (0,1],
monotonic, fully-differentiated similarities across the entire
[0.11, 1.46] range — including the [1.023, 1.457] band the clamp had
flattened. **No new dependencies. No change to the three gate-consumer
functions** (`_candidate_max_similarity`, `_filter_by_similarity`,
`_dedupe_by_redundancy` already read `r.get("similarity")` correctly and
will simply start receiving real values). **No functional tradeoff on
this configuration:** Mem0's `search()` fusion adds BM25 (inactive — the
Chroma store returns `None` from `keyword_search`), entity boosts
(layered on the same broken base), and reranking (`rerank=False` default,
no reranker configured), so bypassing the fusion to read the raw
distance sacrifices nothing real and recovers the lost signal.

This is not hedged: the fix is understood well enough to scope
concretely.

---

## `retrieve_memory_raw` scope question — RESOLVED

The recommended fix's scope is **just `retrieve_memory`; it is
complete.** `retrieve_memory_raw` does **not** need the same treatment:

- Its only functional caller is the agentic-memory evolution flow —
  `SyscallExecutor.execute_memory_evolve` sets
  `operation_type = "retrieve_memory_raw"` to fetch similar memories to
  evolve (`aios/syscall/syscall.py:836`). The manager's
  `retrieve_memory_raw` branch (`aios/memory/manager.py:1032–1056`)
  returns the provider result directly and applies **no** retrieval
  policy (no `_apply_retrieval_policy`, no gates).
- It returns raw `MemoryNote` objects, which carry **no `similarity`
  field at all** — nothing reads a similarity off that path.
- The novelty probe `_candidate_max_similarity` explicitly issues a
  `retrieve_memory` query (not raw), so the novelty gate is served by
  the fixed path too.

So all three gates are fed exclusively through `retrieve_memory`.
Fixing that one provider method closes the defect for every gated
decision; `retrieve_memory_raw` is out of scope by design.

---

## Connection to the full investigation chain (end to end)

This chain established, by trace and by in-process measurement against
real accumulated data:

1. **Novelty and similarity gates are structurally blind** — both read
   a `similarity` field that is permanently `None` on the Mem0
   `get_all()` path (28/28 `None` across real queries; universal
   fail-open / admit-everything).
2. **The obvious fix direction (`search()`) is itself broken** — its
   score saturates to 1.0 for ~90% of results via an irreversible clamp,
   so a naive swap would not fix the gates.
3. **The real fix is raw-distance + `distance_to_similarity`** — proven
   correct on the actual observed distances, scoped to one method.

**This is now the best-supported root cause of the two prior findings
that motivated the chain — displacing the earlier hypotheses:**

- **Flat reward trend (`AIOS_REWARD_TREND_REPORT.md`):** reward sat at
  ~3.95/5 with no trend for both independent signals (novelty; the
  co-firing similarity+redundancy pair). The report considered
  equal-credit attribution and accumulation as candidate causes. This
  chain supplies a stronger one: **two of the three gated decisions
  could not vary their outcome with the threshold the bandit picked at
  all**, because the signal they threshold was `None` (novelty,
  similarity) — so flat reward is expected even with a clean reward
  signal and perfect attribution.
- **Non-convergent arm selection (`AIOS_ARM_CONVERGENCE_REPORT.md`):**
  late-run arm selections stayed a near-uniform spread (~20–21% vs 16.7%
  uniform). A bandit whose action never changes the outcome has no
  gradient to converge on — the non-convergence is the same defect
  viewed from the selection side.

**Both prior reports' conclusions were reached while two-thirds of the
system's core gating mechanism was inert** — across the entire benchmark
history investigated in this chain (the 150-trial gpt-4o
`kernel_shared_adaptive` run, the accumulating-session pilots, all of
it). They should be treated as **provisional** and re-examined once the
gates actually discriminate.

---

## Next steps, in priority order

1. **Implement the fix.** In `aios/memory/providers/mem0.py::retrieve_memory`,
   obtain the raw L2 distance via a direct ChromaDB semantic query on
   the per-user collection the provider already owns (embed the query
   with `client.embedding_model`, `collection.query(query_embeddings=…,
   where=user_filter, n_results=k)`), read the collection metric
   (`hnsw.space`, default `l2`), and set
   `similarity = distance_to_similarity(distance, space)` on each
   `search_results` entry (replacing today's always-`None`
   `item.get("score")`). One provider method; gate consumers unchanged.

2. **Small-scale post-fix sanity check (NOT the full benchmark).**
   Re-run the Subtask-2 saturation probe pattern post-fix and confirm
   the `similarity` values are now non-`None`, differentiated, and
   monotonic; then confirm the novelty and similarity gate *decisions*
   actually vary with real content (e.g. an irrelevant memory now falls
   below a mid-range similarity threshold while an on-topic one passes).
   This validates the gates discriminate before spending any large
   compute.

3. **Only then revisit the larger questions.** Equal-credit reward
   attribution, the accumulating-session ceiling pilot, and any full
   benchmark re-run should be reconsidered **after** the gates work —
   every one of those investigations was conducted with two-thirds of
   the mechanism inert, so their conclusions are provisional until
   re-examined with working gates.

---

## Bundled documentation corrections (make when the fix lands)

Flagged across Subtasks 1–3; bundle so they aren't lost across the four
investigations:

- **`.kiro/steering/memory-providers.md` — similarity-alias description.**
  It currently states Mem0 exposes `similarity` as an alias of `score`.
  In practice the `get_all()` retrieval path drops `score`, so
  `similarity` is `None` today; post-fix it will be derived from the raw
  distance via `distance_to_similarity` (matching what the doc already
  documents for InHouseProvider). Correct the description to reflect the
  raw-distance path.
- **`Cerebrum/docs/mem0-search-results-memory-id-gap.md` — resolved gap.**
  The documented missing-`memory_id` gap has since been fixed
  (`retrieve_memory` now emits `"memory_id": item.get("id")`). Mark the
  doc resolved so it doesn't keep blocking downstream tracks.
- **Note:** the `similarity`-always-`None` problem is **distinct** from
  that `memory_id` gap; do not conflate them when updating docs.

---

## Deviations from the master prompt

- The master prompt said to append this synthesis to
  `docs/AIOS_SEARCH_SCORE_SATURATION_REPORT.md`. Subtasks 1–3 of this
  chain were reported in chat under "skip commit," so that file did not
  exist. It was therefore **created** (not appended to), and restates
  the Subtask 1–3 findings inline so the report is self-contained. This
  mirrors the earlier `AIOS_GATE_BLINDNESS_INVESTIGATION_REPORT.md`
  handling. No other deviation.
- The three diagnostic scripts from the chain
  (`scratch_mem0_cap_repro.py`, `scratch_retrieve_gates_probe.py`,
  `scratch_saturation_probe.py`) remain uncommitted scratch per their
  subtasks' instructions; only this report is committed.
