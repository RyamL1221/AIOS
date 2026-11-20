# The full grid (stub)

Subtask 23 runs the final evaluation, the full grid: every scored cell
at 150 users (`BENCHMARK_V2.md`, Amendment 7). This stub holds what is
decided before
then. It is not the grid's pre-registration: Subtask 23 writes the cell
list, the rules and the analyses before any grid run, and fills in the
sections marked open.

Started 2026-11-16 (Subtask 18 housekeeping).

## Cells decided so far

- **Native k = 30 on Graphiti**, beside its k = 10 cell, to measure how
  much of a native gap is the k native kept (`BENCHMARK_V2.md`,
  Amendment 7; DEV_STATUS open decision 6 (b), confirmed 2026-11-16).
  Graphiti, because the cap binds hardest there: at k = 10 it bound in
  all 540 probes of the Graphiti smoke. The harness switch for the
  native k is the grid's to add.
- **The stress dimensions of Subtask 18** (`STRESS_DIMENSIONS.md`):
  agent count, concurrency and the faulty agent run judge-free in
  Subtask 18; their scored runs wait for the grid.
- **The ablations of Subtask 19** (`ABLATION.md`): Graphiti and A-MEM
  each get one confirmatory ablation in the grid; the formatting and
  budget rows (`block_format`, `block_order`, `budget`, `threshold`),
  which need the judge, are scored there.

Open: the full cell list (loci, backends, models, H, the stress
levels), the users per cell, the run order and the cost; the switch of
each confirmatory ablation; each model's `no_memory` cell ("The
decision items").

## The judge window

**Why.** The judge drifts. The same answers, judged again with the
same prompt, seed and greedy decoding (DEV_STATUS known issue 24):
- in one sitting, 92.2% of profile, 100% of task and 94.4% of
  integration scores were the same (Subtask 9d, 90 trials re-judged);
- a week apart, 75.8%, 98.8% and 83.6% (Subtask 17, 165 identical
  pilot_v1 answers), with mean differences within 0.03.

A judge that moves between the judging of two cells adds a difference
that is not theirs. So every score the paper compares comes from one
window.

**The plan.**
1. **Answers first, scores after.** Every grid cell runs with
   `--no-judge`. Each trial keeps what the judge needs: the integration
   probe's answer and the user's final profile and task context. No cell
   is judged while the grid runs.
2. **One pass over every cell**, after the last cell has finished, with
   one deployment (`gpt-5.4` on Azure, judge prompt v2, greedy
   decoding, the fixed seed), one harness commit and a fixed
   concurrency.
3. **Interleaved.** The pass judges user by user across cells: user i
   of every cell, in a seeded cell order, before user i + 1. Drift
   during the pass then falls alike on every cell, and on both sides of
   every paired comparison.
4. **Bounded.** The window runs from the pass's first judgment to its
   last and closes within 24 hours. Subtask 23 checks that bound
   against the pass's size and Azure's rate limits before the run. An
   interrupted pass resumes inside the window; one that cannot finish
   in it is redone whole in a new window, never completed in another.
5. **Anchors.** A fixed anchor set, the 165 pilot_v1 answers of
   Subtask 17's test-retest, is judged at the window's start and at its
   end. Reported per score: the share of identical scores, and the
   paired mean difference (end − start) with its 95% CI. Stated now: if
   a score's CI excludes 0, that score's judgments from the window are
   not used and the pass is redone.
6. **Recorded.** Per judgment: the window id, a timestamp, the
   deployment and its API version, and the judge prompt's sha256. Per
   results file: the window id. The analysis refuses to compare scores
   from two windows.
7. **Re-runs.** A cell re-run after its window (a failed user, known
   issue 36) is judged again, in a new window, with every cell it is
   compared against.

**Tooling Subtask 23 adds.** `rejudge.py` judges the top-level (v1)
fields, which a v2 trial mirrors from its integration probe, and since
Subtask 20 writes each judge's record on the probe too (not when a
primary judgment fails: DEV_STATUS known issue 55); it must also
interleave across results files and record the window. And a window
report: the anchors' agreement and the pass's start, end and failures.

Open: the pass's size and cost (one judge call per judged trial, plus
retries), the concurrency, and the cell order's seed.

## Size and cost (Subtask 20)

An estimate, for the decision on what Subtask 23 runs. It fixes no
cell: the cell list, the rules and the analyses are Subtask 23's to
write. Where the documents leave a choice open, the choice sized here
is named and listed under "Open decisions" below. Computed 2026-11-20
from the stored runs' own records (Cerebrum `results/<run>/` and the
logs in `repo-artifacts/Cerebrum/`); no run was made for it.

**The grid as sized.** 455 cells and 68,250 user-trials, every cell at
150 users:
- **v1** (`users_v1`, all 150 users): 4 backends × 3 loci × H 0, 1, 2
  × 3 models (Qwen, Llama and GPT-4o, `MODELS.md`): 108 cells.
- **v2** (`users_v2` revision 4, with its decision items), on the same
  three models: the 12 locus × backend cells at H = 0 and at H = 2 (24
  cells a model), and each control at H = 0 in the cells the
  functional checks ran it in (`no_delete` in all 12, `no_visibility`
  in the 4 native cells, `writer_scoped` and `no_supersession` in the
  8 kernel and replicated cells: 32 a model): 168 cells.
- **The stress dimensions** (`STRESS_DIMENSIONS.md`): the cells of
  Subtask 18's functional check, on in-house and Mem0, for the stress
  pair of `MODELS.md` (Qwen and GPT-4o). Per backend and model: N 3, 6
  and 12 at H 0 and 2 in the three loci (18 cells), `concurrent` (3),
  the faults `wrong_user`, `missing_metadata`, `flood10` and `flood50`
  (12), and the load mode at 1, 4 and 16 users at a time (kernel only,
  3): 144 cells. The floods are the decided ones: 10 and 50 extra rows
  a session, against a quota of 4 writes.
- **The ablations** (`ABLATION.md`), at N = 6 in the kernel locus:
  every switch on in-house for Qwen (22 cells: 8 on the full kernel, 13
  ablated, and the replicated V4 cell); the four judged switches
  (`block_format`, `block_order`, `budget`, `threshold`) and their
  reference for GPT-4o too (5), since the formatting prediction names
  both models; one switch and its reference on Graphiti and on A-MEM
  (4, sized as a switch whose condition is H = 0): 31 cells.
- **Single cells**: native at k = 30 on Graphiti (1: Qwen, H = 0), and
  one `no_memory` cell per model (3: kernel locus, in-house,
  judge-free, as `decision_nomemory150_s20` ran it): 4 cells.

**How a row is sized.**
- **Seconds per user** are a stored cell's wall clock in its driver's
  log (its `start` and `done` lines) over its users: the writers, the
  backend's calls, the consumer's turns, the listings and the harness.
  A driver starts a phase's kernel before the phase's first cell, so a
  kernel start (17 and 19 s in `driver_mem0.log`) falls between cells
  and is left out. One cell has no such lines, the pilot's re-run of
  native Mem0 at H = 0, and is read from its own log (21:07:52 to
  21:28:23). Summed latencies are used only to split a cell's time
  (the rules below).
