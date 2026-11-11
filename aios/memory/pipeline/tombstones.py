"""
Tombstones: what a user asked to forget, and how a row is matched
against it (docs/DELETION_AND_SUPERSESSION.md).

A tombstone holds one value of a forgotten fact: the user, the slot
(``fact_key``), the value and its aliases (its forms), the forgotten
statements' ``provenance_event`` ids, the agent that asked and when. A
row whose text carries a form, under the scorer's matcher
(``matching``), is a carrier. The slot's forgotten statements are also
kept apart, per slot, where a lift never removes them: a replay of a
statement the user forgot lifts nothing, even after a restatement and
a second forget of the slot.

``TombstoneStore`` keeps them in a SQLite file, read on every call, so
every pipeline over one store sees the same tombstones: the kernel
builds a pipeline per request, and a replicated cell runs four agents
over one store. Without a path it keeps them in memory, for one
process's tests and library-only use.
"""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .matching import match_forms, normalize
from .memory_formatter import format_memory


@dataclass(frozen=True)
class Tombstone:
    """One forgotten value of a user's fact."""

    user_id: str
    fact_key: str
    value: str
    aliases: Tuple[str, ...] = ()
    events: Tuple[str, ...] = ()
    requested_by: str = ""
    created_at: str = ""

    @property
    def forms(self) -> List[str]:
        """The value, then its aliases."""
        return [self.value, *self.aliases]


