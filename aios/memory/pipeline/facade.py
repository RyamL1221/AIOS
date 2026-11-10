"""
``MemoryPipeline``: the memory logic one agent's requests go through.

The kernel builds it over its shared barrier and identity registry; a
replicated agent builds its own (docs/REPLICATED_LOGIC.md). Everything
that decides what is stored and what an agent sees is here, so both run
the same code.
"""
import logging
from contextlib import nullcontext
from datetime import datetime, timezone
from typing import (
    Any, Callable, ContextManager, Dict, List, Optional, Tuple,
)

from ..note import MemoryNote
from ..providers.base import Candidate, MemoryProvider
from .barrier import MemoryWriteBarrier
from .deletion import LIST_TOP_K, MARKS, after_write, forget_fact
from .formatter import Formatter, estimate_tokens
from .identity import IdentityResolver
from .selector import Selector
from .settings import PipelineSettings
from .tombstones import TombstoneStore, carried_form
from .visibility import Visibility

logger = logging.getLogger(__name__)

# An update may not move a memory to another owner or user, rewrite
# when it was created, or set or clear a supersession mark (only the
# library marks a row retired).
UPDATE_PROTECTED_METADATA = (
    "owner_agent", "user_id", "created_at", *MARKS,
)

# MemoryNote fields an SDK request may set directly.
NOTE_FIELDS = (
    "content", "id", "keywords", "links", "retrieval_count",
    "timestamp", "last_accessed", "context", "evolution_history",
    "category", "tags",
)

_LOCAL = object()

# Tags the provider's own LLM and embedding calls with the user they
# serve, for cost accounting. The library imports nothing outside the
# standard library and the provider contract, so the caller passes the
# tag: the kernel and the replicated agents pass the SDK's
# ``cerebrum.utils.usage.tagged``.
UsageTag = Callable[[Optional[str]], ContextManager]


def untagged(user_id: Optional[str]) -> ContextManager:
    """The default usage tag: tags nothing."""
    return nullcontext()


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


def note_metadata_of(note: MemoryNote) -> Dict[str, Any]:
    """The metadata ``after_write`` reads from a written note: its
    ``metadata`` dict (fact_key, structured, value_aliases,
    provenance_event, session)."""
    return dict(getattr(note, "metadata", None) or {})


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


def retrieval_error(
    own_error: Optional[str], shared_error: Optional[str]
) -> Optional[str]:
    """A selection's failed fetches as one string, or None when both
    succeeded: ``"own: <error>"`` and/or ``"shared: <error>"``, joined
    by ``"; "``."""
    failed = [
        f"{fetch}: {error}"
        for fetch, error in (("own", own_error), ("shared", shared_error))
        if error
    ]
    return "; ".join(failed) or None


