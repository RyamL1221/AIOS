"""Complete deletion and supersession in the memory library
(docs/DELETION_AND_SUPERSESSION.md, NeurIPS Subtask 15 step 1).

A forget deletes every row of a user's fact and every carrier of its
forms, whoever owns it, after it records a tombstone. The tombstone
sweeps any later re-write of a form until the user states the fact
again, and the guard keeps an escaped carrier out of every read path.
With ``supersession: exclude`` a later statement retires the earlier
rows of its slot, which selection never picks.

Everything runs the library on the in-memory provider. The barrier
tests use ``GatedStore`` (test_list_and_delete.py), which is not
synchronous: the in-memory provider bypasses every barrier wait.
"""
import importlib.util
import json
import logging
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import aios.memory.pipeline as pipeline_package
import aios.memory.pipeline.deletion as deletion_module
import aios.memory.pipeline.matching as matching
import aios.memory.pipeline.tombstones as tombstone_module
from aios.memory.note import MemoryNote
from aios.memory.pipeline import (
    LIST_TOP_K,
    MARKS,
    SUPERSESSION_MODES,
    ListingLimitError,
    MemoryPipeline,
    PipelineSettings,
    TombstoneStore,
    carried_form,
    note_from_request,
    statement_forms,
)
from aios.memory.pipeline.memory_formatter import format_memory
from aios.memory.providers.base import Candidate, ProviderError
from aios.memory.providers.in_house import InHouseProvider
from tests.modules.memory.test_list_and_delete import (
    ASSISTANT,
    USER,
    WAIT,
    WRITER,
    Background,
    GatedStore,
    ids,
    store,
    write,
)

TASK = "task_agent"
CALENDAR = "calendar_agent"
SLOT = "lawyer"
VALUE = "Greta Sandvik"
ALIAS = "Sandvik"
HOME = "home"
EXCLUDE = PipelineSettings(supersession="exclude")
SELECTOR = "aios.memory.pipeline.selector"
FACADE = "aios.memory.pipeline.facade"


def stated(value, event, fact_key=SLOT, aliases=(ALIAS,), session=None):
    """A v2 statement's metadata (Cerebrum ``v2_write_metadata``): the
    slot, ``structured`` and ``value_aliases`` as JSON strings, and the
    event's id as ``provenance_event``."""
    metadata = {
        "fact_key": fact_key,
        "event_type": "add",
        "structured": json.dumps({
            "event_type": "add", "fact_key": fact_key, "value": value,
        }, sort_keys=True),
        "value_aliases": json.dumps(list(aliases)),
        "provenance_event": event,
    }
    if session is not None:
        metadata["session"] = session
    return metadata


def home(value, event, session):
    """A statement of where the user lives, a slot without aliases."""
    return stated(value, event, fact_key=HOME, aliases=(), session=session)


def note(agent, content, policy="shared", memory_type="profile",
         **metadata):
    """The note ``write`` sends, for a write that needs more than
    ``write`` passes (an outcome, a barrier sequence)."""
    return note_from_request({"content": content, "metadata": {
        "owner_agent": agent, "user_id": USER,
        "memory_type": memory_type, "sharing_policy": policy,
        **metadata,
    }})


def written(pipeline, agent, content, **metadata):
    """One write through the library: its id and its outcome."""
    outcome = {}
    memory_id = pipeline.write(
        agent, USER, note(agent, content, **metadata), outcome=outcome,
    )
    return memory_id, outcome


def plant(provider, agent, content, memory_type="calendar", **metadata):
    """A shared row stored by the provider directly, so no sweep runs:
    a carrier that escaped the forget."""
    return provider.add(MemoryNote(content=content, metadata={
        "owner_agent": agent, "user_id": USER,
        "memory_type": memory_type, "sharing_policy": "shared",
        "created_at": "2026-11-10T00:00:00+00:00", **metadata,
    }))


def stored(provider, user=USER):
    """The user's stored rows, by id."""
    return {row.memory_id: row for row in provider.list(user, LIST_TOP_K)}


def deleted(report):
    """A forget's deleted rows: id -> (owner, reason)."""
    return {
        entry["memory_id"]: (entry["owner_agent"], entry["reason"])
        for entry in report["deleted"]
    }


def forgotten_store(provider=None, settings=None):
    """A provider and a pipeline over it whose user stated ``VALUE``
    (alias ``ALIAS``, event e1) for ``SLOT`` and then forgot it."""
    provider = provider or store()
    pipeline = MemoryPipeline(provider, settings)
    write(pipeline, WRITER, "My lawyer is Greta Sandvik.",
          **stated(VALUE, "e1"))
    pipeline.forget(WRITER, USER, SLOT)
    assert stored(provider) == {}
    return provider, pipeline


def warned(caplog, logger, memory_id):
    """The WARNINGs ``logger`` logged that name ``memory_id``."""
    return [
        record.getMessage() for record in caplog.records
        if record.name == logger and record.levelno == logging.WARNING
        and memory_id in record.getMessage()
    ]


# --- the matcher, shared with the scorer -------------------------------


def test_the_library_matches_with_its_one_matcher(monkeypatch):
    """The forget, the sweep and the guard all use the matcher module
    the scorer re-exports (``aios.memory.pipeline.matching``), not a
    copy: its functions are theirs, and replacing its ``value_in``
    changes what a row carries."""
    assert tombstone_module.match_forms is matching.match_forms
    assert tombstone_module.normalize is matching.normalize
    assert deletion_module.normalize is matching.normalize
    assert pipeline_package.match_forms is matching.match_forms
    assert pipeline_package.value_in is matching.value_in

    calls = []

    def value_in(text, value):
        calls.append((text, value))
        return value == "anything"

    monkeypatch.setattr(matching, "value_in", value_in)
    assert carried_form(VALUE, {}, [VALUE, "anything"]) == "anything"
    assert (VALUE, VALUE) in calls


def test_the_matcher_loads_by_path_as_the_scorer_loads_it():
    """The scorer loads the matcher by its file path, outside the
    package, so the file must stand alone (standard library only) and
    match as the library does."""
    spec = importlib.util.spec_from_file_location(
        "scorer_matching", matching.__file__
    )
    standalone = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(standalone)
    assert standalone is not matching
    for text, forms in (
        ("Mail greta.sandvik now.", [VALUE]),
        ("Call Sandvik.", [VALUE, ALIAS]),
        ("We hiked near Sandviken.", [ALIAS]),
        ("Zoë Brandt called.", ["zoe brandt"]),
    ):
        assert standalone.match_forms(text, forms) \
            == matching.match_forms(text, forms)
    assert standalone.normalize("Zoë  Brandt-Sandvik") == "zoe brandt sandvik"


def test_carried_form_reads_the_stored_and_the_formatted_text():
    """A row's text is its stored content and its formatted text: the
    raw JSON escapes "Zoë Brandt", which only ``format_memory``'s
    sentence spells as the block does, and a key the template drops is
    still found in the content. The first form found wins."""
    profile = {"memory_type": "profile"}
    content = json.dumps({"name": "Zoë Brandt"})
    assert "\\u00eb" in content
    assert matching.match_forms(content, ["Zoë Brandt"]) is None
    assert matching.value_in(format_memory(content, profile), "zoe brandt")
    assert carried_form(content, profile, ["Zoë Brandt"]) == "Zoë Brandt"

    tools = json.dumps({"tools": "Jira"})
    assert not matching.value_in(format_memory(tools, profile), "tools")
    assert carried_form(tools, profile, ["tools"]) == "tools"

    assert carried_form("Call Greta Sandvik.", {}, [ALIAS, VALUE]) == ALIAS
    assert carried_form("Mail greta.sandvik now.", {}, [VALUE]) == VALUE
    assert carried_form("We hiked near Sandviken.", {}, [ALIAS]) is None
    assert carried_form("Call Sandvik.", {}, ["", None]) is None


