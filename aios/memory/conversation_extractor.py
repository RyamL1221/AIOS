"""
Conversation Extractor for the AIOS personalization pipeline.

Extracts user+assistant conversation pairs from completed LLM turns
and stores them as memories via the configured memory provider.
Runs asynchronously in a daemon thread so it never blocks LLM responses.
"""
import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aios.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class ConversationExtractor:
    """Extracts conversation turns and stores them as memories.

    Uses the memory provider's ``add_memory`` operation (never
    ``add_agentic_memory``) to persist conversation pairs scoped
    to the originating agent name.
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
        """
        if not self.enabled:
            return

        try:
            thread = threading.Thread(
                target=self._store_conversation,
                args=(
                    agent_name,
                    user_message,
                    assistant_message,
                    user_id,
                ),
                daemon=True,
            )
            thread.start()
        except Exception:
            logger.warning(
                "Failed to spawn extraction thread",
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _store_conversation(
        self,
        agent_name: str,
        user_message: str,
        assistant_message: str,
        user_id: str | None = None,
    ) -> None:
        """Synchronous storage called from the background thread."""
        try:
            from aios.memory.note import MemoryNote

            content = self._build_conversation_content(
                user_message, assistant_message,
            )

            # Use the resolved user_id when available so
            # the conversation memory lands in the same
            # Mem0 scope as profile/task memories written
            # by other agents for this user.  Fall back to
            # agent_name for backward compatibility.
            effective_user_id = user_id or agent_name

            memory_note = MemoryNote(
                content=content,
                context="conversation",
                category="conversation",
            )
            memory_note.metadata = {
                "user_id": effective_user_id,
                "owner_agent": agent_name,
                "memory_type": "conversation",
                "sharing_policy": "private",
            }

            result = self.memory_manager.provider.add_memory(
                memory_note
            )

            logger.info(
                "Stored conversation memory for "
                "user_id=%s (agent=%s): %s",
                effective_user_id,
                agent_name,
                content[:80],
            )
        except Exception as e:
            logger.warning(
                "Conversation extraction failed for "
                "user_id=%s",
                agent_name,
                exc_info=True,
            )

    @staticmethod
    def _build_conversation_content(
        user_message: str,
        assistant_message: str,
    ) -> str:
        """Format the conversation pair for storage."""
        return f"User: {user_message}\nAssistant: {assistant_message}"
