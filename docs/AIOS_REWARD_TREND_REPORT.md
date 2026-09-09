# Is the Adaptive Memory Policy Actually Learning? — Reward-Trend Synthesis

**Self-contained report.** Answers, for the gpt-4o 150-trial
`kernel_shared_adaptive` run, whether the LinUCB adaptive-threshold
policy measurably improves over the run — the "why does adaptive match
tuned" question for the paper. It stands alone; the supporting per-step
detail lives in `ARM_INDEX_THRESHOLD_MAPPING_REPORT.md`,
`AIOS_ARM_CONVERGENCE_REPORT.md`, and
`POLICY_ACTION_NULL_INVESTIGATION_REPORT.md`, and the mechanism it
analyzes was verified by the LinUCB reward-normalization fix
(`286c10c`/`a4cef0f`/`44ed99a`, `REWARD_NORMALIZATION_FIX_REPORT.md`).

## Background in one paragraph

The `kernel_shared_adaptive` condition runs three independent LinUCB
contextual bandits that pick memory-gating thresholds
(`novelty_threshold` at add time; `similarity_threshold` and
`redundancy_threshold` at retrieve time). Each picks a threshold from a
6-value discrete "action space" (arm), and after each trial a judge
score (1–5 scale) is fed back as reward via
`MemoryManager.report_reward` → `PolicyManager.update`. If the policy is
learning, reward should trend upward as it settles onto better
thresholds. All numbers below come from the run's own
`policy_trials.jsonl`, scoped to the validated model-pure gpt-4o window
(1,786 reward records; novelty 298, similarity 744, redundancy 744).
Note: similarity and redundancy **co-fire** on every retrieve, so they
are **one shared signal, not two independent ones** — the two
independent signals are **novelty** and the **similarity+redundancy
pair**.

## Headline finding

**Reward is FLAT throughout the run, for both independent signals, and
the algorithm shows no measurable improvement over the 150 trials.**

| Bandit | 1st-third mean | mid-third | last-third | Spearman(position, reward) | classification |
|--------|----------------|-----------|------------|-----------------------------|----------------|
| novelty | 3.973 | 3.939 | 3.947 | rho = −0.032, p = 0.58 | FLAT |
| similarity | 3.973 | 3.950 | 3.944 | rho = −0.032, p = 0.38 | FLAT |
| redundancy | 3.973 | 3.950 | 3.944 | rho = −0.032, p = 0.38 | FLAT |

