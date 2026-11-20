# Paper notes: the findings so far

Written 2026-11-20, at the end of NeurIPS Subtask 20. This file lists
each finding the main-track paper could report, as the documents and the
stored reports state it. It is notes to write from, not prose for the
paper. It holds no new analysis: every number is quoted from a document
or a stored report, with the interval that source gives.

## How to read this file

**Sources.** `DEV_STATUS.md` and every spec in `docs/`, as committed at
AIOS `980cbc5` (Subtask 20's last edits); and the runs' own records in
Cerebrum `results/<run>/` (`PROVENANCE.md` and the stored reports:
`analysis.md`, `report.md`, `directions.md`, `summary.md`, `cells.csv`),
as committed at Cerebrum `3b9c923`. `memory-providers.md` and
`CONTRIBUTE.md` were read and hold no count or interval. No project code
or test was run, and no raw results file was opened: where an entry
speaks of code, it repeats what a document says of it.

**Subtask 20's last results** (2026-11-20) are committed in both
repositories: the primary judge's reliability and its k, the agreement
between the judges, the primary judge's re-judge and the direction
agreement, Subtask 11's verdict on its score (Cerebrum `968029a`); the
decision check's Mem0 cells (Cerebrum `de12cbf`); the grid's letter rule
(`FULL_GRID.md`, "The decision items").

**An entry.** One finding per entry, under the claim or the paper
section it serves. The bold label states the finding in one line. Then:
- Numbers: with the interval the source gives. "No interval stated"
  means the source gives none.
- Run: the run's id and the commits its files record (AIOS, Cerebrum).
  "Runs" below gives each run's directory.
- Rests on: how many users, or a calibration set, a unit test or a
  document's reading of the code; and what the full grid does with it.
- Caveat: what qualifies it.

**Intervals.** A mean with brackets is a mean over users with its 95% t
interval; for a difference it is the paired difference over users. A
rate with brackets is a 95% Wilson interval. "a of b" is a count. A
difference is written "ablated − full kernel", "kernel − replicated" and
so on, as its source subtracts.

**"The grid".** The full grid is Subtask 23's final evaluation: "every
scored cell at 150 users" (`FULL_GRID.md`, citing `BENCHMARK_V2.md`
Amendment 7). That file is a stub; its cell list is open: "Open: the
full cell list (loci, backends, models, H, the stress levels), the users
per cell, the run order and the cost". It describes benchmark v2 cells.
So "the grid replaces it" marks a 5-user or 30-user number as
provisional, to be replaced by a 150-user cell the documents name or
imply. "Grid: not stated" means the documents name no grid cell for it;
that is the case for every benchmark v1 result, the pilot included.

## The findings in short

1. The pre-registered pilot (benchmark v1, 30 users, two models) gave
   GO: with two of three agents deviating, kernel − replicated on
   Integration is +0.82 [+0.43, +1.21] for Qwen and +1.18 [+0.63, +1.74]
   for GPT-4o, and the gap grows with the number of deviating agents
   (C1.4, C3.1). The verdict is GO on the hybrid score it registered, on
   the keyword score and on each judge's own score (L.1).
2. With reference agents the loci are not told apart, and on the
   in-house backend the kernel and the replicated agents build identical
   blocks (C1.1, C1.2).
3. Two variants carry the pilot's gap: another identity convention (V2)
   and a consumer's own retrieval settings (V4). The second holds by
   construction (C3.2, L.5).
4. The same two readings (a tie at H = 0, a gap at H = 2) hold on
   Graphiti and A-MEM, on Qwen only, and are not part of any rule (C2.2,
   C2.3).
5. On benchmark v2 (30 users, Qwen, H = 0) the kernel and the replicated
   agents delete a revoked fact completely and serve no superseded row;
   native does neither, by its design (C1.7). The judged score shows no
   kernel advantage there, and the backend moves it more than the locus
   (C1.9).
6. Under concurrency, a wrong-user writer and floods the kernel keeps
   its guarantees. Outside the kernel the measured cost is small, or
   shows in block measures only; these runs are judge-free, on 5 or 30
   users (C3.4 to C3.6). Agent count shows no growth, as its spec
   predicts (C3.7).
7. Four kernel switches each move their own measure on 30 users (C4.1 to
   C4.4). The other switches rest on 5 users or wait for the judge.
8. Every judge score stored before Subtask 20 is a hybrid of a keyword
   score and the judge's own (L.1). The two judges agree on the
   direction of every difference either can tell from zero (116 of 116),
   not on the level (L.2).
9. The judge-free decision items separate native from kernel and
   replicated on in-house (5 users), but without memory Qwen scores
   0.18, below chance, and native Mem0's right answers were guesses
   (C1.10, L.11, L.12).
10. The documents list eight silent failures of memory systems and tools
    met on the way, the paper's motivation (M.1). Before Subtask 5 the
    workshop kernel's relevance threshold never acted (L.13).
11. Only two runs were pre-registered (the re-validation and the pilot).
    Most other numbers rest on 5 or 30 users and one model, Qwen ("What
    each finding rests on").

## The claims, as read here

The four claim names are the user's: C1 locus, C2 generality, C3 grows
under stress, C4 mechanism. The documents name only C4. `ABLATION.md`
opens: "It answers a reviewer's question (Jg94; claim C4 in the claims
document): which of the kernel's responsibilities produce its advantage
over the replicated and native loci?" `DEV_STATUS.md`, Subtask 19,
repeats it: "(Jg94; claim C4)". The claims document is in neither
repository (no tracked file of either has "claim" in its name, and
`git grep` finds no other mention), and no document names C1, C2 or C3.
The readings below are therefore this file's, each tied to the text that
states or tests it.

**C1, locus.** Where the memory policy runs decides what the consumer
gets: in the kernel, in each agent as a copy of the kernel's library
(replicated), or in each agent's own use of its backend (native).
- `PILOT.md` states the thesis: "when the agents that share memory are
  built heterogeneously, memory logic in the kernel serves the consumer
  better than the same logic replicated in every agent."
- `REPLICATED_LOGIC.md` says why replicated is the control: "If
  kernel-managed memory beats it, the gain comes from where the logic
  runs, not from better logic."
- `NATIVE_USAGE.md` defines native: "the agents manage memory
  themselves, using each backend the way its documentation says to, and
  the kernel takes no part in memory. This is how people deploy these
  backends today."
- Without stress the documents predict a tie: "a tie is the correct
  result. Separation is predicted only under stress: concurrent
  cross-agent writes, heterogeneous copies, a faulty agent."
  (`REPLICATED_LOGIC.md`). So C1, read here, is not a claim that the
  kernel scores higher everywhere. It has two halves: with identical
  agents the loci tie (C1.1 to C1.3), and the kernel differs where
  agents differ or misbehave (the rest of C1, and C3).
- The pre-registered rule tests kernel − replicated only. Of native,
  `PILOT.md` says: "It informs the paper but not the decision, because
  its block and retrieval differ by design (known issue 13)."

**C2, generality.** The C1 and C3 results hold across memory backends
and assistant models. No document states this as a claim or gives it a
rule. What exists: the pilot on two backends (Mem0, in-house) and two
models (Qwen, GPT-4o); the pilot's design on Graphiti and on A-MEM with
Qwen, whose readings are "reported, not required" (`DEV_STATUS.md`,
Subtasks 16 and 17); and benchmark v2 smokes on four backends with Qwen.
`MODELS.md` fixes the stress-sweep pair as GPT-4o and Qwen-2.5:7B. The
grid's backends and models are open (`FULL_GRID.md`).

**C3, grows under stress.** The kernel's advantage over the other loci
grows with the stress level.
- The pilot's rule tests it for heterogeneity: "(ii) the gap grows with
  H (the H2−H0 difference-in-differences has a CI excluding 0)"
  (`PILOT.md`).
- `HETEROGENEITY.md` gives the reason: "kernel-managed memory puts one
  policy instance between the agents and the store, so it should be
  insensitive to how an agent was built. The replicated and native loci
  degrade as more agents deviate, because each agent applies its own
  copy of the policy (replicated) or its own convention (native)."
- `STRESS_DIMENSIONS.md` adds agent count, concurrency and a faulty
  agent (a wrong user id, missing metadata, floods): each "asks whether
  a property holds that only a layer seeing every writer can provide".
  Its measurements are judge-free: "No scored trial runs under these
  dimensions in this subtask: the scored runs wait for the full grid".
- For agent count the same spec predicts no growth of the effect: "At
  H > 0, the per-probe effect is flat in N; the number of deviating
  agents grows."

So only heterogeneity has a scored, pre-registered result for C3. The
other dimensions have judge-free results on 5 or 30 users.

**C4, mechanism.** Which kernel component produces which effect.
`ABLATION.md` gives the kernel one switch per responsibility: "Each
switch removes that one component, and each is paired with the
measurement that should move when it is gone." Its smoke covers four
switches on 30 users, in-house, Qwen, judge-free. The others rest on 5
users or wait for the judge.

## Terms

- **Loci.** Kernel (`kernel_shared`): the agents call the kernel, which
  runs the memory policy. Replicated (`replicated_<backend>`): each
  agent links the kernel's memory library (`aios/memory/pipeline/`) with
  its own barrier, resolver and settings. Native (`native_<backend>`):
  each agent calls its backend as the backend's documentation shows.
- **Backends.** In-house (Chroma, verbatim, no LLM); Mem0 (`mem0ai`
  2.0.2, facts extracted by Azure gpt-4o); Graphiti (`graphiti-core`
  0.31.2 on Neo4j); A-MEM (WujiangXu/A-mem-sys at `f303dfc`).
- **Models.** Assistants: Qwen-2.5:7B and Llama-3.1:8B on Ollama, GPT-4o
  on Azure. Judges: `gpt-5.4` on Azure (primary) and Claude Sonnet 5.5
  (second, since Subtask 20).
- **Benchmark v1** (`users_v1`, 150 users; `pilot_v1`, its first 30).
  One interaction per user: two writers store a profile and a task
  context, the consumer answers one question, and the judge scores
  Profile, Task and Integration from 1 to 5.
- **Benchmark v2** (`users_v2`; `pilot_v2`, its first 30). Six sessions
  written by three agents, then six probes: deletion, privacy, recall,
  recency and contradiction (judge-free, exact matching) and integration
  (judged). Since revision 4, two judge-free decision items per user
  (`d1`, `d2`), four options each.
- **H**, heterogeneity: how many of the three agents deviate from the
  reference (0, 1 or 2), each with one variant. V1 stale version
  (private writes, the old block). V2 identity convention (an email form
  of the user id). V3 missing metadata (no owner or policy; as a
  consumer, no visibility check). V4 tuned consumer (k 5, threshold 0.5,
  budget 1500). V5 raw-payload writer (JSON).
- **Judge-free measures.** `memories_missing`: writers none of whose
  rows reached the block, split into withheld (the writer stored nothing
  shared) and lost (it stored a shared row and none arrived). Leak rate:
  the share of trials whose block held another user's row or another
  agent's private row. `profile_facts_in_block`: the share of the
  profile's items in the block. A lenient recency or contradiction pass:
  the new value named, the stale one or not.
- **Scores.** The hybrid: round((keyword + LLM) / 2) per dimension, the
  score every run stored before Subtask 20. The keyword score: a
  judge-free count of the user's keywords in the answer. The LLM score:
  the judge's own.
- **Echo user.** A v2 user (one in three) for whom another writer
  restates the value that is later revoked. **Fold.** A Mem0 row of one
  fact into which its extraction wrote another fact's value.
- **Functional check.** Users 0 to 4, Qwen, no judge. **Smoke.** 30
  users, Qwen. Neither is pre-registered.
- **Pooled.** Each user's mean of the Mem0 and in-house differences (the
  pilot's primary measure). **DiD.** Per user, the difference at H = 2
  minus the difference at H = 0.

## Runs

Every run an entry cites. The directory is under Cerebrum `results/`.
Commits are those the results files record, as the run's `PROVENANCE.md`
or the document gives them.