# --- what a row states -------------------------------------------------


def test_statement_forms_reads_the_structured_value_and_its_aliases():
    """A row states its ``structured`` value with its ``value_aliases``
    (JSON strings, or a list); a base row, a row without ``structured``
    and bad JSON state no value."""
    assert statement_forms(stated(VALUE, "e1")) == (VALUE, [ALIAS])
    as_list = dict(stated(VALUE, "e1"), value_aliases=[ALIAS, ""])
    assert statement_forms(as_list) == (VALUE, [ALIAS])
    assert statement_forms(stated(VALUE, "e1", aliases=())) == (VALUE, [])
    bad_aliases = dict(stated(VALUE, "e1"), value_aliases="[oops")
    assert statement_forms(bad_aliases) == (VALUE, [])
    unaliased = stated(VALUE, "e1")
    del unaliased["value_aliases"]
    assert statement_forms(unaliased) == (VALUE, [])
    as_dict = {"structured": {"fact_key": SLOT, "value": VALUE}}
    assert statement_forms(as_dict) == (VALUE, [])

    base = {"fact_key": "base_profile", "structured": json.dumps(
        {"user_name": "Alice", "preferred_language": "Rust"}
    )}
    assert statement_forms(base) is None
    assert statement_forms(stated(None, "e1")) is None
    assert statement_forms(stated("  ", "e1")) is None
    assert statement_forms({"fact_key": SLOT, "value_aliases": "[]"}) \
        is None
    assert statement_forms(None) is None
    for bad in ("{not json", "[1, 2]", '"Greta Sandvik"'):
        assert statement_forms(dict(stated(VALUE, "e1"), structured=bad)) \
            is None


# --- the tombstone store -----------------------------------------------


def test_recording_a_value_twice_merges_its_aliases_and_events():
    """A value tombstoned again for the slot (equal once normalized)
    gains the new aliases and events; another value, slot or user is a
    tombstone of its own."""
    tombstones = TombstoneStore()
    tombstones.record(USER, SLOT, [(VALUE, [ALIAS])], ["e1"],
                      requested_by=WRITER)
    entries = tombstones.record(
        USER, SLOT, [("greta-SANDVIK", ["G. Sandvik", ALIAS])], ["e2"],
        requested_by=TASK,
    )
    assert len(entries) == 1
    (tombstone,) = entries
    assert matching.normalize(tombstone.value) == "greta sandvik"
    assert tombstone.aliases == (ALIAS, "G. Sandvik")
    assert tombstone.events == ("e1", "e2")
    assert tombstone.forms == [tombstone.value, ALIAS, "G. Sandvik"]

    tombstones.record(USER, SLOT, [("Henrik Olsen", [])], ["e3"])
    tombstones.record(USER, "pet", [(VALUE, [])])
    tombstones.record("bob", SLOT, [(VALUE, [])])
    assert len(tombstones.entries(USER)) == 3
    assert len(tombstones.entries("bob")) == 1
    assert tombstones.entries(None) == []


def test_forms_are_every_tombstoned_value_and_alias_of_the_user():
    """``forms`` lists each tombstoned value of the user, then its
    aliases, across slots, each once; another user has none."""
    tombstones = TombstoneStore()
    tombstones.record(USER, SLOT, [(VALUE, [ALIAS])], ["e1"])
    tombstones.record(USER, "pet", [("Mochi", ["Mochi-cat"]),
                                    ("Biscuit", [VALUE])], ["e2"])
    forms = tombstones.forms(USER)
    assert sorted(forms) == sorted(
        [VALUE, ALIAS, "Mochi", "Mochi-cat", "Biscuit"]
    )
    assert forms.index(VALUE) < forms.index(ALIAS)
    assert forms.index("Mochi") < forms.index("Mochi-cat")
    assert tombstones.forms("bob") == []
    assert tombstones.forms(None) == []


@pytest.mark.parametrize("restated", [
    VALUE, "greta  SANDVIK", "Greta-Sandvik", ALIAS, "sandvik",
])
def test_lift_by_the_value_or_an_alias(restated):
    """A restatement of the slot lifts its tombstone when the stated
    value, normalized, is the tombstoned value or one of its aliases;
    the same value under another slot stays tombstoned."""
    tombstones = TombstoneStore()
    tombstones.record(USER, SLOT, [(VALUE, [ALIAS])], ["e1"])
    tombstones.record(USER, "contact", [(VALUE, [])], ["e9"])
    assert tombstones.lift(USER, SLOT, restated, event="e2") == [VALUE]
    assert [t.fact_key for t in tombstones.entries(USER)] == ["contact"]


def test_lift_refuses_a_replay_and_other_values():
    """A forgotten statement's own event is a replay and lifts nothing;
    neither does another value, a longer word, another slot or user, or
    no value. A new statement then lifts it."""
    tombstones = TombstoneStore()
    tombstones.record(USER, SLOT, [(VALUE, [ALIAS])], ["e1", "e2"])
    assert tombstones.lift(USER, SLOT, VALUE, event="e1") == []
    assert tombstones.lift(USER, SLOT, ALIAS, event="e2") == []
    for other in ("Henrik Olsen", "Sandviken", "Greta Sandvik Jr", ""):
        assert tombstones.lift(USER, SLOT, other, event="e3") == []
    assert tombstones.lift(USER, "contact", VALUE, event="e3") == []
    assert tombstones.lift("bob", SLOT, VALUE, event="e3") == []
    assert tombstones.forms(USER) == [VALUE, ALIAS]
    assert tombstones.lift(USER, SLOT, VALUE, event="e3") == [VALUE]
    assert tombstones.forms(USER) == []


def test_stores_on_one_file_share_tombstones_and_memory_is_isolated(
        tmp_path):
    """Two stores on one SQLite file see each other's records and lifts,
    and a store reopened on it later still has them; an in-memory store
    sees only its own."""
    path = tmp_path / "state" / "tombstones.sqlite"
    first, second = TombstoneStore(str(path)), TombstoneStore(str(path))
    assert path.is_file()
    first.record(USER, SLOT, [(VALUE, [ALIAS])], ["e1"],
                 requested_by=WRITER)
    assert second.forms(USER) == [VALUE, ALIAS]
    assert second.entries(USER)[0].requested_by == WRITER
    assert second.lift(USER, SLOT, ALIAS, event="e2") == [VALUE]
    assert first.entries(USER) == []
    second.record(USER, "pet", [("Mochi", [])])
    assert TombstoneStore(str(path)).forms(USER) == ["Mochi"]

    one, other = TombstoneStore(), TombstoneStore()
    one.record(USER, SLOT, [(VALUE, [ALIAS])], ["e1"])
    assert one.forms(USER) == [VALUE, ALIAS]
    assert other.forms(USER) == []
    assert one.path is None


