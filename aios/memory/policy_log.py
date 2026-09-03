"""
Per-trial structured logging for the adaptive threshold policy.

Emits one JSON object per line (JSONL) describing each policy decision
and each reward update, so the records can be *joined to the external
benchmark's per-trial JSON logs by trial id*. The trial id is taken
verbatim from whatever the caller supplies (the benchmark's own id
field carried through ``metadata["trial_id"]`` on add/retrieve queries
and ``trial_metadata["trial_id"]`` on ``report_reward``) — this module
never invents an id scheme.

Record types (``event`` field):

- ``"select"``: a bandit chose a threshold for a gate decision.
  Fields: ``trial_id``, ``bandit``, ``value``, ``arm_index``,
  ``gate`` (the decision role: "novelty" | "similarity" |
  "redundancy"), ``llm_core``, ``task_type``, ``context`` (the feature
  vector as a list), ``ts``.
- ``"reward"``: a reward was applied to one bandit decision.
  Fields: ``trial_id``, ``bandit``, ``arm_index``, ``reward``,
  ``memory_id``, ``ts``.

The logger is inert unless an output path is configured (returned by
``PolicyTrialLogger.from_config`` only when
``memory.adaptive_policy.trial_log`` is set), so the frozen baseline
and the flag-on-but-unconfigured case write nothing.

Thread-safe: appends are serialized under a lock (memory syscalls run
on scheduler worker threads).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PolicyTrialLogger:
    """Append-only JSONL logger for policy decisions and rewards."""

    def __init__(self, path: str):
        """Initialize the logger.

        Args:
            path: Filesystem path for the JSONL output. Parent
                directories are created if needed.
        """
        self.path = path
        self._lock = threading.Lock()
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        logger.info("PolicyTrialLogger writing to %s", path)

    @classmethod
    def from_config(
        cls, adaptive_config: Dict[str, Any]
    ) -> Optional["PolicyTrialLogger"]:
        """Build a logger from the ``adaptive_policy`` config block,
        or return ``None`` when no ``trial_log`` path is set.

        Args:
            adaptive_config: The ``memory.adaptive_policy`` dict.

        Returns:
            A configured logger, or ``None`` (logging disabled).
        """
        path = (adaptive_config or {}).get("trial_log")
        if not path:
            return None
        try:
            return cls(path)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(
                "Failed to create PolicyTrialLogger at %s: %s",
                path,
                e,
            )
            return None

    def _write(self, record: Dict[str, Any]) -> None:
        record.setdefault("ts", time.time())
        line = json.dumps(record, default=str)
        with self._lock:
            with open(self.path, "a") as f:
                f.write(line + "\n")

    def log_select(
        self,
        trial_id: Optional[str],
        bandit: str,
        gate: str,
        value: float,
        arm_index: int,
        llm_core: str,
        task_type: str,
        context: Any,
    ) -> None:
        """Record a threshold-selection decision.

        Args:
            trial_id: The benchmark trial id (join key), or ``None``.
            bandit: Bandit name (e.g. "novelty_threshold").
            gate: Decision role ("novelty" | "similarity" |
                "redundancy").
            value: The selected threshold value.
            arm_index: The selected arm index.
            llm_core: Bandit context — model name.
            task_type: Bandit context — task type.
            context: The context feature vector (array-like).
        """
        try:
            ctx_list: List[float]
            if hasattr(context, "tolist"):
                ctx_list = context.tolist()
            else:
                ctx_list = list(context)
        except Exception:
            ctx_list = []
        self._write(
            {
                "event": "select",
                "trial_id": trial_id,
                "bandit": bandit,
                "gate": gate,
                "value": value,
                "arm_index": arm_index,
                "llm_core": llm_core,
                "task_type": task_type,
                "context": ctx_list,
            }
        )

    def log_reward(
        self,
        trial_id: Optional[str],
        bandit: str,
        arm_index: int,
        reward: float,
        memory_id: str,
    ) -> None:
        """Record a reward applied to one bandit decision.

        Args:
            trial_id: The benchmark trial id (join key), or ``None``.
            bandit: Bandit name.
            arm_index: The arm the reward was applied to.
            reward: The scalar reward value.
            memory_id: The memory_id whose decision this reward updated.
        """
        self._write(
            {
                "event": "reward",
                "trial_id": trial_id,
                "bandit": bandit,
                "arm_index": arm_index,
                "reward": reward,
                "memory_id": memory_id,
            }
        )
