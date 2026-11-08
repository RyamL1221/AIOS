"""
The memory block: selected memories formatted as natural language,
fitted to the token budget, printed in type order.

Decision 1 (docs/REPLICATED_LOGIC.md): candidates arrive ranked by
score, and the budget drops the lowest-ranked first; the block is then
printed profile, task context, calendar, conversation, then any other
type, each in score order.

Block format (Subtask 9d): ``"compact"`` (the default) is one header
line and a bullet per memory, the shape of the native agents' block;
``"legacy"`` is the pre-9d kernel block (delimiters, an instruction
line and a timestamp per line), kept for the formatting ablation.
Timestamps stay in the memory's metadata either way. ``recency`` adds an
age per bullet, off by default. ``recency_unit`` says what the age
counts: ``"time"`` (the default) is the wall-clock age of the row's
timestamp ("(3 days ago)"); ``"session"`` (benchmark v2,
docs/BENCHMARK_V2.md) is the current session minus the row's
``metadata.session`` ("(2 sessions ago)").
"""
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .memory_formatter import format_memory

logger = logging.getLogger(__name__)

TYPE_ORDER = ("profile", "task_context", "calendar", "conversation")

BLOCK_FORMATS = ("compact", "legacy")
DEFAULT_BLOCK_FORMAT = "compact"

# What a recency age counts: wall-clock time since the row's timestamp,
# or sessions since the row's metadata.session (benchmark v2).
RECENCY_UNITS = ("time", "session")
DEFAULT_RECENCY_UNIT = "time"

COMPACT_HEADER = "Known about this user:"

# The legacy block (format "legacy").
BLOCK_HEADER = "===== MEMORY CONTEXT ====="
BLOCK_FOOTER = "===== END MEMORY CONTEXT ====="
LEGACY_INSTRUCTION = (
    "The following are relevant memories from prior "
    "interactions with this user. Use them to "
    "personalize your response:"
)
TIMESTAMP_FORMAT = "%Y%m%d%H%M"


def estimate_tokens(text: str) -> int:
    """Rough token estimate: words * 1.3."""
    return int(len(text.split()) * 1.3)


def memory_type_of(mem: dict) -> str:
    return (mem.get("metadata") or {}).get("memory_type", "")


def type_rank(mem: dict) -> int:
    memory_type = memory_type_of(mem)
    if memory_type in TYPE_ORDER:
        return TYPE_ORDER.index(memory_type)
    return len(TYPE_ORDER)


def _check_format(block_format: str, recency_unit: str) -> None:
    """Refuse a block format or recency unit the block cannot print."""
    if block_format not in BLOCK_FORMATS:
        raise ValueError(
            f"block_format must be one of {BLOCK_FORMATS}, "
            f"got {block_format!r}"
        )
    if recency_unit not in RECENCY_UNITS:
        raise ValueError(
            f"recency_unit must be one of {RECENCY_UNITS}, "
            f"got {recency_unit!r}"
        )


