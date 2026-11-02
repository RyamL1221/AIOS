"""
Tests for Mem0Provider's response parsing.

Covers:
- _extract_memory_id() handles all expected Mem0 response shapes
- _normalize_get_all_result() handles list and dict response shapes
- (add waiting until a write is readable: test_mem0_contract_unit.py)

No real Mem0 service, ChromaDB, LLM credentials, or network
access required.
"""
import pytest

from aios.memory.providers.mem0 import Mem0Provider


# ------------------------------------------------------------------
# Fake Mem0 clients
# ------------------------------------------------------------------


@pytest.fixture
def provider():
    """A Mem0Provider without initialize()."""
    return Mem0Provider()


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
