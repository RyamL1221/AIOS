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
