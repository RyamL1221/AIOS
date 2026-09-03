# Verification harness for Subtask 2:
# Prove the Mem0 `memory_id` (emitted by retrieve_memory in Subtask 1)
# flows through MemoryManager's retrieve gate into
# _pending_reward_decisions, and that report_reward consumes those
# decisions and applies reward to the correct bandit(s).
#
# This is a *proof* harness, not a pytest test. It drives the REAL
# MemoryManager methods (_apply_retrieval_policy, _record_decision,
# report_reward) and the REAL PolicyManager/LinUCBBandit. It does not
# require a live Mem0/Ollama stack: the retrieve gate operates purely on
# the provider's `search_results` dicts, so we feed it Mem0-shaped
# results identical to what the just-fixed retrieve_memory produces
# (each dict carrying a non-null "memory_id").
#
# Run:  python scripts/verify_mem0_reward_attribution.py

import numpy as np

from aios.memory.manager import MemoryManager
from aios.memory.policy import PolicyManager
from cerebrum.memory.apis import MemoryQuery


def _mem0_shaped_results():
    """Mimic exactly what Mem0Provider.retrieve_memory now returns.

    Each entry carries the additive "memory_id" key (Subtask 1) plus the
    pre-existing keys. "similarity" is at/above any plausible threshold
    so both results survive the similarity gate and get decisions
    recorded.
    """
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
        {
            "memory_id": "mem0-id-bbbb",
            "content": "The current sprint ships the billing dashboard.",
            "keywords": [],
            "tags": [],
            "category": "Uncategorized",
            "timestamp": "",
            "score": 0.88,
            "similarity": 0.88,
            "metadata": {"user_id": "alex", "memory_type": "task_context"},
        },
    ]


def _make_manager():
    """Build a MemoryManager with adaptive policy ENABLED without
    running __init__ (which would require a provider/config). We only
    need the retrieve-gate + reward machinery, so we wire exactly the
    attributes those methods read."""
    mgr = MemoryManager.__new__(MemoryManager)
    mgr._adaptive_enabled = True
    mgr.policy = PolicyManager(alpha=1.0)
    mgr.policy_logger = None
    mgr._latest_llm_core = "qwen2.5:7b"
    mgr._pending_reward_decisions = {}
    # Force the redundancy gate to keep everything (offline-safe:
    # avoids the MiniLM download and makes the proof deterministic).
    # Every surviving memory still records its similarity + redundancy
    # decision, which is the path under test.
    mgr._pairwise_cosine = staticmethod(lambda a, b: 0.0)
    return mgr


