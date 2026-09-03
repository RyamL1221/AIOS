# Verification harness for Subtask 3:
# Prove that with memory.adaptive_policy.trial_log configured, a
# retrieve_memory + report_reward cycle persists JSONL records to
# logs/policy_trials.jsonl, keyed by trial_id, containing the bandit /
# arm touched and the reward value applied.
#
# This drives the REAL MemoryManager retrieve gate + report_reward and
# the REAL PolicyTrialLogger.from_config path (fed the actual config
# block from config.yaml), then reads the file back to confirm the
# records landed. No live Mem0/Ollama stack needed: the retrieve gate
# operates on the provider's search_results dicts (Mem0-shaped, each
# carrying the Subtask-1 "memory_id").
#
# Run:  PYTHONPATH=. .venv/bin/python scripts/verify_policy_trial_log.py

import json
import os

from aios.config.config_manager import config
from aios.memory.manager import MemoryManager
from aios.memory.policy import PolicyManager
from aios.memory.policy_log import PolicyTrialLogger
from cerebrum.memory.apis import MemoryQuery

TRIAL_ID = "trial-subtask3-verify"


def _mem0_shaped_results():
    """Same shape Mem0Provider.retrieve_memory now emits (Subtask 1)."""
    return [
        {
            "memory_id": "mem0-id-aaaa",
            "content": "User prefers Python for backend services.",
            "keywords": [],
            "tags": [],
            "category": "Uncategorized",
            "timestamp": "",
            "score": 0.95,
            "similarity": 0.95,
            "metadata": {"user_id": "alex", "memory_type": "profile"},
        },
    ]


def main():
    print("=" * 70)
    print("Subtask 3 verification: per-trial policy trial_log")
    print("=" * 70)

    # --- Confirm config.yaml actually carries the active trial_log. ---
    adaptive_cfg = (config.get_memory_config() or {}).get(
        "adaptive_policy", {}
    )
    print(f"\n[0] memory.adaptive_policy from config.yaml: {adaptive_cfg}")
    assert adaptive_cfg.get("trial_log") == "logs/policy_trials.jsonl", (
        "trial_log must be active in config.yaml"
    )
    print("    -> trial_log is active (not commented): OK")

    log_path = adaptive_cfg["trial_log"]
    # Start from a clean file so we can assert on exactly this run's
    # records (the writer itself is append-only).
    if os.path.exists(log_path):
        os.remove(log_path)

    # --- Build a manager wired exactly as __init__ would from this
    # config block: real PolicyManager + real PolicyTrialLogger via
    # from_config (proving the config key drives the logger). ---
    mgr = MemoryManager.__new__(MemoryManager)
    mgr._adaptive_enabled = bool(adaptive_cfg.get("enabled", False))
    mgr.policy = PolicyManager(alpha=float(adaptive_cfg.get("alpha", 1.0)))
    mgr.policy_logger = PolicyTrialLogger.from_config(adaptive_cfg)
    mgr._latest_llm_core = "qwen2.5:7b"
    mgr._pending_reward_decisions = {}
    # Offline-safe redundancy gate (avoids MiniLM download; keeps both
    # results; does not affect decision recording or logging).
    mgr._pairwise_cosine = staticmethod(lambda a, b: 0.0)

    assert mgr._adaptive_enabled, "adaptive policy must be enabled"
    assert mgr.policy_logger is not None, (
        "PolicyTrialLogger.from_config must return a logger when "
        "trial_log is set"
    )
    print(f"    -> PolicyTrialLogger active at {mgr.policy_logger.path}")

    # --- retrieve gate (writes 'select' records per gate decision) ---
    query = MemoryQuery(
        operation_type="retrieve_memory",
        params={
            "content": "what does the user prefer?",
            "k": 5,
            "user_id": "alex",
            "metadata": {
                "memory_type": "profile",
                "trial_id": TRIAL_ID,
            },
        },
    )
    mgr._apply_retrieval_policy(_mem0_shaped_results(), query)
    print(f"\n[1] Ran retrieve gate with trial_id={TRIAL_ID!r}")

    # --- report_reward (writes 'reward' records per decision) ---
    mgr.report_reward(["mem0-id-aaaa"], 1.0, {"trial_id": TRIAL_ID})
    print("[2] Ran report_reward(reward_value=1.0)")

    # Subtask-2 invariant still holds: consumed id cleared.
    assert "mem0-id-aaaa" not in mgr._pending_reward_decisions, (
        "consumed id must be cleared (Subtask 2 invariant)"
    )
    print("    -> Subtask-2 invariant intact (consumed id cleared)")

    # --- Read the file back and verify records. ---
    print(f"\n[3] Reading {log_path} back:")
    with open(log_path) as f:
        lines = [json.loads(ln) for ln in f if ln.strip()]
    for rec in lines:
        print(f"    {rec}")

    selects = [r for r in lines if r.get("event") == "select"]
    rewards = [r for r in lines if r.get("event") == "reward"]

    # Every record must carry OUR trial_id (join key to the benchmark).
    assert all(r.get("trial_id") == TRIAL_ID for r in lines), (
        "every record must carry the trial_id"
    )
    print(f"\n    all {len(lines)} record(s) carry trial_id={TRIAL_ID!r}: OK")

    # 'select' records: both retrieve-side bandits chose a threshold.
    select_bandits = {r["bandit"] for r in selects}
    assert select_bandits == {
        "similarity_threshold",
        "redundancy_threshold",
    }, f"unexpected select bandits: {select_bandits}"
    for r in selects:
        assert "arm_index" in r and "value" in r
    print(f"    select records for {sorted(select_bandits)} with "
          f"arm_index + value: OK")

    # 'reward' records: reward applied to each touched bandit/arm, with
    # the reward value and memory_id present (auditable join back).
    assert len(rewards) == 2, (
        f"expected 2 reward records (sim + redundancy), got {len(rewards)}"
    )
    for r in rewards:
        assert r["reward"] == 1.0, "reward value must be recorded"
        assert r["memory_id"] == "mem0-id-aaaa"
        assert "arm_index" in r and "bandit" in r
    reward_bandits = {r["bandit"] for r in rewards}
    assert reward_bandits == {
        "similarity_threshold",
        "redundancy_threshold",
    }, f"unexpected reward bandits: {reward_bandits}"
    print(f"    reward records for {sorted(reward_bandits)} with "
          f"reward=1.0, arm_index, memory_id: OK")

    print("\n" + "=" * 70)
    print("ALL CHECKS PASSED: trial_log persists select + reward records "
          "joinable by trial_id.")
    print("=" * 70)


if __name__ == "__main__":
    main()
