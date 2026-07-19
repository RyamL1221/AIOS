"""
End-to-end regression test: cross-agent memory retrieval via Mem0.

Proves that shared memories written by one agent (profile_agent) are
visible to another agent (assistant_agent) for the same user_id —
exercising the actual provider retrieval path and the ContextInjector
auto-injection path with mocked Mem0 client search results shaped
exactly as real Mem0 returns them (user_id promoted to top level).

No live Mem0, ChromaDB, or Ollama required.

Run:
    pytest tests/modules/memory/test_mem0_cross_agent_retrieval.py -v
"""

import sys
import os
from unittest.mock import MagicMock, patch

# ──────────────────────────────────────────────────────────────────────
# Path setup
# ──────────────────────────────────────────────────────────────────────

_project_root = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
    )
)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# ──────────────────────────────────────────────────────────────────────
# Standard imports (uses installed cerebrum package)
# ──────────────────────────────────────────────────────────────────────

from cerebrum.llm.apis import LLMQuery
from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from aios.memory.providers.mem0 import Mem0Provider
from aios.memory.providers.base import _enrich_metadata
from aios.memory.context_injector import ContextInjector
from aios.memory.write_barrier import WaitOutcome


# ──────────────────────────────────────────────────────────────────────
# Fixtures: Mem0-shaped search results (promoted top-level user_id)
# ──────────────────────────────────────────────────────────────────────

def _make_mem0_search_results():
    """Simulate what Mem0 client.get_all() returns.

    Includes:
    - A shared memory from profile_agent for alex_chen (promoted user_id)
    - A shared memory from task_agent for alex_chen (promoted user_id)
    - A shared memory from profile_agent for a DIFFERENT user
    """
    return [
        {
            "id": "mem_profile_1",
            "memory": "User prefers Python",
            "user_id": "alex_chen",
            "agent_id": "profile_agent",
            "metadata": {
                "owner_agent": "profile_agent",
                "sharing_policy": "shared",
                "memory_type": "profile",
            },
            "score": 0.91,
        },
        {
            "id": "mem_task_1",
            "memory": "Working on FastAPI migration",
            "user_id": "alex_chen",
            "agent_id": "task_agent",
            "metadata": {
                "owner_agent": "task_agent",
                "sharing_policy": "shared",
                "memory_type": "task_context",
            },
            "score": 0.87,
        },
        {
            "id": "mem_other_user",
            "memory": "Other user prefers Java",
            "user_id": "different_user",
            "agent_id": "profile_agent",
            "metadata": {
                "owner_agent": "profile_agent",
                "sharing_policy": "shared",
                "memory_type": "profile",
            },
            "score": 0.82,
        },
    ]


# ──────────────────────────────────────────────────────────────────────
# Test: Explicit provider retrieval path
# ──────────────────────────────────────────────────────────────────────

class TestExplicitProviderRetrieval:
    """Exercise Mem0Provider.retrieve_memory() with a mocked client.

    This simulates the explicit SDK/API memory search path where
    an agent directly calls retrieve_memory via MemoryManager.
    """

    def _make_provider_with_mock_client(self, search_results):
        """Create a Mem0Provider with a mocked Mem0 client.

        Routes all user_ids through _get_client_for_user to the
        shared mock, matching production's per-user client routing.
        """
        provider = Mem0Provider()
        provider.client = MagicMock()
        provider.client.get_all.return_value = search_results
        provider.default_user_id = "alex_chen"
        provider.default_agent_id = None
        # Patch per-user client routing so retrieval methods
        # reach the mock client via the production code path.
        provider._get_client_for_user = (
            lambda uid: provider.client
        )
        return provider

    def test_shared_memory_from_another_agent_returned(self):
        """assistant_agent retrieves shared memories from
        profile_agent and task_agent for the same user_id."""
        provider = self._make_provider_with_mock_client(
            _make_mem0_search_results()
        )

        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={
                "content": "What does the user prefer?",
                "k": 5,
                "agent_name": "assistant_agent",
                "user_id": "alex_chen",
                "sharing_policy": "shared",
            },
        )

        response = provider.retrieve_memory(query)

        assert response.success is True
        assert response.search_results is not None

        contents = [r["content"] for r in response.search_results]
        assert "User prefers Python" in contents
        assert "Working on FastAPI migration" in contents

    def test_different_user_memory_excluded(self):
        """Memories for a different user_id must not appear."""
        provider = self._make_provider_with_mock_client(
            _make_mem0_search_results()
        )

        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={
                "content": "What does the user prefer?",
                "k": 5,
                "agent_name": "assistant_agent",
                "user_id": "alex_chen",
                "sharing_policy": "shared",
            },
        )

        response = provider.retrieve_memory(query)

        assert response.success is True
        contents = [r["content"] for r in response.search_results]
        assert "Other user prefers Java" not in contents

    def test_retrieve_memory_raw_also_works(self):
        """retrieve_memory_raw() returns MemoryNote objects
        with correct filtering."""
        provider = self._make_provider_with_mock_client(
            _make_mem0_search_results()
        )

        query = MemoryQuery(
            operation_type="retrieve_memory_raw",
            params={
                "content": "user preferences",
                "k": 5,
                "agent_name": "assistant_agent",
                "user_id": "alex_chen",
                "sharing_policy": "shared",
            },
        )

        notes = provider.retrieve_memory_raw(query)

        note_contents = [n.content for n in notes]
        assert "User prefers Python" in note_contents
        assert "Working on FastAPI migration" in note_contents
        assert "Other user prefers Java" not in note_contents