def relative_age(timestamp: Any, now: datetime) -> Optional[str]:
    """``"just now"``, ``"N minutes ago"``, ``"N hours ago"`` or ``"N
    days ago"`` for a ``YYYYMMDDHHMM`` timestamp; ``None`` if it does
    not parse."""
    try:
        then = datetime.strptime(str(timestamp), TIMESTAMP_FORMAT)
    except (TypeError, ValueError):
        return None
    minutes = int((now - then).total_seconds() // 60)
    if minutes < 1:
        return "just now"
    for size, unit in ((1440, "day"), (60, "hour"), (1, "minute")):
        if minutes >= size:
            count = minutes // size
            return f"{count} {unit}{'' if count == 1 else 's'} ago"
    return "just now"


def _is_session(value: Any) -> bool:
    """Whether ``value`` is a session index: an int, and not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def session_age(row_session: Any, current_session: Any) -> Optional[str]:
    """``"this session"``, ``"1 session ago"`` or ``"N sessions ago"``:
    the current session minus the row's. ``None`` (no age) when either
    is not an integer, or when the row's session is after the current
    one."""
    if not (_is_session(row_session) and _is_session(current_session)):
        return None
    sessions = current_session - row_session
    if sessions < 0:
        return None
    if sessions == 0:
        return "this session"
    return f"{sessions} session{'' if sessions == 1 else 's'} ago"


def _text(mem: dict) -> str:
    """A memory's text as the block prints it."""
    return str(mem.get("content", ""))


def _age(
    mem: dict,
    recency_unit: str,
    now: Optional[datetime],
    current_session: Optional[int],
) -> Optional[str]:
    """One memory's age in ``recency_unit``, or ``None`` for none."""
    if recency_unit == "session":
        return session_age(
            (mem.get("metadata") or {}).get("session"), current_session
        )
    return relative_age(mem.get("timestamp"), now or datetime.now())


def _with_age(
    line: str,
    mem: dict,
    recency: bool,
    recency_unit: str,
    now: Optional[datetime],
    current_session: Optional[int],
) -> str:
    """``line`` with `` (<age>)`` appended when recency is on and the
    memory has an age."""
    if recency:
        age = _age(mem, recency_unit, now, current_session)
        if age:
            line += f" ({age})"
    return line


def format_block(
    memories: list,
    block_format: str = DEFAULT_BLOCK_FORMAT,
    *,
    recency: bool = False,
    now: Optional[datetime] = None,
    recency_unit: str = DEFAULT_RECENCY_UNIT,
    current_session: Optional[int] = None,
) -> str:
    """Format memories into the block's system message text.

    With ``recency``, each line ends with its age: wall-clock from
    ``now`` (default: the time of the call) for ``recency_unit``
    ``"time"``, or sessions before ``current_session`` for
    ``"session"``.
    """
    _check_format(block_format, recency_unit)
    ages = (recency, recency_unit, now, current_session)
    if block_format == "compact":
        return "\n".join(
            [COMPACT_HEADER]
            + [_with_age(f"- {_text(mem)}", mem, *ages) for mem in memories]
        )
    lines = [BLOCK_HEADER, LEGACY_INSTRUCTION, ""]
    for mem in memories:
        ts = mem.get("timestamp", "unknown")
        lines.append(_with_age(f"- [{ts}] {_text(mem)}", mem, *ages))
    lines.append("")
    lines.append(BLOCK_FOOTER)
    return "\n".join(lines)


def is_memory_block(text: str) -> bool:
    """Whether a system message is a memory block, in either format."""
    return isinstance(text, str) and (
        text.startswith(COMPACT_HEADER + "\n")
        or text.startswith(BLOCK_HEADER + "\n")
    )


def block_contents(text: str) -> List[str]:
    """The memory lines of a block, without bullet, timestamp or age
    (the first line of a multi-line memory)."""
    if not is_memory_block(text):
        return []
    out = []
    for line in text.split("\n")[1:]:
        if not line.startswith("- "):
            continue
        body = line[2:]
        if text.startswith(BLOCK_HEADER) and body.startswith("["):
            body = body[body.index("]") + 2:] if "] " in body else body
        out.append(body)
    return out


# Metadata a writer may attach to say who wrote a memory for whom, and
# for which scripted event (benchmark v2); the pipeline copies it into
# the diagnostics and never reads it.
PROVENANCE_FIELDS = ("provenance_agent", "provenance_user", "provenance_event")


def injected_entry(mem: dict) -> Dict[str, Any]:
    """One injected memory in the diagnostics: id, owner, type, score,
    the stored ``user_id`` / ``sharing_policy`` and provenance the
    judge-free measures read (docs/HETEROGENEITY.md), and ``content``,
    its text as printed in the block without the age, with its
    ``fact_key`` and ``session`` (the v2 probes check which injected
    row carried a value)."""
    metadata = mem.get("metadata") or {}
    entry = {
        "memory_id": mem.get("memory_id"),
        "owner_agent": metadata.get("owner_agent", ""),
        "memory_type": memory_type_of(mem),
        "match_score": mem.get("score"),
        "user_id": metadata.get("user_id", ""),
        "sharing_policy": metadata.get("sharing_policy", ""),
    }
    for key in PROVENANCE_FIELDS:
        entry[key] = metadata.get(key)
    entry["content"] = _text(mem)
    # Which fact and session the row states (benchmark v2), so a probe
    # can tell the target's rows from the rest.
    entry["fact_key"] = metadata.get("fact_key")
    entry["session"] = metadata.get("session")
    return entry


class Formatter:
    """Builds the memory block for one pipeline.

    ``recency_unit`` and ``current_session`` choose the age printed
    when ``recency`` is on (``format_block``).
    """

    def __init__(
        self,
        max_tokens: int,
        block_format: str = DEFAULT_BLOCK_FORMAT,
        *,
        recency: bool = False,
        now: Optional[datetime] = None,
        recency_unit: str = DEFAULT_RECENCY_UNIT,
        current_session: Optional[int] = None,
    ):
        _check_format(block_format, recency_unit)
        self.max_tokens = max_tokens
        self.block_format = block_format
        self.recency = recency
        self.now = now
        self.recency_unit = recency_unit
        self.current_session = current_session

    def render(self, memories: list) -> str:
        """This formatter's block text for ``memories``, in order."""
        return format_block(
            memories, self.block_format, recency=self.recency, now=self.now,
            recency_unit=self.recency_unit,
            current_session=self.current_session,
        )

    def truncate_by_token_budget(self, memories: list) -> list:
        """Remove least-relevant memories until the formatted block
        fits within ``max_tokens``. Memories arrive sorted by score
        descending; the tail goes first."""
        while memories:
            block = self.render(memories)
            if estimate_tokens(block) <= self.max_tokens:
                return memories
            memories = memories[:-1]
        return memories

    def build(self, candidates: list) -> Tuple[str, Dict[str, Any]]:
        """The block for selected candidates, and its diagnostics:
        ``injected_count`` / ``after_budget`` (memories in the block),
        ``injected_memories`` (in block order), ``source_agents`` and
        ``memory_types`` (sorted), ``tokens_estimated``, the format and
        recency settings with the ``session`` the ages count from, and
        ``format_ms``. No candidates, or none within the budget, give an
        empty text."""
        started = time.perf_counter()
        formatted: List[dict] = []
        for mem in candidates:
            row = dict(mem)  # shallow copy
            try:
                row["content"] = format_memory(
                    mem.get("content", ""), mem.get("metadata", {}),
                )
            except Exception:
                logger.warning(
                    "Memory formatting failed, using raw content",
                    exc_info=True,
                )
            formatted.append(row)

        kept = self.truncate_by_token_budget(formatted)
        kept = sorted(kept, key=type_rank)  # stable: score order within
        text = self.render(kept) if kept else ""
        diagnostics: Dict[str, Any] = {
            "injected_count": len(kept),
            "after_budget": len(kept),
            "injected_memories": [injected_entry(mem) for mem in kept],
            "source_agents": sorted({
                (mem.get("metadata") or {}).get("owner_agent", "")
                for mem in kept
            } - {""}),
            "memory_types": sorted(
                {memory_type_of(mem) for mem in kept} - {""}
            ),
            "tokens_estimated": estimate_tokens(text) if text else 0,
            "block_format": self.block_format,
            "block_recency": self.recency,
            "block_recency_unit": self.recency_unit,
            # The caller's current session (benchmark v2), or None.
            "session": self.current_session,
            # The block as sent, for judge-free checks of what reached
            # the consumer (docs/HETEROGENEITY.md).
            "block_text": text,
            "format_ms": (time.perf_counter() - started) * 1000,
        }
        return text, diagnostics