- **Made the grid's.** A stored cell differs from a grid cell in three
  measured ways, and each row is corrected for them:
  - before the event-driven scheduler (AIOS `c389539`, known issue 15)
    every model call waited about 0.85 s (`scheduler_check_s18`: median
    845 ms before, 1.0 ms after). Every v1 and v2 cell used here ran
    before it, and the stress, ablation and decision cells after;
  - a grid cell runs with `--no-judge` ("The judge window"): a judged
    stored user loses 3.9 s, its judge call (3.05 s, the mean of the
    2,325 judge calls in those runs' kernel logs) and the wait before
    it. A cell run before the new scheduler also loses 0.85 s for each
    other model call: 3 a v1 user (the assistant and the two writers)
    and 6 a v2 user (the probes);
  - a v2-type cell (on `users_v2` or its agent-count versions: the v2,
    stress and ablation cells) run before revision 4 gains its two
    decision turns: 4.9 s a user in-house and 8.3 s on Mem0
    (`decision_functional_s20`, the 10 cells with memory of each
    backend: 0.97 to 8.64 s and 5.73 to 10.41 s).

  So the 13.3 s a user of GPT-4o's v1 in-house cells become 6.9 s,
  and the 98.9 s of Qwen's v2 in-house kernel cell become 94.8 s.
- **Users.** Every row but one rests on cells of 30 users or fewer,
  scaled to 150 by the user count: an extrapolation ("Not measured"
  below). The one 150-user cell is Qwen's `no_memory`.
- **Basis.** `M30`, `M16`, `M5`, `M150`: measured on that many users in
  the run named; the range is over its cells' wall clocks per user,
  before the corrections. `R1` to `R10`: no cell of its own, sized by
  the rule named.
- **Hours** are cells × users × seconds per user. **Dollars** are cells
  × users × a rate per user; the second judge's users are 45 of 150
  ("The two judges").

**Rates per user.**
- **Assistant**: GPT-4o rows only; Qwen and Llama run here. v1:
  $0.0066 (the assistant's and the two writers' calls, the 18 GPT-4o
  cells of `pilot_v1_hetero`). v2 and every row built on it: $0.019,
  not measured: Qwen's tokens a user in the v2 smokes (2,320 to 2,485
  in and 952 to 1,216 out over six probes, by backend) and two
  decision turns of 472 in and 2 out (`decision_functional_s20`) give
  $0.018 to $0.021 by backend. `no_memory`: $0.0085 (1,251 in, 541 out
  over its eight turns, `decision_nomemory150_s20`).
- **Backend extraction**, on Azure gpt-4o whatever the assistant
  (`memory.backend_llm`, `MODELS.md`). v1, from the H = 0 cells (agent
  cells at H > 0 counted fewer calls before Cerebrum `a836d69`): Mem0
  $0.065, Graphiti $0.096 and A-MEM $0.0144 a user. v2, from the
  smokes: Mem0 $0.36 (139,700 tokens in and 1,100 out), Graphiti $0.42
  (153,600 and 3,500) and A-MEM $0.10 (23,200 and 4,400). The decision
  check's Mem0 cells, at Subtask 20's code, agree: $0.34 to $0.37 a
  user with memory (6,982,522 tokens in and 55,668 out over its 65
  trials, $18.01). Under the floods on Mem0, from the 5-user cells of
  `stress_functional_f18b`: kernel $0.40, replicated and native $0.73
  at F = 10 and $2.22 at F = 50.
- **Prices**: gpt-4o $2.50 and $10 per million tokens in and out
  (Cerebrum `prices.yaml`, from price aggregators as of 2026-11-03;
  Microsoft's page not checked); GPT-5.4 $2.50 and $15 (OpenAI's model
  page, read 2026-11-20); Claude Sonnet 5.5 $2 and $10, half in the
  Message Batches API: $1 and $5 (Anthropic's API reference as bundled
  with Claude Code, its price table of 2026-11-03).
- **The judge**: $0.0058 a judgment, 1,037 tokens in and 215 out (the
  calibration's 2,000 judgments; the re-judge's 1,350: 1,015 and 211).
  **The second judge**: $0.0038, 1,711 in and 415 out (the re-judge:
  1,675 and 399). Each at k = 1, the k the rule gave it (Cerebrum
  `results/judge_reliability_s20/`); at k = 3 a judge's dollars and
  hours triple.

**The rules**, each with what it rests on:
- **R1, Llama as Qwen.** No Llama cell after Subtask 9d: none on
  Graphiti or A-MEM, none at H > 0, none on v2. Llama's rows take
  Qwen's seconds. In the two stored runs with both (Subtask 9's and
  9d's `pilot_v1` baselines: 30 users, H = 0, in-house and Mem0),
  Llama's six locus cells took 0.89 and 0.78 of Qwen's wall clock
  (0.63 to 1.16 by cell).
