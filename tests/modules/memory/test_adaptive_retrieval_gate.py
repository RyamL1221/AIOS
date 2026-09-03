"""
Tests for the adaptive retrieval gates + report_reward loop.

Subtask 6 wires ``retrieve_memory`` (the ``address_request``
retrieve branch) to two bandits behind the same
``memory.adaptive_policy.enabled`` flag, and completes the
``report_reward`` → ``PolicyManager.update`` loop.

Coverage:

(a) Flag OFF — retrieve returns the provider's results unchanged
    (same set/order/count); PolicyManager is never consulted.
(b) Flag ON — the ``similarity_threshold`` bandit is consulted and its
    value excludes a low-similarity candidate.
(c) Flag ON — the ``redundancy_threshold`` bandit drops a near-duplicate
    result (keeping the higher-ranked one).
(d) report_reward end-to-end — a flag-on retrieval records decisions;
    report_reward updates the correct bandits/arms for the involved
    memory_ids and cleans up the pending-decision entries.

Managers are built via ``__new__`` + manual wiring (no ConfigManager /
provider factory / scheduler). ``_pairwise_cosine`` is monkeypatched to
a deterministic content-based stub so the redundancy test needs no
embedding model.

Run standalone:

    python tests/modules/memory/test_adaptive_retrieval_gate.py
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

from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from aios.memory.manager import MemoryManager
from aios.memory.write_barrier import MemoryWriteBarrier
from aios.syscall.memory import MemorySyscall


class FakeProvider:
    """Provider double returning a fixed search_results list."""

    def __init__(self, search_results):
        self._results = search_results

    def retrieve_memory(self, query):
        # Return a fresh copy so the manager can mutate freely.
        return MemoryResponse(
            success=True,
            search_results=[dict(r) for r in self._results],
        )

    def retrieve_memory_raw(self, query):
        return []


def _make_manager(adaptive_enabled, provider, alpha=1.0):
    m = MemoryManager.__new__(MemoryManager)
    m.log_mode = "console"
    m._known_user_ids = OrderedDict()
    m.provider = provider
    m.barrier = MemoryWriteBarrier(config={"enabled": False})
    m._adaptive_enabled = adaptive_enabled
    m._latest_llm_core = "qwen2.5:7b"
    m._pending_reward_decisions = {}
    m.policy = None
    if adaptive_enabled:
        from aios.memory.policy import PolicyManager
        m.policy = PolicyManager(alpha=alpha)
    return m


def _retrieve_syscall(content="q", user_id="alex", k=10):
    q = MemoryQuery(
        operation_type="retrieve_memory",
        params={"content": content, "k": k, "user_id": user_id},
    )
    return MemorySyscall("AssistantAgent", q)


def _force_thresholds(m, sim=None, red=None):
    """Monkeypatch policy.select_threshold to force deterministic
    thresholds while returning real context vectors/arms. Returns a
    list recording (bandit_name,) calls."""
    calls = []
    real = m.policy.select_threshold

    forced = {"similarity_threshold": sim, "redundancy_threshold": red}

    def spy(bandit_name, llm_core, task_type):
        value, arm, ctx = real(bandit_name, llm_core, task_type)
        calls.append(bandit_name)
        override = forced.get(bandit_name)
        if override is not None:
            return override, arm, ctx
        return value, arm, ctx

    m.policy.select_threshold = spy
    return calls


class FlagOffRetrieveRegressionTest(unittest.TestCase):
    def test_results_unchanged_when_disabled(self) -> None:
        results = [
            {"memory_id": "a", "content": "alpha", "similarity": 0.9},
            {"memory_id": "b", "content": "beta", "similarity": 0.1},
            {"memory_id": "c", "content": "alpha", "similarity": 0.85},
        ]
        m = _make_manager(adaptive_enabled=False,
                          provider=FakeProvider(results))
        resp = m.address_request(_retrieve_syscall())
        # Identical set / order / count to the provider's output —
        # low-sim 'b' and duplicate 'c' are NOT filtered when off.
        self.assertEqual(
            [r["memory_id"] for r in resp.search_results],
            ["a", "b", "c"],
        )
        self.assertIsNone(m.policy)
        self.assertEqual(m._pending_reward_decisions, {})


class FlagOnSimilarityGateTest(unittest.TestCase):
    def test_low_similarity_candidate_excluded(self) -> None:
        results = [
            {"memory_id": "a", "content": "alpha", "similarity": 0.9},
            {"memory_id": "b", "content": "beta", "similarity": 0.2},
        ]
        m = _make_manager(adaptive_enabled=True,
                          provider=FakeProvider(results))
        # Force similarity threshold 0.5, redundancy 0.99 (no dedup).
        calls = _force_thresholds(m, sim=0.5, red=0.99)
        # Avoid loading an embedding model in this test.
        m._pairwise_cosine = lambda a, b: 0.0

        resp = m.address_request(_retrieve_syscall())
        ids = [r["memory_id"] for r in resp.search_results]
        # 'b' (sim 0.2 < 0.5) dropped; 'a' (0.9) kept.
        self.assertEqual(ids, ["a"])
        self.assertIn("similarity_threshold", calls)

    def test_threshold_value_is_decisive(self) -> None:
        results = [
            {"memory_id": "a", "content": "x", "similarity": 0.45},
        ]
        # threshold 0.5 > 0.45 -> dropped
        m1 = _make_manager(True, FakeProvider(results))
        _force_thresholds(m1, sim=0.5, red=0.99)
        m1._pairwise_cosine = lambda a, b: 0.0
        r1 = m1.address_request(_retrieve_syscall())
        self.assertEqual(r1.search_results, [])
        # threshold 0.4 < 0.45 -> kept
        m2 = _make_manager(True, FakeProvider(results))
        _force_thresholds(m2, sim=0.4, red=0.99)
        m2._pairwise_cosine = lambda a, b: 0.0
        r2 = m2.address_request(_retrieve_syscall())
        self.assertEqual(
            [r["memory_id"] for r in r2.search_results], ["a"]
        )


class FlagOnRedundancyGateTest(unittest.TestCase):
    def test_near_duplicate_dropped(self) -> None:
        results = [
            {"memory_id": "a", "content": "the user likes python",
             "similarity": 0.9},
            {"memory_id": "b", "content": "the user likes python",
             "similarity": 0.85},  # near-duplicate of a
            {"memory_id": "c", "content": "the user drinks coffee",
             "similarity": 0.8},
        ]
        m = _make_manager(True, FakeProvider(results))
        # sim threshold low (keep all), redundancy 0.8.
        _force_thresholds(m, sim=0.0, red=0.8)
        # Deterministic pairwise: identical content -> 1.0 else 0.0.
        m._pairwise_cosine = (
            lambda x, y: 1.0 if x == y else 0.0
        )
        resp = m.address_request(_retrieve_syscall())
        ids = [r["memory_id"] for r in resp.search_results]
        # 'b' is a duplicate of 'a' (pairwise 1.0 > 0.8) -> dropped.
        # 'a' (higher-ranked) and 'c' (distinct) survive, order kept.
        self.assertEqual(ids, ["a", "c"])


class ReportRewardLoopTest(unittest.TestCase):
    def test_retrieve_then_report_reward_updates_and_cleans_up(
        self,
    ) -> None:
        results = [
            {"memory_id": "a", "content": "alpha", "similarity": 0.9},
            {"memory_id": "b", "content": "beta", "similarity": 0.8},
        ]
        m = _make_manager(True, FakeProvider(results))
        _force_thresholds(m, sim=0.0, red=0.99)  # keep both
        m._pairwise_cosine = lambda a, b: 0.0

        resp = m.address_request(_retrieve_syscall())
        kept = [r["memory_id"] for r in resp.search_results]
        self.assertEqual(kept, ["a", "b"])

        # Each surviving memory recorded 2 decisions (similarity +
        # redundancy).
        for mid in ("a", "b"):
            self.assertIn(mid, m._pending_reward_decisions)
            self.assertEqual(len(m._pending_reward_decisions[mid]), 2)

        # Spy on policy.update to verify the reward loop.
        updates = []
        real_update = m.policy.update

        def update_spy(bandit_name, arm_index, ctx, reward):
            updates.append((bandit_name, arm_index, reward))
            return real_update(bandit_name, arm_index, ctx, reward)

        m.policy.update = update_spy

        m.report_reward(["a", "b"], 1.0, {"trial": "t1"})

        # 2 memories x 2 bandit decisions each = 4 updates, all with
        # the full reward (naive equal-credit, not split).
        self.assertEqual(len(updates), 4)
        for _, _, reward in updates:
            self.assertEqual(reward, 1.0)
        bandits_updated = {u[0] for u in updates}
        self.assertEqual(
            bandits_updated,
            {"similarity_threshold", "redundancy_threshold"},
        )

        # Cleanup: consumed entries removed.
        self.assertEqual(m._pending_reward_decisions, {})

    def test_report_reward_unknown_memory_id_noop(self) -> None:
        m = _make_manager(True, FakeProvider([]))
        # No decisions recorded; must not raise and must update nothing.
        updates = []
        m.policy.update = (
            lambda *a, **k: updates.append(a)
        )
        m.report_reward(["ghost"], 1.0, {})
        self.assertEqual(updates, [])
        self.assertEqual(m._pending_reward_decisions, {})

    def test_report_reward_noop_when_disabled(self) -> None:
        m = _make_manager(adaptive_enabled=False,
                          provider=FakeProvider([]))
        # policy is None; must be a safe no-op.
        m.report_reward(["a"], 1.0, {})  # should not raise
        self.assertIsNone(m.policy)


if __name__ == "__main__":
    unittest.main(verbosity=2)
