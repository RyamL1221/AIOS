"""
Bug condition exploration tests for the profile-agent pre-write scoping bug.

These tests are EXPECTED TO FAIL on the unfixed code — their failure
confirms the bug exists. They encode the EXPECTED (correct) behavior:
once the fix is applied, they will PASS.

Property 1: Bug Condition — Pre-Write Retrieve Missing user_id Injection

    For all retrieve_memory syscalls processed by address_request() where:
      - query.params has NO user_id
      - self.latest_user_id IS NOT None
      - self.latest_user_id != memory_syscall.agent_name

    After address_request() processes the syscall:
      - query.params["user_id"] MUST equal self.latest_user_id

On unfixed code:
  - query.params["user_id"] is absent after address_request()
  - The retrieve is unscoped, returning memories from ALL users

Validates: Requirements 1.1, 2.1, 2.2
"""
from __future__ import annotations

import os
import sys
import unittest
from collections import OrderedDict
from typing import Any, Dict, List, Optional
from unittest.mock import patch, MagicMock

# Ensure project root on sys.path when invoked via pytest from any cwd.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hypothesis import given, settings, strategies as st, assume
from hypothesis import HealthCheck

from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from aios.memory.manager import MemoryManager
from aios.memory.providers.base import MemoryProvider
from aios.syscall.memory import MemorySyscall


# ------------------------------------------------------------------
# Test double: Mem0-shaped mock provider
# ------------------------------------------------------------------