- **R2, GPT-4o in a v2-type cell.** No GPT-4o cell on v2, on the
  stress dimensions or under an ablation. A row takes what its Qwen
  cells spend outside the consumer's turns (wall clock less the
  consumer's summed latency, corrected as above), plus GPT-4o's time
  for the same turns: 1.07 s and 6.33 ms per completion token a call
  (a line through the pilot's 180 GPT-4o kernel trials, their latency
  less the scheduler's recorded wait, R² 0.73), for six probes with
  Qwen's completion tokens and two decision turns. What is left of a
  v1 in-house kernel user once the model's own seconds in the kernel
  log are taken out is the same for both models (4.46 s Qwen, 4.48 s
  GPT-4o), which is what the rule assumes. Concurrent and load rows
  are sized as sequential ones.
- **R3, GPT-4o on Graphiti and A-MEM in v1.** No such cell. GPT-4o's
  in-house seconds, plus what the backend adds in Qwen's v1 kernel
  cells (wall clock less the model's seconds in the kernel log, against
  the in-house kernel's): 16.9 s on Graphiti and 3.3 s on A-MEM. The
  same rule gives Mem0 3.1 s, against 3.7 s measured (GPT-4o's Mem0
  cells less its in-house cells).
- **R4, H = 2 and the controls in v2.** At 30 users only H = 0 is
  measured. A cell at H = 2 or under a control takes the H = 0 seconds
  of its locus and backend (a backend's 8 controls are 3 kernel, 3
  replicated and 2 native cells). In the 5-user checks
  (`bench_v2_functional_*`, `stress_functional_f18b`) an H = 2 cell
  took 0.61 to 1.78 of its H = 0 cell (31 pairs, median 0.94), but the
  in-house kernel's 1.05 to 1.52 (4 pairs), so R4 may be low there. A
  control took 0.77 to 1.78 of its H = 0 cell (40 pairs, median 1.01,
  with `decision_functional_s20`); the three above 1.3 ran at 1.44 to
  1.78 times their reference's milliseconds per completion token.
- **R5, H = 1 on Graphiti and A-MEM in v1.** Not run. The mean of the
  H = 0 and H = 2 cells.
- **R6, the other agent counts and the identity faults.** At 30 users
  only N = 6 at H = 0, `concurrent` and the floods are measured, all
  in-house (`stress_smoke_s18`). The other levels take the N = 6,
  H = 0 seconds. At 5 users (`stress_functional_f18b`) the kernel cells
  took 67.6, 66.0 and 64.0 s at N = 3, 6 and 12 in-house and 115.0,
  114.0 and 105.2 s on Mem0, and a `wrong_user` or `missing_metadata`
  cell 0.78 to 1.17 of its reference (12 pairs).
- **R7, no 30-user cell at N = 6 on that backend.** The stress cells on
  Mem0 and the ablation pairs on Graphiti and A-MEM take the seconds
  of the v2 H = 0 cells (N = 4). At 5 users the Mem0 cells at N = 6
  come to 122.3, 114.9 and 128.7 s by the same corrections (kernel,
  replicated, native; `stress_functional_f18b`), against the v2
  cells' 132.1, 98.6 and 100.9 s used here. The decision check's Mem0
  cells at H = 0, run at Subtask 20's code (no judge, the new
  scheduler, the decision turns) and so not corrected, took 108.8,
  144.4 and 170.2 s (5 users).
- **R8, ablation cells outside the smoke.** The smoke ran 10 of the 22
  cells at 30 users. The other 12 take the mean of the ten. At 5 users
  (`ablation_functional_f19b`) the 12 took 106.1 s a user on average
  (63.0 to 141.2), against 103.1 s for the ten.
- **R9, native at k = 30.** Its k = 10 cell: the harness has no switch
  for the native k yet ("Cells decided so far").
- **R10, decision turns on Graphiti and A-MEM.** Not measured: 6.6 s a
  user, the mean of the 20 in-house and Mem0 cells with memory.

**v1**: 150 users of `users_v1`. A backend's 9 cells per model are 3
loci × H 0, 1, 2. Every row is judged.

| Cells | n | Users | s per user | Basis | Hours | Assistant $ | Backend $ | Judge $ | Second judge $ |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| Qwen and Llama (9 each), in-house | 18 | 150 | 34.9 | M30 `pilot_v1_hetero`: 9 Qwen cells, 34.5 to 49.2 s. Llama R1 | 26.2 | 0 | 0 | 16 | 3 |
| Qwen and Llama (9 each), Mem0 | 18 | 150 | 38.5 | M30 `pilot_v1_hetero`: 9 Qwen cells, 38.6 to 51.2 s. Llama R1 | 28.9 | 0 | 176 | 16 | 3 |
| Qwen and Llama (9 each), Graphiti | 18 | 150 | 51.4 | M30 `pilot_v1_graphiti` (native: `pilot_v1_graphiti_native_filter`): 6 Qwen cells at H 0 and 2, 50.1 to 63.5 s; H = 1 R5. Llama R1 | 38.5 | 0 | 259 | 16 | 3 |
| Qwen and Llama (9 each), A-MEM | 18 | 150 | 31.3 | M30 `pilot_v1_amem`: 6 Qwen cells at H 0 and 2, 34.3 to 41.8 s; H = 1 R5. Llama R1 | 23.5 | 0 | 39 | 16 | 3 |
| GPT-4o, in-house | 9 | 150 | 6.9 | M30 `pilot_v1_hetero`: 9 cells, 12.3 to 14.0 s | 2.6 | 9 | 0 | 8 | 2 |
| GPT-4o, Mem0 | 9 | 150 | 10.5 | M30 `pilot_v1_hetero`: 9 cells, 15.9 to 18.8 s | 3.9 | 9 | 88 | 8 | 2 |
| GPT-4o, Graphiti | 9 | 150 | 23.8 | R3: no cell | 8.9 | 9 | 130 | 8 | 2 |
| GPT-4o, A-MEM | 9 | 150 | 10.2 | R3: no cell | 3.8 | 9 | 19 | 8 | 2 |
| **Sum** | 108 | | | | 136.3 | 36 | 711 | 96 | 20 |

**v2**: 150 users of `users_v2`. A backend's cells per model are 6 at
H = 0 and 2 (3 loci × 2) and 8 controls. Every row is judged, on its
integration answer.

| Cells | n | Users | s per user | Basis | Hours | Assistant $ | Backend $ | Judge $ | Second judge $ |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| Qwen and Llama (6 each), in-house, H = 0 and 2 | 12 | 150 | 86.4 | M30 at H = 0: 98.9 (kernel), 99.7 (replicated) in `bench_v2_smoke_s17`, 73.0 (native) in `bench_v2_smoke_a4`; H = 2 R4. Llama R1 | 43.2 | 0 | 0 | 10 | 2 |
| GPT-4o, in-house, H = 0 and 2 | 6 | 150 | 16.2 | R2: no GPT-4o v2 cell | 4.0 | 17 | 0 | 5 | 1 |
| Qwen and Llama (8 each), in-house, controls | 16 | 150 | 88.6 | the same cells, 3 : 3 : 2; R4. Llama R1 | 59.1 | 0 | 0 | 14 | 3 |
| GPT-4o, in-house, controls | 8 | 150 | 16.3 | R2: no GPT-4o v2 cell | 5.4 | 23 | 0 | 7 | 1 |
| Qwen and Llama (6 each), Mem0, H = 0 and 2 | 12 | 150 | 110.5 | M30 at H = 0: 132.8 (kernel), 99.3 (replicated) in `bench_v2_smoke_s17`, 101.6 (native) in `bench_v2_smoke_a4`; H = 2 R4. Llama R1 | 55.2 | 0 | 648 | 10 | 2 |
| GPT-4o, Mem0, H = 0 and 2 | 6 | 150 | 44.1 | R2: no GPT-4o v2 cell | 11.0 | 17 | 324 | 5 | 1 |
| Qwen and Llama (8 each), Mem0, controls | 16 | 150 | 111.7 | the same cells, 3 : 3 : 2; R4. Llama R1 | 74.5 | 0 | 864 | 14 | 3 |
| GPT-4o, Mem0, controls | 8 | 150 | 44.3 | R2: no GPT-4o v2 cell | 14.8 | 23 | 432 | 7 | 1 |
| Qwen and Llama (6 each), Graphiti, H = 0 and 2 | 12 | 150 | 181.2 | M30 at H = 0: 184.5, 186.8, 179.4 (kernel, replicated, native) in `bench_v2_smoke_s17`; H = 2 R4. Llama R1 | 90.6 | 0 | 756 | 10 | 2 |
| GPT-4o, Graphiti, H = 0 and 2 | 6 | 150 | 132.9 | R2: no GPT-4o v2 cell | 33.2 | 17 | 378 | 5 | 1 |
| Qwen and Llama (8 each), Graphiti, controls | 16 | 150 | 181.7 | the same cells, 3 : 3 : 2; R4. Llama R1 | 121.1 | 0 | 1,008 | 14 | 3 |
| GPT-4o, Graphiti, controls | 8 | 150 | 132.6 | R2: no GPT-4o v2 cell | 44.2 | 23 | 504 | 7 | 1 |
| Qwen and Llama (6 each), A-MEM, H = 0 and 2 | 12 | 150 | 118.2 | M30 at H = 0: 122.9, 121.2, 117.5 (kernel, replicated, native) in `bench_v2_smoke_amem`; H = 2 R4. Llama R1 | 59.1 | 0 | 180 | 10 | 2 |
| GPT-4o, A-MEM, H = 0 and 2 | 6 | 150 | 74.7 | R2: no GPT-4o v2 cell | 18.7 | 17 | 90 | 5 | 1 |
| Qwen and Llama (8 each), A-MEM, controls | 16 | 150 | 118.5 | the same cells, 3 : 3 : 2; R4. Llama R1 | 79.0 | 0 | 240 | 14 | 3 |
| GPT-4o, A-MEM, controls | 8 | 150 | 74.8 | R2: no GPT-4o v2 cell | 24.9 | 23 | 120 | 7 | 1 |
| **Sum** | 168 | | | | 738.0 | 160 | 5,544 | 144 | 28 |

**The stress dimensions**: 150 users of the agent-count datasets
(`agents_n3`, `agents_n6`, `agents_n12`, derived from `users_v2`, 150
users each). The load rows are not judged.

| Cells | n | Users | s per user | Basis | Hours | Assistant $ | Backend $ | Judge $ | Second judge $ |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| Qwen, in-house, agent count and the two identity faults | 24 | 150 | 70.5 | M30 `stress_smoke_s18`: the N = 6, H = 0 cells, 59.5 to 68.8 s; other levels R6 | 70.5 | 0 | 0 | 21 | 4 |
| Qwen, in-house, concurrent | 3 | 150 | 73.4 | M30 `stress_smoke_s18`: 59.6 to 75.4 s | 9.2 | 0 | 0 | 3 | 1 |
| Qwen, in-house, flood10 and flood50 | 6 | 150 | 75.2 | M30 `stress_smoke_s18`: 64.6 to 78.2 s | 18.8 | 0 | 0 | 5 | 1 |
| Qwen, in-house, load 1, 4, 16 (kernel) | 3 | 150 | 72.4 | M16 `stress_functional_f18b`: 60.1 to 79.8 s | 9.1 | 0 | 0 | 0 | 0 |
| Qwen, Mem0, agent count, concurrent, the two identity faults | 27 | 150 | 110.5 | R7: the three v2 Mem0 H = 0 cells | 124.3 | 0 | 1,458 | 23 | 5 |
| Qwen, Mem0, floods, kernel | 2 | 150 | 132.1 | R7: the v2 Mem0 kernel cell | 11.0 | 0 | 120 | 2 | 0 |
| Qwen, Mem0, flood10, replicated and native | 2 | 150 | 99.8 | R7: the v2 Mem0 replicated and native cells | 8.3 | 0 | 219 | 2 | 0 |
| Qwen, Mem0, flood50, replicated and native | 2 | 150 | 226.2 | M5 `stress_functional_f18b`: 212.4 and 223.4 s | 18.9 | 0 | 666 | 2 | 0 |
| Qwen, Mem0, load 1, 4, 16 (kernel) | 3 | 150 | 100.2 | M16 `stress_functional_f18b`: 86.6 to 98.5 s | 12.5 | 0 | 162 | 0 | 0 |
| GPT-4o, in-house, agent count and the two identity faults | 24 | 150 | 16.0 | R2: no GPT-4o cell | 16.0 | 68 | 0 | 21 | 4 |
| GPT-4o, in-house, concurrent | 3 | 150 | 18.9 | R2: no GPT-4o cell | 2.4 | 9 | 0 | 3 | 1 |
| GPT-4o, in-house, flood10 and flood50 | 6 | 150 | 17.0 | R2: no GPT-4o cell | 4.2 | 17 | 0 | 5 | 1 |
| GPT-4o, in-house, load 1, 4, 16 (kernel) | 3 | 150 | 17.9 | R2: no GPT-4o cell | 2.2 | 9 | 0 | 0 | 0 |
| GPT-4o, Mem0, agent count, concurrent, the two identity faults | 27 | 150 | 44.1 | R2: no GPT-4o cell | 49.6 | 77 | 1,458 | 23 | 5 |
| GPT-4o, Mem0, floods, kernel | 2 | 150 | 48.6 | R2: no GPT-4o cell | 4.0 | 6 | 120 | 2 | 0 |
| GPT-4o, Mem0, flood10, replicated and native | 2 | 150 | 41.9 | R2: no GPT-4o cell | 3.5 | 6 | 219 | 2 | 0 |
| GPT-4o, Mem0, flood50, replicated and native | 2 | 150 | 170.9 | R2: no GPT-4o cell | 14.2 | 6 | 666 | 2 | 0 |
| GPT-4o, Mem0, load 1, 4, 16 (kernel) | 3 | 150 | 33.8 | R2: no GPT-4o cell | 4.2 | 9 | 162 | 0 | 0 |
| **Sum** | 144 | | | | 382.9 | 207 | 5,250 | 116 | 22 |

**The ablations**: 150 users of `agents_n6`, kernel locus. Only the
rows of the four judged switches are judged.

| Cells | n | Users | s per user | Basis | Hours | Assistant $ | Backend $ | Judge $ | Second judge $ |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| Qwen, in-house, the four judged switches and their reference | 5 | 150 | 110.9 | M30 `ablation_smoke_s19`: 10 cells, 97.1 to 116.7 s; cells outside it R8 | 23.1 | 0 | 0 | 4 | 1 |
| Qwen, in-house, the other seven switches | 17 | 150 | 110.9 | M30 `ablation_smoke_s19`: 10 cells, 97.1 to 116.7 s; cells outside it R8 | 78.6 | 0 | 0 | 0 | 0 |
| GPT-4o, in-house, the four judged switches and their reference | 5 | 150 | 18.9 | R2: no GPT-4o cell | 3.9 | 14 | 0 | 4 | 1 |
| Qwen, Graphiti, one switch and its reference | 2 | 150 | 182.1 | R7: the v2 Graphiti kernel cell | 15.2 | 0 | 126 | 0 | 0 |
| Qwen, A-MEM, one switch and its reference | 2 | 150 | 120.5 | R7: the v2 A-MEM kernel cell | 10.0 | 0 | 30 | 0 | 0 |
| **Sum** | 31 | | | | 130.8 | 14 | 156 | 8 | 2 |

**Single cells.** The k = 30 cell is judged; the `no_memory` cells are
not.

| Cells | n | Users | s per user | Basis | Hours | Assistant $ | Backend $ | Judge $ | Second judge $ |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| Qwen, native Graphiti at k = 30 | 1 | 150 | 177.0 | R9: its k = 10 cell, `bench_v2_smoke_s17` | 7.4 | 0 | 63 | 1 | 0 |
| Qwen and Llama, `no_memory` | 2 | 150 | 31.2 | M150 `decision_nomemory150_s20` (Qwen). Llama R1 | 2.6 | 0 | 0 | 0 | 0 |
| GPT-4o, `no_memory` | 1 | 150 | 12.5 | R2: no GPT-4o cell | 0.5 | 1 | 0 | 0 | 0 |
| **Sum** | 4 | | | | 10.5 | 1 | 63 | 1 | 0 |

**The judges.** Judged, once by the primary judge: every v1 answer, and
the integration answer of every v2, stress and k = 30 user, the
controls' included; of the ablations, the four judged switches and
their reference. Not judged: `no_memory`, the load cells and the other
ablation cells.

| Pass | Judgments | Hours | $ |
|---|---:|---:|---:|
| Primary judge, one pass over every judged answer | 62,850 | 14.9 | 365 |
| Its anchors: 165 answers at the start and at the end | 330 | 0.1 | 2 |
| Second judge: 45 of 150 users, one batch | 18,855 | | 72 |

- The pass is timed at the calibration's rate: 2,000 judgments in 28
  minutes 27 seconds at 8 workers (17:09:12 to 17:37:39 UTC), 0.85 s a
  judgment. The re-judge of 1,350 answers, one process per results
  file, took 21 minutes 16 seconds: 0.95 s a judgment, or 16.6 hours
  for the pass. Either is inside the window's 24 hours, if the rate
  holds for 15 hours (it is measured over 28 minutes) and Azure's
  limits allow it: they are not known, and the pass drew about 88,000
  tokens a minute.
- The second judge's batch runs at Anthropic, not here. The
  calibration's batch of 1,998 requests was collected 3 minutes 12
  seconds after its submission, and the re-judge's 1,350 ended 4
  minutes 2 seconds after theirs. 18,855 requests are under the
  Batches API's 100,000 a batch; its 256 MB a batch is not checked
  against the requests' size.

**Totals.**

| Block | Cells | Hours | Days | Assistant $ | Backend $ | Judge $ | Second judge $ |
|---|---:|---:|---:|---:|---:|---:|---:|
| v1 | 108 | 136.3 | 5.7 | 36 | 711 | 96 | 20 |
| v2 | 168 | 738.0 | 30.8 | 160 | 5,544 | 144 | 28 |
| The stress dimensions | 144 | 382.9 | 16.0 | 207 | 5,250 | 116 | 22 |
| The ablations | 31 | 130.8 | 5.5 | 14 | 156 | 8 | 2 |
| Single cells | 4 | 10.5 | 0.4 | 1 | 63 | 1 | 0 |
| The judge's pass and anchors | | 15.0 | 0.6 | | | 2 | |
| **Sum** | 455 | 1,413.5 | 58.9 | 418 | 11,724 | 367 | 72 |

- **Serially**: 1,414 hours, 58.9 days of 24 hours, at the speeds the
  stored cells ran at.
- **Dollars**: $12,509 on Azure (assistant 418, backend extraction
  11,724, the judge 367) and $72 for the second judge: $12,581. Backend
  extraction is 93% of it; the stress cells on Mem0 alone are $5,250.
- **By model**: Qwen 192 cells and 768 hours, Llama 93 and 351, GPT-4o
  170 and 280; in dollars, to the nearest 10: 5,100, 2,180 and 5,300.

**The laptop's speed.** Qwen's time per completion token moves with
the laptop's heat and power state (DEV_STATUS known issue 48), and the
rows above are as measured, on whichever day their run fell. The same
cell (N = 6, H = 0, kernel, in-house, 30 users, the same tokens) took
68.8 s a user in `stress_smoke_s18` on 2026-11-17 (69.4 ms per
completion token) and 102.0 s in `ablation_smoke_s19` on 2026-11-18
(102.1 ms). As bounds, every local-model row's model time (its
consumer's and decision turns, and in v1 the writers' generation) is
rescaled to the fastest and the slowest speed a stored 30-user Qwen
cell had, the old scheduler's wait taken out: 40.8 and 75.1 ms per
completion token in v1 (`pilot_v1_amem` replicated, `pilot_v1_hetero`
kernel in-house, both H = 0), 49.0 and 115.2 ms in the v2-type cells
(`bench_v2_smoke_a4` native Mem0, `ablation_smoke_s19` `quota` at
F = 50). That gives 1,193 and 1,926 hours for the cells: 50.3 and 80.9
days with the judge's pass. GPT-4o's rows do not move.

