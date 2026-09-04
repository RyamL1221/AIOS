"""
Unit tests for the pure static-threshold lookup (resolve_threshold).

Proves the lookup in isolation (no MemoryManager, config, or
scheduler): scalar shorthand, table form with a matching override,
table form with no matching override (falls to default), and the
missing-default error case.

Run standalone:

    python tests/modules/memory/test_static_thresholds.py
"""
from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from aios.memory.static_thresholds import (
    StaticThresholdConfigError,
    normalize_gate_config,
    resolve_threshold,
)


class ScalarFormTest(unittest.TestCase):
    """Bare scalar shorthand resolves to itself for any context."""

    def test_scalar_int(self) -> None:
        self.assertEqual(resolve_threshold(1, "qwen2.5:7b", "profile"), 1.0)

    def test_scalar_float_any_context(self) -> None:
        # Context is irrelevant for a bare scalar — always the scalar.
        self.assertEqual(
            resolve_threshold(0.7, "qwen2.5:7b", "profile"), 0.7
        )
        self.assertEqual(
            resolve_threshold(0.7, "unknown", ""), 0.7
        )

    def test_scalar_normalizes_to_empty_overrides(self) -> None:
        norm = normalize_gate_config(0.42)
        self.assertEqual(norm["default"], 0.42)
        self.assertEqual(norm["overrides"], {})

    def test_bool_rejected(self) -> None:
        # bool is an int subclass; must not slip through as 1.0/0.0.
        with self.assertRaises(StaticThresholdConfigError):
            resolve_threshold(True, "qwen2.5:7b", "profile")


class TableFormMatchingOverrideTest(unittest.TestCase):
    """An exact (llm_core, task_type) match returns the override."""

    def setUp(self) -> None:
        self.cfg = {
            "default": 0.7,
            "overrides": [
                {"llm_core": "qwen2.5:7b", "task_type": "profile",
                 "value": 0.8},
                {"llm_core": "llama3.1:8b", "task_type": "task",
                 "value": 0.55},
            ],
        }

    def test_matching_override_returned(self) -> None:
        self.assertEqual(
            resolve_threshold(self.cfg, "qwen2.5:7b", "profile"), 0.8
        )
        self.assertEqual(
            resolve_threshold(self.cfg, "llama3.1:8b", "task"), 0.55
        )

    def test_partial_match_does_not_count(self) -> None:
        # Same llm_core but different task_type => no match => default.
        self.assertEqual(
            resolve_threshold(self.cfg, "qwen2.5:7b", "task"), 0.7
        )
        # Same task_type but different llm_core => no match => default.
        self.assertEqual(
            resolve_threshold(self.cfg, "gpt-4o", "profile"), 0.7
        )


class TableFormNoMatchTest(unittest.TestCase):
    """No matching override falls back to default."""

    def test_no_match_falls_to_default(self) -> None:
        cfg = {
            "default": 0.65,
            "overrides": [
                {"llm_core": "qwen2.5:7b", "task_type": "profile",
                 "value": 0.9},
            ],
        }
        self.assertEqual(
            resolve_threshold(cfg, "some-other-model", "conversation"),
            0.65,
        )

    def test_empty_overrides_is_scalar_equivalent(self) -> None:
        cfg = {"default": 0.5, "overrides": []}
        self.assertEqual(resolve_threshold(cfg, "x", "y"), 0.5)

    def test_absent_overrides_key_ok(self) -> None:
        cfg = {"default": 0.5}
        self.assertEqual(resolve_threshold(cfg, "x", "y"), 0.5)


class MissingDefaultErrorTest(unittest.TestCase):
    """Table form without a default raises a clear config error."""

    def test_missing_default_raises(self) -> None:
        cfg = {
            "overrides": [
                {"llm_core": "qwen2.5:7b", "task_type": "profile",
                 "value": 0.8},
            ]
        }
        with self.assertRaises(StaticThresholdConfigError) as ctx:
            resolve_threshold(cfg, "qwen2.5:7b", "profile")
        self.assertIn("default", str(ctx.exception))

    def test_missing_default_raises_via_normalize(self) -> None:
        with self.assertRaises(StaticThresholdConfigError):
            normalize_gate_config({"overrides": []})


