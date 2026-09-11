# Reward-Loop Investigation — Synthesis & Go/No-Go (Subtask 5)

Final synthesis of the "Close the Adaptive-Policy Reward Loop"
investigation. No code changes, no new pilot runs. One cheap on-disk
cross-reference was done to characterize the emily/alex asymmetry (§2).

---

## 1. Does the loop close on clean data, and can arms move? YES.

From `CLEAN_2x10_PILOT_VERIFICATION.md` (live 2×10, kernel PID 42753, no
mid-run restart, gpt-4o/gpt-5.4):

- **Reward events: 0 → 110.** `logs/policy_trials.jsonl` = 178 `select`
  + **110 `reward`**; 9 `report_reward: reward applied` lines kernel-side;
  9 `report_reward` calls with non-empty `memory_ids_involved`.
- **All three bandits moved off arm 0.** Selects: novelty `{0:2, 1:22}`;
  similarity `{0:14,1:4,2:47,3:4,4:4,5:4}`; redundancy identical. Reward
  updates landed across arms 0–5.
- **Both fail-open branches fired live:** bootstrap fail-open 20×,
  "honoring converged arm" 43×.

The decision → reward → update chain that was completely broken in the
premise-confirmation run (0 reward events, all arms pinned to arm 0) now
closes. This is the core deliverable and it is met.

**Claim scope:** "the loop closes and arms can move." NOT "it learns."
N=20 (9 rewarded trials, 1 user per effective condition) is far too small
for any learning/quality claim.

## 2. The emily_carter / alex_morgan asymmetry — RESOLVED AS STRUCTURAL (not noise)

Observed: emily_carter (s0) = 14 injected ids across 10 interactions;
alex_morgan (s1) = **0** across 10 — despite identical write counts and
identical post-run retrievable records (both 12: 1 profile + 1
task_context shared + 10 conversation private).

A cheap cross-reference of the on-disk data (results JSON per-trial
`injection_status` + `kernel.log` gate lines) **resolves this as a
structural session-order artifact, not noise and not write/retrieval
failure.** The evidence:

- **Per-trial split is perfectly clean, not scattered:** every
  emily_carter trial 0–8 = `audit_inferred` (ids injected); trial 9 +
  **all ten alex_morgan trials = `unknown` (0 ids)**. Random noise would
  not split exactly on the session boundary.
- **alex_morgan's rows WERE retrieved, then dropped by a converged arm.**
  `kernel.log` for trials 10–19 repeatedly shows
  `similarity_threshold=0.700 (arm 2) dropped all N result(s); honoring
  converged arm (arm_updates=8 >= 1)` with `kept 0/N` (N=2..5). So the
  audit found rows; the *converged* similarity gate (arm 2 = 0.70)
  rejected them because their similarity sat below 0.70.
- **Why emily got injections and alex didn't — the fail-open, not
  relevance.** Early in s0 the similarity arm was unvalidated
  (`arm_updates=0`), so the **bootstrap fail-open kept rows across arms
  0.60→0.70→0.80→0.90→0.95 despite them being below threshold** (log:
  "would drop all N ... still bootstrapping ... failing open"). Emily's
  14 injected ids were largely **fail-open overrides while arms were
  uninformed**, not rows that cleared the gate on relevance. Once the
  shared bandit converged (arm 2, `arm_updates=8`), the gate began
  honoring 0.70 and dropped everything below it — the tail of s0 (trial
  9 → `unknown`) and all of s1.

**Mechanism:** both sessions share ONE `PolicyManager` for the kernel's
lifetime. s1 ran second and **inherited s0's converged arm**. alex's rows
all score < 0.70, so the converged gate correctly drops them → 0 injected
→ empty `memory_ids_involved` → `unknown`. This is the "second session
inherits the first's converged arm" hypothesis, confirmed in the log.

This refines (and partly corrects) the pilot report's softer note
("retrieval-time outcome, not write loss"): directionally right, but the
specific cause is **cross-session bandit convergence starving the later
session**, combined with the observation that the *early* session's
injections were fail-open-driven, not relevance-driven.

Two implications this raises (both for the larger run to resolve, not
resolved here):
- The observed sub-0.70 similarities are the same embedding-space
  calibration caveat noted throughout: real distinct memories score
  ~0.45–0.65, so a converged 0.70 arm rejects most of them. Whether 0.70
  is even a *good* converged value is unknown at N=20.
