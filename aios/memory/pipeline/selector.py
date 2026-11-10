"""
Selection: which memories an agent sees for one query.

search -> user partition -> visibility -> supersession -> tombstone guard
-> dedupe -> threshold -> sort -> cap, with diagnostics for every stage
and timings for the barrier wait, the provider calls and the selection.
The supersession and tombstone stages come before the threshold and the
cap (docs/DELETION_AND_SUPERSESSION.md), so a new statement competes for
the slot a retired one held, and ``cap_bound`` and ``budget_bound`` keep
their meaning.
"""
import logging
import time
from contextlib import nullcontext
from typing import Any, Dict, Optional, Tuple

from ..providers.base import MemoryProvider
from .barrier import MemoryWriteBarrier, WaitOutcome
from .identity import IdentityResolver
from .settings import PipelineSettings
from .tombstones import TombstoneStore, carried_form
from .visibility import apply_sharing_filter

logger = logging.getLogger(__name__)

# Shared retrieval over-fetches because a provider applies k before the
# visibility filter removes other agents' private memories.
SHARED_FETCH_FACTOR = 4


def commits_synchronously(provider: MemoryProvider) -> bool:
    """True for a provider whose writes are durable when ``add``
    returns (``MemoryProvider.synchronous_commit``), where a barrier
    wait would only add latency."""
    return getattr(type(provider), "synchronous_commit", False) is True