**What can run at once.** As the drivers stand, one cell at a time:
- Every driver starts its kernel on port 8000 (all but
  `run_pilot_v1.sh` refuse a port in use) and rewrites its checkout's
  one `config.yaml` for each phase (`run_bench_v2.sh`,
  `run_stress_s18.sh`, `run_ablation.sh`, the pilot drivers). So one
  driver per checkout at a time.
- Two local-model cells would share Ollama, which bounds throughput.
  In the load mode 16 in-house users took 79.8, 62.7 and 60.1 s a user
  at 1, 4 and 16 at a time (0.75, 0.96 and 1.00 users a minute), and
  on Mem0 90.8, 86.6 and 98.5 s (`stress_functional_f18b`).
- GPT-4o cells use the laptop for the embedder, the kernel and the
  harness only (and Neo4j on Graphiti). Their 280 hours could overlap
  local-model cells on a second kernel with its own checkouts, port and
  stores: the harness takes its kernel from `CEREBRUM_KERNEL_URL` (a v2
  run refuses a `--kernel-url` other than the configured one), but no
  driver takes a port. That bounds the gain at 11.7 days. It is not
  measured, and both kernels would load Ollama and Azure.
- The judge's pass comes after the last cell, by design ("The judge
  window"), through a kernel too. The second judge's batch runs at
  Anthropic, after the pass.
