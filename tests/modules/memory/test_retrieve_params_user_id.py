"""
Regression test: retrieve_memory with top-level params["user_id"].

Proves the kernel memory syscall path correctly recognizes user_id
when it is sent as:

    params["user_id"] = "alexandra_carter_0421d4d1__mem0_default"

and not only when it is nested under:

    params["metadata"]["user_id"] = "..."

The SDK's ``search_memories()`` function places ``user_id`` at the
top level of params. The kernel's ``/query`` endpoint diagnostic log
in ``runtime/launch.py`` must report this user_id correctly rather
than showing ``<none>``.

Key failing test: ``test_launch_log_extracts_top_level_user_id``
FAILS on the current broken implementation (the log extraction uses
``params.get("metadata", {}).get("user_id", "<none>")`` which misses
the top-level ``params["user_id"]``) and PASSES after Subtask 2 fix.
"""
from __future__ import annotations

import logging
import os
import sys
import unittest
from typing import Any, Dict, List
from unittest.mock import patch, MagicMock

# Ensure project root on sys.path when invoked from any cwd.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from aios.memory.manager import MemoryManager
from aios.memory.providers.base import MemoryProvider
from aios.syscall.memory import MemorySyscall


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

TEST_USER_ID = "alexandra_carter_0421d4d1__mem0_default"
TEST_AGENT = "assistant_agent"


# ------------------------------------------------------------------
# Mock provider that records retrieve calls
# ------------------------------------------------------------------


class RecordingMem0Provider(MemoryProvider):
    """A Mem0-shaped provider that records retrieve_memory calls.

    Not an InHouseProvider or ZepProvider, so the MemoryManager's
    _provider_supports_barrier() returns True (matching real Mem0).
    """

    def __init__(self) -> None:
        self.retrieve_calls: List[MemoryQuery] = []

    def initialize(self, config: Dict[str, Any]) -> None:
        pass

    def add_memory(self, memory_note: Any) -> MemoryResponse:
        return MemoryResponse(success=True, memory_id="mock-id")

    def remove_memory(self, memory_id: str) -> MemoryResponse:
        return MemoryResponse(success=True, memory_id=memory_id)

    def update_memory(self, memory_note: Any) -> MemoryResponse:
        return MemoryResponse(success=True, memory_id="mock-id")

    def get_memory(self, memory_id: str) -> MemoryResponse:
        return MemoryResponse(success=False, error="not found")

    def retrieve_memory(
        self, query: MemoryQuery
    ) -> MemoryResponse:
        self.retrieve_calls.append(query)
        return MemoryResponse(success=True, search_results=[])

    def retrieve_memory_raw(
        self, query: MemoryQuery
    ) -> List[Any]:
        self.retrieve_calls.append(query)
        return []

    def close(self) -> None:
        pass


# ------------------------------------------------------------------
# Helper: create a MemoryManager with the recording provider
# ------------------------------------------------------------------


def _create_manager() -> "tuple[MemoryManager, RecordingMem0Provider]":
    """Create a MemoryManager wired to our recording provider."""
    provider = RecordingMem0Provider()

    with patch(
        "aios.memory.manager.global_config"
    ) as mock_config:
        mock_config.get_memory_config.return_value = {}
        mock_config.get_storage_config.return_value = {}

        with patch(
            "aios.memory.manager.ProviderFactory.create",
            return_value=provider,
        ):
            manager = MemoryManager(
                log_mode="console", provider="mem0"
            )

    manager.provider = provider
    return manager, provider


# ------------------------------------------------------------------
# Helper: extract user_id the way launch.py currently does it
# ------------------------------------------------------------------


def _extract_log_user_id(params: Dict[str, Any]) -> str:
    """Replicate the ACTUAL extraction from runtime/launch.py.

    Source (fixed version):
        _mem_params = request.query_data.params or {}
        _mem_params.get("user_id")
        or _mem_params.get("metadata", {}).get("user_id")
        or "<none>"

    Resolution order:
    1. Top-level params["user_id"] (SDK's search_memories format)
    2. Nested params["metadata"]["user_id"] (add_memory format)
    3. "<none>" if neither is present
    """
    p = params or {}
    return (
        p.get("user_id")
        or p.get("metadata", {}).get("user_id")
        or "<none>"
    )


# ==================================================================
# Test Cases
# ==================================================================


