"""Gives a fake memory manager the real kernel retrieval path."""
from aios.memory.manager import MemoryManager


class KernelRetrievalDouble:
    """Base for fake managers that only fake the registry or provider.

    ``ContextInjector`` swallows exceptions, so a fake without
    ``retrieve_for_agent`` would inject nothing and silently pass any
    test that expects no injection.
    """

    relevance_threshold = 0.0
    retrieve_for_agent = MemoryManager.retrieve_for_agent
    _resolve_user_id = MemoryManager._resolve_user_id
    _await_pending_writes = MemoryManager._await_pending_writes
    _fetch_candidates = MemoryManager._fetch_candidates
    _provider_supports_barrier = MemoryManager._provider_supports_barrier
    _merge_and_deduplicate = staticmethod(
        MemoryManager._merge_and_deduplicate
    )
