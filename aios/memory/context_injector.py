"""
Context Injector for the AIOS personalization pipeline.

Retrieves relevant memories from the configured memory provider and
prepends them as a system message to the LLM query's message list,
enabling personalized agent responses based on prior interactions.
"""
import logging
from typing import TYPE_CHECKING, Optional

from cerebrum.llm.apis import LLMQuery
from cerebrum.memory.apis import MemoryQuery

from aios.memory.memory_formatter import format_memory

if TYPE_CHECKING:
    from aios.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class ContextInjector:
    """Retrieves relevant memories and injects them into LLM
    query messages.

    Asks ``MemoryManager.retrieve_for_agent`` which memories the
    requesting agent sees, formats them, applies the token budget,
    and prepends the resulting system message at index 0 of the
    query's message list.
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
        - **happy path**: fully populated diagnostics.
        - **exception**: ``injected_count`` forced to 0,
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
            })

        diagnostics: dict = {
            "auto_inject_enabled": True,
            "candidate_count": 0,
            "injected_count": 0,
            "source_agents": [],
            "memory_types": [],
            "prompt_tokens_before": 0,
            "prompt_tokens_after": 0,
            "resolved_user_id": None,
            "barrier_waits": [],
            "after_budget": 0,
            "tokens_estimated": 0,
            "injected_memories": [],
        }

        try:
            diagnostics["prompt_tokens_before"] = (
                self._estimate_tokens(
                    self._serialize_messages(
                        query.messages
                    )
                )
            )

            user_text = self._extract_latest_user_message(
                query.messages
            )
            if user_text is None:
                diagnostics["prompt_tokens_after"] = (
                    diagnostics["prompt_tokens_before"]
                )
                return (query, diagnostics)

            filtered, retrieval = (
                self.memory_manager.retrieve_for_agent(
                    agent_name,
                    agent_name,
                    user_text,
                    k=self.max_memories,
                    include_shared=True,
                    request_user_id=user_id,
                )
            )
            retrieval.pop("error", None)
            diagnostics.update(retrieval)
            diagnostics["candidate_count"] = retrieval["after_dedupe"]
            resolved_user_id = retrieval["resolved_user_id"]

            logger.info(
                "Injection pipeline for agent=%s: "
                "resolved_user_id=%s, candidates=%d, kept=%d",
                agent_name,
                resolved_user_id,
                retrieval["after_dedupe"],
                len(filtered),
            )

            if not filtered:
                logger.info(
                    "No memories selected for agent=%s "
                    "(resolved_user_id=%s)",
                    agent_name,
                    resolved_user_id,
                )
                diagnostics["prompt_tokens_after"] = (
                    diagnostics["prompt_tokens_before"]
                )
                return (query, diagnostics)

            # Format memory content to natural language
            formatted_memories = []
            for mem in filtered:
                formatted = dict(mem)  # shallow copy
                try:
                    formatted["content"] = format_memory(
                        mem.get("content", ""),
                        mem.get("metadata", {}),
                    )
                except Exception:
                    logger.warning(
                        "Memory formatting failed, "
                        "using raw content",
                        exc_info=True,
                    )
                formatted_memories.append(formatted)
            filtered = formatted_memories

            # Truncate by token budget
            filtered = self._truncate_by_token_budget(
                filtered
            )

            if not filtered:
                diagnostics["prompt_tokens_after"] = (
                    diagnostics["prompt_tokens_before"]
                )
                return (query, diagnostics)

            # Record injected_count after all filtering
            diagnostics["injected_count"] = len(filtered)
            diagnostics["after_budget"] = len(filtered)
            diagnostics["injected_memories"] = [
                {
                    "memory_id": mem.get("memory_id"),
                    "owner_agent": (mem.get("metadata") or {}).get(
                        "owner_agent", ""
                    ),
                    "memory_type": (mem.get("metadata") or {}).get(
                        "memory_type", ""
                    ),
                    "match_score": mem.get("score"),
                }
                for mem in filtered
            ]

            # Extract unique source_agents and memory_types
            agents: set = set()
            types: set = set()
            for mem in filtered:
                meta = mem.get("metadata") or {}
                oa = meta.get("owner_agent", "")
                if oa:
                    agents.add(oa)
                mt = meta.get("memory_type", "")
                if mt:
                    types.add(mt)
            diagnostics["source_agents"] = list(agents)
            diagnostics["memory_types"] = list(types)

            # Build and prepend the system message
            block = self._format_memory_block(filtered)
            diagnostics["tokens_estimated"] = self._estimate_tokens(
                block
            )
            system_msg = {
                "role": "system",
                "content": block,
            }
            query.messages = [system_msg] + query.messages

            diagnostics["prompt_tokens_after"] = (
                self._estimate_tokens(
                    self._serialize_messages(
                        query.messages
                    )
                )
            )

            logger.info(
                "Injected %d memories (%d own + %d shared) "
                "for agent=%s, resolved_user_id=%s",
                len(filtered),
                sum(
                    1 for m in filtered
                    if (m.get("metadata") or {}).get(
                        "owner_agent", ""
                    ) == agent_name
                ),
                sum(
                    1 for m in filtered
                    if (m.get("metadata") or {}).get(
                        "owner_agent", ""
                    ) != agent_name
                ),
                agent_name,
                resolved_user_id,
            )
            return (query, diagnostics)

        except Exception:
            logger.warning(
                "Context injection failed for agent=%s "
                "(resolved_user_id=%s)",
                agent_name,
                diagnostics.get("resolved_user_id"),
                exc_info=True,
            )
            diagnostics["injected_count"] = 0
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

    @staticmethod
    def _extract_latest_user_message(
        messages: list,
    ) -> Optional[str]:
        """Return the content of the last user-role message,
        or ``None`` if none exists."""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return msg.get("content")
        return None

    @staticmethod
    def _format_memory_block(
        memories: list,
    ) -> str:
        """Format memories into a delimited system message
        string."""
        lines = [
            "===== MEMORY CONTEXT =====",
            "The following are relevant memories from prior "
            "interactions with this user. Use them to "
            "personalize your response:",
            "",
        ]
        for mem in memories:
            ts = mem.get("timestamp", "unknown")
            content = mem.get("content", "")
            lines.append(f"- [{ts}] {content}")

        lines.append("")
        lines.append("===== END MEMORY CONTEXT =====")
        return "\n".join(lines)

    @staticmethod
    def _serialize_messages(messages: list) -> str:
        """Join all message content strings for token
        estimation."""
        return " ".join(
            m.get("content", "") for m in messages
        )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimate: words * 1.3."""
        return int(len(text.split()) * 1.3)

    def _truncate_by_token_budget(
        self,
        memories: list,
    ) -> list:
        """Remove least-relevant memories until the formatted
        block fits within ``max_tokens``.

        Memories are assumed to be sorted by score descending.
        We remove from the tail (lowest score) first.
        """
        while memories:
            block = self._format_memory_block(memories)
            if self._estimate_tokens(block) <= self.max_tokens:
                return memories
            # Drop the least relevant (last item)
            memories = memories[:-1]
        return memories