def test_pipelines_on_one_tombstone_file_share_a_forget(tmp_path):
    """Pipelines over one store whose tombstone stores share a file (a
    replicated cell's agents) share a forget: the other agent's write
    of the value is swept and its guard drops an escaped carrier."""
    path = str(tmp_path / "tombstones.sqlite")
    provider = store()
    one = MemoryPipeline(provider, tombstones=TombstoneStore(path))
    other = MemoryPipeline(provider, tombstones=TombstoneStore(path))
    write(one, WRITER, "My lawyer is Greta Sandvik.", **stated(VALUE, "e1"))
    one.forget(WRITER, USER, SLOT)

    echo, outcome = written(other, TASK, "Meeting with Greta Sandvik.",
                            memory_type="task_context", fact_key="meeting")
    assert (echo, outcome["suppressed"]) == ("", True)
    planted = plant(provider, CALENDAR, "Call Sandvik.")
    candidates, diagnostics = other.retrieve(ASSISTANT, USER, "Call Sandvik")
    assert candidates == []
    assert diagnostics["tombstoned_rows"] == [planted]


# --- the forget --------------------------------------------------------


def test_forget_deletes_every_carrier_of_the_fact():
    """A forget deletes the slot's rows (a reworded one too), another
    writer's echo, a row naming only an alias and a fold by the same
    writer, each with its owner and reason. It keeps rows that carry no
    form and other users' rows, and records the tombstone."""
    provider = store()
    pipeline = MemoryPipeline(provider)
    statement = write(pipeline, WRITER, "My lawyer is Greta Sandvik.",
                      **stated(VALUE, "e1"))
    reworded = write(pipeline, WRITER, "I have a lawyer for the lease.",
                     **stated(VALUE, "e1"))
    echo = write(pipeline, TASK, "Meeting with greta-sandvik on Friday.",
                 memory_type="task_context", fact_key="meeting")
    alias = write(pipeline, CALENDAR, "Call Sandvik about the lease.",
                  memory_type="calendar", fact_key="call")
    fold = write(pipeline, WRITER, "I live in Oslo, near Greta Sandvik.",
                 fact_key=HOME)
    kept = [
        write(pipeline, WRITER, "I live in Tallinn.", fact_key=HOME),
        write(pipeline, TASK, "We hiked near Sandviken.",
              memory_type="task_context", fact_key="trip"),
        write(pipeline, ASSISTANT, "User: hi\nAssistant: hello",
              policy="private", memory_type="conversation"),
    ]
    bobs = write(pipeline, WRITER, "My lawyer is Greta Sandvik.",
                 user="bob", **stated(VALUE, "b1"))

    report = pipeline.forget(TASK, USER, SLOT)

    assert deleted(report) == {
        statement: (WRITER, "fact_key"),
        reworded: (WRITER, "fact_key"),
        echo: (TASK, "value"),
        alias: (CALENDAR, "alias"),
        fold: (WRITER, "value"),
    }
    assert (report["values_count"], report["forms_count"]) == (1, 2)
    assert report["values"] == [VALUE]
    assert (report["user_id"], report["fact_key"]) == (USER, SLOT)
    assert (report["listed"], report["not_found"]) == (8, [])
    assert sorted(stored(provider)) == sorted(kept)
    assert list(stored(provider, "bob")) == [bobs]
    (tombstone,) = pipeline.tombstones.entries(USER)
    assert (
        tombstone.fact_key, tombstone.value, tombstone.aliases,
        tombstone.events, tombstone.requested_by,
    ) == (SLOT, VALUE, (ALIAS,), ("e1",), TASK)
    assert pipeline.tombstones.entries("bob") == []


@pytest.mark.parametrize("caller, policy, readable", [
    (ASSISTANT, "private", False),
    (WRITER, "private", True),
    (ASSISTANT, "shared", True),
])
def test_forget_reports_only_values_the_caller_may_read(caller, policy,
                                                        readable):
    """A forget by any agent deletes another agent's private statement,
    and counts its value, but names the value only to a caller that may
    read the row: otherwise it appears nowhere in the report."""
    provider = store()
    pipeline = MemoryPipeline(provider)
    secret = write(pipeline, WRITER,
                   "Just between us: my lawyer is Greta Sandvik.",
                   policy=policy, **stated(VALUE, "e1"))
    report = pipeline.forget(caller, USER, SLOT)
    assert deleted(report) == {secret: (WRITER, "fact_key")}
    assert (report["values_count"], report["forms_count"]) == (1, 2)
    assert report["values"] == ([VALUE] if readable else [])
    if not readable:
        text = json.dumps(report).casefold()
        for word in ("sandvik", "greta", "between us"):
            assert word not in text


def test_forget_names_a_value_only_as_the_caller_may_read_it():
    """When another agent's private row and a row the caller may read
    state one value in different spellings, the report names it as the
    readable row spells it: the private spelling is that agent's text."""
    provider = store()
    pipeline = MemoryPipeline(provider)
    write(pipeline, WRITER, "Just between us: my lawyer is Grétà Sandvik.",
          policy="private", **stated("Grétà  SANDVIK", "e1"))
    write(pipeline, TASK, "The lawyer is Greta Sandvik.",
          memory_type="task_context", **stated(VALUE, "e2"))
    report = pipeline.forget(TASK, USER, SLOT)
    assert len(report["deleted"]) == 2
    assert report["values_count"] == 1
    assert report["values"] == [VALUE]
    text = json.dumps(report, ensure_ascii=False)
    assert "Grétà" not in text and "SANDVIK" not in text


def test_a_second_forget_finds_its_forms_in_the_tombstone():
    """Once the slot's rows are gone, a second forget of the slot still
    knows the value and alias from its tombstone and deletes a carrier
    that appeared since; a store without that tombstone keeps it."""
    provider, pipeline = forgotten_store()
    late = plant(provider, CALENDAR, "Sandvik called back.")

    blank = MemoryPipeline(provider).forget(WRITER, USER, SLOT)
    assert (blank["values_count"], blank["deleted"]) == (0, [])
    assert late in stored(provider)

    report = pipeline.forget(WRITER, USER, SLOT)
    assert (report["values_count"], report["forms_count"]) == (1, 2)
    assert deleted(report) == {late: (CALENDAR, "alias")}
    assert stored(provider) == {}
    (tombstone,) = pipeline.tombstones.entries(USER)
    assert (tombstone.value, tombstone.aliases, tombstone.events) == (
        VALUE, (ALIAS,), ("e1",),
    )


class FailingDeleteStore(InHouseProvider):
    """The in-memory store, but its first ``delete`` fails, as a backend
    that errs partway through a forget."""

    def __init__(self):
        super().__init__()
        self.failures = 1

    def delete(self, memory_id, user_id):
        if self.failures:
            self.failures -= 1
            raise ProviderError("delete failed")
        return super().delete(memory_id, user_id)


