"""
Provider-level test: Mem0Provider passes user_id as a pre-filter.

Verifies that ``retrieve_memory`` and ``retrieve_memory_raw`` pass
the request-scoped ``user_id`` into the Mem0 ``client.get_all()``
call as part of the ``filters`` dict — NOT merely as a post-filter
applied after broad unscoped retrieval.

This ensures scalability: ChromaDB/Mem0 narrows the metadata lookup
to only the target user's documents via a WHERE clause, rather than
retrieving all users' memories and filtering afterward. ``get_all()``
is used instead of ``search()`` because Mem0's ``score_and_rank()``
was dropping valid results for small per-user result sets even with
a similarity threshold of 0.0.
"""
from __future__ import annotations

import os
import sys
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

# Ensure project root on sys.path.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from aios.memory.providers.mem0 import Mem0Provider


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

TEST_USER_ID = "alexandra_carter_0421d4d1__mem0_default"
TEST_AGENT = "assistant_agent"
TEST_CONTENT = "What should I focus on next?"


# ------------------------------------------------------------------
# Helper: create a Mem0Provider with a mock client
# ------------------------------------------------------------------


def _create_provider_with_mock_client() -> (
    "tuple[Mem0Provider, MagicMock]"
):
    """Create a Mem0Provider whose per-user client is a mock.

    Returns the provider and the mock client so tests can
    inspect what arguments were passed to client.get_all().

    The mock is installed both as provider.client (legacy) and
    as the per-user cached client for all user_ids via
    _get_client_for_user monkeypatch.
    """
    provider = Mem0Provider()
    mock_client = MagicMock()
    # Default: return empty results list
    mock_client.get_all.return_value = []
    provider.client = mock_client
    provider.default_user_id = "default"
    provider.default_agent_id = None

    # Monkeypatch _get_client_for_user to always return the
    # mock client, so per-user routing still exercises the
    # get_all call assertions.
    provider._get_client_for_user = lambda uid: mock_client

    return provider, mock_client


# ==================================================================
# Test Cases
# ==================================================================


class TestRetrieveMemoryUserIdPreFilter(unittest.TestCase):
    """retrieve_memory passes user_id into Mem0 get_all as a
    pre-filter (filters dict), not as a post-retrieval filter."""

    def test_user_id_passed_as_filter_to_get_all(self):
        """When params["user_id"] is provided, it must appear in
        the filters dict passed to client.get_all()."""
        provider, mock_client = _create_provider_with_mock_client()

        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={
                "content": TEST_CONTENT,
                "k": 5,
                "user_id": TEST_USER_ID,
                "agent_name": TEST_AGENT,
            },
        )

        provider.retrieve_memory(query)

        # client.get_all must have been called exactly once
        mock_client.get_all.assert_called_once()

        kwargs = mock_client.get_all.call_args[1]

        # The filters dict must contain user_id as a pre-filter
        filters = kwargs.get("filters", {})
        self.assertIn(
            "user_id",
            filters,
            "user_id must be passed inside the 'filters' dict "
            "to Mem0's get_all (pre-filter), not applied after.",
        )
        self.assertEqual(
            filters["user_id"],
            TEST_USER_ID,
            "The filter user_id must match the request's "
            "params['user_id'].",
        )

    def test_top_k_passed_to_get_all(self):
        """Per-user collections are small so the top_k=1000
        workaround is removed. get_all should be called
        without an explicit top_k argument."""
        provider, mock_client = _create_provider_with_mock_client()

        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={
                "content": TEST_CONTENT,
                "k": 3,
                "user_id": TEST_USER_ID,
            },
        )

        provider.retrieve_memory(query)

        kwargs = mock_client.get_all.call_args[1]
        self.assertNotIn(
            "top_k",
            kwargs,
            "top_k workaround should be removed for per-user collections.",
        )

    def test_no_user_id_falls_back_to_agent_name(self):
        """When user_id is absent, the filter should use
        agent_name as the scope (not None or empty)."""
        provider, mock_client = _create_provider_with_mock_client()

        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={
                "content": TEST_CONTENT,
                "k": 5,
                "agent_name": TEST_AGENT,
                # No user_id
            },
        )

        provider.retrieve_memory(query)

        kwargs = mock_client.get_all.call_args[1]
        filters = kwargs.get("filters", {})

        self.assertEqual(
            filters["user_id"],
            TEST_AGENT,
            "Without explicit user_id, the filter should fall "
            "back to agent_name.",
        )

    def test_no_user_id_no_agent_falls_back_to_default(self):
        """When both user_id and agent_name are absent, the filter
        should use the provider's default_user_id."""
        provider, mock_client = _create_provider_with_mock_client()

        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={
                "content": TEST_CONTENT,
                "k": 5,
                # No user_id, no agent_name
            },
        )

        provider.retrieve_memory(query)

        kwargs = mock_client.get_all.call_args[1]
        filters = kwargs.get("filters", {})

        self.assertEqual(
            filters["user_id"],
            "default",
            "Without user_id or agent_name, the filter should "
            "use the provider's default_user_id.",
        )
        # Must never be None
        self.assertIsNotNone(
            filters["user_id"],
            "user_id filter must never be None.",
        )

    def test_filter_is_not_none_when_user_id_absent(self):
        """The filters dict must never contain user_id=None.
        This would cause Mem0/ChromaDB errors or unscoped queries."""
        provider, mock_client = _create_provider_with_mock_client()

        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={
                "content": TEST_CONTENT,
                "k": 5,
                # Explicitly no user_id
            },
        )

        provider.retrieve_memory(query)

        kwargs = mock_client.get_all.call_args[1]
        filters = kwargs.get("filters", {})

        self.assertIsNotNone(
            filters.get("user_id"),
            "filters['user_id'] must never be None.",
        )


