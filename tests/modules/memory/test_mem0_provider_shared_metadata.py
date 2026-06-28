"""
Regression test: Mem0 promoted metadata and cross-agent sharing filter.

Mem0's _search_vector_store() promotes certain payload keys (user_id,
agent_id, run_id, actor_id, role) to TOP-LEVEL fields in the returned
dict and EXCLUDES them from the nested item["metadata"] dict.

This means a shared memory from profile_agent will look like:

    {
        "id": "mem_1",
        "memory": "User prefers Python",
        "user_id": "alex_chen",        <-- promoted to top level
        "agent_id": "profile_agent",   <-- promoted to top level
        "metadata": {
            "owner_agent": "profile_agent",
            "sharing_policy": "shared",
            "memory_type": "profile",
        },
        "score": 0.91,
    }

Without _extract_filter_metadata() merging the promoted keys back
into a unified dict, _apply_sharing_filter's `meta.get("user_id")`
would return "" and silently drop valid shared results.

This test verifies:
1. Promoted user_id (top-level) is correctly merged for filtering.
2. Backward-compatible shape (user_id inside metadata) still works.
3. The filter retains shared memories visible to a different agent.
4. The filter drops private memories from other agents.

Run:
    pytest tests/modules/memory/test_mem0_provider_shared_metadata.py -v
"""

import sys
import os
import types

# Ensure project root is on the path
sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
        )
    ),
)

# Stub out heavy dependencies so we can import only the
# functions under test without the full dependency tree.
_cerebrum_stub = types.ModuleType("cerebrum")
_memory_stub = types.ModuleType("cerebrum.memory")
_apis_stub = types.ModuleType("cerebrum.memory.apis")


class _MemoryQuery:
    pass


class _MemoryResponse:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


_apis_stub.MemoryQuery = _MemoryQuery
_apis_stub.MemoryResponse = _MemoryResponse
_memory_stub.apis = _apis_stub
_cerebrum_stub.memory = _memory_stub

sys.modules.setdefault("cerebrum", _cerebrum_stub)
sys.modules.setdefault("cerebrum.memory", _memory_stub)
sys.modules.setdefault("cerebrum.memory.apis", _apis_stub)

# We only need _apply_sharing_filter from base.py and
# _extract_filter_metadata from mem0.py.  Import them
# directly to avoid pulling in InHouseProvider, retrievers,
# sentence_transformers, etc via __init__.py.
import importlib.util

def _import_module_directly(name, filepath):
    """Import a single module file without triggering __init__.py."""
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_project_root = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
    )
)

_base_mod = _import_module_directly(
    "aios.memory.providers.base",
    os.path.join(
        _project_root,
        "aios", "memory", "providers", "base.py",
    ),
)

_mem0_mod = _import_module_directly(
    "aios.memory.providers.mem0",
    os.path.join(
        _project_root,
        "aios", "memory", "providers", "mem0.py",
    ),
)

_apply_sharing_filter = _base_mod._apply_sharing_filter
_extract_filter_metadata = _mem0_mod.Mem0Provider._extract_filter_metadata


# ──────────────────────────────────────────────────────────────────────
# Fixtures: simulated Mem0 search results
# ──────────────────────────────────────────────────────────────────────

def _promoted_shared_result():
    """Mem0 result shape with user_id promoted to top level.

    This is the real shape returned by Mem0 >= 0.1.x when user_id
    was provided at add() time — it gets promoted out of metadata.
    """
    return {
        "id": "mem_shared_1",
        "memory": "User prefers Python",
        "user_id": "alex_chen",
        "agent_id": "profile_agent",
        "metadata": {
            "owner_agent": "profile_agent",
            "sharing_policy": "shared",
            "memory_type": "profile",
        },
        "score": 0.91,
    }


def _nested_shared_result():
    """Backward-compatible shape: user_id inside metadata dict."""
    return {
        "id": "mem_shared_2",
        "memory": "User is working on a FastAPI project",
        "metadata": {
            "user_id": "alex_chen",
            "owner_agent": "task_agent",
            "sharing_policy": "shared",
            "memory_type": "task_context",
        },
        "score": 0.88,
    }


def _promoted_private_result():
    """Private memory from another agent — should be dropped."""
    return {
        "id": "mem_private_1",
        "memory": "Internal agent state note",
        "user_id": "alex_chen",
        "agent_id": "profile_agent",
        "metadata": {
            "owner_agent": "profile_agent",
            "sharing_policy": "private",
            "memory_type": "profile",
        },
        "score": 0.85,
    }