def test_forget_records_the_tombstone_before_any_delete():
    """A forget whose first delete fails raises, but its tombstone is
    already recorded, so retrieval drops every carrier it left behind;
    its barrier sequence is released and a retry completes it."""
    provider = FailingDeleteStore()
    pipeline = MemoryPipeline(provider)
    statement = write(pipeline, WRITER, "My lawyer is Greta Sandvik.",
                      **stated(VALUE, "e1"))
    echo = write(pipeline, TASK, "Meeting with Greta Sandvik.",
                 memory_type="task_context", fact_key="meeting")

    with pytest.raises(ProviderError):
        pipeline.forget(WRITER, USER, SLOT)
    assert sorted(stored(provider)) == sorted([statement, echo])
    assert [t.value for t in pipeline.tombstones.entries(USER)] == [VALUE]
    candidates, diagnostics = pipeline.retrieve(
        ASSISTANT, USER, "Who is my lawyer?"
    )
    assert candidates == []
    assert diagnostics["tombstoned_rows"] == sorted([statement, echo])
    assert pipeline.barrier.stats()["total_pending"] == 0

    report = pipeline.forget(WRITER, USER, SLOT)
    assert sorted(deleted(report)) == sorted([statement, echo])
    assert stored(provider) == {}


@pytest.mark.parametrize("user_id, fact_key", [
    (None, SLOT), ("", SLOT), ("  ", SLOT), (USER, ""), (USER, None),
])
def test_forget_needs_the_user_and_the_slot(user_id, fact_key):
    """A forget without the user's id or the slot is refused: it records
    and deletes nothing, and holds no barrier sequence afterwards."""
    provider = store()
    pipeline = MemoryPipeline(provider)
    statement = write(pipeline, WRITER, "My lawyer is Greta Sandvik.",
                      **stated(VALUE, "e1"))
    with pytest.raises(ValueError):
        pipeline.forget(WRITER, user_id, fact_key)
    assert list(stored(provider)) == [statement]
    assert pipeline.tombstones.entries(USER) == []
    assert pipeline.barrier.stats()["total_pending"] == 0


def test_forget_needs_a_tombstone_store():
    """A pipeline built with ``tombstones=None`` cannot forget, since
    nothing would guard what it deleted: it raises and deletes
    nothing."""
    provider = store()
    pipeline = MemoryPipeline(provider, tombstones=None)
    statement = write(pipeline, WRITER, "My lawyer is Greta Sandvik.",
                      **stated(VALUE, "e1"))
    with pytest.raises(RuntimeError, match="tombstone"):
        pipeline.forget(WRITER, USER, SLOT)
    assert list(stored(provider)) == [statement]


@pytest.mark.parametrize("fact_key, with_store, error", [
    ("", True, ValueError),
    (SLOT, False, RuntimeError),
])
def test_a_refused_forget_releases_its_stamped_sequence(fact_key,
                                                        with_store, error):
    """A forget the kernel stamped for the user but that is refused (no
    slot, no tombstone store) releases that sequence, so a retrieval
    accepted after it does not wait for the barrier's timeout."""
    provider = GatedStore()
    pipeline = MemoryPipeline(
        provider, tombstones=TombstoneStore() if with_store else None,
    )
    stamped = pipeline.barrier.acquire(USER)
    with pytest.raises(error):
        pipeline.forget(WRITER, USER, fact_key, barrier_seq=stamped)
    assert pipeline.barrier.stats()["total_pending"] == 0
    later = Background(pipeline.retrieve, ASSISTANT, USER, "lawyer",
                       barrier_snapshot=pipeline.barrier.snapshot(USER))
    assert later.done(1)


class FullListing(InHouseProvider):
    """A store whose ``list`` returns ``size`` rows of the user, the
    first a statement of ``SLOT``; deletes are recorded."""

    def __init__(self, size):
        super().__init__()
        statement = Candidate("m0", "My lawyer is Greta Sandvik.", {
            "owner_agent": WRITER, "user_id": USER,
            "sharing_policy": "shared", **stated(VALUE, "e1"),
        })
        self.rows = [statement] + [
            Candidate(f"m{i}", f"filler {i}",
                      {"owner_agent": TASK, "user_id": USER})
            for i in range(1, size)
        ]
        self.deleted = []

    def list(self, user_id, top_k):
        return self.rows[:top_k]

    def delete(self, memory_id, user_id):
        self.deleted.append(memory_id)
        return True


def test_a_listing_at_its_limit_fails_the_forget():
    """A listing that returns ``LIST_TOP_K`` rows may be partial, so the
    forget fails before it records or deletes anything, and releases
    its sequence; one row fewer is a complete listing."""
    provider = FullListing(LIST_TOP_K)
    pipeline = MemoryPipeline(provider)
    with pytest.raises(ListingLimitError):
        pipeline.forget(WRITER, USER, SLOT)
    assert provider.deleted == []
    assert pipeline.tombstones.entries(USER) == []
    assert pipeline.barrier.stats()["total_pending"] == 0

    provider = FullListing(LIST_TOP_K - 1)
    pipeline = MemoryPipeline(provider)
    report = pipeline.forget(WRITER, USER, SLOT)
    assert provider.deleted == ["m0"]
    assert report["listed"] == LIST_TOP_K - 1
    assert [t.value for t in pipeline.tombstones.entries(USER)] == [VALUE]


def test_a_forget_that_finds_no_value_deletes_by_fact_key_only():
    """When no row of the slot states a value, the forget says so
    (``values_count`` 0), deletes the slot's rows only and records no
    tombstone, so a later write of anything is kept."""
    provider = store()
    pipeline = MemoryPipeline(provider)
    base = write(pipeline, WRITER, json.dumps({"user_name": "Alice"}),
                 fact_key=SLOT, provenance_event="b1",
                 structured=json.dumps({"user_name": "Alice"}))
    bare = write(pipeline, WRITER, "I have a lawyer.", fact_key=SLOT)
    other = write(pipeline, TASK, "Meeting with Greta Sandvik.",
                  memory_type="task_context", fact_key="meeting")

    report = pipeline.forget(WRITER, USER, SLOT)
    assert (report["values_count"], report["forms_count"]) == (0, 0)
    assert report["values"] == []
    assert deleted(report) == {
        base: (WRITER, "fact_key"), bare: (WRITER, "fact_key"),
    }
    assert list(stored(provider)) == [other]
    assert pipeline.tombstones.entries(USER) == []
    assert pipeline.tombstoned_forms(USER) == []
    echo, outcome = written(pipeline, TASK, "Alice met Greta Sandvik.",
                            memory_type="task_context")
    assert echo in stored(provider)
    assert (outcome["swept"], outcome["suppressed"]) == ([], False)


# --- the forget and the write barrier ----------------------------------


class HeldDeletes(GatedStore):
    """``GatedStore`` whose deletes also wait for ``held``, so a forget
    can be held in flight; ``deleting`` is set when one starts."""

    def __init__(self):
        super().__init__()
        self.held = threading.Event()
        self.held.set()
        self.deleting = threading.Event()

    def delete(self, memory_id, user_id):
        self.deleting.set()
        assert self.held.wait(WAIT)
        return super().delete(memory_id, user_id)


