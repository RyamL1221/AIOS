# Retrieve-Time Gate Blindness — Investigation Synthesis

**Self-contained report.** Establishes, by source trace and in-process
empirical measurement, that two of the three LinUCB-gated memory
decisions on the current Mem0 integration are permanently non-functional
because the signal they threshold is always `None`. Connects this to the
flat-reward-trend finding (`AIOS_REWARD_TREND_REPORT.md`) as a distinct,
previously-unaccounted-for root cause, and gives an honestly-scoped
priority recommendation.

The gates analyzed:
- `novelty_threshold` — admission gate at **add** time.
- `similarity_threshold` — relevance gate at **retrieve** time.
- `redundancy_threshold` — near-duplicate gate at **retrieve** time.

All findings below are from read-only code trace plus two uncommitted
in-process diagnostic scripts run against the real `MemoryManager` +
real `Mem0Provider` with the real `config.yaml`
(`provider: "mem0"`, `adaptive_policy.enabled: true`). No mocking.

---

## Per-gate verdict

### `novelty_threshold` — BLIND
The add-time novelty gate calls `MemoryManager._candidate_max_similarity`
(`aios/memory/manager.py`), which probes `provider.retrieve_memory` and
reads each result's `similarity` field. On the Mem0 path that field is
always `None` (see root cause below), so the probe defaults to
`max_sim = 0.0` ("treat as maximally novel") on every call. Empirically,
every novelty-gate log line reads `max_sim=0.000 -> admit=True`,
including for near-identical content. The gate admits everything
regardless of the threshold the bandit picks.

### `similarity_threshold` — BLIND (same defect as novelty)
The retrieve-time relevance gate is `_filter_by_similarity`
(`aios/memory/manager.py`), which reads `r.get("similarity")` on each
`search_results` entry and keeps a result iff `sim is None or
float(sim) >= threshold`. This is the **same field, from the same
`provider.retrieve_memory` method, as the novelty probe**. Measured
across 4 distinct real queries over 7 accumulated memories: `similarity`
was `None` on **28/28 entries**, and `_filter_by_similarity` kept
**7/7 at every threshold tested (0.20, 0.50, 0.70) for every query** —
universal fail-open. The threshold choice never changes the outcome.

**Novelty and similarity_threshold share the exact same defect.** Both
read the permanently-`None` `similarity`/`score` field produced by
`retrieve_memory`'s `get_all()`-based path. Confirmed by trace and
empirically (28/28 `None`, universal fail-open).

### `redundancy_threshold` — SOUND (not part of this defect)
The retrieve-time dedup gate is `_dedupe_by_redundancy`
(`aios/memory/manager.py`), which computes its comparison value itself
via `_pairwise_cosine(content, existing_content)` using a locally-loaded
`all-MiniLM-L6-v2` `SentenceTransformer`. It reads **only the
`content` string** from each result — never the provider `similarity`/
`score` field — so it is architecturally independent of the defect.
Measured real values:
- Genuinely-distinct pairs: profile vs task_context = **0.4267**; most
  distinct pairs below 0.30.
- A deliberate near-duplicate pair: **0.9859**.
- `_dedupe_by_redundancy` correctly dropped the one near-duplicate
  (kept 6/7) at thresholds 0.45, 0.70, and 0.85; it left all distinct
  content intact.

**Refined characterization:** the redundancy gate is not "dead." It
fires correctly on genuine near-duplicates (0.99 ≫ 0.70) and correctly
stays quiet on legitimately distinct content (≤0.43). Its reputation for
rarely firing is a property of mostly-distinct real content, not a bug.
It is sound.

---

## Root cause behind the two blind gates

`aios/memory/providers/mem0.py::retrieve_memory` fetches candidates with
`client.get_all(filters={...})` and then maps each item with
`"similarity": item.get("score")`. In the installed Mem0 2.0.0
(`.venv/.../mem0/memory/main.py`), `_get_all_from_vector_store`
serializes each memory with `.model_dump(exclude={"score"})` — it
**explicitly drops the score field**. Only `search()` /
`_search_vector_store` populates `score`. Because `retrieve_memory`
calls `get_all` (not `search`), `item.get("score")` is always `None`, so
`similarity` is always `None`. Both the novelty probe and
`_filter_by_similarity` consume exactly this field, which is why both
gates are blind. (The separately-documented
`mem0-search-results-memory-id-gap.md` concerns the `memory_id` field,
not `similarity`; that `memory_id` gap has since been fixed in the code
—`retrieve_memory` now emits `memory_id`— but the `similarity`-is-`None`
problem is distinct and still live.)

