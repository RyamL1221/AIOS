"""
Tests for per-trial policy logging (PolicyTrialLogger + wiring).

Verifies:
- The logger writes joinable JSONL records keyed by trial_id.
- from_config returns None when no trial_log path is set (inert).
- An end-to-end flag-on add→retrieve→report_reward run emits
  select records for all three gates and reward records, all carrying
  the same trial_id supplied by the caller (never invented).

Run standalone:
    python tests/modules/memory/test_policy_trial_logging.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from collections import OrderedDict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from aios.memory.manager import MemoryManager
from aios.memory.policy_log import PolicyTrialLogger
from aios.memory.write_barrier import MemoryWriteBarrier
from aios.syscall.memory import MemorySyscall


class FakeProvider:
    def __init__(self, results=None):
        self.added = []
        self._results = results or []

    def add_memory(self, note):
        self.added.append(note.id)
        return MemoryResponse(success=True, memory_id=note.id)

    def retrieve_memory(self, query):
        return MemoryResponse(
            success=True,
            search_results=[dict(r) for r in self._results],
        )

    def retrieve_memory_raw(self, query):
        return []


def _make_manager(provider, trial_log_path):
    from aios.memory.policy import PolicyManager
    m = MemoryManager.__new__(MemoryManager)
    m.log_mode = "console"
    m._known_user_ids = OrderedDict()
    m.provider = provider
    m.barrier = MemoryWriteBarrier(config={"enabled": False})
    m._adaptive_enabled = True
    m._latest_llm_core = "qwen2.5:7b"
    m._pending_reward_decisions = {}
    m.policy = PolicyManager(alpha=1.0)
    m.policy_logger = PolicyTrialLogger(trial_log_path)
    return m


class FromConfigTest(unittest.TestCase):
    def test_none_when_no_path(self) -> None:
        self.assertIsNone(
            PolicyTrialLogger.from_config({"enabled": True})
        )

    def test_logger_when_path_set(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "trials.jsonl")
            lg = PolicyTrialLogger.from_config({"trial_log": p})
            self.assertIsNotNone(lg)
            lg.log_select(
                "t1", "novelty_threshold", "novelty",
                0.5, 0, "qwen2.5:7b", "profile", [0.0, 1.0],
            )
            with open(p) as f:
                rec = json.loads(f.readline())
            self.assertEqual(rec["trial_id"], "t1")
            self.assertEqual(rec["event"], "select")
            self.assertEqual(rec["gate"], "novelty")


class EndToEndLoggingTest(unittest.TestCase):
    def test_add_retrieve_reward_all_logged_with_trial_id(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "trials.jsonl")
            provider = FakeProvider(results=[
                {"memory_id": "r1", "content": "alpha",
                 "similarity": 0.9},
            ])
            m = _make_manager(provider, path)

            # add_memory carrying trial_id in metadata
            add_q = MemoryQuery(
                operation_type="add_memory",
                params={
                    "content": "novel fact",
                    "memory_id": "r1",
                    "metadata": {
                        "user_id": "alex",
                        "memory_type": "profile",
                        "trial_id": "trial-007",
                    },
                },
            )
            m.address_request(MemorySyscall("ProfileAgent", add_q))

            # retrieve_memory carrying same trial_id
            ret_q = MemoryQuery(
                operation_type="retrieve_memory",
                params={
                    "content": "q",
                    "k": 5,
                    "user_id": "alex",
                    "metadata": {"trial_id": "trial-007"},
                },
            )
            m.address_request(MemorySyscall("AssistantAgent", ret_q))

            # reward for the retrieved memory
            m.report_reward(["r1"], 1.0, {"trial_id": "trial-007"})

            # Parse the JSONL.
            records = []
            with open(path) as f:
                for line in f:
                    records.append(json.loads(line))

            events = [r["event"] for r in records]
            gates = {
                r.get("gate") for r in records if r["event"] == "select"
            }
            bandits = {r["bandit"] for r in records}
            trial_ids = {r["trial_id"] for r in records}

            # All three gates produced a select record.
            self.assertEqual(
                gates, {"novelty", "similarity", "redundancy"}
            )
            # Reward records were emitted.
            self.assertIn("reward", events)
            # Every record joins to the caller-supplied trial_id.
            self.assertEqual(trial_ids, {"trial-007"})
            self.assertIn("novelty_threshold", bandits)
            self.assertIn("similarity_threshold", bandits)
            self.assertIn("redundancy_threshold", bandits)


if __name__ == "__main__":
    unittest.main(verbosity=2)