def test_a_forget_waits_for_a_write_accepted_before_it():
    """A forget stamped after a write waits for that write's commit,
    still in flight, and then deletes the row it stored, so the write
    cannot slip a carrier in behind it."""
    provider = GatedStore()
    pipeline = MemoryPipeline(provider)
    statement = write(pipeline, WRITER, "My lawyer is Greta Sandvik.",
                      **stated(VALUE, "e1"))
    write_seq = pipeline.barrier.acquire(USER)  # the echo, accepted
    forget_seq = pipeline.barrier.acquire(USER)  # then the forget
    provider.gate.clear()
    outcome = {}
    writer = Background(
        pipeline.write, TASK, USER,
        note(TASK, "Meeting with Greta Sandvik.",
             memory_type="task_context", fact_key="meeting"),
        barrier_seq=write_seq, outcome=outcome,
    )
    forget = Background(pipeline.forget, WRITER, USER, SLOT,
                        barrier_seq=forget_seq)
    assert not forget.done(0.3)
    provider.gate.set()
    assert writer.done(WAIT) and forget.done(WAIT)
    echo = writer.result
    # The echo committed before the tombstone, and the forget took it.
    assert echo and outcome["swept"] == []
    assert deleted(forget.result) == {
        statement: (WRITER, "fact_key"), echo: (TASK, "value"),
    }
    assert stored(provider) == {}
    assert pipeline.barrier.stats()["total_pending"] == 0


def test_a_retrieval_accepted_after_a_forget_waits_for_it():
    """A retrieval stamped after the forget's sequence waits until the
    forget returns and then finds nothing left to guard; one stamped
    before it does not wait, and the tombstone already guards it."""
    provider = HeldDeletes()
    pipeline = MemoryPipeline(provider)
    statement = write(pipeline, WRITER, "My lawyer is Greta Sandvik.",
                      **stated(VALUE, "e1"))
    before = pipeline.barrier.snapshot(USER)
    forget_seq = pipeline.barrier.acquire(USER)
    after = pipeline.barrier.snapshot(USER)
    assert before < forget_seq <= after
    provider.held.clear()
    forget = Background(pipeline.forget, WRITER, USER, SLOT,
                        barrier_seq=forget_seq)
    assert provider.deleting.wait(WAIT)

    early = Background(pipeline.retrieve, ASSISTANT, USER, "my lawyer",
                       barrier_snapshot=before)
    late = Background(pipeline.retrieve, ASSISTANT, USER, "my lawyer",
                      barrier_snapshot=after)
    assert early.done(1)
    assert not late.done(0.3)
    provider.held.set()
    assert forget.done(WAIT) and late.done(WAIT)

    candidates, diagnostics = early.result
    assert (candidates, diagnostics["tombstoned_rows"]) == ([], [statement])
    candidates, diagnostics = late.result
    assert (candidates, diagnostics["tombstoned_rows"]) == ([], [])
    assert diagnostics["barrier_waits"] == [
        {"user_id": USER, "outcome": "DRAINED"},
    ]
    assert stored(provider) == {}


def test_a_forget_never_waits_on_its_own_sequence():
    """A forget waits for the writes before its sequence, never a fresh
    snapshot that holds its own: with a 30 s barrier timeout, a forget
    that takes its own sequence, or is given one, returns at once."""
    provider = GatedStore()
    pipeline = MemoryPipeline(provider, PipelineSettings(
        write_barrier={"timeout_ms": 30_000},
    ))
    write(pipeline, WRITER, "My lawyer is Greta Sandvik.",
          **stated(VALUE, "e1"))
    started = time.perf_counter()
    own = Background(pipeline.forget, WRITER, USER, SLOT)
    assert own.done(2)
    assert time.perf_counter() - started < 1
    assert own.result["values_count"] == 1

    stamped_seq = pipeline.barrier.acquire(USER)
    started = time.perf_counter()
    stamped = Background(pipeline.forget, WRITER, USER, SLOT,
                         barrier_seq=stamped_seq)
    assert stamped.done(2)
    assert time.perf_counter() - started < 1
    assert pipeline.barrier.stats()["total_pending"] == 0


# --- after a forget: the sweep -----------------------------------------


class Recording(InHouseProvider):
    """The in-memory store, keeping the id of every row it adds."""

    def __init__(self):
        super().__init__()
        self.added = []

    def add(self, memory_note):
        memory_id = super().add(memory_note)
        self.added.append(memory_id)
        return memory_id


REWRITES = {
    "echo of another slot": (
        TASK, "Meeting with Greta Sandvik on Friday.",
        {"memory_type": "task_context", "fact_key": "meeting"},
    ),
    "conversation row": (
        ASSISTANT, "User: Who is my lawyer?\nAssistant: Greta Sandvik.",
        {"memory_type": "conversation", "policy": "private"},
    ),
    "alias only": (
        CALENDAR, "Call Sandvik about the lease.",
        {"memory_type": "calendar", "fact_key": "call"},
    ),
    "fold under another slot": (
        WRITER, "I live in Oslo, near Greta Sandvik.", {"fact_key": HOME},
    ),
}


@pytest.mark.parametrize("agent, content, metadata", REWRITES.values(),
                         ids=list(REWRITES))
def test_a_rewrite_of_a_forgotten_value_is_swept(agent, content, metadata):
    """After a forget, a write by any agent whose row carries a form is
    swept: it returns "", and its outcome says suppressed and names the
    swept row. Without the forget the same write is kept."""
    provider, pipeline = forgotten_store(Recording())
    memory_id, outcome = written(pipeline, agent, content, **metadata)
    assert memory_id == ""
    assert outcome["suppressed"] is True
    assert outcome["swept"] == [
        {"memory_id": provider.added[-1], "owner_agent": agent},
    ]
    assert (outcome["lifted"], outcome["retired"]) == ([], [])
    assert stored(provider) == {}

    fresh = store()
    memory_id, outcome = written(MemoryPipeline(fresh), agent, content,
                                 **metadata)
    assert memory_id in stored(fresh)
    assert (outcome["swept"], outcome["suppressed"]) == ([], False)


def test_a_write_that_carries_no_form_is_kept():
    """After a forget, a write that carries no form (a longer word that
    contains one included) is kept and not suppressed."""
    provider, pipeline = forgotten_store()
    for content in ("Client is Halvorsen.", "We hiked near Sandviken."):
        memory_id, outcome = written(pipeline, TASK, content,
                                     memory_type="task_context")
        assert memory_id in stored(provider)
        assert (outcome["swept"], outcome["suppressed"]) == ([], False)


def test_a_write_sweeps_every_carrier_in_the_partition():
    """The sweep after a write lists the user's whole partition: a
    carrier that escaped the forget is deleted by the next write of
    anything, which is kept, not suppressed."""
    provider, pipeline = forgotten_store()
    escaped_id = plant(provider, CALENDAR, "Call Sandvik about the lease.")
    memory_id, outcome = written(pipeline, TASK, "Client is Halvorsen.",
                                 memory_type="task_context")
    assert outcome["swept"] == [
        {"memory_id": escaped_id, "owner_agent": CALENDAR},
    ]
    assert outcome["suppressed"] is False
    assert list(stored(provider)) == [memory_id]


class Scrubbing(InHouseProvider):
    """The in-memory store, recording each history scrub and answering
    with fixed counts, as Mem0's would."""

    def __init__(self):
        super().__init__()
        self.scrubs = []

    def scrub_history(self, user_id, forms, deleted_ids=(), kept_ids=()):
        self.scrubs.append(
            (user_id, list(forms), list(deleted_ids), list(kept_ids))
        )
        return {"messages": 2, "history": 3}


