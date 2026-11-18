# Kernel ablations: where the gains come from

NeurIPS Subtask 19. This spec, with its predictions, was committed
before the code. It answers a reviewer's question (Jg94; claim C4 in
the claims document): which of the kernel's responsibilities produce
its advantage over the replicated and native loci? The kernel locus
gets one switch per responsibility. Each switch removes that one
component, and each is paired with the measurement that should move
when it is gone.

## Why switches, not more conditions

The loci already differ by more than one thing. A replicated cell
gives each agent its own barrier, resolver and quota, and lets a
consumer's own retrieval settings in. A native cell also uses each
agent's own selection, format and visibility code. So a kernel-against-
replicated difference does not say which difference caused it. A switch
removes one component from the kernel and leaves everything else as it
is: same users, same backend, same settings. The ablated cell is paired
user by user with the full kernel in the same condition.

Four controls of earlier subtasks were already such switches
(`no_visibility`, `no_delete`, `writer_scoped`, `no_supersession`,
`BENCHMARK_V2.md`). Each was its own mechanism: a harness attribute of
the writers, a native consumer's flag, or the kernel's
`memory.supersession`. They are folded into the one mechanism below,
and their names are kept as aliases.

## The mechanism

**One config block.** `memory.ablate` in `config.yaml`. Every switch
defaults to the full kernel; an absent block is the full kernel.

```yaml
memory:
  ablate:
    barrier: on            # off
    identity: session      # claim
    visibility: on         # off
    supersession: on       # off
    forget_scope: user     # writer | none
    quota: on              # off
    block_format: compact  # legacy
    block_order: type      # similarity
    budget: on             # off
    threshold: null        # a number: the threshold applied instead
    consumer_config: kernel  # honor
```

An unknown key or value fails startup, naming it. The block is part of
the library's settings (`PipelineSettings.ablate`), so the replicated
agents, which copy the kernel's settings, copy it too; the switches the
library does not implement (identity and the consumer config) have no
effect there. A switch never rewrites another setting: under
`supersession: off` the kernel still reports `supersession: exclude`,
and the switch, not the setting, turns the marking and the exclusion
off. Two paired cells therefore differ in the `ablate` block only.

**Reported.** `GET /memory/config` reports the whole block, with its
defaults filled in, as `pipeline.ablate`.

**Checked.** The harness's pre-flight compares the kernel's block with
the run's ablation (`run_evaluation.py --ablate SWITCH[=VALUE]`, which
may be repeated; the value defaults to the switch's ablated value in
the table below). They must match in every switch, whatever the locus:
a full-kernel cell refuses an ablated kernel, and an ablated cell
refuses a kernel that runs any other ablation. A switch that the
locus does not implement is refused (for example `barrier` on a native
cell).

**Recorded.** Every `TrialResult` records `ablation`, the switches that
differ from the full kernel (`{}` for the full kernel), and the results
file records the kernel's whole block in `run_settings`.

**Aliases.** `--control` keeps its old names. Each one now means an
ablation, recorded as such:

| Control | Ablation | Before this subtask |
|---|---|---|
| `no_visibility` | `visibility: off` | the native consumer skipped its visibility check (native only) |
| `no_delete` | `forget_scope: none` | the writers listed their rows and deleted none |
| `writer_scoped` | `forget_scope: writer` | the writers revoked by their own list and delete |
| `no_supersession` | `supersession: off` | `memory.supersession: off` |

A trial written before this subtask has no `ablation`; readers take it
from the trial's `control` by this table, so earlier results load as
the ablations they were. Two aliases change mechanism, not meaning:
under `no_delete` and `writer_scoped` the kernel and replicated writers
now call the user's forget as in the full kernel, and the forget (the
kernel's, or the library's in a replicated agent) deletes nothing, or
only the writer's own rows. The writer-scoped forget also deletes the
writer's own rows that carry the value under another slot, which the
old list-and-delete did not; an echo row is never one of them (the echo
slot is another writer's), so the echo users read the same. In the
native locus the
switches stay in the agents' own code, as before (`visibility: off` the
consumer's check, `forget_scope: none` the writers' delete).
`no_memory` is not an ablation (it removes every write, not a kernel
component) and stays a control.

## The components

Each row: the switch, what it removes in the kernel locus, the
condition under which the effect should be visible, the measurement
(field names as the harness records them), and the prediction made
before the code. N = 6 is the agent-count dataset `agents_n6`
(`STRESS_DIMENSIONS.md`): five writers (`profile_agent`, `task_agent`,
`docs_agent`, `calendar_agent`, `travel_agent`) and the consumer.