def _own_agent_result():
    """Memory owned by the requesting agent (assistant_agent)."""
    return {
        "id": "mem_own_1",
        "memory": "Previous conversation context",
        "user_id": "alex_chen",
        "agent_id": "assistant_agent",
        "metadata": {
            "owner_agent": "assistant_agent",
            "sharing_policy": "private",
            "memory_type": "conversation",
            "user_id": "alex_chen",
        },
        "score": 0.80,
    }


# ──────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────

class TestExtractFilterMetadata:
    """Unit tests for Mem0Provider._extract_filter_metadata."""

    def test_promotes_user_id_from_top_level(self):
        """user_id at top level should appear in merged metadata."""
        item = _promoted_shared_result()
        meta = _extract_filter_metadata(item)
        assert meta["user_id"] == "alex_chen"

    def test_promotes_agent_id_from_top_level(self):
        """agent_id at top level should appear in merged metadata."""
        item = _promoted_shared_result()
        meta = _extract_filter_metadata(item)
        assert meta["agent_id"] == "profile_agent"

    def test_nested_user_id_preserved(self):
        """user_id already in metadata should remain untouched."""
        item = _nested_shared_result()
        meta = _extract_filter_metadata(item)
        assert meta["user_id"] == "alex_chen"

    def test_does_not_overwrite_existing_metadata_key(self):
        """If user_id exists in BOTH places, metadata wins."""
        item = {
            "memory": "test",
            "user_id": "top_level_id",
            "metadata": {"user_id": "nested_id"},
        }
        meta = _extract_filter_metadata(item)
        # metadata key should not be overwritten by top-level
        assert meta["user_id"] == "nested_id"


class TestSharingFilterWithPromotedMetadata:
    """Integration tests: _apply_sharing_filter + _extract_filter_metadata.

    These simulate what happens inside Mem0Provider.retrieve_memory
    when the requesting agent differs from the memory owner.
    """

    def test_shared_memory_visible_with_promoted_user_id(self):
        """A shared memory with promoted user_id should be retained
        when assistant_agent requests memories for user alex_chen.

        This is the core regression case. Before the
        _extract_filter_metadata fix, user_id would be missing from
        the metadata dict passed to _apply_sharing_filter, causing
        mem_user == "" which != "alex_chen", dropping the result.
        """
        candidates = [_promoted_shared_result()]
        requesting_agent = "assistant_agent"
        user_id = "alex_chen"
        sharing_policy = "shared"

        results = _apply_sharing_filter(
            candidates,
            requesting_agent,
            user_id,
            sharing_policy,
            _extract_filter_metadata,
        )

        assert len(results) == 1
        assert results[0]["memory"] == "User prefers Python"

    def test_shared_memory_visible_with_nested_user_id(self):
        """Backward-compatible: user_id inside metadata should also work."""
        candidates = [_nested_shared_result()]
        requesting_agent = "assistant_agent"
        user_id = "alex_chen"
        sharing_policy = "shared"

        results = _apply_sharing_filter(
            candidates,
            requesting_agent,
            user_id,
            sharing_policy,
            _extract_filter_metadata,
        )

        assert len(results) == 1
        assert (
            results[0]["memory"]
            == "User is working on a FastAPI project"
        )

    def test_private_memory_from_other_agent_dropped(self):
        """Private memory from profile_agent should NOT be visible
        to assistant_agent, even with matching user_id."""
        candidates = [_promoted_private_result()]
        requesting_agent = "assistant_agent"
        user_id = "alex_chen"
        sharing_policy = "shared"

        results = _apply_sharing_filter(
            candidates,
            requesting_agent,
            user_id,
            sharing_policy,
            _extract_filter_metadata,
        )

        assert len(results) == 0

    def test_own_agent_memory_retained_with_user_scope(self):
        """Own private memory from assistant_agent should be visible
        when querying with user_id but no sharing_policy filter."""
        candidates = [_own_agent_result()]
        requesting_agent = "assistant_agent"
        user_id = "alex_chen"
        sharing_policy = None  # no explicit policy filter

        results = _apply_sharing_filter(
            candidates,
            requesting_agent,
            user_id,
            sharing_policy,
            _extract_filter_metadata,
        )

        assert len(results) == 1
        assert results[0]["memory"] == "Previous conversation context"

    def test_mixed_results_correctly_filtered(self):
        """End-to-end: mix of promoted/nested, shared/private, own/other.

        Should retain:
        - Shared from profile_agent (promoted user_id) ✓
        - Shared from task_agent (nested user_id) ✓
        - Own private from assistant_agent ✗ (sharing_policy="shared"
          filter excludes private)

        Should drop:
        - Private from profile_agent ✗
        """
        candidates = [
            _promoted_shared_result(),
            _nested_shared_result(),
            _promoted_private_result(),
            _own_agent_result(),
        ]
        requesting_agent = "assistant_agent"
        user_id = "alex_chen"
        sharing_policy = "shared"

        results = _apply_sharing_filter(
            candidates,
            requesting_agent,
            user_id,
            sharing_policy,
            _extract_filter_metadata,
        )

        retained_ids = {r["id"] for r in results}
        # Shared memories from other agents should pass
        assert "mem_shared_1" in retained_ids
        assert "mem_shared_2" in retained_ids
        # Private from other agent must be dropped
        assert "mem_private_1" not in retained_ids
        # Own private with sharing_policy="shared" filter:
        # the memory's policy is "private" so it won't match
        assert "mem_own_1" not in retained_ids

    def test_no_user_id_anywhere_drops_cross_agent(self):
        """If user_id is missing from both top-level and metadata,
        cross-agent retrieval should not match."""
        candidate = {
            "id": "mem_no_uid",
            "memory": "Orphan memory",
            "metadata": {
                "owner_agent": "profile_agent",
                "sharing_policy": "shared",
            },
            "score": 0.70,
        }
        results = _apply_sharing_filter(
            [candidate],
            "assistant_agent",
            "alex_chen",
            "shared",
            _extract_filter_metadata,
        )

        # user_id="" != "alex_chen" → dropped
        assert len(results) == 0


