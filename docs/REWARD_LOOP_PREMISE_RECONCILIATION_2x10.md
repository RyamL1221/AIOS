# Reward-Loop Premise Reconciliation — genuine 2×10 pilot on current code

Read-only premise-confirmation step (no code changes). Resolves the
conflict between:

- **Master-prompt premise** (from prior 2×10 pilots, kernel PIDs 39869 /
  77341): every `report_reward` arrives with empty `memory_ids_involved`,
  so 0 reward events are logged and all three LinUCB bandits stay pinned
  at arm 0.
- **This session's Cerebrum-side trace** (`Cerebrum/docs/MEMORY_IDS_INVOLVED_TRACE.md`,
  Cerebrum HEAD `30e7afc`), §5: current pilots (5×4 and 3×12) show the
  audit path returning real memory IDs (`merged_count=4 → unique_count=2
  → has_ids`), attributing the historical empty symptom to a now-closed
  Mem0 id-gap.

**Verdict: (b) — the loop is still broken specifically at the 2×10
`kernel_shared_adaptive` config on current code, even though the id-gap
fix is present. The master prompt's "0 reward events / arm-0" premise is
CONFIRMED CURRENT, not stale.** The break is *not* the id-gap; it is that
retrieval returns **zero memories** per trial, so there is no id to read
in the first place.

---

## 1. Current on-disk state confirms the id-gap fix IS present

`aios/memory/providers/mem0.py`, `retrieve_memory`, builds every
`search_results` entry with `"memory_id": item.get("id")` — **line 1311**
(sourced from the Mem0 record id via `get_all()`), plus a real
`"similarity"` from the raw ChromaDB distance (~line 1330). So the AIOS
side reliably populates `memory_id` on every returned entry. The id-gap
described in `Cerebrum/docs/mem0-search-results-memory-id-gap.md` is
genuinely closed kernel-side.

The Cerebrum harness (on disk at `../Cerebrum`, HEAD `30e7afc`,
`feature/self-improving-memory`) reads that field: `injected_memory_ids`
is built from `mem.get("memory_id") or mem.get("id")`
(`benchmarks/shared_memory/pipeline.py:428`) and copied verbatim into
`memory_ids_involved` (`run_evaluation.py:523-526`), then POSTed to
`/memory/report_reward` (`run_evaluation.py:566-576`).

## 2. The genuine 2×10 run (current code, no restart)

- **Config:** `--users 2 --interactions-per-user 10` (20 trials),
  `--method kernel_shared_adaptive`, gpt-4o assistant / gpt-5.4 judge.
- **Kernel:** PID **77341**, started `Thu Sep 10 13:54:13 2026`, still
  running (`ps` elapsed 54:21 at check time) — **one of the two exact
  PIDs the master prompt cites**, and continuously up across the whole
  run. Live `GET /memory/gating_status` on it returns
  `adaptive_policy_enabled: true, static_thresholds_enabled: false` —
  the correct `kernel_shared_adaptive` gating.
- **Artifact used:** `Cerebrum/results/clean_combined_pilot_rerun/`
  (results JSON `timestamp: 2026-09-10T14:04:53`) cross-checked against
  `AIOS/kernel.log` and `AIOS/logs/policy_trials.jsonl`. The 20
  `report_reward` POSTs in `kernel.log` span **13:57:18 → 14:04:53**,
  entirely inside the single PID-77341 session — **no mid-run restart**.
  (The earlier `clean_combined_pilot`, timestamp 13:30, is a second 2×10
  run with the identical outcome; both are reported below.)

This is a genuine 2×10 `kernel_shared_adaptive` run on current code, not
a differently-shaped sample and not solely inferred from a historical
report.

## 3. Concrete numbers

**Harness side** (`results_kernel_shared_adaptive.json`, per-trial
`retrieval_log`):

| metric | clean_combined_pilot_rerun | clean_combined_pilot |
|--------|:--:|:--:|
| trials | 20 | 20 |
| trials with non-empty `injected_memory_ids` | **0 / 20** | **0 / 20** |
| total injected ids across all trials | 0 | 0 |
| trials with non-empty `retrieved_memories` | **0 / 20** | **0 / 20** |
| `injection_status` | `unknown` ×20 | `unknown` ×20 |
| `reward_value` range (judge) | 1.667–3.0 (varies) | 2.333–3.0 (varies) |

**Kernel side** (`AIOS/kernel.log`, PID 77341):

- **20** `report_reward` POSTs; **all 20** with `memory_ids_involved=[]`
  (0 non-empty). Every one logged `report_reward: applied 0 bandit
  update(s)`.
- **0** `report_reward: reward applied to …` lines (the line that fires
  only on a genuine bandit update). So **PolicyManager.update invocation
  count = 0**.

**Policy log** (`AIOS/logs/policy_trials.jsonl`): 182 `select` events,
**0 `reward` events**. Arm distribution — every gate pinned at arm 0:
novelty `{0: 22}`, similarity `{0: 80}`, redundancy `{0: 80}`. **No
bandit arm moved off arm 0 for any of the three gates.**

