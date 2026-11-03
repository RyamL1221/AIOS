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
    budget; ``write_barrier`` is ``memory.write_barrier``."""

    relevance_threshold: float = 0.0
    max_injected_memories: int = 5
    max_memory_tokens: int = 1500
    write_barrier: Dict[str, Any] = field(default_factory=dict)

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
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)