- Never at once: two cells of one kernel (one memory thread, one store
  directory, one tombstone file) or two with one run id (known issue
  36). Graphiti cells share one Neo4j database, kept apart by group id.

**Not measured, or not in the sizes.**
- **Cells without a cell of their own.** 256 of the 455 cells have no
  stored cell of their model, backend and condition at any user count:
  Llama's 93, GPT-4o's 152 (all but its 18 v1 cells on in-house and
  Mem0), Qwen's 6 v1 cells at H = 1 on Graphiti and A-MEM, the k = 30
  cell and the 4 ablation cells on Graphiti and A-MEM. 116 are
  measured on 5 or 16 users only, and 83 on 30 or more.
- **150 users.** No cell with a store in the runs used here has more
  than 30 users. In the one 150-user cell (`no_memory`, no store) users
  30 to 149 took 1.13 times the first 30's latency a user at the same
  completion tokens: the laptop slowed (51 to 58 ms per completion
  token). Within the 30-user v2 cells, what a user spent outside the
  consumer's turns (the writes, the backend, the listings, the judge)
  changed from the first third of the users to the last by 0.89 to 1.06
  (Graphiti 0.97 to 1.04, A-MEM 0.97 to 0.99): it did not grow with the
  store. A cell's time per user rose by up to 1.57 where the model
  slowed (`bench_v2_smoke_s17`, in-house kernel: 75 to 117 ms per
  completion token). Whether Graphiti slows as its one Neo4j database
  grows is not measured: the grid's Graphiti cells are 10,800
  user-trials, against 505 in the stored Graphiti runs measured here.
