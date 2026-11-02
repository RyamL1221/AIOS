"""
Memory Manager for the AIOS system.

This module provides the MemoryManager class that serves as the high-level
interface to the memory management system. It uses pluggable memory providers
to enable different storage backends (in-house, Mem0, Zep).
"""
import logging
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Set, Tuple

from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from aios.config.config_manager import config as global_config
from .embedding import EmbeddingConfig
from .providers import ProviderFactory, MemoryProvider
from .providers.base import Candidate, ProviderError
from .providers.in_house import InHouseProvider
from .providers.zep import ZepProvider
from .visibility import apply_sharing_filter
from .write_barrier import MemoryWriteBarrier, WaitOutcome

logger = logging.getLogger(__name__)

# Shared retrieval over-fetches because a provider applies k before the
# kernel's visibility filter removes other agents' private memories.
SHARED_FETCH_FACTOR = 4

# An update may not move a memory to another owner or user, or rewrite
# when it was created.
UPDATE_PROTECTED_METADATA = ("owner_agent", "user_id", "created_at")


class MemoryManager:
    """
    Memory manager using pluggable providers.
    
    This class serves as a high-level interface to the memory management system,
    delegating operations to a configured memory provider. It supports multiple
    backend providers (in-house, Mem0, Zep) through the provider abstraction layer.
    
    The manager maintains backward compatibility with existing code by defaulting
    to the "in-house" provider when no provider is specified.
    
    Attributes:
        provider (MemoryProvider): The configured memory provider instance
        known_user_ids (Set[str]): User IDs observed in memory metadata
            during add_memory operations.  The ContextInjector reads
            this set to discover which real user_ids have memories in
            the store, enabling cross-agent shared retrieval without
            requiring the requesting agent to already have its own
            memories.
        barrier (MemoryWriteBarrier): Per-user_id write barrier that
            tracks accepted-but-uncommitted ``create_memory``
            operations and lets retrievals scoped to the same
            ``user_id`` wait until those writes drain. Read by
            ``SyscallExecutor`` (acceptance-time stamping) and
            ``ContextInjector`` (inline waits). Configured via
            ``memory.write_barrier.*``.
    """
    
    def __init__(
        self,
        log_mode: str = "console",
        provider: Optional[str] = None,
    ):
        """
        Initialize the MemoryManager.
        
        Args:
            log_mode: Logging mode for memory operations. Defaults to "console".
            provider: Optional provider type to use. If not specified, uses the
                     provider from configuration or defaults to "in-house".
                     Valid values: "in-house", "mem0", "zep"
        """
        self.log_mode = log_mode
        
        # Registry of user_ids seen in memory metadata.
        # Populated by add_memory; read by ContextInjector.
        # Keys: user_id strings. Values: monotonic timestamp of
        # last write. OrderedDict preserves insertion order; we
        # move-to-end on each write for recency tracking.
        self._known_user_ids: OrderedDict[str, float] = OrderedDict()
        
        # Get configuration
        memory_config = global_config.get_memory_config() or {}
        storage_config = global_config.get_storage_config() or {}
        # The one embedding model every backend uses.
        self.embedding = EmbeddingConfig.from_memory_config(memory_config)
        self.provider_type = (
            provider or memory_config.get("provider", "in-house")
        )
        
        # Determine provider type: explicit parameter > config > default
        provider_type = provider or memory_config.get("provider", "in-house")
        
        # Get provider-specific configuration
        provider_config = self._get_provider_config(
            provider_type, memory_config, storage_config
        )
        
        # Create the provider using the factory
        self.provider = ProviderFactory.create(provider_type, provider_config)

        # Per-user_id write barrier. Owns the pending-write registry
        # consulted by SyscallExecutor (acceptance-time stamping) and
        # ContextInjector (inline waits). Reads memory.write_barrier.*
        # once at construction; defaults are coded in the barrier so
        # omitting the section is safe.
        barrier_config = memory_config.get("write_barrier", {}) or {}
        self.barrier = MemoryWriteBarrier(config=barrier_config)

        # Selection settings for retrieve_for_agent. A threshold of 0.0
        # ranks scored candidates without dropping any.
        self.relevance_threshold = memory_config.get(
            "relevance_threshold", 0.0
        )
        self.max_injected_memories = memory_config.get(
            "max_injected_memories", 5
        )
        self.max_memory_tokens = memory_config.get(
            "max_memory_tokens", 1500
        )

    @property
    def known_user_ids(self) -> Set[str]:
        """Backward-compatible set view for existing code."""
        return set(self._known_user_ids.keys())

    @property
    def latest_user_id(self) -> Optional[str]:
        """Return the most recently written user_id, or None."""
        if not self._known_user_ids:
            return None
        # Last key in OrderedDict = most recently moved-to-end
        return next(reversed(self._known_user_ids))

    def _register_user_id(self, user_id: str) -> None:
        """Register a user_id with current timestamp, moving to
        end of the ordered registry."""
        self._known_user_ids[user_id] = time.monotonic()
        self._known_user_ids.move_to_end(user_id)
    
    def _get_provider_config(
        self,
        provider_type: str,
        memory_config: Dict[str, Any],
        storage_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get provider-specific configuration.
        
        Extracts the appropriate configuration section based on the provider type.
        
        Args:
            provider_type: The type of provider ("in-house", "in-memory",
                "mem0", "zep")
            memory_config: The memory configuration section from config
            storage_config: The storage configuration section from config
        
        Returns:
            Dictionary containing provider-specific configuration
        """
        embedding = EmbeddingConfig.from_memory_config(memory_config)
        if provider_type == "in-house":
            return {
                **(memory_config.get("chroma_inhouse") or {}),
                "embedding": embedding.as_dict(),
            }
        elif provider_type == "in-memory":
            return dict(memory_config.get("in_memory") or {})
        elif provider_type == "mem0":
            mem0_config = dict(memory_config.get("mem0") or {})
            pinned = embedding.mem0_embedder()
            configured = mem0_config.get("embedder")
            if configured and configured != pinned:
                logger.warning(
                    "memory.mem0.embedder is ignored; Mem0 embeds with "
                    "memory.embedding (%s)", embedding.model,
                )
            mem0_config["embedder"] = pinned
            return mem0_config
        elif provider_type == "zep":
            return memory_config.get("zep", {})
        return {}

    def _provider_supports_barrier(self) -> bool:
        """Return True for providers that participate in the
        per-user write barrier.

        The barrier is meaningful only for providers whose writes
        commit asynchronously (Mem0Provider and Mem0-shaped test
        doubles). InHouseProvider and ZepProvider commit
        synchronously inside their own ``add_memory`` calls, so
        the barrier wait would only add latency without changing
        ordering -- Clause 3.5 of the design requires those paths
        stay byte-for-byte identical to the pre-fix behaviour.

        We use an *exclusion* check (``not isinstance(...,
        (InHouseProvider, ZepProvider))``) rather than a positive
        ``isinstance(self.provider, Mem0Provider)`` so Mem0-shaped
        test doubles -- which subclass ``MemoryProvider`` directly
        -- still take the barrier path. This is also a
        defense-in-depth backstop on top of the barrier's own
        ``_enabled`` check.
        """
        return not isinstance(
            self.provider, (InHouseProvider, ZepProvider)
        )
    
    def _resolve_user_id(
        self,
        agent_name: str,
        request_user_id: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve the active end-user for a retrieval.

        Returns the explicit per-request identity, or ``None``, which
        tells the caller to skip shared retrieval and use ``agent_name``
        for own memories only. Never returns ``agent_name``: it is not a
        valid end-user for cross-agent retrieval. Never guesses from
        ``latest_user_id``: that caused cross-user contamination.
        """
        if request_user_id and request_user_id != agent_name:
            logger.info(
                "user_id resolved from REQUEST: %s (agent=%s)",
                request_user_id,
                agent_name,
            )
            return request_user_id
        if not request_user_id:
            logger.debug(
                "No request-scoped user_id; skipping user-scoped "
                "retrieval (agent=%s)",
                agent_name,
            )
        return None

    def _await_pending_writes(
        self,
        user_id: Optional[str],
        barrier_snapshot: Optional[int] = None,
    ) -> WaitOutcome:
        """Wait for writes accepted before a retrieval of ``user_id``.

        Args:
            user_id: The user the retrieval is scoped to.
            barrier_snapshot: The high-water mark stamped at syscall
                acceptance. ``None`` takes one now (kernel-internal
                retrievals have no acceptance step); the sentinel ``0``
                skips the wait.

        Returns:
            The wait outcome; ``BYPASSED`` when no wait ran.
        """
        barrier = getattr(self, "barrier", None)
        if (
            not user_id
            or barrier is None
            or not self._provider_supports_barrier()
        ):
            return WaitOutcome.BYPASSED
        if barrier_snapshot is None:
            barrier_snapshot = barrier.snapshot(user_id)
        if not barrier_snapshot:
            return WaitOutcome.BYPASSED
        return barrier.wait_until_drained(user_id, barrier_snapshot)

    def stamp_syscall(self, memory_syscall) -> None:
        """Stamp a memory syscall against the write barrier.

        The only stamping site. It must run before the write can be
        observed as accepted: a write records itself before it is
        enqueued, so any retrieval accepted later sees it pending; a
        retrieval records the high-water mark at acceptance, so later
        writes never delay it. ``add_agentic_memory`` is included
        because this can run before ``execute_request`` rewrites it. An
        update is stamped like a write, so a retrieval accepted after it
        reads the new content.
        """
        query = memory_syscall.query
        operation = query.operation_type
        if operation in ("add_memory", "add_agentic_memory"):
            user_id = query.params.get("metadata", {}).get("user_id")
            if user_id:
                memory_syscall.barrier_seq = self.barrier.acquire(user_id)
        elif operation == "update_memory":
            user_id = self._update_user_id(query)
            if user_id:
                memory_syscall.barrier_seq = self.barrier.acquire(user_id)
        elif operation in ("retrieve_memory", "retrieve_memory_raw"):
            user_id = query.params.get("user_id")
            if user_id:
                memory_syscall.barrier_snapshot = self.barrier.snapshot(
                    user_id
                )

    @staticmethod
    def _update_user_id(query: MemoryQuery) -> Optional[str]:
        """The user an update is stamped under: the caller's user_id."""
        params = query.params
        return (
            params.get("user_id")
            or (params.get("metadata") or {}).get("user_id")
        )

    @staticmethod
    def _can_write(agent_name: str, metadata: Optional[dict]) -> bool:
        """Only the owner may update or delete a memory, shared or not.
        Fails closed: a memory with no owner is not writable."""
        return (metadata or {}).get("owner_agent") == agent_name

    def _locate_memory(
        self, query: MemoryQuery, agent_name: str
    ) -> Optional[Candidate]:
        """Fetch a memory named by id, wherever it is stored.

        Providers keep one collection per user, so an id alone cannot
        find a row. Uses the caller's user_id when given; otherwise tries
        the agent's own scope, then the provider's default.
        """
        params = query.params
        user_id = (
            params.get("user_id")
            or (params.get("metadata") or {}).get("user_id")
        )
        scopes = [user_id] if user_id else [agent_name, None]
        for scope in scopes:
            found = self.provider.get(params["memory_id"], scope)
            if found is not None:
                return found
        return None

    @staticmethod
    def _can_read(agent_name: str, metadata: Optional[dict]) -> bool:
        """Apply the visibility rule to one memory read by id. Fails
        closed: a memory with no owner is not readable."""
        metadata = metadata or {}
        return (
            metadata.get("owner_agent") == agent_name
            or metadata.get("sharing_policy") == "shared"
        )

    def _fetch_candidates(
        self, scope_user_id: str, query_text: str, top_k: int
    ) -> Tuple[list, Optional[str]]:
        """One provider search with an explicit ``top_k``, as kernel
        rows. Returns ``(rows, error)``."""
        try:
            found = self.provider.search(query_text, scope_user_id, top_k)
        except Exception as e:
            return [], f"{type(e).__name__}: {e}"
        return [candidate.to_row() for candidate in found], None

    @staticmethod
    def _merge_and_deduplicate(own: list, shared: list) -> list:
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

    def retrieve_for_agent(
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

        The single kernel retrieval path: context injection and SDK
        search both end here, so the visibility rule holds whatever a
        caller passes. Runs identity resolution, one barrier wait, own
        and shared retrieval, the user-partition check, the visibility
        rule, exact-content dedupe, the relevance threshold, the sort
        and the count cap, in that order. Called directly, never through
        the syscall queue.

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
            barrier_snapshot: See ``_await_pending_writes``.

        Returns:
            ``(candidates, diagnostics)``. ``diagnostics["error"]`` is
            the provider's error when own retrieval failed, else None.
        """
        resolved_user_id = self._resolve_user_id(
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
            "after_dedupe": 0,
            "scores_present": False,
            "threshold_used": None,
            "after_threshold": 0,
            "after_cap": 0,
            "top_k_used": top_k_used,
            "barrier_waits": [],
            "error": None,
        }

        outcome = self._await_pending_writes(
            scope_user_id, barrier_snapshot
        )
        if outcome is not WaitOutcome.BYPASSED:
            diagnostics["barrier_waits"].append({
                "user_id": scope_user_id,
                "outcome": outcome.name,
            })

        # Without a resolved user, own memories live in the agent's
        # scope, where add_memory files a write that names no user.
        own, diagnostics["error"] = self._fetch_candidates(
            scope_user_id, query_text, top_k_used["own"]
        )

        shared: list = []
        if fetch_shared:
            shared, error = self._fetch_candidates(
                scope_user_id, query_text, top_k_used["shared"]
            )
            if error:
                logger.debug(
                    "Shared memory retrieval failed for user_id=%s: %s",
                    scope_user_id,
                    error,
                )
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

        results = (
            self._merge_and_deduplicate(own, shared) if shared else own
        )
        diagnostics["after_dedupe"] = len(results)

        # A provider without scored search returns no scores: the
        # threshold cannot apply and scores_present records that.
        scores_present = any(
            mem.get("score") is not None for mem in results
        )
        diagnostics["scores_present"] = scores_present
        if scores_present:
            threshold = getattr(self, "relevance_threshold", 0.0)
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
        return results, diagnostics

    def _analyze_query_to_memory(self, query: MemoryQuery) -> 'MemoryNote':
        """
        Convert a MemoryQuery to a MemoryNote object.
        
        This method extracts parameters from a MemoryQuery and creates a
        MemoryNote object suitable for provider operations.
        
        Args:
            query: Memory query containing parameters
        
        Returns:
            MemoryNote created from query parameters
        """
        from .note import MemoryNote
        
        params = query.params
        valid_keys = [
            "content", "id", "keywords", "links", "retrieval_count",
            "timestamp", "last_accessed", "context", "evolution_history",
            "category", "tags"
        ]
        
        # Extract metadata if present
        metadata = params.get("metadata", {})
        
        # Create filtered data dictionary
        filtered_data = {}
        
        # Add direct parameters
        for k in params:
            if k in valid_keys:
                filtered_data[k] = params[k]
        
        # Handle memory_id specifically
        if "memory_id" in params and "id" not in filtered_data:
            filtered_data["id"] = params["memory_id"]
        
        # Add metadata fields if they exist
        if "tags" in metadata and "tags" not in filtered_data:
            filtered_data["tags"] = metadata.get("tags", [])
        if "keywords" in metadata and "keywords" not in filtered_data:
            filtered_data["keywords"] = metadata.get("keywords", [])
        if "category" in metadata and "category" not in filtered_data:
            filtered_data["category"] = metadata.get("category", "Uncategorized")
        
        memory_note = MemoryNote(**filtered_data)
        
        # Preserve the full metadata dict on the note so
        # that providers can read cross-agent fields
        # (user_id, owner_agent, sharing_policy, memory_type).
        if metadata:
            memory_note.metadata = metadata
        
        return memory_note
    
    def address_request(self, memory_syscall) -> MemoryResponse:
        """
        Process an agent's memory request.
        
        Routes the memory syscall to the appropriate provider method based
        on the operation type specified in the syscall's query.
        
        Args:
            memory_syscall: Memory syscall object containing the operation
                           and parameters
        
        Returns:
            MemoryResponse containing the result of the operation
        
        Raises:
            TypeError: If memory_syscall is not a MemorySyscall
            ValueError: If the operation type is invalid
        """
        # Import here to avoid circular dependency
        from aios.syscall.memory import MemorySyscall
        
        if not isinstance(memory_syscall, MemorySyscall):
            raise TypeError(f"Expected MemorySyscall, got {type(memory_syscall)}")
        
        query = memory_syscall.query
        operation_type = query.operation_type
        
        if operation_type == "add_memory":
            memory_note = self._analyze_query_to_memory(query)
            # Ensure metadata has a user_id so the memory is
            # scoped properly in Mem0's ChromaDB.  When the SDK
            # caller didn't provide an explicit user_id, fall
            # back to the requesting agent's name — this keeps
            # add and retrieve consistent (both scope to
            # agent_name by default).
            if memory_note.metadata is None:
                memory_note.metadata = {}
            if not memory_note.metadata.get("user_id"):
                memory_note.metadata["user_id"] = (
                    memory_syscall.agent_name
                )
            # The visibility rule keys on owner_agent, so a write
            # without one would be invisible even to its author.
            if not memory_note.metadata.get("owner_agent"):
                memory_note.metadata["owner_agent"] = (
                    memory_syscall.agent_name
                )
            # The rest of the required metadata (PROVIDER_CONTRACT.md).
            memory_note.metadata.setdefault("memory_type", "")
            if not memory_note.metadata.get("sharing_policy"):
                memory_note.metadata["sharing_policy"] = "private"
            memory_note.metadata.setdefault(
                "created_at", datetime.now(timezone.utc).isoformat()
            )
            # Track user_id for cross-agent discovery.
            uid = (memory_note.metadata or {}).get("user_id")
            logger.info(
                "add_memory: agent=%s, uid_from_metadata=%s, "
                "latest_user_id=%s, known=%s",
                memory_syscall.agent_name,
                uid,
                self.latest_user_id,
                self.known_user_ids,
            )
            if uid and uid != memory_syscall.agent_name:
                self._register_user_id(uid)
                logger.info(
                    "Registered user_id=%s (latest=%s, "
                    "known=%s)",
                    uid,
                    self.latest_user_id,
                    self.known_user_ids,
                )
            # Drain the per-user write barrier on commit (or
            # failure / exception) so any retrieval scoped to the
            # same ``user_id`` waiting on this write's ``seq_no``
            # is released. ``barrier_seq`` is stamped on the
            # syscall by ``SyscallExecutor`` (task 6); when absent
            # (e.g., a direct call from a test that bypasses the
            # executor), the sentinel ``0`` makes ``release`` a
            # no-op so the fast path stays free.
            barrier_seq = getattr(memory_syscall, "barrier_seq", 0)
            barrier_user_id = memory_note.metadata.get("user_id")
            resp = None
            try:
                try:
                    resp = MemoryResponse(
                        success=True,
                        memory_id=self.provider.add(memory_note),
                    )
                except ProviderError as e:
                    resp = MemoryResponse(success=False, error=str(e))
                logger.info(
                    "[MEM0_DEBUG] add_memory result: "
                    "user_id=%s, success=%s, memory_id=%s, "
                    "error=%s",
                    barrier_user_id,
                    getattr(resp, "success", "?"),
                    getattr(resp, "memory_id", "?"),
                    getattr(resp, "error", None),
                )
                return resp
            finally:
                # ``finally`` guarantees waiters are notified even
                # if the provider raised; failed writes still
                # release waiters so a provider error does not
                # strand retrievals.
                success = bool(
                    resp and getattr(resp, "success", False)
                )
                self.barrier.release(
                    barrier_user_id, barrier_seq, success=success
                )
        
        elif operation_type == "remove_memory":
            found = self._locate_memory(query, memory_syscall.agent_name)
            if found is None or not self._can_write(
                memory_syscall.agent_name, found.metadata
            ):
                return MemoryResponse(
                    success=False, error="Memory not found"
                )
            memory_id = query.params["memory_id"]
            try:
                deleted = self.provider.delete(
                    memory_id, found.metadata.get("user_id") or None
                )
            except ProviderError as e:
                return MemoryResponse(success=False, error=str(e))
            if not deleted:
                return MemoryResponse(
                    success=False, error="Memory not found"
                )
            return MemoryResponse(success=True, memory_id=memory_id)
        
        elif operation_type == "update_memory":
            return self._update_memory(memory_syscall)
        
        elif operation_type == "get_memory":
            found = self._locate_memory(query, memory_syscall.agent_name)
            if found is None or not self._can_read(
                memory_syscall.agent_name, found.metadata
            ):
                # Same answer as a missing id, so a read by id does
                # not reveal that a private memory exists.
                return MemoryResponse(
                    success=False, error="Memory not found"
                )
            return MemoryResponse(
                success=True,
                memory_id=found.memory_id,
                content=found.content,
                metadata=found.metadata,
            )
        
        elif operation_type == "retrieve_memory":
            query.params["agent_name"] = memory_syscall.agent_name
            if not query.params.get("user_id"):
                logger.warning(
                    "retrieve_memory called without request-scoped "
                    "user_id; skipping latest_user_id fallback to "
                    "avoid cross-user contamination (agent=%s)",
                    memory_syscall.agent_name,
                )
            # ``barrier_snapshot`` is stamped on the syscall by
            # ``SyscallExecutor`` at acceptance; the sentinel ``0``
            # (no user_id, or no executor) skips the wait.
            sharing_policy = query.params.get("sharing_policy")
            candidates, diagnostics = self.retrieve_for_agent(
                memory_syscall.agent_name,
                query.params.get("user_id"),
                query.params.get("content", ""),
                k=query.params.get("k", 5),
                include_shared=sharing_policy == "shared",
                sharing_policy=sharing_policy,
                barrier_snapshot=getattr(
                    memory_syscall, "barrier_snapshot", 0
                ),
            )
            logger.info(
                "[MEM0_DEBUG] retrieve_memory result: "
                "user_id=%s, success=%s, result_count=%d",
                query.params.get("user_id"),
                diagnostics["error"] is None,
                len(candidates),
            )
            if diagnostics["error"] is not None:
                return MemoryResponse(
                    success=False, error=diagnostics["error"]
                )
            return MemoryResponse(
                success=True, search_results=candidates
            )

        elif operation_type == "retrieve_memory_raw":
            # The same selection as retrieve_memory, returned as notes.
            from .note import MemoryNote

            sharing_policy = query.params.get("sharing_policy")
            candidates, _ = self.retrieve_for_agent(
                memory_syscall.agent_name,
                query.params.get("user_id"),
                query.params.get("content", ""),
                k=query.params.get("k", 5),
                include_shared=sharing_policy == "shared",
                sharing_policy=sharing_policy,
                barrier_snapshot=getattr(
                    memory_syscall, "barrier_snapshot", 0
                ),
            )
            return [
                MemoryNote(
                    content=row["content"],
                    id=row["memory_id"],
                    keywords=row["keywords"],
                    tags=row["tags"],
                    category=row["category"],
                    context=row["metadata"].get("context", "General"),
                    timestamp=row["timestamp"] or None,
                    metadata=row["metadata"],
                )
                for row in candidates
            ]

        else:
            raise ValueError(f"Invalid operation: {operation_type}")
    
    def _update_memory(self, memory_syscall) -> MemoryResponse:
        """Owner-only update, stamped against the write barrier like a
        write: a retrieval accepted after the update waits for it, so it
        reads the new content. The barrier is released on every path."""
        query = memory_syscall.query
        params = query.params
        barrier_user_id = self._update_user_id(query)
        barrier_seq = getattr(memory_syscall, "barrier_seq", 0)
        success = False
        try:
            found = self._locate_memory(query, memory_syscall.agent_name)
            if found is None or not self._can_write(
                memory_syscall.agent_name, found.metadata
            ):
                return MemoryResponse(
                    success=False, error="Memory not found"
                )
            metadata = {
                key: value
                for key, value in (params.get("metadata") or {}).items()
                if key not in UPDATE_PROTECTED_METADATA
            }
            try:
                updated = self.provider.update(
                    params["memory_id"],
                    found.metadata.get("user_id") or None,
                    params.get("content"),
                    metadata,
                )
            except ProviderError as e:
                return MemoryResponse(success=False, error=str(e))
            if not updated:
                return MemoryResponse(
                    success=False, error="Memory not found"
                )
            success = True
            return MemoryResponse(
                success=True, memory_id=params["memory_id"]
            )
        finally:
            if barrier_user_id:
                self.barrier.release(
                    barrier_user_id, barrier_seq, success=success
                )

    def close(self) -> None:
        """
        Clean up resources.
        
        Delegates to the provider's close method to release any held resources.
        """
        if self.provider:
            self.provider.close()

    def sync_llm_from_query(
        self,
        llms: "list[dict] | None",
    ) -> None:
        """Propagate the agent's runtime LLM selection to the
        memory provider.

        Delegates to the provider's ``sync_llm_from_query`` method
        so that providers with an internal LLM (e.g., Mem0) can use
        the same model as the assistant agent.

        Args:
            llms: The ``LLMQuery.llms`` field.
        """
        if self.provider:
            self.provider.sync_llm_from_query(llms)