class MemoryPipeline:
    """One agent's memory logic over one provider.

    Args:
        provider: Any ``MemoryProvider`` (docs/PROVIDER_CONTRACT.md).
        settings: Threshold, cap, token budget and barrier settings.
        barrier: The write barrier. Omitted: a new one of the agent's
            own, from ``settings.write_barrier``. ``None``: no barrier.
        resolver: The identity resolver; omitted, a new one.
        tombstones: The store's tombstones (``TombstoneStore``). Every
            pipeline over one store must share them: the kernel passes
            its own to each per-request pipeline, and a replicated
            store's agents share one file. Omitted: a new in-memory
            one. ``None``: no tombstones (a forget fails, and the guard
            and the sweep have nothing to act on).
        usage_tag: A context manager factory that tags the provider's
            calls with the user they serve (``cerebrum.utils.usage
            .tagged`` in the kernel and the replicated agents); omitted,
            nothing is tagged.
    """

    def __init__(
        self,
        provider: MemoryProvider,
        settings: Optional[PipelineSettings] = None,
        *,
        barrier: Any = _LOCAL,
        resolver: Optional[IdentityResolver] = None,
        tombstones: Any = _LOCAL,
        usage_tag: Optional[UsageTag] = None,
    ):
        self.provider = provider
        self.usage_tag: UsageTag = usage_tag or untagged
        self.settings = settings or PipelineSettings()
        self.barrier: Optional[MemoryWriteBarrier] = (
            MemoryWriteBarrier(config=self.settings.write_barrier)
            if barrier is _LOCAL else barrier
        )
        self.resolver = resolver or IdentityResolver()
        self.tombstones: Optional[TombstoneStore] = (
            TombstoneStore() if tombstones is _LOCAL else tombstones
        )
        self.selector = Selector(
            provider, self.settings, self.barrier, self.resolver,
            tombstones=self.tombstones, usage_tag=self.usage_tag,
        )

    # -- writes --------------------------------------------------------

    def write(
        self, agent_name: str, user_id: Optional[str], note: MemoryNote,
        *, barrier_seq: Optional[int] = None,
        outcome: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store one note and return its id; raises ``ProviderError``.

        Fills the required metadata (``user_id`` from the note, else
        ``user_id``, else the agent; ``owner_agent``; ``memory_type``;
        ``sharing_policy`` private; ``created_at``), registers the user,
        and holds the write barrier for the user until the provider
        returns and ``after_write`` is done (a restatement's lift, the
        sweep of tombstoned values, supersession). ``barrier_seq`` is a
        sequence already acquired (the kernel stamps it when the syscall
        is accepted; ``0`` means none); without it the write acquires
        its own.

        ``outcome``, when given, gets ``after_write``'s report: the ids
        swept, retired and lifted, and ``suppressed``. A suppressed
        write (its own rows carried a forgotten value and were swept)
        returns ``""``, as a write that stored nothing does.
        """
        if note.metadata is None:
            note.metadata = {}
        metadata = note.metadata
        # Only the library marks a row retired: a write that carried a
        # mark would be born retired, never selected.
        for mark in MARKS:
            metadata.pop(mark, None)
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
            with self.usage_tag(uid):
                memory_id = self.provider.add(note)
                success = True
                report = after_write(
                    self.provider, self.tombstones, self.settings, uid,
                    note_metadata_of(note), memory_id=memory_id,
                )
            if outcome is not None:
                outcome.update(report)
            return "" if report["suppressed"] else memory_id
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
        outcome: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Owner-only update; False when the memory is missing or not
        the agent's. Raises ``ProviderError``. Held against the barrier
        like a write, so a retrieval accepted after it reads the new
        content; released on every path. Then, like a write, a
        restatement lifts its tombstone and tombstoned values are swept
        (``outcome``); an update retires no other row."""
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
            with self.usage_tag(owner_user or agent_name):
                success = bool(self.provider.update(
                    memory_id, owner_user, content, kept,
                ))
                if success and owner_user:
                    report = after_write(
                        self.provider, self.tombstones, self.settings,
                        owner_user, {**found.metadata, **kept},
                        memory_id=memory_id, supersede=False,
                    )
                    if outcome is not None:
                        outcome.update(report)
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
        with self.usage_tag(owner_user or agent_name):
            return bool(self.provider.delete(memory_id, owner_user))

    # -- reads ---------------------------------------------------------

    def list_own(
        self, agent_name: str, user_id: Optional[str], *,
        top_k: Optional[int] = None,
        barrier_snapshot: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """The rows of ``list_own_report``."""
        return self.list_own_report(
            agent_name, user_id, top_k=top_k,
            barrier_snapshot=barrier_snapshot,
        )[0]

    def list_own_report(
        self, agent_name: str, user_id: Optional[str], *,
        top_k: Optional[int] = None,
        barrier_snapshot: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Every memory ``agent_name`` owns in ``user_id``'s scope (the
        agent's own scope without a user), as rows (``Candidate
        .to_row``), unscored, in storage order.

        A writer lists its own rows to find the ones it must delete on a
        revoke (docs/BENCHMARK_V2.md, "Revoke and deletion"). Owner-only:
        another agent's rows are left out, shared or not, as are rows
        outside the user's partition. ``top_k`` caps the rows returned;
        the provider is asked for at least ``LIST_TOP_K``, so the cap
        applies to the agent's own rows. Raises ``ProviderError``.

        Waits for the scope's writes accepted before it, as a retrieval
        does (``Selector.await_pending_writes``), so a listing made right
        after a chat turn includes the turn the kernel writes in the
        background. ``barrier_snapshot`` is the high-water mark stamped
        when the listing was accepted: ``None`` takes one now, ``0``
        skips the wait.

        A row carrying a tombstoned value is never returned
        (docs/DELETION_AND_SUPERSESSION.md): it is left out with a
        WARNING, and its id comes back as withheld, the second element
        of the result, so an audit counts it as a carrier.
        """
        scope = self.resolver.canonical(user_id) or agent_name
        limit = LIST_TOP_K if top_k is None else top_k
        self.selector.await_pending_writes(scope, barrier_snapshot)
        with self.usage_tag(scope):
            found = self.provider.list(scope, max(limit, LIST_TOP_K))
        owned = [
            candidate for candidate in found
            if (candidate.metadata or {}).get("user_id", "") == scope
            and Visibility.can_write(agent_name, candidate.metadata)
        ]
        forms = self.tombstoned_forms(scope)
        rows, withheld = [], []
        for candidate in owned:
            if forms and carried_form(
                candidate.content, candidate.metadata, forms
            ) is not None:
                withheld.append(candidate.memory_id)
                logger.warning(
                    "Listing withheld memory %s of user_id=%s: it carries "
                    "a forgotten value, so it escaped the forget",
                    candidate.memory_id, scope,
                )
            else:
                rows.append(candidate.to_row())
        return rows[:max(limit, 0)], withheld

    def tombstoned_forms(self, user_id: Optional[str]) -> List[str]:
        """Every tombstoned form of the user; [] without a store."""
        if self.tombstones is None or not user_id:
            return []
        return self.tombstones.forms(user_id)

    def read(
        self, agent_name: str, user_id: Optional[str], memory_id: str
    ) -> Optional[Candidate]:
        """A memory by id, as ``agent_name`` may read it (``get_memory``):
        None when it is missing, not readable (another agent's private
        row) or carries a tombstoned value. The last logs a WARNING: a
        carrier that escaped the forget is never returned."""
        found = self.locate(memory_id, user_id, agent_name)
        if found is None or not Visibility.can_read(
            agent_name, found.metadata
        ):
            return None
        owner_user = (found.metadata or {}).get("user_id")
        forms = self.tombstoned_forms(owner_user)
        if forms and carried_form(
            found.content, found.metadata, forms
        ) is not None:
            logger.warning(
                "Read withheld memory %s of user_id=%s: it carries a "
                "forgotten value, so it escaped the forget",
                memory_id, owner_user,
            )
            return None
        return found

    def forget(
        self, agent_name: str, user_id: Optional[str], fact_key: str,
        *, barrier_seq: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Forget ``fact_key`` for the user: the user's request, made by
        any agent that serves the user (``deletion.forget_fact``, which
        returns the report). Raises ``ValueError`` without a user or a
        slot, ``RuntimeError`` without a tombstone store, and whatever
        the provider raises.

        Holds a barrier sequence until it returns, so a retrieval
        accepted after it sees no deleted row. ``barrier_seq`` is one
        already acquired (the kernel stamps it when the request is
        accepted); without it the forget acquires its own. It first
        waits for the user's writes accepted before it: those through
        ``barrier_seq - 1``, never a fresh snapshot, which would hold
        its own sequence and wait on itself until the timeout.
        """
        scope = self.resolver.canonical(user_id) if user_id else None
        if barrier_seq is None:
            barrier_seq = (
                self.barrier.acquire(scope) if self.barrier and scope else 0
            )
        success = False
        try:
            # Checked inside the hold, so a sequence the kernel stamped
            # is released on every path (a stuck one would hold every
            # later retrieval of the user until the barrier's timeout).
            if not scope:
                raise ValueError("a forget needs the user's id")
            if not fact_key:
                raise ValueError(
                    "a forget needs the fact's slot (fact_key)"
                )
            if self.tombstones is None:
                raise RuntimeError("this pipeline has no tombstone store")
            if barrier_seq:
                self.selector.await_pending_writes(scope, barrier_seq - 1)
            with self.usage_tag(scope):
                report = forget_fact(
                    self.provider, self.tombstones, scope, agent_name,
                    fact_key,
                )
            success = True
            return report
        finally:
            if self.barrier and scope:
                self.barrier.release(scope, barrier_seq, success=success)

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
        caller's current session (``build_block``).

        ``diagnostics["retrieval_error"]`` is None when both fetches
        succeeded, else which failed and why (``retrieval_error``). The
        block is still built from whatever was fetched; a caller that
        scores it must check this key, since a failed fetch otherwise
        looks like an empty store."""
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
            "retrieval_error": None,
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
        # Reported, not dropped: a failed fetch left an empty block that
        # passed deletion and privacy probes (BENCHMARK_V2.md, Amendment
        # 2). The selector's two keys become this one.
        diagnostics["retrieval_error"] = retrieval_error(
            retrieval.pop("error", None), retrieval.pop("shared_error", None)
        )
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
