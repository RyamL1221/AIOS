# Kernel Retrieval Path

`MemoryManager.retrieve_for_agent` decides which memories an agent sees.
`ContextInjector.inject` and the `retrieve_memory` branch of
`MemoryManager.address_request` both call it, directly and never through
the syscall queue.

## Steps, in order

1. Identity: `_resolve_user_id` returns the per-request user, else
   `None`. `None` means own memories under `agent_name`, no shared fetch.
2. One barrier wait for that user. SDK search waits on the snapshot
   stamped at syscall acceptance; injection takes one at retrieval time.
3. Own fetch (`top_k = k`), then shared fetch (`top_k = 4k`) when
   `include_shared` and there is a resolved user.
4. User partition, failing closed on a missing `user_id`.
5. Visibility: `_apply_sharing_filter`, always, even if the provider
   filtered. `sharing_policy="shared"` only selects the shared fetch; any
   other value also narrows the rule (`"private"`: own private only).
6. Exact-content dedupe of shared rows against earlier rows, own first.
7. Relevance threshold, only on rows with a score.
8. Sort by score when any row has one; otherwise keep provider order.
9. Count cap at `k`.

The injector then formats and applies `max_memory_tokens`. It reports
`after_budget`, `tokens_estimated` and `injected_memories`.

## Diagnostics

Returned by `retrieve_for_agent`: `resolved_user_id`, `own_fetched`,
`shared_fetched`, `after_partition`, `after_visibility`, `after_dedupe`,
`scores_present`, `after_threshold`, `after_cap`, `top_k_used`,
`barrier_waits`. Own and shared counts are summed before dedupe.

They reach the harness as `injection_diagnostics`, a sibling of
`response` in the LLM response. `AssistantAgent.run` forwards them, and
`TrialResult.injection_diagnostics` stores them. Before this change the
kernel only logged them and the agent had no field to forward, so all
1,800 stored trials have them null or unrelated. With diagnostics present
the trial's `injection_status` is `confirmed`, including when nothing was
injected; the audit query is only a fallback.

## Mem0 has no scores here

`Mem0Provider.retrieve_memory` uses `get_all`, which removes `score` and
does not rank. So `scores_present` is `false`, `relevance_threshold` does
nothing, and the rows are the first `top_k` in storage order whatever the
query. This is unchanged, and now recorded instead of hidden.

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
is reachable only inside `add_agentic_memory`, and its provider-level
filter still depends on the caller's `sharing_policy`, and still has
Mem0's 20-row limit.

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
