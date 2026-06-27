"""
Bug Reproduction: User Identity Caching in MemoryManager

This test proves that the kernel memory manager's `latest_user_id`-based
resolution causes the WRONG user_id to be used for retrieval when multiple
sequential trials serve different synthetic users within the same kernel
process.

The bug manifests as follows:
  - Trial 1 writes memories for user "jordan_matthews_75157bae"
  - Trial 2 writes memories for user "julia_romero_a3e82c1f"
  - Trial 3 writes memories for user "olivia_ramirez_d9f04b72"
  - At each trial, `ContextInjector._resolve_user_id()` returns
    `latest_user_id` which is ALWAYS the most recently written user_id
    across ALL trials — not the user_id that belongs to the CURRENT
    request.

This means:
  - Trial 1: Correctly resolves "jordan_matthews_75157bae" (it's the only one)
  - Trial 2: Resolves "julia_romero_a3e82c1f" (latest write), BUT if
    trial 1's user later comes back, they get julia's memories
  - Trial 3: Resolves "olivia_ramirez_d9f04b72" (latest write), overriding
    ALL previous users' scoping

The core architectural flaw: `_resolve_user_id()` uses a GLOBAL
`latest_user_id` property which reflects the kernel's most recent write,
not the current request's user. There is no per-request user_id context.

Run:
    python tests/modules/memory/test_user_id_caching_bug_repro.py
    # or
    pytest tests/modules/memory/test_user_id_caching_bug_repro.py -v
"""
from __future__ import annotations

import os
import sys
import time
import unittest
from collections import OrderedDict
from typing import Any, Dict, List, Optional

# Ensure project root on sys.path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cerebrum.llm.apis import LLMQuery
from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from aios.memory.context_injector import ContextInjector
from aios.memory.providers.base import MemoryProvider
from aios.memory.write_barrier import MemoryWriteBarrier


# ------------------------------------------------------------------
# Synthetic users for the 5 sequential trials
# ------------------------------------------------------------------

SYNTHETIC_USERS = [
    {
        "user_id": "jordan_matthews_75157bae",
        "profile": "Jordan Matthews is a backend engineer who loves Go.",
        "memory_type": "profile",
    },
    {
        "user_id": "julia_romero_a3e82c1f",
        "profile": "Julia Romero is a data scientist who prefers R.",
        "memory_type": "profile",
    },
    {
        "user_id": "olivia_ramirez_d9f04b72",
        "profile": "Olivia Ramirez is a DevOps engineer who uses Terraform.",
        "memory_type": "profile",
    },
    {
        "user_id": "ethan_nakamura_1b5c7d9e",
        "profile": "Ethan Nakamura is a frontend dev who uses Svelte.",
        "memory_type": "profile",
    },
    {
        "user_id": "maya_patel_e8a3f620",
        "profile": "Maya Patel is a security researcher who codes in Rust.",
        "memory_type": "profile",
    },
]


# ------------------------------------------------------------------
# Recording provider: tracks all retrieve_memory calls with user_ids
# ------------------------------------------------------------------


class TracingProvider(MemoryProvider):
    """Provider that records all operations and returns memories
    scoped by user_id, simulating correct ChromaDB WHERE filtering."""

    def __init__(self) -> None:
        self._store: Dict[str, List[dict]] = {}
        self.retrieve_log: List[Dict[str, Any]] = []
        self.add_log: List[Dict[str, Any]] = []

    def initialize(self, config: Dict[str, Any]) -> None:
        pass

    def add_memory(self, memory_note: Any) -> MemoryResponse:
        metadata = getattr(memory_note, "metadata", {}) or {}
        user_id = metadata.get("user_id", "unknown")
        content = getattr(memory_note, "content", "")
        mem = {
            "content": content,
            "metadata": dict(metadata),
            "score": 0.95,
        }
        self._store.setdefault(user_id, []).append(mem)
        self.add_log.append({
            "user_id": user_id,
            "content": content,
            "metadata": dict(metadata),
            "timestamp": time.monotonic(),
        })
        return MemoryResponse(success=True, memory_id="mem-ok")

    def store_for_user(
        self, user_id: str, content: str, metadata: dict
    ) -> None:
        """Seed the store directly (bypasses add_memory logging)."""
        mem = {
            "content": content,
            "metadata": dict(metadata),
            "score": 0.95,
        }
        self._store.setdefault(user_id, []).append(mem)

    def remove_memory(self, memory_id: str) -> MemoryResponse:
        return MemoryResponse(success=True, memory_id=memory_id)

    def update_memory(self, memory_note: Any) -> MemoryResponse:
        return MemoryResponse(success=True, memory_id="mem-ok")

    def get_memory(self, memory_id: str) -> MemoryResponse:
        return MemoryResponse(success=False, error="not found")

    def retrieve_memory(
        self, query: MemoryQuery
    ) -> MemoryResponse:
        user_id = query.params.get("user_id")
        agent_name = query.params.get("agent_name")
        self.retrieve_log.append({
            "user_id_in_query": user_id,
            "agent_name": agent_name,
            "params": dict(query.params),
            "timestamp": time.monotonic(),
        })
        # Return only memories stored under the requested user_id
        results = []
        for item in self._store.get(user_id, []):
            results.append({
                "content": item["content"],
                "metadata": dict(item.get("metadata", {})),
                "score": item.get("score", 0.9),
                "keywords": [],
                "tags": [],
                "category": "Uncategorized",
                "timestamp": "",
            })
        return MemoryResponse(
            success=True, search_results=results
        )

    def retrieve_memory_raw(
        self, query: MemoryQuery
    ) -> List[Any]:
        return []

    def close(self) -> None:
        pass


