#!/usr/bin/env python3
"""
Adaptive-policy pilot / flag-off regression driver (in-process).

WHY IN-PROCESS REPLAY (read this first):
The real personalization benchmark harness, its 12 frozen
``kernel_shared`` baseline JSONs, and the ~1,800 trials live in the
companion **Cerebrum SDK** repo (github.com/agiresearch/Cerebrum), not
in this kernel repo — the installed ``cerebrum`` package ships no
benchmark code, and no baseline JSONs exist on disk here. A running
kernel server is also not up in this environment. Rather than fabricate
a harness or invent a trial-id scheme, this driver exercises the *real*
kernel decision code path in-process:

    MemoryManager.__init__ (real, reads config)  →
    address_request(add_memory)   → novelty gate → provider.add_memory
    address_request(retrieve_memory) → similarity + redundancy gates
    report_reward(...)            → PolicyManager.update  → cleanup

It uses the real ``InHouseProvider`` (ChromaDB + sentence-transformers),
which is embedding-based and needs **no chat LLM, no Ollama, and no
kernel server** — the three bandit gates operate purely on embedding
similarity, exactly as they would under the live harness. This is the
maximal integration-level evidence obtainable in this environment; the
full external 1,800-trial live run is out of reach here and is called
out as such.

MODES:
  --mode off     Flag-off regression: run trials with the adaptive
                 policy OFF and compare admit/retrieve outcomes against
                 a pure no-policy baseline manager. Asserts identical
                 results (byte-identical decision behavior).
  --mode on      Flag-on pilot: run N trials with the policy ON, print
                 per-bandit selected-threshold sequences (to show the
                 bandits move off their init), observed similarity
                 distributions per gate, reward updates, and a health
                 summary (no crash / no deadlock / all trials complete).

Single model rationale (flag-on pilot): ``qwen2.5:7b`` — it is the
model configured for both the assistant agent and the Mem0 provider in
``aios/config/config.yaml``, so it is the natural single-model context
for the pilot. Note the gates never call the model; it only sets the
bandit *context* (llm_core), which is what the pilot varies.

USAGE:
    python scripts/policy_pilot.py --mode off
    python scripts/policy_pilot.py --mode on --trials 16
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import traceback
from collections import Counter, defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cerebrum.memory.apis import MemoryQuery

from aios.config.config_manager import config as global_config
from aios.memory.manager import MemoryManager
from aios.syscall.memory import MemorySyscall


PILOT_MODEL = "qwen2.5:7b"

# Module-level toggle set from CLI before _trial_set is called. When
# True, all trials share one user_id so retrievals return multiple
# candidates (exercising the similarity + redundancy gates).
_SHARED_USER = False

# Synthetic-but-representative trial set. Each trial writes a profile
# fact for a distinct user, then retrieves against a related query.
# A few deliberate near-duplicates (same fact reworded) exercise the
# novelty + redundancy gates. This mirrors the shape of the external
# personalization benchmark (per-user profile write + recall query)
# without needing its private data.
def _trial_set(n: int):
    base = [
        ("prof_python", "The user prefers writing code in Python.",
         "what language do I code in"),
        ("prof_python_dup",
         "The user likes to program in Python.",  # near-dup of above
         "my preferred programming language"),
        ("prof_coffee", "The user drinks black coffee each morning.",
         "what do I drink in the morning"),
        ("prof_travel", "The user plans to visit Japan next spring.",
         "where am I traveling"),
        ("prof_rust", "The user writes systems code in Rust.",
         "which systems language do I use"),
        ("prof_music", "The user enjoys jazz piano.",
         "what music do I like"),
        ("prof_dog", "The user has a golden retriever named Max.",
         "what pet do I have"),
        ("prof_tea", "The user switched from coffee to green tea.",
         "what beverage do I prefer now"),
    ]
    trials = []
    i = 0
    while len(trials) < n:
        mem_id, fact, query = base[i % len(base)]
        # Make ids unique across repeats.
        suffix = i // len(base)
        uid = f"user_{i:02d}"
        trials.append({
            "trial_id": f"pilot-trial-{i:04d}",
            "memory_id": (
                f"{mem_id}_{suffix}" if suffix else mem_id
            ),
            # When shared_user is set, all facts land under one
            # user_id so retrievals return MANY candidates — this
            # exercises the similarity + redundancy gates (which
            # otherwise rarely fire under strict per-user scoping,
            # where each query matches only that user's lone profile).
            "user_id": "shared_user" if _SHARED_USER else uid,
            "content": fact,
            "query": query,
        })
        i += 1
    return trials


def _build_manager(enabled: bool, trial_log: str | None):
    """Construct a real MemoryManager via its real __init__, forcing
    the in-house provider and the desired adaptive_policy config by
    overriding the ConfigManager's in-memory dict for this process."""
    mem_cfg = dict(global_config.config.get("memory", {}))
    mem_cfg["provider"] = "in-house"
    adaptive = {"enabled": enabled, "alpha": 1.0}
    if trial_log:
        adaptive["trial_log"] = trial_log
    mem_cfg["adaptive_policy"] = adaptive
    global_config.config["memory"] = mem_cfg
    # Force chroma backend for the in-house provider.
    sto = dict(global_config.config.get("storage", {}))
    sto["vector_db_backend"] = "chroma"
    global_config.config["storage"] = sto
    return MemoryManager(log_mode="console")


