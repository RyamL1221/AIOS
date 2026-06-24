"""
Injection log parser for AIOS kernel stdout verification.

Parses ContextInjector INFO log lines from kernel stdout to
extract structured injection data, providing a deterministic
alternative verification path when Mem0Provider metadata-based
queries cannot confirm injection occurred.

The log format parsed is:
    Injected %d memories (%d own + %d shared)
    for agent=%s, user_id=%s
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class InjectionRecord:
    """Structured representation of a single injection event.

    Fields correspond 1-to-1 with the capture groups in the
    ContextInjector INFO log line format string.
    """

    injected_count: int
    own_count: int
    shared_count: int
    agent_name: str
    user_id: str


# Module-level compiled regex for the injection log line.
# Uses re.search (not re.match) so Python logging prefixes
# (timestamps, module names, log levels) are tolerated.
_INJECTION_PATTERN = re.compile(
    r"Injected (\d+) memories "
    r"\((\d+) own \+ (\d+) shared\) "
    r"for agent=(.+), user_id=(.+)"
)


def parse_injection_line(line: str) -> InjectionRecord | None:
    """Parse a single log line for injection data.

    Args:
        line: A single line of text (may include Python
            logging prefixes such as timestamps and module
            names).

    Returns:
        An InjectionRecord if the line matches the expected
        format, or None if it does not match.
    """
    match = _INJECTION_PATTERN.search(line)
    if match is None:
        return None
    return InjectionRecord(
        injected_count=int(match.group(1)),
        own_count=int(match.group(2)),
        shared_count=int(match.group(3)),
        agent_name=match.group(4),
        user_id=match.group(5),
    )


def parse_injection_lines(
    text: str,
) -> list[InjectionRecord]:
    """Parse multi-line text for all injection log entries.

    Splits *text* by newlines and applies
    ``parse_injection_line`` to each line, returning only
    non-None results.  Handles Python logging prefixes and
    interleaved non-injection output gracefully.

    Args:
        text: Multi-line kernel stdout or log capture.

    Returns:
        List of InjectionRecord instances extracted from
        all matching lines, in the order they appear.
    """
    records: list[InjectionRecord] = []
    for line in text.split("\n"):
        record = parse_injection_line(line)
        if record is not None:
            records.append(record)
    return records


def filter_by_agent(
    records: list[InjectionRecord],
    agent_name: str,
) -> list[InjectionRecord]:
    """Filter records to those matching *agent_name*.

    Args:
        records: List of InjectionRecord instances.
        agent_name: Agent name to filter by.

    Returns:
        Subset of *records* where ``record.agent_name``
        equals *agent_name*.
    """
    return [
        r for r in records if r.agent_name == agent_name
    ]


def filter_by_user_id(
    records: list[InjectionRecord],
    user_id: str,
) -> list[InjectionRecord]:
    """Filter records to those matching *user_id*.

    Args:
        records: List of InjectionRecord instances.
        user_id: User ID to filter by.

    Returns:
        Subset of *records* where ``record.user_id``
        equals *user_id*.
    """
    return [
        r for r in records if r.user_id == user_id
    ]


def verify_injection_occurred(
    records: list[InjectionRecord],
    agent_name: str | None = None,
    user_id: str | None = None,
) -> bool:
    """Check whether at least one injection record matches.

    Applies optional *agent_name* and *user_id* filters.
    Returns True if at least one record survives filtering.

    Args:
        records: List of InjectionRecord instances.
        agent_name: If provided, only consider records for
            this agent.
        user_id: If provided, only consider records for
            this user ID.

    Returns:
        True if at least one matching record exists.
    """
    filtered = records
    if agent_name is not None:
        filtered = filter_by_agent(filtered, agent_name)
    if user_id is not None:
        filtered = filter_by_user_id(filtered, user_id)
    return len(filtered) > 0