| Run | Directory | Subtask | What ran | AIOS | Cerebrum |
|---|---|---|---|---|---|
| re-validation | `revalidation` (v2 judge: `revalidation_v2`) | 3, 4 | 150 generated users × 2 conditions × 3 models, pre-registered | `672665e` (GPT-4o), `19c3ea9` (Llama, Qwen) | `76dc9f1`, `99933e4` |
| provider smoke | `provider_smoke` | 5 | 30 `kernel_shared` trials per cell, 2 backends × 3 models, unpaired | `d7d8682` (Mem0), `9f06018` (in-house) | `c3dc42e` |
| native smoke | `native_smoke` | 6 | 30 trials per cell, 2 native conditions × 3 models | `0c59a28` | `066bc29` |
| `cc7` | `cost_check` | 7 | 10 GPT-4o trials × 2 conditions, "run to check the cost instrumentation, not to compare conditions" | `4d89763-dirty` (committed as `5f61bff`) | `52330ff-dirty` (committed as `f0e18ca`) |
| locus smoke | `locus_smoke` | 8 | 30 trials per cell, 3 models, unpaired | `149aa7d` | `408ceea` |
| `p9` | `pilot_v1` | 9 | 10 cells × 3 models × 30 users, sampled decoding; superseded | `c953fad-dirty` | `f9cf426-dirty` |
| `p9d` | `pilot_v1_9d`, re-judged in `pilot_v1_9d_greedy` | 9d | 10 cells × 3 models × 30 users, fixed decoding | `7cc3774` | `14b3c67`; re-judge `be72d70` |
| `h10` | `heterogeneity_check` | 10 | 18 cells × 5 users, Qwen, no judge | `709d0b4`, `da25e2c` | `268e270`, `04631f6` |
| `pv1` | `pilot_v1_hetero` | 11 | the pilot: 36 cells × 30 users, Qwen and GPT-4o, pre-registered | `ef05d66` | `7fc5769` |
| `f14c` | `bench_v2_functional` | 14 | v2, 21 cells × 5 users, Qwen, no judge | `554a408` | `1eb5ede` |
| `s14b` | `bench_v2_smoke` | 14 | v2, 6 cells × 30 users, Qwen | `208322c` | `2bb46b8` |
| replay | `native_mem0_ranking` | 15 | native Mem0's searches of `s14b`, replayed | | `7d4224a` |
| `f15a` | `bench_v2_functional_a3` | 15 | v2, 21 cells × 5 users | `38696f3` | `af078c3` |
| `f15b` | `bench_v2_functional_a4` | 15 | v2, 29 cells × 5 users | `945548e` | `059e5a5` |
| `s15b` | `bench_v2_smoke_a4` | 15 | v2, 6 cells × 30 users, k = 10 | `ef3fdc9` | `64da5f7` |
| `pg16e` | `pilot_v1_graphiti` | 16 | the pilot's design on Graphiti, H = 0 and 2, 6 cells × 30 users, Qwen | `d9ca01f` | `abfd503` |
| `s16` | `bench_v2_smoke_graphiti` | 16 | v2 on Graphiti, 3 cells × 30 users, k = 10 | `d9ca01f` | `c3f5ade` |
| `s17` | `bench_v2_smoke_s17` | 17 | v2, kernel and replicated at k = 30 on three backends, native Graphiti with its filter; 7 cells × 30 users | `612c989` | `2b9a776` |
| `pg17n` | `pilot_v1_graphiti_native_filter` | 17 | native Graphiti with its filter, H = 0 and 2, 30 users | `612c989` | `2b9a776` |
| `f17` | `bench_v2_functional_amem` | 17 | v2 on A-MEM, 14 cells × 5 users | `13708ee` | `56f0573` |
| `pa17` | `pilot_v1_amem` | 17 | the pilot's design on A-MEM, 6 cells × 30 users, Qwen | `a145a26` | `f6d2646` |
| `s17a` | `bench_v2_smoke_amem` | 17 | v2 on A-MEM, 3 cells × 30 users | `a145a26` | `f6d2646` |
| scheduler check | `scheduler_check_s18` | 18 | `pilot_v1` users 0 to 9, before and after the scheduler change | `7053e0a`, `c389539` | `d876f0f` |
| `f18b` | `stress_functional_f18b` | 18 | stress dimensions, 72 cells × 5 users (16 in the load cells), Qwen, no judge | `d451801` | `8ef6d6f` |
| `s18` | `stress_smoke_s18` | 18 | stress dimensions, 12 cells × 30 users, in-house, Qwen, no judge | `d451801` | `8ef6d6f` |
| `f19b` | `ablation_functional_f19b` | 19 | ablations, 22 cells × 5 users, in-house, Qwen, no judge | `64bbbee` | `bb7e845` |
| `s19` | `ablation_smoke_s19` | 19 | ablations, 10 cells × 30 users, in-house, Qwen, no judge | `64bbbee` | `bb7e845` |
| `d20a`, `d20m` | `decision_functional_s20` | 20 | decision items, 13 cells × 5 users per backend: in-house (`d20a`, 2026-11-19) and Mem0 (`d20m`, 2026-11-20), Qwen | `849fd09` (in-house), `d49afc9` (Mem0) | `87e5aa0` (in-house), `968029a` (Mem0) |
| `dn150` | `decision_nomemory150_s20` | 20 | decision items without memory, 150 users, Qwen | `20f2447` | `692319c` |
| reliability | `judge_reliability_s20` | 20 | `calibration_v1`: 200 answers × 10 repeats × 2 judges | `d49afc9` (the primary judge's kernel) | `26d2bc5` (the second judge's code; files produced from the tree on `7d19bf4` just before it), `6e912d1` (primary) |
| re-judge | `s20_rejudge` | 20 | 1,350 stored answers of `pv1`, `pa17` and `s17a`, by both judges | `d49afc9` (the primary judge's kernel) | `26d2bc5` (second; files record `7d19bf4-dirty`), `6e912d1` (primary) |

## C1: locus

**C1.1 The replicated agents run the kernel's own code, and on the
in-house backend the two loci build identical blocks.**
- Numbers: the equivalence test gives byte-identical prompts and
  identical diagnostics (without timings) for 20 seeded users. In the v2
  smokes the in-house kernel and replicated blocks are identical in 180
  of 180 paired probes (`s14b`, `s15b`, `s17`), in `s14b` the answers
  too. In the functional checks: 30 of 30 probes (`f14c`, `f15a`,
  `f15b`).
- Run: AIOS `tests/modules/memory/test_pipeline_library.py` (Subtask 8);
  `s14b` (AIOS `208322c`, Cerebrum `2bb46b8`); `s15b` (AIOS `ef3fdc9`,
  Cerebrum `64da5f7`); `s17` (AIOS `612c989`, Cerebrum `2b9a776`).
- Rests on: a unit test, and 30 users (Qwen, H = 0, judge-free). The
  grid replaces the smoke counts.
- Caveat: in-house only. On Mem0 the blocks differ (in all 30 probes of
  `f14c`), and some paired judge-free outcomes differ: in `s14b`
  discordant pairs on recall (0 and 1), recency (3 and 3) and
  contradiction (2 and 1), all p = 1.00; in `s15b` "1 of the 150 paired
  judge-free outcomes" (user 8's recency); in `s17` recency, 4
  kernel-only and 2 replicated-only passes (p 0.69). Mem0's extraction
  varies between runs (L.8). On A-MEM the kernel's and the replicated
  store's blocks hold the same writes in 106 of 180 probes (`s17a`), and
  every judge-free outcome agrees.

**C1.2 On benchmark v1 with reference agents (H = 0), kernel, replicated
and native are not told apart.**
- Numbers: paired, other − kernel, 30 users, greedy judge, 12
  comparisons × 3 dimensions: no 95% interval excludes 0. The largest
  mean differences are −0.27 [−0.59, +0.06] (Qwen, Mem0, replicated,
  Profile) and +0.23 [−0.04, +0.51] (GPT-4o, in-house, native, Profile).
  Equivalent within ±0.25 by TOST (p < 0.05): GPT-4o on Mem0, replicated
  and native, every dimension; Llama on Mem0, replicated, Task and
  Integration; Llama in-house, replicated, every dimension. The pilot's
  H = 0 cells agree: pooled kernel − replicated, Qwen Profile −0.02
  [−0.20, +0.17] and Integration +0.05 [−0.08, +0.18]; GPT-4o +0.05
  [−0.07, +0.17] and +0.03 [−0.12, +0.19].
- Run: `p9d` (AIOS `7cc3774`, Cerebrum `14b3c67`), re-judged greedily
  (Cerebrum `be72d70`); `pv1` (AIOS `ef05d66`, Cerebrum `7fc5769`).
- Rests on: 30 users (`pilot_v1`); three models in `p9d`, two in the
  pilot; hybrid scores (L.1). Grid: not stated.
- Caveat: not differing is not equivalence. `DEV_STATUS.md`: "Not shown
  equivalent at n = 30: the in-house and Qwen comparisons are
  inconclusive, with wide CIs."

**C1.3 Two earlier locus differences did not survive pairing and fixed
decoding.**
- Numbers: (a) Subtask 8, unpaired, in-house, Llama: replicated above
  the kernel by +0.47 Profile and +0.53 Integration (Welch p = 0.012
  against 60 pooled kernel trials; "Bonferroni p ≈ 0.2"). Paired on
  fixed users in Subtask 9 the Profile difference is +0.03 [−0.43,
  +0.49] (n = 29). (b) Subtask 9, paired, sampled decoding: Qwen, Mem0,
  native − kernel, Profile +0.63 [+0.18, +1.09] and Integration +0.53
  [+0.13, +0.93]. Under fixed decoding and the shared compact block
  (9d): Profile −0.10 [−0.54, +0.34].
- Run: (a) the locus smoke (AIOS `149aa7d`, Cerebrum `408ceea`); (b)
  `p9` (recorded as AIOS `c953fad-dirty`, Cerebrum `f9cf426-dirty`; tag
  `neurips-subtask-09`), then `p9d`.
- Rests on: 30 trials or users per cell. Both are superseded by C1.2.
- Caveat: (b) is an interval that excluded 0 and then vanished. Subtask
  9c's reading: "mostly answer noise (temperature 1.0, one answer per
  user), with a residual ~0.3 that needs the whole native block". For
  the paper it is the reason for fixed decoding, pairing and intervals,
  and a warning about any single 30-user cell.

**C1.4 Under heterogeneity the kernel scores above replicated (the
pre-registered primary measure).**
- Numbers: kernel − replicated at H = 2, pooled over Mem0 and in-house,
  n = 30. Qwen: Profile +0.73 [+0.26, +1.20], Integration +0.82 [+0.43,
  +1.21]. GPT-4o: Profile +1.15 [+0.62, +1.68], Integration +1.18
  [+0.63, +1.74]. At H = 1: Qwen +0.53 [+0.17, +0.90] and +0.67 [+0.31,
  +1.02]; GPT-4o +0.90 [+0.34, +1.46] and +1.02 [+0.43, +1.61]. Each
  backend alone, at H = 2 on each model: gaps between +0.70 and +1.23,
  each interval above 0. Verdict: GO. Conditions (i), (ii) and (iii)
  hold on both models, where the rule requires (i) and (ii) on one.
- Run: `pv1`, tag `pilot-v1-code` (AIOS `ef05d66`, Cerebrum `7fc5769`):
  36 cells, 1,080 trials, 0 failed, 2026-11-07 to 08. Design and rule:
  `PILOT.md`, committed and tagged before the first scored trial.
- Rests on: 30 users (`pilot_v1`), Qwen and GPT-4o, hybrid judge scores.
  Grid: not stated.
- Caveat: two variants carry the gap, one by construction (C3.2). The
  score is the hybrid; the verdict is GO on the keyword score and on
  each judge's own score too (L.1). The kernel's own scores fall with H
  as well (C3.3). One cell was re-run whole (Qwen `native_mem0` at H =
  0, not a cell of this difference).

**C1.5 Under heterogeneity the kernel also scores above native
(reported, not part of the rule).**
- Numbers: kernel − native at H = 2, pooled, n = 30. Qwen: Profile +0.55
  [+0.05, +1.05], Integration +0.62 [+0.14, +1.09]. GPT-4o: +0.88
  [+0.25, +1.52] and +0.88 [+0.18, +1.59]. At H = 0: Qwen −0.17 [−0.49,
  +0.16] and −0.15 [−0.43, +0.13]; GPT-4o −0.03 [−0.17, +0.10] and −0.05
  [−0.18, +0.08]. Per backend an interval can reach 0: Qwen, in-house,
  Profile at H = 2, +0.60 [−0.00, +1.20].
- Run: `pv1`, Cerebrum `results/pilot_v1_hetero/analysis.md`.
- Rests on: 30 users. Grid: not stated.
- Caveat: native differs from the kernel by design in more than the
  locus (L.4), which is why the rule leaves it out. On the other scores
  of Subtask 20's re-judge (`s20_rejudge/pilot_report/`), the same H = 2
  pooled kernel − native: Qwen keyword Profile +0.47 [−0.17, +1.10],
  Integration +0.65 [+0.04, +1.26]; Qwen second judge +0.43 [+0.01,
  +0.86] and +0.53 [+0.11, +0.96]; Qwen primary judge's own score +0.58
  [+0.03, +1.14] and +0.68 [+0.15, +1.22]; GPT-4o above 0 on all four
  scores (the smallest, the second judge's Profile, +0.72 [+0.21,
  +1.23]). So on Qwen the kernel − native gap holds on Integration under
  every score and on Profile under all but the keyword score, with lower
  ends near 0.

**C1.6 Judge-free, the kernel loses no shared memory and leaks nothing;
replicated and native lose shared rows, and only native leaks.**
- Numbers (share of trials, both backends pooled, the same on both
  models). Leak rate: kernel 0 of 180 trials per model; replicated 0;
  native 0.10 at H = 2, the three users whose V3 consumer is paired with
  a private V1 or V3 writer (users 5, 15 and 25). `memories_missing` at
  H = 1 and H = 2: kernel 0.20 and 0.53; replicated 0.50 and 0.87;
  native 0.45 and 0.75. Its split at H ≥ 1, lost and withheld: kernel
  0.00 and 0.37; replicated 0.37 and 0.37; native 0.33 and 0.32.
- Run: `pv1`; the split was recomputed from the same files in Subtask 14
  (Cerebrum `results/pilot_v1_hetero/missing_split.md`).
- Rests on: 30 users; no interval stated. The schedule fixes these
  figures: "The figures are identical on both models, because the
  variants decide them." Grid: not stated.
- Caveat: the leak needs the one pairing the schedule placed to expose
  it: `HETEROGENEITY.md` says "Native leaks are rare by construction."
  The kernel's `memories_missing` is not 0 (C3.3). Native's withheld
  share is lower because its V3 consumer leaks the private row instead.

**C1.7 On benchmark v2 the kernel and the replicated agents delete a
revoked fact completely and never serve a superseded value; native does
neither.**
- Numbers (`s15b`: H = 0, 30 users per cell, k = 10; passes, with the
  Wilson interval where it is not 30 of 30, which is 1.00 [0.89, 1.00]).
  Deletion: kernel and replicated 30 of 30 on both backends; native
  in-house 21 of 30, 0.70 [0.52, 0.83], its echo users 1 of 10; native
  Mem0 26 of 30, 0.87 [0.70, 0.95]. Recency: kernel and replicated
  in-house 30 of 30; kernel Mem0 22 of 30, 0.73 [0.56, 0.86]; replicated
  Mem0 23 of 30, 0.77 [0.59, 0.88]; native in-house 10 of 30, 0.33
  [0.19, 0.51]; native Mem0 0 of 30, 0.00 [0.00, 0.11]. Contradiction:
  kernel and replicated 30 of 30 in all four cells; native in-house 18
  of 30, 0.60 [0.42, 0.75]; native Mem0 0 of 30. In the four kernel and
  replicated cells no audit kept a carrier of a revoked value (120
  revokes), and no block of their 720 probes held a retired row;
  native's blocks held one in 168 of 180 probes in-house and 131 on
  Mem0. Trials whose revoked value showed in any block or answer: kernel
  and replicated 0 of 30 per cell; native in-house 10, native Mem0 11.
- Run: `s15b` (AIOS `ef3fdc9`, Cerebrum `64da5f7`), 180 user-trials, 0
  failed. The same holds for kernel and replicated on Graphiti (`s16`)
  and A-MEM (`s17a`): C2.5.
- Rests on: 30 users, Qwen, H = 0, judge-free. The grid replaces it.
- Caveat: for native this holds by construction. By Decisions 4 and 6 of
  `DELETION_AND_SUPERSESSION.md` the native writers revoke only their
  own rows and retire nothing: "nothing in either's documented usage
  retires a row". The kernel and replicated tie (one library), so the
  contrast is a shared rule against none, not kernel against agent.
  Before Subtask 15 every locus failed alike (`s14b`, kernel in-house:
  echo-user deletion 1 of 10, recency 8 of 30, contradiction 14 of 30).
  The Mem0 recency failures (8 kernel, 7 replicated) came through the
  new statement's own row, which Mem0 wrote as a transition ("moved from
  Ryver to Brosix"): "Each answer named the new value, and 14 of the 15
  named the old one as past." The strict rule fails an answer that names
  both values; the lenient pass is 30 of 30 in both Mem0 cells. Native
  Mem0's 26 deletion passes include 7 in trials whose revoked value
  showed in another probe's block or answer ("Trial-level exposure";
  known issue 43). A smoke: no rule was registered.