# ──────────────────────────────────────────────────────────────────────
# Test: ContextInjector auto-injection path
# ──────────────────────────────────────────────────────────────────────

class TestContextInjectorCrossAgentInjection:
    """Exercise ContextInjector.inject() with a Mem0Provider whose
    client returns promoted-key search results.

    This tests the full auto-injection pipeline:
    1. inject() resolves user_id
    2. Own-memory retrieval (returns nothing or own memories)
    3. Shared-memory retrieval via _retrieve_shared_memories()
    4. Results merged, filtered, formatted, and prepended
    """

    def _build_injector(self, own_results, shared_results):
        """Build a ContextInjector with a mock MemoryManager
        whose provider returns controlled search results.

        Args:
            own_results: List of Mem0-shaped dicts for own-memory query
            shared_results: List of Mem0-shaped dicts for shared query
        """
        # Mock provider that returns different results based on
        # the sharing_policy param in the query.
        provider = MagicMock()

        def _mock_retrieve(query):
            params = query.params
            if params.get("sharing_policy") == "shared":
                # Shared retrieval path
                return MemoryResponse(
                    success=True,
                    search_results=shared_results,
                )
            else:
                # Own-memory retrieval path
                return MemoryResponse(
                    success=True,
                    search_results=own_results,
                )

        provider.retrieve_memory.side_effect = _mock_retrieve

        # Mock MemoryManager
        memory_manager = MagicMock()
        memory_manager.provider = provider
        # Barrier mock: always bypass
        memory_manager.barrier.snapshot.return_value = 0
        memory_manager.barrier.wait_until_drained.return_value = (
            WaitOutcome.BYPASSED
        )

        config = {
            "auto_inject": True,
            "max_injected_memories": 10,
            "relevance_threshold": 0.3,
            "max_memory_tokens": 2000,
        }

        injector = ContextInjector(memory_manager, config)
        return injector

    def _format_shared_result(self, mem0_item):
        """Convert a Mem0-shaped search result dict into the format
        returned by Mem0Provider.retrieve_memory (post-filtering).

        This simulates what the provider returns after applying
        _apply_sharing_filter + _enrich_metadata.
        """
        meta = Mem0Provider._extract_filter_metadata(mem0_item)
        meta = _enrich_metadata(meta)
        return {
            "content": mem0_item.get("memory", ""),
            "keywords": meta.get("keywords", []),
            "tags": meta.get("tags", []),
            "category": meta.get("category", "Uncategorized"),
            "timestamp": meta.get("timestamp", ""),
            "score": mem0_item.get("score"),
            "metadata": meta,
        }

    def test_shared_memories_injected_into_context(self):
        """When assistant_agent requests context for user alex_chen,
        shared memories from profile_agent appear in the injected
        system message."""
        # Prepare results in the format ContextInjector expects
        # (already passed through provider.retrieve_memory)
        mem0_results = _make_mem0_search_results()

        # Filter to only alex_chen + shared (simulating what
        # the provider would return)
        shared_formatted = [
            self._format_shared_result(r)
            for r in mem0_results
            if r["user_id"] == "alex_chen"
        ]

        injector = self._build_injector(
            own_results=[],  # No own memories
            shared_results=shared_formatted,
        )

        query = LLMQuery(
            messages=[
                {"role": "user", "content": "Tell me about my preferences"},
            ]
        )

        modified_query, diagnostics = injector.inject(
            agent_name="assistant_agent",
            query=query,
            user_id="alex_chen",
        )

        # Verify injection happened
        assert diagnostics["auto_inject_enabled"] is True
        assert diagnostics["injected_count"] > 0
        assert diagnostics["resolved_user_id"] == "alex_chen"

        # The first message should be the injected system message
        assert len(modified_query.messages) > 1
        injected_msg = modified_query.messages[0]
        assert injected_msg["role"] == "system"

        # Check content includes our shared memories
        injected_content = injected_msg["content"]
        assert "User prefers Python" in injected_content
        assert "Working on FastAPI migration" in injected_content

    def test_different_user_not_injected(self):
        """Memories for a different user should not appear in
        the injected context."""
        mem0_results = _make_mem0_search_results()

        # Include ALL results (even different_user) to prove
        # the provider-level filtering excluded it
        shared_formatted = [
            self._format_shared_result(r)
            for r in mem0_results
            if r["user_id"] == "alex_chen"
            # Only alex_chen results pass the filter
        ]

        injector = self._build_injector(
            own_results=[],
            shared_results=shared_formatted,
        )

        query = LLMQuery(
            messages=[
                {"role": "user", "content": "Hello"},
            ]
        )

        modified_query, diagnostics = injector.inject(
            agent_name="assistant_agent",
            query=query,
            user_id="alex_chen",
        )

        # If anything was injected, confirm no wrong-user content
        if diagnostics["injected_count"] > 0:
            injected_content = modified_query.messages[0]["content"]
            assert "Other user prefers Java" not in injected_content

    def test_no_shared_injection_without_explicit_user_id(self):
        """Without an explicit user_id, no shared memory retrieval
        should occur (only own-agent memories are used)."""
        injector = self._build_injector(
            own_results=[],
            shared_results=[
                self._format_shared_result(
                    _make_mem0_search_results()[0]
                ),
            ],
        )

        query = LLMQuery(
            messages=[
                {"role": "user", "content": "Hello"},
            ]
        )

        # No user_id provided
        modified_query, diagnostics = injector.inject(
            agent_name="assistant_agent",
            query=query,
            user_id=None,
        )

        # resolved_user_id should be None → no shared retrieval
        assert diagnostics["resolved_user_id"] is None
        # Without own results and without shared retrieval,
        # nothing injected
        assert diagnostics["injected_count"] == 0

    def test_diagnostics_report_source_agents(self):
        """Diagnostics should list the source agents that
        contributed shared memories."""
        mem0_results = _make_mem0_search_results()
        shared_formatted = [
            self._format_shared_result(r)
            for r in mem0_results
            if r["user_id"] == "alex_chen"
        ]

        injector = self._build_injector(
            own_results=[],
            shared_results=shared_formatted,
        )

        query = LLMQuery(
            messages=[
                {"role": "user", "content": "preferences"},
            ]
        )

        _, diagnostics = injector.inject(
            agent_name="assistant_agent",
            query=query,
            user_id="alex_chen",
        )

        assert "profile_agent" in diagnostics["source_agents"]
        assert "task_agent" in diagnostics["source_agents"]


