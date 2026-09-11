# Subtask 3 — Isolated sanity check: reward loop closes end-to-end

In-process only (no live kernel, no API). Confirms the full
decision → reward → update chain closes with the CURRENT code (the three
original fixes + the two-revision, now per-arm similarity-gate bootstrap
fail-open), before spending a real 2×10 pilot (Subtask 4, user-gated —
NOT run here).

Method mirrors the prior fix-chain sanity checks
(`scripts/verify_mem0_reward_attribution.py` style): a real
`MemoryManager` retrieve gate (`_apply_retrieval_policy`), the real
`report_reward`, and a real `PolicyManager` / `LinUCBBandit`.
`PolicyManager.update` was wrapped ONLY to COUNT invocations — the spy
calls through to the real method, so bandit state genuinely changes
(verified via the arm's `_b` vector norm), i.e. we prove real learning,
not a cleared dict or a mocked update.

## Scenario A — BOOTSTRAP (arm-0 wipeout → fail-open → reward reaches the arm)

Setup: similarity gate pinned to arm 0 (threshold 0.50), arm 0 has 0
updates; one result row at similarity 0.4766 (below 0.50, would wipe
out). Redundancy forced off (arm 0 / 0.99).

| signal | before | after |
|--------|:------:|:-----:|
| rows kept by gate | — | **1 / 1** (fail-open kept `row-aaaa`) |
| similarity decisions recorded | 0 | **1** (arm 0) |
| reward events logged (real `PolicyManager.update` calls) | **0** | **2** |
| — of which `similarity_threshold` | 0 | **1 (arm 0)** |
| similarity arm 0 `update_count` | **0** | **1** |
| similarity arm 0 `_b` L2 norm | **0.0000** | **0.6928** (real learning) |
| `_pending_reward_decisions` | 0 | 0 (consumed) |

Result: **PASS.** The bootstrap fail-open kept the row, a decision was
recorded against the surviving `memory_id`, `report_reward` invoked the
REAL `PolicyManager.update`, and the specific arm that made the
fail-open decision (arm 0) received the reward and moved off its
optimistic init (`_b` 0 → 0.6928).

Note on the count being **2, not 1**: the surviving row records both a
`similarity_threshold` and a `redundancy_threshold` decision, so
equal-split `report_reward` credits both bandits (2 updates total). The
task's specific requirement — the similarity arm that made the
bootstrap-open decision (arm 0) receives the reward — holds exactly:
1 `similarity_threshold` update, on arm 0.

## Scenario B — CONVERGED (validated strict arm → wipeout honored → no reward)

Setup: similarity gate pinned to a strict arm 4 (threshold 0.90),
pre-validated with 2 real reward updates (≥ `BOOTSTRAP_MIN_UPDATES` = 1);
one result row at similarity 0.60 (below 0.90, wipes out).

| signal | value |
|--------|:-----:|
| selected arm 4 `update_count` (pre) | 2 (≥ 1) |
| rows kept by gate | **0 / 1** (strict arm rejects everything) |
| `_pending_reward_decisions` after gate | **0** |
| reward events logged this trial (via `report_reward([], …)`) | **0** |

Result: **PASS.** A validated strict arm still empties the result set
end-to-end (ceiling restored, not disabled by the fail-open); with
nothing surviving, the harness sends an empty `memory_ids_involved` and
`report_reward` correctly credits nothing.

## Conclusion

The decision → reward → update chain **closes end-to-end in-process** for
the bootstrap case (0 → 2 reward events, arm-0 validated with real
bandit-state change) and correctly stays closed-with-no-reward for the
converged case (0 surviving rows, 0 reward events). No code changes were
required — this was a sanity check and the chain is intact.

Per the status gate (`OWNER_AGENT_MECHANISM_AND_RETRIEVE_GATE_FIX.md`):
no further unit-level narrowing from armchair reasoning. This in-process
check surfaced **no new problem**, so the next and only remaining
verification is the live 2×10 `kernel_shared_adaptive` pilot (Subtask 4),
which is gated on explicit user sign-off and was not run here.