**C1.8 Privacy does not separate the loci at H = 0.**
- Numbers: the privacy probe passed 30 of 30 in every cell of `s14b` and
  of `s15b` (180 of 180 each), and no private value reached any block or
  answer. It failed only where a consumer skips the visibility check:
  native in-house with a V3 consumer (H = 2, user 4: 1 failure among the
  60 privacy probes of the real conditions, in `f15a` and in `f15b`),
  and the native `no_visibility` control (`f14c`: the value reached the
  probe's block for 5 of 5 in-house users and 1 of 5 Mem0 users). The
  kernel's privacy probe never failed: 0 of 35 (`f14c`), 55 probes
  (`f15b`).
- Run: `s14b`, `s15b`, `f14c` (AIOS `554a408`, Cerebrum `1eb5ede`),
  `f15a` (AIOS `38696f3`, Cerebrum `af078c3`), `f15b` (AIOS `945548e`,
  Cerebrum `059e5a5`).
- Rests on: 30 users at H = 0; 5 users at H = 2 and under the control.
  The grid replaces it.
- Caveat: the dataset helps the pass. `BENCHMARK_V2.md`: "Private facts
  are written last, so Mem0 never gets the chance to fold one into a
  shared fact. Whether it would is a separate question." In the stress
  spec's N = 3 derivation (two writers, as in v1) that placement cannot
  hold for 32 of the 150 users (`STRESS_DIMENSIONS.md`). A pass can also
  hide the value in the trial's other blocks: native Mem0's V3 consumer
  passed privacy while the private row reached 3 other blocks (known
  issue 43).

**C1.9 The judged v2 score (integration) shows no kernel advantage at H
= 0, and the backend moves it more than the locus.**
- Numbers (cell mean [95% t interval], 30 users, Qwen). At k = 10
  (`s15b`): in-house kernel 2.87 [2.50, 3.23], replicated 2.87 [2.50,
  3.23], native 3.10 [2.73, 3.47]; Mem0 kernel 3.57 [3.25, 3.89],
  replicated 3.60 [3.31, 3.89], native 3.00 [2.62, 3.38]. Graphiti
  (`s16`): 2.20 [1.99, 2.41], 1.97 [1.74, 2.20] and 2.00 [1.74, 2.26].
  With k = 30 for kernel and replicated (`s17`, `s17a`): in-house 2.57
  [2.23, 2.90] and 2.60 [2.27, 2.93]; Mem0 3.40 [3.07, 3.73] and 3.57
  [3.26, 3.87]; Graphiti 2.50 [2.15, 2.85] and 2.17 [1.91, 2.43], native
  2.07 [1.77, 2.36]; A-MEM 2.57 [2.20, 2.93] and 2.63 [2.22, 3.04],
  native 2.73 [2.32, 3.15].
- Run: `s15b`; `s16` (AIOS `d9ca01f`, Cerebrum `c3f5ade`); `s17` (AIOS
  `612c989`, Cerebrum `2b9a776`); `s17a` (AIOS `a145a26`, Cerebrum
  `f6d2646`).
- Rests on: 30 users, one judgment each, hybrid scores. The grid
  replaces it.
- Caveat: these are cell means; the documents give almost no paired
  locus difference on this score. The one they give is from `s14b`, on
  Mem0, kernel 3.33 against native 2.93 (paired t p = 0.05, Wilcoxon p =
  0.07): "An association in one pair of cells; the smoke does not
  explain this gap." At k = 10 native in-house's mean is above the
  kernel's (3.10 against 2.87; no test stated). Since Amendment 6 the
  loci also differ in k and budget (L.4). `BENCHMARK_V2.md` says of this
  score: "so it is not comparable with pilot_v1's integration". On
  `s17a` the two judges give opposite signs for kernel − replicated
  (+0.17 [−0.31, +0.65] and −0.23 [−0.60, +0.13]); neither interval
  excludes 0.

**C1.10 A judge-free task measure, the decision items, separates native
from kernel and replicated at H = 0 on in-house; on Mem0 native's
answers were guesses.**
- Numbers (Qwen, users 0 to 4, 10 items per cell; accuracy with its
  Wilson interval, from the stored `analysis.md`). In-house: kernel 10
  of 10, 1.00 [0.72, 1.00]; replicated 10 of 10; native 3 of 10, 0.30
  [0.11, 0.60], with 7 stale picks. With a wrong-user writer: kernel 10
  of 10; replicated 7 of 10, 0.70 [0.40, 0.89] (3 foreign picks); native
  6 of 10, 0.60 [0.31, 0.83] (3 foreign, 1 stale). Mem0: kernel and
  replicated 10 of 10 at H = 0; under `wrong_user` kernel 10 of 10,
  replicated 6 of 10 (3 foreign, 1 stale); native 4 of 10, 0.40 [0.17,
  0.69] at H = 0 and 1 of 10, 0.10 [0.02, 0.40] under `wrong_user`. The
  criteria over both backends: D1 met (47 of 60), D3 met (22 stale of 40
  against 0 of 40), D4 met (4 revoked of 8 against 0 of 8), D5 met (10
  foreign of 40 against 0 of 20); D2 not met (0 of 60; L.12). In-house
  alone: D1 23 of 30, D3 10 of 20 against 0 of 20, D4 2 of 4 against 0
  of 4, D5 6 of 20 against 0 of 10.
- Run: `d20a` (in-house, 2026-11-19: kernel AIOS `849fd09`, harness
  Cerebrum `87e5aa0`) and `d20m` (Mem0, 2026-11-20: kernel `d49afc9`,
  harness `968029a`), 13 cells per backend, 130 of 130 trials finished,
  no decision turn with an error. Result: Amendment 10, "The functional
  check's result" and "The functional check's Mem0 cells"; Cerebrum
  `results/decision_functional_s20/`.
- Rests on: 5 users, one model. The grid replaces it.
- Caveat: native in-house's stale picks are the absence of supersession,
  which native lacks by design (C1.7). An error names a memory failure
  only when the picked option's value is in the block: every stale,
  revoked and foreign error of an in-house cell with memory had it (26
  of 26); on Mem0, 19 of 33. Native Mem0's blocks held the correct
  option's value on none of its 20 items (its own search at k = 10), so
  "its 5 right answers were guesses, and 12 of its 15 errors were of a
  value not in the block": its decision accuracy measures no memory
  failure, though its `wrong_user` blocks did hold 3 to 7 of user i −
  1's rows (users 1 to 4). Of the 10 foreign errors that make D5, 8 had
  the foreign value in the block. An accuracy here is read within a
  model and paired: without memory Qwen scores 0.18, not 0.25, and the
  answer key of `pilot_v2`, the users of every functional check and
  smoke, is uneven (L.11).

**C1.11 The benchmarks tell memory from no memory; on v1 a full-context
baseline is at the kernel's level.**
- Numbers (`p9d`, greedy judge, cell means of 30 users, Profile / Task /
  Integration; no interval stated). `kernel_private` (the kernel with
  sharing off): 1.00 to 1.03 Profile and 1.00 Integration in every cell.
  `vanilla_rag`: Profile 1.90 to 2.30. `naive_concat` (the profile and
  task context pasted into the prompt, no memory system): GPT-4o 4.67 /
  4.80 / 4.53 against `kernel_shared` 4.73 / 4.97 / 4.67 on Mem0 and
  4.53 / 5.00 / 4.57 in-house; Qwen 2.93 / 4.50 / 2.93 against 3.80 /
  4.87 / 3.70 and 3.00 / 5.00 / 3.07; Llama 3.77 / 4.87 / 3.80 against
  4.07 / 4.87 / 4.07 and 4.03 / 4.87 / 3.97. On v2 the `no_memory`
  control failed recall, recency and contradiction 5 of 5 each (`f14c`,
  `f15a`, `f15b`).
- Run: `p9d`, Cerebrum `results/pilot_v1_9d_greedy/cells.csv`; the v2
  functional checks.
- Rests on: 30 users (v1); 5 users (v2 control). Grid: not stated for
  v1.
- Caveat: no paired comparison of a baseline against `kernel_shared` is
  in the documents. "Notes for the paper" 3: `kernel_private` "resolves
  §4.1's TODO"; the paper draft it refers to (`paper_v2`) "is in neither
  repo" (`DEV_STATUS.md`, Subtask 4). A v1 user has two memories, so the
  full-context baseline holds what the kernel injects: `BENCHMARK_V2.md`
  gives this as the reason for v2 ("No pressure": in the pilot's 1,080
  trials neither the cap nor the budget ever bound).

## C2: generality

**C2.1 The pilot's result holds on both models and on each backend
alone.**
- Numbers: conditions (i), (ii) and (iii) hold on Qwen and on GPT-4o
  (C1.4, C3.1). `PILOT.md`: "At H = 2 on each model, both backends' gaps
  lie between +0.70 and +1.23 with the CI above 0. Their DiDs lie
  between +0.73 and +1.30, also with the CI above 0."
- Run: `pv1` (AIOS `ef05d66`, Cerebrum `7fc5769`).
- Rests on: 30 users × 2 models × 2 backends (Mem0, in-house). Grid: not
  stated.
- Caveat: Llama is not in the pilot; it is in the H = 0 baseline only
  (C1.2). `PILOT.md`: "Mem0 extraction noise: not measured in this
  pilot."

**C2.2 On Graphiti (Qwen) the pilot's two readings hold: a tie at H = 0
and a gap at H = 2 in the pilot's direction.**
- Numbers (n = 30). Kernel − replicated: H = 0 Profile +0.20 [−0.03,
  +0.43], Integration +0.13 [−0.12, +0.39]; H = 2 Profile +0.73 [+0.23,
  +1.23], Integration +1.00 [+0.57, +1.43]; H2 − H0 +0.53 [+0.11, +0.96]
  and +0.87 [+0.40, +1.33]. Kernel − native: H = 0 −0.10 [−0.28, +0.08]
  and −0.07 [−0.23, +0.10]; H = 2 +0.57 [+0.03, +1.10] and +0.70 [+0.20,
  +1.20].
- Run: `pg16e` (AIOS `d9ca01f`, Cerebrum `abfd503`), 180 user-trials, 0
  failed. The native cells were run again with native's validity filter,
  `pg17n` (AIOS `612c989`, Cerebrum `2b9a776`): the native scores moved
  by −0.17 to −0.03, every interval holding 0, and "The kernel − native
  readings hold".
- Rests on: 30 users, Qwen only, hybrid scores. Grid: not stated.
- Caveat: "reported, not required": the rule is the pilot's, and no rule
  was set for this run. No GPT-4o cell. The backend cost of its H = 2
  agent cells is a lower bound (K.8).

**C2.3 On A-MEM (Qwen) the same two readings hold against replicated;
against native the H = 2 gap is weaker.**
- Numbers (n = 30). Kernel − replicated: H = 0 Profile +0.00 [−0.26,
  +0.26], Integration +0.00 [−0.24, +0.24]; H = 2 +0.67 [+0.11, +1.22]
  and +0.70 [+0.26, +1.14]. Kernel − native: H = 0 −0.07 [−0.49, +0.36]
  and −0.13 [−0.48, +0.22]; H = 2 Profile +0.50 [−0.08, +1.08],
  Integration +0.50 [+0.00, +1.00].
- Run: `pa17` (AIOS `a145a26`, Cerebrum `f6d2646`), 180 user-trials, 0
  failed.
- Rests on: 30 users, Qwen only, hybrid scores. Grid: not stated.
- Caveat: the kernel − native Profile interval at H = 2 includes 0, and
  the Integration interval starts at 0. On v1, A-MEM is not an
  independent replication. It stores each write verbatim, "with 3 notes
  a user and k 10 every note is in the block", and its answers equal
  in-house's, trial for trial, in all 30 kernel and 30 replicated trials
  at H = 0 (30 and 28 at H = 2). A V4 consumer applies its 0.5 threshold
  to native A-MEM's distance, so it keeps the farther notes: "It can
  lower native A-MEM's H = 2 scores."

**C2.4 Both judges give the same direction for every locus difference
either can tell from zero.**
- Numbers: the same direction on 139 of 164 paired differences, and on
  116 of 116 where either judge's 95% interval excludes 0. Every
  difference at H = 1 or 2 and every H2 − H0 difference agrees (120 of
  120). The 25 disagreements are all at H = 0: both intervals include 0,
  and no mean is further than 0.24 from zero. By run: `pv1` 126 of 144
  (104 of 104); `pa17` 13 of 18 (12 of 12); `s17a` 0 of 2 (none to
  count).
- Run: the re-judge, Cerebrum `results/s20_rejudge/directions.md`
  (committed `968029a`): 1,350 stored answers judged again by Claude
  Sonnet 5.5 (2026-11-19, one batch, none failed) and by `gpt-5.4`
  (2026-11-20, Cerebrum `6e912d1`, a kernel at AIOS `d49afc9`, none
  failed), each once per answer. `DEV_STATUS.md`, Subtask 20, "Direction
  agreement".
- Rests on: 30 users per cell; the stored answers of three runs. In the
  grid the second judge scores a fixed 30% of the users (45 of 150).
- Caveat: both are LLM judges on one prompt, and neither sees the block
  (L.16). The only human rating the documents mention is
  `benchmarks/human_rating`, "a frozen workshop-era study". The judges
  disagree on the level (L.2). In 16 of the 25 disagreements one judge's
  mean is exactly 0, "a zero mean is its own sign"
  (`s20_rejudge/PROVENANCE.md`).

**C2.5 On benchmark v2 at H = 0 the kernel and the replicated agents
pass the judge-free probes on four backends; the misses are Mem0's.**
- Numbers (30 users per cell, five judge-free probe types). In-house
  (`s15b`): 150 of 150 in each locus. Graphiti (`s16`): 30 of 30 on
  every type in both loci, agreeing on all 150 pairs. A-MEM (`s17a`):
  150 of 150 each, agreeing on every pair. Mem0 (`s15b`): recall 28 of
  30, 0.93 [0.79, 0.98], in both loci; recency 22 and 23 of 30 (C1.7);
  the other types 30 of 30.
- Run: `s15b` (AIOS `ef3fdc9`, Cerebrum `64da5f7`); `s16` (AIOS
  `d9ca01f`, Cerebrum `c3f5ade`); `s17a` (AIOS `a145a26`, Cerebrum
  `f6d2646`).
- Rests on: 30 users, Qwen, H = 0, judge-free. The grid replaces it.
- Caveat: Mem0's misses are the backend's own: two recall targets
  deleted with a fold (L.6) and recency rows written as transitions,
  whose answers named the new value (C1.7). Under k = 30 (`s17`) the
  rates are as at k = 10 but for recency on Mem0 (kernel 22 to 23,
  replicated 23 to 21 of 30) and one kernel Graphiti recency probe (30
  to 29).

**C2.6 How far native falls behind the kernel on v2 depends on the
backend.**
- Numbers (native, 30 users, H = 0; deletion / recall / recency /
  contradiction passes of 30). In-house (`s15b`): 21 / 30 / 10 / 18.
  Mem0 (`s15b`): 26 / 5 / 0 / 0. Graphiti without the validity filter
  (`s16`): 23 / 30 / 11 / 13; with it (`s17`): 23 / 30 / 30 / 26. A-MEM
  (`s17a`): 20 / 30 / 17 / 17. The kernel passes 30 on each (but Mem0's
  recall and recency, C2.5).
- Run: `s15b`, `s16`, `s17`, `s17a`.
- Rests on: 30 users, Qwen, judge-free. The grid replaces it; it adds
  one sensitivity cell, native at k = 30 on Graphiti.
- Caveat: with Graphiti's own validity marks, native matches the kernel
  on recency: a backend mechanism does there what the kernel's
  supersession does. Graphiti had marked invalid 52 of the kernel cell's
  60 retired rows. What remains on Graphiti is deletion, 23 of 30, every
  failure an echo row. The filter itself is the project's reading of
  Graphiti's documentation, adopted after the smoke (L.4). Native Mem0's
  numbers reflect Mem0's ranking, not the locus (L.4).

**C2.7 Models: three at H = 0 on v1, two under heterogeneity, one
everywhere else.**
- Numbers: none. `p9d` ran GPT-4o, Qwen and Llama. The pilot ran Qwen
  and GPT-4o. Every v2, Graphiti, A-MEM, stress, ablation and decision
  run is Qwen only ("Runs").
- Rests on: the run records.
- Caveat: no v2 result has a second model yet. The grid's models are
  open (`FULL_GRID.md`); `MODELS.md` names GPT-4o and Qwen as the
  stress-sweep pair, chosen so that "a sweep measures the memory system
  rather than writer failures". Llama's writers fail more often: in
  Subtask 9, 3 failed trials and 5 to 11 retried trials per Llama cell,
  none for GPT-4o or Qwen; in 9d, under fixed decoding, none in any
  cell.

## C3: grows under stress

**C3.1 The kernel − replicated gap grows with H (the pre-registered
condition (ii)).**
- Numbers: H2 − H0 difference-in-differences, pooled, n = 30. Qwen:
  Profile +0.75 [+0.24, +1.26], Integration +0.77 [+0.34, +1.20].
  GPT-4o: +1.10 [+0.57, +1.63] and +1.15 [+0.59, +1.71]. H1 − H0: Qwen
  +0.55 [+0.11, +0.99] and +0.62 [+0.21, +1.02]; GPT-4o +0.85 [+0.27,
  +1.43] and +0.98 [+0.38, +1.59]. The gaps themselves at H = 0, 1 and
  2, Integration: Qwen +0.05, +0.67, +0.82; GPT-4o +0.03, +1.02, +1.18.
- Run: `pv1` (AIOS `ef05d66`, Cerebrum `7fc5769`); `PILOT.md` and
  Cerebrum `results/pilot_v1_hetero/analysis.md`.
- Rests on: 30 users, hybrid scores; on the other three scores the DiD's
  interval is above 0 too (L.1). Grid: not stated.
- Caveat: three levels of one dimension. No H2 − H1 difference is
  reported. `PILOT.md`: "The variant mix is a design choice, and other
  mixes would give other magnitudes."

**C3.2 Two variants carry the gap, one of them by construction (V4).**
- Numbers (H = 1, pooled kernel − replicated, Profile / Integration, 3
  users per variant and role, no interval stated). V2 consumer: Qwen
  +2.50 / +2.50, GPT-4o +3.67 / +3.50. V4 consumer: +1.50 / +1.50 and
  +3.17 / +3.17. V2 writer, Integration: +1.33 and +3.17. V1 and V3
  private writers: −0.17 to +0.33. V5, writer and consumer: −0.17 to
  +0.17. "Replicated misses memories in every V2 and V4-consumer trial,
  the kernel in none."
- Run: `pv1`; `PILOT.md`, "Against the pre-stated expectations" and
  "What the GO rests on".
- Rests on: 3 users per variant and role. Grid: not stated.
- Caveat: `PILOT.md` says it itself: "The V4 effect holds by
  construction. The kernel has no channel for a consumer's settings
  (`variants_not_applied`), so it measures what centralizing the
  settings buys, not a better retrieval algorithm." V2 rests on a
  premise as well (`HETEROGENEITY.md`): "A replicated deployment could
  give every agent's resolver the same rules. V2's premise is that one
  team uses a different convention, which means its resolver does not."
  The ablation `consumer_config: honor` measures what the V4
  construction is worth (C4.7). The pre-stated "V5 degrades every locus"
  was not seen: "V5 did not show up in any gap", and "Whether V5 lowers
  every locus by the same amount is not separated here."

**C3.3 The kernel is not insensitive to heterogeneity: it loses what a
deviating writer keeps private.**
- Numbers: the kernel's `memories_missing` rate is 0.20 at H = 1 and
  0.53 at H = 2 (C1.6), all of it withheld: 28, 28, 20 and 20 missing
  writer instances (V1 and V3 profile writers, V1 and V3 task writers),
  none lost. The kernel's cell means fall with H (Profile / Task /
  Integration): GPT-4o, in-house, 4.70 / 5.00 / 4.63 at H = 0 and 3.67 /
  4.00 / 3.10 at H = 2; Qwen, Mem0, 3.73 / 4.93 / 3.67 and 3.27 / 4.00 /
  2.87. Under the `missing_metadata` fault (5 users, in-house) the
  kernel's `memories_missing` rises as replicated's does: +0.40 [−0.28,
  +1.08] in both.