# ------------------------------------------------------------------
# Minimal MemoryManager mock with real OrderedDict tracking
# ------------------------------------------------------------------


class FakeMemoryManager:
    """Mirrors the real MemoryManager's user_id registry behavior."""

    def __init__(self, provider: TracingProvider) -> None:
        self.provider = provider
        self.barrier = MemoryWriteBarrier(config={})
        self._known_user_ids: OrderedDict[str, float] = OrderedDict()

    @property
    def known_user_ids(self) -> set:
        return set(self._known_user_ids.keys())

    @property
    def latest_user_id(self) -> Optional[str]:
        if not self._known_user_ids:
            return None
        return next(reversed(self._known_user_ids))

    def _register_user_id(self, user_id: str) -> None:
        self._known_user_ids[user_id] = time.monotonic()
        self._known_user_ids.move_to_end(user_id)


# ------------------------------------------------------------------
# Bug Reproduction Test
# ------------------------------------------------------------------


class TestUserIdCachingBug(unittest.TestCase):
    """Reproduces the user identity caching bug across 5 sequential
    trials in a single kernel process.

    The bug: `_resolve_user_id()` returns `latest_user_id` which is
    the GLOBALLY most recently written user_id, not the user_id that
    belongs to the CURRENT request. This means after Trial N writes
    user X, ALL subsequent retrievals (including for earlier users)
    resolve to user X.
    """

    def setUp(self) -> None:
        self.provider = TracingProvider()
        self.manager = FakeMemoryManager(provider=self.provider)
        self.injector = ContextInjector(
            memory_manager=self.manager,
            config={
                "auto_inject": True,
                "max_injected_memories": 5,
                "relevance_threshold": 0.0,
                "max_memory_tokens": 8000,
            },
        )

    def _make_query(self, text: str = "Hello") -> LLMQuery:
        return LLMQuery(
            messages=[{"role": "user", "content": text}],
            action_type="chat",
        )

    def _get_system_content(self, query: LLMQuery) -> str:
        for msg in query.messages:
            if msg.get("role") == "system":
                content = msg.get("content", "")
                if "MEMORY CONTEXT" in content:
                    return content
        return ""

    # ==============================================================
    # CORE REPRODUCTION: 5 sequential trials, same kernel process
    # ==============================================================

    def test_sequential_trials_user_id_stale_caching(self) -> None:
        """Prove that after registering multiple users sequentially,
        the injector ALWAYS resolves to the LAST registered user_id,
        not the one associated with the current request.

        This demonstrates the caching bug: there is no mechanism
        to associate a specific incoming request with a specific
        user_id. The global `latest_user_id` is the only signal.
        """
        results = []

        for i, user in enumerate(SYNTHETIC_USERS):
            uid = user["user_id"]
            profile = user["profile"]

            # 1. Simulate ProfileAgent writing shared memory for this user
            self.provider.store_for_user(
                user_id=uid,
                content=profile,
                metadata={
                    "user_id": uid,
                    "owner_agent": "profile_agent",
                    "sharing_policy": "shared",
                    "memory_type": "profile",
                },
            )

            # 2. Register the user_id (as address_request would)
            self.manager._register_user_id(uid)

            # 3. Simulate AssistantAgent making a chat request
            query = self._make_query(
                f"Trial {i+1}: Tell me about myself"
            )
            result_query, diag = self.injector.inject(
                "assistant_agent", query
            )

            results.append({
                "trial": i + 1,
                "expected_user_id": uid,
                "resolved_user_id": diag["resolved_user_id"],
                "latest_user_id_at_time": self.manager.latest_user_id,
                "injected_count": diag["injected_count"],
            })

        # --- Assertions ---
        # Each trial should resolve its own user_id.
        # In the CURRENT (buggy) architecture, all trials resolve
        # to latest_user_id which IS correct for the sequential
        # forward case (since each trial registers THEN retrieves).
        for r in results:
            self.assertEqual(
                r["resolved_user_id"],
                r["expected_user_id"],
                f"Trial {r['trial']}: resolved_user_id mismatch. "
                f"Expected {r['expected_user_id']}, "
                f"got {r['resolved_user_id']}",
            )

        # Print log for inspection
        print("\n=== Sequential Trial Results ===")
        for r in results:
            status = (
                "OK"
                if r["resolved_user_id"] == r["expected_user_id"]
                else "BUG"
            )
            print(
                f"  Trial {r['trial']}: "
                f"expected={r['expected_user_id']}, "
                f"resolved={r['resolved_user_id']}, "
                f"injected={r['injected_count']} [{status}]"
            )

    # ==============================================================
    # KEY BUG: "Return visit" — earlier user comes back but gets
    # the LATEST user's memories
    # ==============================================================

    def test_return_visit_gets_wrong_user_memories(self) -> None:
        """THE ACTUAL BUG: After Trial 3, if Jordan (Trial 1's user)
        comes back, the injector resolves to Olivia (Trial 3's user)
        because latest_user_id == olivia's id.

        This is the critical data contamination scenario.
        """
        # --- Setup: Register 3 users in sequence ---
        users = SYNTHETIC_USERS[:3]
        for user in users:
            uid = user["user_id"]
            self.provider.store_for_user(
                user_id=uid,
                content=user["profile"],
                metadata={
                    "user_id": uid,
                    "owner_agent": "profile_agent",
                    "sharing_policy": "shared",
                    "memory_type": "profile",
                },
            )
            self.manager._register_user_id(uid)

        # At this point:
        #   latest_user_id = "olivia_ramirez_d9f04b72" (last registered)
        #   known_user_ids = {jordan, julia, olivia}
        self.assertEqual(
            self.manager.latest_user_id,
            "olivia_ramirez_d9f04b72",
        )

        # --- Now Jordan comes back for a NEW request ---
        # In real life, the LLMQuery would carry Jordan's identity
        # somehow. But the current architecture has NO per-request
        # user_id — only the global latest_user_id.

        query = self._make_query(
            "Hey, what programming language do I prefer?"
        )
        result_query, diag = self.injector.inject(
            "assistant_agent", query
        )

        # THE BUG: resolved_user_id will be OLIVIA, not JORDAN
        resolved = diag["resolved_user_id"]
        injected_content = self._get_system_content(result_query)

        print("\n=== Return Visit Bug Reproduction ===")
        print(f"  Jordan's user_id: jordan_matthews_75157bae")
        print(f"  latest_user_id:   {self.manager.latest_user_id}")
        print(f"  resolved_user_id: {resolved}")
        print(f"  Injected content: {injected_content[:200]}")

        # Document the bug: resolved_user_id is OLIVIA's, not Jordan's
        # This proves memory contamination — Jordan gets Olivia's profile
        self.assertEqual(
            resolved,
            "olivia_ramirez_d9f04b72",
            "BUG NOT REPRODUCED: Expected the injector to resolve "
            "Olivia's user_id (the latest) instead of Jordan's. "
            "If this fails, the bug may have been fixed.",
        )

        # Confirm the WRONG memories would be injected:
        # Jordan should get "backend engineer who loves Go"
        # But instead gets "DevOps engineer who uses Terraform" (Olivia's)
        if injected_content:
            self.assertIn(
                "Terraform",
                injected_content,
                "Expected Olivia's profile (Terraform) to be "
                "injected since resolved_user_id is Olivia's",
            )
            self.assertNotIn(
                "Go",
                injected_content,
                "Jordan's profile (Go) should NOT appear since "
                "the retrieval is scoped to Olivia's user_id",
            )

    # ==============================================================
    # Prove the stale caching via retrieve_log inspection
    # ==============================================================

    def test_retrieve_log_shows_stale_user_id(self) -> None:
        """Inspect the provider's retrieve_log to prove that
        the user_id passed to retrieve_memory is always
        latest_user_id, not per-request.
        """
        users = SYNTHETIC_USERS[:3]

        # Register all 3 users and seed their memories
        for user in users:
            uid = user["user_id"]
            self.provider.store_for_user(
                user_id=uid,
                content=user["profile"],
                metadata={
                    "user_id": uid,
                    "owner_agent": "profile_agent",
                    "sharing_policy": "shared",
                    "memory_type": "profile",
                },
            )
            self.manager._register_user_id(uid)

        # Now simulate 3 requests — all SHOULD be for different users
        # but the injector has no way to know which user is asking.
        # It will always use latest_user_id for all 3.
        self.provider.retrieve_log.clear()

        for trial_num in range(3):
            query = self._make_query(
                f"Request {trial_num + 1}: What do I like?"
            )
            self.injector.inject("assistant_agent", query)

        # All 3 retrieval queries should have used the SAME user_id
        # (olivia's — the latest). This is the bug.
        print("\n=== Retrieve Log (Stale user_id) ===")
        unique_user_ids_in_retrieves = set()
        for i, entry in enumerate(self.provider.retrieve_log):
            uid_used = entry["user_id_in_query"]
            unique_user_ids_in_retrieves.add(uid_used)
            print(
                f"  Retrieve #{i+1}: user_id={uid_used}, "
                f"agent={entry['agent_name']}"
            )

        # BUG: All retrieves use the same user_id (olivia's)
        # because latest_user_id never changes between requests.
        self.assertEqual(
            len(unique_user_ids_in_retrieves),
            1,
            "Expected all retrieves to use the SAME (stale) user_id. "
            "If they differ, the resolution mechanism has been changed.",
        )
        # And that single user_id is olivia's (the latest)
        self.assertIn(
            "olivia_ramirez_d9f04b72",
            unique_user_ids_in_retrieves,
        )

    # ==============================================================
    # Document where the bad value is introduced
    # ==============================================================

    def test_identify_bug_location(self) -> None:
        """Trace exactly where the stale user_id is introduced.

        The bug is in ContextInjector._resolve_user_id() at the line:
            latest = getattr(manager, "latest_user_id", None)
            if latest and latest != agent_name:
                return latest

        This returns a GLOBAL property of the MemoryManager, not
        anything from the current request. There is no per-request
        user_id context passed into inject().
        """
        # Register two users
        self.manager._register_user_id("jordan_matthews_75157bae")
        self.manager._register_user_id("julia_romero_a3e82c1f")

        # _resolve_user_id returns the global latest, regardless
        # of which user is actually making the current request.
        resolved = self.injector._resolve_user_id("assistant_agent")

        self.assertEqual(
            resolved,
            "julia_romero_a3e82c1f",
            "Expected _resolve_user_id to return the globally latest "
            "user_id (julia), proving it doesn't consider the current "
            "request's identity.",
        )

        # The value is NOT introduced during:
        #   - request parsing (no per-request user_id exists)
        #   - create_memory (that correctly scopes writes)
        #
        # The value IS introduced during:
        #   - memory manager resolution (_resolve_user_id)
        #   - which feeds into retrieve injection (own_query_user_id)
        #
        # Root cause: The LLMQuery carries no user_id field,
        # and inject() receives no user_id parameter, so the
        # only signal is the global latest_user_id property.

        print("\n=== Bug Location Identification ===")
        print("  Bug introduced in: ContextInjector._resolve_user_id()")
        print(f"  latest_user_id: {self.manager.latest_user_id}")
        print(f"  resolved for request: {resolved}")
        print("  Root cause: No per-request user_id context.")
        print("  The global latest_user_id is the ONLY signal.")
        print("")
        print("  Affected paths:")
        print("    1. retrieve injection (own_query_user_id)")
        print("    2. shared memory retrieval user_id")
        print("    3. diagnostics['resolved_user_id']")
        print("    4. ConversationExtractor user_id propagation")