def test_forget_and_sweep_scrub_the_providers_history():
    """A forget, and a sweep after it, ask the provider to scrub the
    user's history with every form, the ids just deleted and the ids
    kept, and report the counts it returns."""
    provider = Scrubbing()
    pipeline = MemoryPipeline(provider)
    statement = write(pipeline, WRITER, "My lawyer is Greta Sandvik.",
                      **stated(VALUE, "e1"))
    city = write(pipeline, WRITER, "I live in Tallinn.", fact_key=HOME)
    report = pipeline.forget(WRITER, USER, SLOT)
    assert report["scrubbed"] == {"messages": 2, "history": 3}
    assert provider.scrubs == [(USER, [VALUE, ALIAS], [statement], [city])]

    _, outcome = written(pipeline, TASK, "Meeting with Greta Sandvik.",
                         memory_type="task_context")
    assert outcome["scrubbed"] == {"messages": 2, "history": 3}
    swept = outcome["swept"][0]["memory_id"]
    assert provider.scrubs[-1] == (USER, [VALUE, ALIAS], [swept], [city])


# --- after a forget: the user's restatement ----------------------------


@pytest.mark.parametrize("value", [VALUE, "greta sandvik", ALIAS])
def test_a_restatement_lifts_the_tombstone(value):
    """A new statement of the slot (a new provenance_event) with the
    forgotten value or an alias lifts the tombstone: the statement is
    kept, its outcome names the value as the write stated it (never the
    tombstone's spelling, which may be another agent's text), and a
    later echo is kept."""
    provider, pipeline = forgotten_store()
    memory_id, outcome = written(pipeline, WRITER,
                                 f"My lawyer is {value} again.",
                                 **stated(value, "e2"))
    assert memory_id in stored(provider)
    assert outcome["lifted"] == [value]
    assert (outcome["swept"], outcome["suppressed"]) == ([], False)
    assert pipeline.tombstones.entries(USER) == []

    echo, outcome = written(pipeline, TASK, "Meeting with Greta Sandvik.",
                            memory_type="task_context", fact_key="meeting")
    assert echo in stored(provider)
    assert (outcome["swept"], outcome["suppressed"]) == ([], False)


def test_a_replay_or_another_value_lifts_nothing():
    """A write that replays the forgotten statement (its
    provenance_event) is swept and lifts nothing; a statement of the
    slot with another value lifts nothing, and the tombstone still
    sweeps the value afterwards."""
    provider, pipeline = forgotten_store()
    replay, outcome = written(pipeline, WRITER,
                              "My lawyer is Greta Sandvik.",
                              **stated(VALUE, "e1"))
    assert (replay, outcome["lifted"], outcome["suppressed"]) == (
        "", [], True,
    )
    other, outcome = written(pipeline, WRITER, "My lawyer is Henrik Olsen.",
                             **stated("Henrik Olsen", "e2", aliases=()))
    assert other in stored(provider)
    assert (outcome["lifted"], outcome["suppressed"]) == ([], False)
    assert [t.value for t in pipeline.tombstones.entries(USER)] == [VALUE]

    echo, outcome = written(pipeline, TASK, "Meeting with Greta Sandvik.",
                            memory_type="task_context", fact_key="meeting")
    assert (echo, outcome["suppressed"]) == ("", True)
    assert list(stored(provider)) == [other]


# --- the guard on every read path --------------------------------------

QUERY = "Call about the lease"


def escaped():
    """A forgotten store with a carrier planted after the forget (one
    that escaped the forget and the sweep) next to a row that carries
    nothing: (provider, pipeline, planted, kept)."""
    provider, pipeline = forgotten_store()
    kept = write(pipeline, CALENDAR, "Dentist about the lease, Monday.",
                 memory_type="calendar")
    planted = plant(provider, CALENDAR, "Call Sandvik about the lease.")
    return provider, pipeline, planted, kept


def test_retrieval_drops_an_escaped_carrier(caplog):
    """SDK search never selects a row carrying a forgotten form: the
    ``after_tombstone`` stage drops it, lists it in ``tombstoned_rows``
    and logs a WARNING. Without the tombstone the row is selected."""
    provider, pipeline, planted, kept = escaped()
    with caplog.at_level(logging.WARNING):
        candidates, diagnostics = pipeline.retrieve(ASSISTANT, USER, QUERY)
    assert ids(candidates) == [kept]
    assert diagnostics["tombstoned_rows"] == [planted]
    assert diagnostics["tombstoned_forms"] == 2
    assert diagnostics["after_tombstone"] < diagnostics["after_supersession"]
    assert len(warned(caplog, SELECTOR, planted)) == 1

    candidates, diagnostics = MemoryPipeline(provider).retrieve(
        ASSISTANT, USER, QUERY
    )
    assert sorted(ids(candidates)) == sorted([kept, planted])
    assert (diagnostics["tombstoned_rows"],
            diagnostics["tombstoned_forms"]) == ([], 0)


def test_injection_drops_an_escaped_carrier(caplog):
    """Injection never puts a row carrying a forgotten form in the
    block: it is dropped, listed in ``tombstoned_rows`` and logged.
    Without the tombstone the row is injected."""
    provider, pipeline, planted, kept = escaped()
    messages = [{"role": "user", "content": QUERY}]
    with caplog.at_level(logging.WARNING):
        injected, diagnostics = pipeline.inject(
            ASSISTANT, messages, user_id=USER
        )
    assert [m["memory_id"] for m in diagnostics["injected_memories"]] == [
        kept,
    ]
    assert ALIAS not in injected[0]["content"]
    assert diagnostics["tombstoned_rows"] == [planted]
    assert diagnostics["tombstoned_forms"] == 2
    assert len(warned(caplog, SELECTOR, planted)) == 1

    injected, diagnostics = MemoryPipeline(provider).inject(
        ASSISTANT, messages, user_id=USER
    )
    assert ALIAS in injected[0]["content"]
    assert diagnostics["tombstoned_rows"] == []


def test_the_owners_listing_withholds_an_escaped_carrier(caplog):
    """``list_own_report`` leaves a row carrying a forgotten form out of
    the owner's listing, reports its id as withheld and logs a WARNING.
    Without the tombstone the row is listed."""
    provider, pipeline, planted, kept = escaped()
    with caplog.at_level(logging.WARNING):
        rows, withheld = pipeline.list_own_report(CALENDAR, USER)
    assert (ids(rows), withheld) == ([kept], [planted])
    assert len(warned(caplog, FACADE, planted)) == 1
    assert ids(pipeline.list_own(CALENDAR, USER)) == [kept]

    rows, withheld = MemoryPipeline(provider).list_own_report(
        CALENDAR, USER
    )
    assert (ids(rows), withheld) == ([kept, planted], [])


def test_a_read_by_id_refuses_an_escaped_carrier(caplog):
    """``read`` (get_memory) answers None for a row carrying a forgotten
    form, as for a missing one, and logs a WARNING. Without the
    tombstone the row is read."""
    provider, pipeline, planted, kept = escaped()
    with caplog.at_level(logging.WARNING):
        assert pipeline.read(ASSISTANT, USER, planted) is None
    assert pipeline.read(ASSISTANT, USER, kept).memory_id == kept
    assert len(warned(caplog, FACADE, planted)) == 1

    found = MemoryPipeline(provider).read(ASSISTANT, USER, planted)
    assert found.memory_id == planted