def main():
    print("=" * 70)
    print("Subtask 2 verification: Mem0 memory_id -> pending decisions "
          "-> report_reward")
    print("=" * 70)

    mgr = _make_manager()

    # --- Step 1: confirm each mem_id resolved from search_results is
    # non-None (this is exactly what the retrieve gate reads at
    # manager.py ~line 572: r.get("memory_id") or r.get("id")). ---
    raw_results = _mem0_shaped_results()
    print("\n[1] Raw Mem0-shaped search_results (as emitted by the "
          "Subtask-1 retrieve_memory fix):")
    resolved_ids = []
    for r in raw_results:
        mem_id = r.get("memory_id") or r.get("id")
        resolved_ids.append(mem_id)
        print(f"    content={r['content']!r:52} "
              f"memory_id={mem_id!r}")
        assert mem_id is not None, "memory_id must be non-None"
    print(f"    -> all {len(resolved_ids)} memory_ids non-None: OK")

    # --- Step 2: run the REAL retrieve gate and confirm
    # _pending_reward_decisions is populated, keyed by those ids. ---
    query = MemoryQuery(
        operation_type="retrieve_memory",
        params={
            "content": "what does the user prefer?",
            "k": 5,
            "user_id": "alex",
            "metadata": {"memory_type": "profile", "trial_id": "trial-42"},
        },
    )
    kept = mgr._apply_retrieval_policy(_mem0_shaped_results(), query)
    print(f"\n[2] _apply_retrieval_policy kept {len(kept)}/"
          f"{len(raw_results)} results.")
    print("    _pending_reward_decisions after retrieve:")
    for mid, decisions in mgr._pending_reward_decisions.items():
        bandits = [d[0] for d in decisions]
        print(f"      {mid!r}: {len(decisions)} decision(s) -> "
              f"{bandits}")
    # Each surviving memory should have exactly the two retrieve-side
    # bandit decisions (similarity + redundancy).
    for mid in resolved_ids:
        assert mid in mgr._pending_reward_decisions, (
            f"expected {mid} in pending decisions")
        names = {d[0] for d in mgr._pending_reward_decisions[mid]}
        assert names == {"similarity_threshold", "redundancy_threshold"}, (
            f"unexpected bandits for {mid}: {names}")
    print("    -> pending decisions populated for every memory_id, each "
          "holding (bandit, arm, context, trial_id): OK")

    # Capture the target bandits' pre-reward state so we can PROVE the
    # update landed (LinUCB update sets b_a += reward * x, so b changes
    # from its zero init).
    target_id = "mem0-id-aaaa"
    decisions_for_target = list(mgr._pending_reward_decisions[target_id])
    pre_state = {}
    for (bandit_name, arm_index, ctx, _tid) in decisions_for_target:
        bandit = mgr.policy._get_bandit(bandit_name)
        pre_state[(bandit_name, arm_index)] = bandit._b[arm_index].copy()

    # --- Step 3: report_reward with a real id + reward_value. ---
    reward = 1.0
    print(f"\n[3] Calling report_reward(memory_ids_involved=[{target_id!r}], "
          f"reward_value={reward})")
    pending_before = len(mgr._pending_reward_decisions)
    mgr.report_reward(
        [target_id], reward, {"trial_id": "trial-42"}
    )

    # 3a: consumed entries cleared for that id.
    assert target_id not in mgr._pending_reward_decisions, (
        "consumed entry should be cleared")
    print(f"    3a: {target_id!r} cleared from pending decisions: OK")
    # The OTHER id's decisions must remain untouched.
    assert "mem0-id-bbbb" in mgr._pending_reward_decisions, (
        "unrelated id must remain")
    print("    3b: unrelated memory_id 'mem0-id-bbbb' still pending "
          "(only involved id consumed): OK")
    print(f"        pending map: {pending_before} -> "
          f"{len(mgr._pending_reward_decisions)} memory_id(s)")

    # 3c: PROVE each decision was replayed into PolicyManager.update
    # with the FULL reward (equal-credit) -- b_a moved by reward * x.
    print("    3c: verifying each bandit decision received the full "
          "reward (equal-credit):")
    for (bandit_name, arm_index, ctx, _tid) in decisions_for_target:
        bandit = mgr.policy._get_bandit(bandit_name)
        expected = pre_state[(bandit_name, arm_index)] + reward * np.asarray(
            ctx, dtype=float
        )
        got = bandit._b[arm_index]
        ok = np.allclose(got, expected)
        print(f"        {bandit_name} arm={arm_index}: "
              f"b_a updated by reward*context = {ok}")
        assert ok, f"reward not applied correctly to {bandit_name}"
    print("    -> both similarity_threshold and redundancy_threshold "
          "bandits updated with full reward: OK")

    # --- Step 4: no-pending-decision id must be a safe no-op. ---
    print("\n[4] Regression: report_reward with an id that has NO pending "
          "decision:")
    # Snapshot the pending map's shape (ids -> decision count) without
    # numpy '==' on the context vectors, which would be ambiguous.
    def _shape(pending):
        return {k: len(v) for k, v in pending.items()}

    snapshot = _shape(mgr._pending_reward_decisions)
    try:
        mgr.report_reward(["nonexistent-id-zzzz"], 1.0, {})
        raised = False
    except Exception as e:  # pragma: no cover
        raised = True
        print(f"    ERROR: raised {e!r}")
    assert not raised, "no-pending case must not raise"
    assert _shape(mgr._pending_reward_decisions) == snapshot, (
        "no-pending case must not mutate other entries")
    print("    -> returned with no error, no side effects "
          "(other pending entries unchanged): OK")

    print("\n" + "=" * 70)
    print("ALL CHECKS PASSED: Mem0 memory_id attribution flows end-to-end.")
    print("=" * 70)


if __name__ == "__main__":
    main()
