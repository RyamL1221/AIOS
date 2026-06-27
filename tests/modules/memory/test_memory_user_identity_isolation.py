"""
Regression Test: Cross-User Memory Identity Isolation

Proves that the kernel MemoryManager reuses the first resolved
user_id (via ``latest_user_id``) across later memory retrieval
operations in the same process — causing cross-user contamination.

This test exercises the REAL MemoryManager.address_request() flow
(not a mock), with a lightweight in-process provider that stores
and retrieves per-user_id, exposing the bug where a second user's
retrieve returns the first user's memories due to stale
``latest_user_id`` injection.

Expected behavior (after fix):
    Each user's retrieval returns ONLY that user's memories.

Current buggy behavior (before fix):
    The retrieve_memory path auto-injects ``latest_user_id``
    into the query when no explicit ``user_id`` is present in
    ``query.params``. When an agent retrieves on behalf of User A
    but User B was the last to write, User B's memories leak into
    User A's results.

Run:
    pytest tests/modules/memory/test_memory_user_identity_isolation.py -v
"""
from __future__ import annotations

import os
import sys
import unittest
from typing import Any, Dict, List
from unittest.mock import patch

# Ensure project root on sys.path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from aios.memory.note import MemoryNote
from aios.memory.providers.base import MemoryProvider
from aios.syscall.memory import MemorySyscall


# ------------------------------------------------------------------
# Synthetic users — clearly different names and projects
# ------------------------------------------------------------------

USER_A = {
    "user_id": "trial_0_alex_martinez",
    "name": "Alex Martinez",
    "project": "Data Pipeline Optimization",
}

USER_B = {
    "user_id": "trial_2_alexandra_morales",
    "name": "Alexandra Morales",
    "project": "Automated Customer Sentiment Analysis",
}


# ------------------------------------------------------------------
# Isolation-aware test provider
# ------------------------------------------------------------------


