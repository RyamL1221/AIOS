# Metrics

Every measure the benchmark reports: its definition, the record field it
comes from, whether it needs the judge, and its known limits. This file
is the paper's metrics appendix. Written in NeurIPS Subtask 20
(2026-11-19), before that subtask's code; the judge-reliability rule in
"The k rule" is fixed here before the reliability study runs.

The measures a run records per probe and per trial are computed by the
run's own modules (`probes.score_probe`, `judge_free.measure`,
`stress`). Everything the reports derive from the records is computed
by one module, Cerebrum `benchmarks/shared_memory/metrics.py` (from
Subtask 20): pass rates, paired outcomes and means, the measures more
than one report reads, a cell's leak and missing rates, the judge's
score arithmetic and the decision scoring; the reports import them
from there. Where two measures of the same idea exist with different
rules, both keep their rule and get distinct names below: recorded
numbers do not change (every report's output on the stored runs was
byte-identical before and after the move).

## Conventions

- **Trial**: one user in one cell (locus × backend × model × condition).
  A v1 trial is one answer to one follow-up query (`pilot_v1`). A v2
  trial is a user's whole history and its probe turns (`users_v2`,
  `BENCHMARK_V2.md`).
- **Probe** (v2): one consumer turn of a user's probe session. Six types:
  deletion, privacy, recall, recency, contradiction, integration; and,
  from revision 4, two `decision` items (Amendment 10).
- **Block**: the memory block injected for one consumer turn
  (`diagnostics.block_text`, rows in `diagnostics.injected_memories`).
  A v1 trial has one; a v2 trial has one per probe. A v2 trial's
  top-level `injection_diagnostics` is its integration probe's.
- **The matcher**: the memory library's `normalize` / `value_in` /
  `match_any` (AIOS `aios/memory/pipeline/matching.py`, loaded by
  Cerebrum `probes.py`): casefolded, accents stripped (NFKD), runs of
  whitespace and `- _ . /` collapsed to one space, and a match needs a
  non-`[0-9a-z]` character or the text's edge on each side. A value
  matches when it or one of its aliases does. The deletion forget uses
  the same matcher, so what counts as exposure is what revocation
  removes.
- **Statistics**: paired differences over users with a 95% t interval
  (`probes.t_interval`; none for n < 2); proportions with a 95% Wilson
  interval; paired binary outcomes with lost / gained counts and the
  exact McNemar p. A measure that is None for a trial is left out of its
  mean, unless its entry says otherwise.

## Judged measures

### The judges