- Run: `pv1` (`analysis.md`, "Cells"; Subtask 14's split); `f18b` (AIOS
  `d451801`, Cerebrum `8ef6d6f`).
- Rests on: 30 users (pilot); 5 users (the fault). The grid replaces the
  fault's numbers.
- Caveat: the specs intend this. `HETEROGENEITY.md`: "The kernel is
  protected only from the leak, not from the miss."
  `STRESS_DIMENSIONS.md` calls the fault "a control: the kernel is not
  immune". The thesis sentence "it should be insensitive to how an agent
  was built" needs this qualifier in the paper.

**C3.4 Concurrency: only the kernel's reads wait for other agents'
writes; the measured outcome cost outside the kernel is small.**
- Numbers (`s18`: 30 users, in-house, six agents, H = 0, against the
  same users' sequential trial). The kernel's 180 probes waited (median
  114 ms, at most 248) and read no late write; every outcome as
  sequential. Replicated had 552 late writes, native 498. Outcomes lost:
  replicated 2 contradiction probes, both stale reads (exact McNemar p
  0.5); native 1 (p 1); nothing else moved. `memories_missing`:
  replicated +0.00 [+0.00, +0.00], native −0.03 [−0.10, +0.03]. On Mem0
  (`f18b`, 5 users) the kernel's probes waited a median 3.7 s, a write
  there being a GPT-4o call, with no timeout.
- Run: `s18` and `f18b` (both AIOS `d451801`, Cerebrum `8ef6d6f`). The
  unit demonstration of Subtask 8 (Cerebrum
  `tests/agents/_replicated_checks.py`): with per-agent barriers a read
  during another agent's accepted write misses it; with one shared
  barrier it waits about 0.3 s and sees it.
- Rests on: 30 users, in-house only, judge-free; Mem0 on 5 users. The
  grid replaces it: "their scored runs wait for the grid".
- Caveat: a late write can still be read: 366 of replicated's 552 and
  210 of native's 498 were in the same probe's block. Only the last
  session's writes can race, and there 6 users have a recency target and
  4 a contradiction target. The spec expected the effect "whenever a
  probe's target was written in the last session" on Mem0, where a write
  takes seconds; the 30-user run is in-house. The kernel was changed so
  that a race could occur at all: before, "concurrent writers were
  serialized at the HTTP layer and no probe could race a write". Not
  crossed with heterogeneity or a fault.

**C3.5 A writer that tags the wrong user: the kernel serves the
session's user; replicated and native file the rows under the next
user.**
- Numbers (`f18b`, 5 users per cell). Kernel: 0 misfiled rows, and
  `identity_overridden` on each of the faulty writer's 27 requests.
  Misfiled rows / cross-user rows in the victim's blocks /
  `memories_missing`: replicated in-house 27 / 88 / +0.80 [+0.24,
  +1.36]; replicated Mem0 32 / 81 / +1.00 [+0.12, +1.88]; native
  in-house 27 / 65 / +1.00 [+0.12, +1.88]; native Mem0 34 / 73 / +1.20
  [+0.64, +1.76]. Decision items (`d20a`, 5 users, in-house): foreign
  picks 0 of 10 in the kernel, 3 of 10 in replicated, 3 of 10 in native.
- Run: `f18b`; `d20a` (AIOS `849fd09`, Cerebrum `87e5aa0`).
- Rests on: 5 users. There is no 30-user replicated or native cell with
  this fault; the 30-user evidence is the kernel's own ablation (C4.2).
  The grid replaces it.
- Caveat: in these 5-user cells no judge-free probe type lost or gained
  more than one user. `STRESS_DIMENSIONS.md` states the premise "for a
  reviewer to weigh": "a replicated deployment could hand each agent's
  library the session's user too, but the faulty agent is the one that
  would have to use it." Kernel sessions were added in this subtask, for
  this fault.

**C3.6 Floods: the kernel's write quota keeps the flood out; replicated
and native store all of it, and their blocks lose profile facts.**
- Numbers (`s18`: 30 users, in-house, against the no-fault trial; F = 10
  and F = 50 flood rows per session). Kernel: 94 and 98 flood writes
  accepted, never more than the quota allows in a turn, no reference
  writer's write rejected; `memories_missing` −0.03 [−0.24, +0.17] at
  both levels; profile facts in the integration block +0.00. Replicated
  and native accepted all 530 and 2,650. `memories_missing`: replicated
  +0.60 [+0.21, +0.99] and +1.03 [+0.57, +1.50]; native +0.60 [+0.23,
  +0.97] and +1.47 [+1.03, +1.90]. Profile facts: replicated −0.23
  [−0.38, −0.07] and −0.53 [−0.72, −0.34]; native −0.36 [−0.54, −0.18]
  and −0.69 [−0.86, −0.52]. Flood rows per probe's block: kernel 1.71
  and 1.82; replicated 6.43 and 10; native 4.33 and 7.06.
- Run: `s18` (AIOS `d451801`, Cerebrum `8ef6d6f`), Cerebrum
  `results/stress_smoke_s18/analysis.md`.
- Rests on: 30 users, in-house, judge-free. The grid replaces it.
- Caveat: no judge-free probe of replicated was lost at either level;
  the report shows one deletion probe gained at each level and nothing
  else. Native's outcomes moved both ways
  (`stress_smoke_s18/analysis.md`, "Faults"): at F = 50 recency 1 lost
  and 11 gained (p 0.0063), "Not read as the flood helping", and
  contradiction 5 lost and 3 gained (p 0.73). So for replicated the
  flood's cost shows in block measures only, and its effect on a judged
  score is not measured. The replicated result is by construction: "the
  flooder is the agent that fails to apply it: its pipeline is built
  without the quota". The flood is benign (restated facts and irrelevant
  notes): "adversarial rows written to be retrieved (poisoning) are not
  tested, and the quota is not a defense against them".

**C3.7 Agent count: nothing changes with N on in-house at H = 0, as
predicted; a gap that grows with N is not tested.**
- Numbers (`f18b`, 5 users; N = 3, 6 and 12 agents). In-house at H = 0:
  every judge-free outcome (25 of 25 per locus) and every block (30 of
  30, byte for byte) is the same at each N, in all three loci. At H = 2,
  against H = 0 at the same N, `memories_missing` rose by 0.4 to 2.4 in
  every locus and N, with no cross-user row. On Mem0 the outcomes agreed
  across N in 24 of 25 (kernel), 17 of 20 (replicated) and 15 of 15
  (native).
- Run: `f18b`.
- Rests on: 5 users, judge-free. The grid replaces it.
- Caveat: the spec predicts no growth of the per-probe effect with N,
  and says so against its brief: "This differs from the brief's
  expectation that more writers bring more identity and visibility slips
  in replicated and native." And `DEV_STATUS.md`: "five users are too
  few to test the spec's prediction that the per-probe effect is flat in
  N". So C3 has no evidence from agent count. On Mem0 the write-up found
  that "the kernel is unaffected except cost" holds "for the kernel's
  own path but not for a backend that extracts per writer": 5 of the 60
  trials at N = 12 failed because Mem0 stored nothing for one sentence
  (M.2).

**C3.8 On benchmark v2 at H = 2 the pilot's two mechanisms appear again
(5 users).**
- Numbers: in `f14c`, 4 of the 13 recall failures of the real conditions
  are user 0's V2 consumer at H = 2, "in all four agent-managed cells:
  its partition holds no writer row (the kernel resolves the id and
  passes)". In `f15b`, at H = 2, replicated leaves user 4's first
  `home_city` row unmarked on both backends, because its V2 profile
  writer stores it under an email form of the id: "The kernel folds the
  domain into the canonical id and marks the row." The one privacy
  failure of a real condition is native in-house's V3 consumer (C1.8).
- Run: `f14c` (AIOS `554a408`, Cerebrum `1eb5ede`); `f15b` (AIOS
  `945548e`, Cerebrum `059e5a5`).
- Rests on: 5 users, Qwen, judge-free. The grid replaces it.
- Caveat: no scored v2 run at H > 0 exists. In the v2 checks H = 2 is
  "reported, not required".

**C3.9 Under load, the barrier wait did not grow (the spec predicted it
would).**
- Numbers and run: K.6. `DEV_STATUS.md`: "the spec's prediction that a
  probe's barrier wait would grow with them did not hold: in the load
  mode a user's probes start after its own writes have completed". The
  load mode runs the kernel only, so it compares no locus.

## C4: mechanism

Each ablation removes one component from the kernel and pairs the
ablated cell, user by user, with the full kernel under the condition
named. C4.1 to C4.4 are the smoke `s19` (30 users); C4.5 to C4.8 rest on
the functional check `f19b` (5 users). Both ran on AIOS `64bbbee` and
Cerebrum `bb7e845`, in-house, Qwen, six agents, judge-free. Differences
are ablated − full kernel.

**C4.1 The write barrier (`barrier: off`, under concurrency) is what
makes a read wait for accepted writes.**
- Numbers (`s19`): covered late writes per user +18.10 [+16.37, +19.83]
  (543 over 180 probes; the full kernel none, its probes waiting a
  median 146 ms, at most 373). Stale reads per user +0.23 [−0.00,
  +0.47]; timing misses +0.10 [−0.01, +0.21]; `memories_missing` −0.10
  [−0.25, +0.05]. Outcomes lost: deletion 2 (p 0.50), recency 3 (p
  0.25), contradiction 3 (p 0.25).
- Run: `s19`, Cerebrum `results/ablation_smoke_s19/analysis.md`: 10
  cells, 300 trials, none failed.
- Rests on: 30 users. Grid: one confirmatory ablation each on Graphiti
  and A-MEM (`ABLATION.md`); which switch is open, and a 150-user repeat
  of this cell is not stated.
- Caveat: only the primary measure's interval excludes 0. The report
  marks the stale-read and timing-miss predictions not confirmed, and no
  outcome loss is significant. The ablated kernel missed more than
  replicated did on the same users (7 stale reads, 3 timing misses and 3
  late forgets, against replicated's 2 stale reads): "more of its late
  writes landed after the search; why was not looked into". The
  comparison with replicated is "not tested: they ran at other commits".

**C4.2 Session-bound identity (`identity: claim`, with a wrong-user
writer) is what keeps rows in their user's partition.**
- Numbers (`s19`): misfiled rows per user +4.03 [+3.22, +4.85] (121
  rows; the full kernel overrode 133 faulty requests and misfiled none).
  Cross-user rows in the blocks +12.23 [+8.43, +16.04].
  `memories_missing` +0.67 [+0.49, +0.85]. Outcomes lost: recall 5 (p
  0.06), recency 6 (p 0.03), contradiction 6 (p 0.03), privacy 1;
  deletion 1 lost and 1 gained. In `f19b` (5 users): 27 misfiled rows,
  88 cross-user rows in blocks and `memories_missing` +0.80, the three
  numbers of replicated in-house in `f18b` (C3.5).
- Run: `s19`; `f19b`.
- Rests on: 30 users; 5 users for the match with replicated. Grid: as
  C4.1.
- Caveat: `memories_missing` rose less than the spec's "about 1": the
  faulty writer was already missing from 5 of 30 blocks on the full
  kernel, cut by the budget. With V2 on the profile writer (5 users) the
  registered rule, profile facts in the block 0 for every user, "did not
  hold as written: one user's block had 1 of 6 profile facts", a fact
  carried by the task agent's row. "Recorded as a deviation; the rule is
  left as registered." The lost privacy probe is a coincidence of names
  (user 27's misfiled row carried the name of user 28's private fact).

**C4.3 The write quota (`quota: off`, under floods) is what keeps a
flood out of the blocks.**
- Numbers (`s19`, F = 10 and F = 50): flood rows in the block per probe
  +4.72 [+4.10, +5.34] (1.71 to 6.43) and +8.21 [+7.50, +8.92] (1.82 to
  10.03). Profile facts in the block −0.23 [−0.38, −0.07] and −0.53
  [−0.72, −0.34]. `memories_missing` +0.63 [+0.32, +0.95] and +1.07
  [+0.68, +1.46]. Flood writes accepted 530 and 2,650, against the full
  kernel's 94 and 98.
- Run: `s19`.
- Rests on: 30 users. Grid: as C4.1.
- Caveat: "No probe lost": no judge-free outcome fell at either level.
  The ablated kernel reproduces replicated's numbers in `s18` (6.43 and
  10 flood rows per probe; profile facts −0.23 and −0.53 with the same
  intervals), at other commits. In `f19b` (5 users) the profile facts
  did not fall at F = 10 (0.00).

**C4.4 The user-scoped forget (`forget_scope: writer`) is what removes
another writer's copy of a revoked value.**
- Numbers (`s19`): carriers left in the store per user +0.67 [+0.31,
  +1.02]. Each of the 10 echo users kept 2 carriers and failed the
  deletion probe; the 20 others passed in both runs. Deletion lost 9 (p
  0.004). The earlier control on both backends and both loci (`f15b`,
  `writer_scoped`, 5 users): 6 of its 8 echo-user deletion probes
  failed.
- Run: `s19`; `f15b` (AIOS `945548e`, Cerebrum `059e5a5`).
- Rests on: 30 users in-house; 5 users on Mem0. Grid: as C4.1.
- Caveat: the full kernel failed one echo user's deletion probe (29 of
  30) with no carrier in its block: Qwen named the revoked chat app
  among popular ones, and a guess fails the probe (L.15).

**C4.5 Visibility (`visibility: off`, with a V3 consumer) is what keeps
another agent's private row out of the block.**
- Numbers (`f19b`): the privacy probe failed for 5 of 5 users, its value
  in the block; the full kernel's never failed.
- Rests on: 5 users. Not in the smoke: `ABLATION.md` keeps the smoke for
  switches "whose mechanism is not definitional". Grid: as C4.1.

**C4.6 Supersession (`supersession: off`) is what keeps an earlier
statement out of the block.**
- Numbers (`f19b`): an earlier statement's row in 10 of 10 recency and
  contradiction blocks; recency passed 0 of 5, contradiction 3 of 5 (the
  spec predicted 1 of 5 and 3 of 5). Decision items (`d20a`, `d20m`,
  `no_supersession`): in-house 5 of 10 correct with 5 stale picks, on
  Mem0 4 of 10 with 6 stale, in the kernel and in replicated alike,
  against 10 of 10 with supersession. The earlier control (`f15b`,
  `no_supersession`, both backends and both loci) put a retired row in
  109 of its 120 probes.
