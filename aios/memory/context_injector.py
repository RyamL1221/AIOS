"""
Context Injector for the AIOS personalization pipeline.

Retrieves relevant memories from the configured memory provider and
prepends them as a system message to the LLM query's message list,
enabling personalized agent responses based on prior interactions.
"""
import logging
from typing import TYPE_CHECKING, Optional

from cerebrum.llm.apis import LLMQuery

from aios.memory.pipeline.facade import (
    latest_user_message,
    serialize_messages,
)
from aios.memory.pipeline.formatter import (
    Formatter,
    estimate_tokens,
    format_block,
)

if TYPE_CHECKING:
    from aios.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class ContextInjector:
    """Retrieves relevant memories and injects them into LLM
    query messages.

    A thin kernel client of the memory pipeline library: it switches
    injection on or off, keeps the kernel's log lines, and asks the
    manager's ``MemoryPipeline`` (shared barrier, shared identity
    registry) to retrieve, format, budget and prepend the block at
    index 0 of the query's message list.
    """

    def __init__(
        self,
        memory_manager: "MemoryManager",
        config: dict,
    ) -> None:
        """
        Args:
            memory_manager: Initialized MemoryManager instance.
            config: Memory config section from config.yaml.
        """
        self.memory_manager = memory_manager
        self.enabled = config.get("auto_inject", False)
        self.max_memories = config.get(
            "max_injected_memories", 5
        )
        self.max_tokens = config.get("max_memory_tokens", 1500)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def inject(
        self,
        agent_name: str,
        query: LLMQuery,
        user_id: Optional[str] = None,
        session: Optional[int] = None,
    ) -> "tuple[LLMQuery, dict]":
        """Retrieve relevant memories and prepend as a system
        message, returning diagnostics alongside the query.

        Args:
            agent_name: The agent making the LLM request.
            query: The LLM query to inject memories into.
            user_id: Optional per-request end-user identity.
                When provided, memory retrieval is scoped to
                this user_id directly. Cross-agent shared memory
                retrieval is ONLY triggered when this parameter
                is a non-empty string different from agent_name.
                When absent or None, only the agent's own
                memories are retrieved (no shared injection).
            session: The caller's current session (benchmark v2):
                with ``memory.block_recency_unit: session``, each
                bullet's age counts the sessions since its row's.

        Retrieval behavior:

        - **Own memories**: Always retrieved, scoped by
          ``agent_name`` as owner_agent. Uses ``user_id`` as
          the query filter when available, falls back to
          ``agent_name`` for backward compatibility.
        - **Shared memories**: Only retrieved when an explicit
          ``user_id`` is provided. Uses ``user_id`` as the
          filter with ``sharing_policy="shared"``. The
          ``agent_name`` is NEVER used as a user_id for
          shared retrieval.

        Returns ``(query, diagnostics)`` in all code paths:

        - **disabled**: ``auto_inject_enabled=False``, counts
          at 0, empty lists, tokens unchanged.
        - **happy path**: fully populated diagnostics, with the
          library's ``retrieval_error`` (None unless a fetch failed).
        - **exception**: ``injected_count`` forced to 0,
          ``injection_error`` set to ``"<ExceptionType>: <message>"``,
          partially-filled diagnostics.
        """
        if not self.enabled:
            tokens = self._estimate_tokens(
                self._serialize_messages(query.messages)
            )
            return (query, {
                "auto_inject_enabled": False,
                "candidate_count": 0,
                "injected_count": 0,
                "source_agents": [],
                "memory_types": [],
                "prompt_tokens_before": tokens,
                "prompt_tokens_after": tokens,
                "resolved_user_id": None,
                "barrier_waits": [],
                "after_budget": 0,
                "tokens_estimated": 0,
                "injected_memories": [],
                "block_text": "",
                "format_ms": 0.0,
                "retrieval_error": None,
            })

        diagnostics: dict = {
            "auto_inject_enabled": True,
            "injected_count": 0,
            "prompt_tokens_before": self._estimate_tokens(
                self._serialize_messages(query.messages)
            ),
            "prompt_tokens_after": 0,
            "resolved_user_id": None,
        }

        try:
            # The library does the work (MemoryPipeline.inject), over
            # the kernel's shared barrier and identity registry.
            messages, diagnostics = (
                self.memory_manager.memory_pipeline().inject(
                    agent_name,
                    query.messages,
                    user_id=user_id,
                    k=self.max_memories,
                    max_tokens=self.max_tokens,
                    session=session,
                )
            )
            resolved_user_id = diagnostics["resolved_user_id"]
            if diagnostics.get("retrieval_error"):
                # Otherwise the log shows only "No memories selected",
                # as for an empty store.
                logger.warning(
                    "Memory retrieval failed for agent=%s "
                    "(resolved_user_id=%s): %s",
                    agent_name,
                    resolved_user_id,
                    diagnostics["retrieval_error"],
                )
            if "after_dedupe" in diagnostics:
                logger.info(
                    "Injection pipeline for agent=%s: "
                    "resolved_user_id=%s, candidates=%d, kept=%d",
                    agent_name,
                    resolved_user_id,
                    diagnostics["after_dedupe"],
                    diagnostics["after_cap"],
                )
            if not diagnostics["injected_count"]:
                if "after_dedupe" in diagnostics:
                    logger.info(
                        "No memories selected for agent=%s "
                        "(resolved_user_id=%s)",
                        agent_name,
                        resolved_user_id,
                    )
                return (query, diagnostics)

            query.messages = messages
            injected = diagnostics["injected_memories"]
            own = sum(
                1 for m in injected if m["owner_agent"] == agent_name
            )
            logger.info(
                "Injected %d memories (%d own + %d shared) "
                "for agent=%s, resolved_user_id=%s",
                len(injected),
                own,
                len(injected) - own,
                agent_name,
                resolved_user_id,
            )
            return (query, diagnostics)

        except Exception as e:
            logger.warning(
                "Context injection failed for agent=%s "
                "(resolved_user_id=%s)",
                agent_name,
                diagnostics.get("resolved_user_id"),
                exc_info=True,
            )
            diagnostics["injected_count"] = 0
            # Reported, not only logged: the caller must not take a
            # failed injection for an empty store (BENCHMARK_V2.md,
            # Amendment 2).
            diagnostics["injection_error"] = f"{type(e).__name__}: {e}"
            # If prompt_tokens_after was never set, match
            # prompt_tokens_before (query was not modified).
            if diagnostics["prompt_tokens_after"] == 0:
                diagnostics["prompt_tokens_after"] = (
                    diagnostics["prompt_tokens_before"]
                )
            return (query, diagnostics)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    # The library's helpers, kept under their old names.
    _extract_latest_user_message = staticmethod(latest_user_message)
    _format_memory_block = staticmethod(format_block)
    _serialize_messages = staticmethod(serialize_messages)
    _estimate_tokens = staticmethod(estimate_tokens)

    def _truncate_by_token_budget(self, memories: list) -> list:
        """Drop the lowest-ranked memories until the block fits
        ``max_tokens`` (``Formatter.truncate_by_token_budget``)."""
        settings = self.memory_manager.pipeline_settings()
        return Formatter(
            self.max_tokens,
            settings.block_format,
            recency=settings.block_recency,
            recency_unit=settings.block_recency_unit,
        ).truncate_by_token_budget(memories)