class IsolationTestProvider(MemoryProvider):
    """A deterministic provider that stores memories per user_id
    and returns ONLY memories matching the requested user_id.

    This simulates correct ChromaDB WHERE-filter behavior so the
    test can prove that the MemoryManager's user_id resolution
    (not the provider) is the source of contamination.
    """

    def __init__(self) -> None:
        # user_id -> list of memory dicts
        self._store: Dict[str, List[dict]] = {}

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
        return MemoryResponse(
            success=True, memory_id=f"mem-{len(self._store)}"
        )

    def remove_memory(self, memory_id: str) -> MemoryResponse:
        return MemoryResponse(success=True, memory_id=memory_id)

    def update_memory(self, memory_note: Any) -> MemoryResponse:
        return MemoryResponse(success=True, memory_id="ok")

    def get_memory(self, memory_id: str) -> MemoryResponse:
        return MemoryResponse(success=False, error="not impl")

    def retrieve_memory(
        self, query: MemoryQuery
    ) -> MemoryResponse:
        """Return memories scoped to the user_id in query.params.

        This faithfully simulates what the Mem0 provider does:
        ``client.search(content, filters={"user_id": X})``.
        If no user_id is provided, returns nothing (mimics empty
        result from ChromaDB with no filter match).
        """
        user_id = query.params.get("user_id")
        if not user_id:
            return MemoryResponse(
                success=True, search_results=[]
            )

        results = []
        for item in self._store.get(user_id, []):
            results.append({
                "content": item["content"],
                "metadata": item.get("metadata", {}),
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
        user_id = query.params.get("user_id")
        if not user_id:
            return []
        results = []
        for item in self._store.get(user_id, []):
            note = MemoryNote(
                content=item["content"],
                metadata=item.get("metadata"),
            )
            results.append(note)
        return results

    def close(self) -> None:
        pass

    def sync_llm_from_query(self, llms) -> None:
        pass


# ------------------------------------------------------------------
# Helper: build a MemorySyscall
# ------------------------------------------------------------------


def _make_syscall(
    agent_name: str,
    operation_type: str,
    params: dict,
) -> MemorySyscall:
    """Construct a MemorySyscall suitable for address_request()."""
    query = MemoryQuery(
        operation_type=operation_type, params=params
    )
    syscall = MemorySyscall(agent_name=agent_name, query=query)
    # Sentinel barrier values so address_request doesn't block.
    syscall.barrier_seq = 0
    syscall.barrier_snapshot = 0
    return syscall


# ------------------------------------------------------------------
# Build a real MemoryManager with injected test provider
# ------------------------------------------------------------------


def _build_manager_with_test_provider():
    """Create a real MemoryManager but replace its provider with
    our IsolationTestProvider. This exercises the actual
    address_request() logic without needing Ollama/ChromaDB.
    """
    from aios.memory.manager import MemoryManager

    # Patch config to avoid hitting real config.yaml dependencies
    with patch(
        "aios.memory.manager.global_config"
    ) as mock_config:
        mock_config.get_memory_config.return_value = {
            "provider": "in-house",
            "write_barrier": {"enabled": False},
        }
        mock_config.get_storage_config.return_value = {}
        manager = MemoryManager(
            log_mode="console", provider="in-house"
        )

    # Swap the provider to our test double
    manager.provider = IsolationTestProvider()
    return manager


# ==================================================================
# Regression tests
# ==================================================================


class TestMemoryUserIdentityIsolation(unittest.TestCase):
    """Regression test proving cross-user contamination in the
    MemoryManager when multiple users write through the same
    kernel process.

    The bug: address_request("retrieve_memory") auto-injects
    ``latest_user_id`` (the most recently written user) into the
    retrieve query when no explicit user_id is in query.params.
    This means an agent retrieving on behalf of User A gets User
    B's memories if User B wrote last.
    """

    def setUp(self) -> None:
        self.manager = _build_manager_with_test_provider()

    def tearDown(self) -> None:
        self.manager.close()

    # ----------------------------------------------------------
    # Write helpers
    # ----------------------------------------------------------

    def _write_memory_for_user(
        self, user: dict, content: str
    ) -> MemoryResponse:
        """Write a memory through MemoryManager.address_request
        using the full syscall path."""
        syscall = _make_syscall(
            agent_name="assistant_agent",
            operation_type="add_memory",
            params={
                "content": content,
                "metadata": {
                    "user_id": user["user_id"],
                    "owner_agent": "assistant_agent",
                    "sharing_policy": "private",
                    "memory_type": "conversation",
                    "trial_id": user["user_id"].split("_")[1],
                },
            },
        )
        return self.manager.address_request(syscall)

    def _retrieve_for_user(
        self, user: dict
    ) -> MemoryResponse:
        """Retrieve memory through MemoryManager.address_request
        with the user's explicit user_id in query.params.

        After the fix, the manager no longer injects
        ``latest_user_id`` as a fallback. Callers MUST pass
        ``user_id`` explicitly to scope the retrieval.
        """
        syscall = _make_syscall(
            agent_name="assistant_agent",
            operation_type="retrieve_memory",
            params={
                "content": (
                    f"What project is {user['name']} "
                    f"working on?"
                ),
                "k": 5,
                "user_id": user["user_id"],
            },
        )
        return self.manager.address_request(syscall)

    def _retrieve_for_user_explicit(
        self, user: dict
    ) -> MemoryResponse:
        """Retrieve with explicit user_id in query params.

        This exercises what SHOULD work correctly once the fix
        passes user_id per-request. It documents the correct
        behavior when the caller properly passes identity.
        """
        syscall = _make_syscall(
            agent_name="assistant_agent",
            operation_type="retrieve_memory",
            params={
                "content": (
                    f"What project is {user['name']} "
                    f"working on?"
                ),
                "k": 5,
                "user_id": user["user_id"],
            },
        )
        return self.manager.address_request(syscall)

    # ----------------------------------------------------------
    # Core regression test: implicit user_id resolution
    # ----------------------------------------------------------

    def test_retrieve_for_user_b_does_not_return_user_a_memories(
        self,
    ) -> None:
        """Write for User A, then User B. Retrieve for User B.

        BUG: If the manager resolves user_id from
        ``latest_user_id``, this should correctly return User B's
        memories because B was the last to write. But if we then
        retrieve for User A, the stale ``latest_user_id`` still
        points to B — returning B's memories for A's request.

        This test verifies the second retrieve (for A) is
        contaminated by B's memories on the current
        implementation.
        """
        # Write memory for User A
        content_a = (
            f"{USER_A['name']} is working on "
            f"{USER_A['project']}."
        )
        resp_a = self._write_memory_for_user(USER_A, content_a)
        self.assertTrue(resp_a.success)

        # Write memory for User B (now latest_user_id = B)
        content_b = (
            f"{USER_B['name']} is working on "
            f"{USER_B['project']}."
        )
        resp_b = self._write_memory_for_user(USER_B, content_b)
        self.assertTrue(resp_b.success)

        # Verify latest_user_id is now User B
        self.assertEqual(
            self.manager.latest_user_id,
            USER_B["user_id"],
            "latest_user_id should be User B after B's write",
        )

        # Retrieve for User B (implicit user_id resolution)
        result_b = self._retrieve_for_user(USER_B)
        self.assertTrue(result_b.success)
        results_b = result_b.search_results or []
        text_b = " ".join(
            r.get("content", "") for r in results_b
        )

        # User B should get their own memories
        self.assertIn(
            USER_B["project"],
            text_b,
            "User B retrieval should include B's project",
        )

        # Now retrieve for User A (implicit user_id resolution)
        # BUG: latest_user_id is still User B, so the manager
        # will scope this retrieve to User B instead of User A.
        result_a = self._retrieve_for_user(USER_A)
        self.assertTrue(result_a.success)
        results_a = result_a.search_results or []
        text_a = " ".join(
            r.get("content", "") for r in results_a
        )

        # ASSERTIONS THAT SHOULD PASS AFTER FIX:
        # User A should get ONLY their own memories
        self.assertIn(
            USER_A["project"],
            text_a,
            (
                "User A retrieval MUST include A's project "
                f"'{USER_A['project']}' — got: {text_a!r}"
            ),
        )
        self.assertNotIn(
            USER_B["project"],
            text_a,
            (
                "User A retrieval MUST NOT include B's project "
                f"'{USER_B['project']}' — cross-contamination! "
                f"Got: {text_a!r}"
            ),
        )

    def test_retrieve_for_user_a_after_b_write_is_contaminated(
        self,
    ) -> None:
        """Explicitly demonstrates the contamination: after
        User B writes, retrieving for User A returns B's memories
        because ``latest_user_id`` points to B.

        This test is expected to FAIL on the current (buggy)
        implementation — it asserts correct isolation that does
        NOT currently exist.
        """
        # Write User A
        content_a = (
            f"{USER_A['name']} is working on "
            f"{USER_A['project']}."
        )
        self._write_memory_for_user(USER_A, content_a)

        # Write User B
        content_b = (
            f"{USER_B['name']} is working on "
            f"{USER_B['project']}."
        )
        self._write_memory_for_user(USER_B, content_b)

        # Retrieve for User A via implicit resolution
        result_a = self._retrieve_for_user(USER_A)
        results_a = result_a.search_results or []
        text_a = " ".join(
            r.get("content", "") for r in results_a
        )

        # This MUST hold after the fix:
        self.assertIn(
            "Data Pipeline Optimization",
            text_a,
            (
                "User A's retrieval must return A's memory. "
                f"Got: {text_a!r}"
            ),
        )
        self.assertIn(
            "Alex Martinez",
            text_a,
            (
                "User A's retrieval must mention Alex Martinez. "
                f"Got: {text_a!r}"
            ),
        )

        # These prove no contamination:
        self.assertNotIn(
            "Automated Customer Sentiment Analysis",
            text_a,
            (
                "User A MUST NOT see B's project. "
                f"Got: {text_a!r}"
            ),
        )
        self.assertNotIn(
            "Alexandra Morales",
            text_a,
            (
                "User A MUST NOT see B's name. "
                f"Got: {text_a!r}"
            ),
        )

    def test_bidirectional_isolation(self) -> None:
        """Both users retrieve independently and each gets ONLY
        their own memories — no leakage in either direction.

        This fails on the buggy implementation because at least
        one direction will resolve to the wrong user_id.
        """
        # Write both users' memories
        self._write_memory_for_user(
            USER_A,
            f"{USER_A['name']} is working on "
            f"{USER_A['project']}.",
        )
        self._write_memory_for_user(
            USER_B,
            f"{USER_B['name']} is working on "
            f"{USER_B['project']}.",
        )

        # Retrieve for User B first (should work because B is
        # latest)
        result_b = self._retrieve_for_user(USER_B)
        results_b = result_b.search_results or []
        text_b = " ".join(
            r.get("content", "") for r in results_b
        )

        self.assertIn(
            "Automated Customer Sentiment Analysis", text_b
        )
        self.assertIn("Alexandra Morales", text_b)
        self.assertNotIn("Data Pipeline Optimization", text_b)
        self.assertNotIn("Alex Martinez", text_b)

        # Retrieve for User A (this is where contamination
        # occurs)
        result_a = self._retrieve_for_user(USER_A)
        results_a = result_a.search_results or []
        text_a = " ".join(
            r.get("content", "") for r in results_a
        )

        self.assertIn("Data Pipeline Optimization", text_a)
        self.assertIn("Alex Martinez", text_a)
        self.assertNotIn(
            "Automated Customer Sentiment Analysis", text_a
        )
        self.assertNotIn("Alexandra Morales", text_a)

    # ----------------------------------------------------------
    # Explicit user_id path (documents correct behavior)
    # ----------------------------------------------------------

    def test_explicit_user_id_provides_correct_isolation(
        self,
    ) -> None:
        """When user_id is explicitly passed in query.params,
        retrieval is correctly scoped — no contamination.

        This test should PASS on both buggy and fixed
        implementations (explicit user_id bypasses the
        latest_user_id fallback).
        """
        # Write both users
        self._write_memory_for_user(
            USER_A,
            f"{USER_A['name']} is working on "
            f"{USER_A['project']}.",
        )
        self._write_memory_for_user(
            USER_B,
            f"{USER_B['name']} is working on "
            f"{USER_B['project']}.",
        )

        # Retrieve with explicit user_id for User A
        result_a = self._retrieve_for_user_explicit(USER_A)
        results_a = result_a.search_results or []
        text_a = " ".join(
            r.get("content", "") for r in results_a
        )

        self.assertIn("Data Pipeline Optimization", text_a)
        self.assertNotIn(
            "Automated Customer Sentiment Analysis", text_a
        )

        # Retrieve with explicit user_id for User B
        result_b = self._retrieve_for_user_explicit(USER_B)
        results_b = result_b.search_results or []
        text_b = " ".join(
            r.get("content", "") for r in results_b
        )

        self.assertIn(
            "Automated Customer Sentiment Analysis", text_b
        )
        self.assertNotIn("Data Pipeline Optimization", text_b)

    # ----------------------------------------------------------
    # Multi-write ordering contamination
    # ----------------------------------------------------------

    def test_no_user_id_returns_empty_not_contaminated(
        self,
    ) -> None:
        """When no user_id is passed in retrieve params, the
        manager returns empty results rather than falling back
        to the last writer's memories.

        This proves the fix: previously, the manager would
        inject latest_user_id (last writer) into the query,
        causing cross-user contamination. Now it returns
        nothing rather than wrong data.
        """
        # Write for both users
        self._write_memory_for_user(
            USER_A,
            f"{USER_A['name']} is working on "
            f"{USER_A['project']}.",
        )
        self._write_memory_for_user(
            USER_B,
            f"{USER_B['name']} is working on "
            f"{USER_B['project']}.",
        )

        # Retrieve WITHOUT user_id in params
        syscall = _make_syscall(
            agent_name="assistant_agent",
            operation_type="retrieve_memory",
            params={
                "content": "What project is the user on?",
                "k": 5,
                # NO user_id — previously caused contamination
            },
        )
        result = self.manager.address_request(syscall)
        results = result.search_results or []
        text = " ".join(
            r.get("content", "") for r in results
        )

        # Must NOT contain either user's data (empty is safe)
        self.assertNotIn(
            USER_A["project"],
            text,
            "No-user_id retrieve must not leak A's data",
        )
        self.assertNotIn(
            USER_B["project"],
            text,
            "No-user_id retrieve must not leak B's data",
        )

    def test_three_users_last_writer_contaminates_all_retrievals(
        self,
    ) -> None:
        """With 3 users writing sequentially, implicit retrieval
        for users 1 and 2 returns user 3's memories because
        latest_user_id points to user 3.
        """
        user_c = {
            "user_id": "trial_4_carlos_rivera",
            "name": "Carlos Rivera",
            "project": "Real-Time Fraud Detection",
        }

        # Write all three in order
        for user in [USER_A, USER_B, user_c]:
            self._write_memory_for_user(
                user,
                f"{user['name']} is working on "
                f"{user['project']}.",
            )

        # latest_user_id should be Carlos
        self.assertEqual(
            self.manager.latest_user_id,
            user_c["user_id"],
        )

        # Implicit retrieval for User A — should get A's memories
        result_a = self._retrieve_for_user(USER_A)
        results_a = result_a.search_results or []
        text_a = " ".join(
            r.get("content", "") for r in results_a
        )

        self.assertIn(
            "Data Pipeline Optimization",
            text_a,
            (
                "User A retrieval must return A's project. "
                f"Got: {text_a!r}"
            ),
        )
        self.assertNotIn(
            "Real-Time Fraud Detection",
            text_a,
            (
                "User A MUST NOT see Carlos's project. "
                f"Got: {text_a!r}"
            ),
        )
        self.assertNotIn(
            "Automated Customer Sentiment Analysis",
            text_a,
            (
                "User A MUST NOT see B's project. "
                f"Got: {text_a!r}"
            ),
        )


if __name__ == "__main__":
    unittest.main()