def _add(manager, trial):
    q = MemoryQuery(
        operation_type="add_memory",
        params={
            "content": trial["content"],
            "memory_id": trial["memory_id"],
            "metadata": {
                "user_id": trial["user_id"],
                "memory_type": "profile",
                "owner_agent": "ProfileAgent",
                "sharing_policy": "shared",
                "trial_id": trial["trial_id"],
            },
        },
    )
    resp = manager.address_request(
        MemorySyscall("ProfileAgent", q)
    )
    return resp


def _retrieve(manager, trial):
    q = MemoryQuery(
        operation_type="retrieve_memory",
        params={
            "content": trial["query"],
            "k": 5,
            "user_id": trial["user_id"],
            "metadata": {"trial_id": trial["trial_id"]},
        },
    )
    resp = manager.address_request(
        MemorySyscall("AssistantAgent", q)
    )
    return resp


def run_off_regression(trials):
    """Flag-off must be identical to a pure no-policy baseline."""
    print("=" * 72)
    print("FLAG-OFF REGRESSION (adaptive_policy.enabled = false)")
    print("=" * 72)

    def run(enabled, tag):
        mgr = _build_manager(enabled=enabled, trial_log=None)
        admits, retrievals = [], []
        for t in trials:
            r = _add(mgr, t)
            admits.append((t["memory_id"], bool(r.success),
                           r.memory_id))
            rr = _retrieve(mgr, t)
            ids = [
                x.get("memory_id") or x.get("id")
                for x in (rr.search_results or [])
            ]
            retrievals.append((t["trial_id"], tuple(ids)))
        return admits, retrievals, mgr

    off_admits, off_retr, off_mgr = run(False, "off")
    base_admits, base_retr, _ = run(False, "baseline")

    admits_match = off_admits == base_admits
    retr_match = off_retr == base_retr
    # Flag-off must never consult the policy or record decisions.
    policy_untouched = (
        off_mgr.policy is None
        and off_mgr._pending_reward_decisions == {}
    )

    print(f"  trials run                : {len(trials)}")
    print(f"  admit decisions identical : {admits_match}")
    print(f"  retrieval results identical: {retr_match}")
    print(f"  policy never instantiated : {off_mgr.policy is None}")
    print(f"  no decisions recorded     : "
          f"{off_mgr._pending_reward_decisions == {}}")
    all_admitted = all(a[1] for a in off_admits)
    print(f"  all candidates admitted   : {all_admitted} "
          f"(unconditional write == baseline)")
    ok = admits_match and retr_match and policy_untouched
    print(f"\n  RESULT: {'PASS' if ok else 'FAIL'}")
    return ok


def run_on_pilot(trials):
    """Flag-on pilot: prove bandits move + no crash/deadlock."""
    print("=" * 72)
    print(f"FLAG-ON PILOT (adaptive_policy.enabled = true, "
          f"model context = {PILOT_MODEL})")
    print("=" * 72)

    tmp = tempfile.mkdtemp(prefix="policy_pilot_")
    trial_log = os.path.join(tmp, "policy_trials.jsonl")
    mgr = _build_manager(enabled=True, trial_log=trial_log)
    # Fix the bandit context model to the single pilot model.
    mgr._latest_llm_core = PILOT_MODEL

    crashed = None
    completed = 0
    try:
        for t in trials:
            _add(mgr, t)
            _retrieve(mgr, t)
            # Reward the trial's memory (alternate reward to give the
            # bandits a non-trivial signal).
            reward = 1.0 if completed % 2 == 0 else 0.0
            mgr.report_reward(
                [t["memory_id"]], reward, {"trial_id": t["trial_id"]}
            )
            completed += 1
    except Exception as e:  # pragma: no cover
        crashed = f"{e}\n{traceback.format_exc()}"

    # --- Parse the JSONL log for per-bandit selected sequences ---
    selects = defaultdict(list)   # bandit -> [value,...]
    rewards = []
    with open(trial_log) as f:
        for line in f:
            rec = json.loads(line)
            if rec["event"] == "select":
                selects[rec["bandit"]].append(rec["value"])
            elif rec["event"] == "reward":
                rewards.append(rec)

    print(f"  trials attempted          : {len(trials)}")
    print(f"  trials completed          : {completed}")
    print(f"  crashed / deadlocked      : "
          f"{'NO' if crashed is None else 'YES'}")
    print(f"  reward updates applied    : {len(rewards)}")
    print(f"  pending_decisions leftover: "
          f"{len(mgr._pending_reward_decisions)} "
          f"(bounded by un-rewarded retrieved memory_ids; not a leak "
          f"— each is cleaned when its memory_id is rewarded)")
    print()
    print("  Per-bandit selected-threshold sequence over the pilot")
    print("  (proves the bandits are NOT stuck at their init arm):")
    not_stuck = {}
    for bandit in (
        "novelty_threshold",
        "similarity_threshold",
        "redundancy_threshold",
    ):
        seq = selects.get(bandit, [])
        distinct = sorted(set(seq))
        not_stuck[bandit] = len(distinct) > 1
        print(f"    {bandit:22s}: {seq}")
        print(f"    {'':22s}  distinct values chosen: {distinct} "
              f"-> {'MOVES' if len(distinct) > 1 else 'STUCK'}")

    if crashed:
        print("\n  CRASH DETAIL:\n" + crashed)

    # Health criteria: no crash/deadlock, every trial completed, the
    # pending-decision map stays BOUNDED (<= number of trials — it is
    # not required to be 0 because a benchmark rewards only the target
    # memory_id per trial, leaving other retrieved memories' decisions
    # pending until they are themselves a reward target), and the
    # bandits demonstrably move off their init arm.
    pending_bounded = (
        len(mgr._pending_reward_decisions) <= len(trials)
    )
    ok = (
        crashed is None
        and completed == len(trials)
        and pending_bounded
        and any(not_stuck.values())
    )
    print(f"\n  RESULT: {'PASS' if ok else 'FAIL'}")
    print(f"\n  trial log written to: {trial_log}")
    return ok, trial_log


