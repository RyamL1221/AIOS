"""
Kernel ablation switches (NeurIPS Subtask 19, docs/ABLATION.md).

``memory.ablate`` holds one switch per kernel responsibility. Each
switch removes that one component and leaves every other setting as it
is; every switch defaults to the full kernel, and an absent block is
the full kernel. The block is a pipeline setting
(``PipelineSettings.ablate``), so the kernel reports it at
``/memory/config`` (``pipeline.ablate``) and the replicated agents copy
it. Where a switch acts:

- ``barrier: off``: the kernel's write barrier stamps nothing and no
  read waits (``MemoryManager``; a replicated agent's own barrier);
- ``identity: claim``: the kernel serves a request for the user id the
  agent claims, verbatim: no session binding, no canonicalization
  (``MemoryManager``; the library has neither);
- ``visibility: off``: every row of the user's partition is visible to
  every agent (``Selector``, ``MemoryPipeline.read``);
- ``supersession: off``: no write retires a row and selection excludes
  none, whatever ``memory.supersession`` says (``deletion.after_write``,
  ``Selector``);
- ``forget_scope``: ``writer``, the forget deletes only the requesting
  agent's own rows and records no tombstone; ``none``, it deletes
  nothing (``deletion.forget_fact``);
- ``quota: off``: no write quota, whatever ``memory.write_quota`` says
  (``MemoryPipeline.write``);
- ``block_format: legacy``: the pre-9d block; ``block_order:
  similarity``: the block's rows in the selector's score order instead
  of type order (``MemoryPipeline.build_block``);
- ``budget: off``: no token budget (k limits the block); ``threshold``:
  a number used instead of ``relevance_threshold`` (``Selector``);
- ``consumer_config: honor``: the kernel applies the k, threshold and
  token budget a consumer's chat request carries (the kernel's
  injector).

``ALIASES`` maps the negative controls of earlier subtasks to the
ablations they now mean, so their results load as such.
"""
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple

# Each switch: its default (the full kernel), its allowed values, and
# its ablated value (``--ablate SWITCH`` with no value).
SWITCHES: Dict[str, Tuple[Any, Tuple[Any, ...], Any]] = {
    "barrier": ("on", ("on", "off"), "off"),
    "identity": ("session", ("session", "claim"), "claim"),
    "visibility": ("on", ("on", "off"), "off"),
    "supersession": ("on", ("on", "off"), "off"),
    "forget_scope": ("user", ("user", "writer", "none"), "writer"),
    "quota": ("on", ("on", "off"), "off"),
    "block_format": ("compact", ("compact", "legacy"), "legacy"),
    "block_order": ("type", ("type", "similarity"), "similarity"),
    "budget": ("on", ("on", "off"), "off"),
    "threshold": (None, (), 0.3),
    "consumer_config": ("kernel", ("kernel", "honor"), "honor"),
}

# The negative controls folded into the mechanism (docs/ABLATION.md,
# "Aliases"): a trial recorded under one ran this ablation.
ALIASES: Dict[str, Dict[str, Any]] = {
    "no_visibility": {"visibility": "off"},
    "no_delete": {"forget_scope": "none"},
    "writer_scoped": {"forget_scope": "writer"},
    "no_supersession": {"supersession": "off"},
}

# YAML 1.1 reads a bare on / off as a boolean.
_ON_OFF = {True: "on", False: "off"}


def _value(name: str, value: Any) -> Any:
    """``value`` of switch ``name``, validated (an on / off switch also
    takes YAML's booleans)."""
    default, allowed, _ = SWITCHES[name]
    if name == "threshold":
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                "memory.ablate.threshold must be null or a number, "
                f"got {value!r}"
            )
        return float(value)
    if "on" in allowed and isinstance(value, bool):
        value = _ON_OFF[value]
    if value not in allowed:
        raise ValueError(
            f"memory.ablate.{name} must be one of {list(allowed)}, "
            f"got {value!r}"
        )
    return value


@dataclass(frozen=True)
class Ablation:
    """The ``memory.ablate`` block, validated; every field defaults to
    the full kernel."""

    barrier: str = "on"
    identity: str = "session"
    visibility: str = "on"
    supersession: str = "on"
    forget_scope: str = "user"
    quota: str = "on"
    block_format: str = "compact"
    block_order: str = "type"
    budget: str = "on"
    threshold: Optional[float] = None
    consumer_config: str = "kernel"

    def __post_init__(self):
        for name in SWITCHES:
            object.__setattr__(self, name, _value(name, getattr(self, name)))

    @classmethod
    def from_config(cls, block: Optional[Dict[str, Any]]) -> "Ablation":
        """The ablation a ``memory.ablate`` block (or a reported one)
        names; ``None`` or ``{}`` is the full kernel. An unknown key or
        value raises ``ValueError``, naming it."""
        if block is None:
            return cls()
        if isinstance(block, Ablation):
            return block
        if not isinstance(block, dict):
            raise ValueError(
                f"memory.ablate must be a mapping, got {block!r}"
            )
        unknown = set(block) - set(SWITCHES)
        if unknown:
            raise ValueError(f"memory.ablate: unknown keys {sorted(unknown)}")
        return cls(**block)

    def as_dict(self) -> Dict[str, Any]:
        """Every switch, defaults included (as ``/memory/config``
        reports it)."""
        return asdict(self)

    def changed(self) -> Dict[str, Any]:
        """The switches that differ from the full kernel (``{}`` for
        the full kernel): what a trial records as its ``ablation``."""
        return {name: value for name, value in self.as_dict().items()
                if value != SWITCHES[name][0]}

    @property
    def full(self) -> bool:
        return not self.changed()

    # Where each switch is read.
    @property
    def barrier_on(self) -> bool:
        return self.barrier == "on"

    @property
    def binds_identity(self) -> bool:
        return self.identity == "session"

    @property
    def visibility_on(self) -> bool:
        return self.visibility == "on"

    @property
    def supersession_on(self) -> bool:
        return self.supersession == "on"

    @property
    def quota_on(self) -> bool:
        return self.quota == "on"

    @property
    def budget_on(self) -> bool:
        return self.budget == "on"

    @property
    def honors_consumer_config(self) -> bool:
        return self.consumer_config == "honor"


def parse_switch(text: str) -> Tuple[str, Any]:
    """``"barrier"`` or ``"forget_scope=none"`` / ``"threshold=0.3"`` as
    ``(switch, value)``; a bare switch takes its ablated value. Raises
    ``ValueError`` for an unknown switch or value."""
    name, _, raw = text.partition("=")
    name = name.strip()
    if name not in SWITCHES:
        raise ValueError(
            f"unknown ablation switch {name!r}; one of {sorted(SWITCHES)}"
        )
    if not raw:
        return name, SWITCHES[name][2]
    raw = raw.strip()
    if name == "threshold":
        if raw.lower() in ("null", "none"):
            return name, None
        try:
            return name, _value(name, float(raw))
        except ValueError:
            raise ValueError(
                f"threshold must be a number, got {raw!r}"
            ) from None
    return name, _value(name, raw)


def ablation_of(switches: Dict[str, Any]) -> Ablation:
    """The ablation that sets ``switches`` and leaves the rest full."""
    return Ablation.from_config(dict(switches))