class TaskTypeOptionalOverrideTest(unittest.TestCase):
    """task_type may be omitted/null -> wildcard-on-llm_core entry."""

    def test_absent_task_type_normalizes_to_none(self) -> None:
        norm = normalize_gate_config(
            {"default": 0.5,
             "overrides": [{"llm_core": "m", "value": 0.8}]}
        )
        self.assertEqual(norm["overrides"], {("m", None): 0.8})

    def test_explicit_null_task_type_same_as_absent(self) -> None:
        norm = normalize_gate_config(
            {"default": 0.5,
             "overrides": [{"llm_core": "m", "task_type": None,
                            "value": 0.8}]}
        )
        self.assertEqual(norm["overrides"], {("m", None): 0.8})

    def test_full_entry_unchanged(self) -> None:
        norm = normalize_gate_config(
            {"default": 0.5,
             "overrides": [{"llm_core": "m", "task_type": "t",
                            "value": 0.8}]}
        )
        self.assertEqual(norm["overrides"], {("m", "t"): 0.8})


class WildcardPrecedenceTest(unittest.TestCase):
    """resolve_threshold honors exact > wildcard > default."""

    def test_wildcard_only_matches_any_task_type(self) -> None:
        cfg = {"default": 0.5,
               "overrides": [{"llm_core": "m", "value": 0.9}]}
        self.assertEqual(resolve_threshold(cfg, "m", "profile"), 0.9)
        self.assertEqual(resolve_threshold(cfg, "m", "task"), 0.9)

    def test_wildcard_does_not_leak_to_other_llm_core(self) -> None:
        cfg = {"default": 0.5,
               "overrides": [{"llm_core": "m", "value": 0.9}]}
        self.assertEqual(resolve_threshold(cfg, "other", "profile"), 0.5)

    def test_exact_wins_over_wildcard(self) -> None:
        cfg = {
            "default": 0.5,
            "overrides": [
                {"llm_core": "m", "value": 0.9},
                {"llm_core": "m", "task_type": "profile", "value": 0.8},
            ],
        }
        self.assertEqual(resolve_threshold(cfg, "m", "profile"), 0.8)
        # Any other task_type for m falls to the wildcard.
        self.assertEqual(resolve_threshold(cfg, "m", "task"), 0.9)

    def test_no_match_falls_to_default(self) -> None:
        cfg = {
            "default": 0.6,
            "overrides": [
                {"llm_core": "m", "task_type": "p", "value": 0.8},
            ],
        }
        self.assertEqual(resolve_threshold(cfg, "x", "y"), 0.6)

    def test_empty_task_type_does_not_collide_with_wildcard(self) -> None:
        # A sentinel ("unknown", "") call still routes through the
        # wildcard step; "" never string-collides with the None key.
        cfg = {"default": 0.6,
               "overrides": [{"llm_core": "unknown", "value": 0.7}]}
        self.assertEqual(resolve_threshold(cfg, "unknown", ""), 0.7)


