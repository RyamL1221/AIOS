#!/usr/bin/env python3
"""Isolated reproduction for the sparse-memory-retrieval investigation.

Subtask 5 — runnable reproduction (NOT a fix). Drives the REAL
``Mem0Provider`` (real ChromaDB PersistentClient + Ollama embedder) in a
throwaway temp directory, so nothing here touches the project's
``.mem0/chroma`` store or any production data.

Two independent demonstrations:

Part A — 63-char collection-name truncation collision (subtask 3).
  Reuses the two REAL colliding user_ids found in subtask 3
  (``alexandra_thompson…_t23__kernel_shared_adaptive`` and ``…_t31…``).
  Shows: (a) both route to the same truncated collection name, (b) the
  two identities get DISTINCT per-user Memory clients (cached by full
  user_id) yet both clients are handed that SAME collection name + the
  SAME shared PersistentClient, so they bind to ONE physical ChromaDB
  collection, and (c) a raw collection-level read returns BOTH
  identities' rows — actual data commingling at the physical-collection
  layer, not just a name clash. Also shows that the provider's own
  ``retrieve_memory`` (which filters get_all by the full user_id value)
  currently masks the commingling at the row level.

Part B — sparse metrics pattern (subtasks 1-2).
  Three per-trial-isolated user_ids, each written exactly as the harness
  does: profile + task as ``sharing_policy="shared"`` (owner
  profile_agent/task_agent) and a conversation memory as the kernel's
  auto_extract would — owner ``assistant_agent``, NOT tagged shared.
  Runs the harness-style audit retrieval (agent_name in the writer set,
  sharing_policy="shared") and shows ``shared_memory_count`` lands at 2,
  never 3, because the conversation memory is structurally excluded.

Requirements: a running Ollama with ``nomic-embed-text`` (embedder) at
localhost:11434; mem0 + chromadb installed. No LLM extraction is used
(``infer=False`` equivalent — we call the provider's add_memory which
stores the note verbatim), so no OpenAI/Azure key is needed.

Run:
    python scripts/reproduce_truncation_collision_and_sparse_metrics.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import shutil
import importlib.util

# Ensure repo root on path when run from anywhere.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _load_module(qualified_name: str, rel_path: str):
    """Load a module by file path, bypassing package __init__ side effects.

    ``aios.memory.providers.__init__`` transitively imports the in-house
    provider, which requires ``sentence_transformers`` — a heavy dependency
    the Mem0 path does not need. Loading ``mem0.py`` (and its ``base``
    dependency) by direct file path sidesteps that unrelated import chain so
    this reproduction runs with only mem0 + chromadb + an Ollama embedder.
    """
    spec = importlib.util.spec_from_file_location(
        qualified_name, os.path.join(_ROOT, rel_path)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    spec.loader.exec_module(module)
    return module

# Load base before mem0 (mem0.py imports aios.memory.providers.base).
_load_module("aios.memory.providers.base", "aios/memory/providers/base.py")
_mem0_mod = _load_module(
    "aios.memory.providers.mem0", "aios/memory/providers/mem0.py"
)
_note_mod = _load_module("aios.memory.note", "aios/memory/note.py")
Mem0Provider = _mem0_mod.Mem0Provider
MemoryNote = _note_mod.MemoryNote
from cerebrum.memory.apis import MemoryQuery


# Two REAL colliding user_ids from subtask 3 (qwen25_7b t23 vs t31).
UID_A = "alexandra_thompson_adaptive_report_v2_qwen25_7b_t23__kernel_shared_adaptive"
UID_B = "alexandra_thompson_adaptive_report_v2_qwen25_7b_t31__kernel_shared_adaptive"


def _make_provider(chroma_path: str) -> Mem0Provider:
    """Initialize the real Mem0Provider against a temp Chroma dir + Ollama."""
    provider = Mem0Provider()
    provider.initialize({
        "user_id": "default",
        "llm": {
            "provider": "ollama",
            "config": {
                "model": "qwen2.5:7b",
                "ollama_base_url": "http://localhost:11434",
            },
        },
        "embedder": {
            "provider": "ollama",
            "config": {
                "model": "nomic-embed-text",
                "ollama_base_url": "http://localhost:11434",
            },
        },
        "vector_store": {
            "provider": "chroma",
            "config": {
                "collection_name": "mem0_memories",
                "path": chroma_path,
            },
        },
    })
    return provider


def _add(provider: Mem0Provider, user_id: str, owner: str, mem_type: str,
         policy: str, content: str) -> str:
    note = MemoryNote(
        content=content,
        metadata={
            "owner_agent": owner,
            "user_id": user_id,
            "memory_type": mem_type,
            "sharing_policy": policy,
        },
    )
    resp = provider.add_memory(note)
    assert resp.success, f"add_memory failed: {resp.error}"
    return note.id


def _distinct_users_in_collection(provider: Mem0Provider, coll_name: str):
    """Return the sorted distinct ``user_id`` values physically stored in
    the named ChromaDB collection, reading rows directly (bypassing the
    per-user_id-value filter). Returns ``[]`` if the collection does not
    exist (post-fix, each identity has its own collection, so the other
    identity's collection simply won't contain this one's rows)."""
    try:
        raw = provider._persistent_client.get_collection(coll_name).get()
    except Exception:
        return []
    metadatas = raw.get("metadatas") or []
    return sorted({(m or {}).get("user_id", "?") for m in metadatas})


def part_a_collision(provider: Mem0Provider) -> bool:
    print("=" * 72)
    print("PART A — 63-char truncation collision -> real data commingling")
    print("=" * 72)

    coll_a = provider._collection_name_for_user(UID_A)
    coll_b = provider._collection_name_for_user(UID_B)
    print(f"UID_A = {UID_A!r}  (len {len(UID_A)})")
    print(f"UID_B = {UID_B!r}  (len {len(UID_B)})")
    print(f"collection(UID_A) = {coll_a!r}  (len {len(coll_a)})")
    print(f"collection(UID_B) = {coll_b!r}  (len {len(coll_b)})")
    same_name = coll_a == coll_b
    print(f"(a) SAME collection name?  {same_name}")

    # Same underlying per-user client object?
    client_a = provider._get_client_for_user(UID_A)
    client_b = provider._get_client_for_user(UID_B)
    print(f"    same Memory client object? {client_a is client_b}")

    # (b) Write DISTINCT content under each identity.
    _add(provider, UID_A, "profile_agent", "profile", "shared",
         "Project WEATHER-FORECAST: user prefers VS Code and Python.")
    _add(provider, UID_B, "profile_agent", "profile", "shared",
         "Project CUSTOMER-FEEDBACK: user prefers PyCharm and Go.")

    # (c) Raw collection-level read (bypasses the user_id-value filter) to
    # check whether either identity's rows physically co-reside with the
    # other's. Pre-fix both user_ids mapped to ONE collection name, so a
    # single read showed both rows commingled. Post-fix the names differ,
    # so we read EACH identity's own collection and confirm neither holds
    # the other identity's rows.
    users_in_a = _distinct_users_in_collection(provider, coll_a)
    users_in_b = _distinct_users_in_collection(provider, coll_b)
    print(f"(b) distinct user_ids co-resident per physical collection:")
    print(f"    {coll_a!r} -> {users_in_a}")
    print(f"    {coll_b!r} -> {users_in_b}")
    # Commingling = more than one distinct identity in a single physical
    # collection (the real cross-user-leak hazard). Post-fix must be False.
    commingled = len(users_in_a) > 1 or len(users_in_b) > 1
    print(f"(c) COMMINGLING (>1 distinct identity in one collection)? {commingled}")

    # Show the provider's own retrieve_memory masks it via user_id-value filter.
    q = MemoryQuery(operation_type="retrieve_memory", params={
        "content": "what should I focus on",
        "k": 20,
        "user_id": UID_A,
        "sharing_policy": "shared",
        "agent_name": "profile_agent",
    })
    r = provider.retrieve_memory(q)
    got = r.search_results or []
    got_users = sorted({(m.get("metadata") or {}).get("user_id", "?") for m in got})
    print(f"    retrieve_memory(user_id=UID_A) returned {len(got)} rows; "
          f"user_ids in result: {got_users}")
    print("    => row-level user_id-value filter (get_all filters by the FULL "
          "user_id value) currently MASKS the commingling at retrieval time "
          "(subtask 3 finding).")

    # Mechanism note (post-fix): _collection_name_for_user now appends an
    # 8-char SHA-256 suffix of the FULL user_id whenever truncation would
    # occur, so two user_ids sharing a long common prefix no longer collapse
    # to one collection name. Distinct names => distinct physical ChromaDB
    # collections => no cross-identity commingling. The SUCCESS criterion is
    # therefore INVERTED from the bug-demonstration version of this script:
    # the fix is confirmed when the collection names DIFFER *and* neither
    # collection holds more than one identity's rows.
    #
    # NOTE (assertion update, subtask 2): this script was originally written
    # to *reproduce* the bug, so its Part A gate was ``same_name and
    # commingled`` (PASS == bug present). Now that _collection_name_for_user
    # is patched, that gate is inverted to assert the FIXED behavior:
    # ``(not same_name) and (not commingled)`` (PASS == collision-free). This
    # is an intended update to the verification script's success criteria to
    # match the changed code under test, not a change to any production code.
    ok = (not same_name) and (not commingled)
    print(f"\nPART A result: {'FIX CONFIRMED' if ok else 'FAIL'}  "
          f"(distinct_collection_names={not same_name}, "
          f"no_commingling={not commingled})")
    return ok


def part_b_sparse(provider: Mem0Provider) -> bool:
    print()
    print("=" * 72)
    print("PART B — sparse metrics: shared_memory_count clusters at 2, not 3")
    print("=" * 72)

    WRITER_AGENTS = ["profile_agent", "task_agent"]
    RELEVANCE_THRESHOLD = 0.3  # harness constant (subtask 2)

    results = []
    for i in range(3):
        uid = f"repro_sparse_user_{i}_t{i}__kernel_shared"
        # Harness-parity per-trial writes:
        _add(provider, uid, "profile_agent", "profile", "shared",
             f"User {i} prefers VS Code, Python, and detailed answers.")
        _add(provider, uid, "task_agent", "task_context", "shared",
             f"Project {i}: goal ship API; blocker flaky tests; next write docs.")
        # Conversation memory as auto_extract writes it: owner assistant_agent,
        # NOT tagged shared (private-by-default).
        _add(provider, uid, "assistant_agent", "conversation", "private",
             f"User: what next? Assistant: prioritize the flaky tests (trial {i}).")

        # Count what is physically stored for this user (subtask 1 style).
        coll = provider._collection_name_for_user(uid)
        raw = provider._persistent_client.get_collection(coll).get()
        raw_metas = [m for m in (raw.get("metadatas") or [])
                     if (m or {}).get("user_id") == uid]
        total_stored = len(raw_metas)

        # Harness audit retrieval: fan out over writer agents, sharing=shared.
        merged = []
        seen = set()
        for writer in WRITER_AGENTS:
            q = MemoryQuery(operation_type="retrieve_memory", params={
                "content": "what should I focus on right now",
                "k": 20,
                "user_id": uid,
                "sharing_policy": "shared",
                "agent_name": writer,
            })
            r = provider.retrieve_memory(q)
            for m in (r.search_results or []):
                mid = m.get("memory_id")
                if mid and mid in seen:
                    continue
                if mid:
                    seen.add(mid)
                merged.append(m)

        # Replicate _build_retrieval_log_from_search: keep None-scored,
        # drop score<0.3, count only sharing_policy=="shared".
        shared_count = 0
        owners = []
        for m in merged:
            score = m.get("score")
            if score is not None and score < RELEVANCE_THRESHOLD:
                continue
            meta = m.get("metadata") or {}
            owner = meta.get("owner_agent", "")
            if not owner:
                continue
            owners.append((owner, meta.get("memory_type", "")))
            if meta.get("sharing_policy") == "shared":
                shared_count += 1

        results.append((uid, total_stored, shared_count, owners))
        print(f"  trial {i}: total_stored_for_user={total_stored}  "
              f"shared_memory_count={shared_count}  owners={owners}")

    counts = [r[2] for r in results]
    stored = [r[3] if False else r[1] for r in results]
    print(f"\n  total_stored distribution: {sorted(stored)} (each trial writes 3)")
    print(f"  shared_memory_count distribution: {sorted(counts)}")
    conv_excluded = all(
        all(o[0] != "assistant_agent" for o in r[3]) for r in results
    )
    clusters_at_2 = all(c <= 2 for c in counts) and max(counts) == 2
    print(f"  conversation memory (owner=assistant_agent) EXCLUDED from audit? "
          f"{conv_excluded}")
    print(f"  shared_memory_count capped at 2 despite 3 stored? {clusters_at_2}")
    ok = conv_excluded and clusters_at_2
    print(f"\nPART B result: {'REPRODUCED' if ok else 'NOT reproduced'} "
          "(matches subtask 2: conversation structurally excluded by "
          "owner-scope + sharing_policy filter)")
    return ok


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="repro_trunc_chroma_")
    print(f"[setup] isolated ChromaDB dir: {tmp}")
    try:
        provider = _make_provider(tmp)
        a = part_a_collision(provider)
        b = part_b_sparse(provider)
        print()
        print("=" * 72)
        print(f"SUMMARY: Part A (collision commingling)={'PASS' if a else 'FAIL'}  "
              f"Part B (sparse metrics)={'PASS' if b else 'FAIL'}")
        print("=" * 72)
        return 0 if (a and b) else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"[cleanup] removed {tmp}")


if __name__ == "__main__":
    sys.exit(main())
