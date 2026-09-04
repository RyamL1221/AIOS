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


class MalformedConfigTest(unittest.TestCase):
    """Other malformed shapes raise clear errors, not silent defaults."""

    def test_non_numeric_default(self) -> None:
        with self.assertRaises(StaticThresholdConfigError):
            normalize_gate_config({"default": "high"})

    def test_overrides_not_a_list(self) -> None:
        with self.assertRaises(StaticThresholdConfigError):
            normalize_gate_config({"default": 0.7, "overrides": {}})

    def test_override_missing_keys(self) -> None:
        with self.assertRaises(StaticThresholdConfigError) as ctx:
            normalize_gate_config(
                {"default": 0.7,
                 "overrides": [{"llm_core": "qwen2.5:7b"}]}
            )
        # Both missing keys are reported.
        msg = str(ctx.exception)
        self.assertIn("task_type", msg)
        self.assertIn("value", msg)

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