class MockMem0Provider(MemoryProvider):
    """A Mem0-shaped provider that records retrieve calls.

    This is NOT an InHouseProvider or ZepProvider, so the
    MemoryManager's _provider_supports_barrier() returns True
    (matching real Mem0 behavior). It simply records calls and
    returns a success response.
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
        """Record the query and return empty results."""
        self.retrieve_calls.append(query)
        return MemoryResponse(success=True, search_results=[])

    def retrieve_memory_raw(
        self, query: MemoryQuery
    ) -> List[Any]:
        """Record the query and return empty list."""
        self.retrieve_calls.append(query)
        return []

    def close(self) -> None:
        pass


# ------------------------------------------------------------------
# Helper: Create a MemoryManager with mock provider
# ------------------------------------------------------------------


def _create_manager_with_mock() -> (
    "tuple[MemoryManager, MockMem0Provider]"
):
    """Create a MemoryManager with our mock Mem0-shaped provider.

    Patches the global config so MemoryManager doesn't try to
    read config.yaml or connect to real backends.
    """
    provider = MockMem0Provider()

    with patch(
        "aios.memory.manager.global_config"
    ) as mock_config:
        mock_config.get_memory_config.return_value = {}
        mock_config.get_storage_config.return_value = {}

        # Patch ProviderFactory.create to return our mock
        with patch(
            "aios.memory.manager.ProviderFactory.create",
            return_value=provider,
        ):
            manager = MemoryManager(
                log_mode="console", provider="mem0"
            )

    # Replace the provider in case it was overwritten
    manager.provider = provider
    return manager, provider


# ------------------------------------------------------------------
# Property-based exploration test
# ------------------------------------------------------------------


class ProfileAgentPreWriteScopingExplorationTests(
    unittest.TestCase
):
    """Property 1: Bug Condition — Pre-Write Retrieve Missing
    user_id Injection.

    **Validates: Requirements 1.1, 2.1, 2.2**
    """

    @given(
        agent_name=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="_",
            ),
            min_size=1,
            max_size=20,
        ),
        latest_user_id=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="_",
            ),
            min_size=1,
            max_size=30,
        ),
    )
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
            HealthCheck.filter_too_much,
        ],
    )
    def test_bug_condition_retrieve_injects_user_id(
        self,
        agent_name: str,
        latest_user_id: str,
    ) -> None:
        """Property 1: For all (agent_name, latest_user_id)
        where latest_user_id != agent_name and both are non-empty:

            After address_request() processes a retrieve_memory
            syscall with query.params containing NO user_id,
            query.params["user_id"] MUST equal latest_user_id.

        Bug condition:
            query.params.get("user_id") IS NULL
            AND self.latest_user_id IS NOT NULL
            AND self.latest_user_id != agent_name

        On unfixed code:
            query.params["user_id"] is absent → FAILS
            (This is correct — proves the bug exists)
        """
        # Precondition: latest_user_id must differ from agent_name
        assume(latest_user_id != agent_name)
        # Precondition: neither should be empty/whitespace-only
        assume(len(agent_name.strip()) > 0)
        assume(len(latest_user_id.strip()) > 0)

        # Create manager with mock provider
        manager, provider = _create_manager_with_mock()

        # Register a user_id so latest_user_id is set
        manager._register_user_id(latest_user_id)

        # Verify precondition: latest_user_id is correctly set
        assert manager.latest_user_id == latest_user_id

        # Build a retrieve_memory query with NO user_id in params
        # (this is what search_memories() in the SDK produces)
        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={"content": "user profile", "k": 5},
        )

        # Create a MemorySyscall (the way the kernel does it)
        syscall = MemorySyscall(agent_name, query)

        # Process the syscall through address_request()
        manager.address_request(syscall)

        # --- Property assertion ---
        # After address_request(), query.params["user_id"] MUST
        # equal self.latest_user_id.
        #
        # On UNFIXED code: query.params has no "user_id" key
        # because the retrieve_memory branch only adds agent_name.
        self.assertIn(
            "user_id",
            query.params,
            (
                f"BUG CONFIRMED: query.params has no 'user_id' "
                f"key after address_request(). "
                f"latest_user_id='{latest_user_id}' was available "
                f"but NOT injected into the retrieve query. "
                f"Params after processing: {query.params}"
            ),
        )

        self.assertEqual(
            query.params["user_id"],
            latest_user_id,
            (
                f"query.params['user_id']="
                f"'{query.params.get('user_id')}' but expected "
                f"latest_user_id='{latest_user_id}'"
            ),
        )

    def test_concrete_failing_case(self) -> None:
        """Concrete example from the task spec:

        MemorySyscall(agent_name="ProfileAgent") with
        query.params={"content": "user profile", "k": 5}
        when latest_user_id="user_alice"

        On unfixed code, query.params["user_id"] will be
        absent after address_request().
        """
        manager, provider = _create_manager_with_mock()

        # Register user_alice as the latest user
        manager._register_user_id("user_alice")
        assert manager.latest_user_id == "user_alice"

        # Build the exact query from the spec
        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={"content": "user profile", "k": 5},
        )

        syscall = MemorySyscall("ProfileAgent", query)

        # Process through address_request()
        manager.address_request(syscall)

        # Assert user_id was injected
        self.assertIn(
            "user_id",
            query.params,
            (
                "BUG CONFIRMED: query.params has no 'user_id' "
                "key after address_request(). "
                "latest_user_id='user_alice' was available but "
                "NOT injected. "
                f"Params: {query.params}"
            ),
        )
        self.assertEqual(
            query.params["user_id"],
            "user_alice",
            (
                f"Expected user_id='user_alice' but got "
                f"'{query.params.get('user_id')}'"
            ),
        )


if __name__ == "__main__":
    unittest.main()


# ------------------------------------------------------------------
# Property 2: Preservation — Non-Bug-Condition Retrieval Unchanged
# ------------------------------------------------------------------


class ProfileAgentPreWriteScopingPreservationTests(
    unittest.TestCase
):
    """Property 2: Preservation — Non-Bug-Condition Retrieval Params
    Unchanged.

    For all inputs where NOT isBugCondition(input), the query.params
    state after address_request() is identical to the observed behavior
    on unfixed code — i.e., no new user_id key is injected.

    Non-bug-condition cases:
      A: query.params already has an explicit user_id
      B: latest_user_id is None (empty registry)
      C: latest_user_id == agent_name (legacy single-user mode)
      D: Non-retrieve operations (add, update, get, remove)

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**
    """

    # ----------------------------------------------------------
    # Case A: Explicit user_id already present — NOT overridden
    # ----------------------------------------------------------

    @given(
        agent_name=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="_",
            ),
            min_size=1,
            max_size=20,
        ),
        latest_user_id=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="_",
            ),
            min_size=1,
            max_size=20,
        ),
        explicit_user_id=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="_",
            ),
            min_size=1,
            max_size=20,
        ),
        operation_type=st.sampled_from(
            ["retrieve_memory", "retrieve_memory_raw"]
        ),
    )
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
            HealthCheck.filter_too_much,
        ],
    )
    def test_case_a_explicit_user_id_preserved(
        self,
        agent_name: str,
        latest_user_id: str,
        explicit_user_id: str,
        operation_type: str,
    ) -> None:
        """Case A: When query.params already has an explicit user_id,
        it is NOT overridden by any injection logic.

        Observed on unfixed code: explicit user_id remains unchanged.
        """
        assume(len(agent_name.strip()) > 0)
        assume(len(latest_user_id.strip()) > 0)
        assume(len(explicit_user_id.strip()) > 0)

        manager, provider = _create_manager_with_mock()

        # Register a user_id so latest_user_id is available
        manager._register_user_id(latest_user_id)

        # Build query WITH an explicit user_id already in params
        query = MemoryQuery(
            operation_type=operation_type,
            params={
                "content": "test query",
                "k": 5,
                "user_id": explicit_user_id,
            },
        )

        syscall = MemorySyscall(agent_name, query)
        manager.address_request(syscall)

        # Property: explicit user_id must be preserved unchanged
        self.assertEqual(
            query.params["user_id"],
            explicit_user_id,
            (
                f"Explicit user_id was overridden! "
                f"Expected '{explicit_user_id}' but got "
                f"'{query.params.get('user_id')}'"
            ),
        )

    # ----------------------------------------------------------
    # Case B: latest_user_id is None — no user_id injected
    # ----------------------------------------------------------

    @given(
        agent_name=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="_",
            ),
            min_size=1,
            max_size=20,
        ),
        operation_type=st.sampled_from(
            ["retrieve_memory", "retrieve_memory_raw"]
        ),
    )
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
            HealthCheck.filter_too_much,
        ],
    )
    def test_case_b_no_latest_user_id_no_injection(
        self,
        agent_name: str,
        operation_type: str,
    ) -> None:
        """Case B: When latest_user_id is None (empty registry),
        no user_id is injected into query.params.

        Observed on unfixed code: query.params has no user_id key
        after address_request() when the registry is empty.
        """
        assume(len(agent_name.strip()) > 0)

        manager, provider = _create_manager_with_mock()

        # Do NOT register any user — latest_user_id is None
        assert manager.latest_user_id is None

        query = MemoryQuery(
            operation_type=operation_type,
            params={"content": "search query", "k": 3},
        )

        syscall = MemorySyscall(agent_name, query)
        manager.address_request(syscall)

        # Property: no user_id key should exist in params
        self.assertNotIn(
            "user_id",
            query.params,
            (
                f"user_id was injected when latest_user_id is "
                f"None! params={query.params}"
            ),
        )

    # ----------------------------------------------------------
    # Case C: latest_user_id == agent_name — no injection
    # ----------------------------------------------------------

    @given(
        agent_name=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="_",
            ),
            min_size=1,
            max_size=20,
        ),
        operation_type=st.sampled_from(
            ["retrieve_memory", "retrieve_memory_raw"]
        ),
    )
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
            HealthCheck.filter_too_much,
        ],
    )
    def test_case_c_latest_user_id_equals_agent_name_no_injection(
        self,
        agent_name: str,
        operation_type: str,
    ) -> None:
        """Case C: When latest_user_id == agent_name (legacy
        single-user mode), no user_id is injected.

        Observed on unfixed code: query.params has no user_id key
        after address_request() when latest_user_id matches agent_name.
        """
        assume(len(agent_name.strip()) > 0)

        manager, provider = _create_manager_with_mock()

        # Register the agent's own name as user_id
        # (legacy single-user mode)
        manager._register_user_id(agent_name)
        assert manager.latest_user_id == agent_name

        query = MemoryQuery(
            operation_type=operation_type,
            params={"content": "test content", "k": 5},
        )

        syscall = MemorySyscall(agent_name, query)
        manager.address_request(syscall)

        # Property: no user_id key should exist in params
        # (legacy behavior — agent_name == latest_user_id means
        # no multi-user context available)
        self.assertNotIn(
            "user_id",
            query.params,
            (
                f"user_id was injected when latest_user_id == "
                f"agent_name='{agent_name}'! This breaks legacy "
                f"single-user mode. params={query.params}"
            ),
        )

    # ----------------------------------------------------------
    # Case D: Non-retrieve operations — completely unaffected
    # ----------------------------------------------------------

    @given(
        agent_name=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="_",
            ),
            min_size=1,
            max_size=20,
        ),
        latest_user_id=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="_",
            ),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
            HealthCheck.filter_too_much,
        ],
    )
    def test_case_d_non_retrieve_ops_unaffected(
        self,
        agent_name: str,
        latest_user_id: str,
    ) -> None:
        """Case D: Non-retrieve operations (add_memory,
        update_memory, get_memory, remove_memory) are completely
        unaffected regardless of latest_user_id state.

        Observed on unfixed code: these operations do not read or
        modify user_id scoping based on latest_user_id.
        """
        assume(len(agent_name.strip()) > 0)
        assume(len(latest_user_id.strip()) > 0)
        assume(latest_user_id != agent_name)

        manager, provider = _create_manager_with_mock()
        manager._register_user_id(latest_user_id)

        # --- add_memory: verify it processes normally ---
        add_query = MemoryQuery(
            operation_type="add_memory",
            params={
                "content": "test memory content",
                "metadata": {"user_id": "some_user"},
            },
        )
        add_syscall = MemorySyscall(agent_name, add_query)
        add_resp = manager.address_request(add_syscall)
        self.assertTrue(
            add_resp.success,
            f"add_memory should succeed; got error: "
            f"{getattr(add_resp, 'error', None)}",
        )

        # --- get_memory: verify it processes normally ---
        get_query = MemoryQuery(
            operation_type="get_memory",
            params={"memory_id": "test-id-123"},
        )
        get_syscall = MemorySyscall(agent_name, get_query)
        # get_memory returns not-found from mock, but should
        # not crash
        get_resp = manager.address_request(get_syscall)
        # Mock returns success=False with error="not found" —
        # that's the expected mock behavior, not a test failure
        self.assertIsNotNone(get_resp)

        # --- update_memory: verify it processes normally ---
        update_query = MemoryQuery(
            operation_type="update_memory",
            params={
                "content": "updated content",
                "memory_id": "test-id-123",
            },
        )
        update_syscall = MemorySyscall(agent_name, update_query)
        update_resp = manager.address_request(update_syscall)
        self.assertTrue(
            update_resp.success,
            f"update_memory should succeed; got error: "
            f"{getattr(update_resp, 'error', None)}",
        )

        # --- remove_memory: verify it processes normally ---
        remove_query = MemoryQuery(
            operation_type="remove_memory",
            params={"memory_id": "test-id-456"},
        )
        remove_syscall = MemorySyscall(agent_name, remove_query)
        remove_resp = manager.address_request(remove_syscall)
        self.assertTrue(
            remove_resp.success,
            f"remove_memory should succeed; got error: "
            f"{getattr(remove_resp, 'error', None)}",
        )
