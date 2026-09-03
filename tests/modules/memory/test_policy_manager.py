"""
Unit tests for the standalone PolicyManager / LinUCBBandit.

Proves the learning mechanism in isolation (no MemoryManager, config,
or scheduler): the bandits explore every arm at init, actually learn
from reward, and the select/update round-trip works for all three
managed bandits.

Run standalone:

    python tests/modules/memory/test_policy_manager.py
"""
from __future__ import annotations

import os
import sys
import unittest

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from aios.memory.policy import (
    CONTEXT_DIM,
    LinUCBBandit,
    PolicyManager,
    build_context_vector,
)


class ContextVectorTest(unittest.TestCase):
    """The context vector is deterministic and fixed-length."""

    def test_deterministic_and_fixed_length(self) -> None:
        v1 = build_context_vector("qwen2.5:7b", "profile")
        v2 = build_context_vector("qwen2.5:7b", "profile")
        self.assertEqual(v1.shape[0], CONTEXT_DIM)
        np.testing.assert_array_equal(v1, v2)

    def test_families_map_and_unknown_falls_through(self) -> None:
        qwen = build_context_vector("qwen3:4b", "task")
        llama = build_context_vector("llama3.1:8b", "task")
        gpt = build_context_vector("gpt-4o", "task")
        unknown = build_context_vector("mistral-7b", "task")
        # Different known families -> different vectors.
        self.assertFalse(np.array_equal(qwen, llama))
        self.assertFalse(np.array_equal(llama, gpt))
        # Unknown llm still yields a valid fixed-length vector with
        # exactly one hot slot in the llm block ("other").
        self.assertEqual(unknown.shape[0], CONTEXT_DIM)
        self.assertEqual(unknown[:4].sum(), 1.0)  # llm one-hot block

    def test_unknown_task_falls_through(self) -> None:
        # Use a task label that does not contain the substrings
        # "profile" or "task" (matching is substring-based so that
        # "qwen2.5:7b" maps to the "qwen" family).
        v = build_context_vector("qwen2.5:7b", "summarize")
        # task block is slots [4:7] (profile, task, other) -> one hot.
        self.assertEqual(v[4:7].sum(), 1.0)
        self.assertEqual(v[6], 1.0)  # "other" task slot


class LinUCBBanditTest(unittest.TestCase):
    """LinUCBBandit explores at init and learns from reward."""

    def setUp(self) -> None:
        self.actions = [0.1, 0.2, 0.3, 0.4, 0.5]
        self.bandit = LinUCBBandit(
            actions=self.actions,
            context_dim=CONTEXT_DIM,
            alpha=1.0,
        )
        self.ctx = build_context_vector("qwen2.5:7b", "profile")

    def test_no_arm_starved_at_init(self) -> None:
        # With random contexts and zero learning, exploration should
        # surface every arm at least once. Use a fixed seed for
        # reproducibility.
        rng = np.random.default_rng(0)
        selected = set()
        for _ in range(200):
            # Random but valid one-hot-ish contexts.
            ctx = build_context_vector(
                rng.choice(["qwen2.5:7b", "llama3.1:8b", "gpt-4o"]),
                rng.choice(["profile", "task"]),
            )
            _, arm_index = self.bandit.select_arm(ctx)
            selected.add(arm_index)
            # Give each pulled arm a small random reward so A/b evolve
            # and exploration continues to rotate arms.
            self.bandit.update(
                arm_index, ctx, float(rng.random())
            )
        self.assertEqual(
            selected,
            set(range(len(self.actions))),
            f"some arms never selected: "
            f"{set(range(len(self.actions))) - selected}",
        )

    def test_learns_preferred_arm(self) -> None:
        # Repeatedly reward arm 2 highly and others with 0 for a FIXED
        # context; arm 2's LinUCB score for that context must end up
        # strictly highest (mechanism learns, not stuck at init).
        target = 2
        for _ in range(50):
            for arm in range(len(self.actions)):
                reward = 1.0 if arm == target else 0.0
                self.bandit.update(arm, self.ctx, reward)

        scores = self.bandit.arm_scores(self.ctx)
        self.assertEqual(
            int(np.argmax(scores)),
            target,
            f"expected arm {target} to win; scores={scores}",
        )
        # And its mean-reward estimate should dominate: selecting under
        # this context returns the target action.
        value, arm_index = self.bandit.select_arm(self.ctx)
        self.assertEqual(arm_index, target)
        self.assertEqual(value, self.actions[target])

    def test_reward_raises_target_mean_relative_to_others(self) -> None:
        # The learning signal is the exploitation term (mean estimate),
        # NOT the total UCB score. (In LinUCB a freshly-rewarded arm's
        # *total* score can fall below untried arms because rewarding
        # it shrinks its exploration bonus — that is intended optimism.)
        # So we assert the rewarded arm's MEAN rises relative to a
        # never-rewarded arm for the same context.
        target, other = 1, 3
        before = self.bandit.arm_mean_estimates(self.ctx)
        gap_before = before[target] - before[other]
        for _ in range(30):
            self.bandit.update(target, self.ctx, 1.0)
        after = self.bandit.arm_mean_estimates(self.ctx)
        gap_after = after[target] - after[other]
        self.assertGreater(gap_after, gap_before)
        # Concretely: target's mean climbs toward the reward (1.0),
        # the untouched arm's mean stays at its initial 0.
        self.assertGreater(after[target], before[target])
        self.assertEqual(after[other], 0.0)

    def test_invalid_context_dim_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.bandit.select_arm(np.zeros(CONTEXT_DIM + 1))

    def test_bad_construction_raises(self) -> None:
        with self.assertRaises(ValueError):
            LinUCBBandit(actions=[], context_dim=CONTEXT_DIM)
        with self.assertRaises(ValueError):
            LinUCBBandit(actions=[0.1], context_dim=0)
        with self.assertRaises(ValueError):
            LinUCBBandit(actions=[0.1], context_dim=CONTEXT_DIM, alpha=-1)