| | Primary judge | Second judge |
|---|---|---|
| Model | `gpt-5.4` on Azure | Claude Sonnet 5.5 (`claude-sonnet-5-5`) |
| Route | the kernel's `/query`, `chat_with_json_output` (LiteLLM, `azure/gpt-5.4`) | the Anthropic Message Batches API, Anthropic Python SDK, called directly by the harness |
| Prompt | judge prompt v2 (`judge.py`, sha256 `17f43dd9…`) | the same text: `SYSTEM_PROMPT` as `system`, the filled `USER_PROMPT_TEMPLATE` as the user message |
| Decoding | greedy (temperature 0.0), seed 20261105 (best effort on Azure), `max_tokens` 1000, `response_format` `json_object` (the harness sends a strict `json_schema`; the kernel's `/query` rebuilds the request without it, and the adapter asks for `json_object`) | default sampling (the API accepts no sampling parameter: no temperature, top_p or top_k), thinking off as far as the model allows (`thinking: {type: "between_tools"}`, no tools, so no thinking), a small fixed `max_tokens` |
| Credentials | the kernel's Azure deployment | an OAuth bearer token from `ant auth print-credentials --access-token`, fetched at call time and never stored, with `anthropic-beta: oauth-2025-04-20`; billed to the profile's workspace |

The two judges' decoding settings differ, and neither judge is claimed
to be deterministic: a greedy call on Azure is not repeatable (DEV_STATUS
known issue 24: 5 of 10 identical answers got a different profile score
within one pass), and Claude Sonnet 5.5 samples. Each judge's
repeatability is measured by the repeat protocol below, and the k rule
is applied to each judge separately.

A judge reply is parsed as JSON (`json.loads`, then the first `{` to the
last `}`); keys are normalized; each score is clamped to 1-5. A reply
missing a score is retried (3 attempts). A primary judgment that still
fails fails the trial (Subtask 4b); a second judgment that still fails
is recorded as failed (`failed`, its attempts) and fails nothing, so
that answer has no second-judge score. No server-side fallback model is
used for the second judge: the Batches API refuses it, and a judge must
be one model.

### The three scores of a judgment

A judgment scores three dimensions d ∈ {profile, task, integration},
each 1-5, against the v2 rubric. From Subtask 20 on, its two halves are
reported apart:

- **LLM score** (`llm_<d>`, judged; the headline judged metric). The
  judge's own score. With k repeats, the score at k is the median of k
  independent judgments of the same answer (k odd, so the median is one
  of the scores). Each repeat's score is recorded with it.
- **Keyword score** (`keyword_<d>`, judge-free, deterministic). From the
  answer text and the user's profile and task context
  (`judge._extract_keywords`, `judge.keyword_score`):
  - profile keywords: each part of the user's name longer than 2
    characters, each preferred tool, the preferred language
    (lowercased; the response style is not a keyword);
  - task keywords: words of the current project longer than 2
    characters, and words of the active experiment, the goals and the
    blockers longer than 3 characters (lowercased, deduplicated);
  - a keyword hits when it is a substring of the lowercased answer (no
    word boundary: "go" hits "algorithm");
  - with r the share of keywords that hit: 5 if r ≥ 0.5, 4 if r ≥ 0.35,
    3 if r ≥ 0.2, 2 if r ≥ 0.1, else 1 (1 for no keyword or an empty
    answer);
  - `keyword_integration` = min(`keyword_profile`, `keyword_task`).
- **Hybrid score** (`hybrid_<d>`; continuity column only, never a
  headline). The score every run before Subtask 20 stored as
  `profile_usage_score` / `task_usage_score` / `integration_score`
  (scorer `hybrid_keyword_llm`):

  hybrid_d = max(1, min(5, round((keyword_d + llm_d) / 2)))

  with Python's `round`, which rounds halves to even (2.5 → 2, 3.5 → 4).
  At k repeats the hybrid is formed from the median LLM score. It is
  kept to compare with the workshop and pilot numbers, which are
  hybrids.

The stored results before Subtask 20 keep only the hybrid: neither the
LLM score nor the keyword score is in the record. The keyword score is
recomputed from the record (answer, profile, task context); the LLM
score of a stored answer exists only by judging it again.

**v1 and v2.** A v1 trial is judged once, on its answer. A v2 trial
judges its integration probe only (`question` = the user's follow-up
query, against the user's final profile and task context); the paper
reports its integration dimension, and records profile and task.

**What the judge sees.** The profile, the task context, the query and
the answer. Not the memory block, not the condition, not the locus.

### Reliability protocol

**Calibration set** (`calibration_v1`, committed in Cerebrum
`benchmarks/shared_memory/data/`). 200 answers drawn from the runs judged
with prompt v2 and greedy decoding, each with its source (results
directory, file, trial index, run id) and the judge's inputs (query,
answer, profile, task context):
- sources: `pilot_v1_hetero`, `pilot_v1_amem`, `pilot_v1_graphiti`,
  `pilot_v1_graphiti_native_filter`, `pilot_v1_9d_greedy` (v1); the
  integration probes of `bench_v2_smoke`, `bench_v2_smoke_a4`,
  `bench_v2_smoke_graphiti`, `bench_v2_smoke_s17`,
  `bench_v2_smoke_amem` (v2);
- excluded: failed trials, `kernel_private` and the two baselines (not
  loci), and the re-test copies (`pilot_v1_9d_greedy_retest`,
  `scheduler_check_s18`), whose answers repeat other runs';
- deduplicated by the judge's inputs (query, answer, profile, task
  context): an answer that appears in several runs is one candidate,
  credited to the first source in the order above;