# ------------------------------------------------------------------
# Summary report (when run standalone)
# ------------------------------------------------------------------


def run_and_report() -> None:
    """Run all tests and print a summary of findings."""
    print("=" * 70)
    print("USER IDENTITY CACHING BUG - REPRODUCTION HARNESS")
    print("=" * 70)
    print()
    print("This harness proves that the AIOS kernel memory manager")
    print("reuses the FIRST (or rather, LATEST) resolved user_id")
    print("across all requests, instead of per-request scoping.")
    print()
    print("5 synthetic users:")
    for u in SYNTHETIC_USERS:
        print(f"  - {u['user_id']}")
    print()
    print("-" * 70)

    # Run the tests
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestUserIdCachingBug)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("-" * 70)
    print("FINDINGS SUMMARY:")
    print("-" * 70)
    print()
    print("1. SEQUENTIAL FORWARD CASE: Works correctly because each")
    print("   trial registers THEN retrieves (latest_user_id matches).")
    print()
    print("2. RETURN VISIT CASE: BROKEN. When an earlier user returns,")
    print("   they get the LATEST user's memories because _resolve_user_id")
    print("   always returns the globally latest_user_id.")
    print()
    print("3. BUG LOCATION: ContextInjector._resolve_user_id()")
    print("   Line: `latest = getattr(manager, 'latest_user_id', None)`")
    print("   This is a global property, not per-request.")
    print()
    print("4. ROOT CAUSE: The LLMQuery object carries no user_id field.")
    print("   inject() receives no user_id parameter.")
    print("   The architecture has NO per-request user identity concept.")
    print()
    print("5. CONTAMINATION VECTOR: User A's request gets User B's")
    print("   memories if User B wrote more recently than User A.")
    print()

    if result.wasSuccessful():
        print("ALL TESTS PASSED — Bug successfully reproduced.")
    else:
        print(f"FAILURES: {len(result.failures)}, "
              f"ERRORS: {len(result.errors)}")
        print("If test_sequential_trials passes but return_visit fails,")
        print("the bug may have been partially fixed.")


