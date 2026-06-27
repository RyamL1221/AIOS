# User Identity Resolution Trace

## Full Call Chain: create_memory (write path)

```
SDK Agent (e.g., ProfileAgent)
  └─ create_memory(agent_name="profile_agent", content="...",
                   metadata={"user_id": "alex_chen", "sharing_policy": "shared"})
      └─ MemoryQuery(operation_type="add_memory",
                     params={"content": "...", "metadata": {"user_id": "alex_chen", ...}})
          └─ send_request(agent_name, query) → HTTP POST /query
              └─ runtime/launch.py → execute_request(agent_name, query)
                  └─ SyscallExecutor.execute_request() [isinstance(query, MemoryQuery)]
                      └─ SyscallExecutor._execute_syscall(agent_name, query)
                          ├─ Barrier stamping: barrier_seq = mm.barrier.acquire("alex_chen")
                          └─ Enqueue to global_memory_req_queue
                              └─ Scheduler picks up → MemoryManager.address_request()
                                  ├─ _analyze_query_to_memory() → MemoryNote
                                  ├─ note.metadata["user_id"] = "alex_chen" ✓ (from SDK)
                                  ├─ _register_user_id("alex_chen")  ← UPDATES latest_user_id
                                  ├─ provider.add_memory(note) → ChromaDB write
                                  └─ barrier.release("alex_chen", seq, success)
```

**user_id is correct throughout the write path.** The SDK passes it in
`metadata`, the kernel preserves it, and `_register_user_id` records it
in the OrderedDict.

---

## Full Call Chain: retrieve / context injection (read path)

```
SDK Agent (e.g., AssistantAgent)
  └─ llm_chat(agent_name="assistant_agent",
              messages=[{"role": "user", "content": "What do I like?"}])
      └─ LLMQuery(messages=[...], action_type="chat")
          └─ send_request(agent_name, query) → HTTP POST /query
              └─ runtime/launch.py → execute_request(agent_name, query)
                  └─ SyscallExecutor.execute_request() [isinstance(query, LLMQuery)]
                      ├─ sync_llm_from_query(query.llms)
                      └─ context_injector.inject(agent_name="assistant_agent", query)
                          ├─ _resolve_user_id("assistant_agent")     ← BUG IS HERE
                          │   └─ returns manager.latest_user_id      ← GLOBAL STATE
                          ├─ own_query_user_id = resolved_user_id or agent_name
                          ├─ MemoryQuery(params={"user_id": own_query_user_id, ...})
                          ├─ _await_pending_writes(own_query_user_id)
                          ├─ provider.retrieve_memory(mem_query)
                          ├─ _retrieve_shared_memories(user_text, derived_user_id, agent_name)
                          ├─ filter, format, truncate
                          └─ prepend system message to query.messages
                      └─ execute_llm_syscall(agent_name, query)
                          └─ (post-LLM) conversation_extractor.extract_async(
                                ..., user_id=injection_diag["resolved_user_id"])
```

---

## Where the Correct user_id EXISTS Before It Gets Lost

| Location | Has user_id? | Details |
|----------|-------------|---------|
| `LLMQuery` schema | **NO** | Only has `messages`, `llms`, `tools`, `action_type` |
| `QueryRequest` envelope | **NO** | Only has `agent_name`, `query_type`, `query_data` |
| `execute_request()` args | **NO** | Only receives `(agent_name, query)` |
| `inject()` signature | **NO** | Only receives `(agent_name, query)` |
| `MemoryQuery.params` (for writes) | **YES** | `params.metadata.user_id` carries it |
| `MemoryManager._known_user_ids` | **YES** (stale) | OrderedDict with ALL ever-written user_ids |
| `MemoryManager.latest_user_id` | **YES** (wrong) | The most recently written user, not the current requester |

**The correct user_id exists in the write path** (SDK agents pass it in
`MemoryQuery.params.metadata.user_id`). But the **read path (LLM chat request)**
has **no mechanism to carry the requesting user's identity**. The `LLMQuery`
schema simply does not have a `user_id` field.

---

## The Broken Behavior (Precise)