- strata: the cell (dataset version, locus, backend, model, H), and a
  score band from the stored hybrid integration score (low 1-2, mid 3,
  high 4-5);
- selection, seeded (seed 20261120): cells are visited round-robin in a
  seeded order; each visit takes one unused answer of the cell's next
  non-empty band (low, mid, high, cycling), until 200 are taken. So every
  cell gets about the same number of answers, spread over its bands.

**Repeats.** Each judge judges each calibration answer 10 times, in one
session: the primary judge through the kernel at a fixed concurrency,
the second judge in one Batch submission (custom id
`<item>-<repeat>`). Ten, not five: the reliability of a median-of-k
score is measured by comparing two medians from disjoint sets of
repeats, which needs 2k repeats (10 for k = 5); resampling five repeats
would count a repeat drawn twice as agreement.

**Measures**, per judge and dimension, on the LLM score (the keyword
score is constant across repeats; the hybrid is reported beside):
- **exact self-agreement**: over every answer and every pair of its
  repeats, the share of pairs with equal scores;
- **within-1 agreement**: the same, for pairs differing by at most 1;
- **Krippendorff's alpha across repeats**, interval metric, the 10
  repeats as coders;
- **reliability of the median of k**, k ∈ {1, 3, 5}: for every way of
  taking two disjoint sets of k repeats from an answer's 10, the
  two-coder interval alpha between the two sets' medians over all
  answers; the estimate is the mean over those splits (45 for k = 1,
  2,100 for k = 3, 126 for k = 5; every split, for the ordinal alpha
  too); with exact and within-1 agreement of the two medians the same
  way;
- a 95% interval for each alpha: the percentile bootstrap over answers
  (2,000 resamples, seeded).
- Ordinal alpha is reported beside interval alpha; the rule uses
  interval.

### The k rule

Written before the reliability study ran, and applied to each judge
separately:

> k = the smallest k in {1, 3, 5} whose median-of-k LLM score reaches
> Krippendorff's alpha ≥ 0.80 (the point estimate) on both Profile and
> Integration. If k = 5 does not reach it for the primary judge, the
> judge score becomes a secondary metric and the paper leads with the
> judge-free measures.

If the two judges need different k, each judge is used at its own k,
and both are reported. `FULL_GRID.md` records each judge's k and its
cost multiplier (k judge calls per judged answer). Task is not in the
rule: its scores are nearly always 1-2 or 4-5 (22 of 2,400 greedy v1
scores are 3) and are reported with the rest.

### Agreement between the judges

On the calibration set, each judge at its own k (median-of-k LLM
scores), per dimension:
- Krippendorff's alpha (interval), the two judges as coders;
- Spearman's ρ between the two judges' medians;
- the mean offset (second − primary) with its 95% t interval (the
  report pairs the primary judge first and names the subtraction in its
  header).

The second judge's self-agreement is measured by the same protocol
before any of its scores is used.

**Direction agreement.** The stored answers of three runs are judged
again by both judges at their own k, with no new model or kernel run:
- the Subtask 11 pilot (`pilot_v1_hetero`, 1,080 answers);
- Subtask 17's A-MEM smokes: `pilot_v1_amem` (v1, 180) and
  `bench_v2_smoke_amem` (v2, 90 integration probes).

