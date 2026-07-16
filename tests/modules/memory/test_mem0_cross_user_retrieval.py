"""
Cross-user retrieval isolation test for Mem0Provider.

Proves that retrieval scoped to one user_id does NOT return memories
belonging to another user_id, even when multiple users have
semantically similar memories in the same backing store.

The mock Mem0 client enforces filter correctness: it inspects the
incoming ``filters`` dict and returns ONLY the matching user's
memories. If called without a proper user_id filter, it returns
both users' memories — which would fail the assertions.

Retrieval goes through Mem0's ``get_all()`` (not ``search()``):
``get_all()`` queries the vector store by metadata filter alone,
without ``score_and_rank()``, which was dropping valid results
for small per-user result sets.

This protects against:
- Regressions where the user_id pre-filter is accidentally removed
- Scalability issues from broad unscoped retrieval + post-filtering
- Cross-user memory leakage in multi-tenant deployments
"""
from __future__ import annotations

import os
import sys
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock

# Ensure project root on sys.path.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from aios.memory.providers.mem0 import Mem0Provider


# ------------------------------------------------------------------
# Constants: two distinct users with semantically similar memories
# ------------------------------------------------------------------

USER_A = "alexandra_carter_0421d4d1__mem0_default"
USER_B = "benjamin_lee_9f83a102__mem0_default"

USER_A_MEMORY = (
    "Focus next on finishing the agent orchestration benchmark."
)
USER_B_MEMORY = (
    "Focus next on preparing the frontend dashboard demo."
)

TEST_AGENT = "assistant_agent"
TEST_CONTENT = "What should I focus on next?"


# ------------------------------------------------------------------
# Mock Mem0 client that enforces filter-based isolation
# ------------------------------------------------------------------


def _make_filter_enforcing_client() -> MagicMock:
    """Create a mock Mem0 client whose get_all() enforces user_id
    filter correctness.

    Behaviour:
    - filters={"user_id": USER_A} → returns only User A's memory
    - filters={"user_id": USER_B} → returns only User B's memory
    - Missing or incorrect filter → returns BOTH users' memories
      (simulating an unscoped broad retrieval)
    """
    user_a_result = {
        "memory": USER_A_MEMORY,
        "score": 0.92,
        "id": "mem_a_001",
        "metadata": {
            "user_id": USER_A,
            "owner_agent": "profile_agent",
            "sharing_policy": "shared",
            "memory_type": "task_context",
        },
    }
    user_b_result = {
        "memory": USER_B_MEMORY,
        "score": 0.91,
        "id": "mem_b_001",
        "metadata": {
            "user_id": USER_B,
            "owner_agent": "profile_agent",
            "sharing_policy": "shared",
            "memory_type": "task_context",
        },
    }

    def mock_get_all(**kwargs) -> list:
        filters = kwargs.get("filters", {})
        uid = filters.get("user_id")

        if uid == USER_A:
            return [user_a_result]
        elif uid == USER_B:
            return [user_b_result]
        else:
            # No filter or wrong filter: return both
            # (simulates unscoped broad retrieval)
            return [user_a_result, user_b_result]

    mock_client = MagicMock()
    mock_client.get_all.side_effect = mock_get_all
    return mock_client


# ------------------------------------------------------------------
# Helper: create a Mem0Provider with the filter-enforcing client
# ------------------------------------------------------------------


def _create_provider() -> "tuple[Mem0Provider, MagicMock]":
    """Create a Mem0Provider wired to the filter-enforcing mock.

    Routes all user_ids through _get_client_for_user to the same
    filter-enforcing mock, matching production's per-user client
    routing architecture.
    """
    provider = Mem0Provider()
    mock_client = _make_filter_enforcing_client()
    provider.client = mock_client
    provider.default_user_id = "default"
    provider.default_agent_id = None
    # Patch per-user client routing to return the shared
    # filter-enforcing mock for any user_id.
    provider._get_client_for_user = lambda uid: mock_client
    return provider, mock_client


# ==================================================================
# Test Cases: retrieve_memory cross-user isolation
# ==================================================================


