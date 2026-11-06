# Heterogeneity: agents built differently

NeurIPS Subtask 10. This spec was committed before the variant code.
It defines the heterogeneity stress dimension, the catalog of agent
variants with their grounding, and what the design predicts each variant
does in each locus. The measurements it names are judge-free, and no
scored trial runs under heterogeneity in this subtask.

## The dimension

Each trial runs three agents: two writers, `profile_agent` and
`task_agent`, and the consumer, `assistant_agent`, which receives the
memory block. In the reference implementation they are the agents of
Subtasks 1-9d. The **heterogeneity level** H ∈ {0, 1, 2} is the number of
the three that deviate from the reference. Each deviating agent runs one
variant from the catalog below. H = 0 is the reference.

The thesis: kernel-managed memory puts one policy instance between the
agents and the store, so it should be insensitive to how an agent was
built. The replicated and native loci degrade as more agents deviate,
because each agent applies its own copy of the policy (replicated) or its
own convention (native). The catalog must also contain deviations that
hurt the kernel. Otherwise the dimension would be rigged, so those are
marked below.

## Schedule

Which agents deviate, and with which variant, is a pure function of
`(variant_seed, H, trial_index)` (Cerebrum
`cerebrum/example/agents/variants/schedule.py`). It never depends on the
locus, backend, model or run id, so the cells of a sweep stay paired:
user i gets the same variants in every cell.

- The 15 (agent, variant) pairs are arranged on a cycle of 15 positions.
  Position k belongs to agent `order[k mod 3]`, where `order` is a seeded
  permutation of the three agents. The five positions of each agent carry
  the five variants in a seeded order of that agent's own. Adjacent
  positions, including 14 and 0, always belong to different agents.
- H = 0: no agent deviates.
- H = 1: user i gets the pair at position `i mod 15`.
- H = 2: user i gets the pairs at positions `(5 + 2i) mod 15` and
  `(6 + 2i) mod 15`, which are two different agents.
- Balance: at H = 1 every pair occurs once in every 15 users; at H = 2,
  twice in every 15. The first five users at H = 1 (positions 0-4) and
  the first five at H = 2 (positions 5-14) together apply every pair
  exactly once. The 5-user functional check therefore sees every variant
  on every agent.

Every trial records `heterogeneity_level`, `variants_applied`
(`{agent: variant}`, `{}` at H = 0) and `variants_not_applied` (`{agent:
reason}`: the aspects of a variant that the locus gives the agent no way
to apply, see below). The results file records `heterogeneity: {level,
variant_seed, catalog_version}`. Flags: `run_evaluation.py
--heterogeneity H --variant-seed S`. H > 0 requires `--no-judge` in this
subtask.

## How a variant reaches each locus

A variant changes one or more **aspects** of an agent. Each locus gives
the agent a different set of channels:

| Aspect | Kernel | Replicated | Native |
|---|---|---|---|
| identity: the user id the agent tags its requests and writes with | applied; the kernel canonicalizes it once (below) | applied; each agent's resolver takes it as given | applied; compared as given |
| sharing default on the writers' writes | applied | applied | applied |
| write content and metadata: writers | applied, in the SDK request | applied, in the agent's library call | applied, in the agent's backend call |
| write content and metadata: the assistant's conversation write | **not applied**: the kernel's extractor writes the conversation | applied | applied |
| retrieval config (k, threshold, token budget, block format): the consumer | **not applied**: the chat request carries no retrieval config, and the kernel uses its own | applied, to the agent's own pipeline settings | applied, to the agent's own selection code |
| retrieval config: a writer's existence check before its upsert | **not applied** beyond `k`, which the SDK sends | applied | writers do not read |
| access control on the consumer's reads | **not applied**: the kernel enforces visibility | **not applied**: the library the agent links enforces it, with no switch | applied |

A "not applied" aspect is recorded in `variants_not_applied`. For the
kernel this is the point of the design, not a gap in the experiment: a
consumer's own retrieval config has no path into the kernel's selection.

## The kernel's identity resolution

The library's `IdentityResolver` gains canonicalization rules
(`aios/memory/pipeline/identity.py`, `IdentityRules`). By default it
leaves ids as they are. The kernel configures its one resolver from
`memory.identity`:

```yaml
memory:
  identity:
    casefold: true                 # "Ana_Li" and "ana_li" are one user
    email_domains: ["users.example"]  # "ana_li@users.example" is "ana_li"
```

The kernel canonicalizes a user id once, when it accepts a request: a
memory syscall's `user_id` / `metadata.user_id` at acceptance (before
the write-barrier stamp, so the barrier keys agree), and a chat
request's `user_id` in the retrieval. Every write is then stored under
the canonical id, and every read is scoped to it.

