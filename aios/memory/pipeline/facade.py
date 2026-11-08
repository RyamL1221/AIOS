"""
``MemoryPipeline``: the memory logic one agent's requests go through.

The kernel builds it over its shared barrier and identity registry; a
replicated agent builds its own (docs/REPLICATED_LOGIC.md). Everything
that decides what is stored and what an agent sees is here, so both run
the same code.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from cerebrum.utils.usage import tagged

from ..note import MemoryNote
from ..providers.base import Candidate, MemoryProvider
from .barrier import MemoryWriteBarrier
from .formatter import Formatter, estimate_tokens
from .identity import IdentityResolver
from .selector import Selector
from .settings import PipelineSettings
from .visibility import Visibility

# An update may not move a memory to another owner or user, or rewrite
# when it was created.
UPDATE_PROTECTED_METADATA = ("owner_agent", "user_id", "created_at")

# MemoryNote fields an SDK request may set directly.
NOTE_FIELDS = (
    "content", "id", "keywords", "links", "retrieval_count",
    "timestamp", "last_accessed", "context", "evolution_history",
    "category", "tags",
)

# ``list_own``'s default size: more rows than any user's store holds, so
# a listing is complete (a revoke deletes every row it finds).
LIST_TOP_K = 10_000

_LOCAL = object()


def note_from_request(params: Dict[str, Any]) -> MemoryNote:
    """The note an SDK ``create_memory`` request describes: its note
    fields, ``memory_id`` as the id, tags / keywords / category from the
    metadata when not given directly, and the full metadata dict (which
    carries the cross-agent fields)."""
    metadata = params.get("metadata", {})
    data = {key: params[key] for key in params if key in NOTE_FIELDS}
    if "memory_id" in params and "id" not in data:
        data["id"] = params["memory_id"]
    if "tags" in metadata and "tags" not in data:
        data["tags"] = metadata.get("tags", [])
    if "keywords" in metadata and "keywords" not in data:
        data["keywords"] = metadata.get("keywords", [])
    if "category" in metadata and "category" not in data:
        data["category"] = metadata.get("category", "Uncategorized")
    note = MemoryNote(**data)
    if metadata:
        note.metadata = metadata
    return note


def conversation_request(
    agent_name: str, user_message: str, assistant_message: str,
    user_id: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """The write request for the conversation memory after a chat turn:
    the pair as text, private to the assistant, in the user's scope
    (the agent's own scope without a user). ``extra_metadata`` is
    merged over that metadata, as a deployment adds it to every write:
    provenance, or the ``session`` the turn belongs to (benchmark
    v2)."""
    metadata = {
        "user_id": user_id or agent_name,
        "owner_agent": agent_name,
        "memory_type": "conversation",
        "sharing_policy": "private",
    }
    metadata.update(extra_metadata or {})
    return {
        "content": f"User: {user_message}\nAssistant: {assistant_message}",
        "context": "conversation",
        "category": "conversation",
        "metadata": metadata,
    }


def conversation_note(
    agent_name: str, user_message: str, assistant_message: str,
    user_id: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> MemoryNote:
    """The conversation memory as a note (``conversation_request``)."""
    return note_from_request(conversation_request(
        agent_name, user_message, assistant_message, user_id,
        extra_metadata,
    ))


def latest_user_message(messages: List[dict]) -> Optional[str]:
    """The content of the last user-role message, or None."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content")
    return None


def serialize_messages(messages: List[dict]) -> str:
    """Join all message content strings for token estimation."""
    return " ".join(m.get("content", "") for m in messages)