- **The decision turns** are measured on 5 users a cell, and vary from
  cell to cell (0.97 to 10.41 s a user over the 20 cells with memory).
  On Graphiti and A-MEM they are not measured (R10).
- **Re-runs.** A cell with a failed user is re-run whole, under a new
  run id (known issue 36), and a 150-user cell holds five times a
  30-user cell's trials. One of the pilot's 36 cells was re-run, for an
  Azure connection drop. A cell with writer failures in more than 20%
  of its trials reports no scores (`MODELS.md`); Llama's writers fail
  more often than Qwen's. No allowance is made here.
- **Prices and limits.** Azure's own prices were not read.
  `prices.yaml` lists regional gpt-4o deployments 10% higher ($2.75 and
  $11), and OpenAI's page prices regional processing of GPT-5.4 10%
  higher. The Azure deployments' rate limits are not known: the stored
  runs ran one cell at a time. By its tokens and seconds a user, a Mem0
  kernel cell on Qwen draws about 64,000 gpt-4o tokens a minute, a
  Graphiti kernel cell 52,000, and a GPT-4o Mem0 cell, being faster,
  about 192,000.
- **The stress dimensions on Graphiti and A-MEM** are not in the grid
  as sized: Subtask 18 ran in-house and Mem0, and its driver has no
  phase for the other two. By the v2 rows, the 27 sequential and
  concurrent cells a model would be 204 hours and $1,701 on Graphiti
  and 133 hours and $405 on A-MEM for a local model. Their flood cells
  cannot be sized: no flooded Graphiti or A-MEM write is measured.
- **The ablations on Mem0** are not in it either (`run_ablation.sh`
  takes `BACKEND=mem0`; `ABLATION.md`'s checks are in-house). By R7 its
  22 cells would be 121 hours and at least $1,188 a model.
- **`kernel_private` and Subtask 9's two baselines** (`naive_concat`,
  `vanilla_rag`) are not in the list above and are not sized.

**Three options.** None is chosen here.

**(a) Run everything as sized.** 455 cells at 150 users: 58.9 days run
serially (50.3 to 80.9 by the bounds above) and about $12,580, before
re-runs.
- It needs first, and none of it exists: an H = 1 and H = 2 schedule
  for v1's 150 users (`pilot_v1_schedule.json` covers 30) and a v2
  schedule for H = 2 (`BENCHMARK_V2.md`, "Loci and backends"); the
  harness switch for the native k; drivers for 150 users (the stress
  and ablation drivers fix `pilot_v2`, the pilot drivers `pilot_v1`),
  for Llama (no driver knows it) and for GPT-4o where
  `run_stress_s18.sh` and `run_ablation.sh` know only Qwen;
  `run_ablation.sh` for Graphiti and A-MEM (it takes `inhouse` and
  `mem0`); the judge window's tooling ("The judge window"); and the
  pre-registration.
- It needs throughout: the laptop awake and on power for two months or
  more (a clamshell sleep ended a cell of `bench_v2_functional_a4`),
  and a network Azure accepts for the 1,058 hours (44 days) of cells
  that call it. Azure refused this machine's calls after a router
  restart and under a second VPN (Subtasks 18 and 20). The 106
  in-house cells on local models (340 hours) call nothing outside.
- It gives every cell of the list at 150 users.

**(b) A reduced grid**: (a) with four cuts. Together: 303 cells, 652
hours of cells and a 9-hour judge pass: 27.5 days run serially (23.1
to 38.5 by the bounds), about $5,025. Three of the cuts run cells at
fewer than 150 users (the controls and the judge-free ablations at 30,
the load cells at 16), against "every scored cell at 150 users" (this
file's opening, `BENCHMARK_V2.md` Amendment 7): choosing them changes
that rule.
- **v2 without Llama** (its 56 cells and its `no_memory` cell). Saves
  292 hours and $1,906. Costs: v2 rests on one local and one API
  model, with no second small model reading the same blocks; v1 keeps
  all three. v2's writers call no model, so the writer failures that
  set Llama apart in `MODELS.md` are not what its v2 cells would test.
- **The controls on Qwen only, at `pilot_v2`'s 30 users** (32 cells of
  30 users in place of 64 of 150). Saves 223 hours and $2,052. Costs:
  each control rests on 30 users and one model. A rate at 0 or 1
  carries a Wilson interval 0.11 wide where 150 users give 0.025, and
  a control's decision items are 60 a cell, against 300. No control is
  paired with the GPT-4o cells. In the kernel locus two of them
  (`supersession: off`, `forget_scope: writer`) also run among the
  ablations, at N = 6.
- **The stress dimensions on Qwen, and on GPT-4o at N = 6
  in-house.** Qwen keeps every cell but Mem0's nine agent-count cells
  at H = 2; the load cells, on both backends, run at 16 users, as
  measured so far; GPT-4o keeps only the N = 6 in-house cells (18: the
  reference, `concurrent` and the four faults). 63 cells cut. Saves 149
  hours and $3,469. Costs: the stress predictions, stated per locus,
  are shown on an API model at N = 6 in-house only (no GPT-4o cell on
  Mem0 or at N = 3 or 12); the agent count at H = 2 on in-house only
  (v2 keeps Mem0 at H = 2, with N = 4); the load mode on one model and
  at 16 users.
- **The judge-free ablation cells at 30 users** (the seven other
  switches' 17 cells and the two pairs on Graphiti and A-MEM; the four
  judged switches stay at 150 users on both models). Saves 83 hours and
  $125. Costs: those switches keep intervals of the width Subtask 19's
  smoke had (every primary interval excluded 0 there), on a re-run at
  the grid's commit.
- Kept whole: v1 (10% of the cell hours); v2's 48 cells at H = 0 and
  2 on Qwen and GPT-4o; Qwen's stress cells but nine; the k = 30 cell;
  both judges. So every prediction the documents state keeps a test at
  150 users, but the controls and the judge-free ablations (at 30
  users) and the load mode (at 16). Not cut, though it could be: Llama
  in v1 (36 cells, 59 hours, $274), the workshop's third model
  (`MODELS.md`). The claims document `ABLATION.md` cites was not read
  for this: it is not among either repository's tracked files.

**(c) Run it elsewhere** (a university cluster, or other machines).
What that would need, from the code as it stands:
- **A unit of work that can be copied.** One job is one driver with its
  own AIOS and Cerebrum checkouts (a driver rewrites `config.yaml`, and
  the kernel's and the agents' stores live under the checkouts), its
  own kernel port, its own Ollama and, for Graphiti, its own Neo4j or
  its own groups in a shared one. The drivers fix port 8000; the
  harness reads its kernel from `CEREBRUM_KERNEL_URL`. So: a port
  parameter in the drivers, and a job per phase.
