# Audit Zero-Retrieval — Mechanical Diagnosis (five open items)

Follow-up to `ADAPTIVE_POLICY_COMBINED_FIX_PILOT_REPORT.md`, addressing
the five items raised in review. This is a mechanical read + live
reproduction, not narrative. All queries run against the SAME live
kernel (`:8000`) that produced the pilot, for the SAME pilot user_id.

Target user_id (byte-for-byte):
`dana_morales_8a598d96_s0__kernel_shared_adaptive` (note the DOUBLE
underscore before `kernel`).
Resolved collection (both paths): `mem0_memories_dana_morales_8a598d96_s0_kernel_shared_adaptive`.

## Item 1 — exact audit user_id, diffed (not asserted)

The harness passes `trial_data.user_id` verbatim to both
`_audit_shared_memories(user_id, ...)` (pipeline.py:172) and the
AssistantAgent (`assistant_agent.user_id = trial_data.user_id`,
pipeline.py:145). So audit and assistant use the **identical** user_id
string — confirmed by reading the call sites, not inferred. The
in-process reproduction below uses that same literal string.

## Item 2 — transport: audit is HTTP (confirmed)

`_audit_shared_memories` (pipeline.py:270+) builds a `MemoryQuery` and
calls `send_request(writer_agent, query_obj, config.get_kernel_url())`
— HTTP to the kernel. Its per-writer params (pipeline.py ~305):
`{content, k=AUDIT_TOP_K(=20), user_id, sharing_policy="shared",
agent_name=writer_agent}` for `writer_agent in ["profile_agent",
"task_agent"]`.

My earlier disambiguation was in-process AND omitted
`sharing_policy`/`agent_name`, so it did NOT reproduce the audit path.
Corrected below with an exact HTTP replay.

## Live HTTP replay against the running kernel (same UID)

| query (HTTP `/query`) | count |
|---|---|
| agent=profile_agent, sharing_policy=shared, k=20 (EXACT audit) | **0** |
| agent=task_agent, sharing_policy=shared, k=20 (EXACT audit) | **0** |
| agent=assistant_agent, NO sharing_policy | **1** |
| agent=assistant_agent, sharing_policy=shared | **0** |
| agent=profile_agent, NO sharing_policy | **1** |

The single record returned (no-policy) is
`owner=assistant_agent, policy=private, memory_type=conversation`. With
`sharing_policy=shared`, `_apply_sharing_filter` correctly drops that
private record → 0. So the audit's 0 is *partly* the sharing filter
working as designed on a private record — but that's downstream of the
real problem: only 1 of 5 records is visible over HTTP at all.

## The actual contradiction (HTTP vs in-process, same store, same UID)

In-process, fresh `Mem0Provider` on the same on-disk store, same UID:

```
resolved collection: mem0_memories_dana_morales_8a598d96_s0_kernel_shared_adaptive
get_all(filters={"user_id": UID}) -> 5 items:
  owner=profile_agent     policy=shared    mt=profile
  owner=assistant_agent   policy=private   mt=conversation   (x4)
```

So:
- **In-process: 5 records** (including the `profile_agent/shared`
  record the audit needs).
- **HTTP (running kernel): 1 record** (only a private conversation),
  0 once the shared filter is applied.

Both resolve the **same collection name**, and the store on disk
genuinely holds all 5.

## Item 4 — truncation/hash-suffix: RULED OUT for this user_id

The leading prior suspicion (long user_id → truncated/hashed collision)
does not apply here: this user_id is short enough that
`_collection_name_for_user` produces the un-suffixed name
`mem0_memories_dana_morales_8a598d96_s0_kernel_shared_adaptive` (no hash
suffix), and the in-process path finds all 5 records under that exact
name. Both paths agree on the collection. (Other, longer session ids in
the run DID get hash suffixes — e.g.
`..._kernel_sharedff432b07` — but that is not what's causing the
0-retrieval, since even this un-truncated one exhibits it.)

## Item 5 — personalization "leaking through": explained + third data point

The assistant responses cite profile details even though the audit sees
0. Two contributing facts, now separated:
1. The audit's `shared_memory_count` counts only shared-policy audited
   records; it is a metric-scoping quantity (established earlier), so it
   reads 0 here.
2. The assistant's own personalization runs through the kernel's
   `ContextInjector` (a separate in-kernel retrieval on the chat path),
   NOT the harness audit HTTP fan-out. If the injector's retrieval sees
   even the profile once, personalization leaks in.
   **Third data point (assistant path vs audit path):** over HTTP the
   assistant-routed retrieve returns 1 and the writer-agent-routed audit
   returns 0/0 — both are starved (1 of 5), so the defect is NOT purely
   in the harness audit code; the kernel's HTTP `retrieve_memory` itself
   under-returns (1 of 5) relative to a fresh in-process provider (5 of
   5). That points at the **running kernel's provider instance**, not
   the audit query construction.

## Leading root-cause hypothesis (scoped, not yet fixed)

The running kernel's long-lived `Mem0Provider` caches one `Memory`
client per user_id (`_get_client_for_user` → `_user_clients`), created
the first time that user_id was seen, over the shared ChromaDB
`PersistentClient`. A fresh script process opens a new PersistentClient
that reads full on-disk state and sees all 5. The divergence (kernel 1
vs fresh 5) is most consistent with a **stale / snapshot-limited view in
the kernel's cached per-user Mem0 client or its ChromaDB collection
handle** — i.e. records committed to the same on-disk collection (by the
same or another agent/process) are not all visible through the kernel's
cached client, whereas a freshly-opened client sees them.

This is a hypothesis pinned to the 1-vs-5 evidence; confirming it needs
a targeted check of the kernel's cached-client behavior (e.g. whether
forcing a fresh `_get_client_for_user` or a collection `.count()` inside
the kernel process reports 1 or 5). Explicitly NOT the similarity fix
(that computes correctly when records are present) and NOT user_id
truncation (collection names match).

## Not yet checked (item 3 — pre-existing vs new-with-sessions)

Whether the original one-shot 150-trial benchmark shows the same
0-result audit pattern is NOT determined here. It requires inspecting a
one-shot run's logs/results rather than the accumulating-session pilot.
Flagged as open.
