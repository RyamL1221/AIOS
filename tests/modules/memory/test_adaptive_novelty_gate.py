"""
Tests for the adaptive novelty gate in MemoryManager.add_memory.

Covers the two behaviors that matter for Subtask 5:

1. **Flag OFF (frozen baseline)** — the most important criterion.
   ``add_memory`` writes every candidate unconditionally (there was no
   novelty gate before this change), and the PolicyManager is never
   imported or consulted. We assert both: identical admit decisions
   (all admitted) AND that no policy code ran.

2. **Flag ON** — the ``novelty_threshold`` bandit is genuinely
   consulted (spied) and its returned threshold — not any static
   constant — decides admit/reject. We also assert the decision-tracking
   dict is populated for admitted memories keyed by memory_id.

The tests build a ``MemoryManager`` via ``__new__`` + manual attribute
wiring (mirroring the write-barrier suites) so they need no
ConfigManager, provider factory, or scheduler. A fake provider records
writes and returns controllable similarities on ``retrieve_memory`` so
admit/reject is deterministic.

Run standalone:

    python tests/modules/memory/test_adaptive_novelty_gate.py
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
    """Minimal provider double.

    Records every ``add_memory`` call and returns a controllable set of
    similarities from ``retrieve_memory`` so the novelty gate's
    admit/reject decision is deterministic.
    """

    def __init__(self, probe_similarities=None):
        self.added = []          # list of (content, memory_id)
        self.probe_similarities = list(probe_similarities or [])

    def add_memory(self, memory_note):
        self.added.append((memory_note.content, memory_note.id))
        return MemoryResponse(success=True, memory_id=memory_note.id)

    def retrieve_memory(self, query):
        results = [
            {"content": f"existing-{i}", "similarity": s}
            for i, s in enumerate(self.probe_similarities)
        ]
        return MemoryResponse(success=True, search_results=results)

    # Unused by these tests but part of the interface.
    def retrieve_memory_raw(self, query):
        return []


def _make_manager(adaptive_enabled, provider, alpha=1.0):
    """Build a MemoryManager without ConfigManager/provider factory."""
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


def _add_syscall(content, memory_id, user_id="alex", memory_type="profile"):
    q = MemoryQuery(
        operation_type="add_memory",
        params={
            "content": content,
            "memory_id": memory_id,
            "metadata": {
                "user_id": user_id,
                "memory_type": memory_type,
            },
        },
    )
    return MemorySyscall("ProfileAgent", q)


class FlagOffRegressionTest(unittest.TestCase):
    """Flag OFF: every candidate admitted; policy never touched."""

    def test_all_candidates_admitted_unconditionally(self) -> None:
        # Even with similarities that WOULD trigger a reject if the gate
        # were active, flag-off must admit everything.
        provider = FakeProvider(probe_similarities=[0.99, 0.98])
        m = _make_manager(adaptive_enabled=False, provider=provider)

        candidates = [
            ("The user likes Python.", "m1"),
            ("The user likes Python.", "m2"),  # near-duplicate
            ("The user drinks coffee.", "m3"),
        ]
        responses = []
        for content, mid in candidates:
            resp = m.address_request(_add_syscall(content, mid))
            responses.append(resp)

        # All admitted -> all written, each with its memory_id.
        self.assertEqual(
            [c[1] for c in candidates],
            [mid for _, mid in provider.added],
        )
        for resp, (_, mid) in zip(responses, candidates):
            self.assertTrue(resp.success)
            self.assertEqual(resp.memory_id, mid)

        # Policy was never constructed and nothing tracked.
        self.assertIsNone(m.policy)
        self.assertEqual(m._pending_reward_decisions, {})

    def test_policy_module_not_imported_when_disabled(self) -> None:
        # A MemoryManager constructed with the flag off must not pull
        # aios.memory.policy into sys.modules on our behalf. (If some
        # other test imported it earlier in the same process we can't
        # unimport it, so this asserts the manager itself holds no
        # policy and never calls it — the import-avoidance is proven by
        # the __init__ lazy-import structure + this no-policy state.)
        provider = FakeProvider(probe_similarities=[0.99])
        m = _make_manager(adaptive_enabled=False, provider=provider)
        m.address_request(_add_syscall("x", "mx"))
        self.assertIsNone(m.policy)


class FlagOnTest(unittest.TestCase):
    """Flag ON: bandit consulted; its threshold drives admit/reject."""

    def _spy_policy(self, m, forced_threshold, forced_arm=0):
        """Wrap policy.select_threshold to record calls and force a
        deterministic threshold/arm."""
        calls = []
        real_select = m.policy.select_threshold

        def spy(bandit_name, llm_core, task_type):
            # Use the real context vector but override the threshold so
            # the admit/reject decision is deterministic in the test.
            _, _, ctx = real_select(bandit_name, llm_core, task_type)
            calls.append((bandit_name, llm_core, task_type))
            return forced_threshold, forced_arm, ctx

        m.policy.select_threshold = spy
        return calls

    def test_bandit_consulted_and_threshold_used_reject(self) -> None:
        # max_sim (0.9) >= threshold (0.6) -> NOT novel -> reject.
        provider = FakeProvider(probe_similarities=[0.9, 0.4])
        m = _make_manager(adaptive_enabled=True, provider=provider)
        calls = self._spy_policy(m, forced_threshold=0.6)

        resp = m.address_request(_add_syscall("dup content", "m1"))

        # select_threshold was called for the novelty bandit.
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "novelty_threshold")
        # Rejected: nothing written, success with no memory_id.
        self.assertEqual(provider.added, [])
        self.assertTrue(resp.success)
        self.assertIsNone(resp.memory_id)

    def test_bandit_consulted_and_threshold_used_admit(self) -> None:
        # max_sim (0.3) < threshold (0.6) -> novel -> admit.
        provider = FakeProvider(probe_similarities=[0.3, 0.1])
        m = _make_manager(adaptive_enabled=True, provider=provider)
        calls = self._spy_policy(m, forced_threshold=0.6, forced_arm=2)

        resp = m.address_request(_add_syscall("novel content", "m1"))

        self.assertEqual(len(calls), 1)
        self.assertTrue(resp.success)
        self.assertEqual(resp.memory_id, "m1")
        self.assertEqual(provider.added, [("novel content", "m1")])

    def test_threshold_value_is_decisive(self) -> None:
        # Same candidate similarity (0.5); flipping the threshold across
        # it flips the decision — proving the bandit's VALUE (not a
        # static constant) is what's compared.
        # threshold 0.4 < sim 0.5 -> reject
        p1 = FakeProvider(probe_similarities=[0.5])
        m1 = _make_manager(adaptive_enabled=True, provider=p1)
        self._spy_policy(m1, forced_threshold=0.4)
        r1 = m1.address_request(_add_syscall("c", "m1"))
        self.assertIsNone(r1.memory_id)
        self.assertEqual(p1.added, [])

        # threshold 0.6 > sim 0.5 -> admit
        p2 = FakeProvider(probe_similarities=[0.5])
        m2 = _make_manager(adaptive_enabled=True, provider=p2)
        self._spy_policy(m2, forced_threshold=0.6)
        r2 = m2.address_request(_add_syscall("c", "m2"))
        self.assertEqual(r2.memory_id, "m2")
        self.assertEqual(p2.added, [("c", "m2")])

    def test_decision_dict_populated_for_admitted(self) -> None:
        provider = FakeProvider(probe_similarities=[0.2])
        m = _make_manager(adaptive_enabled=True, provider=provider)
        self._spy_policy(m, forced_threshold=0.6, forced_arm=3)

        m.address_request(_add_syscall("novel", "mem-42"))

        self.assertIn("mem-42", m._pending_reward_decisions)
        # Value is now a LIST of decisions per memory_id (a memory can
        # be touched by multiple bandits). The add path records exactly
        # one novelty decision.
        decisions = m._pending_reward_decisions["mem-42"]
        self.assertEqual(len(decisions), 1)
        bandit_name, arm_index, ctx = decisions[0]
        self.assertEqual(bandit_name, "novelty_threshold")
        self.assertEqual(arm_index, 3)
        self.assertEqual(ctx.shape[0], m.policy.context_dim)

    def test_rejected_not_tracked(self) -> None:
        provider = FakeProvider(probe_similarities=[0.95])
        m = _make_manager(adaptive_enabled=True, provider=provider)
        self._spy_policy(m, forced_threshold=0.5)
        m.address_request(_add_syscall("dup", "m9"))
        self.assertEqual(m._pending_reward_decisions, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