## 4. Why it's still broken — and why it is NOT the id-gap

The empty `memory_ids_involved` at 2×10 is **not** the id-gap
(entries-present-but-no-id-field). It is one hop earlier: **no entries at
all.**

The harness builds `retrieval_log` via two branches
(`pipeline.py:167-184`):

1. kernel injection diagnostics, if `injected_count > 0` → status
   `confirmed`; else
2. `_audit_shared_memories` fan-out; if `shared_memory_count > 0` →
   `audit_inferred`; else (with `share_memory`) → **`unknown`** + a
   logged "audit query returned 0 results" warning
   (`pipeline.py:176-183`).

All 20 trials landed on `unknown`, which means **both** paths yielded
nothing: the kernel returned no inline diagnostics AND the per-writer
audit fan-out (`WRITER_AGENTS = ["profile_agent","task_agent"]`,
`AUDIT_TOP_K=20`, `user_id`=session user, `sharing_policy="shared"`,
`pipeline.py:304-312`) returned 0 rows. With `retrieved_memories=[]`, the
id-read at `pipeline.py:428` never executes — there is nothing to read an
id *from*. The id-gap fix is therefore irrelevant to this failure: fixing
"entries have no id" cannot help when there are no entries.

Corroborating kernel-side detail: `report_reward` logs
`pending_decisions now tracks 2–3 memory_id(s)` throughout. So the kernel
**did** record novelty (add-time) decisions — writes succeeded and were
gated — but because retrieval returned 0, no retrieve-gate decisions were
recorded and no reward ever consumed the pending novelty decisions. The
break is unambiguously on the **retrieval/audit** side, not the write
side and not the id-attribution side.

## 5. Reconciliation against the trace doc's §5 "has_ids" claim

The two observations don't contradict each other about the *code* — they
describe **different runs**:

- The trace doc §5's `merged_count=4 → unique_count=2 → has_ids` +
  `memory_ids_involved=['f9be400e…','5893c2f7…']` came from the **5×4 and
  3×12** pilots run **Sep 9** (`results/session_pilot_5x4_gpt/`,
  `results/session_pilot_3x12_gpt/`, mtimes Sep 9 16:56 / 17:14). In
  those, the audit path did return rows, so `audit_inferred` fired and
  ids were read.
- The **2×10** `kernel_shared_adaptive` clean pilots (**Sep 10**, the
  config the master prompt's claim is actually about) retrieve **0**
  memories per trial (`injection_status=unknown` ×20), so
  `injected_memory_ids` is empty for lack of any retrieved memory.

So the conflict resolves as **explanation (b), not (a)**: the id-gap fix
is real and present, but it does not close the loop at 2×10 because a
*distinct, still-open* retrieval/audit issue zeroes out retrieval for
this config. Whatever differs between the Sep-9 5×4/3×12 runs (audit
returned rows) and the Sep-10 2×10 runs (audit returns 0) is the live
open question — candidate differences to investigate (NOT resolved here):
per-writer-agent audit fan-out scoping, `sharing_policy="shared"`
visibility, within-session Mem0 dedupe of same-user writes (the known
"no within-session accumulation" finding — `shared_memory_count` pins
low), or session-length / user-count interactions in the accumulating
harness. This reconciliation step does not pick among those; it only
establishes that the premise holds at 2×10.

## 6. Gating conclusion for Subtask 2

The master prompt's "reward events: 0 / all bandits at arm 0" premise is
**confirmed on current code at the exact 2×10 config** — not stale, not
pre-fix. Therefore Subtask 2 is **"implement/locate the fix for the
still-broken retrieval/audit path"**, NOT "confirm already-fixed and move
to verification." The specific fix target is the zero-retrieval at 2×10
(the `unknown`-status audit path), which is upstream of and independent
from the already-closed Mem0 id-gap. No fix is proposed here.

## 7. Evidence (files, no edits)

- `aios/memory/providers/mem0.py:1311` — `memory_id` populated per entry
  (id-gap fix present).
- `Cerebrum/benchmarks/shared_memory/pipeline.py:167-184` (branch /
  `unknown` status), `:270,:304-312` (audit fan-out request), `:428`,
  `:436-437` (id read), `:449-459` (id-gap warning).
- `Cerebrum/benchmarks/shared_memory/run_evaluation.py:523-526`
  (`memory_ids_involved` = `injected_memory_ids`), `:566-576`
  (`POST /memory/report_reward`).
- `Cerebrum/results/clean_combined_pilot_rerun/results_kernel_shared_adaptive.json`
  (20 trials, 0 non-empty ids, `unknown` ×20; ts 14:04:53) and
  `.../clean_combined_pilot/...` (ts 13:30; identical outcome).
- `AIOS/kernel.log` — 20 `report_reward memory_ids_involved=[]` +
  `applied 0 bandit update(s)`; 0 `reward applied`; POSTs 13:57:18–14:04:53.
- `AIOS/logs/policy_trials.jsonl` — 182 `select`, 0 `reward`; arms all 0.
- Kernel PID 77341, `lstart Thu Sep 10 13:54:13 2026`, no restart.