class TestCrossUserRetrieveMemory(unittest.TestCase):
    """retrieve_memory must return ONLY the scoped user's memories."""

    def test_user_a_gets_only_user_a_memory(self):
        """Retrieval scoped to USER_A returns only User A's memory,
        not User B's semantically similar memory."""
        provider, mock_client = _create_provider()

        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={
                "content": TEST_CONTENT,
                "k": 5,
                "user_id": USER_A,
                "agent_name": TEST_AGENT,
            },
        )

        response = provider.retrieve_memory(query)

        self.assertTrue(response.success)
        self.assertEqual(len(response.search_results), 1)

        result_content = response.search_results[0]["content"]
        self.assertEqual(
            result_content,
            USER_A_MEMORY,
            "User A retrieval must return User A's memory.",
        )
        self.assertNotEqual(
            result_content,
            USER_B_MEMORY,
            "User A retrieval must NOT contain User B's memory.",
        )

    def test_user_b_gets_only_user_b_memory(self):
        """Retrieval scoped to USER_B returns only User B's memory,
        not User A's semantically similar memory."""
        provider, mock_client = _create_provider()

        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={
                "content": TEST_CONTENT,
                "k": 5,
                "user_id": USER_B,
                "agent_name": TEST_AGENT,
            },
        )

        response = provider.retrieve_memory(query)

        self.assertTrue(response.success)
        self.assertEqual(len(response.search_results), 1)

        result_content = response.search_results[0]["content"]
        self.assertEqual(
            result_content,
            USER_B_MEMORY,
            "User B retrieval must return User B's memory.",
        )
        self.assertNotEqual(
            result_content,
            USER_A_MEMORY,
            "User B retrieval must NOT contain User A's memory.",
        )

    def test_get_all_called_with_user_a_filter(self):
        """client.get_all() must receive filters={"user_id": USER_A}
        when retrieving for User A."""
        provider, mock_client = _create_provider()

        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={
                "content": TEST_CONTENT,
                "k": 5,
                "user_id": USER_A,
                "agent_name": TEST_AGENT,
            },
        )

        provider.retrieve_memory(query)

        mock_client.get_all.assert_called_once()
        kwargs = mock_client.get_all.call_args[1]
        filters = kwargs.get("filters", {})

        self.assertEqual(
            filters.get("user_id"),
            USER_A,
            "get_all() must be called with user_id=USER_A "
            "in the filters dict.",
        )

    def test_get_all_called_with_user_b_filter(self):
        """client.get_all() must receive filters={"user_id": USER_B}
        when retrieving for User B."""
        provider, mock_client = _create_provider()

        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={
                "content": TEST_CONTENT,
                "k": 5,
                "user_id": USER_B,
                "agent_name": TEST_AGENT,
            },
        )

        provider.retrieve_memory(query)

        mock_client.get_all.assert_called_once()
        kwargs = mock_client.get_all.call_args[1]
        filters = kwargs.get("filters", {})

        self.assertEqual(
            filters.get("user_id"),
            USER_B,
            "get_all() must be called with user_id=USER_B "
            "in the filters dict.",
        )

    def test_fails_if_no_filter_applied(self):
        """If the provider dropped the user_id filter, the mock
        would return BOTH users' memories — proving leakage."""
        provider, mock_client = _create_provider()

        # Simulate what would happen if user_id filter was missing:
        # call mock_get_all directly without the proper filter
        unscoped_results = mock_client.get_all(filters={}, top_k=5)

        # Without proper filter, both memories are returned
        self.assertEqual(
            len(unscoped_results),
            2,
            "Sanity check: unscoped get_all returns both users' "
            "memories (this is what we're protecting against).",
        )

        # But a properly scoped call returns only one
        scoped_results = mock_client.get_all(
            filters={"user_id": USER_A},
            top_k=5,
        )
        self.assertEqual(
            len(scoped_results),
            1,
            "Scoped get_all must return only the filtered user.",
        )


# ==================================================================
# Test Cases: retrieve_memory_raw cross-user isolation
# ==================================================================


class TestCrossUserRetrieveMemoryRaw(unittest.TestCase):
    """retrieve_memory_raw must return ONLY the scoped user's
    memories, same isolation guarantee as retrieve_memory."""

    def test_user_a_gets_only_user_a_memory_raw(self):
        """Raw retrieval scoped to USER_A returns only User A."""
        provider, mock_client = _create_provider()

        query = MemoryQuery(
            operation_type="retrieve_memory_raw",
            params={
                "content": TEST_CONTENT,
                "k": 5,
                "user_id": USER_A,
                "agent_name": TEST_AGENT,
            },
        )

        notes = provider.retrieve_memory_raw(query)

        self.assertEqual(len(notes), 1)
        self.assertEqual(
            notes[0].content,
            USER_A_MEMORY,
            "Raw retrieval for User A must return "
            "User A's memory only.",
        )

    def test_user_b_gets_only_user_b_memory_raw(self):
        """Raw retrieval scoped to USER_B returns only User B."""
        provider, mock_client = _create_provider()

        query = MemoryQuery(
            operation_type="retrieve_memory_raw",
            params={
                "content": TEST_CONTENT,
                "k": 5,
                "user_id": USER_B,
                "agent_name": TEST_AGENT,
            },
        )

        notes = provider.retrieve_memory_raw(query)

        self.assertEqual(len(notes), 1)
        self.assertEqual(
            notes[0].content,
            USER_B_MEMORY,
            "Raw retrieval for User B must return "
            "User B's memory only.",
        )

    def test_raw_get_all_called_with_user_filter(self):
        """client.get_all() receives the correct user_id filter
        for retrieve_memory_raw."""
        provider, mock_client = _create_provider()

        query = MemoryQuery(
            operation_type="retrieve_memory_raw",
            params={
                "content": TEST_CONTENT,
                "k": 5,
                "user_id": USER_A,
                "agent_name": TEST_AGENT,
            },
        )

        provider.retrieve_memory_raw(query)

        mock_client.get_all.assert_called_once()
        kwargs = mock_client.get_all.call_args[1]
        filters = kwargs.get("filters", {})

        self.assertEqual(filters.get("user_id"), USER_A)

    def test_raw_no_cross_leakage_between_users(self):
        """Sequential retrievals for different users must not
        leak state between calls."""
        provider, mock_client = _create_provider()

        # Retrieve for User A
        query_a = MemoryQuery(
            operation_type="retrieve_memory_raw",
            params={
                "content": TEST_CONTENT,
                "k": 5,
                "user_id": USER_A,
                "agent_name": TEST_AGENT,
            },
        )
        notes_a = provider.retrieve_memory_raw(query_a)

        # Retrieve for User B
        query_b = MemoryQuery(
            operation_type="retrieve_memory_raw",
            params={
                "content": TEST_CONTENT,
                "k": 5,
                "user_id": USER_B,
                "agent_name": TEST_AGENT,
            },
        )
        notes_b = provider.retrieve_memory_raw(query_b)

        # Each should have exactly their own memory
        self.assertEqual(len(notes_a), 1)
        self.assertEqual(len(notes_b), 1)
        self.assertEqual(notes_a[0].content, USER_A_MEMORY)
        self.assertEqual(notes_b[0].content, USER_B_MEMORY)

        # No overlap
        self.assertNotEqual(
            notes_a[0].content,
            notes_b[0].content,
            "User A and User B memories must be distinct.",
        )


if __name__ == "__main__":
    unittest.main()
