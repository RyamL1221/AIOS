"""
Verification probe for the judge-reward normalization fix.

WHAT THIS PROVES (and why it exists):
Before the fix, MemoryManager.report_reward forwarded the RAW judge
reward (1--5 scale) straight into LinUCBBandit.update. At alpha=1.0 with
this module's context geometry (x·x = 3), an unexplored arm's UCB bonus
is ≈ 1.7, so a raw reward of up to 5.0 swamped the bonus and the bandit
degenerated to "always picks arm 0 / never learns". The fix normalizes
the reward by JUDGE_MAX_SCORE (5.0) inside PolicyManager.update so the
reward magnitude is comparable to the exploration bonus.

This probe drives the REAL, patched PolicyManager (imported, not mocked
on the select/update path) through a realistic online loop and checks
the fix on the two required axes:

  Axis 1 — Exploration: across all three bandits, arms OTHER than arm 0
           are selected (the bug symptom was arm 0 forever).
  Axis 2 — Context-sensitivity: under distinct (llm, task_type)
           contexts, each with a DIFFERENT designed best-arm, the
           bandit's converged argmax tracks that per-context best arm —
           i.e. the choice follows the reward signal, not just noise.

Standalone, no kernel server / Ollama / provider needed (the bandits are
pure numpy). Run:

    .venv/bin/python scripts/verify_reward_normalization_probe.py

This is a throwaway verification probe, not production code. It does not
run the full 450-trial evaluation — that is explicitly out of scope for
this subtask.
"""
from __future__ import annotations

import os
import sys
from collections import Counter

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from aios.memory.policy import (  # noqa: E402
    JUDGE_MAX_SCORE,
    PolicyManager,
)

# Deterministic synthetic feedback so the probe output is reproducible.
_RNG = np.random.default_rng(20260909)

# Iterations per (bandit, context) online loop. 50--80 per the plan.
N_ITERS = 70

# Three distinct contexts, each mapped (via the real one-hot family
# matching in build_context_vector) to a different llm/task combination.
# "integration" is not a KNOWN_TASK_TYPE so it lands in the task "other"
# slot — still a distinct context vector from "profile"/"task".
CONTEXTS = [
    ("gpt-4o", "profile"),
    ("llama3.1:8b", "task"),
    ("qwen2.5:7b", "integration"),
]


def _synthetic_reward(arm_index: int, best_arm: int) -> float:
    """Return a synthetic judge reward on the confirmed 1--5 scale.

    The designed "best" arm draws a high reward (mean ~4.6), every other
    arm draws a low reward (mean ~1.6). Gaussian noise with clipping to
    [1, 5] simulates realistic, noisy trial feedback rather than a clean
    step signal.
    """
    if arm_index == best_arm:
        r = _RNG.normal(4.6, 0.4)
    else:
        r = _RNG.normal(1.6, 0.4)
    return float(np.clip(r, 1.0, 5.0))


def _run_online_loop(pm, bandit_name, llm_core, task_type, best_arm):
    """One realistic online loop: select -> synthetic reward -> update.

    Returns (selection_counter, converged_argmax_arm). Nothing on the
    select/update path is mocked — the real patched PolicyManager makes
    every decision.
    """
    selections = Counter()
    for _ in range(N_ITERS):
        _value, arm_index, ctx = pm.select_threshold(
            bandit_name, llm_core, task_type
        )
        selections[arm_index] += 1
        reward = _synthetic_reward(arm_index, best_arm)
        # Pass the RAW 1--5 reward, exactly as MemoryManager.report_reward
        # does; normalization happens inside PolicyManager.update.
        pm.update(bandit_name, arm_index, ctx, reward)

    # After learning, the converged choice is the current argmax of the
    # bandit's scores for this context.
    scores = pm.arm_scores(bandit_name, llm_core, task_type)
    return selections, int(np.argmax(scores))


def _fmt_dist(counter, n_arms):
    """Format a per-arm selection distribution as 'arm:count'."""
    return "  ".join(
        f"arm{a}:{counter.get(a, 0)}" for a in range(n_arms)
    )