For each run, every paired locus difference it reports: per model,
backend and H, the per-user paired difference kernel − replicated and
kernel − native (the pilot's `gap`); the pilot's pooled-over-backends
differences and its H2 − H0 difference-in-differences; per dimension
(v1: profile, task, integration; v2: integration). A difference's
direction is the sign of its mean (zero is its own sign). Reported: how
many differences the two judges give the same direction, overall and
among those where either judge's 95% interval excludes 0; and the list
of disagreements.

**In the full grid** the second judge scores a stratified 30% subset of
the judged answers at its k, not every answer. The stratification rule
is written into `FULL_GRID.md` before the grid runs.

### Subtask 11's verdict on each score

The pilot's verdict stands as registered (`PILOT.md`, on the hybrid
scores). As a robustness check it is recomputed, with the same rule, on
the keyword score (from the stored records) and on the LLM score (from
each judge's re-judge at its k), and all four are reported.
Condition (iii) is judge-free and does not change.

### Recording

Per judgment in a results file: the judge (name, model id), prompt
version and sha256, decoding, the repeat index, the call's timestamp
(UTC; for a batch, its submission and its end), the LLM scores and
reasoning, the attempts, and the token usage. A calibration row
(`judge_reliability judge`) carries the judge's name and model, the
repeat, the scores, the attempts, the times and the tokens; its prompt
(v2, sha256 `17f43dd9…`) and decoding are the judge's fixed ones, as in
the table above. Per judged trial: the per-repeat LLM scores, their
median, the keyword scores, the hybrid, and the judge timestamps. A
judge's token usage is kept in its own field per judge: it is an
evaluation cost, not the system's, and stays out of `total_tokens` and
`tokens_per_quality`.

## Judge-free measures

Section by section, as the reports group them. "Scope" is what one value
covers.

### Probe outcomes (v2)

Per probe, from `probes.score_probe` (`probe_results[]`):

| Measure | Definition | Limits |
|---|---|---|
| `passed` | recall: every expected value is in the answer. recency, contradiction: the expected value is in the answer and the stale one is not. deletion, privacy: False if the forbidden value is in the answer; else True when the block does not hold it; None without a block. integration: None (judged) | exact matching: a paraphrased value fails; an answer that names both values fails recency and contradiction |
| `expected_present`, `stale_present`, `forbidden_in_answer` | the matcher on the answer | |
| `expected_in_block`, `stale_in_block`, `forbidden_in_block` | the matcher on the block | |
| `transition_marked`, `rows_with_*` (with `row_source`), `contaminated`, `cap_bound`, `budget_bound` | readings of why a probe passed or failed; decide no pass | |

A cell's pass rate per probe type: passed over scored probes of trials
that did not fail, with a Wilson interval (`bench_v2_analysis.cell_rows`,
which also splits deletion by echo users; `stress_report.probe_rows`,
the same count). Two cells are compared per probe type by lost / gained
probes and the exact McNemar p (`stress_report.paired_outcomes`;
`bench_v2_analysis.contrast_rows` reports the same pairs as
kernel-only / replicated-only).

### Leaks and privacy

| Measure | Scope | Definition | Source | Limits |
|---|---|---|---|---|
| `cross_user_rows` | trial (one block) | injected rows whose user (`provenance_user`, else `user_id`) differs from the trial's; a row naming no user counts | `judge_free` (v1 block; v2 integration block) | sees one block |
| `cross_user_rows_all_probes` | trial (every probe) | injected rows, over every probe's block, whose `provenance_user` is set and differs from the trial's user; rows without it are skipped | recomputed from `probe_results[].diagnostics` (stress and ablation reports) | a different rule from `cross_user_rows`; both kept |
| `private_rows_from_others` | trial (one block) | injected rows written by another agent (`provenance_agent`, else `owner_agent`) whose `sharing_policy` is not `shared` (none counts as private) | `judge_free` | |
| leak rate | cell | share of trials with `cross_user_rows + private_rows_from_others > 0` | `pilot_analysis` | |
| privacy probe failed, exposure | probe, trial | the privacy probe's `passed`; a trial is exposed when the forbidden value is in any probe's block or answer | `bench_v2_analysis.exposure_rows` | |

### Lost, withheld and missing memories

| Measure | Scope | Definition | Limits |
|---|---|---|---|
| `memories_missing` | trial | writers other than the consumer that wrote at least one memory, none of whose rows (credited to `provenance_agent`, else `owner_agent`; rows of this user only) reached the block | v2: the whole history's writes against the integration block only |
| `memories_withheld`, `memories_lost` | trial | the missing writers split: withheld when the writer stored nothing shared, lost when it did | |
| missing / withheld / lost rate | cell | share of trials with the count > 0 | |
| `writes_without_fact` (v2) | trial | write events, on a backend that extracts (Graphiti, A-MEM, Mem0), that left no listed row and whose reply named none (Amendments 5, 9) | |
| `writes_without_fact` (v1) | trial | writers whose writes stored no row, on Graphiti or A-MEM | a v1 count of writers, not events |
| `writes_without_row` | trial | write events whose reply listed an empty id list, not suppressed or quota-rejected, on any backend | a looser rule than either `writes_without_fact`; used by the stress report |
| `revoked_value_rows`, carriers left | trial | store rows, in the history and probe listings, that carry a value or alias of the revoked slot (the matcher) | |

### Timing (stress dimensions)

Per probe, from `stress.probe_timing` (`stress.probes[probe_id]`); a
write's commit time is its `committed_at`, else its completion:

| Measure | Definition | Limits |
|---|---|---|
| `writes_in_flight` | events issued at or before the probe and completed after it | |
| `late_writes` | events issued before the probe and committed after its fetch began (`fetch_started_at`); floods excluded | |
| `uncovered_writes` | kernel only: late writes with a barrier sequence above the probe's snapshot | |
| `late_covered` | late writes the probe should have waited for (late minus uncovered) | |
| `late_rows` | stored rows of covered, non-private late writes | |
| `timing_miss` | recall, recency, contradiction: the target event is a covered late write and the expected value is not in the block (an unknown block counts as a miss) | |
| `stale_read` | recency, contradiction: the target is a covered late write and the stale value is in the block | |
| `late_forget` | deletion: a covered late revoke of the target's slot, with the value in the block | |

Per trial: `memories_missing_timing` (writers with a covered late write
at the integration probe and no row in its block), `barrier_timeouts`,
`barrier_drained`.

### Identity

| Measure | Scope | Definition |
|---|---|---|
| `misfiled_rows` | trial | rows written for this user found in the victim's partition at the end of the trial (wrong_user) |
| `identity_overridden_requests`, `identity_overridden_chats` | trial | requests and chats whose claimed user the kernel's session overrode |

### Flood and quota

| Measure | Scope | Definition | Limits |
|---|---|---|---|
| `flood_rows_in_block` | probe | injected rows that are stored flood rows | |
| flood rows per probe | trial | mean of `flood_rows_in_block` over the trial's probes | |
| `flood_writes_accepted`, `flood_rows_stored`, `flood_sessions_over_bound` | trial | flood writes stored, flood rows in the store, sessions whose writer stored more than the quota allows | `flood_rows_written` counts writes, not rows |
| `quota_rejected` | trial | rejections by reason (quota, duplicate) | |

### Profile facts

| Measure | Scope | Definition | Limits |
|---|---|---|---|
| `profile_facts_in_block` | trial (one block) | share of the user's profile items (name, language, response style, each tool) found in the block | its own matcher (`judge_free.contains`): whole words, case-insensitive, no accent folding, multi-word items verbatim; v2: the integration block |
| `profile_facts_in_answer` (new, Subtask 20) | trial (one answer) | share of the user's profile items other than the response style (name, language, each tool) found in the answer, with the same matcher as `profile_facts_in_block`; v1: the answer; v2: the integration probe's answer, against the final profile. Recorded from Subtask 20; for a stored trial, computed from its record (answer and profile). Cell mean: `facts_in_answer` in the pilot report | a style is shown, not named, so it is not an item; the matcher does not see paraphrases |
| `raw_payload_rows` | trial | block rows that are raw JSON or carry a writer-schema key | |

### Block and size

| Measure | Scope | Definition | Limits |
|---|---|---|---|
| `tokens_estimated` | probe | words × 1.3, the formatter's estimate | not a tokenizer count |
| block tokens | cell | mean `tokens_estimated` over probes | `bench_v2_analysis` counts a missing value as 0; the ablation report leaves it out; the heterogeneity report reads the integration probe's only. Each keeps its rule |
| `after_threshold`, `after_cap`, `after_budget` | probe | rows left after the threshold, the count cap, the token budget | |
| `cap_bound`, `budget_bound` | probe | the cap (or budget) removed a row; native: its k was filled with more rows visible | |

### Cost and latency

| Measure | Scope | Definition | Limits |
|---|---|---|---|
| `token_usage`, `writer_tokens`, `backend_llm_tokens`, `embedding_tokens` | trial | tokens of the assistant, the writers, the memory backend's LLM, the embeddings | v2 records no `writer_tokens`. On revision 4 a v2 trial's every field includes its two decision turns (from Subtask 20's fix for the assistant's tokens; the backend and embedding fields always did), so its cost is not comparable with a revision-3 trial's |
| USD per trial | trial | the tokens at `prices.yaml` | a field with more than one model, or an unpriced model, is not priced |
| `latency_seconds`, `latency_breakdown` | trial | the consumer's wall time; its stages | v2 sums the probes' latencies, and on revision 4 the decision turns' |
| `tokens_per_quality` | cell | mean tokens over the mean of the judged means | needs the judge |
| judge tokens (new) | trial | each judge's tokens, in its own field | an evaluation cost, not in the above |

### Decision probe (revision 4, Amendment 10)

Per decision item (`decision_results[]`):

| Measure | Definition |
|---|---|
| `passed` | the answer names exactly one option letter, the correct one |
| `choice` | the letter named, or none |
| `error` | the wrong option's kind: `stale` (a superseded value: a recency failure), `revoked` or `private` (a value the consumer must not use: a deletion or privacy failure), `foreign` (another user's fact: an identity failure); `no_letter` or `multiple_letters` (format) |

