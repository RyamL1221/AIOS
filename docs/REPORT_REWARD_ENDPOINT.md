# `POST /memory/report_reward` — Adaptive Memory Reward Endpoint

## Purpose

`/memory/report_reward` is the **reverse-direction reward channel** for
the self-improving memory system. A completed trial's judge sends its
scalar reward back into the kernel, where it updates the adaptive
policy's LinUCB bandits (novelty, similarity, redundancy) so future
add/retrieve threshold decisions improve.

It exists as its own HTTP route rather than going through `/query`
because the Cerebrum SDK's `MemoryQuery.operation_type` is a fixed
`Literal` that cannot hold `"report_reward"`. Routing a reward through
`/query` therefore fails pydantic validation and returns **HTTP 500**.
The dedicated endpoint sidesteps that entirely — **no SDK change is
required** to submit a reward.

## Endpoint

```
POST /memory/report_reward
Content-Type: application/json
```

### Request body (`ReportRewardRequest`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `agent_name` | string | yes | The agent/source reporting the reward. |
| `memory_ids_involved` | `list[str]` | no (default `[]`) | Memory IDs that contributed to the trial — the bandit "arms" whose reward is being reported. |
| `reward_value` | float | yes | The judge's scalar reward for the trial (convention: higher is better; callers typically use `[0, 1]`). |
| `trial_metadata` | object | no (default `{}`) | Arbitrary per-trial context. Include `trial_id` here so the reward joins to the per-trial policy log and the benchmark's own trial records. |

### Response (200)

```json
{
  "success": true,
  "error": null,
  "memory_ids_involved": ["mem_a", "mem_b"],
  "reward_value": 0.83
}
```

- `success` — whether the kernel accepted the reward.
- `error` — error message when `success` is `false`, else `null`.

### Status codes

| Code | Meaning |
|------|---------|
| 200 | Reward accepted (see `success` in the body). |
| 422 | Request body failed validation (e.g. missing `reward_value`). |
| 500 | Unexpected server error while dispatching the reward. |

## Behavior

1. The handler builds a kernel-side `ReportRewardQuery`
   (`aios/memory/schemas.py`) from the request body.
2. It dispatches through the normal path:
   `execute_request` → memory queue → `FIFOScheduler.process_memory_requests`
   → `MemoryManager.address_request` → `MemoryManager.report_reward`.
3. `report_reward` looks up each `memory_id` in
   `MemoryManager._pending_reward_decisions` (populated when the
   novelty/similarity/redundancy gates made a decision for that memory)
   and replays every recorded `(bandit, arm, context)` decision into
   `PolicyManager.update` using **naive equal-credit** — the full
   `reward_value` is applied to each distinct bandit decision, not
   split. Consumed entries are then removed.

### Requires the adaptive policy to be enabled

The reward only updates the bandits when the adaptive policy is on:

```yaml
# aios/config/config.yaml
memory:
  adaptive_policy:
    enabled: true        # required for rewards to update the bandits
    alpha: 1.0
    # trial_log: "logs/policy_trials.jsonl"   # optional per-trial JSONL
```

When `enabled: false` (the default / frozen baseline), the endpoint
still returns `success: true` but is a **safe no-op** — no bandits
exist to update. This means a harness can always report rewards without
first checking whether the policy is on.

## Examples

### curl

```bash
curl -s -X POST http://localhost:8000/memory/report_reward \
  -H "Content-Type: application/json" \
  -d '{
        "agent_name": "JudgeAgent",
        "memory_ids_involved": ["mem_a", "mem_b"],
        "reward_value": 0.83,
        "trial_metadata": {"trial_id": "trial-0042"}
      }'
```

### Python (no SDK dependency)

```python
import requests

resp = requests.post(
    "http://localhost:8000/memory/report_reward",
    json={
        "agent_name": "JudgeAgent",
        "memory_ids_involved": ["mem_a", "mem_b"],
        "reward_value": 0.83,
        "trial_metadata": {"trial_id": "trial-0042"},
    },
    timeout=30,
)
resp.raise_for_status()
print(resp.json())   # {"success": true, "error": null, ...}
```