def main() -> int:
    print("=" * 68)
    print("Reward-normalization verification probe")
    print(f"JUDGE_MAX_SCORE = {JUDGE_MAX_SCORE}   alpha = 1.0   "
          f"iters/context = {N_ITERS}")
    print("=" * 68)

    bandit_names = list(PolicyManager.ACTION_SPACES.keys())

    # --- Axis 1: exploration (aggregate distribution per bandit) -----
    # A fresh manager per bandit, single fixed context, best arm chosen
    # to be NON-ZERO so "arm 0 forever" would be an obvious failure.
    print("\n[Axis 1] Exploration — per-bandit arm distribution")
    print("         (single context gpt-4o/profile; designed best arm "
          "is non-zero)\n")
    axis1_pass = True
    for name in bandit_names:
        n_arms = len(PolicyManager.ACTION_SPACES[name])
        best_arm = n_arms - 2  # deliberately not arm 0
        pm = PolicyManager(alpha=1.0)
        selections, converged = _run_online_loop(
            pm, name, "gpt-4o", "profile", best_arm
        )
        distinct_arms = len([a for a, c in selections.items() if c > 0])
        non_zero_selected = sum(
            c for a, c in selections.items() if a != 0
        )
        ok = non_zero_selected > 0 and distinct_arms >= 2
        axis1_pass = axis1_pass and ok
        print(f"  {name:22s} n_arms={n_arms}")
        print(f"    dist:      {_fmt_dist(selections, n_arms)}")
        print(f"    distinct arms explored: {distinct_arms} | "
              f"non-arm0 selections: {non_zero_selected} | "
              f"designed best arm: {best_arm} | "
              f"converged argmax: {converged}")
        print(f"    -> {'PASS' if ok else 'FAIL'} "
              f"(arms other than 0 chosen)\n")

    # --- Axis 2: context-sensitivity --------------------------------
    # ONE manager per bandit, shared across 3 contexts, each context
    # given a DIFFERENT designed best arm. Confirm the converged argmax
    # per context tracks that context's designed best arm.
    print("[Axis 2] Context-sensitivity — converged argmax must track "
          "the per-context designed best arm\n")
    axis2_pass = True
    for name in bandit_names:
        n_arms = len(PolicyManager.ACTION_SPACES[name])
        # Distinct best arm per context (spread across the arm range,
        # all non-trivially different from each other).
        designed = {
            CONTEXTS[0]: 1,
            CONTEXTS[1]: n_arms // 2,
            CONTEXTS[2]: n_arms - 1,
        }
        pm = PolicyManager(alpha=1.0)
        # Interleave the three contexts so no single context's learning
        # is favored by ordering.
        loops = {ctx: [] for ctx in CONTEXTS}
        for _ in range(N_ITERS):
            for (llm_core, task_type) in CONTEXTS:
                best_arm = designed[(llm_core, task_type)]
                _v, arm_index, ctx_vec = pm.select_threshold(
                    name, llm_core, task_type
                )
                loops[(llm_core, task_type)].append(arm_index)
                reward = _synthetic_reward(arm_index, best_arm)
                pm.update(name, arm_index, ctx_vec, reward)

        print(f"  {name:22s} n_arms={n_arms}")
        per_ctx_ok = True
        converged_by_ctx = {}
        for (llm_core, task_type) in CONTEXTS:
            best_arm = designed[(llm_core, task_type)]
            scores = pm.arm_scores(name, llm_core, task_type)
            converged = int(np.argmax(scores))
            converged_by_ctx[(llm_core, task_type)] = converged
            sel = Counter(loops[(llm_core, task_type)])
            hit = converged == best_arm
            per_ctx_ok = per_ctx_ok and hit
            print(f"    ctx {llm_core:12s}/{task_type:11s} "
                  f"designed_best={best_arm} converged={converged} "
                  f"{'OK' if hit else 'MISS'}")
            print(f"        dist: {_fmt_dist(sel, n_arms)}")
        # Also confirm the converged arms genuinely DIFFER across
        # contexts (otherwise a single global winner could accidentally
        # match one context).
        distinct_converged = len(set(converged_by_ctx.values()))
        differ = distinct_converged >= 2
        ok = per_ctx_ok and differ
        axis2_pass = axis2_pass and ok
        print(f"    distinct converged arms across contexts: "
              f"{distinct_converged} "
              f"-> {'PASS' if ok else 'FAIL'}\n")

    print("=" * 68)
    print(f"Axis 1 (exploration):        "
          f"{'PASS' if axis1_pass else 'FAIL'}")
    print(f"Axis 2 (context-sensitivity):"
          f"{'PASS' if axis2_pass else 'FAIL'}")
    print("=" * 68)
    return 0 if (axis1_pass and axis2_pass) else 1


if __name__ == "__main__":
    raise SystemExit(main())
