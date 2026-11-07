# Pilot: locus × heterogeneity on pilot_v1 (NeurIPS Subtask 11)

Pre-registered. This file, the schedule and the driver were committed
and tagged `pilot-v1-code` in both repos before the first scored trial.
Everything above "Result" is fixed; the "Result" section is added after
the runs and does not change the rule.

The pilot decides, from data, whether the thesis holds well enough to
justify Phase D. The thesis: when the agents that share memory are
built heterogeneously, memory logic in the kernel serves the consumer
better than the same logic replicated in every agent.

## Cells

- Loci: `kernel_shared` (kernel), `replicated_*` (each agent links the
  kernel's pipeline library, Subtask 8), `native_*` (each agent manages
  memory itself, Subtask 6).
- Backends: Mem0 (infer=True, extraction on Azure gpt-4o at
  temperature 0.0, seed 20261105) and in-house (Chroma, verbatim).
- Heterogeneity H ∈ {0, 1, 2} (`docs/HETEROGENEITY.md`).
- Users: pilot_v1's 30, paired: user i is trial i in every cell, with
  the same inputs (`input_sha256`) and the same variants.
- Models: Qwen-2.5:7B (Ollama) first, then GPT-4o (Azure). The
  assistant and the writers use the model; fixed decoding (temperature
  0.0, seed 20261105).
- 3 loci × 2 backends × 3 levels × 30 users = 540 trials per model,
  1,080 in all.
- Judge: gpt-5.4 (Azure), judge prompt v2, greedy (temperature 0.0,
  seed 20261105), as in Subtask 9d.

## Schedule

`Cerebrum/benchmarks/shared_memory/data/pilot_v1_schedule.json`
(`pilot_schedule.py`; the test checks the file equals the generator's
output). It replaces the seeded cycle, which left pairings to chance
(known issue 34). The same file drives every cell, and each results file
records its SHA-256:
`f4f2c8fe6fc0bef8857848df15cc365a44652672d79833570c1c44c989e4c10e`.

- H = 1: each (variant × role) pairing, role writer or consumer, occurs
  3 times: 10 pairings × 3 = 30 users. Every variant is observed in
  isolation on each role. Writer slots alternate ProfileAgent /
  TaskAgent.
- H = 2: two agents deviate, one variant each (H is the number of
  deviating agents). There is one consumer, so a consumer-only stratum
  cannot exist at H = 2. The strata are therefore writer-only (both
  writers, 15 users) and one-of-each (one writer and the consumer, 15
  users). In each stratum every variant fills every slot equally often.
  - The V5-writer-with-blanking-consumer pairing (consumer V2 or V4) is
    capped at 0, so V5 writers are isolated in all 9 of their users.
    The design asks for at least 6.
  - Every V3 consumer is paired with a V1 or V3 writer: the pairing
    under which a consumer that skips the visibility check can leak.

## Measures

- **Primary:** the paired difference kernel − replicated, per user, on
  Profile and Integration (judge scores, 1-5). It is computed per
  backend, and pooled: each user's mean of the Mem0 and in-house
  differences (n = 30).
- **Judge-free** (Subtask 10, `judge_free.py`), per cell:
  - leak rate: the share of trials with `cross_user_rows +
    private_rows_from_others > 0`;
  - `memories_missing` rate: the share of trials with
    `memories_missing > 0`;
  - mean `profile_facts_in_block`.
- **Statistics:** 95% paired t-intervals over users (as in Subtask 9's
  `compare.py`). The difference-in-differences across H is, per user,
  (kernel − replicated at H = 2) − (kernel − replicated at H = 0),
  pooled over backends the same way, with its 95% t-interval.
- Also reported (not part of the rule):
  - kernel − native with the same statistics;
  - per cell means;
  - the H = 1 per-variant breakdown (the gap by variant and role);
  - cost per cell.

## Decision rule

As written before the pilot:

> GO if, for at least one model, pooled over backends: (i) kernel −
> replicated at H=2 is ≥ +0.25 on Profile or Integration with a 95% CI
> excluding 0; (ii) the gap grows with H (the H2−H0
> difference-in-differences has a CI excluding 0); and (iii) kernel leak
> rate is 0 and kernel memories_missing is below replicated's at H ≥ 1.
> Condition (iii) must hold on both models regardless.
>
> CONDITIONAL GO if (iii) holds and the H=2 gap is positive on both
> models but CIs include 0: extend to all 150 users for kernel vs.
> replicated at H=2 on Qwen before committing to Subtasks 16–17 and
> 21–22; everything else in Phase D proceeds.
>
> NO-GO if kernel − replicated at H=2 is ≤ 0 on both models, or (iii)
> fails. Then the paper pivots to the guarantees-under-stress framing
> and a systems venue, and Phase D is re-planned.

Operational reading, fixed before the runs:

- **(i)** On one dimension d (Profile or Integration), the pooled mean
  of kernel − replicated at H = 2 is ≥ +0.25 and its 95% CI lies above
  0.
- **(ii)** On the same dimension d, the pooled H2 − H0 DiD is positive
  and its 95% CI lies above 0. A DiD whose CI lies below 0 means the gap
  shrinks, and fails (ii).
- **(iii)**, per model:
  - the kernel's leak rate is 0 over all its trials (both backends, every
    H);
  - the kernel's `memories_missing` rate over its H ∈ {1, 2} trials,
    both backends pooled, is below replicated's over the same trials.

  The per-H rates are reported too.
- **"The H=2 gap is positive"** (CONDITIONAL GO): the pooled mean of
  kernel − replicated at H = 2 is > 0 on Profile or Integration.
- **"≤ 0 on both models"** (NO-GO): on each model, the pooled H = 2 mean
  is ≤ 0 on both Profile and Integration.
- A result that meets none of the three outcomes is reported as such
  ("no rule outcome") and goes back to the user. It is not rounded to
  the nearest one.
- **Native** is reported with the same statistics. It informs the paper
  but not the decision, because its block and retrieval differ by design
  (known issue 13).

## Pre-stated expectations

- H = 0: kernel and replicated tie (as in Subtask 9d).
- H ≥ 1:
  - V2 and V3 drive misses under replicated and native, and V4 drives
    block collapse. The kernel resolves V2, and it ignores V4's
    settings.
  - V1 and V3 private writers are missed in every locus.
  - V5 degrades every locus.
- Mem0 cells carry about ±2 rows of extraction noise (Azure treats the
  seed as best effort).

## Procedure

- Frozen code: tag `pilot-v1-code` in both repos at the commit that
  includes this file, the schedule and the driver. The driver
  (`scripts/run_pilot_v1.sh`) refuses to start unless both repos are at
  the tag with no tracked change. A cell counts as done only if every
  trial completed and the results file records exactly the tagged
  commits, never `-dirty`.
- Kernels: one fresh kernel per model per phase. The phases are Mem0
  kernel, in-house kernel, and agent-managed (kernel memory off, where
  the kernel's log must show 0 memory operations).
- The Subtask 10 guard is on: a trial whose memory backend failed
  silently fails.
- Network: stay on a network Azure accepts. Mem0 extraction, the judge
  and GPT-4o need it.
- A cell with any failed trial is re-run whole. Every re-run is recorded
  in the results' PROVENANCE.
- Logs: one log per cell, plus one kernel log per kernel start (never
  overwritten), archived to `repo-artifacts/Cerebrum/pilot_v1_hetero/`.
- Analysis: `benchmarks/shared_memory/pilot_analysis.py` and the
  headline-figure draft (the kernel − replicated gap vs. H, one line per
  backend, per model, with CIs). The analysis code is written during the
  runs and does not touch run code.
