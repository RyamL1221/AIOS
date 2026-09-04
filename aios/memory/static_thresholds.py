"""
Static (fixed) threshold lookup for AIOS memory gating.

This module is the non-learning counterpart to ``policy.py``'s LinUCB
bandits. Given a ``memory.static_thresholds.<gate>`` config block and a
``(llm_core, task_type)`` context, it resolves the fixed threshold to
use for that gate — an exact-match override if one is configured,
otherwise the mandatory ``default``.

Two config forms are accepted (see ``config.yaml`` /
``memory-providers.md``):

* **Scalar shorthand** — a bare float, e.g. ``novelty_threshold: 0.7``.
  Normalizes to ``{"default": 0.7, "overrides": {}}``.
* **Table form** — a mandatory ``default`` plus an ``overrides`` list of
  ``{llm_core, task_type, value}`` entries, e.g.::

      novelty_threshold:
        default: 0.7
        overrides:
          - {llm_core: "qwen2.5:7b", task_type: "profile", value: 0.8}

  Normalizes to ``{"default": 0.7, "overrides": {("qwen2.5:7b",
  "profile"): 0.8}}``.

The lookup is **pure and stateless** — it reads no ``MemoryManager`` or
``_latest_llm_core`` state — so one function serves all three gates and
is independently testable.
"""
from __future__ import annotations

from numbers import Real
from typing import Any, Dict, Optional, Tuple


class StaticThresholdConfigError(ValueError):
    """Raised when a ``static_thresholds.<gate>`` block is malformed.

    The most common cause is a table-form block missing the mandatory
    ``default`` key. Raised rather than silently substituting an
    arbitrary fallback, so a misconfiguration fails loudly at
    normalization time instead of skewing gating decisions.
    """


# Internal normalized shape:
#   {"default": float, "overrides": Dict[(llm_core, task_type), float]}
NormalizedThresholds = Dict[str, Any]


def _coerce_float(value: Any, context: str) -> float:
    """Coerce *value* to ``float`` or raise a config error.

    ``bool`` is rejected explicitly: in Python ``bool`` is a subclass of
    ``int``, so ``True``/``False`` would otherwise pass as ``1.0``/``0.0``
    and mask a config typo.

    Args:
        value: The raw config value.
        context: Human-readable location for the error message.

    Returns:
        The value as a ``float``.

    Raises:
        StaticThresholdConfigError: If *value* is not a real number.
    """
    if isinstance(value, bool) or not isinstance(value, Real):
        raise StaticThresholdConfigError(
            f"{context}: expected a number, got "
            f"{type(value).__name__} ({value!r})"
        )
    return float(value)


def normalize_gate_config(gate_config: Any) -> NormalizedThresholds:
    """Normalize either config form into one internal shape.

    Args:
        gate_config: Either a bare scalar (scalar shorthand) or a dict
            with a mandatory ``default`` and optional ``overrides`` list
            (table form).

    Returns:
        ``{"default": float, "overrides": {(llm_core, task_type):
        float}}``.

    Raises:
        StaticThresholdConfigError: If the table form is missing
            ``default``, or any value is non-numeric, or an override
            entry is malformed.
    """
    # --- Scalar shorthand: a bare number ---
    if isinstance(gate_config, bool) or isinstance(gate_config, Real):
        return {
            "default": _coerce_float(gate_config, "static threshold"),
            "overrides": {},
        }

    # --- Table form: a dict with default (+ optional overrides) ---
    if not isinstance(gate_config, dict):
        raise StaticThresholdConfigError(
            "static threshold config must be a number (scalar form) "
            "or a mapping with a 'default' (table form); got "
            f"{type(gate_config).__name__}"
        )

    if "default" not in gate_config:
        raise StaticThresholdConfigError(
            "static threshold table form is missing the mandatory "
            "'default' key"
        )

    default = _coerce_float(gate_config["default"], "default")

    # Keys are (llm_core, task_type); task_type is None for a
    # wildcard-on-llm_core override entry.
    overrides: Dict[Tuple[str, Optional[str]], float] = {}
    # Only an absent key or an explicit None means "no overrides". A
    # present-but-wrong-type value (e.g. a dict) must error rather than
    # be silently coerced to an empty list — otherwise an empty dict
    # ``{}`` (falsy) would sneak past the type check below.
    raw_overrides = gate_config.get("overrides")
    if raw_overrides is None:
        raw_overrides = []
    if not isinstance(raw_overrides, (list, tuple)):
        raise StaticThresholdConfigError(
            "'overrides' must be a list of "
            "{llm_core, task_type, value} entries; got "
            f"{type(raw_overrides).__name__}"
        )

    for i, entry in enumerate(raw_overrides):
        if not isinstance(entry, dict):
            raise StaticThresholdConfigError(
                f"overrides[{i}] must be a mapping with keys "
                "llm_core, value (task_type optional)"
            )
        # llm_core and value stay mandatory; task_type is optional. A
        # missing key or an explicit None both mean "wildcard on
        # llm_core alone" and normalize to task_type = None internally.
        missing = [
            k for k in ("llm_core", "value")
            if k not in entry
        ]
        if missing:
            raise StaticThresholdConfigError(
                f"overrides[{i}] is missing key(s): "
                f"{', '.join(missing)}"
            )
        llm_core = entry["llm_core"]
        if not isinstance(llm_core, str) or not llm_core:
            raise StaticThresholdConfigError(
                f"overrides[{i}].llm_core must be a non-empty string"
            )
        # task_type: None denotes a wildcard-on-llm_core entry.
        raw_task_type = entry.get("task_type")
        task_type = None if raw_task_type is None else str(raw_task_type)
        key = (llm_core, task_type)
        overrides[key] = _coerce_float(
            entry["value"], f"overrides[{i}].value"
        )

    return {"default": default, "overrides": overrides}


def resolve_threshold(
    gate_config: Any,
    llm_core: str,
    task_type: str,
) -> float:
    """Resolve the fixed threshold for a gate under a context.

    Pure and stateless: normalizes *gate_config*, then does an
    exact-match lookup on ``(llm_core, task_type)``, falling back to
    ``default`` on a miss.

    Args:
        gate_config: A ``static_thresholds.<gate>`` block in either the
            scalar-shorthand or default+overrides table form.
        llm_core: The agent's LLM model string (e.g. ``"qwen2.5:7b"``);
            ``"unknown"`` when not synced.
        task_type: The task/memory type (e.g. ``"profile"``); ``""``
            when absent.

    Returns:
        The resolved threshold as a ``float``.

    Raises:
        StaticThresholdConfigError: If *gate_config* is malformed (see
            ``normalize_gate_config``).
    """
    normalized = normalize_gate_config(gate_config)
    return normalized["overrides"].get(
        (str(llm_core), str(task_type)),
        normalized["default"],
    )
