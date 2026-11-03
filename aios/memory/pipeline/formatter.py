"""
The memory block: selected memories formatted as natural language,
fitted to the token budget, printed in type order.

Decision 1 (docs/REPLICATED_LOGIC.md): candidates arrive ranked by
score, and the budget drops the lowest-ranked first; the block is then
printed profile, task context, conversation, then any other type, each
in score order.
"""
import logging
import time
from typing import Any, Dict, List, Tuple

from .memory_formatter import format_memory

logger = logging.getLogger(__name__)

TYPE_ORDER = ("profile", "task_context", "conversation")

BLOCK_HEADER = "===== MEMORY CONTEXT ====="
BLOCK_FOOTER = "===== END MEMORY CONTEXT ====="


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


def format_block(memories: list) -> str:
    """Format memories into a delimited system message string."""
    lines = [
        BLOCK_HEADER,
        "The following are relevant memories from prior "
        "interactions with this user. Use them to "
        "personalize your response:",
        "",
    ]
    for mem in memories:
        ts = mem.get("timestamp", "unknown")
        content = mem.get("content", "")
        lines.append(f"- [{ts}] {content}")

    lines.append("")
    lines.append(BLOCK_FOOTER)
    return "\n".join(lines)


class Formatter:
    """Builds the memory block for one pipeline."""

    def __init__(self, max_tokens: int):
        self.max_tokens = max_tokens

    def truncate_by_token_budget(self, memories: list) -> list:
        """Remove least-relevant memories until the formatted block
        fits within ``max_tokens``. Memories arrive sorted by score
        descending; the tail goes first."""
        while memories:
            block = format_block(memories)
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
        text = format_block(kept) if kept else ""
        diagnostics: Dict[str, Any] = {
            "injected_count": len(kept),
            "after_budget": len(kept),
            "injected_memories": [
                {
                    "memory_id": mem.get("memory_id"),
                    "owner_agent": (mem.get("metadata") or {}).get(
                        "owner_agent", ""
                    ),
                    "memory_type": memory_type_of(mem),
                    "match_score": mem.get("score"),
                }
                for mem in kept
            ],
            "source_agents": sorted({
                (mem.get("metadata") or {}).get("owner_agent", "")
                for mem in kept
            } - {""}),
            "memory_types": sorted(
                {memory_type_of(mem) for mem in kept} - {""}
            ),
            "tokens_estimated": estimate_tokens(text) if text else 0,
            "format_ms": (time.perf_counter() - started) * 1000,
        }
        return text, diagnostics