if __name__ == "__main__":
    run_and_report()


# ------------------------------------------------------------------
# FIX VERIFICATION: Tests that prove the fix works
# ------------------------------------------------------------------


class TestUserIdFixVerification(unittest.TestCase):
    """Regression tests proving that when user_id is passed
    explicitly to inject(), the return-visit bug is eliminated.

    These tests exercise the NEW code path:
        inject(agent_name, query, user_id=request_user_id)
    """

    def setUp(self) -> None:
        self.provider = TracingProvider()
        self.manager = FakeMemoryManager(provider=self.provider)
        self.injector = ContextInjector(
            memory_manager=self.manager,
            config={
                "auto_inject": True,
                "max_injected_memories": 5,
                "relevance_threshold": 0.0,
                "max_memory_tokens": 8000,
            },
        )

    def _make_query(self, text: str = "Hello") -> LLMQuery:
        return LLMQuery(
            messages=[{"role": "user", "content": text}],
            action_type="chat",
        )

    def _get_system_content(self, query: LLMQuery) -> str:
        for msg in query.messages:
            if msg.get("role") == "system":
                content = msg.get("content", "")
                if "MEMORY CONTEXT" in content:
                    return content
        return ""

    # ==============================================================
    # FIX TEST: Return visit now gets correct user's memories
    # ==============================================================

    def test_return_visit_with_explicit_user_id(self) -> None:
        """With the fix: passing user_id= to inject() ensures
        Jordan gets Jordan's memories, even though Olivia wrote last.
        """
        users = SYNTHETIC_USERS[:3]
        for user in users:
            uid = user["user_id"]
            self.provider.store_for_user(
                user_id=uid,
                content=user["profile"],
                metadata={
                    "user_id": uid,
                    "owner_agent": "profile_agent",
                    "sharing_policy": "shared",
                    "memory_type": "profile",
                },
            )
            self.manager._register_user_id(uid)

        # latest_user_id is olivia (last registered)
        self.assertEqual(
            self.manager.latest_user_id,
            "olivia_ramirez_d9f04b72",
        )

        # Jordan comes back — pass Jordan's user_id explicitly
        query = self._make_query("What programming language do I prefer?")
        result_query, diag = self.injector.inject(
            "assistant_agent",
            query,
            user_id="jordan_matthews_75157bae",
        )

        # FIX: resolved_user_id is now JORDAN's, not Olivia's
        self.assertEqual(
            diag["resolved_user_id"],
            "jordan_matthews_75157bae",
        )

        # FIX: Jordan gets their own memories (Go), not Olivia's
        injected = self._get_system_content(result_query)
        self.assertIn("Go", injected)
        self.assertNotIn("Terraform", injected)

    # ==============================================================
    # FIX TEST: Sequential trials with explicit user_id
    # ==============================================================

    def test_sequential_trials_with_explicit_user_id(self) -> None:
        """Each trial passes its own user_id explicitly.
        All 5 trials should get the correct user's memories.
        """
        # Seed all users' memories and register them
        for user in SYNTHETIC_USERS:
            uid = user["user_id"]
            self.provider.store_for_user(
                user_id=uid,
                content=user["profile"],
                metadata={
                    "user_id": uid,
                    "owner_agent": "profile_agent",
                    "sharing_policy": "shared",
                    "memory_type": "profile",
                },
            )
            self.manager._register_user_id(uid)

        # Now run all 5 trials with explicit user_id
        for user in SYNTHETIC_USERS:
            uid = user["user_id"]
            query = self._make_query(f"Tell me about myself ({uid})")
            result_query, diag = self.injector.inject(
                "assistant_agent",
                query,
                user_id=uid,
            )

            self.assertEqual(
                diag["resolved_user_id"],
                uid,
                f"Expected resolved_user_id={uid}, "
                f"got {diag['resolved_user_id']}",
            )

            # Verify correct content was injected
            injected = self._get_system_content(result_query)
            self.assertIn(
                user["profile"].split(" who ")[0].split(" is ")[1],
                injected,
                f"Expected {uid}'s profile content in injection",
            )

    # ==============================================================
    # FIX TEST: _resolve_user_id prefers explicit over latest
    # ==============================================================

    def test_resolve_prefers_explicit_over_latest(self) -> None:
        """_resolve_user_id(agent, request_user_id=X) returns X
        even when latest_user_id is something different.
        """
        self.manager._register_user_id("jordan_matthews_75157bae")
        self.manager._register_user_id("olivia_ramirez_d9f04b72")

        # latest is olivia, but request says jordan
        resolved = self.injector._resolve_user_id(
            "assistant_agent",
            request_user_id="jordan_matthews_75157bae",
        )
        self.assertEqual(resolved, "jordan_matthews_75157bae")

    # ==============================================================
    # FIX TEST: Fallback still works when no explicit user_id
    # ==============================================================

    def test_fallback_when_no_explicit_user_id(self) -> None:
        """Without explicit user_id, the old fallback behavior
        (latest_user_id) still works.
        """
        self.manager._register_user_id("jordan_matthews_75157bae")
        self.manager._register_user_id("olivia_ramirez_d9f04b72")

        # No request_user_id → falls back to latest
        resolved = self.injector._resolve_user_id(
            "assistant_agent",
        )
        self.assertEqual(resolved, "olivia_ramirez_d9f04b72")

    # ==============================================================
    # FIX TEST: Retrieve log shows per-request user_id
    # ==============================================================

    def test_retrieve_log_shows_per_request_user_id(self) -> None:
        """When user_id is passed per-request, the retrieve_log
        shows different user_ids for different requests.
        """
        users = SYNTHETIC_USERS[:3]
        for user in users:
            uid = user["user_id"]
            self.provider.store_for_user(
                user_id=uid,
                content=user["profile"],
                metadata={
                    "user_id": uid,
                    "owner_agent": "profile_agent",
                    "sharing_policy": "shared",
                    "memory_type": "profile",
                },
            )
            self.manager._register_user_id(uid)

        self.provider.retrieve_log.clear()

        # 3 requests for 3 different users
        for user in users:
            uid = user["user_id"]
            query = self._make_query(f"Request for {uid}")
            self.injector.inject(
                "assistant_agent", query, user_id=uid
            )

        # Verify that each retrieve used the correct user_id
        unique_user_ids = set()
        for entry in self.provider.retrieve_log:
            unique_user_ids.add(entry["user_id_in_query"])

        # With the fix, all 3 different user_ids appear
        self.assertEqual(
            len(unique_user_ids),
            3,
            f"Expected 3 different user_ids in retrieve log, "
            f"got {unique_user_ids}",
        )
        for user in users:
            self.assertIn(
                user["user_id"],
                unique_user_ids,
            )
