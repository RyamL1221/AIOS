"""
Tests for Mem0Provider searchability polling logic.

Covers:
- add_memory() polls get_all() until the memory ID appears
- Delayed indexing succeeds without fixed sleep workarounds
- Timeout logs a warning but still returns success=True
- _extract_memory_id() handles all expected Mem0 response shapes
- _normalize_get_all_result() handles list and dict response shapes

No real Mem0 service, ChromaDB, LLM credentials, or network
access required.
"""
import logging
import pytest

from aios.memory.providers.mem0 import Mem0Provider
from aios.memory.note import MemoryNote


# ------------------------------------------------------------------
# Fake Mem0 clients
# ------------------------------------------------------------------


class FakeDelayedMem0Client:
    """Simulates delayed indexing: get_all() returns empty until
    the Nth call."""

    def __init__(self, visible_after_calls: int = 3):
        self.get_all_calls = 0
        self.visible_after_calls = visible_after_calls
        self.last_add_result = {"id": "mem-123"}

    def add(self, content, **kwargs):
        return self.last_add_result

    def get_all(self, **kwargs):
        self.get_all_calls += 1
        if self.get_all_calls < self.visible_after_calls:
            return []
        return [{"id": "mem-123", "memory": "stored fact"}]


class FakeNeverVisibleMem0Client:
    """Simulates a memory that never becomes visible through
    get_all() — always returns empty."""

    def __init__(self):
        self.get_all_calls = 0

    def add(self, content, **kwargs):
        return {"id": "mem-timeout"}

    def get_all(self, **kwargs):
        self.get_all_calls += 1
        return []


class FakeGetAllErrorClient:
    """Simulates intermittent get_all() failures followed by
    eventual visibility."""

    def __init__(self):
        self.get_all_calls = 0

    def add(self, content, **kwargs):
        return {"id": "mem-retry"}

    def get_all(self, **kwargs):
        self.get_all_calls += 1
        if self.get_all_calls <= 2:
            raise ConnectionError("transient failure")
        return [{"id": "mem-retry", "memory": "data"}]


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def provider():
    """Create a Mem0Provider without calling initialize().

    Patches _get_client_for_user to return provider.client so
    that add_memory() (which calls _get_client_for_user in
    production) routes to the test's fake client.
    """
    p = Mem0Provider()
    p.default_user_id = "test-user"
    p._get_client_for_user = lambda uid: p.client
    return p


@pytest.fixture
def memory_note():
    """A simple MemoryNote for testing."""
    return MemoryNote(
        content="Test memory content",
        keywords=["test"],
        tags=["unit"],
        category="Testing",
        context="General",
    )


@pytest.fixture(autouse=True)
def patch_sleep(monkeypatch):
    """Patch time.sleep so tests run instantly."""
    monkeypatch.setattr(
        "aios.memory.providers.mem0.time.sleep", lambda _: None
    )


# ------------------------------------------------------------------
# Tests: add_memory() polling behaviour
# ------------------------------------------------------------------


class TestAddMemorySearchabilityPolling:
    """Tests proving add_memory() waits for the memory to appear."""

    def test_waits_until_memory_is_searchable(
        self, provider, memory_note
    ):
        """add_memory() polls get_all() and succeeds once memory
        appears on the 3rd call."""
        client = FakeDelayedMem0Client(visible_after_calls=3)
        provider.client = client

        response = provider.add_memory(memory_note)

        assert response.success is True
        assert response.memory_id == "mem-123"
        # 1 diagnostic call + 2 _await_searchable polls
        # (visible_after_calls=3 means call #3 returns results)
        assert client.get_all_calls == 3

    def test_delayed_visibility_first_call(
        self, provider, memory_note
    ):
        """Memory visible on first get_all() call — no extra
        polling needed."""
        client = FakeDelayedMem0Client(visible_after_calls=1)
        provider.client = client

        response = provider.add_memory(memory_note)

        assert response.success is True
        assert response.memory_id == "mem-123"
        # +1 for the diagnostic get_all call added after add
        assert client.get_all_calls == 2

    def test_timeout_logs_warning_but_returns_success(
        self, provider, memory_note, caplog
    ):
        """When memory never becomes visible, add_memory() still
        returns success and logs a warning."""
        client = FakeNeverVisibleMem0Client()
        provider.client = client

        with caplog.at_level(logging.WARNING):
            response = provider.add_memory(memory_note)

        assert response.success is True
        assert response.memory_id == "mem-timeout"
        # get_all was called multiple times
        assert client.get_all_calls > 1
        # Warning was logged
        assert any(
            "not searchable" in record.message
            for record in caplog.records
        )

    def test_get_all_failures_are_retried(
        self, provider, memory_note, caplog
    ):
        """Transient get_all() exceptions are logged and retried;
        add_memory() still succeeds once visibility is confirmed."""
        client = FakeGetAllErrorClient()
        provider.client = client

        with caplog.at_level(logging.ERROR):
            response = provider.add_memory(memory_note)

        assert response.success is True
        assert response.memory_id == "mem-retry"
        # 1 diagnostic call (raises, caught) + 2 _await polls
        # (call 2 raises, call 3 succeeds)
        assert client.get_all_calls == 3
        # Exception was logged
        assert any(
            "failed while checking searchability"
            in record.message
            for record in caplog.records
        )

    def test_memory_id_field_variant(
        self, provider, memory_note
    ):
        """get_all() returns memories with 'memory_id' field
        instead of 'id'."""
        class MemoryIdFieldClient:
            def __init__(self):
                self.get_all_calls = 0

            def add(self, content, **kwargs):
                return {"id": "mem-variant"}

            def get_all(self, **kwargs):
                self.get_all_calls += 1
                return [
                    {"memory_id": "mem-variant", "memory": "x"}
                ]

        client = MemoryIdFieldClient()
        provider.client = client

        response = provider.add_memory(memory_note)

        assert response.success is True
        assert response.memory_id == "mem-variant"
        # +1 for the diagnostic get_all call added after add
        assert client.get_all_calls == 2

    def test_dict_wrapped_get_all_response(
        self, provider, memory_note
    ):
        """get_all() returns a dict with 'results' key wrapping
        the memories list."""
        class DictWrappedClient:
            def __init__(self):
                self.get_all_calls = 0

            def add(self, content, **kwargs):
                return {"id": "mem-wrapped"}

            def get_all(self, **kwargs):
                self.get_all_calls += 1
                return {
                    "results": [
                        {"id": "mem-wrapped", "memory": "x"}
                    ]
                }

        provider.client = DictWrappedClient()

        response = provider.add_memory(memory_note)

        assert response.success is True
        assert response.memory_id == "mem-wrapped"


