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
from .providers.in_house import InHouseProvider
from .providers.zep import ZepProvider
from .write_barrier import MemoryWriteBarrier

logger = logging.getLogger(__name__)


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

        # Adaptive threshold policy (LinUCB bandits). Off by default.
        # When disabled we do NOT import or instantiate PolicyManager
        # so the frozen-baseline add/retrieve paths are byte-for-byte
        # unchanged and carry zero policy overhead. When enabled we
        # lazily import and construct the manager here (one-time cost
        # at MemoryManager construction, not on the hot path).
        adaptive_config = (
            memory_config.get("adaptive_policy", {}) or {}
        )
        self._adaptive_enabled: bool = bool(
            adaptive_config.get("enabled", False)
        )
        # The LLM model the agent is currently running. Populated by
        # sync_llm_from_query on chat flows; used only as the bandit
        # context when adaptive policy is enabled. Defaults to
        # "unknown" (a valid one-hot "other" bucket in the policy).
        self._latest_llm_core: str = "unknown"
        # Records adaptive decisions pending a reward, keyed by
        # memory_id. Each value is a LIST of
        # ``(bandit_name, arm_index, context_vector)`` tuples: a single
        # memory_id can be touched by multiple bandits (novelty at add
        # time; similarity + redundancy at retrieve time), so
        # report_reward must be able to update every decision that
        # touched it. In-memory only (v1); entries are removed once a
        # reward consumes them (see report_reward).
        self._pending_reward_decisions: Dict[str, list] = {}
        self.policy: Optional[Any] = None
        # Per-trial JSONL logger. Inert unless a trial_log path is
        # configured under memory.adaptive_policy.trial_log (so the
        # frozen baseline and unconfigured runs write nothing).
        self.policy_logger: Optional[Any] = None
        if self._adaptive_enabled:
            from aios.memory.policy import PolicyManager
            from aios.memory.policy_log import PolicyTrialLogger
            alpha = float(adaptive_config.get("alpha", 1.0))
            self.policy = PolicyManager(alpha=alpha)
            self.policy_logger = PolicyTrialLogger.from_config(
                adaptive_config
            )
            logger.info(
                "Adaptive threshold policy ENABLED (alpha=%.3f, "
                "trial_log=%s)",
                alpha,
                getattr(self.policy_logger, "path", None),
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
    
    def _candidate_max_similarity(
        self, content: str, user_id: Optional[str]
    ) -> float:
        """Return the max similarity of *content* to existing memories.

        Uses the provider's own semantic search (which exposes a
        per-result ``similarity`` field, added in the retrieval-score
        subtask). The candidate's novelty is ``1 - max_similarity``;
        the gate compares ``max_similarity`` against the bandit's
        threshold. Returns ``0.0`` when there are no existing memories
        or no similarity is available (i.e. treat as maximally novel).

        This is a read-only probe; it does not write or mutate state.

        Args:
            content: The candidate memory content.
            user_id: The scope for the search.

        Returns:
            The highest similarity in ``[?, 1]`` among existing
            memories, or ``0.0`` if none.
        """
        from cerebrum.memory.apis import MemoryQuery

        probe = MemoryQuery(
            operation_type="retrieve_memory",
            params={"content": content, "k": 5},
        )
        if user_id:
            probe.params["user_id"] = user_id
        try:
            resp = self.provider.retrieve_memory(probe)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(
                "novelty gate: similarity probe failed (%s); "
                "treating candidate as novel",
                e,
            )
            return 0.0

        results = getattr(resp, "search_results", None) or []
        sims = [
            r.get("similarity")
            for r in results
            if isinstance(r, dict) and r.get("similarity") is not None
        ]
        if not sims:
            return 0.0
        return float(max(sims))

    def _record_decision(self, memory_id: str, decision) -> None:
        """Append an adaptive decision tuple for *memory_id*.

        A decision is ``(bandit_name, arm_index, context_vector,
        trial_id)``. Multiple decisions can attach to one memory_id
        (e.g. a novelty decision at add time, then similarity +
        redundancy decisions at retrieve time). ``report_reward``
        replays and clears all of them.
        """
        self._pending_reward_decisions.setdefault(
            memory_id, []
        ).append(decision)

    @staticmethod
    def _extract_trial_id(query) -> Optional[str]:
        """Read the benchmark trial id from a query's metadata.

        Looks in ``query.params["trial_id"]`` and
        ``query.params["metadata"]["trial_id"]``. Returns ``None`` when
        absent. This is the join key to the external benchmark's
        per-trial JSON logs; we never synthesize one.
        """
        params = getattr(query, "params", {}) or {}
        if params.get("trial_id"):
            return str(params["trial_id"])
        meta = params.get("metadata", {}) or {}
        if meta.get("trial_id"):
            return str(meta["trial_id"])
        return None

    def _novelty_gate_admits(
        self, memory_note, user_id: Optional[str], query=None
    ) -> "tuple[bool, Any]":
        """Decide whether to admit *memory_note* via the bandit.

        Consults the ``novelty_threshold`` bandit for a threshold given
        the current context ``(llm_core, task_type)``, then compares the
        candidate's max similarity to existing memories against it:
        admit iff ``max_similarity < threshold`` (i.e. the candidate is
        novel enough).

        Only called when ``self._adaptive_enabled`` is True.

        Args:
            memory_note: The candidate note (has ``.content`` and
                ``.metadata``).
            user_id: Scope for the similarity probe.
            query: The originating MemoryQuery (for trial_id logging).

        Returns:
            Tuple ``(admit, decision)`` where ``decision`` is
            ``(bandit_name, arm_index, context_vector, trial_id)`` to be
            recorded against the written memory_id for later reward
            attribution.
        """
        task_type = (
            (memory_note.metadata or {}).get("memory_type") or ""
        )
        llm_core = self._latest_llm_core
        threshold, arm_index, context = self.policy.select_threshold(
            "novelty_threshold", llm_core, task_type
        )
        trial_id = self._extract_trial_id(query)
        if getattr(self, "policy_logger", None):
            self.policy_logger.log_select(
                trial_id, "novelty_threshold", "novelty",
                threshold, arm_index, llm_core, task_type, context,
            )
        max_sim = self._candidate_max_similarity(
            memory_note.content, user_id
        )
        admit = max_sim < threshold
        logger.info(
            "novelty gate: llm=%s task=%s threshold=%.3f "
            "max_sim=%.3f -> admit=%s",
            llm_core,
            task_type,
            threshold,
            max_sim,
            admit,
        )
        decision = (
            "novelty_threshold", arm_index, context, trial_id
        )
        return admit, decision

    def _retrieval_context(self, query) -> "tuple[str, str]":
        """Return the ``(llm_core, task_type)`` context for a
        retrieval decision.

        ``llm_core`` is the last model synced via
        ``sync_llm_from_query`` (defaulting to ``"unknown"``).
        ``task_type`` is taken from ``query.params`` metadata's
        ``memory_type`` when present, else "".
        """
        llm_core = getattr(self, "_latest_llm_core", "unknown")
        params = getattr(query, "params", {}) or {}
        meta = params.get("metadata", {}) or {}
        task_type = (
            params.get("memory_type")
            or meta.get("memory_type")
            or ""
        )
        return llm_core, task_type

    @staticmethod
    def _pairwise_cosine(a: str, b: str) -> float:
        """Cosine similarity between two texts, in [0, 1]-ish.

        Uses the same SentenceTransformer family as the in-house
        retriever. The model is loaded lazily and cached on the class
        so the redundancy check adds no import/startup cost when the
        adaptive policy is disabled. Returns 0.0 on any failure (treat
        as non-redundant / keep both).
        """
        try:
            model = MemoryManager._get_redundancy_model()
            import numpy as _np
            embs = model.encode([a, b])
            v1, v2 = embs[0], embs[1]
            denom = (
                float(_np.linalg.norm(v1))
                * float(_np.linalg.norm(v2))
            )
            if denom == 0.0:
                return 0.0
            return float(_np.dot(v1, v2) / denom)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(
                "redundancy pairwise sim failed (%s); "
                "treating as non-redundant",
                e,
            )
            return 0.0

    @classmethod
    def _get_redundancy_model(cls):
        """Lazily construct and cache the redundancy embedding model.

        Loaded only when the adaptive policy's redundancy filter runs,
        so the frozen baseline never pays for it.
        """
        model = getattr(cls, "_redundancy_model", None)
        if model is None:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            cls._redundancy_model = model
        return model

    def _apply_retrieval_policy(
        self, search_results: list, query
    ) -> list:
        """Filter retrieval results via the similarity + redundancy
        bandits, and record per-memory decisions for reward.

        Two sequential gates (only called when adaptive is enabled):

        1. **similarity_threshold** — drop any result whose
           ``similarity`` to the query is *below* the bandit's chosen
           threshold (not relevant enough). Results with no similarity
           value are kept (fail-open, mirroring the ContextInjector's
           relevance handling).
        2. **redundancy_threshold** — walk the surviving results in
           their existing (relevance-ranked) order and drop any whose
           pairwise similarity to an already-kept result *exceeds* the
           bandit's chosen threshold (near-duplicate). The earlier
           (higher-ranked) result is kept.

        Ordering of survivors is preserved. Each surviving memory_id
        records both the similarity and redundancy decisions so
        report_reward can update both bandits.

        Args:
            search_results: The provider's result dicts (each may have
                ``content``, ``memory_id``/``id``, ``similarity``).
            query: The MemoryQuery (for context + user scope).

        Returns:
            The filtered list of result dicts (subset, same order).
        """
        if not search_results:
            return search_results

        llm_core, task_type = self._retrieval_context(query)
        trial_id = self._extract_trial_id(query)

        # --- Gate 1: similarity threshold ---
        sim_threshold, sim_arm, sim_ctx = (
            self.policy.select_threshold(
                "similarity_threshold", llm_core, task_type
            )
        )
        if getattr(self, "policy_logger", None):
            self.policy_logger.log_select(
                trial_id, "similarity_threshold", "similarity",
                sim_threshold, sim_arm, llm_core, task_type, sim_ctx,
            )
        kept = []
        for r in search_results:
            sim = r.get("similarity") if isinstance(r, dict) else None
            if sim is None or float(sim) >= sim_threshold:
                kept.append(r)
        logger.info(
            "retrieve gate: similarity_threshold=%.3f kept %d/%d",
            sim_threshold,
            len(kept),
            len(search_results),
        )

        # --- Gate 2: redundancy threshold ---
        red_threshold, red_arm, red_ctx = (
            self.policy.select_threshold(
                "redundancy_threshold", llm_core, task_type
            )
        )
        if getattr(self, "policy_logger", None):
            self.policy_logger.log_select(
                trial_id, "redundancy_threshold", "redundancy",
                red_threshold, red_arm, llm_core, task_type, red_ctx,
            )
        deduped = []
        for r in kept:
            content = (
                r.get("content", "") if isinstance(r, dict) else ""
            )
            is_redundant = False
            for existing in deduped:
                ex_content = (
                    existing.get("content", "")
                    if isinstance(existing, dict)
                    else ""
                )
                if (
                    content
                    and ex_content
                    and self._pairwise_cosine(content, ex_content)
                    > red_threshold
                ):
                    is_redundant = True
                    break
            if not is_redundant:
                deduped.append(r)
        logger.info(
            "retrieve gate: redundancy_threshold=%.3f kept %d/%d",
            red_threshold,
            len(deduped),
            len(kept),
        )

        # --- Record decisions for surviving memories ---
        for r in deduped:
            mem_id = None
            if isinstance(r, dict):
                mem_id = r.get("memory_id") or r.get("id")
            if not mem_id:
                continue
            self._record_decision(
                mem_id,
                ("similarity_threshold", sim_arm, sim_ctx, trial_id),
            )
            self._record_decision(
                mem_id,
                ("redundancy_threshold", red_arm, red_ctx, trial_id),
            )

        return deduped

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
        
        if operation_type == "report_reward":
            # Reverse-direction syscall: a completed trial's judge
            # reward flowing back into the kernel. Delegates to the
            # stub handler (bandit routing arrives in a later
            # subtask). Fields come directly off the ReportRewardQuery
            # schema (not query.params, unlike MemoryQuery).
            from aios.memory.schemas import ReportRewardResponse
            try:
                self.report_reward(
                    query.memory_ids_involved,
                    query.reward_value,
                    query.trial_metadata,
                )
                return ReportRewardResponse(success=True)
            except Exception as e:  # pragma: no cover - defensive
                return ReportRewardResponse(
                    success=False, error=str(e)
                )
        
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

            # Adaptive novelty gate (opt-in). When enabled, the
            # novelty-threshold bandit decides how novel a candidate
            # must be to be admitted. When disabled, this block is
            # skipped entirely and the write proceeds unconditionally
            # exactly as before (frozen baseline).
            novelty_decision = None
            # ``getattr`` default keeps managers constructed via
            # ``__new__`` (e.g. tests that bypass ``__init__``) on the
            # frozen baseline instead of raising — flag-off is the safe
            # default in every construction path.
            if getattr(self, "_adaptive_enabled", False):
                admit, novelty_decision = self._novelty_gate_admits(
                    memory_note, barrier_user_id, query
                )
                if not admit:
                    # Rejected as not novel enough. Do NOT write, but
                    # release the barrier so any retrieval waiting on
                    # this write's seq_no is not stranded. Return a
                    # success response with no memory_id (nothing was
                    # persisted).
                    self.barrier.release(
                        barrier_user_id, barrier_seq, success=True
                    )
                    logger.info(
                        "add_memory: novelty gate REJECTED "
                        "candidate (user_id=%s); not written",
                        barrier_user_id,
                    )
                    return MemoryResponse(
                        success=True, memory_id=None
                    )

            resp = None
            try:
                with open("/tmp/per_user_proof.txt", "a") as _f:
                    _f.write(
                        f"provider type={type(self.provider).__name__} "
                        f"module={type(self.provider).__module__}\n"
                    )
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
                # Record the adaptive decision against the written
                # memory_id so a future report_reward can attribute
                # the reward to the exact (bandit, arm, context).
                if (
                    novelty_decision is not None
                    and resp is not None
                    and getattr(resp, "success", False)
                ):
                    mem_id = getattr(resp, "memory_id", None)
                    if mem_id:
                        self._record_decision(
                            mem_id, novelty_decision
                        )
                        logger.debug(
                            "Recorded novelty decision for "
                            "memory_id=%s: %s",
                            mem_id,
                            novelty_decision,
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
            return self.provider.remove_memory(query.params["memory_id"])
        
        elif operation_type == "update_memory":
            memory_note = self._analyze_query_to_memory(query)
            return self.provider.update_memory(memory_note)
        
        elif operation_type == "get_memory":
            return self.provider.get_memory(query.params["memory_id"])
        
        elif operation_type == "retrieve_memory":
            query.params["agent_name"] = memory_syscall.agent_name
            if not query.params.get("user_id"):
                logger.warning(
                    "retrieve_memory called without request-scoped "
                    "user_id; skipping latest_user_id fallback to "
                    "avoid cross-user contamination (agent=%s)",
                    memory_syscall.agent_name,
                )
            # Wait for any accepted-but-uncommitted ``create_memory``
            # writes scoped to the same ``user_id`` and stamped at or
            # below ``barrier_snapshot`` to drain before serving this
            # retrieval. ``barrier_snapshot`` is stamped on the syscall
            # by ``SyscallExecutor`` (task 6); when absent (sentinel
            # ``0``) or when no ``user_id`` was supplied, skip the
            # wait entirely so the fast path stays free.
            # Provider-type guard (task 5.5): InHouseProvider and
            # ZepProvider commit synchronously and MUST NOT consult
            # the barrier (Clause 3.5).
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
            resp = self.provider.retrieve_memory(query)
            logger.info(
                "[MEM0_DEBUG] retrieve_memory result: "
                "user_id=%s, success=%s, result_count=%d",
                query.params.get("user_id"),
                getattr(resp, "success", "?"),
                len(getattr(resp, "search_results", None) or []),
            )
            # Adaptive retrieval gates (opt-in). When enabled, filter
            # results via the similarity + redundancy bandits before
            # returning. When disabled, this block is skipped and the
            # provider's results are returned unchanged (frozen
            # baseline). Only applied to successful responses that
            # carry search_results.
            if (
                getattr(self, "_adaptive_enabled", False)
                and getattr(resp, "success", False)
                and getattr(resp, "search_results", None)
            ):
                resp.search_results = self._apply_retrieval_policy(
                    resp.search_results, query
                )
            return resp
        
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
        # Capture the primary model name as the adaptive-policy
        # bandit context (only when the policy is enabled — otherwise
        # this is a no-op and the frozen path is unchanged).
        if getattr(self, "_adaptive_enabled", False) and llms:
            primary = llms[0] if isinstance(llms, list) else None
            name = (primary or {}).get("name") if primary else None
            if name:
                self._latest_llm_core = name
        if self.provider:
            self.provider.sync_llm_from_query(llms)

    def report_reward(
        self,
        memory_ids_involved: list,
        reward_value: float,
        trial_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Handle a completed trial's judge reward.

        This is the kernel-side entry point for the ``report_reward``
        memory syscall — the reverse-direction flow that lets a
        finished trial's reward propagate back into the kernel so the
        learned policy bandits (novelty-threshold, similarity,
        redundancy-filter) can update.

        For each memory_id in ``memory_ids_involved`` it replays every
        recorded ``(bandit_name, arm_index, context_vector)`` decision
        (from ``_pending_reward_decisions``) into
        ``PolicyManager.update`` using naive equal-credit assignment:
        the full ``reward_value`` is applied to each distinct bandit
        decision that touched the memory (v1 attribution rule — the
        reward is *not* split, since each bandit's decision is
        independent). Consumed entries are removed afterward so the
        pending map does not grow unbounded.

        No-ops safely when the adaptive policy is disabled or no
        decisions were recorded for the given memory_ids. Never raises
        on well-formed input.

        Args:
            memory_ids_involved: IDs of the memories that contributed
                to the trial (the arms whose reward is being reported).
            reward_value: Scalar judge reward for the trial.
            trial_metadata: Arbitrary per-trial context. Defaults to an
                empty dict when omitted.
        """
        trial_metadata = trial_metadata or {}
        logger.info(
            "report_reward: memory_ids_involved=%s, reward_value=%s, "
            "trial_metadata=%s",
            memory_ids_involved,
            reward_value,
            trial_metadata,
        )

        # Only route into the bandits when the adaptive policy is
        # active. When disabled there is nothing to update and
        # _pending_reward_decisions is empty (fast/no-op path).
        if not getattr(self, "_adaptive_enabled", False):
            return
        if self.policy is None:
            return

        updates = 0
        for memory_id in memory_ids_involved or []:
            decisions = self._pending_reward_decisions.pop(
                memory_id, None
            )
            if not decisions:
                continue
            for decision in decisions:
                # Decisions are 4-tuples
                # (bandit_name, arm_index, context_vector, trial_id).
                bandit_name, arm_index, context_vector = decision[:3]
                decision_trial_id = (
                    decision[3] if len(decision) > 3 else None
                )
                try:
                    self.policy.update(
                        bandit_name,
                        arm_index,
                        context_vector,
                        float(reward_value),
                    )
                    updates += 1
                    if getattr(self, "policy_logger", None):
                        self.policy_logger.log_reward(
                            decision_trial_id
                            or (trial_metadata or {}).get("trial_id"),
                            bandit_name,
                            arm_index,
                            float(reward_value),
                            memory_id,
                        )
                except Exception as e:  # pragma: no cover
                    logger.warning(
                        "report_reward: policy.update failed for "
                        "memory_id=%s bandit=%s arm=%s (%s)",
                        memory_id,
                        bandit_name,
                        arm_index,
                        e,
                    )
        logger.info(
            "report_reward: applied %d bandit update(s); "
            "pending_decisions now tracks %d memory_id(s)",
            updates,
            len(self._pending_reward_decisions),
        )
