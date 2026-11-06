"""
The memory block: selected memories formatted as natural language,
fitted to the token budget, printed in type order.

Decision 1 (docs/REPLICATED_LOGIC.md): candidates arrive ranked by
score, and the budget drops the lowest-ranked first; the block is then
printed profile, task context, conversation, then any other type, each
in score order.

Block format (Subtask 9d): ``"compact"`` (the default) is one header
line and a bullet per memory, the shape of the native agents' block;
``"legacy"`` is the pre-9d kernel block (delimiters, an instruction
line and a timestamp per line), kept for the formatting ablation.
Timestamps stay in the memory's metadata either way. ``recency`` adds a
relative age per bullet ("(3 days ago)"), off by default.
"""
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .memory_formatter import format_memory

logger = logging.getLogger(__name__)

TYPE_ORDER = ("profile", "task_context", "conversation")

BLOCK_FORMATS = ("compact", "legacy")
DEFAULT_BLOCK_FORMAT = "compact"

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


def _bullet(mem: dict, recency: bool, now: Optional[datetime]) -> str:
    line = f"- {mem.get('content', '')}"
    if recency:
        age = relative_age(mem.get("timestamp"), now or datetime.now())
        if age:
            line += f" ({age})"
    return line


def format_block(
    memories: list,
    block_format: str = DEFAULT_BLOCK_FORMAT,
    *,
    recency: bool = False,
    now: Optional[datetime] = None,
) -> str:
    """Format memories into the block's system message text."""
    if block_format not in BLOCK_FORMATS:
        raise ValueError(
            f"block_format must be one of {BLOCK_FORMATS}, "
            f"got {block_format!r}"
        )
    if block_format == "compact":
        return "\n".join(
            [COMPACT_HEADER]
            + [_bullet(mem, recency, now) for mem in memories]
        )
    lines = [BLOCK_HEADER, LEGACY_INSTRUCTION, ""]
    for mem in memories:
        ts = mem.get("timestamp", "unknown")
        line = f"- [{ts}] {mem.get('content', '')}"
        if recency:
            age = relative_age(ts, now or datetime.now())
            if age:
                line += f" ({age})"
        lines.append(line)
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


# Metadata a writer may attach to say who wrote a memory for whom; the
# pipeline copies it into the diagnostics and never reads it.
PROVENANCE_FIELDS = ("provenance_agent", "provenance_user")


def injected_entry(mem: dict) -> Dict[str, Any]:
    """One injected memory in the diagnostics: id, owner, type, score,
    and the stored ``user_id`` / ``sharing_policy`` and provenance the
    judge-free measures read (docs/HETEROGENEITY.md)."""
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
    return entry


class Formatter:
    """Builds the memory block for one pipeline."""

    def __init__(
        self,
        max_tokens: int,
        block_format: str = DEFAULT_BLOCK_FORMAT,
        *,
        recency: bool = False,
        now: Optional[datetime] = None,
    ):
        if block_format not in BLOCK_FORMATS:
            raise ValueError(
                f"block_format must be one of {BLOCK_FORMATS}, "
                f"got {block_format!r}"
            )
        self.max_tokens = max_tokens
        self.block_format = block_format
        self.recency = recency
        self.now = now

    def render(self, memories: list) -> str:
        """This formatter's block text for ``memories``, in order."""
        return format_block(
            memories, self.block_format, recency=self.recency, now=self.now,
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
        ``memory_types`` (sorted), ``tokens_estimated`` and
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
            # The block as sent, for judge-free checks of what reached
            # the consumer (docs/HETEROGENEITY.md).
            "block_text": text,
            "format_ms": (time.perf_counter() - started) * 1000,
        }
        return text, diagnostics
