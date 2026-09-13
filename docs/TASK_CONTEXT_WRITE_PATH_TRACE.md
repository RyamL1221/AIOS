# Task-Context Write Path Trace + 1×15 Run Write Activity

Read-only trace (no code changed, nothing run) resolving the first fork
of the single-profile-memory-ceiling diagnosis: **is task_context
content ever constructed and written during a session like the 1×15
run?** Follows on `docs/GATE_REJECTION_DIAGNOSIS_FINAL.md` (which flagged
that only a single profile memory ever retrieved and no task_context
ever did).

## Finding (definitive)

**Task-context writes EXIST in code, fire UNCONDITIONALLY every
interaction, and DID fire during the 1×15 run — but they were REJECTED
at the kernel's novelty (add) gate, so no task_context memory was ever
stored.** This rules out hypothesis 1 ("never constructed/written") and
points at the gate — specifically the **novelty add-gate**, not the
similarity retrieve-gate that earlier subtasks examined.

## Code path (exact citations)

Harness (sibling checkout `../Cerebrum`):
- `benchmarks/shared_memory/pipeline.py:144-150` — `AgentPipeline.run_trial`
  Step 2 constructs and runs the TaskAgent every interaction:
  ```
  task_agent = TaskAgent("task_agent")
  task_agent.share_memory = self.share_memory
  task_agent.user_id = trial_data.user_id
  task_agent.llms = self.assistant_llms
  task_result = task_agent.run(json.dumps(trial_data.task_context.model_dump()))
  ```
  This is symmetric to and distinct from the ProfileAgent write at
  `pipeline.py:110-116`. **Neither is behind any `if` guard** — both run
  every trial.

SDK agent (`cerebrum/example/agents/task_agent/agent.py`):
- `TaskAgent.run()` (line ~47): extracts structured task context via
  `_extract_task_context` (LLM JSON call), then calls
  `_upsert_task_memory(user_id, context_data)`.
- `_upsert_task_memory()` (line ~176): searches for an existing
  task_context memory; if none, the **else branch** builds metadata with
  `memory_type=MEMORY_TYPE_TASK_CONTEXT` and
  `sharing_policy=POLICY_SHARED` (since `share_memory=True` for
  `kernel_shared_adaptive`) and calls `create_memory(...)` → the kernel
  `add_memory` syscall.

### Conditionality (two guards, both passed this run)
1. **user_id must be non-empty** (`agent.py` run(): "Skipping memory
   write: no explicit user_id"). The harness sets
   `task_agent.user_id = trial_data.user_id`, so this guard passed — and
   the kernel evidence below (22 task_context add attempts) confirms the
   write was actually issued.
2. **`_extract_task_context` must not throw** — it makes a gpt-4o JSON
   call; on exception, `run()` returns `Error:` and skips the write. No
   such error occurred (writes reached the kernel every trial).

So the write is **effectively unconditional per interaction** given a
user_id and a successful extraction, both of which held.

## Run evidence (kernel.log, the authoritative record)

Searched the surviving 1×15 artifacts. Note two artifact caveats first:
- `../Cerebrum/results/subtask4_fresh_1x15_run.log` **still exists**
  (20,657 bytes, Sep 13 16:38 — the *valid* run's log; the earlier
  VPN-off failed attempt's log was the one removed). It contains **no**
  task_agent lines — the harness run log only logs harness-side events
  (Mem0 diagnostic, audit, report_reward), not agent writes, so absence
  there is not evidence of absence.
- The results JSON's `written_memories` field is **empty for all 15
  trials** — including for the profile write we know happened
  (`a0162e92…` was retrieved). So `written_memories` was not populated in
  the saved JSON and is **not** a reliable write signal. Not used as
  evidence.

**kernel.log (run window 16:30–16:38) is authoritative and shows the
writes firing and being rejected:**

- 110 `add_memory` mentions and 44 `task_context` mentions in-window.
- **29 novelty-gate evaluations**, split by `task_type`:

  | task_type | evals | admitted | rejected | max_sim range (mean) | thresholds used |
  |-----------|------:|---------:|---------:|----------------------|-----------------|
  | task_context | 22 | **0** | **22** | 0.482–0.587 (0.558) | 0.1, 0.2 |
  | profile | 7 | 1 | 6 | 0.000–1.000 (0.857) | 0.1, 0.2 |

Representative lines:
```
novelty gate: llm=gpt-4o task=task_context threshold=0.200 max_sim=0.519 -> admit=False
novelty gate: llm=gpt-5.4 task=task_context threshold=0.100 max_sim=0.482 -> admit=False
```

The novelty gate admits iff `max_sim < threshold`. Every task_context
write had `max_sim` ≈ 0.48–0.59, far **above** the bandit-selected
novelty thresholds (0.1, 0.2), so **admit=False on all 22** — the
task_context memory was never written to the store.

(The profile task_type shows 1 admit at max_sim=0.0 — the very first
profile write, nothing to compare against — then rejects; that single
admitted write is the `a0162e92…` profile memory that every retrieval
later surfaced. Its rejections are correct dedupe of an already-stored
profile.)

## Verdict against hypothesis 1

**RULED OUT: "task-context writes are never issued."** They are issued
every interaction and reached the kernel 22 times during the run.

**Actual finding: task-context writes fire but are rejected at the
NOVELTY ADD-GATE** (`max_sim ~0.55 > novelty_threshold 0.1–0.2 →
admit=False`), so no task_context memory is ever stored, which is why
only the one admitted profile memory was ever available to retrieve. The
diagnosis now points at hypotheses 2–4 — and specifically re-centers it
on the **novelty (add) gate**, a different gate than the similarity
(retrieve) gate that `FAILOPEN_EVENT_ACCOUNTING.md` and
`GATE_REJECTION_JOINED_TABLE.md` analyzed.

### Note for the next subtask (not resolved here)
There is a striking directional oddity worth investigating: the novelty
gate admits iff `max_sim < threshold`, and the adaptive bandit here
picked *low* novelty thresholds (0.1, 0.2). A low novelty threshold means
"only admit things very dissimilar to what's stored" — i.e. it is
*strict*, rejecting anything with `max_sim` above ~0.1–0.2. Since real
task_context memories sit at max_sim ~0.55, the low arm guarantees
rejection. Whether that arm choice is the bandit exploring, or whether
the novelty-gate admit direction is inverted relative to intent, is the
open question for the next step. This trace establishes only: writes
fire, and the novelty gate rejects them.

## Artifacts referenced
- `../Cerebrum/benchmarks/shared_memory/pipeline.py:110-116, 144-150`
- `../Cerebrum/cerebrum/example/agents/task_agent/agent.py` (`run`,
  `_upsert_task_memory`)
- `kernel.log` (PID 69841, run window 16:30–16:38): 22 task_context
  novelty-gate rejections, 0 admits
- `../Cerebrum/results/subtask4_fresh_1x15_run.log` (present; no
  agent-write lines by design)
- results JSON `written_memories` (empty; unreliable, not used)