A decision turn that errors (no answer, a failed block, a consumer
that raised) is recorded with `turn_error`, is not scored, and fails
nothing. A cell's decision accuracy: correct over the scored items of
trials that did not fail, with a Wilson interval, against chance 0.25
(four options); its error breakdown: each error kind's count and share
of the scored items (`<error>_share`), and the items with a turn error
(`turn_errors`). Judge-free.

A cell's picks (`metrics.decision_picks`, the report's "Picks by option
kind and letter"): of the scored items that named one letter, per item
(`d1`, `d2`) and pooled, each kind's picks (`correct`, `stale`,
`must_not_use`: `revoked` on `d1`, `private` on `d2`; `foreign`) with
its share and Wilson interval; the letters picked and the items'
correct letters, each with a chi-square test's p against uniform.

In a cell with memory the model picks the options whose values its
block holds (the correct ones where memory works), and the option
shuffle set their letters, so there the p of the letters picked tests
the shuffle, not the model: a 150-user cell that answered every `d2`
item correctly would show p = 0.021. A model's letter lean shows in a
`no_memory` cell (`FULL_GRID.md`, "The decision items").

**The items without memory** (revision 4; Amendment 10's no-memory
check over every user: Qwen, kernel locus, in-house, `no_memory`, 300
items, 2026-11-19). Without memory the four options are not equally
plausible to this model:
- accuracy 0.18 [0.14, 0.23], below chance: the correct option is the
  least plausible-sounding;
