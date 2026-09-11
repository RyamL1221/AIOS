"""Regression tests for the *narrowed* similarity-gate fail-open.

The similarity gate's total-wipeout fail-open must fire ONLY while the
``similarity_threshold`` bandit is still bootstrapping (no / too-few
reward updates), so an over-aggressive initial arm cannot starve its own
learning. Once the bandit has real learning signal, a converged strict
arm MUST be allowed to reject everything again (the gate's ceiling is
restored). The static (kernel_shared_tuned) path must be UNTOUCHED — it
calls _filter_by_similarity directly and never sees the fail-open.

Cases proven here:
  1. BOOTSTRAP: update_count = 0, every row below the chosen threshold
     -> fail open (full set kept) so >=1 creditable id reaches reward.
  2. CONVERGED: update_count >= BOOTSTRAP_MIN_UPDATES, every row below
     the chosen threshold -> returns EMPTY (strict rejection honored).
  3. PARTIAL (any state): a mix above/below threshold -> only the
     below-threshold rows are dropped (never triggers fail-open).
  4. STATIC PATH: _filter_by_similarity itself never fail-opens on a
     total wipeout (returns []), so kernel_shared_tuned is unaffected.

Run standalone (needs the cerebrum SDK from the venv):

    .venv/bin/python tests/modules/memory/test_bootstrap_failopen.py
"""
from __future__ import annotations

import os
import sys
import unittest
from collections import OrderedDict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cerebrum.memory.apis import MemoryQuery

from aios.memory.manager import MemoryManager
from aios.memory.policy import PolicyManager, build_context_vector


LLM = "gpt-4o"
TASK = "profile"


def _make_adaptive_manager():
    """MemoryManager on the adaptive path with a real PolicyManager,
    no ConfigManager / provider factory."""
    m = MemoryManager.__new__(MemoryManager)
    m.log_mode = "console"
    m._known_user_ids = OrderedDict()
    m.provider = None
    m._adaptive_enabled = True
    m._static_thresholds_enabled = False
    m._latest_llm_core = LLM
    m._pending_reward_decisions = {}
    m.policy_logger = None
    m.policy = PolicyManager(alpha=1.0)
    return m


def _query():
    return MemoryQuery(
        operation_type="retrieve_memory",
        params={
            "content": "what should I work on next?",
            "k": 20,
            "user_id": "u1",
            "memory_type": TASK,
        },
    )


def _rows_all_below(threshold):
    """Result rows whose similarity is strictly below *threshold*
    (so the gate would drop all of them)."""
    return [
        {"memory_id": "a", "content": "profile row", "similarity": threshold - 0.03},
        {"memory_id": "b", "content": "task row", "similarity": threshold - 0.10},
    ]


def _force_similarity_arm(m, threshold, arm):
    """Pin the similarity_threshold selection to a fixed (threshold,
    arm) so the per-arm fail-open gate can be tested deterministically
    without depending on LinUCB's (state-dependent) argmax. Redundancy
    is forced high so it never drops anything. Uses the real context
    vector for *arm* so arm_update_count / decision recording line up.
    Also stubs _pairwise_cosine to avoid loading an embedding model."""
    ctx = build_context_vector(LLM, TASK)
    real = m.policy.select_threshold

    def spy(bandit_name, llm_core, task_type):
        if bandit_name == "similarity_threshold":
            return threshold, arm, ctx
        if bandit_name == "redundancy_threshold":
            return 0.99, 0, ctx
        return real(bandit_name, llm_core, task_type)

    m.policy.select_threshold = spy
    m._pairwise_cosine = lambda a, b: 0.0
    return ctx


