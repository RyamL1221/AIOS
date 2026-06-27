"""
Property-based tests for the injection log parser module.

This test file validates:
- Property 1 (Bug Condition): Log Parser Extracts Injection Data
- Property 2 (Preservation): Existing Kernel Paths Unchanged

**Validates: Requirements 2.5**

The bug condition exploration test (Property 1) is expected to FAIL
on unfixed code because `aios.memory.injection_log_parser` does not
exist yet. This failure confirms the bug condition: injection log
lines exist in kernel stdout but cannot be programmatically
parsed/verified without the log parser module.
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st


# --- Strategies ---

# Non-negative integers for memory counts
count_strategy = st.integers(min_value=0, max_value=10000)

# Non-empty text for agent names (no newlines or commas to avoid
# ambiguity in the log line format)
agent_name_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        blacklist_characters="\n\r,",
    ),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip() == s and len(s.strip()) > 0)

# Non-empty text for user IDs (no newlines to avoid log line breaks)
user_id_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        blacklist_characters="\n\r",
    ),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip() == s and len(s.strip()) > 0)

# Strategy for generating non-matching text lines (random text that
# does NOT match the injection log pattern)
non_matching_line_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        blacklist_characters="\n\r",
    ),
    min_size=0,
    max_size=200,
).filter(lambda s: "Injected" not in s or "memories" not in s)


# =================================================================
# Property 1: Bug Condition — Log Parser Extracts Injection Data
# =================================================================
# **Validates: Requirements 2.5**
#
# These tests encode the EXPECTED behavior of the log parser module.
# On unfixed code, they will fail with ImportError because the module
# does not exist yet. This failure confirms the bug condition.
# =================================================================


class TestBugConditionLogParserExtractsInjectionData:
    """
    Property 1: Bug Condition — Log Parser Extracts Injection Data

    **Validates: Requirements 2.5**

    For any kernel stdout containing injection log lines matching
    the format "Injected %d memories (%d own + %d shared) for
    agent=%s, user_id=%s", the log parser module SHALL extract
    structured data for each matching line.
    """

    @given(
        injected_count=count_strategy,
        own_count=count_strategy,
        shared_count=count_strategy,
        agent_name=agent_name_strategy,
        user_id=user_id_strategy,
    )
    @settings(max_examples=100)
    def test_round_trip_parsing(
        self,
        injected_count,
        own_count,
        shared_count,
        agent_name,
        user_id,
    ):
        """
        Generate random InjectionRecord instances, format them to
        the log line pattern, parse back via parse_injection_line(),
        and assert round-trip equality.

        **Validates: Requirements 2.5**
        """
        from aios.memory.injection_log_parser import (
            InjectionRecord,
            parse_injection_line,
        )

        # Format as the ContextInjector log line
        log_line = (
            f"Injected {injected_count} memories "
            f"({own_count} own + {shared_count} shared) "
            f"for agent={agent_name}, user_id={user_id}"
        )

        # Parse back
        result = parse_injection_line(log_line)

        # Assert round-trip equality
        assert result is not None, (
            f"parse_injection_line returned None for: {log_line!r}"
        )
        assert result.injected_count == injected_count
        assert result.own_count == own_count
        assert result.shared_count == shared_count
        assert result.agent_name == agent_name
        assert result.user_id == user_id

    @given(line=non_matching_line_strategy)
    @settings(max_examples=100)
    def test_no_false_positives(self, line):
        """
        Generate random non-matching text lines and verify
        parse_injection_line() returns None (no false positives).

        **Validates: Requirements 2.5**
        """
        from aios.memory.injection_log_parser import (
            parse_injection_line,
        )

        result = parse_injection_line(line)
        assert result is None, (
            f"parse_injection_line returned a result for "
            f"non-matching line: {line!r}"
        )

    @given(
        valid_records=st.lists(
            st.tuples(
                count_strategy,
                count_strategy,
                count_strategy,
                agent_name_strategy,
                user_id_strategy,
            ),
            min_size=0,
            max_size=5,
        ),
        invalid_lines=st.lists(
            non_matching_line_strategy,
            min_size=0,
            max_size=5,
        ),
    )
    @settings(max_examples=50)
    def test_mixed_multiline_extraction(
        self, valid_records, invalid_lines
    ):
        """
        Generate mixed valid/invalid multi-line text and verify
        parse_injection_lines() extracts exactly the valid lines.

        **Validates: Requirements 2.5**
        """
        from aios.memory.injection_log_parser import (
            InjectionRecord,
            parse_injection_lines,
        )

        # Build valid log lines
        valid_lines = []
        for (
            injected_count,
            own_count,
            shared_count,
            agent_name,
            user_id,
        ) in valid_records:
            valid_lines.append(
                f"Injected {injected_count} memories "
                f"({own_count} own + {shared_count} shared) "
                f"for agent={agent_name}, user_id={user_id}"
            )

        # Interleave valid and invalid lines
        all_lines = []
        vi = 0
        ii = 0
        while vi < len(valid_lines) or ii < len(invalid_lines):
            if vi < len(valid_lines):
                all_lines.append(valid_lines[vi])
                vi += 1
            if ii < len(invalid_lines):
                all_lines.append(invalid_lines[ii])
                ii += 1

        text = "\n".join(all_lines)

        # Parse
        results = parse_injection_lines(text)

        # Should extract exactly the valid records
        assert len(results) == len(valid_records), (
            f"Expected {len(valid_records)} records, "
            f"got {len(results)}"
        )

        for i, (
            injected_count,
            own_count,
            shared_count,
            agent_name,
            user_id,
        ) in enumerate(valid_records):
            assert results[i].injected_count == injected_count
            assert results[i].own_count == own_count
            assert results[i].shared_count == shared_count
            assert results[i].agent_name == agent_name
            assert results[i].user_id == user_id


# =================================================================
# Property 2: Preservation — Existing Kernel Paths Unchanged
# =================================================================
# **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
#
# These tests verify that existing kernel modules (ContextInjector,
# MemoryWriteBarrier, MemoryManager) remain unchanged and that the
# log format string produced by ContextInjector is stable. They
# MUST PASS on unfixed code (baseline preservation).
# =================================================================

import re
import inspect
import pathlib


# The regex pattern the log parser will use to extract injection data
_INJECTION_LOG_REGEX = re.compile(
    r"Injected (\d+) memories "
    r"\((\d+) own \+ (\d+) shared\) "
    r"for agent=(.+), resolved_user_id=(.+)"
)


class TestPreservationExistingKernelPaths:
    """
    Property 2: Preservation — Existing Kernel Paths Unchanged

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

    Verifies that existing kernel memory modules import correctly,
    the injection log format string is stable, and
    MemoryWriteBarrier retains its full public API with correct
    signatures.
    """

    # --- Observation tests: imports work on unfixed code ---

    def test_context_injector_imports_without_error(self):
        """
        Observe: ContextInjector imports without error.

        **Validates: Requirements 3.1**
        """
        from aios.memory.context_injector import (
            ContextInjector,
        )
        assert ContextInjector is not None

    def test_memory_write_barrier_imports_without_error(self):
        """
        Observe: MemoryWriteBarrier imports without error.

        **Validates: Requirements 3.3**
        """
        from aios.memory.write_barrier import (
            MemoryWriteBarrier,
        )
        assert MemoryWriteBarrier is not None

    def test_memory_manager_imports_without_error(self):
        """
        Observe: MemoryManager imports without error.

        **Validates: Requirements 3.2**
        """
        from aios.memory.manager import MemoryManager
        assert MemoryManager is not None

    # --- Source-level log format check ---

    def test_log_format_string_exists_in_context_injector(
        self,
    ):
        """
        The log format string "Injected %d memories (%d own +
        %d shared) for agent=%s, resolved_user_id=%s" exists in
        context_injector.py source.

        **Validates: Requirements 3.1, 3.5**
        """
        source_path = (
            pathlib.Path(__file__).resolve().parents[3]
            / "aios"
            / "memory"
            / "context_injector.py"
        )
        source = source_path.read_text()
        # The format string is split across lines in the source,
        # but the key fragments must all be present.
        assert "Injected %d memories" in source
        assert "(%d own + %d shared)" in source
        assert "for agent=%s, resolved_user_id=%s" in source

    # --- Property-based test: log format matches regex ---

    @given(
        injected_count=count_strategy,
        own_count=count_strategy,
        shared_count=count_strategy,
        agent_name=agent_name_strategy,
        user_id=user_id_strategy,
    )
    @settings(max_examples=200)
    def test_log_format_matches_parser_regex(
        self,
        injected_count,
        own_count,
        shared_count,
        agent_name,
        user_id,
    ):
        """
        For all combinations of (injected_count, own_count,
        shared_count, agent_name, user_id), the ContextInjector
        INFO log format string produces output matching the
        expected regex pattern.

        **Validates: Requirements 3.1, 3.5**
        """
        # Reproduce the exact format string from ContextInjector
        log_line = (
            f"Injected {injected_count} memories "
            f"({own_count} own + {shared_count} shared) "
            f"for agent={agent_name}, resolved_user_id={user_id}"
        )

        # Verify it matches the parser regex
        match = _INJECTION_LOG_REGEX.match(log_line)
        assert match is not None, (
            f"Log line did not match regex: {log_line!r}"
        )

        # Verify extracted groups match input values
        assert int(match.group(1)) == injected_count
        assert int(match.group(2)) == own_count
        assert int(match.group(3)) == shared_count
        assert match.group(4) == agent_name
        assert match.group(5) == user_id

    # --- Preservation: MemoryWriteBarrier API ---

    def test_write_barrier_instantiation_with_default_config(
        self,
    ):
        """
        MemoryWriteBarrier can be instantiated with default config
        (empty dict) without error.

        **Validates: Requirements 3.3**
        """
        from aios.memory.write_barrier import (
            MemoryWriteBarrier,
        )
        barrier = MemoryWriteBarrier(config={})
        assert barrier is not None

    def test_write_barrier_acquire_method_exists(self):
        """
        MemoryWriteBarrier.acquire exists with correct signature:
        (self, user_id) -> int.

        **Validates: Requirements 3.3**
        """
        from aios.memory.write_barrier import (
            MemoryWriteBarrier,
        )
        assert hasattr(MemoryWriteBarrier, "acquire")
        sig = inspect.signature(MemoryWriteBarrier.acquire)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "user_id" in params

    def test_write_barrier_release_method_exists(self):
        """
        MemoryWriteBarrier.release exists with correct signature:
        (self, user_id, seq_no, success) -> None.

        **Validates: Requirements 3.3**
        """
        from aios.memory.write_barrier import (
            MemoryWriteBarrier,
        )
        assert hasattr(MemoryWriteBarrier, "release")
        sig = inspect.signature(MemoryWriteBarrier.release)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "user_id" in params
        assert "seq_no" in params
        assert "success" in params

    def test_write_barrier_snapshot_method_exists(self):
        """
        MemoryWriteBarrier.snapshot exists with correct signature:
        (self, user_id) -> int.

        **Validates: Requirements 3.3**
        """
        from aios.memory.write_barrier import (
            MemoryWriteBarrier,
        )
        assert hasattr(MemoryWriteBarrier, "snapshot")
        sig = inspect.signature(
            MemoryWriteBarrier.snapshot
        )
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "user_id" in params

    def test_write_barrier_wait_until_drained_method_exists(
        self,
    ):
        """
        MemoryWriteBarrier.wait_until_drained exists with correct
        signature: (self, user_id, barrier_seq, deadline=None).

        **Validates: Requirements 3.3**
        """
        from aios.memory.write_barrier import (
            MemoryWriteBarrier,
        )
        assert hasattr(
            MemoryWriteBarrier, "wait_until_drained"
        )
        sig = inspect.signature(
            MemoryWriteBarrier.wait_until_drained
        )
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "user_id" in params
        assert "barrier_seq" in params

    # --- Preservation: importing new module does NOT modify ---

    def test_importing_new_module_does_not_modify_classes(
        self,
    ):
        """
        Importing the new module (once it exists) does NOT modify
        any attribute of ContextInjector, MemoryWriteBarrier, or
        MemoryManager classes.

        On unfixed code (module doesn't exist yet), this test
        simply verifies that the classes have stable attributes
        before/after a failed import attempt.

        **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
        """
        from aios.memory.context_injector import (
            ContextInjector,
        )
        from aios.memory.write_barrier import (
            MemoryWriteBarrier,
        )
        from aios.memory.manager import MemoryManager

        # Snapshot attributes before
        ci_attrs_before = set(dir(ContextInjector))
        wb_attrs_before = set(dir(MemoryWriteBarrier))
        mm_attrs_before = set(dir(MemoryManager))

        # Attempt to import the new module (may not exist yet)
        try:
            import aios.memory.injection_log_parser  # noqa: F401
        except ImportError:
            pass  # Expected on unfixed code

        # Snapshot attributes after
        ci_attrs_after = set(dir(ContextInjector))
        wb_attrs_after = set(dir(MemoryWriteBarrier))
        mm_attrs_after = set(dir(MemoryManager))

        # Assert no attributes were added or removed
        assert ci_attrs_before == ci_attrs_after, (
            "ContextInjector attributes changed after "
            "importing injection_log_parser"
        )
        assert wb_attrs_before == wb_attrs_after, (
            "MemoryWriteBarrier attributes changed after "
            "importing injection_log_parser"
        )
        assert mm_attrs_before == mm_attrs_after, (
            "MemoryManager attributes changed after "
            "importing injection_log_parser"
        )
