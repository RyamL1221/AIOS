"""
The memory pipeline's settings: the selection and budget parts of the
``memory:`` config block.

The kernel reports them at ``/memory/config`` (``pipeline``), and a
replicated agent builds its own copy from that report, so in the clean
condition every copy matches the kernel's settings by construction.
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from .ablation import Ablation
from .quota import QuotaSettings

# ``memory.supersession``: off, or retire earlier statements and never
# select them (docs/DELETION_AND_SUPERSESSION.md).
SUPERSESSION_MODES = ("off", "exclude")


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
    since the row's ``metadata.session`` (benchmark v2).
    ``supersession`` (``memory.supersession``) is ``"off"`` (the
    default) or ``"exclude"``: a later statement of a fact retires the
    earlier rows of its slot, and selection never picks a retired
    row. ``write_quota`` (``memory.write_quota``) bounds what one writer
    stores per user per session (``quota.QuotaSettings``; off by
    default, Subtask 18). ``ablate`` (``memory.ablate``) holds the
    kernel ablation switches (``ablation.Ablation``; every one the full
    kernel by default, Subtask 19, docs/ABLATION.md). A switch never
    rewrites another field: the ``effective_*`` values are what the
    library applies."""

    relevance_threshold: float = 0.0
    max_injected_memories: int = 5
    max_memory_tokens: int = 1500
    write_barrier: Dict[str, Any] = field(default_factory=dict)
    block_format: str = "compact"
    block_recency: bool = False
    block_recency_unit: str = "time"
    supersession: str = "off"
    write_quota: Dict[str, Any] = field(
        default_factory=lambda: QuotaSettings().as_dict()
    )
    ablate: Dict[str, Any] = field(
        default_factory=lambda: Ablation().as_dict()
    )

    def __post_init__(self):
        # Validated here, so a bad block fails where the settings are
        # built (the kernel at startup, an agent when it copies them).
        QuotaSettings.from_config(self.write_quota)
        # Every switch, its defaults filled in and its values normalized.
        object.__setattr__(
            self, "ablate", Ablation.from_config(self.ablate).as_dict()
        )
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
        if self.supersession not in SUPERSESSION_MODES:
            raise ValueError(
                "memory.supersession must be 'off' or 'exclude', "
                f"got {self.supersession!r}"
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
            supersession=memory_config.get(
                "supersession", defaults.supersession
            ),
            write_quota=QuotaSettings.from_config(
                memory_config.get("write_quota")
            ).as_dict(),
            ablate=Ablation.from_config(
                memory_config.get("ablate")
            ).as_dict(),
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    # -- the ablation switches applied (docs/ABLATION.md) ---------------

    @property
    def ablation(self) -> Ablation:
        return Ablation.from_config(self.ablate)

    @property
    def effective_supersession(self) -> str:
        """``supersession``, or ``"off"`` under ``supersession: off``."""
        return self.supersession if self.ablation.supersession_on else "off"

    @property
    def effective_block_format(self) -> str:
        """``block_format``, or ``"legacy"`` under
        ``block_format: legacy``."""
        if self.ablation.block_format == "legacy":
            return "legacy"
        return self.block_format

    @property
    def effective_threshold(self) -> float:
        """``relevance_threshold``, or the ablation's ``threshold``."""
        threshold: Optional[float] = self.ablation.threshold
        return self.relevance_threshold if threshold is None else threshold

    @property
    def effective_write_barrier(self) -> Dict[str, Any]:
        """``write_barrier``; under ``barrier: off`` its waits are off
        and its bookkeeping kept (``MemoryWriteBarrier``)."""
        if self.ablation.barrier_on:
            return dict(self.write_barrier)
        return dict(self.write_barrier, waits=False)

    @property
    def effective_write_quota(self) -> Dict[str, Any]:
        """``write_quota``, disabled under ``quota: off``."""
        if self.ablation.quota_on:
            return dict(self.write_quota)
        return dict(self.write_quota, enabled=False)