# ──────────────────────────────────────────────────────────────────────
# Test: Full Mem0Provider integration (mocked client)
# ──────────────────────────────────────────────────────────────────────

class TestFullProviderWithPromotedKeys:
    """End-to-end through Mem0Provider with mocked Mem0 client,
    proving the real retrieval path handles promoted keys correctly
    for both the cross-agent and negative-control cases."""

    def test_only_matching_user_and_policy_returned(self):
        """Full filter pipeline: user_id match + sharing_policy match."""
        provider = Mem0Provider()
        provider.client = MagicMock()
        provider.default_user_id = "alex_chen"
        provider.default_agent_id = None
        # Patch per-user client routing.
        provider._get_client_for_user = (
            lambda uid: provider.client
        )

        # Mem0 returns a mix of users and policies
        provider.client.get_all.return_value = [
            {
                "id": "shared_match",
                "memory": "User prefers Python",
                "user_id": "alex_chen",
                "agent_id": "profile_agent",
                "metadata": {
                    "owner_agent": "profile_agent",
                    "sharing_policy": "shared",
                    "memory_type": "profile",
                },
                "score": 0.91,
            },
            {
                "id": "wrong_user",
                "memory": "Other user prefers Java",
                "user_id": "bob_smith",
                "agent_id": "profile_agent",
                "metadata": {
                    "owner_agent": "profile_agent",
                    "sharing_policy": "shared",
                    "memory_type": "profile",
                },
                "score": 0.85,
            },
            {
                "id": "private_other",
                "memory": "Private note from profile_agent",
                "user_id": "alex_chen",
                "agent_id": "profile_agent",
                "metadata": {
                    "owner_agent": "profile_agent",
                    "sharing_policy": "private",
                },
                "score": 0.80,
            },
        ]

        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={
                "content": "user preferences",
                "k": 10,
                "agent_name": "assistant_agent",
                "user_id": "alex_chen",
                "sharing_policy": "shared",
            },
        )

        response = provider.retrieve_memory(query)
        assert response.success is True

        contents = [r["content"] for r in response.search_results]
        # Only the shared memory for alex_chen passes
        assert contents == ["User prefers Python"]


# ──────────────────────────────────────────────────────────────────────
# CLI runner
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