- **The models.** Ollama serving the pinned Qwen, Llama and embedding
  models (`MODELS.md`'s digests), one GPU a job for the local-model
  cells. GPT-4o cells need the embedder only.
- **Azure from there.** The resource admits listed networks only: it
  refused this machine's calls whenever they left from another address
  (DEV_STATUS, Subtask 20). The cluster's addresses must be admitted,
  or the cells that call Azure stay here: all but the 106 in-house
  local-model cells.
- **Secrets on shared storage**: the Azure variables and the Neo4j
  credentials, kept in `AIOS/.env` (DEV_STATUS, Subtasks 6 and 16).
  The second judge's token is fetched on this machine at call time,
  and both judges need only the stored answers, so the judging can
  stay here.
- **Neo4j** 5.26.33 for the Graphiti cells: a Docker container here.
- **One kind of machine per comparison.** Qwen and Llama repeat their
  answers on this laptop under the fixed decoding (`MODELS.md`); across
  hardware that is not checked. Cells compared with each other would
  run on one kind of machine, the stored laptop runs would not be mixed
  in, and latency and the load mode would measure the cluster.
- **A smoke there first**, as each new backend had: the 12 v2 cells at
  H = 0 on Qwen at 30 users are 12.4 hours on one worker and $79 of
  backend calls, and the in-house cells' blocks can be compared with
  the stored ones probe by probe.
- **What it buys**: with K jobs at once, about 1,398 / K hours of cells
  (175 at 8, 87 at 16) plus the judge's pass, if the cluster's speed
  matches this laptop's. The longest cell is 9.4 hours. K jobs multiply
  the load on Azure (above).
- **Not known**: the cluster's GPUs, queue and storage, whether its
  nodes may call Azure, and whether it runs containers.

**Open decisions.** Each is sized above under the choice named first.
1. **v2's models.** The three of v1, or the stress pair: Llama's 56
   cells and its `no_memory` cell are 292 hours and $1,906.
2. **The controls.** Every control in each cell it applies to, at 150
   users on three models, judged (96 cells, 423 hours, $3,360); or
   fewer users, models or cells, or unjudged (their 14,400 answers are
   $84 of the judge and $16 of the second judge).
3. **The stress dimensions' cells.** The functional check's 72 cells a
   model on in-house and Mem0 for Qwen and GPT-4o (383 hours, $5,595);
   or the smoke's design (12 in-house cells a model: 37 hours on Qwen);
   or more backends (Graphiti and A-MEM, above). The load cells at 150
   users (12 cells, 28 hours, $342) or at the check's 16.
4. **The ablations.** Which switches run at 150 users and on which
   models; whether Mem0 gets the set; which switch Graphiti and A-MEM
   get (a `quota` or `barrier` switch needs flood or concurrent cells
   there, which nothing measures); and whether the five full-kernel
   cells that repeat stress cells (23 hours) run once.
5. **v1 and v2 at H > 0 on 150 users.** Which schedule: the pilot's
   balanced design extended to 150 users (each H = 1 pairing 15 times,
   for 3), or another rule; and v2's at H = 2. No H > 0 cell can start
   before it.
6. **The native k = 30 cell.** One cell (Qwen, H = 0: 7.4 hours, $64)
   or one a model (GPT-4o's by R2: 5.6 hours, $67).
7. **Each model's `no_memory` cell** (DEV_STATUS open decision 8).
   Qwen's exists (78 minutes; kept, or run again at the grid's commit);
   GPT-4o's is one draw (31 minutes and $1.28 by R2); Llama's only if
   Llama runs v2; and whether its integration answer is judged.
8. **Measuring before the list is fixed.** The rows without a cell
   could be measured first, at R1's and R2's sizes: a 30-user GPT-4o
   v2 cell on each backend, 2.2 hours and $30 in all; a 30-user Llama
   cell on each backend in v1 and in v2, 5.4 hours and $33; one
   150-user in-house v2 kernel cell, 4.0 hours and no Azure call
   without its judge.
9. **Azure's prices and limits.** Read the two deployments' own prices
   (global or regional) and rate limits before a budget is fixed:
   backend extraction is $11,724 at `prices.yaml`'s price.
10. **Re-runs.** No allowance is made; one could be budgeted once the
    failure rate at 150 users is known.

## The two judges (Subtask 20)

Definitions, the reliability protocol and the k rule are in
`METRICS.md` ("Judged measures"). Fixed here for the grid:

**Decoding differs, and neither judge is claimed to be deterministic.**
The primary judge, `gpt-5.4` on Azure, decodes greedily (temperature
0.0) with a best-effort seed (20261105). The second judge, Claude
Sonnet 5.5, uses default sampling: its API accepts no sampling
parameter. Repeatability is measured for each judge by the repeat
protocol (10 judgments of each of 200 calibration answers), and the k
rule (the smallest k in {1, 3, 5} whose median reaches Krippendorff's
alpha ≥ 0.80 on Profile and Integration) is applied to each judge
separately. If the two judges need different k, each is used at its
own k and both are reported.

| Judge | k | Cost multiplier | Evidence |
|---|---|---|---|
| `gpt-5.4` (primary) | 1 | 1 call per judged answer | median-of-1 alpha: Profile 0.864 [0.827, 0.893], Integration 0.906 [0.876, 0.929] (Cerebrum `results/judge_reliability_s20/`) |
| Claude Sonnet 5.5 (second) | 1 | 1 call per answer in its subset | median-of-1 alpha: Profile 0.966 [0.951, 0.977], Integration 0.963 [0.947, 0.975] (Cerebrum `results/judge_reliability_s20/`) |

Both judges reach the rule's 0.80 with one judgment, so each answer is
judged once by each judge that scores it. (At k > 1 an answer would be
judged k times in the window, its score the median, every repeat
recorded.)

**The second judge's subset**, fixed before the grid runs. The second
judge scores 30% of the judged answers, at its k, chosen by user, so
the same users are in the subset in every cell and every paired
difference of the grid (kernel − other, H2 − H0) also exists on the
subset:
- strata: echo users (i mod 9 in {0, 4, 8}, `synth_v2.is_echo_user`)
  and the other users;
- order: within each stratum, the indices of users_v2's 150 users in
  the order `random.Random(20261121).shuffle` gives the stratum's
  sorted list (echo stratum shuffled first, then the other, from one
  generator);
- a cell with users U takes, from each stratum, the first
  round(0.3 × |U ∩ stratum|) of U's users in that order (at least one
  when U has a user of the stratum); at 150 users, 15 echo and 30
  others, 45 in all;
- the subset never depends on a score: it is fixed by the user index
  alone.

Code: Cerebrum `judge.second_judge_users(users)`. At 150 users it is
users 4, 5, 7, 11, 15, 16, 20, 25, 26, 27, 28, 32, 36, 38, 41, 43, 44,
49, 54, 56, 57, 60, 61, 62, 66, 72, 74, 78, 79, 80, 89, 90, 93, 94,
96, 97, 105, 106, 115, 120, 130, 134, 138, 140 and 147.

The second judge's answers go in one Batch submission after the
primary judge's pass has closed. The Batches API orders its work as it
chooses, so the interleaving of the primary pass does not apply; the
batch's submission and end bound its window, recorded with every
judgment. Reported on the subset: inter-judge alpha, Spearman and mean
offset per dimension, and direction agreement for each of the grid's
paired differences (`METRICS.md`, "Agreement between the judges").

## The decision items (Subtask 20)

