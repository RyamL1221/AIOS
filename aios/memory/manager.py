"""
Memory Manager for the AIOS system.

This module provides the MemoryManager class that serves as the high-level
interface to the memory management system. It uses pluggable memory providers
to enable different storage backends (in-house, Mem0, Zep).
"""
import logging
import os
import time
from collections import OrderedDict
from typing import Optional, Dict, Any, Set, Tuple

from cerebrum.memory.apis import MemoryQuery, MemoryResponse
from cerebrum.utils.usage import tagged

from aios.config.config_manager import config as global_config
from .embedding import EmbeddingConfig
from .pipeline import (
    LIST_TOP_K,
    SHARED_FETCH_FACTOR,  # noqa: F401  (re-exported for callers)
    UPDATE_PROTECTED_METADATA,  # noqa: F401
    IdentityResolver,
    IdentityRules,
    MemoryPipeline,
    PipelineSettings,
    Selector,
    Visibility,
    note_from_request,
)
from .pipeline.barrier import MemoryWriteBarrier, WaitOutcome
from .pipeline.tombstones import TombstoneStore
from .pipeline.selector import commits_synchronously
from .providers import ProviderFactory, MemoryProvider
from .providers.base import Candidate, ProviderError
from .providers.factory import provider_config

logger = logging.getLogger(__name__)