- Run: `f19b`; `d20a` (AIOS `849fd09`, Cerebrum `87e5aa0`) and `d20m`
  (AIOS `d49afc9`, Cerebrum `968029a`); `f15b`.
- Rests on: 5 users. Grid: as C4.1.

**C4.7 Consumer-config enforcement (`consumer_config: honor`, with a V4
consumer): what the V4 construction is worth.**
- Numbers (`f19b`): under `honor` the kernel's V4 block equals the
  replicated V4 block in 30 of 30 probes; on the full kernel the V4
  consumer's block equals the H = 0 block in 30 of 30. Under `honor`:
  rows per probe 13.6 to 1.2, profile facts 1.0 to 0.0,
  `memories_missing` +3.6. No interval stated.
- Run: `f19b`.
- Rests on: 5 users, judge-free. Grid: as C4.1.
- Caveat: this is the measurement that answers the V4 critique (C3.2).
  `ABLATION.md`: "the difference between `kernel` and `honor` is what
  that construction is worth." It has no judged score yet.

**C4.8 Formatting and budgeted ranking: no result yet.**
- Numbers (`f19b`, judge-free only). `block_format: legacy` and
  `block_order: similarity`: the blocks differ from the full kernel's in
  30 of 30 probes, and legacy adds 3 tokens per probe. `budget: off`:
  the budget binds in no probe (4.8 of 6 per user on the full kernel)
  and the block grows by 73 tokens per probe. `threshold: 0.3`: 0.27
  fewer rows per probe.
- Rests on: 5 users. The grid scores these rows (`ABLATION.md`: "The
  score waits for the full grid").
- Caveat: the predictions are "Qwen sensitive, GPT-4o not (Subtask 9c)"
  for formatting and "small" for the budget. Subtask 9c's own 2 × 2 on
  Qwen (format × facts and order) found that neither factor alone moved
  Profile (+0.03 and +0.00); together +0.27 [−0.05, +0.58], and
  Integration +0.30 [+0.04, +0.56]. Earlier, unpaired: in the Subtask 5
  provider smoke the injected set stayed the same but the order changed
  (the task context first in 177 of 180 trials), and in-house Qwen's
  Profile mean moved +0.57 and Integration +0.41 against the
  re-validation's Mem0 cell (30 trials, no interval stated); that
  comparison also changes the backend, and no cause is established.

**C4.9 What the ablations do not show.**
- In-house, Qwen and six agents only: "Mem0's extraction changes what a
  write stores, so its differences are larger and noisier". Each switch
  is removed alone. The switch is removed from the kernel, not from an
  agent: "It says what the component is worth inside the kernel, not
  what an agent that implemented it would get."
- In `f19b` 13 of the 14 rules held, and at n = 5 three predicted
  primary intervals included 0.
- The report's code was the least tested area before the mutation run's
  tests: 43 of its 50 mutants survived its tests, 36 of them changing
  what `f19b` or `s19` reported. It is now pinned by tests that
  regenerate both reports from the records.

## Motivation

**M.1 The documents' list of silent failures: memory systems and tools
that failed without an error.**

`DEV_STATUS.md`, "Notes for the paper" 2, calls these "the motivation's
evidence that real memory systems fail quietly". Each was met while
building the benchmark:
- The judge's keyword-only fallback (Subtask 4b). A judge call that
  failed fell back to a keyword-only score. Fixed: the judge retries,
  then the trial fails. No count of affected trials is stated.
- Writers that stored a status payload (Subtasks 8 and 9). In one Llama
  cell the task writer's extraction returned no task fields in 10 of 30
  trials (for example "status: success. message: Task context extracted
  successfully."), against 1 of 30 in the first draw and 2 of 30 in
  replicated (the Subtask 8 locus smoke, in-house Llama), and the
  payload was stored as the memory. Fixed: writers validate, retry
  twice, then store nothing and fail the trial.
- Mem0 swallows its extraction errors (Subtask 10; Amendment 9). From a
  network Azure refused, a native Mem0 cell ran 5 trials with 0 backend
  calls and 0 injected rows, and every trial was recorded as completed.
  `mem0ai` 2.0.2 logs and swallows four failures of a write (the
  extraction call, parsing its reply, embedding, inserting) and stores
  nothing.
- Ollama truncates a long prompt (known issue 29). Ollama 0.40.11 read
  an 8,354-token prompt as 2,050 tokens, with no error; the code in its
  first line came back wrong. The pilot's largest Qwen prompt was 456
  tokens, never cut.
- The library dropped a failed retrieval (Amendment 2): "Before, a
  failed fetch looked like an empty store, so deletion and privacy
  passed."
- A listing missed an acknowledged write (Amendment 2): every kernel
  user's listing after the last probe missed that probe's conversation
  row.
- Mem0's search score is a clamped distance (`NATIVE_USAGE.md`,
  "Evidence"): the more similar a row is above cosine 0.5, the later
  Mem0 returns it. In `f14c`, 1,024 of the 1,030 rows native Mem0
  injected scored exactly 1.0 (L.4).
- Mem0 folds a revoked value into another fact's row (known issue 38),
  where a delete by the fact's key misses it: users 13, 19 and 25 in
  `s14b` (L.6).
- Rests on: single incidents and small counts, each with its fix and a
  test. They are not rates.
- Caveat: Subtask 10's record of the guard says "real memory systems
  fail quietly, and only a layer that sees every write notices. It
  belongs in the paper's motivation." The documents do not test its
  second half. What caught these were the harness's checks, which run in
  every locus (the extraction guard, the pre-flight, the listings), and
  since Amendment 9 the Mem0 write of every locus raises. So the
  evidence is that such failures occur and are quiet, not that the
  kernel detects them. By origin: three are Mem0's (the swallowed
  errors, the clamped score, the fold); one is Ollama's; one is the
  writers' model output; three are the project's own code (the judge's
  fallback, the dropped retrieval error, the listing).

**M.2 Further quiet failures the documents record, not in that list.**
- Azure gpt-4o fences its JSON. In the re-validation's first run 102 of
  150 and 100 of 150 GPT-4o trials failed in data generation. And "a
  fenced agent reply lost that memory without failing the trial (1 of
  the 48 completed GPT-4o trials injected no task context). The driver
  counted trials, not failures, and reported success."
- `written_memories` was empty in every trial ever run before Subtask 4
  (the harness patched a name the agents did not use), and
  `memory_counts` was 0 in every trial, the workshop's included.
- Mem0's `get_all` returns at most 20 rows unless told otherwise, and
  returns them unranked (L.13).
- Mem0 stored nothing for one vague sentence when its writer had written
  little for the user: 7 of 16 times with twelve agents and 1 of 6 under
  concurrency, never in 54 writes with three or six agents (known issue
  53). These were empty extractions, not swallowed errors.
- Graphiti sometimes extracts a write's entities and no fact: 3 of 720
  writes in its functional check, each of which gave a fact in another
  run. Its `search()` returns facts it has itself invalidated (in `s16`,
  32 of native's 36 recency and contradiction failures). `search()` also
  writes its result limit into a recipe object that ingestion reads, so
  one consumer's limit of 5 stayed for the next users' writes until the
  Subtask 16 review.
- A-MEM catches its LLM's failures and stores the note without
  attributes. Its evolution writes text drawn from the user's other
  notes, another agent's private ones included, into a note's tags and
  context: on review the kernel's rows, which carried that text, were "a
  path past the visibility rule". It was found after the A-MEM
  functional check and fixed before its two smokes; no reported number
  changed.
- `Mem0Provider.get` read every exception as a missing row, so a forget
  could file a row it failed to read as not found and succeed (fixed in
  Subtask 15's review).
- A V2 agent's backend calls were not counted in v1 (K.8).
- Rests on: the documents' incident records. Whether any of these joins
  the paper's list is the author's choice ("Open decisions").

**M.3 A delete in a backend does not remove what the backend keeps
elsewhere.**
- Numbers: Mem0 reads its last 10 stored messages into each extraction,
  and a delete leaves them; until Subtask 15 every kernel and replicated
  Mem0 store shared one history file (about 84 MB on 2026-11-10).
  Deleting a Graphiti episode leaves a fact another episode restated,
  with the deleted episode's sentence; a forgotten value can also sit in
  episode texts, entity names and summaries, which later writes read.
  A-MEM's evolution can leave a deleted note's value in other notes'
  tags and context. Chroma keeps the text of every deleted row in its
  write-ahead log: every store measured on 2026-11-10 still held the
  record of each row ever deleted (kernel Mem0 111 of 111, kernel
  in-house 65 of 65, each `f15a` replicated store 10 of 10).
- Run: `DELETION_AND_SUPERSESSION.md`, `GRAPHITI_BACKEND.md` and
  `AMEM_BACKEND.md` (each from the backend's source and an exploration);
  the Chroma count is a store inspection.
- Rests on: readings of the backends' code, explorations of one user,
  and one inspection.
- Caveat: the kernel's forget scrubs Mem0's messages and history,
  Graphiti's episode texts, entity names and summaries, and A-MEM's
  derived text. It does not reach Chroma's log (L.7).

**M.4 This codebase's own identity and visibility bugs came from single
agents.**
- Numbers: none. `STRESS_DIMENSIONS.md`: "every identity and visibility
  bug so far came from one agent's own handling of a shared convention
  (known issue 10, the `latest_user_id` contamination fixed before
  Subtask 1, the user-less searches)".
- Rests on: the project's own history. An anecdote that grounds V2 and
  the wrong-user fault, not a measurement.

## Limitations

**L.1 Every judge score stored before Subtask 20 is a hybrid of a
keyword score and the judge's own score.**
- Numbers: per dimension, hybrid = max(1, min(5, round((keyword + LLM) /
  2))), with Python's `round`, which rounds halves to even (2.5 → 2, 3.5
  → 4). The stored results keep neither half. The keyword score,
  recomputed from the records, is consistent with 3,240 of 3,240 stored
  scores. The pilot's verdict on each score (Integration, pooled kernel
  − replicated at H = 2, then the H2 − H0 DiD):
  - hybrid, as registered: Qwen +0.82 [+0.43, +1.21] and +0.77 [+0.34,
    +1.20]; GPT-4o +1.18 [+0.63, +1.74] and +1.15 [+0.59, +1.71];
  - keyword only: Qwen +0.95 [+0.46, +1.44] and +0.90 [+0.39, +1.41];
    GPT-4o +1.33 [+0.71, +1.96] and +1.27 [+0.65, +1.89];
  - the second judge's own score: Qwen +0.73 [+0.39, +1.08] and +0.63
    [+0.22, +1.04]; GPT-4o +0.97 [+0.48, +1.45] and +1.02 [+0.54,
    +1.49];
  - the primary judge's own score, from its re-judge: Qwen +0.97 [+0.54,
    +1.40] and +0.93 [+0.47, +1.39]; GPT-4o +1.20 [+0.60, +1.80] and
    +1.13 [+0.49, +1.77].

  The verdict is GO on all four.
- Run: the re-judge, Cerebrum `results/s20_rejudge/pilot_report/`:
  `hybrid.md`, `keyword.md` and `llm_claude-sonnet-5.5.md` rendered at
  `fae6ce1`; `llm_gpt-5.4.md` at `6e912d1`, committed `968029a`.
  `DEV_STATUS.md`, Subtask 20: "GO on all four scores."
- Rests on: 30 users, the pilot's stored answers.
- Caveat: the workshop paper's judge score is this hybrid too. Each
  trial has recorded its scorer since Subtask 4b (`scorer`:
  `hybrid_keyword_llm`, "the keyword score averaged with the LLM's,
  rounded"); "Notes for the paper" 1 dates the finding to Subtask 20.
  `DEV_STATUS.md`, "Notes for the paper" 1: "The main-track paper states
  the formula or reports the components apart". Every judge score in C1,
  C2 and C3 above is a hybrid. The keyword half matches substrings with
  no word boundary ("go" hits "algorithm"), and its Integration is the
  lower of its Profile and Task. The registered verdict stands on the
  hybrid; the other three are a robustness check. From Subtask 20 the
  judge's own score is the judged metric, the keyword score a judge-free
  metric, and the hybrid a continuity column.

**L.2 The two judges agree on direction, not on level.**
- Numbers (`calibration_v1`, 200 answers, each judge once per answer;
  Profile, Task, Integration). Krippendorff's alpha between the judges:
  0.498 [0.382, 0.597], 0.876 [0.822, 0.911], 0.683 [0.608, 0.741].
  Spearman: 0.685, 0.763, 0.756. Exact agreement: 0.325, 0.620, 0.355.
  Mean offset, second − primary: −0.69 [−0.81, −0.56], −0.36 [−0.43,
  −0.29], −0.34 [−0.46, −0.23]. Where the primary judge gives Profile 4,
  the second gives 2 or 3 on 89 of 101 answers (`DEV_STATUS.md`, Subtask
  20).
- Run: the reliability study, Cerebrum
  `results/judge_reliability_s20/report.md` (committed `968029a`): the
  second judge 2026-11-19, the primary judge 2026-11-20 (2,000 judgments
  each, none failed).
- Rests on: a calibration set, 200 answers drawn from 60 cells of
  earlier runs.
- Caveat: "Notes for the paper" 4 draws the consequence: "So a judged
  claim holds as a paired difference, which both judges can be shown to
  give one direction, and a judged mean's level is its judge's, not
  comparable with another paper's." Direction agreement: C2.4. In the
  grid the second judge scores a fixed 30% of the users (45 of 150;
  `FULL_GRID.md`), so its agreement there rests on that subset. The
  judges' decoding differs (greedy with a best-effort seed; default
  sampling), and neither is claimed to be deterministic.

**L.3 Each judge repeats itself well enough for one judgment per answer;
the primary judge with less room.**
- Numbers (200 answers × 10 repeats per judge; the k rule asks for an
  alpha of at least 0.80 on Profile and Integration). Primary,
  `gpt-5.4`: alpha of one judgment 0.864 [0.827, 0.893] Profile, 0.906
  [0.876, 0.929] Integration, 0.989 [0.980, 0.994] Task; exact
  self-agreement 0.815, 0.841 and 0.965; within one point 0.924, 0.960
  and 1.000. Second, Claude Sonnet 5.5: 0.966 [0.951, 0.977], 0.963
  [0.947, 0.975] and 0.985 [0.977, 0.991]; exact 0.939, 0.939 and 0.955;
  within one point 1.000 on each. By the rule k = 1 for both; the
  primary judge's Profile alpha is 0.907 at k = 3 and 0.935 at k = 5. 46
  of the primary judge's 200 answers have Profile repeats 2 or more
  points apart; the second judge's repeats never differ by more than 1.
  At its first repeat the primary judge gives Profile 3 to 6 of the 200
  answers, the second judge to 66.