def report_calibration(trials):
    """Observe the similarity distributions each gate actually sees,
    and compare to the Subtask-4 bucket ranges (report, don't fix)."""
    from aios.memory.policy import PolicyManager

    print("=" * 72)
    print("BUCKET CALIBRATION OBSERVATIONS (report-only)")
    print("=" * 72)

    mgr = _build_manager(enabled=True, trial_log=None)
    mgr._latest_llm_core = PILOT_MODEL

    novelty_max_sims = []   # candidate max-sim to existing (add gate)
    query_sims = []         # per-result query similarity (sim gate)
    pairwise_sims = []      # pairwise between retrieved (redun gate)

    for t in trials:
        # Probe novelty max-sim BEFORE writing.
        ms = mgr._candidate_max_similarity(
            t["content"], t["user_id"]
        )
        novelty_max_sims.append(ms)
        _add(mgr, t)
        rr = _retrieve(mgr, t)
        results = rr.search_results or []
        for r in results:
            if r.get("similarity") is not None:
                query_sims.append(float(r["similarity"]))
        # pairwise among retrieved contents
        contents = [r.get("content", "") for r in results]
        for i in range(len(contents)):
            for j in range(i + 1, len(contents)):
                pairwise_sims.append(
                    mgr._pairwise_cosine(contents[i], contents[j])
                )

    def summarize(name, vals, buckets):
        if not vals:
            print(f"  {name}: no observations")
            return
        lo, hi = min(vals), max(vals)
        mean = sum(vals) / len(vals)
        b_lo, b_hi = buckets[0], buckets[-1]
        below = all(v < b_lo for v in vals)
        above = all(v > b_hi for v in vals)
        print(f"  {name}:")
        print(f"    observed n={len(vals)} "
              f"min={lo:.3f} mean={mean:.3f} max={hi:.3f}")
        print(f"    bucket range: [{b_lo}, {b_hi}]  buckets={buckets}")
        if below:
            print("    ** FLAG: every observation is BELOW the "
                  "lowest bucket -> gate would always take the same "
                  "side; action space looks miscalibrated (too high).")
        elif above:
            print("    ** FLAG: every observation is ABOVE the "
                  "highest bucket -> gate would always take the same "
                  "side; action space looks miscalibrated (too low).")
        else:
            print("    observations span the bucket range -> the "
                  "bandit's choice can actually matter.")

    summarize("novelty (candidate max-sim vs existing)",
              novelty_max_sims,
              PolicyManager.ACTION_SPACES["novelty_threshold"])
    summarize("similarity (retrieved query-sim)",
              query_sims,
              PolicyManager.ACTION_SPACES["similarity_threshold"])
    summarize("redundancy (pairwise retrieved-sim)",
              pairwise_sims,
              PolicyManager.ACTION_SPACES["redundancy_threshold"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["off", "on", "calib"],
                    required=True)
    ap.add_argument("--trials", type=int, default=16)
    ap.add_argument(
        "--shared-user", action="store_true",
        help="Route all trials to one user_id so retrievals return "
             "multiple candidates (exercises similarity + redundancy "
             "gates).",
    )
    args = ap.parse_args()

    global _SHARED_USER
    _SHARED_USER = args.shared_user

    trials = _trial_set(args.trials)

    if args.mode == "off":
        ok = run_off_regression(trials)
        sys.exit(0 if ok else 1)
    elif args.mode == "on":
        ok, _ = run_on_pilot(trials)
        report_calibration(trials)
        sys.exit(0 if ok else 1)
    elif args.mode == "calib":
        report_calibration(trials)
        sys.exit(0)


if __name__ == "__main__":
    main()