| Component | Switch | What it removes | Visible under | Measurement | Prediction |
|---|---|---|---|---|---|
| Write barrier | `barrier: off` | the kernel stamps no write and no read waits (chat, SDK read, list, forget). The memory thread still runs SDK requests in arrival order, so only a chat's injection, which runs on the request pool, can overtake a queued write | `concurrent` | covered late writes (`stress.probes[*].late_covered`), `stale_read`, `timing_miss`; paired outcomes | covered late writes from 0 to hundreds over 30 users, as replicated's (s18: 552 late writes over 180 probes); a few stale reads or timing misses (s18 replicated: 2 stale reads, both contradiction probes lost) |
| Identity resolution | `identity: claim` | the kernel serves a request for the user id the agent claims, verbatim: a session token is ignored (no binding, no `identity_overridden`) and ids are not canonicalized | `wrong_user`; V2 on `profile_agent` | `stress.misfiled_rows`, cross-user rows in the blocks (`stress_report.cross_user_rows`), `memories_missing`; under V2 `profile_facts_in_block` | wrong_user: misfiled rows from 0 to about one per faulty write (s18 functional check, replicated: 27 to 34 over 5 users), reaching the next user's blocks, `memories_missing` up by about 1; V2: the profile writer's rows go to the alias's partition, profile facts in the block fall to 0. Kernel ≈ replicated |
| Visibility | `visibility: off` | every row of the user's partition is visible to every agent: the selector applies no sharing rule and a read by id needs no ownership or share. Writes stay owner-only, and the user partition stays | V3 on the consumer; the privacy probe | privacy probe `passed`, `forbidden_in_block`; `private_rows_from_others` | the privacy probe fails (its forbidden value in the block) in most users; the full kernel's never fails (Subtask 15: 55 probes) |
| Supersession | `supersession: off` | a later statement of a slot retires no earlier row, and selection excludes none | H = 0; recency and contradiction probes | earlier statements' rows in the block (`stale_in_block`), recency and contradiction `passed` | an earlier statement's row in every in-house recency and contradiction block, and both pass rates down to the levels before supersession (`no_supersession` in Subtask 15: as `f15a`, recency 1 of 5 and contradiction 3 of 5 in-house) |
| Forget scope | `forget_scope: writer` | the forget deletes only the requesting writer's own rows (the slot's, and its own carriers of a value), records no tombstone and scrubs only what it deleted | H = 0; the deletion probe, echo users (i mod 9 in {0, 4, 8}) | carriers left in the store (`revoked_value_rows`), deletion `passed` split by echo user | echo users keep the echo row and fail the deletion probe (Subtask 15 `writer_scoped`: 6 of 8 echo-user probes failed); non-echo users pass as in the full kernel |
| Quota | `quota: off` | no write quota, with `memory.write_quota` still enabled | `flood10`, `flood50` | flood rows in the block per probe (`flood_rows_in_block`), `profile_facts_in_block`, `memories_missing`, `flood_writes_accepted` | the flooding writer's writes all accepted; the native-like collapse, as replicated's in s18: 4.3 to 10 flood rows in a probe's block, profile facts −0.23 and −0.53, `memories_missing` +0.60 and +1.03 (F = 10 and 50) against the full kernel's 1.7 to 1.8 flood rows per probe and no change |
| Formatting | `block_format: legacy`; `block_order: similarity` | the compact block, a header line and a bullet per row (legacy: the kernel's block before Subtask 9d, with delimiters, an instruction line and a timestamp per row); the type order of the block's rows (similarity: the selector's score order) | integration (judge) | `integration_score` | Qwen sensitive, GPT-4o not (Subtask 9c) |
| Budgeted ranking | `budget: off` (k only); `threshold: 0.3` | the 300-token budget (k 30 then limits the block); the 0.0 threshold (0.3 drops lower scores) | integration (judge); cap and budget statistics | block tokens (`tokens_estimated`), `cap_bound` / `budget_bound`, `integration_score` | small |
| Consumer-config enforcement | `consumer_config: honor` | the kernel applies a consumer's own k, threshold and token budget, which its chat request now carries; by default the kernel ignores them | V4 on the consumer | `after_threshold`, `after_cap`, block tokens, `profile_facts_in_block`, `memories_missing` | kernel ≈ replicated on V4: the threshold 0.5 drops most rows (HETEROGENEITY.md, V4), profile facts fall to about 0; in-house, the kernel's block equals replicated's V4 block probe by probe |

The last row makes the V4 critique measurable. The kernel's immunity to
a consumer's own retrieval settings is by construction: the chat request
had no way to carry them. Under `honor` it does, and the kernel applies
them, so the difference between `kernel` and `honor` is what that
construction is worth.

**What carries a consumer's config.** `LLMQuery` gains an optional
`retrieval` (`k`, `relevance_threshold`, `max_memory_tokens`). The
assistant sends its own when it has one: the V4 variant gives the
kernel consumer one now (it had no channel before), so V4's retrieval
aspect is recorded as applied under `honor` and as not applied (the
kernel applies its own) otherwise. A chat's injection diagnostics record
`consumer_config`: what the request carried and whether it was applied.

## The conditions

`--variants AGENT=CODE` (new) gives every user the same variants, so a
condition such as "V4 on the consumer" holds for every user instead of
one user in 15 (the seeded cycle). Every condition below runs the first
users of `agents_n6` in the kernel locus.

| Switch | Conditions |
|---|---|
| `barrier: off` | `--concurrency concurrent` |
| `identity: claim` | `--fault wrong_user`; `--variants profile_agent=V2` |
| `visibility: off` | `--variants assistant_agent=V3` |
| `supersession: off` | H = 0 |
| `forget_scope: writer` | H = 0 |
| `quota: off` | `--fault flood10`; `--fault flood50` |
| `block_format: legacy`, `block_order: similarity`, `budget: off`, `threshold: 0.3` | H = 0 |
| `consumer_config: honor` | `--variants assistant_agent=V4`, with the replicated in-house V4 cell for comparison |

**The driver.** `scripts/run_ablation.sh` runs `ABLATE=<switch>` against
the full kernel on `BACKEND=inhouse` or `mem0`: a phase on the full
kernel and a phase on the ablated kernel, each a fresh kernel, the
switch's conditions in both, the same users, kernel locus only (plus
the replicated V4 cell for `consumer_config`). Graphiti and A-MEM each
get one confirmatory ablation in the full grid (`FULL_GRID.md`).

## Checks

**Functional check** (judge-free, users 0 to 4, in-house, N = 6):
every row on in-house; each prediction confirmed or the deviation
recorded. What counts as confirmed, per switch, in the ablated cell
against the full kernel's:
- `barrier`: at least one covered late write; the full kernel none.
- `identity`: under `wrong_user` misfiled rows and a cross-user row in
  some block; the full kernel neither. Under V2, the profile facts in
  the integration block fall to 0 for every user.
- `visibility`: at least one privacy probe fails with its forbidden
  value in the block; the full kernel's never.
- `supersession`: an earlier statement's row in every recency and
  contradiction block.
- `forget_scope`: users 0 and 4 (the echo users) keep a carrier in
  the store and fail the deletion probe; users 1 to 3 pass.
- `quota`: no quota rejection, and more flood rows in the blocks than
  the full kernel's, at both levels.
- `block_format`, `block_order`: the blocks differ from the full
  kernel's (the format; the order in some probe). The score waits for
  the full grid.
- `budget: off`: the budget binds in no probe; `threshold: 0.3`:
  `after_threshold` never above the full kernel's. The score waits.
- `consumer_config: honor`: the kernel's V4 block equals the replicated
  V4 block in every probe; on the full kernel the V4 consumer's block
  equals the H = 0 block.

**Smoke** (judge-free, users 0 to 29, in-house, N = 6) for the four
switches whose measurement is judge-free and whose mechanism is not
definitional: `barrier`, `identity` (`wrong_user`), `quota` (both
levels) and `forget_scope`. Per switch, the paired difference (ablated
minus full kernel, by trial index) with a 95% t interval for each mean,
and exact McNemar for each probe type's outcomes. A prediction is
confirmed when its primary measure's interval excludes 0 in the
predicted direction: covered late writes per user (`barrier`), misfiled
rows per user (`identity`), flood rows in the block per probe and
profile facts (`quota`), carriers left per user (`forget_scope`; with
the deletion probe's echo-user outcomes reported beside it). "≈
replicated" is reported against s18's replicated cells on the same
users where they exist (concurrency and floods), not tested: they ran
at other commits. The formatting and budget rows need the judge and
wait for the full grid.

**Analysis.** `benchmarks/shared_memory/ablation_report.py` writes one
row per switch and measurement: the full kernel's value, the ablated
value, the paired difference with its interval, and the measurement's
name; and a contribution figure, one horizontal bar per component
(the paired difference of its primary measure, with the interval), each
on its own axis since the units differ.

## What this does not show

- A switch removes a component from the kernel, not from the agents. It
  says what the component is worth inside the kernel, not what an agent
  that implemented it would get.
- Each switch is removed alone. Components can interact (the quota and
  the budget both bound what a flood puts in a block); no pair is
  removed together here.
- In-house only in these checks. Mem0's extraction changes what a write
  stores, so its differences are larger and noisier (known issue 42).