class BootstrapFailOpenTest(unittest.TestCase):

    def _chosen_threshold(self, m):
        """The similarity_threshold the bandit will pick for this ctx."""
        thr, _arm, _ctx = m.policy.select_threshold(
            "similarity_threshold", LLM, TASK
        )
        return thr

    def test_bootstrap_fails_open_when_no_updates(self):
        """update_count == 0: total wipeout -> keep full set."""
        m = _make_adaptive_manager()
        self.assertEqual(
            m.policy.update_count("similarity_threshold"), 0
        )
        thr = self._chosen_threshold(m)
        rows = _rows_all_below(thr)  # sims below the selected arm
        # Isolate the SIMILARITY fail-open (the behavior under test):
        # neutralize the redundancy gate so it can't independently drop
        # rows. Since redundancy now floors at 0.1, a fresh bandit can
        # select a low redundancy arm and collapse these two distinct
        # rows as "near-duplicates" (pairwise > 0.1) — that's the
        # redundancy gate working, not a similarity-fail-open failure.
        # Stub pairwise sim to 0.0 so nothing is redundant here.
        m._pairwise_cosine = lambda a, b: 0.0
        out = m._apply_retrieval_policy(rows, _query())
        # Fail-open: all rows survive the similarity gate.
        self.assertEqual(len(out), len(rows))
        surviving_ids = {r["memory_id"] for r in out}
        self.assertEqual(surviving_ids, {"a", "b"})
        # And a similarity decision was recorded so reward can flow.
        self.assertTrue(
            any(
                any(d[0] == "similarity_threshold" for d in decs)
                for decs in m._pending_reward_decisions.values()
            )
        )

    def test_converged_high_arm_rejects_everything(self):
        """update_count >= BOOTSTRAP_MIN_UPDATES: total wipeout ->
        return EMPTY (strict rejection honored)."""
        m = _make_adaptive_manager()
        # Pin the gate to a specific high arm (0.90) and validate THAT
        # arm (>= BOOTSTRAP_MIN_UPDATES reward updates on it).
        arm = m.policy.ACTION_SPACES["similarity_threshold"].index(0.90)
        ctx = _force_similarity_arm(m, threshold=0.90, arm=arm)
        for _ in range(max(MemoryManager.BOOTSTRAP_MIN_UPDATES, 3)):
            m.policy.update("similarity_threshold", arm, ctx, 5.0)
        self.assertGreaterEqual(
            m.policy.arm_update_count("similarity_threshold", arm),
            MemoryManager.BOOTSTRAP_MIN_UPDATES,
        )
        rows = _rows_all_below(0.90)
        out = m._apply_retrieval_policy(rows, _query())
        # Converged: the SELECTED arm is validated -> strict rejection
        # honored -> empty.
        self.assertEqual(out, [])
        # No similarity decision recorded (nothing survived to credit).
        self.assertEqual(m._pending_reward_decisions, {})

    def test_sibling_arm_reward_does_not_disarm_untested_arm(self):
        """Per-arm regression (the whole-bandit gap this fix closes):
        rewarding arm X must NOT turn off the fail-open for a DIFFERENT,
        still-untested arm Y that the gate selects and that causes a
        wipeout. Whole-bandit semantics would wrongly return empty here
        (its total > 0); per-arm keeps failing open because Y itself is
        unvalidated."""
        m = _make_adaptive_manager()
        # The gate will select arm Y = 0.90 (pinned), which is untested.
        arm_y = m.policy.ACTION_SPACES["similarity_threshold"].index(0.90)
        ctx = _force_similarity_arm(m, threshold=0.90, arm=arm_y)
        # Reward a DIFFERENT arm X several times, leaving Y at zero.
        arm_x = m.policy.ACTION_SPACES["similarity_threshold"].index(0.50)
        for _ in range(3):
            m.policy.update("similarity_threshold", arm_x, ctx, 5.0)
        # Whole-bandit total is now > 0 ...
        self.assertGreater(
            m.policy.update_count("similarity_threshold"), 0
        )
        # ... but the SELECTED arm Y is still untested.
        self.assertEqual(
            m.policy.arm_update_count("similarity_threshold", arm_y), 0
        )
        rows = _rows_all_below(0.90)
        out = m._apply_retrieval_policy(rows, _query())
        # Per-arm: selected arm Y is unvalidated -> still fail open.
        self.assertEqual(len(out), len(rows))

    def test_partial_filter_never_triggers_failopen(self):
        """A mix above/below threshold drops only the below ones,
        regardless of update_count."""
        m = _make_adaptive_manager()
        thr = self._chosen_threshold(m)
        rows = [
            {"memory_id": "hi", "content": "x", "similarity": thr + 0.05},
            {"memory_id": "lo", "content": "y", "similarity": thr - 0.20},
        ]
        out = m._apply_retrieval_policy(rows, _query())
        ids = {r["memory_id"] for r in out}
        self.assertEqual(ids, {"hi"})

    def test_static_helper_does_not_failopen(self):
        """_filter_by_similarity (shared/static path) returns [] on a
        total wipeout — the static kernel_shared_tuned path is untouched
        by the bootstrap fail-open."""
        rows = [
            {"memory_id": "a", "content": "x", "similarity": 0.10},
            {"memory_id": "b", "content": "y", "similarity": 0.20},
        ]
        kept = MemoryManager._filter_by_similarity(rows, 0.50)
        self.assertEqual(kept, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