```python
# In ContextInjector._resolve_user_id():
def _resolve_user_id(self, agent_name: str) -> Optional[str]:
    manager = self.memory_manager
    latest = getattr(manager, "latest_user_id", None)  # ← GLOBAL
    if latest and latest != agent_name:
        return latest  # ← Returns whoever wrote LAST, not who is asking NOW
    ...
```

**Current issue**: `create_memory` updates `manager.latest_user_id`, but
`retrieve`/context injection does not receive a per-request `user_id`.
`ContextInjector._resolve_user_id()` falls back to `manager.latest_user_id`,
causing cross-user memory contamination when:
1. User A's agent writes a memory (latest_user_id = A)
2. User B's agent writes a memory (latest_user_id = B)
3. User A comes back with a chat request
4. inject() resolves user_id = B (WRONG — should be A)
5. User A gets User B's memories injected

---

## Why `latest_user_id` Is Unsafe for Retrieve Operations

1. **Global state**: It reflects the most recent write across ALL users, not
   the current request's user.
2. **Race condition**: In concurrent scenarios, multiple agents writing for
   different users will clobber each other's latest_user_id.
3. **No causal link**: There is nothing connecting an incoming `LLMQuery` to the
   user_id it should be scoped to. The LLMQuery carries no user identity.
4. **Stale on return visits**: Once user B writes, user A can never get their
   correct memories unless they happen to trigger another write first.

---

## Cleanest Fix Point

### PREFERRED: Pass user_id from the current request into context injection

The fix must add a `user_id` field to the `LLMQuery` (or the `QueryRequest`
envelope) so that:
1. The SDK agent (or terminal) sets `user_id` on the LLM request
2. `execute_request()` extracts it and passes it to `inject()`
3. `inject()` uses it directly instead of consulting `latest_user_id`
4. `_resolve_user_id()` only serves as a **fallback** for legacy callers
   that don't set `user_id`

Concretely:
```python
# Option A: Add user_id to LLMQuery schema (Cerebrum SDK change)
class LLMQuery(Query):
    ...
    user_id: Optional[str] = None  # End-user identity for memory scoping

# Option B: Add user_id to QueryRequest envelope (kernel-only change)
class QueryRequest(BaseModel):
    agent_name: str
    query_type: ...
    query_data: ...
    user_id: Optional[str] = None  # End-user identity

# Then in execute_request():
def execute_request(self, agent_name, query):
    if isinstance(query, LLMQuery) and query.action_type == "chat":
        user_id = getattr(query, "user_id", None)
        if self.context_injector:
            query, diag = self.context_injector.inject(
                agent_name, query, user_id=user_id  # ← NEW PARAM
            )
```

### FALLBACK: Attach request metadata to the query object before injection

If changing the SDK schema is too invasive, the kernel could read the user_id
from the `messages` metadata or from a dedicated field on the HTTP request:
```python
# In runtime/launch.py /query handler, extract user_id from request:
user_id = request.user_id  # or request.query_data.user_id
# Attach to query before dispatching:
query._request_user_id = user_id
```

### AVOID: Relying on `latest_user_id` for normal user-scoped retrieval

`latest_user_id` is inherently unsafe for multi-user scenarios and should only
be used as a backward-compatibility fallback when no explicit user_id is
available in the request.

---

## Fix Belongs In

| Layer | Fix needed? | Reason |
|-------|------------|--------|
| `LLMQuery` schema (Cerebrum SDK) | **YES** (preferred) | Needs a `user_id` field so requests carry identity |
| `QueryRequest` / HTTP layer | **Alternative** | Could carry user_id without SDK change |
| `SyscallExecutor.execute_request()` | **YES** | Must extract user_id and pass to inject() |
| `ContextInjector.inject()` | **YES** | Must accept optional `user_id` param |
| `ContextInjector._resolve_user_id()` | **MAYBE** | Becomes fallback-only when explicit user_id is available |
| `MemoryManager` | **NO** | Write path is correct; issue is on read path |

---

## Summary

The bug is an **architectural gap**: the read path (LLM chat) has no way to
carry the end-user's identity to the context injection layer. The `LLMQuery`
schema has no `user_id` field. The only signal available to `_resolve_user_id()`
is `MemoryManager.latest_user_id`, which is a global mutable property reflecting
the last write across all users — fundamentally inappropriate for determining
which user is making the current read request.