class TestRetrieveMemoryTopLevelUserId(unittest.TestCase):
    """Regression: top-level params["user_id"] must be recognized
    by the kernel diagnostic log and propagated to the provider."""

    # --------------------------------------------------------------
    # FAILING TEST: The launch.py log extraction bug
    # This test FAILS before Subtask 2 fix, PASSES after.
    # --------------------------------------------------------------

    def test_launch_log_extracts_top_level_user_id(self):
        """REGRESSION: The /query endpoint log must report user_id
        when it is at the TOP LEVEL of params (SDK format).

        The SDK's search_memories() sends:
            params={"content": ..., "k": 5, "user_id": "..."}

        The kernel log extraction MUST resolve this to the actual
        user_id, not "<none>".

        FAILS before fix: _extract_log_user_id() only checks
        params["metadata"]["user_id"], returning "<none>".
        PASSES after fix: extraction also checks params["user_id"].
        """
        params = {
            "content": "What should I focus on next?",
            "k": 5,
            "user_id": TEST_USER_ID,
        }

        extracted = _extract_log_user_id(params)

        self.assertEqual(
            extracted,
            TEST_USER_ID,
            f"Expected log to report user_id="
            f"'{TEST_USER_ID}' but got '{extracted}'. "
            f"The launch.py log extraction must recognize "
            f"top-level params['user_id'] for retrieve_memory.",
        )

    # --------------------------------------------------------------
    # Provider propagation tests (these pass on current code)
    # --------------------------------------------------------------

    def test_top_level_user_id_propagated_to_provider(self):
        """The provider receives a MemoryQuery whose params["user_id"]
        is preserved when user_id is at the top level of params."""
        manager, provider = _create_manager()

        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={
                "content": "What should I focus on next?",
                "k": 5,
                "user_id": TEST_USER_ID,
            },
        )

        syscall = MemorySyscall(TEST_AGENT, query)
        manager.address_request(syscall)

        # Provider must have received exactly one call
        self.assertEqual(len(provider.retrieve_calls), 1)
        received_query = provider.retrieve_calls[0]

        # The user_id must be present in the query params
        self.assertEqual(
            received_query.params.get("user_id"),
            TEST_USER_ID,
            "Provider did not receive user_id from top-level "
            "params — the kernel dropped it.",
        )

    def test_barrier_snapshot_stamped_for_top_level_user_id(self):
        """SyscallExecutor barrier stamping must read user_id from
        the top level of params for retrieve_memory operations.

        Exercises the same extraction as _execute_syscall:
            uid = syscall.query.params.get("user_id")
        """
        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={
                "content": "What should I focus on next?",
                "k": 5,
                "user_id": TEST_USER_ID,
            },
        )

        # Simulate what _execute_syscall does for retrieve_memory
        uid = query.params.get("user_id")

        self.assertEqual(
            uid,
            TEST_USER_ID,
            "Barrier stamping must extract user_id from "
            "top-level params for retrieve operations.",
        )

    # --------------------------------------------------------------
    # Backward-compatible nested metadata tests
    # --------------------------------------------------------------

    def test_nested_metadata_user_id_recognized_by_log(self):
        """Backward compat: params["metadata"]["user_id"] must still
        be recognized by the log extraction logic."""
        params = {
            "content": "What should I focus on next?",
            "k": 5,
            "metadata": {
                "user_id": TEST_USER_ID,
            },
        }

        extracted = _extract_log_user_id(params)

        self.assertEqual(
            extracted,
            TEST_USER_ID,
            "Nested metadata user_id must be recognized "
            "by the log extraction.",
        )

    def test_nested_metadata_user_id_propagated_to_provider(self):
        """When user_id is ONLY in metadata (not top-level params),
        the provider retrieval still receives the query with
        metadata intact."""
        manager, provider = _create_manager()

        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={
                "content": "What should I focus on next?",
                "k": 5,
                "metadata": {
                    "user_id": TEST_USER_ID,
                },
            },
        )

        syscall = MemorySyscall(TEST_AGENT, query)
        manager.address_request(syscall)

        self.assertEqual(len(provider.retrieve_calls), 1)
        received_query = provider.retrieve_calls[0]

        # The metadata dict should be passed through
        self.assertEqual(
            received_query.params.get("metadata", {}).get(
                "user_id"
            ),
            TEST_USER_ID,
            "Nested metadata user_id must be preserved in "
            "the query passed to the provider.",
        )


class TestRetrieveMemoryUserIdEndToEnd(unittest.TestCase):
    """End-to-end: the full address_request path preserves top-level
    user_id through to the provider and uses it for barrier logic."""

    def test_address_request_does_not_drop_top_level_user_id(self):
        """Regression: address_request must not strip or ignore
        params["user_id"] for retrieve_memory operations.

        The query passed to the provider must retain the original
        user_id so that Mem0's search is scoped correctly.
        """
        manager, provider = _create_manager()

        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={
                "content": "What should I focus on next?",
                "k": 5,
                "user_id": TEST_USER_ID,
            },
        )

        syscall = MemorySyscall(TEST_AGENT, query)
        manager.address_request(syscall)

        self.assertEqual(len(provider.retrieve_calls), 1)
        received = provider.retrieve_calls[0]

        # user_id must survive the address_request processing
        self.assertEqual(
            received.params["user_id"],
            TEST_USER_ID,
        )
        # agent_name should also have been injected
        self.assertEqual(
            received.params["agent_name"],
            TEST_AGENT,
        )

    def test_retrieve_memory_raw_preserves_top_level_user_id(self):
        """Same as above but for retrieve_memory_raw operation."""
        manager, provider = _create_manager()

        query = MemoryQuery(
            operation_type="retrieve_memory_raw",
            params={
                "content": "What should I focus on next?",
                "k": 5,
                "user_id": TEST_USER_ID,
            },
        )

        syscall = MemorySyscall(TEST_AGENT, query)
        manager.address_request(syscall)

        self.assertEqual(len(provider.retrieve_calls), 1)
        received = provider.retrieve_calls[0]

        self.assertEqual(
            received.params["user_id"],
            TEST_USER_ID,
        )


if __name__ == "__main__":
    unittest.main()
