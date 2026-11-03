# Kernel Retrieval Path

Since NeurIPS Subtask 8 the steps below are the memory pipeline library,
`aios/memory/pipeline/` (`Selector.select`, then `Formatter.build` for
the block), which the kernel and the replicated agents both run
(`docs/REPLICATED_LOGIC.md`). `retrieve_for_agent` and the injector
delegate to `MemoryPipeline` over the kernel's shared barrier and
identity registry. The block is printed in type order (profile, task
context, conversation, other) after ranking, cap and budget (Decision 1).

`MemoryManager.retrieve_for_agent` decides which memories an agent sees.
`ContextInjector.inject` and the `retrieve_memory` branch of
`MemoryManager.address_request` both call it, directly and never through
the syscall queue. It calls providers only through the provider contract
(`docs/PROVIDER_CONTRACT.md`): `search(query_text, user_id, top_k)`, with
no visibility filtering in the provider.

## Steps, in order

1. Identity: `_resolve_user_id` returns the per-request user, else
   `None`. `None` means own memories under `agent_name`, no shared fetch.
2. One barrier wait for that user. SDK search waits on the snapshot
   stamped at syscall acceptance; injection takes one at retrieval time.
3. Own fetch (`top_k = k`), then shared fetch (`top_k = 4k`) when
   `include_shared` and there is a resolved user. Both search the user's
   scope; without a resolved user, the agent's own scope, where a write
   that names no user is filed.
4. User partition, failing closed on a missing `user_id`.
5. Visibility: `apply_sharing_filter` (`aios/memory/pipeline/visibility.py`), the
   only place it runs; providers never filter. `sharing_policy="shared"` only selects the shared fetch; any
   other value also narrows the rule (`"private"`: own private only).
6. Exact-content dedupe of shared rows against earlier rows, own first.
7. Relevance threshold, only on rows with a score. Default 0.0: rank,
   drop nothing.
8. Sort by score when any row has one; otherwise keep provider order.
9. Count cap at `k`.

The injector then formats and applies `max_memory_tokens`. It reports
`after_budget`, `tokens_estimated` and `injected_memories`.

## Diagnostics

Returned by `retrieve_for_agent`: `resolved_user_id`, `own_fetched`,
`shared_fetched`, `after_partition`, `after_visibility`, `after_dedupe`,
`scores_present`, `threshold_used`, `after_threshold`, `after_cap`,
`top_k_used`,
`barrier_waits`. Own and shared counts are summed before dedupe.

They reach the harness as `injection_diagnostics`, a sibling of
`response` in the LLM response. `AssistantAgent.run` forwards them, and
`TrialResult.injection_diagnostics` stores them. Before this change the
kernel only logged them and the agent had no field to forward, so all
1,800 stored trials have them null or unrelated. With diagnostics present
the trial's `injection_status` is `confirmed`, including when nothing was
injected; the audit query is only a fallback.

## Scores

Until Subtask 5, `Mem0Provider.retrieve_memory` used `get_all`, which
returns no score and does not rank: `scores_present` was `false` in every
trial, `relevance_threshold` did nothing, and the rows were the first
`top_k` in storage order whatever the query.

Since Subtask 5, every conforming provider's `search` is scored and
ranked: Mem0 by the cosine similarity of the pinned embedding (computed
from the raw Chroma distance, not Mem0's own `search()` score, which is
inverted; see `docs/PROVIDER_CONTRACT.md`), the in-house Chroma provider
by cosine similarity. `scores_present` is `true`, and `threshold_used`
reports the threshold applied. At the default of 0.0 nothing is dropped;
the sort and cap now act on similarity instead of storage order, which
changes nothing while a user has fewer memories than the cap.

## Behavior changes

Intended, and neither fires on a user with few memories:

- **Explicit `top_k`.** `get_all` silently returned at most 20 rows. A
  shared fetch now reads `4k` rows, so with `k=10` a user's rows 21-40
  become candidates.