- Numbers, earlier test-retests of the primary judge on hybrid scores
  (the share of identical scores, Profile / Task / Integration): in one
  sitting 92.2% / 100% / 94.4% (90 trials, Subtask 9d); a week apart
  75.8% / 98.8% / 83.6% (165 identical answers, Subtask 17, mean
  differences within 0.03); within one pass 5 of 10, 10 of 10 and 6 of
  10 (the scheduler check). The re-judge of 2026-11-20 against the
  pilot's stored hybrid (the same judge: the pilot judged on 2026-11-07
  and 08, the re-judge on 2026-11-20): the same on 893 of 1,080 Profile
  scores (0.83), 1,077 Task (1.00) and 973 Integration (0.90); "no
  overall mean moved by more than 0.05 (a cell's mean can move more)".
  Sampled against greedy judging (Subtask 9d, 720 trials): "Only one
  cell mean moved by more than 0.25: Qwen in-house `kernel_shared`
  profile, 3.27 → 3.00".
- Run: the reliability study (`968029a`); `pilot_v1_9d_greedy` and its
  retest; `pa17`; the scheduler check; the re-judge
  (`s20_rejudge/PROVENANCE.md`).
- Rests on: a calibration set; 90, 165, 10 and 1,080 stored answers.
- Caveat: the k rule was written before the study ran. The judge drifts
  between sittings, so the grid judges every cell in one pass: "So every
  score the paper compares comes from one window." (`FULL_GRID.md`). The
  runs so far were judged as they ran; the pilot's cells over one night.

**L.4 The native conditions: what they are, and their documented
limits.**
- Native is each backend used "the way its documentation says to", fixed
  in `NATIVE_USAGE.md` before the agents' code, with the documentation
  pages it follows. It is the reference for agent-managed memory, not a
  tuned competitor.
- Native Mem0 uses Mem0's own `search()` as installed. Its Chroma
  adapter returns a squared distance as the score and clamps it at 1.0,
  so every row at cosine 0.5 or below ties first, and "the more similar
  a row is above cosine 0.5, the later Mem0 returns it". Once a store
  holds more than k such rows the relevant ones are cut. On v2 (`s15b`):
  recall 5 of 30, 0.17 [0.07, 0.34]; recency and contradiction 0 of 30.
  The replay of `s14b` reproduced 90 of 90 recorded fetches: the recall
  target was the user's nearest row by cosine for 26 of 30 users, Mem0
  ranked it a median 24.5th (1 to 29), and it reached the 10-row fetch
  for 4. So native Mem0's v2 numbers measure Mem0's ranking, and of the
  first check `DEV_STATUS.md` says: "So its deletion and privacy passes
  are not evidence of anything." On v1, with a few rows per user, native
  Mem0 ties with the kernel (C1.2).
- Native Mem0 runs Mem0's default install, without its `[nlp]` extra.
  Whether to use the full install is open (`DEV_STATUS.md`, open
  decision 1); the documents say the extra "would not repair the
  ranking".
- Since Amendment 6 the loci differ in k and budget: kernel and
  replicated run k = 30 under a 300-token budget; native keeps k = 10
  and has no budget. In `s17` a kernel or replicated block held 11.6 to
  11.8 rows in-house and on Mem0 and 17.3 to 17.5 on Graphiti; a native
  Graphiti block held 9.3. The grid adds one cell, native at k = 30 on
  Graphiti, "to measure how much of a native gap is the k native kept".
- Native fetches k rows and then applies its sharing rule, so "a hidden
  row still takes a slot": in 42 of the 90 replayed Mem0 fetches, and on
  Graphiti in 117 of the 180 probes of `s16`.
- Native Graphiti's validity filter (use only the facts Graphiti holds
  true now) is "our reading of this documented intent, not a documented
  call". It was decided after the smoke, and it raised native's recency
  from 11 to 30 of 30 and its contradiction from 13 to 26 of 30 (exact
  McNemar p < 0.001 for both).
- A V4 consumer applies its 0.5 threshold to whatever its backend
  returns as a score. On native Mem0 and native A-MEM that is a
  distance, so it keeps the farther rows. Documented, not changed.
- Native revokes are writer-scoped and native retires nothing, by
  Decisions 4 and 6 (C1.7).
- Native's block is its own, in the backend's order. The session ages of
  v2 were given to native too: "It is a decision of this spec, not a
  property of the backends."
- `native_inhouse` has no vendor convention behind it: "the convention
  is the minimal one a careful developer would write on Chroma".
- Mem0's extraction model is Azure gpt-4o in every locus: in the
  extraction check it was "The only model that kept every fact." Native
  Mem0 with a local extraction model is not run.
- Known issue 13 still says the native conditions differ from the
  kernel's "in what they store, not only in who stores it". Since
  Subtask 9 all three loci store the same rendered text and the kernel's
  Mem0 extracts too. `DEV_STATUS.md` does not reconcile the two, and
  `PILOT.md` cites known issue 13 for leaving native out of the rule.
- Rests on: the specs, a replay of 90 fetches, and 30-user smokes (which
  the grid replaces).

**L.5 Results that hold by construction.**
- The V4 consumer's effect (C3.2).
- Deletion, recency and contradiction against native on v2: native was
  given no forget and no supersession (C1.7).
- The identity results: the replicated resolvers are built with no
  canonicalization rules, and the library trusts its caller. The specs
  state both premises for a reviewer (C3.2, C3.5).
- Floods against replicated: the flooder's pipeline is built without the
  quota (C3.6).
- No leak under replicated: a V3 consumer cannot skip visibility there,
  since "the library the agent links enforces it, with no switch".
- Native's leak needs the pairing the schedule placed (C1.6).
- The tie on in-house at H = 0: "the two run one library on the same
  inputs, so their blocks should be identical" (C1.1).
- `contaminated` is 0 by construction since Amendment 3: probes write
  nothing.
- Privacy at H = 0 passes with the help of where v2 places the private
  fact (C1.8).
- Rests on: the specs' own statements.
- Caveat: none of these makes a result wrong. Each fixes what the paper
  may say the result shows: what a shared rule, a central setting or a
  bound identity buys, not a better algorithm.

**L.6 A forget deletes a fold row whole, so another fact goes with it.**
- Numbers: in `s15b`, in both Mem0 cells that run the library (kernel
  and replicated), the forget deleted by value a row of the revoking
  writer's other fact: user 13's client row, into which Mem0 had folded
  the codename, and user 25's codename row, which held the teammate.
  Each was its user's recall target and its only row, so both users
  failed recall: 28 of 30, 0.93 [0.79, 0.98], "the only recall failures
  outside native Mem0". The forget reading for each of those cells: 42
  rows deleted, 30 by the fact's key and 12 by value, 10 of them other
  agents' echoes and 2 the folds. On A-MEM (`s17a`) the kernel's forget
  of user 2's conference also deleted the user's base task context,
  whose derived text carried the value. On Graphiti the scrub deletes an
  entity a form names with the facts attached to it; they are reported,
  and in the runs "no forget detached a fact".
- Run: `s15b` (AIOS `ef3fdc9`, Cerebrum `64da5f7`); `s17a` (AIOS
  `a145a26`, Cerebrum `f6d2646`).
- Rests on: 30 users, Qwen, H = 0. The grid replaces it.
- Caveat: undecided. `DEV_STATUS.md`, "Not decided here (the user's
  call)": "a forget deletes a Mem0 fold row whole, so the row's own fact
  goes with it", and "Rewriting the row without the forgotten value
  would keep that fact, at the cost of a write the forget makes on
  another agent's behalf." Without the forget the same folds failed
  deletion instead (`s14b`: users 13, 19 and 25). `BENCHMARK_V2.md`
  adds: "A fold in a contradiction's later statement would leave its
  slot with no selectable row". Folds have room to occur: 27 of the 30
  `pilot_v2` users have a same-writer write between an add and its
  revoke.

**L.7 "Complete deletion" covers what the memory system reads, not
everything a store keeps.**
- `DELETION_AND_SUPERSESSION.md`: "Complete deletion here covers what
  the memory system reads: the rows, Mem0's messages and Mem0's
  history." Chroma's own log keeps every deleted row's text (M.3): "No
  API call purges it while a client has the store open."
- Not covered, by the same spec's list: a rewording the matcher does not
  find (Mem0 paraphrasing a value); a write that commits between a
  forget's listing and its tombstone (it stays stored; the read guard
  drops it from every read); rows another identity convention puts in
  another partition (H = 2); retention outside the memory system (logs,
  the model provider); what the consumer already said.
- On A-MEM the runs do not measure it: "No A-MEM run measures the
  store's completeness after a forget (the audit reads content): claim
  weakened."
- In-house cells never exercise the sweep that follows a forget: "Their
  correctness rests on the unit tests, and on the criterion that the
  guard drops nothing." Nor does any run restate a forgotten fact: "v2
  has no restatement; unit tests cover it."
- With the barrier ablated, reads met a forget's rows after its
  tombstone and before its deletes: the guard dropped 12 rows 46 times
  in that phase and in no other (C4.1).
- Rests on: the spec's own list, unit tests and one store inspection.

**L.8 Cells on an extracting backend are paired runs of an extractor
that varies.**
- Numbers: Azure treats the seed as best effort. Under fixed decoding
  Qwen gave byte-identical answers on 5 of 5 users, and GPT-4o's answers
  differed on every user (similarity 0.22 to 0.69). Mem0 cells move by
  about ±2 injected rows with no change of condition. Mem0's extraction
  prompt holds the UTC date, which it writes into facts. Kernel against
  replicated on Mem0: the blocks differ in all 30 probes of `f14c`, and
  some paired outcomes differ in each of the three smokes (C1.1). Mem0
  stored a contradiction without its "only" in 7 of 7 cells that sent it
  the utterance, and in `f14c` 15 of the 45 Mem0 update rows that
  reached a block carried the old value. Graphiti: "Azure GPT-4o at
  temperature 0 with a seed is not deterministic here". A-MEM: two runs
  "differed in every generated attribute set", and in the search from
  its third hit on.
- Rests on: 5-user and 30-user runs, and explorations of one user.
- Caveat: known issue 42: "Read kernel against replicated on Mem0 as
  paired runs of an extractor that varies." It also asks to keep a run's
  Mem0 phases on one UTC date, or to report the date per cell.
  `PILOT.md`: "Mem0 extraction noise: not measured in this pilot."

**L.9 Sample sizes, and what was fixed before it ran.**
- Numbers: a v2 user has one probe of each type, so a cell's rate rests
  on n = 30 in a smoke and n = 5 in a functional check (known issue 37).
  Of `f14c`: "the per-cell rates are not comparisons". A 30 of 30 has
  the interval 1.00 [0.89, 1.00].
- Fixed before running: the documents call two runs pre-registered, the
  re-validation (Subtask 3) and the pilot (Subtask 11). The
  heterogeneity, stress and ablation specs, with their predictions, were
  committed before their code; the decision criteria D1 to D5 and the
  judges' k rule were written before their runs. The v2 smokes have no
  rule: "A smoke, not a verdict: no rule is pre-registered here." The
  Graphiti and A-MEM pilots are "reported, not required".
- Rests on: the documents.

**L.10 The datasets.**
- `users_v1` is skewed (known issue 22): 122 of 150 users prefer Python,
  and four tools make up most of the tools; 104 distinct queries, one
  asked 17 times: "a limit on any claim about attribute coverage". Every
  `pilot_v1` and `pilot_v2` result is on the first 30 users.
