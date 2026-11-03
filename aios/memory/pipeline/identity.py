"""
Identity resolution for memory retrieval, and the registry of the users
memories were written for.

The kernel holds one resolver for every agent; a replicated agent holds
its own, which knows only the users that agent wrote for
(docs/REPLICATED_LOGIC.md, difference 2).
"""
import logging
import time
from collections import OrderedDict
from typing import Optional, Set

_logger = logging.getLogger(__name__)


class IdentityResolver:
    """Resolves the end-user a retrieval is for.

    ``registry`` maps each user written for to the monotonic time of its
    last write, most recent last. ``logger`` lets the kernel keep its log
    lines under its own logger.
    """

    def __init__(
        self,
        registry: "Optional[OrderedDict[str, float]]" = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.registry: "OrderedDict[str, float]" = (
            registry if registry is not None else OrderedDict()
        )
        self.logger = logger or _logger

    def register(self, user_id: str) -> None:
        """Record a write for ``user_id``, as the most recent."""
        self.registry[user_id] = time.monotonic()
        self.registry.move_to_end(user_id)

    @property
    def known_user_ids(self) -> Set[str]:
        return set(self.registry.keys())

    @property
    def latest_user_id(self) -> Optional[str]:
        """The most recently written user_id, or None."""
        if not self.registry:
            return None
        return next(reversed(self.registry))

    def resolve(
        self, agent_name: str, request_user_id: Optional[str] = None
    ) -> Optional[str]:
        """Resolve the active end-user for a retrieval.

        Returns the explicit per-request identity, or ``None``, which
        tells the caller to skip shared retrieval and use ``agent_name``
        for own memories only. Never returns ``agent_name``: it is not a
        valid end-user for cross-agent retrieval. Never guesses from
        ``latest_user_id``: that caused cross-user contamination.
        """
        if request_user_id and request_user_id != agent_name:
            self.logger.info(
                "user_id resolved from REQUEST: %s (agent=%s)",
                request_user_id,
                agent_name,
            )
            return request_user_id
        if not request_user_id:
            self.logger.debug(
                "No request-scoped user_id; skipping user-scoped "
                "retrieval (agent=%s)",
                agent_name,
            )
        return None