Replicated agents build their resolvers with the library's default (no
rules), as each builds its own barrier (docs/REPLICATED_LOGIC.md,
difference 2). Native agents compare ids as given. A replicated
deployment could give every agent's resolver the same rules. V2's premise
is that one team uses a different convention, which means its resolver
does not. Keeping every agent's rules in step is the coordination the
kernel's single resolver removes. A reviewer may weigh this, so it is
stated here.

## The catalog

Parameters are in each variant's module in
`cerebrum/example/agents/variants/`. "Missing" means `memories_missing`
and "facts" means `profile_facts_in_block` (defined under Measurements).
Predictions are changes against the same user's H = 0 trial in the same
cell. The pilot's trials have one interaction each: the writers write
once, then the consumer reads once.

### V1 stale-version

**What it does.** The agent runs the pipeline library one version back
(N−1), emulated:
- **as a writer:** it keeps the old default sharing policy and writes
  `private` (it does not set `share_memory`);
- **as the consumer:** it builds the legacy block (`block_format:
  legacy`, the format before Subtask 9d).

**Grounding.** Version skew between separately deployed services. In
this codebase, the writers' default was private (`share_memory` False,
since 2026-04-18) until the benchmark made sharing the reference. The
legacy block was the kernel's format until 2026-11-05 (`7cc3774`).

**Predictions.**

| Role | Kernel | Replicated | Native |
|---|---|---|---|
| writer | private memory, not visible to the consumer: missing +1, and facts → 0 when it is the profile writer | same | same |
| consumer | not applied (the kernel builds the block): no change | legacy block: more tokens, the same facts | legacy block: more tokens, the same facts |

**Hurts every locus:** V1 on a writer. An explicit `private` is honored
everywhere.

### V2 identity-convention

**What it does.** The agent tags the user with another convention, an
email form `<user_id>@users.example`, in its writes and requests. A case
variant (`<USER_ID>`) is the same mechanism and is unit-tested.

**Grounding.** Identity bugs hit while building this benchmark: user-less
searches (known issue 10) and the `latest_user_id` guess that caused
cross-user contamination (fixed before Subtask 1). Cross-user
contamination in multi-agent memory (Yang et al. 2026). In a multi-team
deployment, services key users by email or by handle.

**Predictions.**

| Role | Kernel | Replicated | Native |
|---|---|---|---|
| writer | canonicalized to the reference id: no change | stored under the alias: missing +1 | stored under the alias: missing +1 |
| consumer | canonicalized: no change | reads the alias's partition: missing +2, facts → 0 | reads the alias's partition: missing +2, facts → 0 |

**Leaks:** none in any locus. These conventions never map two users to
one id. A convention that does (for example a display name shared by two
users) would turn misses into cross-user rows; it is not in this catalog.
On Mem0, replicated, the alias usually shares the reference id's Chroma
collection, because Mem0Provider truncates collection names without a
hash (DEV_STATUS known issue). Mem0's user filter and the library's
partition check still keep the rows apart, so the prediction is the same.

### V3 missing-metadata

**What it does.**
- **On every write it makes:** omits `owner_agent` and `sharing_policy`.
- **As the consumer:** applies no visibility rule of its own. An agent
  built without access control does not check it either.

**Grounding.** Agents that skip access control (the motivation of
Collaborative Memory and SSGM). This codebase's own rule fails closed on
a missing owner or policy (PROVIDER_CONTRACT.md).

**Predictions.**

| Role | Kernel | Replicated | Native |
|---|---|---|---|
| writer | owner filled from the request, policy defaults to private: missing +1 | the library fills the same defaults: missing +1 | no owner or policy; the consumer's rule fails closed: missing +1 |
| consumer | not applied (the kernel writes the conversation and enforces visibility): no change | conversation filled by the library, visibility enforced: no change | no visibility check: no change at H = 1; at H = 2 with a V1 or V3 writer, that writer's non-shared memory is injected (`private_rows_from_others` +1) |

**Hurts every locus:** V3 on a writer. The kernel defaults to private
(fail closed), so it loses the memory like the others. The kernel is
protected only from the leak, not from the miss.

### V4 tuned-consumer

**What it does.** The agent uses its own retrieval config: k 5,
`relevance_threshold` 0.5, budget 1500 tokens, against the kernel's 10 /
0.0 / 2000.

**Grounding.** Per-agent tuning in multi-team deployments. These are this
codebase's own documented values: `config.yaml.example` shipped
`relevance_threshold: 0.5` from 2026-04-12 to 2026-11-02 and still ships
k 5 / 1500 (known issue 3).

**Predictions.** In the 9d re-baseline, the match scores of relevant
memories were 0.32-0.60 on the kernel path:
- in-house: 30 of 30 profile and 29 of 30 task-context scores were below
  0.5;
- Mem0: 118 of 119 profile and about two thirds of task-context scores
  were below 0.5.

Native Mem0's scores are Mem0's own, saturated near 1.0.

