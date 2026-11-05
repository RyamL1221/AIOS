# Replicated-logic conditions: `replicated_mem0`, `replicated_inhouse`

Written before any agent code (NeurIPS Subtask 8), so the condition is
defined before any result exists.

## Purpose

The replicated-logic condition is the anti-strawman for kernel-managed
memory. Every agent runs the kernel's own memory code, in its own
process space, against the backend directly. If kernel-managed memory
beats it, the gain comes from where the logic runs, not from better
logic.

"The kernel's own code" is meant literally. The kernel's memory
pipeline is a library, `aios/memory/pipeline/`, that depends only on
the provider contract (`aios/memory/providers/base.py`) and the
`memory:` config. The kernel is a thin client of it, and so is each
replicated agent. An equivalence test proves the kernel path and a
direct library call give byte-identical memory blocks and identical
diagnostics for 20 seeded users. The LangGraph reproduction (Subtask 22)
uses the same library.

## The condition

- **Agents.** `ProfileAgent`, `TaskAgent` and `AssistantAgent` in
  Cerebrum `cerebrum/example/agents/replicated/`.
- **Pipeline instances.** Each agent builds its own
  `MemoryPipeline(provider, config)`, with its own provider client,
  write barrier and identity resolver.
- **Writes and retrieval.** The writers extract with the same LLM calls
  as the kernel conditions' writers and upsert through their pipeline,
  with the kernel writers' logic: search their own memories, update the
  memory of their type if found, create it otherwise. The assistant
  retrieves through its pipeline, prepends `build_block`'s output as a
  system message, exactly where the kernel injector puts it, and writes
  the conversation turn through its pipeline, as the kernel's extractor
  does.
- **Inference.** The kernel serves the LLM calls (`llm_chat`) and
  nothing else. `memory.auto_inject` and `memory.auto_extract` are off,
  and the harness refuses to run otherwise (the Subtask 6 pre-flight).
- **Config.** Each agent loads the kernel's `memory:` settings from
  `/memory/config` (threshold, count cap, token budget, barrier
  settings, embedding), so in the clean condition every copy matches
  the kernel's settings by construction.
- **Backend.** `replicated_mem0` uses the kernel's `Mem0Provider`
  (scored search; since Subtask 9 the kernel's `infer` setting, read
  from `/memory/config` `backend_extraction`, with the pinned
  `memory.backend_llm`, so it extracts facts as the kernel's Mem0 does). `replicated_inhouse`
  uses the kernel's `ChromaInHouseProvider`. Each condition has its own
  store, separate from the kernel's.
- **Records.** Every trial records `locus` (`kernel`, `replicated`,
  `native`, or `none` for the no-memory baselines) and
  `pipeline_version`, a hash of the library's source, so a later
  heterogeneity condition shows as a version difference.

## The three inherent differences

Replicated logic differs from kernel-managed memory in three ways that
come with where the code runs, and in nothing else.

1. **No shared write barrier.** Each agent's barrier is local, so it
   orders only that agent's own writes. A read by one agent cannot wait
   for another agent's write that is accepted but not yet durable.
   Cross-agent read-after-write cannot be enforced from inside one
   agent. A test shows it: ProfileAgent writes, the assistant reads
   immediately, before the write is durable, and does not see it. The
   kernel, with one barrier shared by all agents, makes the same read
   wait and see the write.
2. **No shared identity resolution.** Each agent resolves `user_id`
   from its own request. There is no cross-agent registry of the users
   other agents have written for: each agent's resolver knows only its
   own writes.
3. **No single policy instance.** Each agent holds its own copy of the
   pipeline and its config. In the clean condition the copies are
   identical, the same source (`pipeline_version`) and the same
   settings. Heterogeneity (Subtask 10) and the faulty agent (Subtask
   18) are the conditions where they diverge.

## Differences that are not memory logic

These are recorded so they are not mistaken for logic differences:

- **Conversation write timing.** The kernel writes the conversation on
  a background thread after the reply. The replicated assistant writes
  it synchronously after the reply. Both are excluded from latency.
- **Stamping.** The kernel stamps a write against its barrier when the
  syscall is accepted. A replicated agent acquires its own barrier when
  it calls `write`. With a local barrier, the two are the same moment.
- **Memory operations are in-process.** There are no HTTP or scheduler
  hops for memory, only for LLM calls.

## Expected result

On this benchmark, writers run sequentially, every request carries an
explicit `user_id`, and the copies are identical. So the design predicts
a **tie** with `kernel_shared` on the same backend, and a tie is the
correct result. Separation is predicted only under stress: concurrent
cross-agent writes, heterogeneous copies, a faulty agent. If replicated
beats kernel by more than noise (0.25 on a judge mean), that means the
kernel path does something the library does not, and it is investigated
before moving on.

## Block order (Decision 1)

The library ranks candidates by score for the threshold, the count cap
and the token budget. It then prints the block in a fixed type order:
profile, task context, conversation, then any other type, each in score
order. Before this, the kernel printed the block in score order (task
context first since Subtask 5). The v2 baseline was produced in storage
order, profile first. Because the block order changes, `kernel_shared`
is re-run under the library for the comparison.