- v2's users are built on v1's base users, with four probed slots and
  one private fact per user (`BENCHMARK_V2.md`, "What v2 does not
  show"). Its writers are scripted and call no LLM; its values are
  distinctive proper names, so that exact matching suffices; its private
  facts are written last (C1.8).
- `users_v2` had four revisions. Revision 1's contradictions often did
  not conflict (conference talks 10 of 10, one-on-ones 16 of 19, client
  12 of 26); its smoke was stopped and nothing from it is reported.
  Revision 2's contradiction questions leaned to one statement by their
  wording: in `s14b`, outside native Mem0, the users whose question
  leaned to the earlier statement passed 9 of 50, those leaning to the
  later one 59 of 80, the ties 0 of 20 (known issue 44). Revision 3 asks
  a question of each lean in each slot (75 of each; 15 in `pilot_v2`);
  22 of its statements fell back to the template text. Revision 4 adds
  the decision items and changes nothing else.
- With both values in the block the wording still decides: in `s15b`
  native in-house passed 13 of 15 later-leaning and 5 of 15
  earlier-leaning questions. And: "The leaned-to row also came first in
  29 of the 30 blocks, so the lean is not told from the rank".
- Wording oddities remain (known issue 41). Among them, 18 of the 31
  home_city earlier statements gained "currently", a time word neither
  lean rule sees.
- Before Amendment 3 each probe's answer was stored and later probes
  read it. In 19 of the first smoke's 900 judge-free probes a value
  reached the block only that way, and the stored answers pushed the
  base rows out of the in-house integration blocks (`s14b`: integration
  1.77 [1.48, 2.06] kernel and 1.80 [1.50, 2.10] replicated, against
  2.87 in `s15b`). The two smokes are not paired: "no difference is
  attributed to one change".
- Rests on: dataset checks and 30-user smokes.

**L.11 The decision items: accuracy without memory is below chance, and
the pilot's answer key is uneven.**
- Numbers, without memory (Qwen, kernel locus, in-house, `no_memory`,
  150 users, 300 items, `METRICS.md`, "The items without memory"):
  accuracy 54 of 300, 0.18 [0.14, 0.23], against a chance level of 0.25.
  The foreign option is picked most: 0.35 [0.28, 0.43] on `d1` and 0.39
  [0.32, 0.47] on `d2`. Letters picked: A 66, B 97, C 72, D 65 (p =
  0.03; B 0.32 [0.27, 0.38]). Correct letters: A 85, B 66, C 80, D 69 (p
  = 0.36); on `d2` 48, 29, 46 and 27 (p = 0.021). No item was left
  without a letter or given several.
- Numbers, readings added on 2026-11-20 (`FULL_GRID.md`, "The decision
  items"; `METRICS.md`; Amendment 10, "The letters' size"; "checks added
  in reading, not stated before"): Qwen's lean to B costs under 0.01 of
  accuracy (letters picked at its shares would score 0.247; 0.244 to
  0.250 with the picks resampled). One letter throughout scores 0.22 (B)
  to 0.28 (A) on the 150 users, 0.18 to 0.32 on `d2`, and 0.13 to 0.37
  on `pilot_v2`, whose correct letters are A 22, B 8, C 22, D 8 (p =
  0.0045; known issue 56). The correct option is alone the shortest
  statement on 111 of 300 items; the shortest statement throughout would
  score 0.38 (0.43 on `d2`); Qwen picks it on 58 of 300. "The kinds are
  tied to slots by construction": a rule that knew each slot's role
  would score 0.47, and 0.97 knowing the item. Evened out over the
  correct letters, Qwen's `no_memory` accuracy is 0.184 against 0.180.
- Run: `dn150` (kernel AIOS `20f2447`, harness Cerebrum `692319c`),
  2026-11-19; it was added after D2 failed, "its reading written before
  it ran".
- Rests on: 150 users, one model. The letter readings' script is
  archived with the run's records (Amendment 10).
- Caveat: the user's rule (2026-11-20): "in the grid a decision accuracy
  is reported with its model's letter distribution beside it"
  (`FULL_GRID.md`). How it is met is proposed there, not fixed (open
  decision 8). "Notes for the paper" 5: reading an accuracy against the
  model's accuracy without memory, and comparing accuracies within a
  model, paired, "are proposed there". Two earlier sentences were
  narrowed: "paired comparisons are unaffected" holds only between cells
  whose blocks are the same, and the p of the letters picked tests a
  lean in a `no_memory` cell only. A model's accuracy without memory is
  "a reference, not a lower bound": a cell can fall below it (native
  Mem0 under `wrong_user`: 1 of 10). No other model's lean is measured.
  `METRICS.md`, "Known limits": decision accuracy is not comparable
  between models, or with 0.25, without each model's letters and its
  accuracy without memory.

**L.12 The decision items' no-memory criterion (D2) was not met, and is
recorded as a deviation.**
- Numbers: D2 (`no_memory` accuracy in [0.10, 0.45]): 0 of 30 on
  in-house, 0 of 60 with both backends. "the six no_memory cells (three
  loci, two backends) gave the same ten answers, DDCACBBDAB (no memory,
  greedy decoding), as did users 0 to 4 of the 150-user no-memory check,
  so they are one sample of ten items; 0 of 10 has probability 0.056
  under uniform guessing." (`decision_functional_s20/PROVENANCE.md`).
- Run: `d20a`, `d20m`; the check over every user, `dn150` (L.11).
- Rests on: 10 items. The grid replaces the functional check.
- Caveat: the check over all 150 users was added after D2 failed, with
  its reading written before it ran; its accuracy is 0.18 [0.14, 0.23]
  (L.11). D1, D3, D4 and D5 were met on both backends (C1.10). "Qwen
  answered alike wherever the prompt was the same": over the 26 cells,
  the 236 pairs of answers to one item with the same block text name the
  same letter.

**L.13 The workshop kernel's retrieval settings never acted: no score,
no ranking, a threshold that filtered nothing, a cap and a budget that
never bound.**
- Numbers (the re-validation, 900 trials on the workshop's pipeline):
  "`scores_present` was false in all 900 trials, as expected.
  `relevance_threshold` filtered nothing." "The cap and the token budget
  bound in 0 of 450 `kernel_shared` trials. `after_cap` and
  `after_budget` were 2 in all 450", about 150 to 175 estimated tokens
  at the median; every `kernel_shared` trial injected one profile and
  one task context (`REVALIDATION.md`, "Truncation and scores").
- Why (`RETRIEVAL_PATH.md`, "Scores"): "Until Subtask 5,
  `Mem0Provider.retrieve_memory` used `get_all`, which returns no score
  and does not rank: `scores_present` was `false` in every trial,
  `relevance_threshold` did nothing, and the rows were the first `top_k`
  in storage order whatever the query." Also "`get_all` silently
  returned at most 20 rows", and `max_injected_memories` "only set the
  fetch size, so the merged list could exceed it" ("Behavior changes").
- How it came about (`PROVIDER_CONTRACT.md`, "Why the kernel used
  `get_all` until Subtask 5"): on 2026-06-28 commit `7793943` set Mem0's
  search threshold to 0.0 after retrieval counts fell as the store grew;
  the same day `3ceea6c` switched retrieval to `get_all` and set
  `infer=False`, "because with `infer=True` Mem0's fact extraction
  deduplicated writes and stored nothing while `add()` reported
  success". "Neither commit tested `threshold=0.0` on its own".
- What a threshold would have done: in the 9d re-baseline the match
  scores of relevant memories were 0.32 to 0.60 on the kernel path;
  in-house, 30 of 30 profile and 29 of 30 task-context scores were below
  0.5 (`HETEROGENEITY.md`, V4). "A V4 consumer on in-house at threshold
  0.5 injects nothing" (`h10`).
- Run: the re-validation (AIOS `672665e` and `19c3ea9`, Cerebrum
  `76dc9f1` and `99933e4`); the history is the documents' reading of the
  commits.
- Rests on: 150 generated users × 3 models, and code history.
- Caveat: the documents disagree on the threshold of that period.
  `HETEROGENEITY.md`: "`config.yaml.example` shipped
  `relevance_threshold: 0.5` from 2026-04-12 to 2026-11-02";
  `SHARED_MEMORY_SYSTEM.md` gives "default 0.3" and describes
  `infer=False` and a provider-side sharing filter, which later subtasks
  removed. Since Subtask 5 the default is 0.0, "rank, drop nothing"
  (`RETRIEVAL_PATH.md`; known issue 1). The workshop recorded no config
  (known issue 2), so which value it ran is not known; under `get_all`
  none acted. `REVALIDATION.md`: the workshop runs "are not cited as
  evidence again, because they span several code states and recorded no
  commit, config or injected sets." The re-validation reproduced the
  workshop's `kernel_shared` on that pipeline (8 of 9 cells, largest
  shift 0.20), in trials that each injected both of their user's two
  memories.

**L.14 Criteria not met, predictions not seen, and deviations
recorded.**
- Re-validation (pre-registered): `kernel_shared` reproduces, but its
  Qwen Task cell failed: +0.200 (Welch p 0.0005, TOST p 0.1895). "No
  listed behavior change explains it"; "The workshop recorded no Ollama
  or model version, so this cannot be confirmed." Under judge prompt v2,
  Spearman's rho against v1 is below the expected 0.8 in 7 of 8
  `kernel_shared` cells (0.571 to 0.870).
- `h10` (5 users): the V5 design check "PASS under kernel in-house;
  FINDING in the other five cells"; the V3 consumer had "no leak
  opportunity" in that schedule (known issue 34, fixed by the pilot's
  balanced schedule).
- The pilot: "V5 did not show up in any gap"; "Mem0 extraction noise:
  not measured in this pilot."
- `f15a`: "Eight of the nine criteria hold"; "The budget criterion
  fails": 300 tokens bound in no probe of a kernel or replicated
  in-house cell, whose largest block was 291 estimated tokens. Resolved
  on review (open decision 4): no budget criterion in the functional
  check or the smoke; its binding is reported, not required.
- Amendment 5 (during the Graphiti functional check): 3 of 720 Graphiti
  writes stored no fact and failed their trials; the rule was changed so
  that such a write is a lost memory and the trial is scored. Amendment
  9 did the same for a Mem0 write that stored nothing when Mem0 logged
  no failure for it (open decision 7).
- `f18b`: the load mode's predicted growth of the barrier wait "did not
  hold"; Mem0 stored nothing for one vague sentence when its writer had
  written little (7 of 16 times at N = 12, 1 of 6 under concurrency;
  "Deviation", known issue 53); five users could not test the flat-in-N
  prediction, and in its concurrency cells "No timing miss or stale read
  was possible".
- `f19b`: 13 of 14 rules held. The V2 identity rule "did not hold as
  written" (one block had 1 of 6 profile facts, carried by the task
  agent's row): "Recorded as a deviation; the rule is left as
  registered." Without the barrier no stale read or timing miss appeared
  ("the spec predicted a few"); without supersession recency passed 0 of
  5 (the spec: 1 of 5); at F = 10 the profile facts did not fall (0.00).
- `s19`: every primary interval excludes 0 in the predicted direction.
  Secondary departures: without the barrier the kernel missed more than
  replicated did, and "why was not looked into"; with claimed identities
  `memories_missing` rose +0.67, "below the spec's 'about 1'".
- `d20a`, `d20m`: D2 not met (L.12).
- Subtask 7: `kernel_overhead_ms` includes the scheduler's wait, which
  "departs from the spec, which named only the four stages".
- Rests on: the documents' own records of each run.

**L.15 The judge-free probes match exactly, so a guess can fail a probe
and an answer that names both values fails recency.**
- `METRICS.md`: recall passes when "every expected value is in the
  answer"; recency and contradiction when "the expected value is in the
  answer and the stale one is not"; "exact matching: a paraphrased value
  fails; an answer that names both values fails recency and
  contradiction". "Known limits": "Exact matching misses paraphrases;
  the semantic score on probes is a reading, never a pass."
- Guesses: the full kernel failed one echo user's deletion probe with no
  carrier in its block, because Qwen named the revoked chat app among
  popular ones, "as in the functional check and in every s18 kernel cell
  (29 of 30)" (`s19`); native Mem0 in `f14c` likewise ("Qwen listed
  Mattermost among popular chat apps"). On the decision items native
  Mem0's right answers were guesses (C1.10).
- Answers that name both: in `s15b` every Mem0 recency failure of the
  kernel and replicated cells named the new value, 14 of 15 the old one
  as past (C1.7); in `f15a`, "Every failing recency answer named both
  values (14 of 14, the stale one as past in 12)". The lenient pass, the
  new value named, is given beside the strict one in the smokes' tables.
- Rests on: the scorer's definition and the runs' readings.
- Caveat: the probes measure whether a value reached the answer, not
  why; `options_in_block` and the block readings say why. A probe checks
  only its own block and answer: a pass can hide the value elsewhere in
  the trial (known issue 43).

**L.16 The judged score measures how personalized an answer is, not what
the memory system served.**
- `METRICS.md`: "What the judge sees. The profile, the task context, the
  query and the answer. Not the memory block, not the condition, not the
  locus." "Known limits": the judge "scores how personalized an answer
  is, not whether the memory system served it."
- The keyword score matches substrings with no word boundary ("go" hits
  "algorithm"), and its Integration is the lower of its Profile and
  Task. Task is not in the k rule: its scores are nearly always 1 to 2
  or 4 to 5 (22 of 2,400 greedy v1 scores are 3).
- A v2 trial is judged on its integration probe only, against the user's
  final profile and task context. `BENCHMARK_V2.md`: v2's integration
  score "is not comparable with pilot_v1's integration".
- Rests on: the definitions.
- Caveat: so a judged locus difference says that the consumer's answer
  used more of the user's facts. The documents tie the pilot's gap to
  what reached the block through the judge-free measures of the same
  trials (C1.6, C3.2). From Subtask 20 `profile_facts_in_answer` is
  recorded (judge-free, its own matcher, no paraphrases).

**L.17 Documents that disagree, or describe an earlier state.**
- Mem0's extraction temperature. `MODELS.md` (decided in Subtask 9):
  Mem0's internal LLM "keeps its own setting", "temperature 0.1".
  `DEV_STATUS.md`, known issue 26: "Fixed in Subtask 10: Mem0's
  extraction runs at temperature 0.0 and seed 20261105 in both loci."
  `PILOT.md`: Mem0 extraction "at temperature 0.0, seed 20261105".
  `MODELS.md` also lists neither the second judge nor the backend LLM of
  Graphiti and A-MEM, though it says "Changing an entry here needs a new
  baseline."
- What native stores. Known issue 13: the native conditions differ "in
  what they store, not only in who stores it: natural-language
  renderings (and, for Mem0, gpt-4o-extracted facts) rather than the
  writers' JSON". `DEV_STATUS.md`, Subtask 9: "Kernel, replicated and
  native writers all store the same plain-language text", and the
  kernel's Mem0 extracts too (`infer: true`). `PILOT.md` cites known
  issue 13 for leaving native out of its rule.
- The shared-memory reference. `SHARED_MEMORY_SYSTEM.md` describes
  `infer=False`, the provider's `_apply_sharing_filter()` and a 0.3
  threshold default. `RETRIEVAL_PATH.md`: visibility runs only in
  `apply_sharing_filter` of the library, "the only place it runs;
  providers never filter", and the default threshold is 0.0.
- Names: `REVALIDATION.md` keeps `mem0_default` for the Subtask 3 run;
  it is `kernel_private` since Subtask 4, "the kernel pipeline with
  sharing off, not Mem0's own behavior".
- Rests on: the documents as committed at AIOS `980cbc5`. These are the
  disagreements met while writing this file; no systematic search for
  others was made.

**L.18 Known issues that qualify a reported number, not named above.**
- Known issue 36: nothing resets the memory stores between runs;
  isolation rests on run ids in user ids, and a re-run under the same id
  sees the earlier attempt's rows and tombstones (its deletion probe
  then "passes without testing the forget"). The re-runs the documents
  name gave themselves new ids (Subtask 11's, `f15b2`, `s15b`, `s17b`).
- Known issue 48: Qwen's speed on this laptop "moves more than twofold"
  (48 to 131 ms per completion token in the `s17` run), so a cell's time
  per user is not comparable across runs (K.4, K.6).
- Known issue 52: embedding scores of the same row and query differ by
  up to 1.1e-6 between runs (254 of 5,646 rows); "no in-house block
  compared in Subtask 18 differed for it".
- Known issue 23: with Mem0 extraction one write can store several facts
  but returns only the first id, so an update by that id replaces one
  fact and leaves the others ("the accumulating benchmark needs an
  update rule for extracted facts"). In `f14c`, of the Mem0 update rows
  that reached a block, 15 of 45 carried the old value (L.8).
- Known issues 3 and 39: `config.yaml` (10 / 2000) and
  `config.yaml.example` (5 / 1500) differ on the cap and the budget; v2
  runs set 300 tokens through the driver, whose pre-flight refuses
  anything else; v1 runs keep 2000.
- Known issue 19: the kernel's conversation write runs on a background
  thread after the reply, the replicated assistant's synchronously;
  "neither can affect a score here".
- Known issue 31: the collection-name sanitizer maps dropped characters
  to `_`, so ids differing only there share a collection; the user
  filter keeps their rows apart.
- Known issue 55: `rejudge.py` leaves a v2 probe's earlier judge scores
  when the primary judge fails after its retries; "no judgment failed in
  Subtask 20's re-judge (0 of 1,350)".

**L.19 What the reviews found: bugs on reported paths, claims narrowed,
one finding refuted.**
- Subtask 15's verification pass, over the review's 78 findings: 70
  fixed as made and 6 partly; "2 fixes were wrong, and the fix commits
  added 2 false sentences and made a third false." "No recorded result
  changes."
- Subtask 16's review: native Graphiti's `search()` wrote its
  `num_results` into the shared recipe Graphiti's ingestion reads, so "a
  V4 consumer's k 5 stayed for the next users' writes" (the functional
  check's native H = 2 cell ran with it); "The selector never deduped
  the own fetch" (a Graphiti control: "12 extra rows in 10 of 30
  probes"; "no Mem0 or in-house block of the Subtask 15 runs held two
  rows with one text"); the Graphiti scrub deleted attached facts
  unreported. The pilot design's Graphiti run, started before the fixes,
  was stopped in its first cell, "so it runs on the fixed code".
- Subtask 17's review, 11 findings: the kernel's rows carried A-MEM's
  derived text, "a path past the visibility rule" (M.2); two claims
  weakened (A-MEM's caught LLM failures; no A-MEM run measures
  completeness after a forget, L.7). "No number the functional check
  reports changes".
- The write-up reviews of Subtasks 18 and 19: "8 errors and 16
  imprecisions", and "6 errors and 6 imprecisions", corrected.
- Subtask 20's review: 9 findings, 8 confirmed and fixed, one (the
  primary judge's `response_format`) refuted. Among the fixed: "the
  inter-judge offset's sign: `report()` paired the judges by name, so
  the offset was primary - second". Its closing check found 6 errors,
  among them a "floor" the new text calls no bound, and "a note for the
  paper that settled what is proposed".
- Mutation runs: the stress measures and report (Subtask 18) and the
  ablation report (Subtask 19) were the weakest areas, 40 of 50 and 43
  of 50 mutants surviving their area's tests, 36 of each changing a
  reported number; both are now pinned by tests that regenerate the
  reports from the runs' records.
- Rests on: the review records in `DEV_STATUS.md`.
- Caveat: rule 6 limits the passes: "at most two review passes per
  subtask", and "where a claim outruns the tests, weaken the claim
  rather than add tests, unless the untested rule affects a reported
  number." So a claim in the documents is as strong as its tests, by
  rule.

## Cost

Costs are the harness's records priced at Cerebrum `prices.yaml`
(`DEV_STATUS.md`, Subtask 7: gpt-4o at 2.50 / 10.00 USD per million
input / output tokens "from price aggregators, since Microsoft's page
was not checked directly"; local models 0). Judge tokens are an
evaluation cost, kept out of the system's cost (`METRICS.md`,
"Recording").

**K.1 Mem0's extraction is the memory system's main cost, and since
Subtask 9 every Mem0 locus pays it.**
- Numbers, the Subtask 7 check (10 GPT-4o trials per condition, means
  per trial): total tokens `kernel_shared` 2,273, `native_mem0` 26,586;
  estimated USD 0.0090 (backend share 0%) and 0.0735 (90%);
  `tokens_per_quality` 487 and 5,617; scores 4.5 / 5.0 / 4.5 and 4.6 /
  5.0 / 4.6. "At similar scores on 10 trials, native Mem0 spends about
  11× the tokens and 8× the money per trial; Mem0's extraction prompt
  (about 7,900 prompt tokens per call) is 90% of the cost."
- Numbers, since Subtask 9 (`p9d`, `cells.csv`, USD per trial): GPT-4o
  on Mem0, kernel 0.0726, replicated 0.0726, native 0.0718; GPT-4o
  in-house, 0.0075, 0.0075 and 0.0069; local models 0 in API calls.
  `DEV_STATUS.md`: "Mem0 cells: 0.062-0.073 USD", "In-house GPT-4o:
  about 0.007 USD". The pilot: "Mem0 extraction is 0.05-0.07 USD per
  Mem0 trial in every locus".
- Run: `cc7` (AIOS `4d89763-dirty`, Cerebrum `52330ff-dirty`); `p9d`
  (AIOS `7cc3774`, Cerebrum `14b3c67`, re-judge `be72d70`); `pv1`.
- Rests on: 10 trials (Subtask 7); 30 users per cell (v1).
- Caveat: the 11× is not a kernel − native cost of the system as later
  run. In Subtask 7 the kernel's Mem0 stored verbatim (`infer=False`, 0
  backend calls), and its run was "run to check the cost
  instrumentation, not to compare conditions"
  (`cost_check/PROVENANCE.md`). From Subtask 9 the kernel's Mem0
  extracts too (`memory.mem0.infer: true`), and `p9d`'s per-trial costs
  above are those of all three Mem0 loci. So no document states a cost
  advantage for the kernel on Mem0 after Subtask 9.

**K.2 The pilot's recorded cost was about 16.4 USD for Qwen and 20.1 USD
for GPT-4o; most of the Qwen cost is Mem0's extraction.**
- Numbers: "Harness-recorded cost, excluding the judge: about 16.4 USD
  for Qwen and 20.1 USD for GPT-4o." "Mem0 extraction is 0.05-0.07 USD
  per Mem0 trial in every locus, and most of the Qwen cost." "In-house
  Qwen cells cost 0." (`PILOT.md`, "Cost").
- Run: `pv1`.
- Caveat: the agent cells' backend cost at H > 0 is a lower bound (K.8).
  The figures exclude the judge.

**K.3 Per user on benchmark v2, Graphiti costs the most and A-MEM the
least of the extracting backends.**
- Numbers: Graphiti makes "about 4 backend calls a v2 write and 6 a v1
  write, against Mem0's 1"; per v2 user $0.41 to 0.43 against Mem0's
  $0.36 (`s16`), and in `s17` Graphiti 72.9 to 73.8 calls and $0.42 a
  user, Mem0 17.8 calls and $0.36. A-MEM (`s17a`): 34.6 calls a user,
  1.94 a write, about 23,200 prompt tokens, $0.10 a user. On v1 (the
  pilots' designs): A-MEM 5 calls a user, $0.012 to $0.014; Graphiti
  15.7 to 19.3 calls, $0.085 to $0.10. In-house has no backend LLM.
- Time per v2 user (`s16`): Graphiti 182 to 191 s, Mem0 95 to 102 s,
  in-house 73 to 77 s; Graphiti's `add_episode` 6.3 to 6.5 s a write
  (median). A-MEM (`s17a`): 118 to 123 s a user at 52 to 54 ms per Qwen
  completion token; a kernel write a median 3.33 s.
- Run: `s16` (AIOS `d9ca01f`, Cerebrum `c3f5ade`), `s17` (AIOS
  `612c989`, Cerebrum `2b9a776`), `s17a`, `pa17` (AIOS `a145a26`,
  Cerebrum `f6d2646`), `pg16e`.
- Rests on: 30 users per cell. The grid replaces it.
- Caveat: wall times are not comparable across runs (known issue 48:
  Qwen's speed moved from 48 to 131 ms per completion token within one
  run); the documents give tokens and calls for that reason. Every
  recorded backend call matches the logs one for one in these runs, but
  for the pilot design's H = 2 agent cells (K.8).

**K.4 The k = 30 block costs little beyond its tokens.**
- Numbers: "k 30 itself costs about 0.03 s of injection and 40 prompt
  tokens a probe (116 to 118 on Graphiti), and no backend cost." The
  budget-off ablation adds 73 block tokens a probe and legacy formatting
  3 (`f19b`).
- Run: `s17`; `f19b`.
- Rests on: 30 users (`s17`); 5 users (`f19b`).
- Caveat: "Time per user did not measure k": the kernel cells took 99
  and 133 s a user against 77 and 95 because Qwen generated more slowly
  that afternoon.

**K.5 The kernel's memory stages take under 1% of a chat's latency; its
old scheduler wait was 14%, and Subtask 18 removed it.**
- Numbers: Subtask 7 (10 GPT-4o trials): latency 6,944 ms = 40 (memory
  stages) + 975 (scheduler wait) + 5,925 (`llm_ms`) for `kernel_shared`;
  "The kernel's memory stages are under 1% of latency; the scheduler's
  wait is most of the kernel's overhead." The scheduler check (10 users,
  in-house, Qwen, before and after Subtask 18's change):
  `schedule_wait_ms` median 845 ms (409 to 925) before, 1.0 ms (0.7 to
  3.4) after; the kernel's overhead median 906 ms before, 77 ms after;
  "Blocks, writes and answers identical for all 10 users."
- Run: `cc7`; the scheduler check (AIOS `7053e0a` and `c389539`,
  Cerebrum `d876f0f`).
- Rests on: 10 trials and 10 users. Grid: not stated.
- Caveat: every result before Subtask 18 ran with the 1 s wait (known
  issue 15: sequential requests "waited about the full second (14% of
  `kernel_shared` latency on GPT-4o)"). No interval is stated for these
  medians.

**K.6 Under concurrency and load the barrier's wait stays small; the
latency that grows is the model's.**
- Numbers: under concurrency the kernel's probes waited a median 114 ms,
  at most 248 (`s18`, in-house, 30 users); a median 99 ms in-house and
  3.7 s on Mem0, "where a write is a GPT-4o call; no timeout" (`f18b`, 5
  users). Load (`f18b`, kernel only, 16 users, M at a time): in-house
  throughput 0.75, 0.96 and 1.00 users a minute at M = 1, 4 and 16 (Mem0
  0.66, 0.69 and 0.61); probe latency grew (in-house median 8.9, 34 and
  80 s), and "the barrier wait did not (p95 under 2 ms, no timeout)";
  `llm_ms` median 8.8, 13 and 47 s; a Mem0 write took a median 1.3, 3.2
  and 24 s.
- Run: `s18`, `f18b` (both AIOS `d451801`, Cerebrum `8ef6d6f`).
- Rests on: 30 users (concurrency, in-house); 5 and 16 users (Mem0,
  load). The grid replaces them: the stress dimensions' "scored runs
  wait for the grid".
- Caveat: "the spec's prediction that a probe's barrier wait would grow
  with them did not hold: in the load mode a user's probes start after
  its own writes have completed". Known issue 54: under load "a probe is
  held by the LLM queue, not the barrier". The load mode runs the kernel
  only, so it compares no locus.

**K.7 The evaluation's own spend in Subtask 20 was about 50 USD.**
- Numbers: the second judge about $12.71 (checks and measurement $0.19,
  calibration $7.57, re-judge $4.95; the Batch API's $1 / $5 per million
  tokens); the primary judge about $19.62 (measurement $0.28,
  calibration $11.65, re-judge $7.69; 3,400 calls, none failed; "priced
  at OpenAI's list $2.50 / $15 per million tokens, Azure's own price not
  read"); the decision check's Mem0 cells about $18.01 of gpt-4o (Mem0's
  extraction: 6,982,522 tokens in, 55,668 out, 888 calls). "In all about
  $50.34." Per judgment: the primary judge 1,037 tokens in and 215 out,
  the second 1,711 and 415.
- Proposed, not run: a GPT-4o `no_memory` decision cell over 150 users,
  "about $1.30 at Qwen's token counts" (open decision 8).
- Run: reliability, re-judge, `d20m`.
- Caveat: the budgets: the user set $200 for the project and $30 for
  this subtask on the second judge; the Azure spend had no budget set,
  each run's cost stated before it ran (`DEV_STATUS.md`, Subtask 20,
  "Spend").

**K.8 Costs the records undercount or price from a secondary source.**
- A V2 agent's backend calls were not counted in v1 (fixed at Cerebrum
  `a836d69`): the Graphiti pilot design's H = 2 agent cells recorded 338
  of 393 (replicated) and 394 of 439 (native) logged calls, "exactly
  their 12 V2 trials", reported as lower bounds; in the pilot's H = 1
  and H = 2 Mem0 agent cells "their V2 trials record 1.5 to 1.75 backend
  calls against 3 for the others". "No report gave agent-locus backend
  cost at H > 0. The kernel reads usage under canonical ids and is
  unaffected."