---

## Connection to the flat-reward-trend finding

`AIOS_REWARD_TREND_REPORT.md` found reward FLAT across the 150-trial
gpt-4o `kernel_shared_adaptive` run for both independent signals
(novelty, and the co-firing similarity+redundancy pair), with no
measurable learning, and reconciled that with a prior finding that arm
selections never converged.

This investigation supplies a **third plausible root cause** for that
flat reward, distinct from the equal-credit attribution hypothesis and
from any "accumulation doesn't happen" hypothesis (accumulation was
already confirmed working — the store holds all records per session):

> **Two of the three gated decisions cannot discriminate on the signal
> they are designed to threshold.** The novelty gate admits everything;
> the similarity gate keeps everything. Their outcome is invariant to
> the arm the bandit selects, at every threshold, regardless of
> accumulation, trial count, `alpha`, or reward attribution.

So the flat reward for the novelty signal and for the
similarity-half of the similarity+redundancy pair is expected even if
the reward signal were perfectly clean and attribution were perfect: the
bandit is "learning" to set a threshold that changes nothing. Only the
redundancy half of the retrieve pair can actually vary the outcome — and
only when a genuine near-duplicate is present, which is rare in the
benchmark's mostly-distinct content. This means **two-thirds of what the
bandits are threshold-tuning never varies with the threshold choice at
all**, which is sufficient on its own to produce flat reward and
non-converging arm selection, independent of the attribution question.

---

## Priority recommendation

**Treat the `get_all()`-vs-`search()` root cause behind Gate 1 (and the
novelty probe) blindness as the top-priority item — ahead of the
equal-credit attribution investigation and ahead of any further
benchmark/pilot runs.**

Reasoning: while the `similarity` signal is permanently `None`, the
novelty and similarity gates are inert by construction, so neither
equal-credit attribution nor additional benchmark trials can produce a
meaningful learning signal for those two bandits — you would be tuning
and measuring decisions that never change. Fixing the signal is a
**precondition** for either of those other investigations to yield
interpretable results. Until it is fixed, any conclusion about "does the
adaptive policy learn" is confounded by two of three gates being unable
to act on their input.

---

## The fix is NOT as simple as "switch get_all() to search()"

`get_all() → search()` is the **validated direction**, not a scoped fix.
The Step-5 sanity check confirmed `client.search()` returns
differentiated, non-null scores where `get_all()` returns none
(e.g. the two TLS turns scored 0.42 and 0.44; a pandas turn 0.324;
project-related entries 0.79–0.94). So the direction is real.

**However, the raw `search()` scores are not drop-in usable.** In the
same check, 5–6 of 7 entries per query came back at exactly **1.0**,
with only 1–2 entries showing differentiated sub-1.0 scores. That
ceiling-saturation pattern means Mem0 2.0.0's hybrid scorer
(BM25 + semantic + `score_and_rank`, with optional reranking) is not
handing back clean cosine similarities out of the box. Thresholding
against saturated 1.0 scores would mis-gate as badly as the current
all-`None` behavior, just in the opposite direction (keep-everything
becomes admit-everything at the ceiling). The scores need to be
understood before a fix can be correctly scoped: is the 1.0 saturation
BM25/keyword clamping, a reranking artifact, a tunable parameter
(e.g. `threshold`, `rerank`, hybrid weights), or something structural in
the hybrid scorer?

---

## Recommended next concrete step

A focused follow-up investigation into the `search()` **score-saturation
behavior**, specifically: reproduce the 1.0-clustering against real
accumulated content, determine whether it is BM25/keyword-driven, a
reranking artifact, or a tunable Mem0 parameter, and establish whether
`search()` can be made to yield calibrated, differentiated similarity
scores. Only after that is the `get_all() → search()` migration
correctly scoped enough to implement as the actual fix.

---

## Deviations from the master prompt

- The master prompt said to append this synthesis to
  `docs/AIOS_GATE_BLINDNESS_INVESTIGATION_REPORT.md` "or wherever
  Subtask 1/2 findings were recorded." Subtasks 1 and 2 were reported in
  chat under a "skip commit" instruction, so no prior report file
  existed. This file was therefore **created** (not appended to), and it
  restates the Subtask 1/2 findings inline so the report is
  self-contained. No other deviation.
- The two diagnostic scripts from the chain
  (`scratch_mem0_cap_repro.py`, `scratch_retrieve_gates_probe.py`)
  remain uncommitted scratch, per their subtasks' "diagnostic script,
  not permanent code" instruction; only this report is committed.
