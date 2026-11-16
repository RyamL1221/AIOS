"""
The write quota: how many rows one writer may store for one user in
one session (NeurIPS Subtask 18, docs/STRESS_DIMENSIONS.md, "flood10,
flood50").

``WriteQuota`` is a stage of ``MemoryPipeline.write``, before the
provider is called. For a write by ``writer`` for ``user`` in
``session`` it rejects:

- ``"duplicate"``: a text that normalizes (the scorer's normalization,
  ``matching.normalize``) to one the writer already stored for the user
  in that session; a rejected duplicate is not counted;
- ``"quota"``: any write once the writer has ``max_writes`` accepted
  writes for the user in that session.

Settings, ``memory.write_quota``: ``enabled`` (False), ``max_writes``
(4) and ``dedupe`` (True). Disabled, every write is admitted. The kernel
holds one quota for every request, as it holds one barrier; a
replicated agent's pipeline holds its own, which counts its own writes.
"""
import threading
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple

from .matching import normalize

QUOTA_KEYS = ("enabled", "max_writes", "dedupe")
DUPLICATE = "duplicate"
OVER_QUOTA = "quota"


@dataclass(frozen=True)
class QuotaSettings:
    """``memory.write_quota``, validated."""

    enabled: bool = False
    max_writes: int = 4
    dedupe: bool = True

    def __post_init__(self):
        if not isinstance(self.enabled, bool):
            raise ValueError("memory.write_quota.enabled must be a boolean")
        if not isinstance(self.dedupe, bool):
            raise ValueError("memory.write_quota.dedupe must be a boolean")
        if (isinstance(self.max_writes, bool)
                or not isinstance(self.max_writes, int)
                or self.max_writes < 1):
            raise ValueError(
                "memory.write_quota.max_writes must be a positive integer"
            )

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]]) -> "QuotaSettings":
        """The settings in a ``write_quota`` block (``None``: the
        defaults). An unknown key is refused."""
        config = dict(config or {})
        unknown = set(config) - set(QUOTA_KEYS)
        if unknown:
            raise ValueError(
                f"memory.write_quota: unknown keys {sorted(unknown)}"
            )
        return cls(**config)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


Key = Tuple[str, str, str]


class WriteQuota:
    """Per (user, writer, session) counts and stored texts. Thread-safe:
    one lock around every check, so concurrent writes of one writer are
    counted once each."""

    def __init__(self, settings: Optional[QuotaSettings] = None):
        self.settings = settings or QuotaSettings()
        self._lock = threading.Lock()
        self._counts: Dict[Key, int] = {}
        self._texts: Dict[Key, set] = {}

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    @staticmethod
    def key(user_id: Any, writer: Any, session: Any) -> Key:
        """The bucket a write counts in. A write with no session counts
        in the writer's bucket for the user without one."""
        return (str(user_id or ""), str(writer or ""),
                "" if session is None else str(session))

    def admit(self, user_id: Any, writer: Any, session: Any,
              text: Optional[str]) -> Optional[str]:
        """``None`` when the write may be stored (it is then counted),
        else why not: ``"duplicate"`` or ``"quota"``."""
        if not self.enabled:
            return None
        key = self.key(user_id, writer, session)
        form = normalize(text)
        with self._lock:
            texts = self._texts.setdefault(key, set())
            if self.settings.dedupe and form in texts:
                return DUPLICATE
            if self._counts.get(key, 0) >= self.settings.max_writes:
                return OVER_QUOTA
            self._counts[key] = self._counts.get(key, 0) + 1
            texts.add(form)
            return None

    def refund(self, user_id: Any, writer: Any, session: Any,
               text: Optional[str]) -> None:
        """Undo an admission whose write then failed: the provider
        stored nothing, so it neither counts nor blocks a retry."""
        if not self.enabled:
            return
        key = self.key(user_id, writer, session)
        with self._lock:
            if self._counts.get(key, 0) > 0:
                self._counts[key] -= 1
            self._texts.get(key, set()).discard(normalize(text))

    def counts(self) -> Dict[Key, int]:
        """A copy of the accepted-write counts, by bucket."""
        with self._lock:
            return dict(self._counts)
