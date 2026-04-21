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

if TYPE_CHECKING:
    from aios.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class ContextInjector:
    """Retrieves relevant memories and injects them into LLM
    query messages.

    Uses the memory provider's ``retrieve_memory`` operation to
    find memories scoped to the requesting agent, filters by
    relevance score, formats them into a delimited system message,
    and prepends it at index 0 of the query's message list.
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
        self.relevance_threshold = config.get(
            "relevance_threshold", 0.5
        )
        self.max_tokens = config.get("max_memory_tokens", 1500)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def inject(
        self,
        agent_name: str,
        query: LLMQuery,
    ) -> "tuple[LLMQuery, dict]":
        """Retrieve relevant memories and prepend as a system
        message, returning diagnostics alongside the query.

        After retrieving the agent's own memories, the injector
        derives a ``user_id`` from the metadata of those memories
        and issues a second retrieval for shared memories from
        other agents with the same ``user_id``.  The two result
        sets are merged and deduplicated before relevance
        filtering and token-budget truncation.

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

            # Retrieve memories scoped to this agent.
            # Pass ``user_id=agent_name`` so the Mem0
            # provider searches under the scope that
            # ConversationExtractor writes to.
            mem_query = MemoryQuery(
                operation_type="retrieve_memory",
                params={
                    "content": user_text,
                    "k": self.max_memories,
                    "agent_name": agent_name,
                    "user_id": agent_name,
                },
            )
            response = (
                self.memory_manager.provider.retrieve_memory(
                    mem_query
                )
            )

            own_results = []
            if response.success and response.search_results:
                own_results = response.search_results
                logger.info(
                    "Retrieved %d own memories for agent=%s",
                    len(own_results),
                    agent_name,
                )

            # --- Cross-agent shared memory retrieval ---
            # Derive user_id from own memories first; fall
            # back to the kernel's known_user_ids registry
            # so that shared retrieval works even when the
            # requesting agent has no memories of its own.
            derived_user_id = (
                self._extract_user_id_from_results(
                    own_results
                )
            )

            # If own memories didn't yield a real user_id
            # (or yielded the agent name), consult the
            # MemoryManager's registry of user_ids that
            # other agents have written.
            if (
                not derived_user_id
                or derived_user_id == agent_name
            ):
                known = getattr(
                    self.memory_manager,
                    "known_user_ids",
                    set(),
                )
                # Pick the first known user_id that
                # isn't the agent's own name.
                for uid in known:
                    if uid and uid != agent_name:
                        derived_user_id = uid
                        break

            results = list(own_results)

            if (
                derived_user_id
                and derived_user_id != agent_name
            ):
                shared = self._retrieve_shared_memories(
                    user_text, derived_user_id, agent_name
                )
                if shared:
                    results = self._merge_and_deduplicate(
                        own_results, shared
                    )
                    shared_agents = list({
                        (m.get("metadata") or {}).get(
                            "owner_agent", ""
                        )
                        for m in shared
                        if (m.get("metadata") or {}).get(
                            "owner_agent", ""
                        )
                    })
                    logger.info(
                        "Retrieved %d shared memories for "
                        "user_id=%s from agents: %s",
                        len(shared),
                        derived_user_id,
                        shared_agents,
                    )

            if not results:
                logger.info(
                    "No memories retrieved for agent=%s",
                    agent_name,
                )
                diagnostics["prompt_tokens_after"] = (
                    diagnostics["prompt_tokens_before"]
                )
                diagnostics["resolved_user_id"] = (
                    derived_user_id
                    if (
                        derived_user_id
                        and derived_user_id != agent_name
                    )
                    else None
                )
                return (query, diagnostics)

            # candidate_count = merged set before filtering
            diagnostics["candidate_count"] = len(results)

            # Filter by relevance threshold
            filtered = []
            for mem in results:
                score = mem.get("score")
                if score is None:
                    filtered.append(mem)
                elif score >= self.relevance_threshold:
                    filtered.append(mem)
                else:
                    logger.debug(
                        "Excluded memory (score=%.3f < "
                        "threshold=%.3f): %s",
                        score,
                        self.relevance_threshold,
                        (mem.get("content", ""))[:60],
                    )

            if not filtered:
                logger.info(
                    "All memories excluded by relevance "
                    "threshold for user_id=%s",
                    agent_name,
                )
                diagnostics["prompt_tokens_after"] = (
                    diagnostics["prompt_tokens_before"]
                )
                return (query, diagnostics)

            # Sort by score descending (most relevant first)
            filtered.sort(
                key=lambda m: m.get("score", 0),
                reverse=True,
            )

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
                "for agent=%s, user_id=%s",
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
                derived_user_id or agent_name,
            )
            diagnostics["resolved_user_id"] = (
                derived_user_id
                if (
                    derived_user_id
                    and derived_user_id != agent_name
                )
                else None
            )
            return (query, diagnostics)

        except Exception:
            logger.warning(
                "Context injection failed for "
                "user_id=%s",
                agent_name,
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
    # Cross-agent helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_user_id_from_results(
        results: list,
    ) -> Optional[str]:
        """Return the first non-empty ``user_id`` found in the
        metadata of *results*, or ``None`` if none exists."""
        for mem in results:
            meta = mem.get("metadata") or {}
            uid = meta.get("user_id")
            if uid:
                return uid
        return None

    def _retrieve_shared_memories(
        self,
        user_text: str,
        user_id: str,
        agent_name: str | None = None,
    ) -> list:
        """Issue a second retrieval for shared memories from
        other agents that belong to *user_id*.

        Returns an empty list on any failure so the caller can
        fall back to using only the agent's own memories.
        """
        try:
            params: dict = {
                "content": user_text,
                "k": self.max_memories,
                "user_id": user_id,
                "sharing_policy": "shared",
            }
            if agent_name is not None:
                params["agent_name"] = agent_name
            shared_query = MemoryQuery(
                operation_type="retrieve_memory",
                params=params,
            )
            resp = (
                self.memory_manager.provider
                .retrieve_memory(shared_query)
            )
            if resp.success and resp.search_results:
                return resp.search_results
        except Exception:
            logger.debug(
                "Shared memory retrieval failed for "
                "user_id=%s",
                user_id,
                exc_info=True,
            )
        return []

    @staticmethod
    def _merge_and_deduplicate(
        own: list,
        shared: list,
    ) -> list:
        """Merge *own* and *shared* result lists, removing
        duplicates by memory content.

        Own memories always come first so they are never
        dropped in favour of a shared duplicate.
        """
        seen_content: set = set()
        merged: list = []

        for mem in own:
            content = mem.get("content", "")
            seen_content.add(content)
            merged.append(mem)

        for mem in shared:
            content = mem.get("content", "")
            if content not in seen_content:
                seen_content.add(content)
                merged.append(mem)

        return merged

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
