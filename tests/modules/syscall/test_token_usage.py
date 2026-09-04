"""
Test graceful None/partial handling of Syscall token-usage metrics.

The token-usage plumbing (Subtasks 1-3) captures a LiteLLM ``usage``
object at the call site and lands it on the ``Syscall`` object via
``set_token_usage``. Because a future model/provider may not return
usage at all (or may return a partial/malformed object), the setter and
getter must behave predictably without raising.

This test exercises the real ``Syscall`` class (no kernel, no network)
and asserts:

1. ``set_token_usage(None)`` is a no-op and does not raise; the field
   stays ``None``.
2. ``set_token_usage`` with a partial usage-like object (one or more of
   prompt/completion/total attributes missing) does not raise and yields
   a sensibly-partial dict with ``None`` for the missing values (no
   coercion to 0).
3. ``get_token_usage()`` on a fresh Syscall where the setter was never
   called returns ``None`` cleanly.
4. A well-formed usage object populates all three fields.

Run standalone:

    python tests/modules/syscall/test_token_usage.py
"""
from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from aios.syscall import Syscall


class _FakeQuery:
    """Minimal stand-in for a Query; Syscall only stores it."""
    pass


class _FullUsage:
    """A well-formed LiteLLM-like usage object."""
    prompt_tokens = 12
    completion_tokens = 8
    total_tokens = 20


class _PartialUsage:
    """A malformed/partial usage object missing two of three attrs."""
    completion_tokens = 12
    # prompt_tokens and total_tokens intentionally absent


def _make_syscall() -> Syscall:
    return Syscall("agent_under_test", _FakeQuery())


class TokenUsageHandlingTest(unittest.TestCase):

    def test_fresh_syscall_returns_none(self):
        """(c) Getter is clean None when the setter was never called."""
        sc = _make_syscall()
        self.assertIsNone(sc.get_token_usage())
        self.assertIsNone(sc.token_usage)

    def test_set_none_is_noop(self):
        """(a) set_token_usage(None) does not raise, field stays None."""
        sc = _make_syscall()
        sc.set_token_usage(None)  # must not raise
        self.assertIsNone(sc.get_token_usage())

    def test_set_none_does_not_clobber_existing(self):
        """A later None call is a no-op and leaves prior data intact."""
        sc = _make_syscall()
        sc.set_token_usage(_FullUsage())
        sc.set_token_usage(None)  # no-op, must not wipe the field
        usage = sc.get_token_usage()
        self.assertIsNotNone(usage)
        self.assertEqual(usage["total_tokens"], 20)

    def test_partial_object_yields_partial_dict(self):
        """(b) Partial object -> partial dict, missing values are None."""
        sc = _make_syscall()
        sc.set_token_usage(_PartialUsage())  # must not raise
        usage = sc.get_token_usage()
        self.assertEqual(
            usage,
            {
                "prompt_tokens": None,
                "completion_tokens": 12,
                "total_tokens": None,
            },
        )
        # Missing values must be None, not coerced to 0.
        self.assertIsNone(usage["prompt_tokens"])
        self.assertIsNone(usage["total_tokens"])

    def test_full_object_populates_all_fields(self):
        """A well-formed usage object populates all three fields."""
        sc = _make_syscall()
        sc.set_token_usage(_FullUsage())
        self.assertEqual(
            sc.get_token_usage(),
            {
                "prompt_tokens": 12,
                "completion_tokens": 8,
                "total_tokens": 20,
            },
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