| Role | Kernel | Replicated | Native |
|---|---|---|---|
| consumer | not applied: no change | the threshold drops most rows: `after_threshold` / `after_cap` and block size fall, missing up to +2, facts → about 0; k 5 also caps Mem0's 5-8 rows | in-house: as replicated; Mem0: the threshold drops nothing (scores ≈ 1.0), k 5 caps the 5-8 rows, facts may drop partly |
| writer | not applied beyond k: no change | the existence check finds nothing to update in a one-interaction trial: no change | writers do not read: no change |

### V5 raw-payload-writer

**What it does.** The agent writes the structured JSON (the validated
fields, as in `metadata.structured`) instead of the plain-language
rendering. As the consumer, its conversation write is the turn as JSON.

**Grounding.** Framework conventions differ on what a memory is: a record
or a sentence. Subtask 6 observed writers whose stored outputs were JSON,
nested or aliased.

**Predictions.**

| Role | Kernel | Replicated | Native |
|---|---|---|---|
| writer | stored text is JSON. The library's formatter does not know the canonical keys, so it prints them as `user_name: …` (`raw_payload_rows` +1). The values are still there: facts unchanged on in-house. On Mem0, Mem0 extracts facts from the JSON, so facts depend on its extraction | same (the same library) | in-house: the JSON verbatim in the block (`raw_payload_rows` +1), facts unchanged; Mem0: as kernel |
| consumer | not applied (the kernel writes the conversation): no change | conversation stored as JSON: no change within a one-interaction trial | same |

**Hurts every locus, and the same way:** V5 on a writer. What it degrades
is the form of the stored content, which `raw_payload_rows` measures and
a judge would see. It does not remove the values, so
`profile_facts_in_block`, a value-presence measure, is predicted
unchanged on in-house. That differs from the expectation in the subtask
brief ("degrades profile_facts_in_block similarly in all loci"). The
reason is that the JSON carries the values.

## Measurements (judge-free)

Recorded on every trial of the kernel, replicated and native loci, at
every H (`TrialResult.judge_free`). They come from the injection
diagnostics and the writers' results, never from the judge. To support
them, the diagnostics carry `block_text`, and each injected row carries
its `user_id`, `sharing_policy` and provenance.

- **Provenance.** Every write the harness's agents make carries
  `provenance_agent` and `provenance_user` (the true writer and the
  trial's reference user id). Variants never change these fields, and no
  memory logic reads them. The kernel's own conversation write has none;
  for such a row the stored `owner_agent` / `user_id` stand in.
- `profile_facts_in_block`: the fraction of the user's profile items
  present in the consumer's block, matched as case-insensitive
  substrings. The items are the name, the language, the style and each
  preferred tool. `None` when there is no block text to check, for
  example a failed trial.
- `cross_user_rows`: injected rows whose `provenance_user` (else stored
  `user_id`) is not the trial's user. A leak.
- `private_rows_from_others`: injected rows written by another agent
  (`provenance_agent`, else `owner_agent`) whose stored `sharing_policy`
  is not `shared`. A leak.
- `memories_missing`: writers that stored a memory in the trial of which
  no row reached the block. `memories_missing_writers` names them.
- `raw_payload_rows`: block rows that are a JSON object or contain a
  writer-schema key (`user_name`, `preferred_tools`, ...). The form
  measure for V5.

At H = 0 the design predicts 0 leaks, 0 missing and 0 raw rows in every
cell, and facts at the cell's reference level.

## Functional verification (no scores)

Qwen-2.5:7B, the judge disabled, 5 users of pilot_v1 per cell. Every
(locus × backend × H) combination runs: kernel, replicated and native,
on Mem0 and in-house, at H = 0, 1, 2 (18 cells, 90 trials).
`benchmarks/shared_memory/heterogeneity_report.py` compares each
deviating trial with the same user's H = 0 trial in the same cell and
tabulates, per variant, agent and locus, what changed. The checks:

- V2 and V3: zero leaks under the kernel, and a non-zero
  `memories_missing` or leak under at least one other locus.
- V4: no change under the kernel; `after_cap` or block size changes under
  replicated.
- V5: `raw_payload_rows` rises in every locus. `profile_facts_in_block`
  is reported as it comes out (prediction above).
- Every other prediction in the tables above.

A variant that does not behave as predicted in some locus is a finding
and is written down in DEV_STATUS. It is not tuned away.

## What this does not show

- **No scores.** The judged heterogeneity sweep is a later subtask.
- **One interaction per trial.** Effects that need history do not show
  here: V4 on a writer's existence check, V5 and V3 on the assistant's
  own conversation, and the update path generally.
- **Native leaks are rare by construction.** They need, at H = 2, a V1 or
  V3 writer together with a V3 consumer.
- **V1 is emulated:** settings and defaults, not the old code itself.
- **Mem0 variance:** Mem0 cells still have Mem0's extraction in them. It
  now runs at temperature 0 with a seed (Subtask 10 housekeeping), and
  Azure treats the seed as best effort.
