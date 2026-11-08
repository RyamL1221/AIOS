"""
Conversation Extractor for the AIOS personalization pipeline.

Extracts user+assistant conversation pairs from completed LLM turns
and stores them as memories through ``MemoryManager.address_request``.
Runs asynchronously in a daemon thread so it never blocks LLM responses.
"""
import logging
import threading
from typing import TYPE_CHECKING

from cerebrum.memory.apis import MemoryQuery

from aios.memory.pipeline import conversation_request

if TYPE_CHECKING:
    from aios.memory.manager import MemoryManager
    from aios.syscall.memory import MemorySyscall

logger = logging.getLogger(__name__)


class ConversationExtractor:
    """Extracts conversation turns and stores them as memories.

    Sends ``add_memory`` (never ``add_agentic_memory``) through the
    manager, so a conversation write gets the same barrier stamp,
    owner, and user registration as any other write. Conversation
    memories are private to the originating agent.
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
        self.enabled = config.get("auto_extract", False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_async(
        self,
        agent_name: str,
        user_message: str,
        assistant_message: str,
        user_id: str | None = None,
        session: int | None = None,
    ) -> None:
        """Store a conversation pair in a background daemon thread.

        No-op when ``auto_extract`` is disabled.  Errors are logged
        at WARNING level and never raised.

        Args:
            agent_name: The requesting agent's name.
            user_message: The user's message content.
            assistant_message: The assistant's response.
            user_id: Optional real user identifier resolved
                by the ContextInjector.  When provided, the
                conversation memory is stored under this
                user_id instead of the agent name, keeping
                it in the same Mem0 scope as profile/task
                memories written by other agents.
            session: The caller's current session (benchmark v2),
                stamped on the stored turn as ``metadata.session``
                so the block can give it an age in sessions. None
                stamps nothing.
        """
        if not self.enabled:
            return

        syscall = None
        try:
            syscall = self._build_syscall(
                agent_name, user_message, assistant_message, user_id,
                session,
            )
            # Stamp here, on the request thread, and not in the
            # background: the chat response must not return before the
            # write is pending, or a retrieval issued right after it
            # could snapshot the barrier too early and miss the write.
            self.memory_manager.stamp_syscall(syscall)
            thread = threading.Thread(
                target=self._store_conversation,
                args=(syscall,),
                daemon=True,
            )
            thread.start()
        except Exception:
            logger.warning(
                "Failed to spawn extraction thread",
                exc_info=True,
            )
            self._release(syscall)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_syscall(
        self,
        agent_name: str,
        user_message: str,
        assistant_message: str,
        user_id: str | None = None,
        session: int | None = None,
    ) -> "MemorySyscall":
        """Build the write, as a syscall that only carries data: it goes
        straight to ``address_request`` and is never started or queued.

        Uses the resolved user_id when available so the memory lands in
        the same Mem0 scope as profile/task memories written by other
        agents for this user. Falls back to agent_name. A ``session``
        is stamped in the metadata.
        """
        from aios.syscall.memory import MemorySyscall

        query = MemoryQuery(
            operation_type="add_memory",
            params=conversation_request(
                agent_name, user_message, assistant_message, user_id,
                extra_metadata=(
                    None if session is None else {"session": session}
                ),
            ),
        )
        return MemorySyscall(agent_name, query)

    def _release(self, syscall: "MemorySyscall | None") -> None:
        """Release a write that failed before ``address_request`` could.
        A second release of the same write is a no-op."""
        seq_no = getattr(syscall, "barrier_seq", 0)
        if seq_no:
            self.memory_manager.barrier.release(
                syscall.query.params["metadata"]["user_id"],
                seq_no,
                success=False,
            )

    def _store_conversation(self, syscall: "MemorySyscall") -> None:
        """Synchronous storage called from the background thread."""
        metadata = syscall.query.params["metadata"]
        try:
            response = self.memory_manager.address_request(syscall)
            if not response.success:
                logger.warning(
                    "Conversation extraction failed for user_id=%s: %s",
                    metadata["user_id"],
                    response.error,
                )
                return
            logger.info(
                "Stored conversation memory for "
                "user_id=%s (agent=%s): %s",
                metadata["user_id"],
                syscall.agent_name,
                syscall.query.params["content"][:80],
            )
        except Exception:
            logger.warning(
                "Conversation extraction failed for "
                "user_id=%s",
                metadata["user_id"],
                exc_info=True,
            )
            self._release(syscall)

    @staticmethod
    def _build_conversation_content(
        user_message: str,
        assistant_message: str,
    ) -> str:
        """Format the conversation pair for storage."""
        return conversation_request(
            "", user_message, assistant_message
        )["content"]