class Selector:
    """Runs the selection for one pipeline."""

    def __init__(
        self,
        provider: MemoryProvider,
        settings: PipelineSettings,
        barrier: Optional[MemoryWriteBarrier],
        resolver: IdentityResolver,
        tombstones: Optional[TombstoneStore] = None,
        usage_tag: Any = None,
    ):
        self.provider = provider
        # Tags the provider's calls with the user (``MemoryPipeline``'s
        # ``usage_tag``); nothing by default.
        self.usage_tag = usage_tag or (lambda user_id: nullcontext())
        self.settings = settings
        self.barrier = barrier
        self.resolver = resolver
        self.tombstones = tombstones

    def await_pending_writes(
        self,
        user_id: Optional[str],
        barrier_snapshot: Optional[int] = None,
    ) -> WaitOutcome:
        """Wait for writes accepted before a retrieval of ``user_id``.

        Args:
            user_id: The user the retrieval is scoped to.
            barrier_snapshot: The high-water mark stamped when the
                retrieval was accepted. ``None`` takes one now; the
                sentinel ``0`` skips the wait.

        Returns:
            The wait outcome; ``BYPASSED`` when no wait ran.
        """
        barrier = self.barrier
        if (
            not user_id
            or barrier is None
            or commits_synchronously(self.provider)
        ):
            return WaitOutcome.BYPASSED
        if barrier_snapshot is None:
            barrier_snapshot = barrier.snapshot(user_id)
        if not barrier_snapshot:
            return WaitOutcome.BYPASSED
        return barrier.wait_until_drained(user_id, barrier_snapshot)

    def fetch(
        self, scope_user_id: str, query_text: str, top_k: int
    ) -> Tuple[list, Optional[str]]:
        """One provider search with an explicit ``top_k``, as rows.
        Returns ``(rows, error)``."""
        try:
            found = self.provider.search(query_text, scope_user_id, top_k)
        except Exception as e:
            return [], f"{type(e).__name__}: {e}"
        return [candidate.to_row() for candidate in found], None

    @staticmethod
    def merge_and_deduplicate(own: list, shared: list) -> list:
        """Merge own and shared results, dropping shared rows whose
        content exactly matches an earlier row. Own rows always come
        first and are never dropped."""
        seen_content: set = set()
        merged: list = []
        for mem in own:
            seen_content.add(mem.get("content", ""))
            merged.append(mem)
        for mem in shared:
            content = mem.get("content", "")
            if content not in seen_content:
                seen_content.add(content)
                merged.append(mem)
        return merged

    def select(
        self,
        agent_name: str,
        user_id: Optional[str],
        query_text: str,
        *,
        k: int,
        include_shared: bool,
        request_user_id: Optional[str] = None,
        sharing_policy: Optional[str] = None,
        barrier_snapshot: Optional[int] = None,
    ) -> "tuple[list, dict]":
        """Decide which memories an agent sees.

        Runs identity resolution, one barrier wait, own and shared
        retrieval, the user-partition check, the visibility rule,
        exact-content dedupe, the relevance threshold, the sort and the
        count cap, in that order.

        Args:
            agent_name: The requesting agent.
            user_id: The scope named by the caller, if any.
            query_text: The retrieval query.
            k: Maximum candidates returned; own fetch size.
            include_shared: Also fetch ``SHARED_FETCH_FACTOR * k`` rows
                of memories shared by other agents.
            request_user_id: The per-request identity; wins over
                ``user_id``.
            sharing_policy: An SDK caller's policy. ``"shared"`` only
                selects the shared fetch; any other value also narrows
                the visibility rule (for example ``"private"``: own
                private memories only).
            barrier_snapshot: See ``await_pending_writes``.

        Returns:
            ``(candidates, diagnostics)``. ``diagnostics["error"]`` is
            the provider's error when own retrieval failed, else None;
            ``diagnostics["shared_error"]`` is the same for the shared
            fetch. Either fetch's rows are then missing, and the caller
            decides what that means: SDK search fails on the own error,
            injection reports both (``MemoryPipeline.inject``).
            ``barrier_wait_ms``, ``search_ms`` (the provider calls) and
            ``select_ms`` (partition through cap) time the stages.
        """
        started = time.perf_counter()
        resolved_user_id = self.resolver.resolve(
            agent_name, request_user_id or user_id
        )
        scope_user_id = resolved_user_id or agent_name
        fetch_shared = include_shared and resolved_user_id is not None
        top_k_used = {
            "own": k,
            "shared": SHARED_FETCH_FACTOR * k if fetch_shared else 0,
        }
        diagnostics: Dict[str, Any] = {
            "resolved_user_id": resolved_user_id,
            "own_fetched": 0,
            "shared_fetched": 0,
            "after_partition": 0,
            "after_visibility": 0,
            "after_supersession": 0,
            "superseded_rows": [],
            "after_tombstone": 0,
            "tombstoned_rows": [],
            "tombstoned_forms": 0,
            "after_dedupe": 0,
            "scores_present": False,
            "threshold_used": None,
            "after_threshold": 0,
            "after_cap": 0,
            "top_k_used": top_k_used,
            "barrier_waits": [],
            "error": None,
            "shared_error": None,
        }

        outcome = self.await_pending_writes(scope_user_id, barrier_snapshot)
        if outcome is not WaitOutcome.BYPASSED:
            diagnostics["barrier_waits"].append({
                "user_id": scope_user_id,
                "outcome": outcome.name,
            })
        waited = time.perf_counter()

        # The provider's own LLM and embedding calls count to this user.
        with self.usage_tag(scope_user_id):
            # Without a resolved user, own memories live in the agent's
            # scope, where a write that names no user is filed.
            own, diagnostics["error"] = self.fetch(
                scope_user_id, query_text, top_k_used["own"]
            )

            shared: list = []
            if fetch_shared:
                # Kept in the diagnostics, not only logged: a failed
                # shared fetch must not read as a store with no shared
                # rows (docs/BENCHMARK_V2.md, Amendment 2).
                shared, diagnostics["shared_error"] = self.fetch(
                    scope_user_id, query_text, top_k_used["shared"]
                )
                if diagnostics["shared_error"]:
                    logger.debug(
                        "Shared memory retrieval failed for user_id=%s: %s",
                        scope_user_id,
                        diagnostics["shared_error"],
                    )
        searched = time.perf_counter()
        diagnostics["own_fetched"] = len(own)
        diagnostics["shared_fetched"] = len(shared)

        # User partition (defense in depth, fail closed): a provider
        # that returns a mis-scoped row must not leak it, and a row with
        # no user_id does not count as this user's.
        def in_partition(mem: dict) -> bool:
            meta = mem.get("metadata") or {}
            return meta.get("user_id", "") == scope_user_id

        own = [mem for mem in own if in_partition(mem)]
        shared = [mem for mem in shared if in_partition(mem)]
        diagnostics["after_partition"] = len(own) + len(shared)

        # The only place visibility is enforced: providers return every
        # row in the scope (docs/PROVIDER_CONTRACT.md).
        policy = None if sharing_policy == "shared" else sharing_policy

        def visible(rows: list) -> list:
            return apply_sharing_filter(
                rows,
                agent_name,
                scope_user_id,
                policy,
                lambda mem: mem.get("metadata") or {},
            )

        own = visible(own)
        shared = visible(shared)
        diagnostics["after_visibility"] = len(own) + len(shared)

        def drop(rows: list, dropping, dropped: dict) -> list:
            """``rows`` without those ``dropping`` holds for, which are
            recorded once each in ``dropped`` (own rows are also among
            the shared fetch's, so a row can come twice)."""
            kept = []
            for mem in rows:
                if dropping(mem):
                    dropped[str(mem.get("memory_id"))] = mem
                else:
                    kept.append(mem)
            return kept

        # A retired row (an earlier statement of a fact with a later
        # one) is never selected.
        superseded: Dict[str, dict] = {}
        if self.settings.supersession == "exclude":
            def retired(mem: dict) -> bool:
                return bool((mem.get("metadata") or {}).get("superseded_by"))

            own = drop(own, retired, superseded)
            shared = drop(shared, retired, superseded)
        diagnostics["after_supersession"] = len(own) + len(shared)
        diagnostics["superseded_rows"] = sorted(superseded)

        # The tombstone guard: no row carrying a forgotten value is
        # selected. After a complete forget it drops nothing, so a drop
        # means a carrier escaped the forget and the sweep.
        forms = (
            self.tombstones.forms(scope_user_id)
            if self.tombstones is not None else []
        )
        diagnostics["tombstoned_forms"] = len(forms)
        tombstoned: Dict[str, dict] = {}
        if forms:
            def carries(mem: dict) -> bool:
                return carried_form(
                    mem.get("content"), mem.get("metadata"), forms
                ) is not None

            own = drop(own, carries, tombstoned)
            shared = drop(shared, carries, tombstoned)
            for memory_id in sorted(tombstoned):
                logger.warning(
                    "Selection guard dropped memory %s of user_id=%s: it "
                    "carries a forgotten value, so it escaped the forget",
                    memory_id, scope_user_id,
                )
        diagnostics["after_tombstone"] = len(own) + len(shared)
        diagnostics["tombstoned_rows"] = sorted(tombstoned)

        results = (
            self.merge_and_deduplicate(own, shared) if shared else own
        )
        diagnostics["after_dedupe"] = len(results)

        # A provider without scored search returns no scores: the
        # threshold cannot apply and scores_present records that.
        scores_present = any(
            mem.get("score") is not None for mem in results
        )
        diagnostics["scores_present"] = scores_present
        if scores_present:
            threshold = self.settings.relevance_threshold
            diagnostics["threshold_used"] = threshold
            results = [
                mem for mem in results
                if mem.get("score") is None
                or mem["score"] >= threshold
            ]
            results = sorted(
                results,
                key=lambda mem: mem.get("score") or 0,
                reverse=True,
            )
        diagnostics["after_threshold"] = len(results)

        results = results[:k]
        diagnostics["after_cap"] = len(results)
        selected = time.perf_counter()
        diagnostics["barrier_wait_ms"] = (waited - started) * 1000
        diagnostics["search_ms"] = (searched - waited) * 1000
        diagnostics["select_ms"] = (selected - searched) * 1000
        return results, diagnostics
