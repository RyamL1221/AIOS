"""
Memory Manager for the AIOS system.

This module provides the MemoryManager class that serves as the high-level
interface to the memory management system. It uses pluggable memory providers
to enable different storage backends (in-house, Mem0, Zep).
"""
import logging
import time
from collections import OrderedDict
from typing import Optional, Dict, Any, Set

from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from aios.config.config_manager import config as global_config
from .providers import ProviderFactory, MemoryProvider
from .providers.base import _apply_sharing_filter
from .providers.in_house import InHouseProvider
from .providers.zep import ZepProvider
from .write_barrier import MemoryWriteBarrier, WaitOutcome

logger = logging.getLogger(__name__)

# Shared retrieval over-fetches because a provider applies k before the
# kernel's visibility filter removes other agents' private memories.
SHARED_FETCH_FACTOR = 4


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

        # Selection settings for retrieve_for_agent.
        self.relevance_threshold = memory_config.get(
            "relevance_threshold", 0.5
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
            provider_type: The type of provider ("in-house", "mem0", "zep")
            memory_config: The memory configuration section from config
            storage_config: The storage configuration section from config
        
        Returns:
            Dictionary containing provider-specific configuration
        """
        if provider_type == "in-house":
            return storage_config
        elif provider_type == "mem0":
            return memory_config.get("mem0", {})
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
        because this can run before ``execute_request`` rewrites it.
        """
        query = memory_syscall.query
        operation = query.operation_type
        if operation in ("add_memory", "add_agentic_memory"):
            user_id = query.params.get("metadata", {}).get("user_id")
            if user_id:
                memory_syscall.barrier_seq = self.barrier.acquire(user_id)
        elif operation in ("retrieve_memory", "retrieve_memory_raw"):
            user_id = query.params.get("user_id")
            if user_id:
                memory_syscall.barrier_snapshot = self.barrier.snapshot(
                    user_id
                )

    @staticmethod
    def _can_write(agent_name: str, metadata: Optional[dict]) -> bool:
        """Only the owner may update or delete a memory, shared or not.
        Fails closed: a memory with no owner is not writable."""
        return (metadata or {}).get("owner_agent") == agent_name

    def _locate_memory(
        self, query: MemoryQuery, agent_name: str
    ) -> MemoryResponse:
        """Fetch a memory named by id, wherever it is stored.

        Mem0 keeps one collection per user, so an id alone cannot find
        a row. Uses the caller's user_id when given; otherwise tries the
        agent's own scope, then the provider's default.
        """
        params = query.params
        user_id = (
            params.get("user_id")
            or (params.get("metadata") or {}).get("user_id")
        )
        scopes = [user_id] if user_id else [agent_name, None]
        response = MemoryResponse(success=False, error="Memory not found")
        for scope in scopes:
            response = self.provider.get_memory_for_user(
                params["memory_id"], scope
            )
            if response.success:
                break
        return response

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
        self,
        agent_name: str,
        provider_user_id: Optional[str],
        query_text: str,
        top_k: int,
        sharing_policy: Optional[str] = None,
    ) -> MemoryResponse:
        """Issue one provider retrieval with an explicit ``top_k``."""
        params: Dict[str, Any] = {
            "content": query_text,
            "k": top_k,
            "top_k": top_k,
            "agent_name": agent_name,
        }
        if provider_user_id is not None:
            params["user_id"] = provider_user_id
        if sharing_policy is not None:
            params["sharing_policy"] = sharing_policy
        return self.provider.retrieve_memory(
            MemoryQuery(operation_type="retrieve_memory", params=params)
        )

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

        # With no user_id at all, the provider applies its own default
        # scope; the kernel never invents one (see _resolve_user_id).
        response = self._fetch_candidates(
            agent_name,
            resolved_user_id or user_id,
            query_text,
            top_k_used["own"],
        )
        if not response.success:
            diagnostics["error"] = response.error
        own = list(response.search_results or [])

        shared: list = []
        if fetch_shared:
            try:
                response = self._fetch_candidates(
                    agent_name,
                    scope_user_id,
                    query_text,
                    top_k_used["shared"],
                    sharing_policy="shared",
                )
                if response.success:
                    shared = list(response.search_results or [])
            except Exception:
                logger.debug(
                    "Shared memory retrieval failed for user_id=%s",
                    scope_user_id,
                    exc_info=True,
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

        # Applied here even when the provider already filtered, so a
        # provider or caller cannot weaken it.
        policy = None if sharing_policy == "shared" else sharing_policy

        def visible(rows: list) -> list:
            return _apply_sharing_filter(
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

        # Mem0's get_all path returns no scores: the threshold cannot
        # apply there and scores_present records that.
        scores_present = any(
            mem.get("score") is not None for mem in results
        )
        diagnostics["scores_present"] = scores_present
        if scores_present:
            threshold = getattr(self, "relevance_threshold", 0.5)
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
                resp = self.provider.add_memory(memory_note)
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
            if not found.success or not self._can_write(
                memory_syscall.agent_name, found.metadata
            ):
                return MemoryResponse(
                    success=False, error="Memory not found"
                )
            return self.provider.remove_memory_for_user(
                query.params["memory_id"],
                found.metadata.get("user_id") or None,
            )
        
        elif operation_type == "update_memory":
            found = self._locate_memory(query, memory_syscall.agent_name)
            if not found.success or not self._can_write(
                memory_syscall.agent_name, found.metadata
            ):
                return MemoryResponse(
                    success=False, error="Memory not found"
                )
            memory_note = self._analyze_query_to_memory(query)
            # Route to the collection the memory was found in.
            stored_user_id = found.metadata.get("user_id")
            if stored_user_id:
                if memory_note.metadata is None:
                    memory_note.metadata = {}
                memory_note.metadata["user_id"] = stored_user_id
            return self.provider.update_memory(memory_note)
        
        elif operation_type == "get_memory":
            resp = self._locate_memory(query, memory_syscall.agent_name)
            if resp.success and not self._can_read(
                memory_syscall.agent_name, resp.metadata
            ):
                # Same answer as a missing id, so a read by id does
                # not reveal that a private memory exists.
                return MemoryResponse(
                    success=False, error="Memory not found"
                )
            return resp
        
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
            query.params["agent_name"] = memory_syscall.agent_name
            if not query.params.get("user_id"):
                logger.warning(
                    "retrieve_memory_raw called without request-scoped "
                    "user_id; skipping latest_user_id fallback to "
                    "avoid cross-user contamination (agent=%s)",
                    memory_syscall.agent_name,
                )
            # See ``retrieve_memory`` above -- same barrier wait
            # contract for the raw-retrieval path, including the
            # provider-type guard from task 5.5.
            barrier_snapshot = getattr(
                memory_syscall, "barrier_snapshot", 0
            )
            barrier_user_id = query.params.get("user_id")
            if (
                barrier_snapshot
                and barrier_user_id
                and self._provider_supports_barrier()
            ):
                self.barrier.wait_until_drained(
                    barrier_user_id, barrier_snapshot
                )
            return self.provider.retrieve_memory_raw(query)
        
        else:
            raise ValueError(f"Invalid operation: {operation_type}")
    
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
