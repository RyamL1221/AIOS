"""
Complete deletion and supersession (docs/DELETION_AND_SUPERSESSION.md).

- ``forget_fact`` forgets one fact of a user: it records the tombstone
  first, then deletes every row of the slot and every carrier of its
  forms, of any agent, and scrubs the provider's history.
- ``after_write`` is what a write or an update does next for the user:
  a restatement lifts its value's tombstone, every carrier of a
  tombstoned form is swept, and, unless the write itself was swept, a
  later statement retires the earlier rows of its slot.

Both act on the provider directly, across owners: a forget and a
supersession are the user's, not an agent's (Decision 1).
``MemoryPipeline`` calls them inside its barrier hold, so a retrieval
accepted after a forget or a write sees their result.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from ..providers.base import Candidate, MemoryProvider
from .matching import normalize
from .settings import PipelineSettings
from .tombstones import TombstoneStore, carried_form, statement_forms
from .visibility import Visibility

logger = logging.getLogger(__name__)

# A listing's size: more rows than any user's store holds, so a listing
# is complete. One that reaches it fails rather than act on part of the
# store.
LIST_TOP_K = 10_000

# Why a forget deleted a row.
REASON_FACT_KEY = "fact_key"
REASON_VALUE = "value"
REASON_ALIAS = "alias"

# The supersession marks: set only by the library, never by an agent.
MARKS = ("superseded_by", "superseded_session")


class ListingLimitError(RuntimeError):
    """A partition listing reached ``LIST_TOP_K``: it may be partial."""


def partition(provider: MemoryProvider, scope: str) -> List[Candidate]:
    """Every row in the user's partition, of every agent, in storage
    order. Raises ``ListingLimitError`` on a listing that may be
    partial."""
    found = provider.list(scope, LIST_TOP_K)
    if len(found) >= LIST_TOP_K:
        raise ListingLimitError(
            f"the listing of {scope!r} reached its limit ({LIST_TOP_K})"
        )
    return [
        row for row in found
        if (row.metadata or {}).get("user_id", "") == scope
    ]


def _merge_value(
    values: Dict[str, Tuple[str, List[str]]], value: str, aliases
) -> str:
    """Add ``(value, aliases)`` to ``values``, keyed by the normalized
    value, keeping the first spelling and every alias once."""
    key = normalize(value)
    old_value, old_aliases = values.get(key, (value, []))
    values[key] = (
        old_value, list(dict.fromkeys([*old_aliases, *aliases])),
    )
    return key


def forget_fact(
    provider: MemoryProvider,
    tombstones: TombstoneStore,
    scope: str,
    agent_name: str,
    fact_key: str,
) -> Dict[str, Any]:
    """Forget ``fact_key`` for the user ``scope``; returns the report.

    The fact's values are the ``structured`` values and
    ``value_aliases`` of every row of the slot, of any agent, and those
    of any tombstone the slot already has. They are tombstoned before
    any delete, so a forget that fails partway still guards every read.
    Every row of the slot and every carrier of a form is then deleted,
    whoever owns it, and the provider's history is scrubbed.

    The report names ids and owners, never another agent's text
    (Decision 1): ``values`` holds only the values the caller may read.
    """
    rows = partition(provider, scope)
    values: Dict[str, Tuple[str, List[str]]] = {}
    # The spelling of each value as a row the caller may read states
    # it: another agent's private row may spell the same value its own
    # way, and the report never repeats another agent's text.
    readable: Dict[str, str] = {}
    events: List[str] = []
    for row in rows:
        metadata = row.metadata or {}
        if metadata.get("fact_key") != fact_key:
            continue
        if metadata.get("provenance_event"):
            events.append(str(metadata["provenance_event"]))
        stated = statement_forms(metadata)
        if stated is None:
            continue
        key = _merge_value(values, *stated)
        if Visibility.can_read(agent_name, metadata):
            readable.setdefault(key, stated[0])
    for tombstone in tombstones.entries(scope):
        if tombstone.fact_key == fact_key:
            _merge_value(values, tombstone.value, tombstone.aliases)
            events.extend(tombstone.events)

    if values:
        tombstones.record(
            scope, fact_key, values.values(), events,
            requested_by=agent_name,
        )
    # Values first, so a row that carries a value is counted by it.
    forms = [value for value, _ in values.values()]
    forms += [a for _, aliases in values.values() for a in aliases]
    value_keys = set(values)

    deleted: List[Dict[str, str]] = []
    not_found: List[str] = []
    for row in rows:
        metadata = row.metadata or {}
        if metadata.get("fact_key") == fact_key:
            reason = REASON_FACT_KEY
        else:
            form = carried_form(row.content, metadata, forms)
            if form is None:
                continue
            reason = (
                REASON_VALUE if normalize(form) in value_keys
                else REASON_ALIAS
            )
        owner_user = metadata.get("user_id") or scope
        if provider.delete(row.memory_id, owner_user):
            deleted.append({
                "memory_id": row.memory_id,
                "owner_agent": metadata.get("owner_agent", ""),
                "reason": reason,
            })
        else:
            not_found.append(row.memory_id)

    gone = {entry["memory_id"] for entry in deleted}
    kept = [
        row.memory_id for row in rows
        if row.memory_id not in gone and row.memory_id not in not_found
    ]
    scrubbed = provider.scrub_history(scope, forms, sorted(gone), kept)
    logger.info(
        "forget: agent=%s user_id=%s fact_key=%s values=%d forms=%d "
        "deleted=%d scrubbed=%s",
        agent_name, scope, fact_key, len(values), len(forms),
        len(deleted), scrubbed,
    )
    return {
        "user_id": scope,
        "fact_key": fact_key,
        "requested_by": agent_name,
        "listed": len(rows),
        "values_count": len(values),
        "forms_count": len(forms),
        "values": sorted(readable.values()),
        "deleted": deleted,
        "not_found": not_found,
        "scrubbed": scrubbed,
    }


def _supersede(
    provider: MemoryProvider,
    scope: str,
    metadata: Dict[str, Any],
    rows: List[Candidate],
) -> List[str]:
    """Mark the earlier rows of the write's slot retired; their ids.

    Only after a write that stored a row (one of its
    ``provenance_event`` is listed): a statement Mem0 stored nothing for
    retires nothing. A row already marked keeps its mark."""
    fact_key = metadata.get("fact_key")
    event = metadata.get("provenance_event")
    if not any(
        (row.metadata or {}).get("provenance_event") == event
        for row in rows
    ):
        return []
    marks: Dict[str, Any] = {"superseded_by": event}
    if metadata.get("session") is not None:
        marks["superseded_session"] = metadata["session"]
    retired = []
    for row in rows:
        row_metadata = row.metadata or {}
        if (
            row_metadata.get("fact_key") != fact_key
            or row_metadata.get("provenance_event") == event
            or row_metadata.get("superseded_by")
        ):
            continue
        owner_user = row_metadata.get("user_id") or scope
        if provider.update_metadata(row.memory_id, owner_user, marks):
            retired.append(row.memory_id)
    return retired


def after_write(
    provider: MemoryProvider,
    tombstones: Optional[TombstoneStore],
    settings: PipelineSettings,
    scope: str,
    metadata: Optional[Dict[str, Any]],
    *,
    memory_id: Optional[str] = None,
    supersede: bool = True,
) -> Dict[str, Any]:
    """What a successful write (or, with ``supersede`` False, an update)
    of a note with ``metadata`` does next for the user ``scope``.

    1. A restatement (a write of a tombstoned slot whose ``structured``
       value is the value or an alias, from a statement other than the
       forgotten ones) lifts that value's tombstone.
    2. Every carrier of a remaining tombstoned form is deleted
       (``swept``), whoever wrote it, and the history is scrubbed. The
       write is ``suppressed`` when its own rows were all swept.
    3. With ``supersession: exclude``, a write with a ``fact_key`` and a
       ``provenance_event`` that was not suppressed retires the earlier
       rows of its slot (``retired``).
    """
    outcome: Dict[str, Any] = {
        "swept": [], "retired": [], "lifted": [], "suppressed": False,
    }
    metadata = metadata or {}
    fact_key = metadata.get("fact_key")
    event = metadata.get("provenance_event")
    if tombstones is not None and fact_key:
        stated = statement_forms(metadata)
        if stated is not None and tombstones.lift(
            scope, fact_key, stated[0], event=event,
        ):
            # The write's own value, not the tombstone's spelling of it,
            # which may come from another agent's private row.
            outcome["lifted"] = [stated[0]]
    forms = tombstones.forms(scope) if tombstones is not None else []
    marking = bool(
        supersede and settings.supersession == "exclude"
        and fact_key and event
    )
    if not forms and not marking:
        return outcome

    rows = partition(provider, scope)
    swept: List[Dict[str, str]] = []
    if forms:
        for row in rows:
            row_metadata = row.metadata or {}
            if carried_form(row.content, row_metadata, forms) is None:
                continue
            if provider.delete(
                row.memory_id, row_metadata.get("user_id") or scope
            ):
                swept.append({
                    "memory_id": row.memory_id,
                    "owner_agent": row_metadata.get("owner_agent", ""),
                })
        gone = {entry["memory_id"] for entry in swept}
        kept = [row.memory_id for row in rows if row.memory_id not in gone]
        outcome["scrubbed"] = provider.scrub_history(
            scope, forms, sorted(gone), kept,
        )
        own = {
            row.memory_id for row in rows
            if event and (row.metadata or {}).get("provenance_event") == event
        } or ({memory_id} if memory_id else set())
        outcome["suppressed"] = bool(own) and own <= gone
        rows = [row for row in rows if row.memory_id not in gone]
        if swept:
            logger.info(
                "sweep: user_id=%s deleted %d rows carrying a forgotten "
                "value after a write (event %s)",
                scope, len(swept), event,
            )
    outcome["swept"] = swept
    if marking and not outcome["suppressed"]:
        outcome["retired"] = _supersede(provider, scope, metadata, rows)
    return outcome