def _json_list(raw: Any) -> List[str]:
    """A list of strings from a JSON string or a list; [] otherwise."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw if item]
    return []


def statement_forms(
    metadata: Optional[Dict[str, Any]],
) -> Optional[Tuple[str, List[str]]]:
    """``(value, aliases)`` a row states: the ``value`` of its
    ``structured`` JSON and its ``value_aliases`` (benchmark v2,
    Amendment 4). None for a row that states no value (a base row, a
    conversation, a row without ``structured``)."""
    metadata = metadata or {}
    structured = metadata.get("structured")
    if isinstance(structured, str):
        try:
            structured = json.loads(structured)
        except ValueError:
            return None
    if not isinstance(structured, dict):
        return None
    value = structured.get("value")
    if not isinstance(value, str) or not value.strip():
        return None
    return value, _json_list(metadata.get("value_aliases"))


def carried_form(
    content: Optional[str],
    metadata: Optional[Dict[str, Any]],
    forms: Iterable[str],
) -> Optional[str]:
    """The first form a row's text carries, or None. The text is the
    stored content and its formatted text (``format_memory``), since the
    scorer reads the formatted block; the two differ for JSON rows."""
    forms = [form for form in forms if form]
    if not forms:
        return None
    found = match_forms(content, forms)
    if found:
        return found
    formatted = format_memory(content or "", metadata or {})
    if formatted != content:
        return match_forms(formatted, forms)
    return None


class TombstoneStore:
    """The tombstones of one store.

    Args:
        path: The SQLite file. ``None`` keeps the tombstones in memory,
            visible only to this object.
    """

    _SCHEMA = (
        "CREATE TABLE IF NOT EXISTS tombstones ("
        " user_id TEXT NOT NULL,"
        " fact_key TEXT NOT NULL,"
        " value_key TEXT NOT NULL,"
        " value TEXT NOT NULL,"
        " aliases TEXT NOT NULL,"
        " events TEXT NOT NULL,"
        " requested_by TEXT NOT NULL,"
        " created_at TEXT NOT NULL,"
        " PRIMARY KEY (user_id, fact_key, value_key))"
    )
    # Every statement of a slot a forget has covered, kept across lifts.
    _EVENTS_SCHEMA = (
        "CREATE TABLE IF NOT EXISTS forgotten_events ("
        " user_id TEXT NOT NULL,"
        " fact_key TEXT NOT NULL,"
        " event TEXT NOT NULL,"
        " PRIMARY KEY (user_id, fact_key, event))"
    )

    def __init__(self, path: Optional[str] = None):
        self.path = os.path.abspath(path) if path else None
        self._lock = threading.RLock()
        self._memory: Optional[sqlite3.Connection] = None
        if self.path:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        else:
            self._memory = sqlite3.connect(
                ":memory:", check_same_thread=False
            )
        with self._connect() as connection:
            connection.execute(self._SCHEMA)
            connection.execute(self._EVENTS_SCHEMA)
            # A file written before the table existed: its tombstones'
            # events are the forgotten statements.
            for user_id, fact_key, events in connection.execute(
                "SELECT user_id, fact_key, events FROM tombstones"
            ).fetchall():
                connection.executemany(
                    "INSERT OR IGNORE INTO forgotten_events "
                    "VALUES (?, ?, ?)",
                    [(user_id, fact_key, e) for e in _json_list(events)],
                )

    @contextmanager
    def _connect(self):
        """One transaction: committed on success, rolled back on error.
        A file store opens a connection per call, so every reader sees
        every writer's last commit."""
        with self._lock:
            connection = self._memory or sqlite3.connect(
                self.path, timeout=30
            )
            try:
                with connection:
                    yield connection
            finally:
                if connection is not self._memory:
                    connection.close()

    def record(
        self,
        user_id: str,
        fact_key: str,
        values: Iterable[Tuple[str, Iterable[str]]],
        events: Iterable[str] = (),
        requested_by: str = "",
    ) -> List[Tombstone]:
        """Tombstone each ``(value, aliases)`` of the user's fact. A
        value already tombstoned (same normalized value) gains the new
        aliases and events. The events are also kept as the slot's
        forgotten statements (``forgotten_events``). Returns the fact's
        tombstones."""
        events = sorted({str(e) for e in events if e})
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.executemany(
                "INSERT OR IGNORE INTO forgotten_events VALUES (?, ?, ?)",
                [(user_id, fact_key, event) for event in events],
            )
            for value, aliases in values:
                key = normalize(value)
                if not key:
                    continue
                row = connection.execute(
                    "SELECT aliases, events FROM tombstones WHERE "
                    "user_id = ? AND fact_key = ? AND value_key = ?",
                    (user_id, fact_key, key),
                ).fetchone()
                old_aliases, old_events = (
                    (_json_list(row[0]), _json_list(row[1]))
                    if row else ([], [])
                )
                merged_aliases = list(dict.fromkeys(
                    [*old_aliases, *[a for a in aliases if a]]
                ))
                merged_events = sorted({*old_events, *events})
                connection.execute(
                    "INSERT OR REPLACE INTO tombstones VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, fact_key, key, value,
                     json.dumps(merged_aliases), json.dumps(merged_events),
                     requested_by, now),
                )
        return [t for t in self.entries(user_id) if t.fact_key == fact_key]

    def entries(self, user_id: Optional[str]) -> List[Tombstone]:
        """The user's tombstones, by slot and value."""
        if not user_id:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT user_id, fact_key, value, aliases, events, "
                "requested_by, created_at FROM tombstones "
                "WHERE user_id = ? ORDER BY fact_key, value_key",
                (user_id,),
            ).fetchall()
        return [
            Tombstone(
                user_id=row[0], fact_key=row[1], value=row[2],
                aliases=tuple(_json_list(row[3])),
                events=tuple(_json_list(row[4])),
                requested_by=row[5], created_at=row[6],
            )
            for row in rows
        ]

    def forgotten_events(self, user_id: str, fact_key: str) -> List[str]:
        """Every statement of the user's slot a forget covered, sorted,
        including those of tombstones a restatement has since lifted."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event FROM forgotten_events WHERE user_id = ? "
                "AND fact_key = ? ORDER BY event",
                (user_id, fact_key),
            ).fetchall()
        return [row[0] for row in rows]

    def forms(self, user_id: Optional[str]) -> List[str]:
        """Every tombstoned form of the user, values first per value."""
        forms: List[str] = []
        for tombstone in self.entries(user_id):
            forms.extend(form for form in tombstone.forms if form)
        return list(dict.fromkeys(forms))

    def lift(
        self,
        user_id: str,
        fact_key: str,
        value: str,
        event: Optional[str] = None,
    ) -> List[str]:
        """The user stated ``fact_key`` again with ``value``: lift every
        tombstone of the slot whose value or an alias normalizes to
        ``value``. Only a new statement lifts: a statement without an
        ``event`` cannot be told from a replay, and one whose event is
        among the slot's forgotten statements (``forgotten_events``,
        which a lift keeps) is a replay; neither lifts anything.
        Returns the lifted values."""
        key = normalize(value)
        if not key or not event:
            return []
        if event in self.forgotten_events(user_id, fact_key):
            return []
        lifted = []
        for tombstone in self.entries(user_id):
            if tombstone.fact_key != fact_key:
                continue
            if key in {normalize(form) for form in tombstone.forms}:
                lifted.append(tombstone.value)
        if lifted:
            with self._connect() as connection:
                connection.executemany(
                    "DELETE FROM tombstones WHERE user_id = ? AND "
                    "fact_key = ? AND value_key = ?",
                    [(user_id, fact_key, normalize(v)) for v in lifted],
                )
        return lifted