- the `foreign` option is picked most, on both items (`d1` 0.35 [0.28,
  0.43], `d2` 0.39 [0.32, 0.47]), at a similar rate whatever its letter;
- `d1`'s `stale` option (0.15 [0.10, 0.21]) and `d2`'s `correct` (0.17
  [0.12, 0.24]) and `private` (0.18 [0.13, 0.249]) options are picked
  less than chance;
- the model leans to B (97 of 300, p = 0.03, the two items pooled),
  the letter that is correct least often (66 of 300). The lean moves
  the score by under 0.01: letters picked at its shares (A 66, B 97, C
  72, D 65), whatever the item, would score 0.247 against the correct
  letters (A 85, B 66, C 80, D 69; the sum over the letters of the
  share picked times the share correct; 0.25 with even shares). The
  0.18 is the options' doing, not the letters'.
Within a model, two cells with the same blocks get the same prompts,
so none of this makes a difference between them (Qwen answered every
such pair of the functional check alike); where only one block holds
both the current and the stale value, all of it can act on that side
(`FULL_GRID.md`, "The decision items").
Two readings follow. This model's accuracy without memory is 0.18, not
0.25. And an error names a failure of the memory system only when the
picked option's value is in the block (`options_in_block`): without it,
a `foreign` pick is the model's preference for that option, not a leak.
In the functional check every `stale`, `revoked` and `foreign` error of
an in-house cell with memory had its value in the block (26 of 26), and
19 of 33 of a Mem0 cell's: native Mem0's blocks held the correct
option's value on none of its 20 items, and 12 of its 15 errors were of
a value not in the block.