- **Count cap.** `max_injected_memories` only set the fetch size, so the
  merged list could exceed it. It is now a real cap.

Also changed:

- **SDK search visibility.** It no longer returns another agent's
  private memory for the same user. With `sharing_policy="shared"` it
  now returns the agent's own private rows too, not only shared ones.
- **SDK search threshold.** The threshold now applies to SDK search on
  providers that return scores (Zep).
- **`memory_id` on results.** All providers now return it. The agents'
  upsert checks therefore update in place; before, they found a match
  with no id and did neither an update nor a create. Their
  `update_memory` calls now pass `metadata.user_id`, because without it
  Mem0 looks in the default user's collection.
- **`owner_agent` stamped on write.** `address_request` defaults it to
  the writing agent. Without this the visibility rule hides a memory
  from its own author. Rows already stored without one stay hidden.
- **Dedupe after visibility.** A shared row with the same text as
  another agent's private row used to be dropped as a duplicate, and
  then the private row was dropped too. The shared row now survives.
- **One barrier wait per injection.** It waited twice for the same user.
- **Unscoped SDK search on the in-house provider.** The partition check
  now requires `metadata.user_id == agent_name`.

Unchanged: dedupe does not remove duplicates inside the own list, because
own retrieval returns every row of the user. So a text stored twice can
be injected twice when both rows are own-list rows.

## Not on this path

`get_memory` applies the same owner-or-shared rule in `address_request`
(`_can_read`), failing closed on a missing owner. `retrieve_memory_raw`
now runs `retrieve_for_agent` and returns its rows as notes (until
Subtask 5 it had its own provider-level filter and Mem0's 20-row limit).

## Writes

Every write reaches the store through `MemoryManager.address_request`.

**One stamping site.** `MemoryManager.stamp_syscall` holds the barrier
stamping. `SyscallExecutor` calls it before enqueueing a memory syscall;
`ConversationExtractor.extract_async` calls it directly. The extractor
does not go through the executor: that would block on the memory queue,
and from the background thread the stamp could land after the chat
response.

**Stamped on the request thread.** The write itself runs on a daemon
thread, but `extract_async` stamps it first, before `execute_request`
returns. A retrieval accepted after the chat response therefore always
finds the write pending and waits for it. `address_request` releases it
in a `finally`; the extractor releases it if the thread cannot start.
The wait is bounded by `write_barrier.timeout_ms`, as for any write.

**Updates are stamped too.** Since Subtask 5 `update_memory` acquires
the barrier at acceptance and releases it in a `finally`, like a write,
so a retrieval accepted after an update reads the new content.

**By-id writes are owner-only.** `update_memory` and `remove_memory`
first fetch the memory; anyone but its owner gets "Memory not found",
also for a shared memory, which others can read. The fetch uses the
caller's `user_id` when given, otherwise the agent's own scope, then the
provider's default, because Mem0 cannot find a row from its id alone.

A conversation memory is private to the agent that had the conversation,
so that agent can see it on later turns and no other agent can. In a
single-turn trial it is written after injection, so it never appears in
that trial's `own_fetched` or `after_visibility`.

## Before/after check

`scripts/retrieval_behavior_check.py` replays 10 seeded users. The
harness cannot be used for this: it has no seed option, and its agents
write LLM-generated text. To capture the block, add this temporarily
after the "Injection diagnostics" log line in `execute_request`, and set
`AIOS_CAPTURE` to the path given as `--capture`:

```python
import json, os
with open(os.environ["AIOS_CAPTURE"], "a") as _c:
    _c.write(json.dumps({
        "user_id": request_user_id,
        "block": query.messages[0].get("content"),
    }) + "\n")
```

Result on 2026-11-01, `workshop-postrun` code vs this change, qwen2.5:7b,
real kernel, Mem0 and ChromaDB: all 10 injected sets identical, in the
same order (counts 3, 3, 3, 5, 2, 3, 3, 5, 3, 6). Neither the cap nor
the larger `top_k` fired. `scripts/retrieval_smoke.py` forces both.