- If most post-convergence trials wipe out and only fail-open-era trials
  inject, the reward signal is dominated by fail-open overrides — which
  is fine for *proving closure* but means the bandit is partly learning
  from rows it was forced to keep, not rows it chose to keep. The larger
  run must be able to tell these apart (see §4).

## 3. The two carried simplifications — do they threaten a larger run?

**(a) Equal-split reward attribution** (flagged before this work began):
the trial reward is split evenly across all decisions credited in the
call. Assessment for the larger run: **acceptable to carry forward, with
one caveat.** It conserves per-trial signal and is unbiased across arms;
it does not distort *whether* arms move. It does blur *which* gate earned
the reward when similarity + redundancy co-fire on the same trial (they
always do), so per-gate credit is not cleanly separable. For a run whose
goal is "does the policy improve outcomes," that blur is tolerable; for a
run trying to attribute improvement to a *specific* gate, it is not. State
the run's goal accordingly.

**(b) Soft per-arm gap** — `arm_update_count` counts ANY reward on an
arm, not specifically wipeout-rejection-validated ones. Assessment:
**acceptable to carry forward.** §2 actually exercised this path live
(arm 2 hit `arm_updates=8` and then honored wipeouts) with no misbehavior.
The residual risk (an arm trusted from non-wipeout trials then wiping out
on its first wipeout) did not manifest and remains a much softer edge
than the whole-bandit bug that was fixed. Watch it at larger N but do not
block on it.

Neither simplification blocks a larger run. Both should be **restated in
the larger run's writeup as known modeling choices**, not silently
assumed resolved.

## 4. Go/No-Go for the larger, properly-powered run

**GO — with conditions on design, not on the fix.** The fix chain is
sound: root cause correctly identified (retrieve-gate wipeout emptying
`memory_ids_involved`, not the originally-suspected owner_agent/harness
path), minimal fix implemented and correctly narrowed once (per-arm
bootstrap fail-open; static/tuned path untouched), in-process closure
confirmed, and live closure confirmed with real numbers. There is no
outstanding correctness blocker.

The conditions are about **experiment design**, driven by what §2
surfaced:

1. **Control for cross-session bandit convergence (the §2 finding).**
   With one shared `PolicyManager` per kernel lifetime, session order
   confounds per-session injection. The larger run must either:
   (a) **balance/randomize session order** across many sessions so no
   single persona is systematically the "first (bootstrap)" or "later
   (converged)" one; and/or (b) run enough sessions that early-bootstrap
   trials are a small fraction of the total. Do not draw per-persona
   conclusions from a design where one persona always runs first.

2. **Report fail-open branch counts per session as a standard metric,**
   not an ad hoc grep. Track, per session: # bootstrap-fail-open,
   # honoring-converged, # wipeouts, # non-empty `memory_ids_involved`.
   This is the metric that made §2 legible; it should be first-class so
   the larger run can immediately see whether reward is coming from
   fail-open overrides vs. genuine gate passes.

3. **Distinguish fail-open-injected from gate-passed injections** in the
   reward accounting. Because early-session reward is dominated by
   fail-open overrides (§2), a run that wants to claim the *policy* is
   improving retrieval must separate "rows the gate chose to keep" from
   "rows the fail-open forced it to keep." If that separation isn't
   instrumented, the run can still claim closure but not learning-quality.

4. **Re-examine the 0.70-era calibration at scale.** The converged arm
   (0.70) rejected most real memories (similarities ~0.45–0.65). The
   larger run should report the similarity distribution of retrieved rows
   vs. the converged arm so we can tell whether the policy is converging
   to a *useful* threshold or just a *high* one that starves retrieval.
   This is the known embedding-space calibration caveat; N=20 could not
   speak to it.

5. **Carry both simplifications (§3) into the writeup** as stated
   modeling choices, and set the run's attribution goal (policy-level vs.
   per-gate) explicitly given equal-split's blur.

**Not decided here:** the exact users × interactions × repeats and
model/budget of the larger run — that is the earlier /dev-task-planner
scope to resume, now informed by conditions 1–5. This synthesis unblocks
that planning; it does not fix its parameters.

## 5. Honest bottom line

The reward loop is closed and demonstrably functional on a live kernel —
the original goal of the whole investigation is met. The one live
surprise (emily/alex asymmetry) turned out to be **explained, not
mysterious**: shared-bandit convergence across sessions plus fail-open-
driven early injections. That explanation is itself the most important
input to the larger run's design (conditions 1–3). Nothing found here
requires further code changes or another small pilot; it requires a
properly-powered run built to control for session order and to report
fail-open provenance as a first-class metric.