class _KernelIdentity(IdentityResolver):
    """The kernel's one identity registry, shared by every agent: a
    write by any agent registers its user in the manager's registry
    (docs/REPLICATED_LOGIC.md, difference 2)."""

    def __init__(self, manager: "MemoryManager"):
        super().__init__(
            registry=getattr(manager, "_known_user_ids", None),
            logger=logger,
            rules=getattr(manager, "identity_rules", None),
        )
        self._manager = manager

    def register(self, user_id: str) -> None:
        self._manager._register_user_id(user_id)
        logger.info(
            "Registered user_id=%s (latest=%s, known=%s)",
            user_id,
            self._manager.latest_user_id,
            self._manager.known_user_ids,
        )


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
        # The kernel's one identity rule set (memory.identity): every
        # request's user id is canonicalized once, at acceptance
        # (docs/HETEROGENEITY.md). Validated here, at startup.
        self.identity_rules = IdentityRules.from_config(
            memory_config.get("identity")
        )

        barrier_config = memory_config.get("write_barrier", {}) or {}
        self._barrier_config = dict(barrier_config)
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
        # The block's format (Subtask 9d): "compact" (default) or the
        # pre-9d "legacy" kernel block, and what its recency ages count
        # (benchmark v2): "time" (default) or "session". Validated here,
        # at startup.
        _block = PipelineSettings.from_memory_config(memory_config)
        self.block_format = _block.block_format
        self.block_recency = _block.block_recency
        self.block_recency_unit = _block.block_recency_unit
        # Whether a later statement retires the earlier rows of its
        # slot ("off" or "exclude"; docs/DELETION_AND_SUPERSESSION.md).
        self.supersession = _block.supersession
        # The kernel's tombstones (memory.tombstones_path): one sidecar
        # file whichever provider the kernel runs, read on every call,
        # so every per-request pipeline sees every forget. Not a
        # pipeline setting: a replicated store keeps its own. Without a
        # path they live in memory and a restart loses them; the v2
        # pre-flight refuses that.
        path = memory_config.get("tombstones_path")
        self.tombstones_path = os.path.abspath(path) if path else None
        self.tombstones = TombstoneStore(self.tombstones_path)
        if self.tombstones_path is None:
            logger.info(
                "memory.tombstones_path is not set: tombstones are kept "
                "in memory and a restart loses them"
            )
        # Whether the kernel injects and extracts memories: off for the
        # agent-managed (native) conditions (docs/NATIVE_USAGE.md).
        self.auto_inject = bool(memory_config.get("auto_inject", False))
        self.auto_extract = bool(memory_config.get("auto_extract", False))
        # The internal LLM pinned for agent-managed backends (Mem0's
        # extraction in native_mem0); reported, not used by the kernel.
        self.backend_llm = dict(memory_config.get("backend_llm") or {})

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
        """The provider's configuration (``providers.factory
        .provider_config``, shared with the replicated agents)."""
        return provider_config(provider_type, memory_config)

    def _provider_supports_barrier(self) -> bool:
        """Return True for providers that participate in the
        per-user write barrier: those whose writes are not durable when
        ``add`` returns (``MemoryProvider.synchronous_commit`` false,
        which includes Mem0-shaped test doubles)."""
        return not commits_synchronously(self.provider)

    # ------------------------------------------------------------------
    # The memory pipeline library (aios.memory.pipeline)
    # ------------------------------------------------------------------

    def pipeline_settings(self) -> PipelineSettings:
        """The kernel's pipeline settings, as it reports them at
        ``/memory/config`` for the replicated agents to copy."""
        return PipelineSettings(
            relevance_threshold=getattr(self, "relevance_threshold", 0.0),
            max_injected_memories=getattr(
                self, "max_injected_memories", 5
            ),
            max_memory_tokens=getattr(self, "max_memory_tokens", 1500),
            write_barrier=dict(getattr(self, "_barrier_config", {})),
            block_format=getattr(self, "block_format", "compact"),
            block_recency=getattr(self, "block_recency", False),
            block_recency_unit=getattr(self, "block_recency_unit", "time"),
            supersession=getattr(self, "supersession", "off"),
        )

    def memory_pipeline(self) -> MemoryPipeline:
        """The library over what placement gives the kernel: the one
        write barrier and the one identity registry every agent shares.
        Built per call from the current settings."""
        if getattr(self, "_known_user_ids", None) is None:
            self._known_user_ids = OrderedDict()
        return MemoryPipeline(
            self.provider,
            self.pipeline_settings(),
            barrier=getattr(self, "barrier", None),
            resolver=_KernelIdentity(self),
            tombstones=getattr(self, "tombstones", None),
            # The provider's calls count to the user they serve.
            usage_tag=tagged,
        )

    def _resolve_user_id(
        self,
        agent_name: str,
        request_user_id: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve the active end-user for a retrieval
        (``IdentityResolver.resolve``)."""
        return IdentityResolver(logger=logger).resolve(
            agent_name, request_user_id
        )

    def _await_pending_writes(
        self,
        user_id: Optional[str],
        barrier_snapshot: Optional[int] = None,
    ) -> WaitOutcome:
        """Wait for writes accepted before a retrieval of ``user_id``
        (``Selector.await_pending_writes``)."""
        return self.memory_pipeline().selector.await_pending_writes(
            user_id, barrier_snapshot
        )

    def stamp_syscall(self, memory_syscall) -> None:
        """Stamp a memory syscall against the write barrier.

        The only stamping site. It must run before the write can be
        observed as accepted: a write records itself before it is
        enqueued, so any retrieval accepted later sees it pending; a
        retrieval records the high-water mark at acceptance, so later
        writes never delay it. ``add_agentic_memory`` is included
        because this can run before ``execute_request`` rewrites it. An
        update is stamped like a write, so a retrieval accepted after it
        reads the new content. A listing is stamped like a retrieval, so
        it includes a conversation turn still being written. A forget is
        stamped like a write, so a retrieval accepted after it waits for
        it; it waits for the writes accepted before it through its own
        sequence minus one (``MemoryPipeline.forget``).
        """
        query = memory_syscall.query
        operation = query.operation_type
        # Canonical ids before stamping, so the barrier keys of a write
        # and a read for the same user agree.
        self.canonicalize_request(query)
        if operation in ("add_memory", "add_agentic_memory"):
            user_id = query.params.get("metadata", {}).get("user_id")
            if user_id:
                memory_syscall.barrier_seq = self.barrier.acquire(user_id)
        elif operation == "update_memory":
            user_id = self._update_user_id(query)
            if user_id:
                memory_syscall.barrier_seq = self.barrier.acquire(user_id)
        elif operation == "forget_memory":
            user_id = query.params.get("user_id")
            if user_id:
                memory_syscall.barrier_seq = self.barrier.acquire(user_id)
        elif operation in (
            "retrieve_memory", "retrieve_memory_raw", "list_memory",
        ):
            user_id = query.params.get("user_id")
            if user_id:
                memory_syscall.barrier_snapshot = self.barrier.snapshot(
                    user_id
                )

    def canonical_user_id(self, user_id: Optional[str]) -> Optional[str]:
        """``user_id`` under the kernel's identity rules."""
        rules = getattr(self, "identity_rules", None)
        return rules.canonical(user_id) if rules else user_id

    def canonicalize_request(self, query) -> None:
        """Rewrite a memory request's ``user_id`` and
        ``metadata.user_id`` to canonical form, in place. Idempotent:
        runs at acceptance (``stamp_syscall``) and again when the
        request is served, for callers that skip the executor."""
        params = getattr(query, "params", None)
        if not isinstance(params, dict):
            return
        if params.get("user_id"):
            params["user_id"] = self.canonical_user_id(params["user_id"])
        metadata = params.get("metadata")
        if isinstance(metadata, dict) and metadata.get("user_id"):
            metadata["user_id"] = self.canonical_user_id(
                metadata["user_id"]
            )

    @staticmethod
    def _update_user_id(query: MemoryQuery) -> Optional[str]:
        """The user an update is stamped under: the caller's user_id."""
        params = query.params
        return (
            params.get("user_id")
            or (params.get("metadata") or {}).get("user_id")
        )

    _can_write = staticmethod(Visibility.can_write)
    _can_read = staticmethod(Visibility.can_read)
    _merge_and_deduplicate = staticmethod(Selector.merge_and_deduplicate)

    def _locate_memory(
        self, query: MemoryQuery, agent_name: str
    ) -> Optional[Candidate]:
        """Fetch a memory named by id, wherever it is stored
        (``MemoryPipeline.locate``), in the caller's user scope."""
        params = query.params
        user_id = (
            params.get("user_id")
            or (params.get("metadata") or {}).get("user_id")
        )
        return self.memory_pipeline().locate(
            params["memory_id"], user_id, agent_name
        )

    def _fetch_candidates(
        self, scope_user_id: str, query_text: str, top_k: int
    ) -> Tuple[list, Optional[str]]:
        """One provider search (``Selector.fetch``)."""
        return self.memory_pipeline().selector.fetch(
            scope_user_id, query_text, top_k
        )

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
        """Decide which memories an agent sees: the library's selection
        (``MemoryPipeline.retrieve``), over the kernel's shared barrier
        and identity registry.

        The single kernel retrieval path: context injection and SDK
        search both end here. ``barrier_snapshot`` is the high-water
        mark stamped when a syscall was accepted (``None``: take one
        now; ``0``: skip the wait).

        Returns:
            ``(candidates, diagnostics)``. ``diagnostics["error"]`` is
            the provider's error when own retrieval failed, else None;
            ``diagnostics["shared_error"]`` the same for the shared
            fetch, which SDK search does not fail on.
        """
        return self.memory_pipeline().retrieve(
            agent_name, user_id, query_text,
            k=k,
            include_shared=include_shared,
            request_user_id=request_user_id,
            sharing_policy=sharing_policy,
            barrier_snapshot=barrier_snapshot,
        )

    def _analyze_query_to_memory(self, query: MemoryQuery) -> 'MemoryNote':
        """The note a MemoryQuery describes (``note_from_request``)."""
        return note_from_request(query.params)
    
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
            (``retrieve_memory_raw``: a list of ``MemoryNote`` when it
            succeeds). A failure, or an operation no branch serves, is
            answered with ``success`` false, never raised: the
            scheduler answers a syscall only when this returns.

        Raises:
            TypeError: If memory_syscall is not a MemorySyscall
        """
        # Import here to avoid circular dependency
        from aios.syscall.memory import MemorySyscall
        
        if not isinstance(memory_syscall, MemorySyscall):
            raise TypeError(f"Expected MemorySyscall, got {type(memory_syscall)}")
        
        self.canonicalize_request(memory_syscall.query)
        with tagged(self._usage_tag(memory_syscall)):
            return self._address_request(memory_syscall)

    @staticmethod
    def _usage_tag(memory_syscall) -> Optional[str]:
        """The user a memory syscall works for, which its provider's
        LLM and embedding calls count to (``cerebrum.utils.usage``)."""
        params = memory_syscall.query.params or {}
        return (
            params.get("user_id")
            or (params.get("metadata") or {}).get("user_id")
            or memory_syscall.agent_name
        )

    def _address_request(self, memory_syscall) -> MemoryResponse:
        query = memory_syscall.query
        self.canonicalize_request(query)
        operation_type = query.operation_type
        
        if operation_type == "add_memory":
            try:
                memory_note = self._analyze_query_to_memory(query)
            except Exception as e:
                # The write never reaches the library, which would release
                # the sequence stamped at acceptance: release it here, or
                # every later retrieval of the user waits out the
                # barrier's timeout.
                self._release_stamp(
                    memory_syscall,
                    (query.params.get("metadata") or {}).get("user_id"),
                )
                return self._failure("add_memory", memory_syscall, e)
            metadata = memory_note.metadata or {}
            logger.info(
                "add_memory: agent=%s, uid_from_metadata=%s, "
                "latest_user_id=%s, known=%s",
                memory_syscall.agent_name,
                metadata.get("user_id"),
                self.latest_user_id,
                self.known_user_ids,
            )
            # ``barrier_seq`` is stamped on the syscall when it is
            # accepted (``stamp_syscall``); the sentinel ``0`` (a direct
            # call that bypasses the executor) makes the release a no-op.
            # The library fills the required metadata, registers the
            # user and releases the barrier even if the provider raises.
            # The reply's metadata says what the write swept, retired and
            # lifted, and whether it was suppressed (Amendment 4).
            outcome: Dict[str, Any] = {}
            try:
                memory_id = self.memory_pipeline().write(
                    memory_syscall.agent_name, None, memory_note,
                    barrier_seq=getattr(memory_syscall, "barrier_seq", 0),
                    outcome=outcome,
                )
                resp = MemoryResponse(
                    success=True, memory_id=memory_id, metadata=outcome,
                )
            except Exception as e:
                resp = self._failure("add_memory", memory_syscall, e)
            logger.info(
                "[MEM0_DEBUG] add_memory result: "
                "user_id=%s, success=%s, memory_id=%s, "
                "error=%s",
                memory_note.metadata.get("user_id"),
                resp.success,
                resp.memory_id,
                resp.error,
            )
            return resp
        
        elif operation_type == "remove_memory":
            return self._remove_memory(memory_syscall)

        elif operation_type == "list_memory":
            return self._list_memory(memory_syscall)

        elif operation_type == "update_memory":
            return self._update_memory(memory_syscall)

        elif operation_type == "forget_memory":
            return self._forget_memory(memory_syscall)

        elif operation_type == "get_memory":
            params = query.params
            try:
                found = self.memory_pipeline().read(
                    memory_syscall.agent_name,
                    self._caller_user_id(query),
                    params["memory_id"],
                )
            except Exception as e:
                return self._failure("get_memory", memory_syscall, e)
            if found is None:
                # Same answer for a missing id, another agent's private
                # memory and one that carries a forgotten value, so a
                # read by id reveals none of them.
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
            try:
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
            except Exception as e:
                return self._failure("retrieve_memory", memory_syscall, e)
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
            # The same selection as retrieve_memory, returned as notes;
            # a failure answers success false, as retrieve_memory's does
            # (a failed fetch is never an empty store).
            from .note import MemoryNote

            sharing_policy = query.params.get("sharing_policy")
            try:
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
            except Exception as e:
                return self._failure(
                    "retrieve_memory_raw", memory_syscall, e
                )
            if diagnostics["error"] is not None:
                return MemoryResponse(
                    success=False, error=diagnostics["error"]
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
            # Answered, not raised: the scheduler sets a syscall's event
            # only when its handler returns.
            logger.warning(
                "address_request: invalid memory operation %r (agent=%s)",
                operation_type, memory_syscall.agent_name,
            )
            return MemoryResponse(
                success=False,
                error=f"Invalid operation: {operation_type}",
            )
    
    def _update_memory(self, memory_syscall) -> MemoryResponse:
        """Owner-only update (``MemoryPipeline.update``), stamped
        against the write barrier like a write: a retrieval accepted
        after the update waits for it, so it reads the new content."""
        params = memory_syscall.query.params
        outcome: Dict[str, Any] = {}
        user_id = self._update_user_id(memory_syscall.query)
        if not params.get("memory_id"):
            # Refused before the library runs, which would release the
            # sequence stamped at acceptance: release it here.
            self._release_stamp(memory_syscall, user_id)
            return MemoryResponse(
                success=False, error="update_memory needs params.memory_id"
            )
        try:
            updated = self.memory_pipeline().update(
                memory_syscall.agent_name,
                user_id,
                params["memory_id"],
                params.get("content"),
                params.get("metadata"),
                barrier_seq=getattr(memory_syscall, "barrier_seq", 0),
                outcome=outcome,
            )
        except Exception as e:
            return self._failure("update_memory", memory_syscall, e)
        if not updated:
            return MemoryResponse(success=False, error="Memory not found")
        return MemoryResponse(
            success=True, memory_id=params["memory_id"], metadata=outcome,
        )

    # The by-id and listing operations below answer every failure with a
    # response: an exception would leave the FIFO scheduler's syscall
    # unanswered, and its caller (and the HTTP server) waiting forever.

    @staticmethod
    def _caller_user_id(query: MemoryQuery) -> Optional[str]:
        """The user a request names: ``params.user_id``, else
        ``metadata.user_id``."""
        params = query.params or {}
        return (
            params.get("user_id")
            or (params.get("metadata") or {}).get("user_id")
        )

    def _release_stamp(self, memory_syscall, user_id: Optional[str]) -> None:
        """Release the barrier sequence stamped on a write syscall that
        failed before reaching the library (which releases its own)."""
        seq = getattr(memory_syscall, "barrier_seq", 0)
        barrier = getattr(self, "barrier", None)
        if seq and user_id and barrier is not None:
            barrier.release(user_id, seq, success=False)

    @staticmethod
    def _failure(
        operation: str, memory_syscall, error: Exception
    ) -> MemoryResponse:
        """A failed operation as a response, logged with its cause."""
        logger.warning(
            "%s failed for agent=%s: %s",
            operation,
            memory_syscall.agent_name,
            error,
            exc_info=not isinstance(error, ProviderError),
        )
        if isinstance(error, ProviderError):
            return MemoryResponse(success=False, error=str(error))
        return MemoryResponse(
            success=False, error=f"{type(error).__name__}: {error}"
        )

    def _remove_memory(self, memory_syscall) -> MemoryResponse:
        """Owner-only delete (``MemoryPipeline.delete``) in the caller's
        user scope. A memory that is missing, or not the agent's, gets
        the same "Memory not found"."""
        query = memory_syscall.query
        memory_id = (query.params or {}).get("memory_id")
        try:
            deleted = self.memory_pipeline().delete(
                memory_syscall.agent_name,
                self._caller_user_id(query),
                memory_id,
            )
        except Exception as e:
            return self._failure("remove_memory", memory_syscall, e)
        if not deleted:
            return MemoryResponse(success=False, error="Memory not found")
        return MemoryResponse(success=True, memory_id=memory_id)

    def _list_memory(self, memory_syscall) -> MemoryResponse:
        """Owner-only listing (``MemoryPipeline.list_own``): the rows the
        agent owns for ``params.user_id``, unranked, in
        ``search_results``. ``params.k`` caps them; by default every row
        is listed. Waits on the write barrier like a retrieval: a
        listing right after the last probe would otherwise miss that
        probe's conversation turn, written in the background."""
        query = memory_syscall.query
        params = query.params or {}
        try:
            rows, withheld = self.memory_pipeline().list_own_report(
                memory_syscall.agent_name,
                params.get("user_id"),
                top_k=params.get("k"),
                # Stamped at acceptance (``stamp_syscall``); the
                # sentinel ``0`` (no user_id, or no executor) skips the
                # wait.
                barrier_snapshot=getattr(
                    memory_syscall, "barrier_snapshot", 0
                ),
            )
        except Exception as e:
            return self._failure("list_memory", memory_syscall, e)
        logger.info(
            "list_memory: agent=%s, user_id=%s, rows=%d, withheld=%d",
            memory_syscall.agent_name,
            params.get("user_id"),
            len(rows),
            len(withheld),
        )
        # A row that carries a forgotten value is never listed; its id
        # is reported in ``metadata.withheld`` for the caller. The
        # benchmark's audit reads the raw store instead (GET
        # /memory/audit; Amendment 4, "The audit reads the store").
        return MemoryResponse(
            success=True, search_results=rows,
            metadata={"withheld": withheld},
        )

    def audit_rows(self, user_id: str) -> Dict[str, Any]:
        """Every row the store holds for ``user_id``, of every agent,
        unfiltered: no visibility rule and no tombstone guard
        (``GET /memory/audit``). The benchmark harness's audit of what a
        forget left in the store reads this, so a carrier the forget
        missed shows with its text, whatever the guard hides from the
        agents (docs/DELETION_AND_SUPERSESSION.md, "The audit reads the
        store"). Not a retrieval path: no agent and no SDK call uses it.
        Waits for the user's writes accepted before it, as a listing
        does. ``at_limit``: the listing reached ``LIST_TOP_K`` and may
        be partial."""
        uid = self.canonical_user_id(user_id)
        self._await_pending_writes(uid)
        with tagged(uid):
            found = self.provider.list(uid, LIST_TOP_K)
        return {
            "user_id": uid,
            "rows": [candidate.to_row() for candidate in found],
            "at_limit": len(found) >= LIST_TOP_K,
        }

    def _forget_memory(self, memory_syscall) -> MemoryResponse:
        """A user-scoped forget (``MemoryPipeline.forget``): the user's
        request, made by any agent that serves the user
        (docs/DELETION_AND_SUPERSESSION.md). Stamped against the barrier
        like a write. The report is the reply's ``metadata``: the ids
        deleted with their owners and reasons, the value and form
        counts, and the history scrub's counts; never another agent's
        text."""
        params = memory_syscall.query.params or {}
        user_id = params.get("user_id")
        fact_key = params.get("fact_key")
        # The library refuses a missing user or slot inside its barrier
        # hold, so the sequence stamped at acceptance is released.
        try:
            report = self.memory_pipeline().forget(
                memory_syscall.agent_name, user_id, fact_key,
                barrier_seq=getattr(memory_syscall, "barrier_seq", 0),
            )
        except Exception as e:
            return self._failure("forget_memory", memory_syscall, e)
        logger.info(
            "forget_memory: agent=%s, user_id=%s, fact_key=%s, "
            "values=%d, deleted=%d",
            memory_syscall.agent_name, user_id, fact_key,
            report["values_count"], len(report["deleted"]),
        )
        return MemoryResponse(success=True, metadata=report)

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