class TestRetrieveMemoryRawUserIdPreFilter(unittest.TestCase):
    """retrieve_memory_raw passes user_id into Mem0 get_all as a
    pre-filter, same as retrieve_memory."""

    def test_user_id_passed_as_filter_to_get_all(self):
        """When params["user_id"] is provided, it must appear in
        the filters dict passed to client.get_all()."""
        provider, mock_client = _create_provider_with_mock_client()

        query = MemoryQuery(
            operation_type="retrieve_memory_raw",
            params={
                "content": TEST_CONTENT,
                "k": 5,
                "user_id": TEST_USER_ID,
                "agent_name": TEST_AGENT,
            },
        )

        provider.retrieve_memory_raw(query)

        mock_client.get_all.assert_called_once()

        kwargs = mock_client.get_all.call_args[1]
        filters = kwargs.get("filters", {})

        self.assertIn(
            "user_id",
            filters,
            "user_id must be passed inside 'filters' dict "
            "for retrieve_memory_raw (pre-filter).",
        )
        self.assertEqual(
            filters["user_id"],
            TEST_USER_ID,
        )

    def test_no_user_id_falls_back_to_agent_name(self):
        """When user_id is absent, retrieve_memory_raw should
        fall back to agent_name in the filter."""
        provider, mock_client = _create_provider_with_mock_client()

        query = MemoryQuery(
            operation_type="retrieve_memory_raw",
            params={
                "content": TEST_CONTENT,
                "k": 5,
                "agent_name": TEST_AGENT,
            },
        )

        provider.retrieve_memory_raw(query)

        kwargs = mock_client.get_all.call_args[1]
        filters = kwargs.get("filters", {})

        self.assertEqual(
            filters["user_id"],
            TEST_AGENT,
        )

    def test_no_user_id_no_agent_falls_back_to_default(self):
        """Without user_id or agent_name, retrieve_memory_raw
        should use default_user_id in the filter."""
        provider, mock_client = _create_provider_with_mock_client()

        query = MemoryQuery(
            operation_type="retrieve_memory_raw",
            params={
                "content": TEST_CONTENT,
                "k": 5,
            },
        )

        provider.retrieve_memory_raw(query)

        kwargs = mock_client.get_all.call_args[1]
        filters = kwargs.get("filters", {})

        self.assertEqual(
            filters["user_id"],
            "default",
        )
        self.assertIsNotNone(filters["user_id"])

    def test_top_k_passed_to_get_all(self):
        """Per-user collections are small so the top_k=1000
        workaround is removed. get_all should be called
        without an explicit top_k argument."""
        provider, mock_client = _create_provider_with_mock_client()

        query = MemoryQuery(
            operation_type="retrieve_memory_raw",
            params={
                "content": TEST_CONTENT,
                "k": 7,
                "user_id": TEST_USER_ID,
            },
        )

        provider.retrieve_memory_raw(query)

        kwargs = mock_client.get_all.call_args[1]
        self.assertNotIn("top_k", kwargs)


class TestPreFilterNotPostFilter(unittest.TestCase):
    """Prove the user_id filter is applied AT the get_all layer,
    not as a post-retrieval Python filter on broad results."""

    def test_get_all_called_with_filter_before_results(self):
        """If user_id were a post-filter, client.get_all() would be
        called WITHOUT user_id in filters. Verify it IS present."""
        provider, mock_client = _create_provider_with_mock_client()

        # Return some results to make post-filtering plausible
        mock_client.get_all.return_value = [
            {
                "memory": "Some memory",
                "score": 0.9,
                "metadata": {
                    "user_id": TEST_USER_ID,
                    "owner_agent": "profile_agent",
                },
            }
        ]

        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={
                "content": TEST_CONTENT,
                "k": 5,
                "user_id": TEST_USER_ID,
                "agent_name": TEST_AGENT,
            },
        )

        provider.retrieve_memory(query)

        # The critical assertion: user_id was in the get_all
        # call's filters — meaning it was applied as a
        # pre-filter at the vector DB level.
        kwargs = mock_client.get_all.call_args[1]
        filters = kwargs.get("filters", {})
        self.assertEqual(
            filters["user_id"],
            TEST_USER_ID,
            "user_id must be a pre-filter in the get_all call, "
            "not a post-retrieval Python filter. If this fails, "
            "the provider is doing broad retrieval then filtering "
            "in Python — which doesn't scale.",
        )

    def test_agent_id_also_passed_as_pre_filter(self):
        """When agent_id is provided, it should also be in the
        filters dict (pre-filter at get_all layer)."""
        provider, mock_client = _create_provider_with_mock_client()

        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={
                "content": TEST_CONTENT,
                "k": 5,
                "user_id": TEST_USER_ID,
                "agent_id": "profile_agent",
            },
        )

        provider.retrieve_memory(query)

        kwargs = mock_client.get_all.call_args[1]
        filters = kwargs.get("filters", {})

        self.assertIn("agent_id", filters)
        self.assertEqual(filters["agent_id"], "profile_agent")


if __name__ == "__main__":
    unittest.main()