@pytest.mark.parametrize("tombstones", ["no store", "empty store"])
def test_the_new_stages_are_always_reported(tombstones):
    """Without tombstones and with supersession off, the selection still
    reports ``after_supersession``, ``superseded_rows``,
    ``after_tombstone``, ``tombstoned_rows`` and ``tombstoned_forms``,
    and they drop nothing: a marked row is selected as before."""
    provider = store()
    pipeline = (
        MemoryPipeline(provider, tombstones=None)
        if tombstones == "no store" else MemoryPipeline(provider)
    )
    _, diagnostics = pipeline.retrieve(ASSISTANT, USER, "lawyer")
    assert diagnostics["after_supersession"] == 0
    assert diagnostics["after_tombstone"] == 0

    write(pipeline, WRITER, "My lawyer is Greta Sandvik.",
          **stated(VALUE, "e2"))
    marked = plant(provider, WRITER, "My lawyer was Henrik Olsen.",
                   memory_type="profile", superseded_by="e2",
                   **stated("Henrik Olsen", "e1", aliases=()))
    candidates, diagnostics = pipeline.retrieve(ASSISTANT, USER, "lawyer")
    assert marked in ids(candidates)
    _, injection = pipeline.inject(
        ASSISTANT, [{"role": "user", "content": "lawyer"}], user_id=USER,
    )
    for report in (diagnostics, injection):
        assert report["after_visibility"] > 0
        assert report["after_supersession"] == report["after_visibility"]
        assert report["superseded_rows"] == []
        assert report["after_tombstone"] == report["after_supersession"]
        assert report["tombstoned_rows"] == []
        assert report["tombstoned_forms"] == 0


# --- supersession ------------------------------------------------------


def test_a_later_statement_retires_the_earlier_rows_of_its_slot():
    """With ``supersession: exclude`` a later statement marks the
    earlier rows of its slot (``superseded_by`` its event,
    ``superseded_session`` its session) and its outcome lists them: by
    the same writer, and across owners for a contradiction. A marked
    row keeps its first mark; other slots are untouched."""
    provider = store()
    pipeline = MemoryPipeline(provider, EXCLUDE)
    juniper, outcome = written(pipeline, WRITER, "I live on Juniper Street.",
                               **home("Juniper Street", "e1", 1))
    assert outcome["retired"] == []
    lawyer = write(pipeline, WRITER, "My lawyer is Greta Sandvik.",
                   **stated(VALUE, "e0"))
    base = write(pipeline, WRITER, "I like Rust.")

    birch, outcome = written(pipeline, WRITER, "I moved to Birch Road.",
                             **home("Birch Road", "e2", 2))
    assert outcome["retired"] == [juniper]
    cedar, outcome = written(pipeline, TASK, "They live on Cedar Lane.",
                             memory_type="task_context",
                             **home("Cedar Lane", "e3", 3))
    assert outcome["retired"] == [birch]

    rows = stored(provider)
    marks = {
        memory_id: tuple(row.metadata.get(mark) for mark in MARKS)
        for memory_id, row in rows.items()
    }
    assert MARKS == ("superseded_by", "superseded_session")
    assert marks == {
        juniper: ("e2", 2), birch: ("e3", 3), cedar: (None, None),
        lawyer: (None, None), base: (None, None),
    }
    assert rows[juniper].content == "I live on Juniper Street."
    assert rows[birch].content == "I moved to Birch Road."


def test_a_mark_is_a_metadata_only_update():
    """A mark goes through ``update_metadata`` with the marks alone (no
    session, no ``superseded_session``), so the retired row keeps its
    content and the rest of its metadata."""
    provider = store()
    pipeline = MemoryPipeline(provider, EXCLUDE)
    juniper = write(pipeline, WRITER, "I live on Juniper Street.",
                    **home("Juniper Street", "e1", 1))
    before = stored(provider)[juniper]
    with patch.object(provider, "update_metadata",
                      wraps=provider.update_metadata) as mark:
        written(pipeline, WRITER, "I moved to Birch Road.",
                **stated("Birch Road", "e2", fact_key=HOME, aliases=()))
    mark.assert_called_once_with(juniper, USER, {"superseded_by": "e2"})
    after = stored(provider)[juniper]
    assert after.content == before.content
    assert after.metadata == {**before.metadata, "superseded_by": "e2"}


def test_supersession_off_marks_nothing():
    """Under ``supersession: off``, the default, a later statement of
    the slot retires nothing."""
    provider = store()
    pipeline = MemoryPipeline(provider)
    assert pipeline.settings.supersession == "off"
    juniper = write(pipeline, WRITER, "I live on Juniper Street.",
                    **home("Juniper Street", "e1", 1))
    _, outcome = written(pipeline, TASK, "They live on Cedar Lane.",
                         memory_type="task_context",
                         **home("Cedar Lane", "e3", 3))
    assert outcome["retired"] == []
    for mark in MARKS:
        assert mark not in stored(provider)[juniper].metadata


def test_retired_rows_are_never_selected_but_listed_and_forgotten():
    """Selection excludes a retired row before the cap, so the new
    statement takes the place the stale one held, and records it in
    ``superseded_rows``; under ``off`` the stale row is selected. A
    listing still returns it, and a forget of the slot deletes it."""
    provider = store()
    pipeline = MemoryPipeline(provider, EXCLUDE)
    juniper = write(pipeline, WRITER, "I live on Juniper Street.",
                    **home("Juniper Street", "e1", 1))
    birch = write(pipeline, WRITER, "I moved to Birch Road.",
                  **home("Birch Road", "e2", 2))
    query = "Do I live on Juniper Street?"

    candidates, diagnostics = pipeline.retrieve(ASSISTANT, USER, query, k=1)
    assert ids(candidates) == [birch]
    assert diagnostics["superseded_rows"] == [juniper]
    assert diagnostics["after_supersession"] < diagnostics["after_visibility"]
    _, injection = pipeline.inject(
        ASSISTANT, [{"role": "user", "content": query}], user_id=USER, k=1,
    )
    assert "Juniper" not in injection["block_text"]
    assert injection["superseded_rows"] == [juniper]

    off = MemoryPipeline(provider)
    candidates, diagnostics = off.retrieve(ASSISTANT, USER, query, k=1)
    assert ids(candidates) == [juniper]
    assert diagnostics["superseded_rows"] == []

    assert ids(pipeline.list_own(WRITER, USER)) == [juniper, birch]
    report = pipeline.forget(WRITER, USER, HOME)
    assert deleted(report) == {
        juniper: (WRITER, "fact_key"), birch: (WRITER, "fact_key"),
    }
    assert report["values_count"] == 2
    assert stored(provider) == {}