# ──────────────────────────────────────────────────────────────────────
# Regression proof: naive extractor that does NOT merge promoted keys
# ──────────────────────────────────────────────────────────────────────

def _naive_metadata_extractor(item: dict) -> dict:
    """Simulates the broken behavior: only reads item["metadata"]
    without merging promoted top-level keys like user_id."""
    return dict(item.get("metadata") or {})


class TestRegressionWithoutFix:
    """Proves that WITHOUT _extract_filter_metadata, shared memories
    with promoted user_id are incorrectly dropped.

    These tests document the bug — they show the failure mode that
    _extract_filter_metadata was introduced to fix.
    """

    def test_promoted_user_id_DROPPED_without_fix(self):
        """Without the merge helper, a promoted user_id means
        mem_user == "" which != "alex_chen" → result dropped."""
        candidates = [_promoted_shared_result()]

        results = _apply_sharing_filter(
            candidates,
            "assistant_agent",
            "alex_chen",
            "shared",
            _naive_metadata_extractor,  # BUG: doesn't merge
        )

        # This demonstrates the bug: 0 results instead of 1
        assert len(results) == 0

    def test_nested_user_id_WORKS_without_fix(self):
        """When user_id is already inside metadata, the naive
        extractor works fine — no merge needed."""
        candidates = [_nested_shared_result()]

        results = _apply_sharing_filter(
            candidates,
            "assistant_agent",
            "alex_chen",
            "shared",
            _naive_metadata_extractor,
        )

        # Still works because user_id is in metadata
        assert len(results) == 1


# ──────────────────────────────────────────────────────────────────────
# Edge-case tests: privacy boundaries and robustness
# ──────────────────────────────────────────────────────────────────────

class TestExtractFilterMetadataEdgeCases:
    """Edge cases for _extract_filter_metadata robustness."""

    def test_metadata_is_none(self):
        """item["metadata"] is None — should not crash."""
        item = {
            "memory": "test",
            "user_id": "alex_chen",
            "metadata": None,
        }
        meta = _extract_filter_metadata(item)
        assert meta["user_id"] == "alex_chen"

    def test_metadata_key_missing(self):
        """No "metadata" key in item at all — should not crash."""
        item = {
            "memory": "test",
            "user_id": "alex_chen",
            "agent_id": "profile_agent",
        }
        meta = _extract_filter_metadata(item)
        assert meta["user_id"] == "alex_chen"
        assert meta["agent_id"] == "profile_agent"

    def test_empty_item(self):
        """Completely empty item — returns empty dict."""
        meta = _extract_filter_metadata({})
        assert meta == {}

    def test_empty_string_promoted_user_id(self):
        """Empty string user_id at top level is still copied."""
        item = {
            "memory": "test",
            "user_id": "",
            "metadata": {},
        }
        meta = _extract_filter_metadata(item)
        # Empty string IS a valid value — it gets copied
        assert meta["user_id"] == ""

    def test_only_promotes_user_id_and_agent_id(self):
        """run_id, actor_id, role are NOT promoted by the helper
        (only user_id and agent_id are needed for filtering)."""
        item = {
            "memory": "test",
            "run_id": "run_123",
            "actor_id": "actor_456",
            "role": "assistant",
            "metadata": {},
        }
        meta = _extract_filter_metadata(item)
        # These should NOT be merged
        assert "run_id" not in meta
        assert "actor_id" not in meta
        assert "role" not in meta


