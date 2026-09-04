"""
Integration tests for the static (fixed/tuned) threshold gates wired
into MemoryManager.address_request.

Proves, with the same FakeProvider harness the adaptive-gate tests use:

* static_thresholds.enabled=True + adaptive_enabled=False gates
  add_memory using the resolved static novelty threshold (admit +
  reject cases), and filters retrieve_memory using the resolved
  similarity/redundancy thresholds;
* both flags False leaves add/retrieve byte-for-byte on the frozen
  baseline (spot-check);
* the static path touches NO bandit state (policy stays None, no
  pending reward decisions recorded);
* adaptive precedence: if both flags are True, the adaptive branch
  fires and the static branch does not.

Run standalone (needs the cerebrum SDK from the venv):

    .venv/bin/python tests/modules/memory/test_static_threshold_gate.py
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
    """Minimal provider double (mirrors the adaptive-gate tests)."""

    def __init__(self, probe_similarities=None, retrieve_results=None):
        self.added = []
        self.probe_similarities = list(probe_similarities or [])
        self._retrieve_results = retrieve_results

    def add_memory(self, memory_note):
        self.added.append((memory_note.content, memory_note.id))
        return MemoryResponse(success=True, memory_id=memory_note.id)

    def retrieve_memory(self, query):
        # When explicit retrieve results are configured, serve those
        # (used by the retrieve-gate tests). Otherwise synthesize from
        # probe_similarities (used by the novelty-probe path).
        if self._retrieve_results is not None:
            return MemoryResponse(
                success=True,
                search_results=list(self._retrieve_results),
            )
        results = [
            {"content": f"existing-{i}", "similarity": s}
            for i, s in enumerate(self.probe_similarities)
        ]
        return MemoryResponse(success=True, search_results=results)

    def retrieve_memory_raw(self, query):
        return []

    def sync_llm_from_query(self, llms):
        # Provider-side sync is a no-op for the double; present so
        # MemoryManager.sync_llm_from_query can delegate to it.
        pass


_STATIC_CFG = {
    "enabled": True,
    "novelty_threshold": {"default": 0.7, "overrides": []},
    "similarity_threshold": {"default": 0.5, "overrides": []},
    "redundancy_threshold": {"default": 0.8, "overrides": []},
}


def _make_manager(
    provider,
    static_enabled=False,
    adaptive_enabled=False,
    static_cfg=None,
):
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
    m._static_thresholds_enabled = static_enabled
    m._static_thresholds_config = static_cfg or dict(_STATIC_CFG)
    if adaptive_enabled:
        from aios.memory.policy import PolicyManager
        m.policy = PolicyManager(alpha=1.0)
    return m


def _add_syscall(content, memory_id, user_id="alex",
                 memory_type="profile"):
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


def _retrieve_syscall(user_id="alex", memory_type="profile"):
    q = MemoryQuery(
        operation_type="retrieve_memory",
        params={
            "content": "what does the user like?",
            "k": 5,
            "user_id": user_id,
            "memory_type": memory_type,
        },
    )
    return MemorySyscall("AssistantAgent", q)


class StaticNoveltyGateAddTest(unittest.TestCase):
    """Static novelty gate admits/rejects using the resolved value."""

    def test_admit_when_below_threshold(self) -> None:
        # max existing similarity 0.4 < default 0.7 -> novel -> admit.
        provider = FakeProvider(probe_similarities=[0.4, 0.3])
        m = _make_manager(provider, static_enabled=True)
        resp = m.address_request(_add_syscall("brand new fact", "m1"))
        self.assertTrue(resp.success)
        self.assertEqual(resp.memory_id, "m1")
        self.assertEqual([mid for _, mid in provider.added], ["m1"])

    def test_reject_when_at_or_above_threshold(self) -> None:
        # max existing similarity 0.95 >= default 0.7 -> not novel ->
        # reject: NOT written, success with memory_id=None.
        provider = FakeProvider(probe_similarities=[0.95, 0.2])
        m = _make_manager(provider, static_enabled=True)
        resp = m.address_request(_add_syscall("dup fact", "m2"))
        self.assertTrue(resp.success)
        self.assertIsNone(resp.memory_id)
        self.assertEqual(provider.added, [])

    def test_override_changes_threshold(self) -> None:
        # An override for (qwen2.5:7b, profile) lifts the threshold to
        # 0.99, so a 0.95-similar candidate now ADMITS.
        cfg = dict(_STATIC_CFG)
        cfg["novelty_threshold"] = {
            "default": 0.7,
            "overrides": [
                {"llm_core": "qwen2.5:7b", "task_type": "profile",
                 "value": 0.99},
            ],
        }
        provider = FakeProvider(probe_similarities=[0.95])
        m = _make_manager(provider, static_enabled=True, static_cfg=cfg)
        resp = m.address_request(_add_syscall("dup-ish", "m3"))
        self.assertEqual(resp.memory_id, "m3")

    def test_no_bandit_state_touched(self) -> None:
        provider = FakeProvider(probe_similarities=[0.4])
        m = _make_manager(provider, static_enabled=True)
        m.address_request(_add_syscall("fact", "m1"))
        self.assertIsNone(m.policy)
        self.assertEqual(m._pending_reward_decisions, {})


class StaticRetrieveGateTest(unittest.TestCase):
    """Static retrieve gates filter by similarity then redundancy."""

    def test_similarity_gate_drops_low_scores(self) -> None:
        results = [
            {"content": "a", "memory_id": "a", "similarity": 0.9},
            {"content": "b", "memory_id": "b", "similarity": 0.3},
            {"content": "c", "memory_id": "c", "similarity": 0.6},
        ]
        provider = FakeProvider(retrieve_results=results)
        m = _make_manager(provider, static_enabled=True)
        resp = m.address_request(_retrieve_syscall())
        kept_ids = [r["memory_id"] for r in resp.search_results]
        # default similarity_threshold=0.5 -> drop the 0.3 result.
        self.assertEqual(kept_ids, ["a", "c"])

    def test_redundancy_gate_drops_near_duplicates(self) -> None:
        # Two identical-content results survive similarity, then the
        # redundancy gate (pairwise cosine > 0.8) drops the second.
        results = [
            {"content": "The user likes Python programming.",
             "memory_id": "a", "similarity": 0.9},
            {"content": "The user likes Python programming.",
             "memory_id": "b", "similarity": 0.85},
            {"content": "Completely unrelated: weather is sunny.",
             "memory_id": "c", "similarity": 0.7},
        ]
        provider = FakeProvider(retrieve_results=results)
        m = _make_manager(provider, static_enabled=True)
        resp = m.address_request(_retrieve_syscall())
        kept_ids = [r["memory_id"] for r in resp.search_results]
        self.assertIn("a", kept_ids)
        self.assertNotIn("b", kept_ids)  # dropped as redundant with a
        self.assertIn("c", kept_ids)

    def test_no_bandit_state_touched(self) -> None:
        results = [
            {"content": "a", "memory_id": "a", "similarity": 0.9},
        ]
        provider = FakeProvider(retrieve_results=results)
        m = _make_manager(provider, static_enabled=True)
        m.address_request(_retrieve_syscall())
        self.assertIsNone(m.policy)
        self.assertEqual(m._pending_reward_decisions, {})


class BothFlagsOffBaselineTest(unittest.TestCase):
    """Both flags False: frozen baseline, no gating at all."""

    def test_add_admits_everything(self) -> None:
        provider = FakeProvider(probe_similarities=[0.99, 0.99])
        m = _make_manager(
            provider, static_enabled=False, adaptive_enabled=False
        )
        for content, mid in [("x", "m1"), ("x", "m2")]:
            resp = m.address_request(_add_syscall(content, mid))
            self.assertEqual(resp.memory_id, mid)
        self.assertEqual([mid for _, mid in provider.added],
                         ["m1", "m2"])

    def test_retrieve_returns_unfiltered(self) -> None:
        results = [
            {"content": "a", "memory_id": "a", "similarity": 0.01},
            {"content": "a", "memory_id": "b", "similarity": 0.01},
        ]
        provider = FakeProvider(retrieve_results=results)
        m = _make_manager(
            provider, static_enabled=False, adaptive_enabled=False
        )
        resp = m.address_request(_retrieve_syscall())
        # Nothing dropped despite low similarity + duplication.
        self.assertEqual(len(resp.search_results), 2)


class AdaptivePrecedenceTest(unittest.TestCase):
    """Both flags True: adaptive fires, static does not."""

    def test_adaptive_branch_wins_on_add(self) -> None:
        # If the static branch had fired we'd see no reward decision
        # tracking; the adaptive branch records a pending decision on
        # an admitted write. Use low similarities so adaptive admits.
        provider = FakeProvider(probe_similarities=[0.1])
        m = _make_manager(
            provider, static_enabled=True, adaptive_enabled=True
        )
        resp = m.address_request(_add_syscall("novel", "m1"))
        self.assertEqual(resp.memory_id, "m1")
        # Adaptive path recorded a pending reward decision; static path
        # never would. Proves adaptive won.
        self.assertIn("m1", m._pending_reward_decisions)


class LlmCoreCaptureOnStaticPathTest(unittest.TestCase):
    """sync_llm_from_query populates _latest_llm_core on the static
    path, and the static gate then keys on that real model identity
    (resolving a matching override, not the default)."""

    def _make_unknown_manager(self, provider, static_cfg):
        # Start from the true default ("unknown") to prove the capture
        # actually runs — do NOT pre-seed a model name.
        m = _make_manager(
            provider, static_enabled=True, static_cfg=static_cfg
        )
        m._latest_llm_core = "unknown"
        return m

    def test_sync_populates_llm_core_without_adaptive(self) -> None:
        provider = FakeProvider(probe_similarities=[0.4])
        m = self._make_unknown_manager(provider, dict(_STATIC_CFG))
        self.assertEqual(m._latest_llm_core, "unknown")
        # Static thresholds on, adaptive OFF: capture must still run.
        self.assertFalse(m._adaptive_enabled)
        m.sync_llm_from_query([{"name": "llama3.1:8b"}])
        self.assertEqual(m._latest_llm_core, "llama3.1:8b")

    def test_static_novelty_gate_uses_synced_override(self) -> None:
        # Override for (llama3.1:8b, profile) = 0.99; default = 0.7.
        # A candidate with max_sim 0.95 is REJECTED under the default
        # (0.95 >= 0.7) but ADMITTED under the override (0.95 < 0.99).
        # If _latest_llm_core were still "unknown", the override would
        # not match and the write would be rejected. Admission proves
        # the synced model name drove the lookup.
        cfg = dict(_STATIC_CFG)
        cfg["novelty_threshold"] = {
            "default": 0.7,
            "overrides": [
                {"llm_core": "llama3.1:8b", "task_type": "profile",
                 "value": 0.99},
            ],
        }
        provider = FakeProvider(probe_similarities=[0.95])
        m = self._make_unknown_manager(provider, cfg)

        # Sanity: with llm_core still "unknown", the override does NOT
        # match, so the candidate is rejected under the default.
        resp_unknown = m.address_request(_add_syscall("dup-ish", "m0"))
        self.assertIsNone(resp_unknown.memory_id)

        # Now sync the model the override targets, then retry.
        m.sync_llm_from_query([{"name": "llama3.1:8b"}])
        self.assertEqual(m._latest_llm_core, "llama3.1:8b")
        resp = m.address_request(_add_syscall("dup-ish", "m1"))
        self.assertEqual(resp.memory_id, "m1")

    def test_static_retrieve_gate_uses_synced_override(self) -> None:
        # similarity_threshold override for (llama3.1:8b, profile)=0.9;
        # default=0.5. A 0.6-similarity result survives the default but
        # is dropped under the override — proving the synced llm_core
        # drives the retrieve gate too.
        cfg = dict(_STATIC_CFG)
        cfg["similarity_threshold"] = {
            "default": 0.5,
            "overrides": [
                {"llm_core": "llama3.1:8b", "task_type": "profile",
                 "value": 0.9},
            ],
        }
        results = [
            {"content": "a", "memory_id": "a", "similarity": 0.95},
            {"content": "b", "memory_id": "b", "similarity": 0.6},
        ]
        provider = FakeProvider(retrieve_results=results)
        m = self._make_unknown_manager(provider, cfg)
        m.sync_llm_from_query([{"name": "llama3.1:8b"}])
        resp = m.address_request(_retrieve_syscall())
        kept_ids = [r["memory_id"] for r in resp.search_results]
        # Under override 0.9: only the 0.95 result survives.
        self.assertEqual(kept_ids, ["a"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