# ------------------------------------------------------------------
# Tests: _extract_memory_id()
# ------------------------------------------------------------------


class TestExtractMemoryId:
    """Unit tests for _extract_memory_id() covering all expected
    Mem0 response shapes."""

    def test_dict_with_id(self, provider):
        assert provider._extract_memory_id(
            {"id": "abc"}
        ) == "abc"

    def test_dict_with_memory_id(self, provider):
        assert provider._extract_memory_id(
            {"memory_id": "abc"}
        ) == "abc"

    def test_dict_with_results_list_id(self, provider):
        assert provider._extract_memory_id(
            {"results": [{"id": "abc"}]}
        ) == "abc"

    def test_dict_with_results_list_memory_id(self, provider):
        assert provider._extract_memory_id(
            {"results": [{"memory_id": "abc"}]}
        ) == "abc"

    def test_dict_with_memories_key(self, provider):
        assert provider._extract_memory_id(
            {"memories": [{"memory_id": "abc"}]}
        ) == "abc"

    def test_dict_with_data_key(self, provider):
        assert provider._extract_memory_id(
            {"data": [{"id": "abc"}]}
        ) == "abc"

    def test_plain_list_with_id(self, provider):
        assert provider._extract_memory_id(
            [{"id": "abc"}]
        ) == "abc"

    def test_plain_list_with_memory_id(self, provider):
        assert provider._extract_memory_id(
            [{"memory_id": "abc"}]
        ) == "abc"

    def test_empty_dict(self, provider):
        assert provider._extract_memory_id({}) is None

    def test_empty_list(self, provider):
        assert provider._extract_memory_id([]) is None

    def test_none(self, provider):
        assert provider._extract_memory_id(None) is None

    def test_nested_empty_results(self, provider):
        assert provider._extract_memory_id(
            {"results": []}
        ) is None

    def test_id_coerced_to_string(self, provider):
        """Numeric IDs are converted to strings."""
        assert provider._extract_memory_id(
            {"id": 12345}
        ) == "12345"

    def test_first_item_in_list_wins(self, provider):
        """When multiple items are in a list, the first ID is
        returned."""
        result = provider._extract_memory_id(
            [{"id": "first"}, {"id": "second"}]
        )
        assert result == "first"


# ------------------------------------------------------------------
# Tests: _normalize_get_all_result()
# ------------------------------------------------------------------


class TestNormalizeGetAllResult:
    """Unit tests for _normalize_get_all_result() covering
    the response shapes Mem0 get_all() may return."""

    def test_plain_list(self, provider):
        data = [{"id": "abc"}]
        assert provider._normalize_get_all_result(data) == data

    def test_dict_with_results_key(self, provider):
        result = {"results": [{"id": "abc"}]}
        assert provider._normalize_get_all_result(result) == [
            {"id": "abc"}
        ]

    def test_dict_with_memories_key(self, provider):
        result = {"memories": [{"id": "abc"}]}
        assert provider._normalize_get_all_result(result) == [
            {"id": "abc"}
        ]

    def test_dict_with_data_key(self, provider):
        result = {"data": [{"id": "abc"}]}
        assert provider._normalize_get_all_result(result) == [
            {"id": "abc"}
        ]

    def test_dict_with_unexpected_key(self, provider):
        result = {"unexpected": [{"id": "abc"}]}
        assert provider._normalize_get_all_result(result) == []

    def test_none_input(self, provider):
        assert provider._normalize_get_all_result(None) == []

    def test_empty_list(self, provider):
        assert provider._normalize_get_all_result([]) == []

    def test_empty_dict(self, provider):
        assert provider._normalize_get_all_result({}) == []

    def test_string_input(self, provider):
        assert provider._normalize_get_all_result("hello") == []

    def test_priority_order_results_first(self, provider):
        """When multiple list keys exist, 'results' takes
        priority."""
        result = {
            "results": [{"id": "from-results"}],
            "memories": [{"id": "from-memories"}],
        }
        normalized = provider._normalize_get_all_result(result)
        assert normalized == [{"id": "from-results"}]