Definitions are in `METRICS.md` ("Decision probe").

**Decided** (by the user, 2026-11-20): in the grid a decision accuracy
is reported with its model's letter distribution beside it, so that a
letter bias does not hide in a result. How that is met is proposed
below, and fixed by Subtask 23 with the cell list.

**Why.** Two things let the letters move an accuracy:
- a model picks some letters more than others (a letter lean). Without
  memory Qwen picks B on 97 of 300 items (A 66, C 72, D 65; p = 0.03
  against uniform);
- an item's correct letter is fixed in the dataset, and the correct
  letters are not spread evenly: A 85, B 66, C 80, D 69 of 300 (p =
  0.36), and on `d2` A 48, B 29, C 46, D 27 of 150 (p = 0.021). The
  shuffle is fair (`BENCHMARK_V2.md`, Amendment 10); the unevenness is
  the draw of `pilot_v2`'s 30 users, who have A 22, B 8, C 22, D 8 (p
  = 0.0045), where the other 120 have A 63, B 58, C 58, D 61.

So a rule that picks one letter for every item, whatever the item
says, scores 0.22 (B) to 0.28 (A) on the 150 users, 0.18 to 0.32 on
`d2`, and 0.13 to 0.37 on `pilot_v2`; any fixed mix of letters scores
between. Two such rules can stand 0.06 apart on the 150 users (0.14 on
`d2`, 0.23 on `pilot_v2`).

Qwen's lean costs it under 0.01, and may cost nothing: letters picked
at its shares, whatever the item, would score 0.247 against these
correct letters (the sum over the letters of the share picked times
the share correct; 0.25 with even shares; 0.244 to 0.250 with the
picks resampled). Its 0.18 without memory is the options' doing
(`METRICS.md`, "The items without memory"). No other model's lean is
measured.

**What the report gives now.** Per cell: its decision accuracy and, in
the same report, its letters picked beside its items' correct letters,
for each item and pooled (the v2 analysis's "Picks by option kind and
letter"). Nothing per model, and nothing for a part of a cell's users.

**Proposed for Subtask 23** (not fixed here: the cell list, the rules
and the analyses are its to write):
1. Per model, a `no_memory` cell over the grid's users, where every
   pick is a guess: its accuracy (the model's accuracy without
   memory), its picks by option kind and its letters picked. Qwen's,
   over all 150 users: Cerebrum `results/decision_nomemory150_s20`.
2. Per cell, the accuracy for each correct letter on `d1` and on `d2`,
   and the mean of the eight: the evened-out accuracy. A rule that
   picks by the letter alone scores 0.25 on it whatever its lean, with
   or without memory (the shuffle places the correct option
   independently of the item), where each letter is the correct one on
   enough items: it is not defined on users 0 to 4, where no `d1` item
   has C and no `d2` item has D. In Qwen's `no_memory` cell: correct
   on A 7 of 85, B 19 of 66, C 14 of 80, D 14 of 69 over the two items
   (chi-square of right or wrong by correct letter, p = 0.012, a check
   added in reading); evened out 0.184 (`d1` 0.185, `d2` 0.182),
   against 0.180.
3. The letters beside an accuracy are those of the items it is
   computed over: an accuracy on a part of the users has correct
   letters of its own (`pilot_v2` above).
4. In a model's `no_memory` cell, the share of picks that are the
   shortest statement, beside its letters: the correct option is alone
   the shortest statement on 111 of 300 items, so the shortest
   throughout scores 0.38 (0.43 on `d2`), more than any one letter
   (`METRICS.md`, "The items without memory").

**Readings of the records so far**, proposed for Subtask 23's rules:
- the p of the letters picked tests a lean in a `no_memory` cell only.
  In a cell with memory the model picks the options whose values its
  block holds (the correct ones where memory works), and the shuffle
  set their letters: a 150-user cell that answered every `d2` item
  correctly would show p = 0.021 (0.004 on `pilot_v2`);
- no lean is tested on counts summed over a model's cells (the
  report's `pooled` row, the two items of one cell, stays): the cells
  ask the same items, so the sum repeats them;
- within a model, a lean makes no difference between two cells whose
  blocks are the same: the items, their letters and the model are the
  same on both sides (Qwen answered every such pair of the functional
  check alike). Where only one cell's block holds both the current and
  the stale value (as under native or `no_supersession`), a lean can
  act on that side: the earlier of the two options is the correct one
  on 0.51 of the 150 users' items (the later on 0.49) and on 0.62 of
  `pilot_v2`'s (0.38). The records show no such effect for Qwen: in the
  native and `no_supersession` cells of both backends, where a block
  held both, it took the earlier option 27 times and the later 27;
- a paired difference also depends on the model: an item one cell
  answers from its block and the other guesses adds 1 minus the
  guess's accuracy (0.18 for Qwen with an empty block; it moves with
  what else the block holds, below).
  So paired differences are read within a model, and two models' are
  not compared without their accuracies without memory;
- a model's accuracy without memory is a reference, not a lower bound,
  and a cell is read against it on the same users. Every error of the
  functional check's in-house cells with memory was of a stale, revoked
  or foreign value the block held (26 of 26), so a cell can fall below
  it. Where the block lacks the four values the picks are guesses, and a
  guess's worth moves with the rest of the block: native Mem0's 16 items
  whose block held none of the four values were right on 4, the same
  items with an empty block on 0. The lowest cell with memory stored,
  native Mem0 under `wrong_user`, scored 1 of 10: below the 150-user
  0.18, above its five users' own 0 of 10. 0.25 stays the registered
  chance level.

**Tooling Subtask 23 adds.** The driver already runs a model's
150-user `no_memory` cell when asked (AIOS `scripts/run_bench_v2.sh`:
`MODE=decision DATASET=users_v2 TRIALS=150 CONDITIONS=no_memory
PHASES=kinh MODELS=<model>`; it knows `qwen` and `gpt4o`). To add: a
row per model in the v2 analysis; the accuracy by correct letter and
the evened-out accuracy (a definition in `METRICS.md`, code in
`metrics.py`; not computed where a letter is never the correct one); a
paired comparison of decision items between two cells, over the users
scored in both, its unit (the user or the item) to fix: the analysis
pairs the five judge-free probe types only; the p of the letters
picked printed for `no_memory` cells only (it is the asymptotic
chi-square, and not valid in a row of 10 items); and, if the stress or
ablation report comes to print a decision accuracy (neither reads a
decision item now), its letters beside it.

Open: each model's `no_memory` cell over the grid's users (DEV_STATUS
open decision 8). Qwen's answers without memory have repeated on every
run so far (users 0 to 4: the functional check's six `no_memory`
cells, in-house and Mem0, and the 150-user run), so its cell needs one
run; GPT-4o's answers vary from run to run, so its cell is one draw.
For both, the
letters and the accuracy are estimates over the items and carry their
intervals (Qwen: B 0.32 [0.27, 0.38]; accuracy 0.18 [0.14, 0.23]).
Open too: whether Amendment 10's readings of the no-memory check (the
0.45 line, a kind's interval, p < 0.05 on the letters picked) are
applied to each model's cell.
