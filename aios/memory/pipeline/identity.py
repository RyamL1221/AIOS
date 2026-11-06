"""
Identity resolution for memory retrieval, and the registry of the users
memories were written for. A resolver's ``IdentityRules`` give a user id
its canonical form (docs/HETEROGENEITY.md); by default ids are left as
they are.

The kernel holds one resolver for every agent; a replicated agent holds
its own, which knows only the users that agent wrote for
(docs/REPLICATED_LOGIC.md, difference 2).
"""
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set, Tuple

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IdentityRules:
    """How a resolver turns a user id into its canonical form
    (docs/HETEROGENEITY.md). The default leaves ids as they are; the
    kernel configures its one resolver from ``memory.identity``.

    ``casefold`` maps ids that differ only in case to one user;
    ``email_domains`` maps ``<id>@<domain>`` to ``<id>`` for the listed
    domains (compared case-insensitively)."""

    casefold: bool = False
    email_domains: Tuple[str, ...] = ()

    @classmethod
    def from_config(
        cls, identity_config: Optional[Dict[str, Any]]
    ) -> "IdentityRules":
        """The rules in a ``memory.identity`` block (``None``: none)."""
        identity_config = identity_config or {}
        unknown = set(identity_config) - {"casefold", "email_domains"}
        if unknown:
            raise ValueError(
                f"memory.identity: unknown keys {sorted(unknown)}"
            )
        domains = identity_config.get("email_domains") or ()
        if isinstance(domains, str):
            domains = (domains,)
        return cls(
            casefold=bool(identity_config.get("casefold", False)),
            email_domains=tuple(
                str(d).strip().lower().lstrip("@") for d in domains
            ),
        )

    def canonical(self, user_id: Optional[str]) -> Optional[str]:
        """``user_id`` in canonical form; a falsy id is returned as is."""
        if not user_id:
            return user_id
        out = str(user_id).strip()
        if self.email_domains and "@" in out:
            local, _, domain = out.rpartition("@")
            if local and domain.lower() in self.email_domains:
                out = local
        if self.casefold:
            out = out.casefold()
        return out

    def as_dict(self) -> Dict[str, Any]:
        return {
            "casefold": self.casefold,
            "email_domains": list(self.email_domains),
        }


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
        rules: Optional[IdentityRules] = None,
    ):
        self.registry: "OrderedDict[str, float]" = (
            registry if registry is not None else OrderedDict()
        )
        self.logger = logger or _logger
        self.rules = rules or IdentityRules()

    def canonical(self, user_id: Optional[str]) -> Optional[str]:
        """``user_id`` under this resolver's rules (unchanged without
        rules)."""
        return self.rules.canonical(user_id)

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
        request_user_id = self.canonical(request_user_id)
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