class PolicyManagerTest(unittest.TestCase):
    """PolicyManager wires three bandits with a uniform API."""

    def setUp(self) -> None:
        self.pm = PolicyManager(alpha=1.0)

    def test_three_bandits_present(self) -> None:
        self.assertEqual(
            set(self.pm.bandit_names),
            {
                "novelty_threshold",
                "similarity_threshold",
                "redundancy_threshold",
            },
        )

    def test_select_returns_valid_action_from_space(self) -> None:
        for name in self.pm.bandit_names:
            value, arm_index, ctx = self.pm.select_threshold(
                name, "qwen2.5:7b", "profile"
            )
            self.assertIn(value, PolicyManager.ACTION_SPACES[name])
            self.assertEqual(
                value,
                PolicyManager.ACTION_SPACES[name][arm_index],
            )
            self.assertEqual(ctx.shape[0], CONTEXT_DIM)

    def test_select_update_round_trip_all_bandits(self) -> None:
        # For each bandit, run a full select -> update -> re-select
        # loop and confirm the manager learns to pick the rewarded arm.
        #
        # To make the target win on the *total* UCB score (not just its
        # mean), every arm must be explored so no untried arm retains
        # pure initialization optimism. We reward the target arm with
        # +1 and give every other arm -1, all under the same context.
        for name in self.pm.bandit_names:
            _, target, ctx = self.pm.select_threshold(
                name, "llama3.1:8b", "task"
            )
            n_arms = len(PolicyManager.ACTION_SPACES[name])
            for _ in range(40):
                for arm in range(n_arms):
                    reward = 1.0 if arm == target else -1.0
                    self.pm.update(name, arm, ctx, reward)

            scores = self.pm.arm_scores(name, "llama3.1:8b", "task")
            self.assertEqual(
                int(np.argmax(scores)),
                target,
                f"{name}: expected arm {target}, scores={scores}",
            )
            # Round-trip closes: a fresh selection returns the target
            # action value.
            value, arm_index, _ = self.pm.select_threshold(
                name, "llama3.1:8b", "task"
            )
            self.assertEqual(arm_index, target)
            self.assertEqual(
                value, PolicyManager.ACTION_SPACES[name][target]
            )

    def test_unknown_bandit_name_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.pm.select_threshold("nope", "qwen2.5:7b", "task")

    def test_bandits_are_independent(self) -> None:
        # Updating one bandit must not affect another's scores.
        ctx_args = ("qwen2.5:7b", "profile")
        before = self.pm.arm_scores("similarity_threshold", *ctx_args)
        _, arm_index, ctx = self.pm.select_threshold(
            "novelty_threshold", *ctx_args
        )
        for _ in range(20):
            self.pm.update("novelty_threshold", arm_index, ctx, 1.0)
        after = self.pm.arm_scores("similarity_threshold", *ctx_args)
        np.testing.assert_array_equal(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
