"""
The memory pipeline's settings: the selection and budget parts of the
``memory:`` config block.

The kernel reports them at ``/memory/config`` (``pipeline``), and a
replicated agent builds its own copy from that report, so in the clean
condition every copy matches the kernel's settings by construction.
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class PipelineSettings:
    """``relevance_threshold`` drops scored candidates below it (0.0
    ranks without dropping); ``max_injected_memories`` is the count cap
    and the own fetch size; ``max_memory_tokens`` is the block's token
    budget; ``write_barrier`` is ``memory.write_barrier``;
    ``block_format`` (``memory.block_format``) is ``"compact"`` or
    ``"legacy"`` and ``block_recency`` (``memory.block_recency``) adds a
    relative age per bullet (Subtask 9d). ``block_recency_unit``
    (``memory.block_recency_unit``) is what that age counts: ``"time"``,
    the wall-clock age (the default), or ``"session"``, the sessions
    since the row's ``metadata.session`` (benchmark v2)."""

    relevance_threshold: float = 0.0
    max_injected_memories: int = 5
    max_memory_tokens: int = 1500
    write_barrier: Dict[str, Any] = field(default_factory=dict)
    block_format: str = "compact"
    block_recency: bool = False
    block_recency_unit: str = "time"

    def __post_init__(self):
        if self.block_format not in ("compact", "legacy"):
            raise ValueError(
                "memory.block_format must be 'compact' or 'legacy', "
                f"got {self.block_format!r}"
            )
        if self.block_recency_unit not in ("time", "session"):
            raise ValueError(
                "memory.block_recency_unit must be 'time' or 'session', "
                f"got {self.block_recency_unit!r}"
            )

    @classmethod
    def from_memory_config(
        cls, memory_config: Dict[str, Any]
    ) -> "PipelineSettings":
        """Read the settings from the ``memory:`` block, or from a
        ``/memory/config`` ``pipeline`` report (the same keys)."""
        defaults = cls()
        return cls(
            relevance_threshold=memory_config.get(
                "relevance_threshold", defaults.relevance_threshold
            ),
            max_injected_memories=memory_config.get(
                "max_injected_memories", defaults.max_injected_memories
            ),
            max_memory_tokens=memory_config.get(
                "max_memory_tokens", defaults.max_memory_tokens
            ),
            write_barrier=dict(memory_config.get("write_barrier") or {}),
            block_format=memory_config.get(
                "block_format", defaults.block_format
            ),
            block_recency=bool(memory_config.get(
                "block_recency", defaults.block_recency
            )),
            block_recency_unit=memory_config.get(
                "block_recency_unit", defaults.block_recency_unit
            ),
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)