class MemoryPipeline:
    """One agent's memory logic over one provider.

    Args:
        provider: Any ``MemoryProvider`` (docs/PROVIDER_CONTRACT.md).
        settings: Threshold, cap, token budget and barrier settings.
        barrier: The write barrier. Omitted: a new one of the agent's
            own, from ``settings.write_barrier``. ``None``: no barrier.
        resolver: The identity resolver; omitted, a new one.
    """

    def __init__(
        self,
        provider: MemoryProvider,
        settings: Optional[PipelineSettings] = None,
        *,
        barrier: Any = _LOCAL,
        resolver: Optional[IdentityResolver] = None,
    ):
        self.provider = provider
        self.settings = settings or PipelineSettings()
        self.barrier: Optional[MemoryWriteBarrier] = (
            MemoryWriteBarrier(config=self.settings.write_barrier)
            if barrier is _LOCAL else barrier
        )
        self.resolver = resolver or IdentityResolver()
        self.selector = Selector(
            provider, self.settings, self.barrier, self.resolver
        )

    # -- writes --------------------------------------------------------

    def write(
        self, agent_name: str, user_id: Optional[str], note: MemoryNote,
        *, barrier_seq: Optional[int] = None,
    ) -> str:
        """Store one note and return its id; raises ``ProviderError``.

        Fills the required metadata (``user_id`` from the note, else
        ``user_id``, else the agent; ``owner_agent``; ``memory_type``;
        ``sharing_policy`` private; ``created_at``), registers the user,
        and holds the write barrier for the user until the provider
        returns. ``barrier_seq`` is a sequence already acquired (the
        kernel stamps it when the syscall is accepted; ``0`` means
        none); without it the write acquires its own.
        """
        if note.metadata is None:
            note.metadata = {}
        metadata = note.metadata
        if not metadata.get("user_id"):
            metadata["user_id"] = user_id or agent_name
        # Stored under the resolver's canonical id (HETEROGENEITY.md).
        metadata["user_id"] = self.resolver.canonical(metadata["user_id"])
        # The visibility rule keys on owner_agent, so a write without
        # one would be invisible even to its author.
        if not metadata.get("owner_agent"):
            metadata["owner_agent"] = agent_name
        # The rest of the required metadata (PROVIDER_CONTRACT.md).
        metadata.setdefault("memory_type", "")
        if not metadata.get("sharing_policy"):
            metadata["sharing_policy"] = "private"
        metadata.setdefault(
            "created_at", datetime.now(timezone.utc).isoformat()
        )
        uid = metadata["user_id"]
        if uid != agent_name:
            self.resolver.register(uid)

        if barrier_seq is None:
            barrier_seq = (
                self.barrier.acquire(uid) if self.barrier else 0
            )
        success = False
        try:
            with tagged(uid):
                memory_id = self.provider.add(note)
            success = True
            return memory_id
        finally:
            # Waiters are released even when the provider raised.
            if self.barrier:
                self.barrier.release(uid, barrier_seq, success=success)

    def locate(
        self, memory_id: str, user_id: Optional[str], agent_name: str
    ) -> Optional[Candidate]:
        """Fetch a memory named by id, wherever it is stored.

        Providers keep one collection per user, so an id alone cannot
        find a row. Uses the caller's user_id when given; otherwise tries
        the agent's own scope, then the provider's default.
        """
        user_id = self.resolver.canonical(user_id)
        scopes = [user_id] if user_id else [agent_name, None]
        for scope in scopes:
            found = self.provider.get(memory_id, scope)
            if found is not None:
                return found
        return None

    def update(
        self, agent_name: str, user_id: Optional[str], memory_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        *, barrier_seq: Optional[int] = None,
    ) -> bool:
        """Owner-only update; False when the memory is missing or not
        the agent's. Raises ``ProviderError``. Held against the barrier
        like a write, so a retrieval accepted after it reads the new
        content; released on every path."""
        user_id = self.resolver.canonical(user_id)
        if barrier_seq is None:
            barrier_seq = (
                self.barrier.acquire(user_id)
                if self.barrier and user_id else 0
            )
        success = False
        try:
            found = self.locate(memory_id, user_id, agent_name)
            if found is None or not Visibility.can_write(
                agent_name, found.metadata
            ):
                return False
            kept = {
                key: value for key, value in (metadata or {}).items()
                if key not in UPDATE_PROTECTED_METADATA
            }
            owner_user = found.metadata.get("user_id") or None
            with tagged(owner_user or agent_name):
                success = bool(self.provider.update(
                    memory_id, owner_user, content, kept,
                ))
            return success
        finally:
            if self.barrier and user_id:
                self.barrier.release(user_id, barrier_seq, success=success)

    def delete(
        self, agent_name: str, user_id: Optional[str], memory_id: str
    ) -> bool:
        """Owner-only delete; False when the memory is missing or not
        the agent's (shared or not: only the owner may delete). Deletes
        from the scope the memory was found in. Raises
        ``ProviderError``."""
        found = self.locate(memory_id, user_id, agent_name)
        if found is None or not Visibility.can_write(
            agent_name, found.metadata
        ):
            return False
        owner_user = found.metadata.get("user_id") or None
        with tagged(owner_user or agent_name):
            return bool(self.provider.delete(memory_id, owner_user))

    # -- reads ---------------------------------------------------------

    def list_own(
        self, agent_name: str, user_id: Optional[str], *,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Every memory ``agent_name`` owns in ``user_id``'s scope (the
        agent's own scope without a user), as rows (``Candidate
        .to_row``), unscored, in storage order.

        A writer lists its own rows to find the ones it must delete on a
        revoke (docs/BENCHMARK_V2.md, "Revoke and deletion"). Owner-only:
        another agent's rows are left out, shared or not, as are rows
        outside the user's partition. ``top_k`` caps the rows returned;
        the provider is asked for at least ``LIST_TOP_K``, so the cap
        applies to the agent's own rows. Raises ``ProviderError``.
        """
        scope = self.resolver.canonical(user_id) or agent_name
        limit = LIST_TOP_K if top_k is None else top_k
        with tagged(scope):
            found = self.provider.list(scope, max(limit, LIST_TOP_K))
        rows = [
            candidate.to_row() for candidate in found
            if (candidate.metadata or {}).get("user_id", "") == scope
            and Visibility.can_write(agent_name, candidate.metadata)
        ]
        return rows[:max(limit, 0)]

    def retrieve(
        self,
        agent_name: str,
        user_id: Optional[str],
        query: str,
        *,
        k: Optional[int] = None,
        include_shared: bool = True,
        request_user_id: Optional[str] = None,
        sharing_policy: Optional[str] = None,
        barrier_snapshot: Optional[int] = None,
    ) -> "tuple[list, dict]":
        """The memories ``agent_name`` sees for ``query``, and the
        selection's diagnostics (``Selector.select``). ``k`` defaults to
        ``max_injected_memories``."""
        return self.selector.select(
            agent_name, user_id, query,
            k=self.settings.max_injected_memories if k is None else k,
            include_shared=include_shared,
            request_user_id=request_user_id,
            sharing_policy=sharing_policy,
            barrier_snapshot=barrier_snapshot,
        )

    def build_block(
        self, candidates: list, *, max_tokens: Optional[int] = None,
        session: Optional[int] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """The memory block for selected candidates
        (``Formatter.build``); ``max_tokens`` defaults to
        ``max_memory_tokens``. ``session`` is the caller's current
        session, which session ages count from
        (``block_recency_unit: "session"``)."""
        budget = (
            self.settings.max_memory_tokens
            if max_tokens is None else max_tokens
        )
        return Formatter(
            budget,
            self.settings.block_format,
            recency=self.settings.block_recency,
            recency_unit=self.settings.block_recency_unit,
            current_session=session,
        ).build(candidates)

    def inject(
        self,
        agent_name: str,
        messages: List[dict],
        *,
        user_id: Optional[str] = None,
        k: Optional[int] = None,
        max_tokens: Optional[int] = None,
        session: Optional[int] = None,
    ) -> Tuple[List[dict], Dict[str, Any]]:
        """Retrieve for the latest user message and prepend the block as
        a system message. Returns the new message list and the
        injection diagnostics. Messages come back unchanged when there
        is no user message or nothing to inject. ``session`` is the
        caller's current session (``build_block``)."""
        diagnostics: Dict[str, Any] = {
            "auto_inject_enabled": True,
            "candidate_count": 0,
            "injected_count": 0,
            "source_agents": [],
            "memory_types": [],
            "prompt_tokens_before": estimate_tokens(
                serialize_messages(messages)
            ),
            "prompt_tokens_after": 0,
            "resolved_user_id": None,
            "barrier_waits": [],
            "after_budget": 0,
            "tokens_estimated": 0,
            "injected_memories": [],
            "block_text": "",
            "format_ms": 0.0,
        }
        unchanged = diagnostics["prompt_tokens_before"]
        user_text = latest_user_message(messages)
        if user_text is None:
            diagnostics["prompt_tokens_after"] = unchanged
            return messages, diagnostics

        candidates, retrieval = self.retrieve(
            agent_name, agent_name, user_text,
            k=k, include_shared=True, request_user_id=user_id,
        )
        retrieval.pop("error", None)
        diagnostics.update(retrieval)
        diagnostics["candidate_count"] = retrieval["after_dedupe"]
        if not candidates:
            diagnostics["prompt_tokens_after"] = unchanged
            return messages, diagnostics

        text, block = self.build_block(
            candidates, max_tokens=max_tokens, session=session
        )
        diagnostics.update(block)
        if not text:
            diagnostics["prompt_tokens_after"] = unchanged
            return messages, diagnostics
        messages = [{"role": "system", "content": text}] + messages
        diagnostics["prompt_tokens_after"] = estimate_tokens(
            serialize_messages(messages)
        )
        return messages, diagnostics