class UnknownSentinelNoSpecialCasingTest(unittest.TestCase):
    """The ("unknown", "") sentinel is treated as an ordinary string
    pair — the resolver has no hidden special-casing for it.

    Callers (``MemoryManager._note_task_type`` /
    ``_retrieval_context`` / ``_latest_llm_core``) pass ``llm_core =
    "unknown"`` (its init default before any ``sync_llm_from_query``)
    and ``task_type = ""`` (empty ``memory_type``). These tests pin
    that a real-model wildcard never leaks onto that sentinel, and a
    wildcard registered *under* ``"unknown"`` matches it purely by
    string equality.
    """

    def test_real_model_wildcard_does_not_match_unknown_sentinel(
        self,
    ) -> None:
        # Wildcard registered for a real model; a ("unknown", "")
        # call must NOT borrow it — it falls through to default.
        cfg = {
            "default": 0.5,
            "overrides": [{"llm_core": "gpt-4o", "value": 0.9}],
        }
        self.assertEqual(resolve_threshold(cfg, "unknown", ""), 0.5)

    def test_wildcard_under_unknown_matches_unknown_sentinel(
        self,
    ) -> None:
        # "unknown" is an ordinary llm_core string: a wildcard
        # registered under it matches the sentinel call by pure
        # string equality (no special-casing either way).
        cfg = {
            "default": 0.5,
            "overrides": [{"llm_core": "unknown", "value": 0.42}],
        }
        self.assertEqual(resolve_threshold(cfg, "unknown", ""), 0.42)
        # And it does not leak onto a real model.
        self.assertEqual(resolve_threshold(cfg, "gpt-4o", ""), 0.5)

    def test_exact_unknown_entry_still_wins_over_unknown_wildcard(
        self,
    ) -> None:
        # Precedence holds even for the sentinel llm_core: an exact
        # ("unknown", "") entry beats an ("unknown", None) wildcard.
        cfg = {
            "default": 0.5,
            "overrides": [
                {"llm_core": "unknown", "value": 0.9},
                {"llm_core": "unknown", "task_type": "", "value": 0.3},
            ],
        }
        self.assertEqual(resolve_threshold(cfg, "unknown", ""), 0.3)


class MalformedConfigTest(unittest.TestCase):
    """Other malformed shapes raise clear errors, not silent defaults."""

    def test_non_numeric_default(self) -> None:
        with self.assertRaises(StaticThresholdConfigError):
            normalize_gate_config({"default": "high"})

    def test_overrides_not_a_list(self) -> None:
        with self.assertRaises(StaticThresholdConfigError):
            normalize_gate_config({"default": 0.7, "overrides": {}})

    def test_override_missing_value(self) -> None:
        # value stays mandatory; task_type is now optional so an entry
        # with only llm_core still fails, but only on the missing value.
        with self.assertRaises(StaticThresholdConfigError) as ctx:
            normalize_gate_config(
                {"default": 0.7,
                 "overrides": [{"llm_core": "qwen2.5:7b"}]}
            )
        msg = str(ctx.exception)
        self.assertIn("value", msg)

    def test_override_missing_llm_core(self) -> None:
        with self.assertRaises(StaticThresholdConfigError) as ctx:
            normalize_gate_config(
                {"default": 0.7,
                 "overrides": [{"task_type": "profile", "value": 0.8}]}
            )
        self.assertIn("llm_core", str(ctx.exception))

    def test_override_empty_llm_core(self) -> None:
        with self.assertRaises(StaticThresholdConfigError):
            normalize_gate_config(
                {"default": 0.7,
                 "overrides": [{"llm_core": "", "value": 0.8}]}
            )

    def test_override_non_numeric_value(self) -> None:
        with self.assertRaises(StaticThresholdConfigError):
            normalize_gate_config(
                {"default": 0.7,
                 "overrides": [
                     {"llm_core": "q", "task_type": "p",
                      "value": "nope"}
                 ]}
            )

    def test_unsupported_top_level_type(self) -> None:
        with self.assertRaises(StaticThresholdConfigError):
            normalize_gate_config(["not", "a", "valid", "block"])


class PurityTest(unittest.TestCase):
    """The lookup is pure: same inputs => same output, no mutation."""

    def test_input_not_mutated(self) -> None:
        cfg = {
            "default": 0.7,
            "overrides": [
                {"llm_core": "q", "task_type": "p", "value": 0.8},
            ],
        }
        import copy

        snapshot = copy.deepcopy(cfg)
        resolve_threshold(cfg, "q", "p")
        resolve_threshold(cfg, "other", "other")
        self.assertEqual(cfg, snapshot)


if __name__ == "__main__":
    unittest.main(verbosity=2)