**What one letter, or the shortest statement, throughout would score**
(2026-11-20; from `users_v2` revision 4 and the no-memory check's
record; checks added in reading, not stated before):
- one letter throughout: 0.22 (B) to 0.28 (A) on the 150 users
  (correct letters A 85, B 66, C 80, D 69), 0.18 to 0.32 on `d2` (A
  48, B 29, C 46, D 27), and 0.13 to 0.37 on `pilot_v2`'s 30 users (A
  22, B 8, C 22, D 8: an uneven draw, p = 0.0045 against uniform; the
  other 120 users have A 63, B 58, C 58, D 61);
- the shortest statement (in characters; a tie counted half)
  throughout: 0.38 (0.33 on `d1`, 0.43 on `d2`). The correct option is
  alone the shortest of the four on 111 of 300 items and ties for it
  on 4; `d2`'s private statement, its marker dropped, is alone the
  longest on 115 of 150. Qwen does not favor the shortest: it picks it
  on 58 of 300 (a pick blind to length: 73) and a tied shortest on 4
  (4);
- what a statement is about: the kinds are tied to slots by
  construction, so a rule that knew each slot's role would score 0.47,
  and 0.97 knowing whether the item is `d1` or `d2`. One prompt does
  not show those roles. Without memory Qwen picks by the subject
  against them: by the option's slot its picks run from 0 of 31 offers
  (`lawyer`) to 22 of 27 (`side_business`), which is what its 0.18 is
  made of.
So no one figure can be assumed for a model's accuracy without
memory; how the grid measures it is open (`FULL_GRID.md`, "The
decision items").

## Known limits

- Exact matching misses paraphrases; the semantic score on probes is a
  reading, never a pass.
- A cell's per-probe-type rate rests on one probe per user (v2), so its
  intervals are wide at 30 users.
- The judge sees one answer and its user's facts, not the conversation
  or the block; it scores how personalized an answer is, not whether the
  memory system served it.
- GPT-4o answers, Mem0's extraction and both judges vary run to run;
  compare cells paired, judged in one window (`FULL_GRID.md`).
- Decision accuracy is not comparable between models, or with 0.25,
  without each model's letters and its accuracy without memory
  (`FULL_GRID.md`, "The decision items": proposed for the grid).