class TestPrivacyBoundaryEdgeCases:
    """Privacy edge cases that must never regress.

    Each test here validates a specific invariant of the
    sharing filter to ensure the promoted metadata fix does
    not widen the privacy boundary.
    """

    def test_shared_same_user_different_agent_kept(self):
        """shared + same user + different agent → KEPT"""
        candidate = {
            "memory": "Shared info",
            "user_id": "alex",
            "metadata": {
                "owner_agent": "profile_agent",
                "sharing_policy": "shared",
            },
        }
        results = _apply_sharing_filter(
            [candidate], "assistant_agent",
            "alex", "shared", _extract_filter_metadata,
        )
        assert len(results) == 1

    def test_private_same_user_different_agent_dropped(self):
        """private + same user + different agent → DROPPED"""
        candidate = {
            "memory": "Private info",
            "user_id": "alex",
            "metadata": {
                "owner_agent": "profile_agent",
                "sharing_policy": "private",
            },
        }
        results = _apply_sharing_filter(
            [candidate], "assistant_agent",
            "alex", "shared", _extract_filter_metadata,
        )
        assert len(results) == 0

    def test_shared_different_user_different_agent_dropped(self):
        """shared + different user + different agent → DROPPED"""
        candidate = {
            "memory": "Shared but wrong user",
            "user_id": "bob",
            "metadata": {
                "owner_agent": "profile_agent",
                "sharing_policy": "shared",
            },
        }
        results = _apply_sharing_filter(
            [candidate], "assistant_agent",
            "alex", "shared", _extract_filter_metadata,
        )
        assert len(results) == 0

    def test_own_agent_same_user_kept(self):
        """own-agent + same user (no policy filter) → KEPT"""
        candidate = {
            "memory": "My own memory",
            "user_id": "alex",
            "metadata": {
                "owner_agent": "assistant_agent",
                "sharing_policy": "private",
                "user_id": "alex",
            },
        }
        results = _apply_sharing_filter(
            [candidate], "assistant_agent",
            "alex", None, _extract_filter_metadata,
        )
        assert len(results) == 1

    def test_missing_sharing_policy_treated_as_private(self):
        """No sharing_policy in metadata → treated as private,
        so cross-agent is dropped."""
        candidate = {
            "memory": "No explicit policy",
            "user_id": "alex",
            "metadata": {
                "owner_agent": "profile_agent",
                # sharing_policy intentionally missing
            },
        }
        results = _apply_sharing_filter(
            [candidate], "assistant_agent",
            "alex", "shared", _extract_filter_metadata,
        )
        assert len(results) == 0

    def test_missing_owner_agent_never_matches(self):
        """No owner_agent in metadata → never matches as own,
        and privacy invariant blocks cross-agent unless shared."""
        candidate = {
            "memory": "Orphan memory",
            "user_id": "alex",
            "metadata": {
                "sharing_policy": "shared",
                # owner_agent intentionally missing
            },
        }
        # owner_agent="" != "assistant_agent" → not own
        # mem_policy == "shared" → passes privacy invariant
        # mem_user == "alex" → matches
        results = _apply_sharing_filter(
            [candidate], "assistant_agent",
            "alex", "shared", _extract_filter_metadata,
        )
        # Should pass because policy is shared and user matches
        assert len(results) == 1

    def test_empty_string_user_id_does_not_match_real_user(self):
        """Empty string user_id must not match a real user_id."""
        candidate = {
            "memory": "Memory with empty user",
            "user_id": "",
            "metadata": {
                "owner_agent": "profile_agent",
                "sharing_policy": "shared",
            },
        }
        results = _apply_sharing_filter(
            [candidate], "assistant_agent",
            "alex", "shared", _extract_filter_metadata,
        )
        # "" != "alex" → dropped
        assert len(results) == 0

    def test_none_metadata_does_not_crash_filter(self):
        """Item with None metadata is handled gracefully."""
        candidate = {
            "memory": "No metadata",
            "user_id": "alex",
            "metadata": None,
        }
        # Should not raise; will be dropped because
        # owner_agent="" and sharing_policy="" → "private"
        # → not own + not shared → dropped by privacy invariant
        results = _apply_sharing_filter(
            [candidate], "assistant_agent",
            "alex", "shared", _extract_filter_metadata,
        )
        assert len(results) == 0


# ──────────────────────────────────────────────────────────────────────
# CLI runner (for standalone execution without pytest)
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