- Known issue 16: the harness's user-less diagnostic search is "not
  counted in the trial"; it is harness instrumentation.
- `METRICS.md`: on revision 4 a v2 trial's cost fields include its two
  decision turns, "so its cost is not comparable with a revision-3
  trial's"; v2 records no `writer_tokens`.
- Prices: gpt-4o from aggregators (Microsoft's page not checked);
  GPT-5.4 at OpenAI's list (Azure's price not read). Embeddings run
  locally and "cost nothing in money, only time".
- Rests on: the documents' reconciliation of records with logs.

## What each finding rests on

From each entry's "Rests on" line. The grid replaces the 5-user and
30-user benchmark v2, stress and ablation numbers with 150-user cells;
it names no cell for a benchmark v1 result (`FULL_GRID.md`).

| Basis | Entries | What the grid does |
|---|---|---|
| 150 users per cell | L.13 (the re-validation: generated users, three models, pre-registered); L.11 (the no-memory decision check: Qwen) | nothing for L.13; per-model `no_memory` cells are proposed (open decision 8) |
| 30 users, pre-registered (the pilot, `pv1`) | C1.4, C1.6, C2.1, C3.1, C3.2 (3 users per variant and role), C3.3 (the pilot's part), L.1 | not stated |
| 30 users, benchmark v1, no rule | C1.2, C1.3, C1.5, C1.11 (v1), C2.2, C2.3, K.1 (`p9d`), K.2 | not stated |
| 30 users, benchmark v2 smokes (Qwen, H = 0) | C1.1 (the smoke counts), C1.7, C1.8 (H = 0), C1.9, C2.5, C2.6, L.6, L.8, L.10, K.3, K.4 (`s17`) | replaces them; adds native k = 30 on Graphiti |
| 30 users, stress and ablation smokes (in-house, Qwen, judge-free) | C3.4, C3.6, C4.1, C4.2, C4.3, C4.4 (in-house), K.6 (concurrency) | the stress cells' "scored runs wait for the grid"; one confirmatory ablation each on Graphiti and A-MEM, its switch open; a 150-user repeat of the in-house ablation cells is not stated |
| 5 users (functional checks) | C1.8 (H = 2 and the control), C1.10, C1.11 (v2 control), C3.3 (the fault), C3.5, C3.7, C3.8, C4.2 (the match with replicated), C4.4 (Mem0), C4.5, C4.6, C4.7, C4.8, L.12, K.4 (`f19b`), K.6 and C3.9 (Mem0; load 16 users) | replaces them; C4.8's rows are scored there |
| 10 trials or 10 users | K.1 (Subtask 7), K.5 | not stated |
| a calibration set (200 answers) | L.2, L.3 | each judge once per answer; the second judge on 45 of 150 users |
| stored answers judged again | C2.4, L.1 (the four scores), L.3 | the grid judges in one window |
| specs, code readings, unit tests | C1.1 (the equivalence test), L.4, L.5, L.7, L.9, L.15, L.16, L.17, M.3, M.4 | none |
| incident, run and review records | C2.7, C4.9, M.1, M.2, L.14, L.18, L.19, K.7, K.8 | none |

Open: one model carries every benchmark v2, stress, ablation and
decision result (C2.7); only the grid can add a second.

## Open decisions

What the user must decide before these findings can be written up. Each
names its options as the documents give them, or as this file sees them
where the documents give none, and what it bears on. None is decided
here.

1. **The claims.** The claims document `ABLATION.md` cites is in neither
   repository, and only C4 is named in the documents. Options: commit
   the four claims (their wording, and which evidence each needs); or
   accept this file's readings. Bears on the grouping of every entry,
   and on whether C2 and C3 need a stated rule (none exists: C2 is never
   stated as a claim, and C3 has a registered rule for H only).
2. **How the pilot's judged scores are shown.** The rule was registered
   on the hybrid, and "The pilot's verdict stands as registered"; from
   Subtask 20 the LLM score is the judged metric and the hybrid "a
   continuity column only" (`METRICS.md`). "Notes for the paper" 1: the
   paper "states the formula or reports the components apart". Options:
   lead with the registered hybrid and show the keyword and both LLM
   scores as the robustness check; or lead with the primary judge's LLM
   score and keep the hybrid as the registered verdict beside it; and in
   either case, the formula, the components, or both. Bears on L.1,
   C1.4, C1.5, C3.1, and every v1 judged number.
3. **The v2 smokes' judged means.** Every integration mean in C1.9 is a
   hybrid of one judgment; of the v2 smokes only `s17a` was judged again
   (`s20_rejudge`), and there the two judges gave kernel − replicated
   opposite signs. Options: cite them as hybrids with that label; judge
   the other smokes' stored answers again (no model run, as
   `s20_rejudge` did); or cite no v2 judged mean before the grid. Bears
   on C1.9, C2.4.
4. **Native's place in the locus claim.** Kernel − native was never part
   of a rule; native differs by design in what it stores and retrieves
   (L.4), several of its results hold by construction (L.5), and known
   issue 13 is stale (L.17). Options: report kernel − native as the
   secondary contrast, as `PILOT.md` does; or report native as the
   deployment reference only, with its judge-free failures and no locus
   claim. Bears on C1.5, C1.7, C1.10, C2.2, C2.3, C2.6.
5. **The forget's fold rows** (`DEV_STATUS.md`, "Not decided here (the
   user's call)"). Options: (a) delete the row whole, as now, so its own
   fact goes with it (users 13 and 25 lost their recall targets); (b)
   rewrite it without the forgotten value, "at the cost of a write the
   forget makes on another agent's behalf". Bears on L.6, C2.5 and the
   Mem0 cells' deletion and recall.
6. **Native Mem0's install** (open decision 1). Options: Mem0's default
   install, as run; or with its `[nlp]` extra, which "would not repair
   the ranking" (`DEV_STATUS.md`). Decide before the final runs. Bears
   on L.4, C1.7, C1.10, C2.6.
7. **Each model's `no_memory` decision cell** (open decision 8).
   Options: (a) one `no_memory` cell per model over the grid's users;
   (b) no new cell, each cell's own letters and the evened-out accuracy;
   (c) both (the document recommends (c)). Open too: whether Amendment
   10's readings of the no-memory check apply to each model's cell.
   Bears on C1.10, L.11, L.12.
8. **The grid's cell list** (`FULL_GRID.md`, open): loci, backends,
   models, H, the stress levels, the users per cell, the run order, the
   cost, and the switch of each confirmatory ablation; and whether any
   benchmark v1 cell is run again at 150 users. Bears on every "the grid
   replaces it" mark, on C2 (no v2 result has a second model) and on
   every v1 result ("Grid: not stated").
9. **Strict or lenient recency and contradiction.** `METRICS.md` defines
   the strict pass; the smokes print the lenient one beside it. Kernel
   and replicated Mem0 pass recency 22 and 23 of 30 strictly and 30 of
   30 leniently (`s15b`). Options: headline the strict rate with the
   lenient beside it; headline the lenient; or both, with the reason.
   Bears on C1.7, C2.5, L.15.
10. **The motivation's list.** "Notes for the paper" 2 lists eight
    incidents; M.2 has others, and M.3's retention findings are
    separate. The documents do not test "only a layer that sees every
    write notices": the harness's checks, which run in every locus,
    caught these. Options: which incidents enter the paper, and whether
    that sentence is kept, weakened, or tested. Bears on M.1 to M.3.
11. **The decision items before the grid.** The functional check has 10
    items a cell on users whose answer key is uneven (known issue 56).
    Options: report its accuracies as a check of the probe only; or
    report decision accuracies from the grid only. Bears on C1.10, C3.5
    and C4.6 (their decision parts).
12. **Documents to correct before citing.** `MODELS.md` (Mem0's
    extraction temperature; no second judge; no Graphiti or A-MEM
    backend LLM), known issue 13, and `SHARED_MEMORY_SYSTEM.md` (L.17).
    Options: correct them; or cite `DEV_STATUS.md` and the run records
    in their place. Bears on the paper's methods section and L.17.
13. **Cost claims.** The 11× of Subtask 7 compares verbatim storage with
    extraction on 10 trials of a check "not to compare conditions", and
    since Subtask 9 every Mem0 locus extracts (K.1). Prices come from
    aggregators and OpenAI's list, not Azure's (K.8). Options: drop the
    11×; report it with its caveat; or take the cost claim from the
    grid's records; and whether to read Azure's prices first. Bears on
    K.1, K.7, K.8.