## How `memory_ids_involved` maps back to bandit decisions

The gates record their decisions keyed by the memory IDs they touch:

- **Novelty gate** (at `add_memory`) records against the *written*
  memory's ID.
- **Similarity + redundancy gates** (at `retrieve_memory`) record
  against each *retrieved* memory's ID.

So `memory_ids_involved` should contain the IDs the trial actually used
(written and/or retrieved). Any ID with no recorded decision is simply
skipped. A memory touched by multiple gates has all of its decisions
updated with the same reward.

> Note: the retrieve gates can only attribute rewards if the provider's
> `retrieve_memory` results carry a `memory_id`. The in-house provider
> does; verify the same for other providers (e.g. Mem0) before relying
> on similarity/redundancy learning with them.

## Verification (what was tested)

- Endpoint wiring, request parsing, response shape, and validation
  were verified with FastAPI's `TestClient` against the exact handler
  body: happy path → 200 `success: true` with a correctly-built
  `ReportRewardQuery` (`operation_type="report_reward"`); missing
  `reward_value` → 422 (not 500).
- The change to `runtime/launch.py` is purely additive (+78 lines, zero
  deletions): a new import, the `ReportRewardRequest` model, and the new
  route. The existing `/query` endpoint and its four query types are
  untouched.

## Related

- `aios/memory/schemas.py` — `ReportRewardQuery` / `ReportRewardResponse`
- `aios/memory/manager.py` — `report_reward` handler + `_pending_reward_decisions`
- `aios/memory/policy.py` — `PolicyManager` (the LinUCB bandits)
- `.kiro/steering/memory-providers.md` — adaptive policy overview
- `.kiro/steering/sdk-and-api.md` — HTTP API reference

## Reward normalization: confirmed insertion point and denominator

Investigation for the upcoming reward-normalization change (recorded
here before any code is written).

### Chosen insertion point (exactly one place)

`PolicyManager.update(bandit_name, arm_index, context_vector,
reward_value)` in `aios/memory/policy.py` (the method beginning at the
`def update(` around line 426).

Rationale — this is the single choke point every bandit update flows
through. `MemoryManager.report_reward` (`aios/memory/manager.py`, the
loop that pops from `_pending_reward_decisions` and calls
`self.policy.update(bandit_name, arm_index, context_vector,
float(reward_value))`) replays *N* decisions per trial, calling
`PolicyManager.update` once per decision. `PolicyManager.update` in turn
is the sole caller of the per-arm `LinUCBBandit.update`. Normalizing
inside `PolicyManager.update` therefore covers all three current
bandits (novelty, similarity, redundancy) **and** any future bandit with
a single conversion, and keeps `report_reward` free of scale knowledge.
Normalizing in `report_reward` would be per-call-site and would miss any
future direct caller of `PolicyManager.update`.

### Confirmed denominator

Fixed denominator: **5.0**, confirmed against the judge documentation —
not assumed.

Source: the evaluation paper (`paper_1.tex` §Evaluation, line ~619;
mirrored in `paper_2.tex` line ~469): "Each trial is scored by GPT-5.4
along three dimensions on a 1--5 scale" (Profile Usage, Task Usage,
Integration). The abstract restates it as a "5-point scale"
(`paper_1.tex` line ~59). The reward is a flat per-dimension score, not
a weighted composite of criteria, so the practical maximum is a flat
5.0 — there is no criteria/component weighting to derive a different
max from.

Caveat to carry into the implementation subtask: the judge scale is
**1–5, not 0–5** (floor is 1). A plain `reward / 5.0` maps the range to
`[0.2, 1.0]` rather than `[0, 1]`. Whether to also subtract the floor
(min-max to `[0, 1]`) is an implementation decision for the next
subtask; this subtask only confirms the fixed max denominator is 5.0.
