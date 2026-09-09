# Trial-Isolation Intent vs. Experiment Design — Sparse-Retrieval Investigation (Subtask 4)

Determination of what "shared memory" is **intended** to mean for
`kernel_shared` / `kernel_shared_adaptive`, from the paper draft and
steering/spec documentation, and reconciliation with the truncation
collision found in subtask 3. Documentation-and-intent analysis only —
**no code or design docs were modified**. Builds on subtasks 1–3
(662d93f, 8f3f7ef, 4ab8a9c).

---

## 1. Determination: "shared" = within-trial, cross-agent — NOT cross-trial

The intended semantics of shared memory in this experiment is
**within-trial sharing across agents for a single synthetic user
identity**. Cross-trial accumulation (memory persisting/growing across
trials for the same synthetic user) is **not** part of the design, and
per-trial isolation is **deliberate**. Four independent sources agree.

### 1a. Paper draft (`~/Downloads/Kernel-Managed_Shared_Memory_for_System_Wide_Personalization.tex`)

- **Condition definition (line ~425):** `kernel_shared` — *"ProfileAgent/TaskAgent write `shared` memories; kernel enforces ordering, identity resolution, visibility, and cross-agent injection."* The mechanism is agent→agent injection, not trial→trial carryover.
- **Visibility rule (lines ~285–297):** `visible(m, a_i) = True if owner == a_i, True if sharing_policy == "shared", else False.` "Shared" is defined purely as **cross-agent visibility within a `user_id`** — nothing about time or trial sequence.
- **Trial definition (lines ~436–438):** *"Each trial generates a synthetic user profile, a synthetic task context, and a vague follow-up query … intentionally underspecified so personalized content must come from injected memory rather than the query itself."* Each trial is a self-contained unit that manufactures its own identity; the personalization signal is expected to flow ProfileAgent/TaskAgent → (kernel) → AssistantAgent **inside that trial**.
- **Privacy verification (lines ~318–329):** measured at *"fully private ($n=450$) … $0/450$ exposure"* and *"fully shared ($n=450$)."* The $n=450$ granularity is per-trial (matching subtask 1's ~450 per-trial collections), confirming the unit of analysis is the individual trial, not an accumulating user history.
- No occurrence of "across trials," "accumulate," "persistent per user," or "per session" appears in the methodology/evaluation sections.

### 1b. Cerebrum steering/spec: `benchmark-memory-isolation-v2`

The spec is explicit that a consistent `user_id` exists to enable
**within-trial cross-agent** sharing, and to make `sharing_policy` the
sole independent variable — not to accumulate across trials:

- **Trial** (glossary): *"A single end-to-end execution of the evaluation pipeline: generate synthetic data, run all three agents, evaluate the assistant response, and record metrics."*
- **Trial_User_ID** (glossary): *"A consistent `user_id` string derived from the Synthetic_Profile's `user_name` that is passed to all three agents (ProfileAgent, TaskAgent, AssistantAgent) **within a single Trial**, so the only experimental variable between conditions is `sharing_policy`."*
- Requirement 2 framing: *"consistent `user_id` across all three agents in a trial so the only experimental variable is `sharing_policy`."*

The shared `user_id` is scoped to *"within a single Trial"* — the design intent is cross-agent, not cross-trial.

### 1c. Harness code as written (`benchmarks/shared_memory/synth.py`)

Per-trial isolation is a **deliberate construction**, not an accident of
synthetic-profile generation:

- `generate_trial_data` (lines ~516–533): *"The user_id format is `{name}_{run_id}_t{trial_index}` … and trial_index guarantees uniqueness,"* implemented as `user_id = f"{base_name}_{self.run_id}_t{trial_index}"`.
- `MethodPipeline` additionally appends `__{method}` (subtask 2), giving the full observed form `{name}_{run_id}_t{idx}__{method}` (e.g. `alexandra_thompson_adaptive_report_v2_qwen25_7b_t23__kernel_shared_adaptive`).

The `run_id` and `t{trial_index}` discriminators exist **specifically to
guarantee uniqueness per trial** — someone deliberately isolated each
trial into its own `user_id` namespace. The trial-index embedding is
therefore evidence of *intentional isolation*, which resolves the core
question: cross-trial accumulation was never the intended behavior, so
its absence is by design.

### 1d. AIOS spec: `mem0-user-id-scoping` (what `user_id` is *for*)

This spec frames `user_id` as an **end-user identity** and treats
collapsing distinct identities into one namespace as a **bug**:

- *"queries Mem0/ChromaDB with `user_id=agent_name` … causes cross-user memory contamination … returns conversation memories from ALL end-users that agent has ever served … potentially leaking private context from one user into another user's session."* (bugfix.md)
- Intended fix: *"use the end-user's actual identifier (e.g., `"alex_martinez__kernel_shared"`) as the `user_id` filter … returning only conversation memories from that specific end-user."*

So the documented invariant is **one `user_id` = one isolated identity
namespace**; mixing two identities is explicitly a defect.

## 2. Reconciliation with subtask 3's truncation collision

Two facts must be held simultaneously:

1. **Cross-trial accumulation was never intended** (§1). Therefore the
   sparse-retrieval symptom (each collection holds only that trial's ~3
   writes, `shared_memory_count` clustering at 2) is **consistent with the
   intended design** — it is *not* a bug of "memory failing to accumulate,"
   because accumulation across trials was never part of the experiment.
   Subtasks 1–2's finding is thus reclassified as **expected behavior**,
   not a regression.

2. **The subtask-3 collision is a genuine, if currently-masked, violation
   of the per-identity isolation invariant** (§1d). The 63-char truncation
   merges two *distinct trial identities* —
   `…qwen25_7b_t23__kernel_shared_adaptive` and
   `…qwen25_7b_t31__kernel_shared_adaptive` (verified different profiles /
   projects in subtask 3) — into one physical ChromaDB collection. That is
   precisely the *cross-user contamination* `mem0-user-id-scoping`
   documents as a bug. It does **not** create the (never-intended)
   cross-trial accumulation; instead it risks the (explicitly-forbidden)
   cross-identity commingling.

**Why it currently doesn't corrupt results:** subtask 3 showed
`retrieve_memory` uses `get_all(filters={"user_id": <full untruncated
value>})`, so rows are filtered by the complete `user_id` metadata value
even when two identities share a collection. The collision is contained
at the row-filter layer today. It remains a latent violation: it depends
on that value-level filter staying correct, and it breaches the "one
`user_id` = one namespace" invariant at the physical-collection layer.

## 3. Answers to the subtask's explicit questions

- **What does "shared memory" mean here?** Within-trial, cross-agent
  visibility for a single synthetic user identity (ProfileAgent/TaskAgent
  → kernel → AssistantAgent), governed by the `sharing_policy=="shared"`
  visibility rule. Not cross-trial persistence; not cross-run.
- **Is the per-trial `user_id` intentional isolation or an accident?**
  Intentional. `synth.py` documents `trial_index` as a uniqueness
  guarantee and appends `run_id`; the isolation spec makes per-identity
  scoping a correctness goal.
- **Does subtask 3's collision violate the intended design?** Partially,
  and in a specific way: it does **not** matter for the "no cross-trial
  accumulation" property (that was never intended), but it **does** violate
  the documented per-identity isolation invariant (`mem0-user-id-scoping`)
  by merging two distinct trial identities into one collection — a real
  latent bug, currently masked by row-level `user_id` filtering.

## 4. Conclusion

The sparse-retrieval finding is **classified as expected behavior**:
kernel_shared/adaptive trials are designed to be per-trial isolated with
within-trial cross-agent sharing, so memories neither should nor do
accumulate across trials. The subtask-3 truncation collision is a
**separate, genuine latent defect** — a violation of the per-identity
isolation invariant documented in `mem0-user-id-scoping`, not a cause of
the sparse-retrieval symptom. Both should be reported distinctly: (a)
"no cross-trial accumulation" = intended; (b) "63-char truncation merges
distinct trial identities" = a real isolation-invariant violation to fix
regardless of its current masked impact.

## 5. Sources cited / reviewed (no modifications)

- `~/Downloads/Kernel-Managed_Shared_Memory_for_System_Wide_Personalization.tex`
  — condition table (l.~425), visibility rule (l.~285–297), trial
  definition (l.~436–438), privacy verification n=450 (l.~318–329)
- `Cerebrum/.kiro/specs/benchmark-memory-isolation-v2/{requirements,design,tasks}.md`
  — Trial / Trial_User_ID glossary, "within a single Trial" scoping
- `Cerebrum/benchmarks/shared_memory/synth.py` — `generate_trial_data`
  user_id format + "trial_index guarantees uniqueness"
- `AIOS/.kiro/specs/mem0-user-id-scoping/{bugfix,design}.md` — user_id as
  end-user identity; cross-user contamination as a documented bug
- `AIOS/.kiro/specs/mem0-chromadb-persistence/` — persistence = survive
  restart (not cross-trial accumulation)
- Cross-referenced: subtasks 1–3 reports (write scope, count/read path,
  scoping-collision evidence)