Reward sits at ~3.95/5 from start to finish. Decile means stay within
[3.87, 4.04] (total drift 0.18 on a 1–5 scale) with no direction. A weak
first-half positive Spearman (rho≈0.17) does **not** survive scrutiny —
the first→middle-third change is slightly *negative* and sub-3.0 rewards
are split evenly across halves, so it is tie-structure noise on a
near-constant series, not an early climb. **Robust to the trial-66
check:** trial 66 (the ~44-min latency outlier) carried an unremarkable
reward of 4.0 (the run's actual minimum, 1.333, belongs to trial 67);
removing trial 66 moves Spearman by ≤0.001 and changes no
classification. The trial-66 latency anomaly is unconnected to the
reward picture.

## This reinforces the earlier selection-frequency finding — one picture, not two

A prior analysis found the bandits' late-run **arm selections** were a
near-even spread (modes at only 20–21%, barely above the 16.7% uniform
baseline for six arms) — i.e. selections never converged. Read together
with flat reward, these are **mutually reinforcing, not two separate
problems**: a bandit whose reward barely changes no matter which arm it
picks has **nothing to learn**, and therefore **no reason to converge**
its selections. Flat reward is the *cause-side* observation; non-
converged selection is the *behavior-side* observation of the same fact.
Their agreement is expected, not coincidental — it is a single coherent
picture of a policy operating on an uninformative reward signal.

## Candidate causes, re-evaluated with this evidence

**1. Equal-credit reward attribution — now the strongest-supported
cause.** `report_reward` applies the **full** trial-level judge score to
**every** bandit decision that touched the trial's memories, undivided
(`manager.py`: "naive equal-credit assignment: the full `reward_value`
is applied to each distinct bandit decision ... the reward is *not*
split"). So every arm of every bandit, on every trial, receives
essentially the same trial-level number regardless of which threshold it
chose. A reward that does not vary with the arm carries **no signal
about which threshold mattered** — which is exactly what a flat,
arm-independent reward curve looks like. This is the leading explanation.

**2. Action-space / tuned-value mismatch — real for similarity &
redundancy, but does NOT explain the key case.** For gpt-4o the offline-
tuned winners are `similarity=0.8` and `redundancy=0.5`, both **outside**
those bandits' arm ranges (similarity arms top out at 0.70; redundancy
arms bottom out at 0.70) — so those two could never reach their tuned
optima. **But novelty is the discriminating case:** its arm range
(0.50–0.95) *brackets* the tuned-optimal 0.7 (arms 0.68 and 0.77 sit on
either side), so the action-space explanation does not apply to it — and
**novelty's reward is still flat and unlearned.** Novelty being flat
*despite* a well-placed action space is the **strongest single piece of
evidence that the problem is the reward signal, not the action space.**
Action-space widening remains independently worth doing for
similarity/redundancy, but it cannot be the whole story.

**3. Alpha (exploration parameter) mistuning — demoted; would not
address this finding.** Alpha only reweights exploration vs. exploitation
of reward differences **that already exist** between arms. It can change
*which* arm gets selected given a spread of learned values; it cannot
manufacture a reward difference where the signal is flat. A flat reward
*level* (not merely flat selection) is not something alpha can fix — if
there is no arm-dependent reward to exploit, alpha is irrelevant. This
moves alpha-retuning from "next thing to try" to "does not target this
problem."

**4. "150 trials is too few" — weaker here than it looks.** The decile
view shows **no directional trend at all** — not even a partial early
rise that more trials would extend. That reads less like "needs more
time to converge" and more like "there is no signal to converge toward."
Not ruled out entirely (a longer run could still surface a faint
signal), but clearly weaker than the equal-credit explanation given the
complete absence of early drift.

## Priority ordering for next steps

Grounded in what *this* evidence supports — and stated as findings, not
as an authorization to change code:

1. **Investigate/fix equal-credit reward attribution BEFORE the
   450-trial re-run.** Re-running 3× the trials against a reward signal
   that may be structurally uninformative risks reproducing the same
   flat, unlearned result at 3× the cost. This should be understood (and
   likely addressed) first — e.g. attributing arm-differentiated reward
   rather than the same trial-level scalar to every decision. (Design of
   that change is a separate task; this report only establishes that it
   is the priority.)
2. **Action-space widening for similarity/redundancy** remains
   independently justified (their tuned optima are unreachable today) but
   does **not** address novelty's flatness, so it is not sufficient on
   its own.
3. **Alpha retuning is deprioritized** — it does not target a flat
   reward level.

## Direct answer to "is the algorithm learning?"

On this run and this data: **no measurable learning.** Reward is flat
across the whole run for both independent signals, selections never
converge, and the two observations are the same underlying phenomenon.
The most likely reason is that the reward signal reaching the bandits is
too diluted by equal-credit attribution to distinguish good threshold
choices from bad ones — most sharply evidenced by novelty, whose action
space is well-placed around the tuned optimum yet still learns nothing.
This also means the paper's "adaptive ≈ tuned" outcome is **not**
explained by the adaptive policy learning its way to the tuned
thresholds; on this evidence the two conditions land at similar judge
scores for reasons unrelated to threshold learning (plausibly the gates
rarely being the binding constraint on this data), and that framing
should be used rather than "adaptive converged to tuned."

## Deviations from the master prompt

None. The requested structure was followed: flat-reward headline;
mutually-reinforcing link to the selection finding; candidate-cause
re-evaluation with novelty's flatness as the discriminating evidence
against the action-space-only explanation; explicit alpha demotion with
reasoning; and equal-credit-before-re-run priority ordering. One factual
value carried forward from the prior convergence report (which corrected
the master-prompt-stated similarity tuned value of 0.70 to the
authoritative 0.8) is used here as well; it strengthens, not changes,
the action-space point.

## Scope / non-modification

Read-only analysis over the run's `policy_trials.jsonl` and config; no
kernel code, `policy.py`, or Cerebrum source was modified. Intermediate
datasets (`logs/gpt4o_reward_events_scoped.csv`,
`logs/gpt4o_select_events_scoped.csv`) are gitignored scratch.
