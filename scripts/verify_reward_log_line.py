# Verification harness for Subtask 4:
# Prove that MemoryManager.report_reward emits an INFO "reward applied"
# line ONLY on a genuine bandit update, and stays silent on the
# no-pending-decision no-op case. Uses a logging capture handler on the
# real aios.memory.manager logger.
#
# Run:  PYTHONPATH=. .venv/bin/python scripts/verify_reward_log_line.py

import logging

from aios.memory.manager import MemoryManager
from aios.memory.policy import PolicyManager
from cerebrum.memory.apis import MemoryQuery


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.INFO)
        self.records = []

    def emit(self, record):
        self.records.append(record.getMessage())


def _mem0_shaped_results():
    return [
        {
            "memory_id": "mem0-id-aaaa",
            "content": "User prefers Python for backend services.",
            "keywords": [], "tags": [], "category": "Uncategorized",
            "timestamp": "", "score": 0.95, "similarity": 0.95,
            "metadata": {"user_id": "alex", "memory_type": "profile"},
        },
    ]


def _make_manager():
    mgr = MemoryManager.__new__(MemoryManager)
    mgr._adaptive_enabled = True
    mgr.policy = PolicyManager(alpha=1.0)
    mgr.policy_logger = None
    mgr._latest_llm_core = "qwen2.5:7b"
    mgr._pending_reward_decisions = {}
    mgr._pairwise_cosine = staticmethod(lambda a, b: 0.0)
    return mgr


def main():
    print("=" * 70)
    print("Subtask 4 verification: report_reward INFO line")
    print("=" * 70)

    cap = _Capture()
    mgr_logger = logging.getLogger("aios.memory.manager")
    mgr_logger.addHandler(cap)
    mgr_logger.setLevel(logging.INFO)

    mgr = _make_manager()
    query = MemoryQuery(
        operation_type="retrieve_memory",
        params={
            "content": "prefs?", "k": 5, "user_id": "alex",
            "metadata": {"memory_type": "profile", "trial_id": "trial-log4"},
        },
    )
    mgr._apply_retrieval_policy(_mem0_shaped_results(), query)

    # --- Genuine update case ---
    cap.records.clear()
    mgr.report_reward(["mem0-id-aaaa"], 1.0, {"trial_id": "trial-log4"})
    applied_lines = [
        m for m in cap.records
        if "reward applied to" in m and "trial_id=trial-log4" in m
    ]
    print("\n[1] Genuine-update case, matching INFO lines:")
    for m in applied_lines:
        print(f"    {m}")
    assert len(applied_lines) == 1, (
        f"expected exactly one 'reward applied' line, got "
        f"{len(applied_lines)}"
    )
    line = applied_lines[0]
    assert "trial_id=trial-log4" in line
    assert "arm(s)" in line
    assert "bandits=" in line and "memory_ids=" in line
    print("    -> exactly one INFO line with trial_id + count + "
          "bandits + memory_ids: OK")

    # --- No-op case (no pending decisions for this id) ---
    cap.records.clear()
    mgr.report_reward(["nonexistent-zzzz"], 1.0, {"trial_id": "trial-log4"})
    noop_applied = [m for m in cap.records if "reward applied to" in m]
    print("\n[2] No-pending-decision no-op case:")
    print(f"    'reward applied' lines emitted: {len(noop_applied)}")
    assert len(noop_applied) == 0, (
        "no-op case must NOT emit the 'reward applied' line"
    )
    print("    -> no 'reward applied' line emitted on no-op: OK")

    print("\n" + "=" * 70)
    print("ALL CHECKS PASSED: INFO line fires only on genuine updates.")
    print("=" * 70)


if __name__ == "__main__":
    main()