def test_agents_cannot_set_or_clear_a_mark():
    """A write's own ``superseded_by`` and ``superseded_session`` are
    dropped, so no row is born retired; an update can neither set a
    mark nor clear one, while its other changes apply."""
    provider = store()
    pipeline = MemoryPipeline(provider, EXCLUDE)
    juniper = write(pipeline, WRITER, "I live on Juniper Street.",
                    superseded_by="e9", superseded_session=9,
                    **home("Juniper Street", "e1", 1))
    for mark in MARKS:
        assert mark not in stored(provider)[juniper].metadata
    candidates, _ = pipeline.retrieve(ASSISTANT, USER, "Juniper Street")
    assert ids(candidates) == [juniper]

    assert pipeline.update(WRITER, USER, juniper, metadata={
        "superseded_by": "e9", "superseded_session": 9, "note": "set",
    })
    row = stored(provider)[juniper]
    assert row.metadata["note"] == "set"
    for mark in MARKS:
        assert mark not in row.metadata

    write(pipeline, WRITER, "I moved to Birch Road.",
          **home("Birch Road", "e2", 2))
    for cleared in (None, ""):
        assert pipeline.update(
            WRITER, USER, juniper, content="I lived on Juniper Street.",
            metadata={"superseded_by": cleared,
                      "superseded_session": cleared, "note": "clear"},
        )
        row = stored(provider)[juniper]
        assert (row.content, row.metadata["note"]) == (
            "I lived on Juniper Street.", "clear",
        )
        assert (row.metadata["superseded_by"],
                row.metadata["superseded_session"]) == ("e2", 2)


class DroppingStore(InHouseProvider):
    """The in-memory store, but while ``dropping`` is set an add stores
    nothing and returns "", as Mem0 may extract no fact."""

    dropping = False

    def add(self, memory_note):
        return "" if self.dropping else super().add(memory_note)


def test_a_write_that_stored_nothing_retires_nothing():
    """A statement whose write stored no row (none of its
    provenance_event is listed) retires nothing; once it stores one,
    the same statement retires the earlier row."""
    provider = DroppingStore()
    pipeline = MemoryPipeline(provider, EXCLUDE)
    juniper = write(pipeline, WRITER, "I live on Juniper Street.",
                    **home("Juniper Street", "e1", 1))
    provider.dropping = True
    memory_id, outcome = written(pipeline, WRITER, "I moved to Birch Road.",
                                 **home("Birch Road", "e2", 2))
    assert (memory_id, outcome["retired"]) == ("", [])
    assert "superseded_by" not in stored(provider)[juniper].metadata

    provider.dropping = False
    _, outcome = written(pipeline, WRITER, "I moved to Birch Road.",
                         **home("Birch Road", "e2", 2))
    assert outcome["retired"] == [juniper]


def test_a_write_without_an_event_or_a_suppressed_one_retires_nothing():
    """A statement without a provenance_event retires nothing, and
    neither does one swept for carrying a forgotten value; a statement
    with an event that is kept retires the earlier rows."""
    provider, pipeline = forgotten_store(settings=EXCLUDE)
    juniper = write(pipeline, WRITER, "I live on Juniper Street.",
                    **home("Juniper Street", "e1", 1))
    eventless = home("Birch Road", "e2", 2)
    del eventless["provenance_event"]
    birch, outcome = written(pipeline, WRITER, "I moved to Birch Road.",
                             **eventless)
    assert birch in stored(provider)
    assert outcome["retired"] == []

    swept, outcome = written(pipeline, WRITER,
                             "I moved next door to Greta Sandvik.",
                             **home("Cedar Lane", "e3", 3))
    assert (swept, outcome["suppressed"], outcome["retired"]) == (
        "", True, [],
    )
    for memory_id in (juniper, birch):
        assert "superseded_by" not in stored(provider)[memory_id].metadata

    _, outcome = written(pipeline, WRITER, "I moved to Cedar Lane.",
                         **home("Cedar Lane", "e4", 4))
    assert sorted(outcome["retired"]) == sorted([juniper, birch])


# --- updates -----------------------------------------------------------


def test_an_update_that_carries_a_forgotten_value_is_swept():
    """An owner's update that makes its row carry a forgotten value gets
    the row swept, and the update's outcome lists it; without the
    forget the same update keeps the row."""
    provider, pipeline = forgotten_store()
    city = write(pipeline, WRITER, "I live in Tallinn.", fact_key=HOME)
    outcome = {}
    assert pipeline.update(WRITER, USER, city,
                           content="I live next door to Greta Sandvik.",
                           outcome=outcome)
    assert outcome["swept"] == [{"memory_id": city, "owner_agent": WRITER}]
    assert city not in stored(provider)

    fresh = store()
    plain = MemoryPipeline(fresh)
    city = write(plain, WRITER, "I live in Tallinn.", fact_key=HOME)
    outcome = {}
    assert plain.update(WRITER, USER, city,
                        content="I live next door to Greta Sandvik.",
                        outcome=outcome)
    assert outcome["swept"] == []
    assert stored(fresh)[city].content == "I live next door to Greta Sandvik."


def test_an_update_never_retires_other_rows():
    """Under ``supersession: exclude`` an update of a statement, even to
    a new event, retires no other row of its slot, where a new
    statement would."""
    provider = store()
    off = MemoryPipeline(provider)
    juniper = write(off, WRITER, "I live on Juniper Street.",
                    **home("Juniper Street", "e1", 1))
    birch = write(off, WRITER, "I moved to Birch Road.",
                  **home("Birch Road", "e2", 2))

    pipeline = MemoryPipeline(provider, EXCLUDE)
    outcome = {}
    assert pipeline.update(WRITER, USER, birch,
                           content="I moved to Birch Road last week.",
                           metadata=home("Birch Road", "e3", 3),
                           outcome=outcome)
    assert outcome["retired"] == []
    for row in stored(provider).values():
        assert "superseded_by" not in row.metadata

    _, outcome = written(pipeline, WRITER, "I moved to Cedar Lane.",
                         **home("Cedar Lane", "e4", 4))
    assert sorted(outcome["retired"]) == sorted([juniper, birch])


# --- settings and version ----------------------------------------------


def test_the_supersession_setting():
    """``supersession`` is "off" unless the memory config says
    "exclude", travels in ``as_dict`` (the /memory/config report a
    replicated agent copies), and any other value is refused."""
    assert SUPERSESSION_MODES == ("off", "exclude")
    assert PipelineSettings().supersession == "off"
    assert PipelineSettings.from_memory_config({}).supersession == "off"
    settings = PipelineSettings.from_memory_config(
        {"supersession": "exclude"}
    )
    assert settings.supersession == "exclude"
    assert settings.as_dict()["supersession"] == "exclude"
    assert PipelineSettings.from_memory_config(settings.as_dict()) \
        == settings
    with pytest.raises(ValueError, match="supersession"):
        PipelineSettings(supersession="bogus")
    with pytest.raises(ValueError, match="supersession"):
        PipelineSettings.from_memory_config({"supersession": "bogus"})


def test_pipeline_version_covers_the_matcher(tmp_path, monkeypatch):
    """``PIPELINE_VERSION`` hashes the matcher's bytes: the matcher the
    library calls is one of the package's files, and in a copy of the
    package one more comment line in it changes the hash."""
    package = Path(pipeline_package.__file__).parent
    assert Path(tombstone_module.match_forms.__code__.co_filename) \
        == package / "matching.py"
    copy = tmp_path / "pipeline"
    copy.mkdir()
    for source in package.glob("*.py"):
        (copy / source.name).write_bytes(source.read_bytes())
    monkeypatch.setattr(pipeline_package, "__file__",
                        str(copy / "__init__.py"))
    before = pipeline_package._source_hash()
    assert pipeline_package._source_hash() == before

    matcher = copy / "matching.py"
    matcher.write_bytes(matcher.read_bytes() + b"# one more line\n")
    assert pipeline_package._source_hash() != before
