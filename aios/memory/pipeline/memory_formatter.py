"""
Memory content formatter for the AIOS personalization pipeline.

Converts JSON memory content into natural language sentences based
on the ``memory_type`` metadata field.  Operates as a pure function
at inject time — stored memory content is never modified.

Supported memory types:
  - ``"profile"``      → user profile sentence (hardcoded template)
  - ``"task_context"`` → task context sentence (hardcoded template)
  - ``"conversation"`` → returned as-is
  - any other type     → generic ``"{key}: {value}."`` formatting
  - missing type       → generic formatting if JSON, else as-is
"""
import json
import logging
from typing import Optional

# The module's old name, so the kernel's log lines keep their logger.
logger = logging.getLogger("aios.memory.memory_formatter")

# -- Profile formatting templates ----------------------------------

_PROFILE_TEMPLATES: dict[str, str] = {
    "name": "Their name is {value}.",
    "language": "They prefer coding in {value}.",
    "tools": "They like using {value}.",
    "style": "They prefer a {value} response style.",
}

_PROFILE_KEY_ORDER: list[str] = [
    "name",
    "language",
    "tools",
    "style",
]

# -- Task-context formatting templates -----------------------------

_TASK_TEMPLATES: dict[str, str] = {
    "project": "Working on project {value}.",
    "experiment": "Running experiment: {value}.",
    "goals": "Goals: {value}.",
    "blockers": "Blockers: {value}.",
    "next_steps": "Next steps: {value}.",
}

_TASK_KEY_ORDER: list[str] = [
    "project",
    "experiment",
    "goals",
    "blockers",
    "next_steps",
]


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _try_parse_json(content: str) -> Optional[dict]:
    """Attempt to parse *content* as a JSON object.

    Returns the parsed ``dict`` on success, or ``None`` when
    *content* is not valid JSON or is not a JSON object.
    """
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return data
        return None
    except (json.JSONDecodeError, TypeError):
        return None


def _value_to_str(value: object) -> str:
    """Convert a value to its string representation.

    Lists are joined with ``", "``.  All other types are
    converted via ``str()``.
    """
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _format_profile(data: dict) -> str:
    """Format a profile JSON dict into a natural language
    sentence prefixed with ``"User profile:"``."""
    parts: list[str] = ["User profile:"]

    for key in _PROFILE_KEY_ORDER:
        if key in data:
            value = _value_to_str(data[key])
            parts.append(
                _PROFILE_TEMPLATES[key].format(
                    value=value
                )
            )

    for key, value in data.items():
        if key not in _PROFILE_TEMPLATES:
            parts.append(
                f"{key}: {_value_to_str(value)}."
            )

    return " ".join(parts)


def _format_task_context(data: dict) -> str:
    """Format a task-context JSON dict into a natural language
    sentence prefixed with ``"Current task context:"``."""
    parts: list[str] = ["Current task context:"]

    for key in _TASK_KEY_ORDER:
        if key in data:
            value = _value_to_str(data[key])
            parts.append(
                _TASK_TEMPLATES[key].format(value=value)
            )

    for key, value in data.items():
        if key not in _TASK_TEMPLATES:
            parts.append(
                f"{key}: {_value_to_str(value)}."
            )

    return " ".join(parts)


def _format_generic(data: dict, memory_type: str) -> str:
    """Format an arbitrary JSON dict into a natural language
    sentence using the ``memory_type`` as a human-readable
    label.

    Converts underscores to spaces in the label and flattens
    all key-value pairs into ``"{key}: {value}."`` sentences.
    This ensures any agent-defined memory type gets readable
    formatting without requiring a dedicated template.
    """
    label = memory_type.replace("_", " ").capitalize()
    parts: list[str] = [f"{label}:"]

    for key, value in data.items():
        readable_key = key.replace("_", " ")
        parts.append(
            f"{readable_key}: {_value_to_str(value)}."
        )

    return " ".join(parts)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def format_memory(content: str, metadata: dict) -> str:
    """Convert memory content to natural language based on
    ``memory_type``.

    Args:
        content: Raw memory content string (may be JSON or
            plain text).
        metadata: Memory metadata dict containing
            ``memory_type``.

    Returns:
        A natural language string.  Falls back to the original
        *content* on any error or unrecognised memory type.
    """
    try:
        memory_type = metadata.get("memory_type", "")
        if not memory_type:
            # No type hint — try generic JSON formatting,
            # fall back to raw content if not JSON.
            data = _try_parse_json(content)
            if data is None:
                return content
            return _format_generic(data, "memory")

        if memory_type == "conversation":
            return content

        data = _try_parse_json(content)
        if data is None:
            return content

        if memory_type == "profile":
            return _format_profile(data)

        if memory_type == "task_context":
            return _format_task_context(data)

        # Unknown memory_type with valid JSON — use
        # generic formatting so any agent-defined type
        # gets readable output instead of raw JSON.
        return _format_generic(data, memory_type)
    except Exception:
        logger.warning(
            "Memory formatting failed, returning raw "
            "content",
            exc_info=True,
        )
        return content
