"""Mem0's history file, its scrub, and the metadata-only mark
(docs/DELETION_AND_SUPERSESSION.md: Decision 3, and "Supersession").

- mem0ai 2.0.2's history schema and message scopes, which
  ``Mem0Provider.scrub_history`` reads with its own SQL, are pinned.
- The scrub, on a real 2.0.2 history file seeded with Mem0's own
  methods: the user's messages that carry a form are deleted, in any of
  the user's scopes and nowhere else; history records stay, but lose
  the text of a deleted row, or the text that carries a form.
- Each Mem0 store keeps its history next to its vector store, and no
  client opens Mem0's default file (``~/.mem0/history.db``).
- A mark (``update_metadata``) on the real Mem0 and Chroma in-house
  stores keeps the row's text, embedding and score, and costs no
  embedding call and no Mem0 history record.
- End to end over an extracting Mem0: a forget through
  ``MemoryPipeline`` removes the statement from the messages Mem0 reads
  into the next extraction.

Real stores live under ``tmp_path`` and embed with the pinned model on
a local Ollama (skipped without one); Mem0's LLM is a fake.
"""
import importlib.metadata
import inspect
import json
import os
import sqlite3
from contextlib import closing

import pytest
from mem0.configs.base import MemoryConfig
from mem0.memory import main as mem0_main
from mem0.memory.main import _build_session_scope
from mem0.memory.storage import SQLiteManager

from aios.memory.pipeline import (
    MARKS,
    MemoryPipeline,
    TombstoneStore,
    carried_form,
)
from aios.memory.providers.base import MemoryProvider
from aios.memory.providers.factory import provider_config
from aios.memory.providers.mem0 import Mem0Provider
from tests.modules.memory.test_list_and_delete import write
from tests.modules.memory.test_mem0_infer import build as mem0_store
from tests.modules.memory.test_mem0_infer import with_llm
from tests.modules.memory.test_provider_contract import (
    DOCS,
    QUERY,
    build as contract_store,
    needs_ollama,
    note,
)

U = "ana_r1_t0__kernel_shared"  # a v2 id: "_" is a SQL LIKE wildcard
PROFILE, TASK = "profile_agent", "task_agent"
VALUE, ALIAS = "Greta Sandvik", "Sandvik"
FORMS = [VALUE, ALIAS]
# The library's marks: superseded_by "u0-e2", superseded_session 3.
MARKED = dict(zip(MARKS, ("u0-e2", 3)))
ZERO = {"messages": 0, "history": 0}


def scope(user, agent=None, run=None):
    """A message scope as mem0ai 2.0.2 builds it."""
    return _build_session_scope(
        {"user_id": user, "agent_id": agent, "run_id": run}
    )


def stored_messages(path):
    """Every message in a history file: (scope, role, content), sorted."""
    with closing(sqlite3.connect(path)) as connection:
        return sorted(connection.execute(
            "SELECT session_scope, role, content FROM messages"
        ).fetchall())


def history_rows(path):
    """Every history record in a history file, by its id."""
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        return {
            row["id"]: dict(row)
            for row in connection.execute("SELECT * FROM history")
        }


def history_count(path):
    """How many history records a history file holds."""
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute("SELECT COUNT(*) FROM history").fetchone()[0]


def events(path, memory_id):
    """The events Mem0 recorded for one row, in the order written."""
    with closing(sqlite3.connect(path)) as connection:
        return [event for (event,) in connection.execute(
            "SELECT event FROM history WHERE memory_id = ? ORDER BY rowid",
            (memory_id,),
        )]


# --- mem0ai 2.0.2, pinned (no Ollama) ---------------------------------

MESSAGE_COLUMNS = [
    "id", "session_scope", "role", "content", "name", "created_at",
]
HISTORY_COLUMNS = [
    "id", "memory_id", "old_memory", "new_memory", "event", "created_at",
    "updated_at", "is_deleted", "actor_id", "role",
]


def test_mem0_is_pinned_at_2_0_2():
    """The scrub's SQL is written against mem0ai 2.0.2's history file."""
    assert importlib.metadata.version("mem0ai") == "2.0.2"


def test_the_history_file_has_mem0_2_0_2s_tables(tmp_path):
    """Mem0's ``SQLiteManager`` makes exactly the two tables the scrub
    reads and writes, with these columns in this order."""
    path = str(tmp_path / "history.db")
    SQLiteManager(path).close()
    with closing(sqlite3.connect(path)) as connection:
        tables = [name for (name,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )]
        columns = {
            table: [row[1] for row in connection.execute(
                f"PRAGMA table_info({table})"
            )]
            for table in tables
        }
    assert columns == {
        "messages": MESSAGE_COLUMNS, "history": HISTORY_COLUMNS,
    }


def test_a_message_scope_ends_with_its_user_entry():
    """Mem0 scopes a message by its sorted ids joined by "&", so the
    ``user_id`` entry comes last: the scrub's scope check relies on
    it."""
    assert list(inspect.signature(_build_session_scope).parameters) == [
        "filters",
    ]
    assert _build_session_scope({"user_id": U, "agent_id": PROFILE}) == (
        f"agent_id={PROFILE}&user_id={U}"
    )
    assert _build_session_scope({"user_id": U}) == f"user_id={U}"
    assert _build_session_scope(
        {"user_id": U, "agent_id": PROFILE, "run_id": "r7"}
    ) == f"agent_id={PROFILE}&run_id=r7&user_id={U}"


# --- Mem0Provider.scrub_history on a real history file (no Ollama) ----

# Ids a loose scope test would take for U's.
OTHER_USER = "ben_r1_t0__kernel_shared"
LIKE_TWIN = "anaXr1_t0__kernel_shared"  # LIKE 'ana_r1_t0__kernel_shared'
SUFFIX_TWIN = "x" + U  # ends with U
PREFIX_TWIN = U + "_2"  # starts with U
U_SCOPES = [scope(U, PROFILE), scope(U, TASK), scope(U),
            scope(U, PROFILE, "r7")]

# (scope, role, content, scrubbed): U's messages, then each twin's
# copy of the statement, which the scrub must leave.
MESSAGES = [
    (scope(U, PROFILE), "user", "My lawyer is Greta Sandvik.", True),
    (scope(U, PROFILE), "user", "I like green tea.", False),
    (scope(U, PROFILE), "user", "I flew to Sandviken in May.", False),
    (scope(U, TASK), "user", "SANDVIK called about the lease.", True),
    (scope(U), "user", "greta-sandvik's office is in Oslo.", True),
    (scope(U), "assistant", "Noted: you moved to Tallinn.", False),
    (scope(U, PROFILE, "r7"), "user", "Ask Greta Sandvik first.", True),
] + [
    (scope(user, PROFILE), "user", "My lawyer is Greta Sandvik.", False)
    for user in (OTHER_USER, LIKE_TWIN, SUFFIX_TWIN, PREFIX_TWIN)
]

# Each row's history records (event, old_memory, new_memory), before
# and after the scrub. Two rows were just deleted (one by its slot,
# its text carrying no form), two are the user's kept rows, and one is
# another user's row, which the scrub is never told of.
DELETED = ["deleted-by-slot", "deleted-carrier"]
KEPT = ["kept-alias", "kept-clean"]
HISTORY = {
    "deleted-by-slot": [
        ("ADD", None, "Has a lawyer"),
        ("DELETE", "Has a lawyer", None),
    ],
    "deleted-carrier": [
        ("ADD", None, "Lawyer is Greta Sandvik"),
        ("DELETE", "Lawyer is Greta Sandvik", None),
    ],
    "kept-alias": [
        ("ADD", None, "Meets Sandvik on Fridays"),
        ("UPDATE", "Meets Sandvik on Fridays", "Meets the lawyer on Fridays"),
    ],
    "kept-clean": [("ADD", None, "Likes green tea")],
    "other-users-row": [("ADD", None, "Lawyer is Greta Sandvik")],
}
SCRUBBED = {
    "deleted-by-slot": [("ADD", None, None), ("DELETE", None, None)],
    "deleted-carrier": [("ADD", None, None), ("DELETE", None, None)],
    "kept-alias": [
        ("ADD", None, None),
        ("UPDATE", None, "Meets the lawyer on Fridays"),
    ],
    "kept-clean": HISTORY["kept-clean"],
    "other-users-row": HISTORY["other-users-row"],
}


def seeded_history_file(path):
    """A real history file at ``path``, seeded through Mem0's own
    ``save_messages`` and ``add_history``; returns its manager."""
    db = SQLiteManager(path)
    for message_scope, role, content, _ in MESSAGES:
        db.save_messages([{"role": role, "content": content}],
                         message_scope)
    second = 0
    for memory_id, records in HISTORY.items():
        for event, old, new in records:
            second += 1
            stamp = f"2026-11-10T00:00:{second:02d}+00:00"
            db.add_history(memory_id, old, new, event, created_at=stamp,
                           updated_at=stamp,
                           is_deleted=int(event == "DELETE"))
    return db


def history_of(db, memory_id):
    """A row's records as Mem0 reads them: (event, old, new)."""
    return [
        (r["event"], r["old_memory"], r["new_memory"])
        for r in db.get_history(memory_id)
    ]


def without_text(rows):
    """History records with their two text fields left out."""
    return {
        record_id: {key: value for key, value in row.items()
                    if key not in ("old_memory", "new_memory")}
        for record_id, row in rows.items()
    }


def scrubber(path):
    """A Mem0Provider that is never initialized: the scrub reads only
    its history file."""
    provider = Mem0Provider()
    provider.history_db_path = path
    return provider


def test_scrub_removes_the_forms_from_the_users_messages_and_history(
    tmp_path,
):
    """Every message in one of the user's scopes that carries the value
    or an alias under the matcher is deleted whole, and no other
    message. Every history record stays: a deleted row's lose their
    text, a kept row's only the text that carries a form."""
    path = str(tmp_path / "history.db")
    db = seeded_history_file(path)
    rows_before = history_rows(path)

    counts = scrubber(path).scrub_history(
        U, FORMS, deleted_ids=DELETED, kept_ids=KEPT,
    )

    # The 4 carrying messages of U's 4 scopes; the 6 records whose text
    # changed (both of each deleted row, both of the alias row).
    assert counts == {"messages": 4, "history": 6}
    assert stored_messages(path) == sorted(
        (message_scope, role, content)
        for message_scope, role, content, gone in MESSAGES if not gone
    )
    for user_scope in U_SCOPES:
        assert sorted(
            m["content"] for m in db.get_last_messages(user_scope)
        ) == sorted(
            content for message_scope, _, content, gone in MESSAGES
            if message_scope == user_scope and not gone
        ), user_scope
    for memory_id, records in SCRUBBED.items():
        assert history_of(db, memory_id) == records, memory_id
    rows_after = history_rows(path)
    assert len(rows_after) == len(rows_before)
    assert without_text(rows_after) == without_text(rows_before)
    db.close()


def test_the_scrub_reaches_records_past_its_first_chunk(tmp_path):
    """The scrub looks records up by id in chunks (SQLite's variable
    limit): a carrying record in the last chunk of a large store is
    cleared like one in the first, and no other record changes."""
    path = str(tmp_path / "history.db")
    db = SQLiteManager(path)
    count = 2 * Mem0Provider._SCRUB_CHUNK + 1  # three chunks
    kept = [f"row-{i:05d}" for i in range(count)]
    carriers = {kept[0], kept[count // 2], kept[-1]}
    deleted = "row-99999"  # sorts after every kept id
    db.batch_add_history([
        {"memory_id": memory_id, "old_memory": None, "event": "ADD",
         "new_memory": (
             "Meets Sandvik on Fridays" if memory_id in carriers
             else "Likes green tea"
         )}
        for memory_id in [*kept, deleted]
    ])

    counts = scrubber(path).scrub_history(
        U, FORMS, deleted_ids=[deleted], kept_ids=kept,
    )

    assert counts == {"messages": 0, "history": len(carriers) + 1}
    texts = {
        row["memory_id"]: row["new_memory"]
        for row in history_rows(path).values()
    }
    assert texts == {
        memory_id: (
            None if memory_id in carriers or memory_id == deleted
            else "Likes green tea"
        )
        for memory_id in [*kept, deleted]
    }
    db.close()


def test_a_scrub_without_forms_clears_only_the_deleted_rows_records(
    tmp_path,
):
    """A forget that found no value deletes by slot alone and scrubs
    with no forms: the deleted rows' records still lose their text, and
    no message or other record changes."""
    path = str(tmp_path / "history.db")
    db = seeded_history_file(path)
    messages = stored_messages(path)

    counts = scrubber(path).scrub_history(
        U, [], deleted_ids=DELETED, kept_ids=KEPT,
    )

    assert counts == {"messages": 0, "history": 4}
    assert stored_messages(path) == messages
    for memory_id, records in HISTORY.items():
        expected = SCRUBBED[memory_id] if memory_id in DELETED else records
        assert history_of(db, memory_id) == expected, memory_id
    db.close()


def test_a_scrub_without_a_history_file_does_nothing(tmp_path):
    """With no history file configured, or none written yet, the scrub
    returns zero counts and creates no file."""
    assert Mem0Provider().history_db_path is None
    assert Mem0Provider().scrub_history(U, FORMS, DELETED, KEPT) == ZERO
    missing = tmp_path / "history.db"
    assert scrubber(str(missing)).scrub_history(
        U, FORMS, DELETED, KEPT,
    ) == ZERO
    assert not missing.exists()


# --- a real Mem0 store: its history file (needs Ollama) ---------------


def file_state(path):
    """A file's mtime and size, or None when it does not exist."""
    try:
        stat = os.stat(path)
    except FileNotFoundError:
        return None
    return stat.st_mtime_ns, stat.st_size


@pytest.fixture
def default_history_untouched():
    """Mem0's default history file (``~/.mem0/history.db``): the test
    fails if its mtime or size changed."""
    path = MemoryConfig.model_fields["history_db_path"].default
    before = file_state(path)
    yield path
    assert file_state(path) == before, f"{path} was written"


@pytest.fixture
def opened_history_files(monkeypatch):
    """The path of every history file a Mem0 client opens."""
    opened = []

    class Recording(SQLiteManager):
        def __init__(self, db_path=":memory:"):
            opened.append(db_path)
            super().__init__(db_path)

    monkeypatch.setattr(mem0_main, "SQLiteManager", Recording)
    return opened


@needs_ollama
def test_every_client_keeps_its_history_in_the_store(
    tmp_path, default_history_untouched, opened_history_files,
):
    """The store's history file is ``history.db`` next to its vector
    store directory: the default client and each per-user client open
    it and no other, and Mem0 records the store's writes there."""
    provider = mem0_store(tmp_path, infer=False)
    chroma = provider.client.config.vector_store.config.path
    assert chroma == str(tmp_path / "mem0")
    expected = os.path.join(os.path.dirname(chroma), "history.db")
    assert provider.history_db_path == expected

    client = provider._get_client_for_user(U)
    assert provider.client.db.db_path == expected
    assert client.db.db_path == expected
    assert opened_history_files == [expected, expected]
    assert expected != default_history_untouched

    memory_id = provider.add(note("My lawyer is Greta Sandvik.", user=U))
    assert events(expected, memory_id) == ["ADD"]
    provider.close()


@needs_ollama
def test_an_explicit_history_path_wins(
    tmp_path, default_history_untouched, opened_history_files,
):
    """A ``history_db_path`` in the provider's config is used, its
    directory created, instead of the file next to the vector store."""
    explicit = tmp_path / "elsewhere" / "mem0_history.db"
    provider = Mem0Provider()
    provider.initialize(provider_config("mem0", {"mem0": {
        "user_id": "default",
        "history_db_path": str(explicit),
        "llm": {"provider": "litellm", "config": {
            "model": "ollama/qwen2.5:7b",
        }},
        "vector_store": {"provider": "chroma", "config": {
            "collection_name": "explicit",
            "path": str(tmp_path / "mem0"),
        }},
    }}))
    client = provider._get_client_for_user(U)
    assert provider.history_db_path == str(explicit)
    assert provider.client.db.db_path == str(explicit)
    assert client.db.db_path == str(explicit)
    assert opened_history_files == [str(explicit)] * 2
    assert explicit.exists()
    assert not (tmp_path / "history.db").exists()
    provider.close()


# --- the mark on both real stores (needs Ollama) ----------------------


class Calls:
    """Counts the calls made to ``owner.name`` (monkeypatched)."""

    def __init__(self, monkeypatch, owner, name):
        self.count = 0
        original = getattr(owner, name)

        def counted(*args, **kwargs):
            self.count += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(owner, name, counted)


def stored(collection, memory_id):
    """A row as Chroma holds it: (embedding, document, metadata)."""
    found = collection.get(
        ids=[memory_id], include=["embeddings", "metadatas", "documents"],
    )
    return (
        found["embeddings"][0].tolist(),
        found["documents"][0],
        found["metadatas"][0],
    )


def score_of(provider, query, memory_id):
    """The row's score in the user's search for ``query``."""
    return next(
        hit.score for hit in provider.search(query, U, 10)
        if hit.memory_id == memory_id
    )


LAWYER_QUERY = "Who is my lawyer?"


@needs_ollama
def test_a_mem0_mark_writes_the_metadata_alone(
    tmp_path, monkeypatch, default_history_untouched,
):
    """Mem0's ``update_metadata`` adds the marks and keeps every other
    payload key (the text, its hash), the embedding and the search
    score, with no embedding call and no history record; a missing id
    is False. Control: Mem0's own update records an UPDATE."""
    provider = mem0_store(tmp_path, infer=False)
    text = "My lawyer is Greta Sandvik."
    marked = provider.add(note(text, user=U, fact_key="lawyer",
                               provenance_event="u0-e1"))
    other = provider.add(note("My lawyer is Juniper Birch.", user=U,
                              fact_key="lawyer", provenance_event="u0-e2"))
    client = provider._get_client_for_user(U)
    collection = client.vector_store.collection
    path = provider.history_db_path
    embedding, document, payload = stored(collection, marked)
    assert payload["data"] == text and payload["hash"]
    score = score_of(provider, LAWYER_QUERY, marked)
    records = history_count(path)
    embeds = Calls(monkeypatch, client.embedding_model, "embed")

    assert provider.update_metadata(marked, U, MARKED)
    assert provider.update_metadata("no-such-id", U, MARKED) is False
    assert embeds.count == 0
    assert history_count(path) == records
    assert stored(collection, marked) == (
        embedding, document, {**payload, **MARKED},
    )
    found = provider.get(marked, U)
    assert found.content == text
    assert {key: found.metadata.get(key) for key in MARKED} == MARKED

    # Control: the same marks through Mem0's own update (the base
    # class's default) re-embed the text and record an UPDATE.
    before = embeds.count
    assert provider.update(other, U, None, MARKED)
    assert embeds.count > before
    assert history_count(path) == records + 1
    assert events(path, other) == ["ADD", "UPDATE"]

    assert score_of(provider, LAWYER_QUERY, marked) == pytest.approx(
        score, abs=1e-6,
    )
    provider.close()


@needs_ollama
def test_an_inhouse_mark_writes_the_metadata_alone(tmp_path, monkeypatch):
    """The Chroma in-house ``update_metadata`` merges the marks over the
    metadata and keeps the document, the embedding and the search
    score, without calling the embedder; a missing id is False.
    Control: the base class's default, through ``update``, embeds."""
    provider = contract_store("chroma_inhouse", tmp_path)
    marked = provider.add(note(DOCS[0], user=U, fact_key="editor",
                               provenance_event="u0-e1"))
    other = provider.add(note(DOCS[1], user=U, fact_key="project",
                              provenance_event="u0-e3"))
    collection = provider._collection(U)
    embedding, document, _ = stored(collection, marked)
    assert document == DOCS[0]
    metadata = provider.get(marked, U).metadata
    score = score_of(provider, QUERY, marked)
    embeds = Calls(monkeypatch, provider._embedder, "embed")

    assert provider.update_metadata(marked, U, MARKED)
    assert provider.update_metadata("no-such-id", U, MARKED) is False
    assert embeds.count == 0
    assert stored(collection, marked)[:2] == (embedding, document)
    found = provider.get(marked, U)
    assert found.content == DOCS[0]
    assert found.metadata == {**metadata, **MARKED}

    # Control: without the override, a mark costs an embedding call.
    assert MemoryProvider.update_metadata(provider, other, U, MARKED)
    assert embeds.count == 1

    assert score_of(provider, QUERY, marked) == pytest.approx(
        score, abs=1e-6,
    )
    provider.close()


# --- end to end: a forget over an extracting Mem0 (needs Ollama) ------

STATEMENT = {
    "fact_key": "lawyer",
    "structured": json.dumps(
        {"fact_key": "lawyer", "value": VALUE, "event_type": "add"}
    ),
    "value_aliases": json.dumps([ALIAS]),
    "provenance_event": "u0-e1",
}


def carrier(text):
    """The form of the forgotten value that ``text`` carries, under the
    library's own matcher, or None."""
    return carried_form(text, {}, FORMS)


def last_k_messages(llm):
    """The "## Last k Messages" section of the latest extraction
    prompt the fake LLM received."""
    prompt = llm.prompts[-1][-1]["content"]
    start = prompt.index("## Last k Messages")
    return prompt[start:prompt.index("## Recently Extracted", start)]


@needs_ollama
def test_a_forget_keeps_the_value_out_of_mem0s_next_extraction(
    tmp_path, default_history_untouched,
):
    """Mem0 stores a statement's utterance as a message and reads it
    into the writer's next extraction (the control). A forget through
    ``MemoryPipeline`` deletes every message that carries a form and
    the deleted rows' history text, so the next extraction's "Last k
    Messages" keeps the user's other message and no form."""
    provider = mem0_store(tmp_path)  # infer: Mem0 extracts, keeps messages
    llm = with_llm(provider, [], user=U)
    pipeline = MemoryPipeline(
        provider,
        tombstones=TombstoneStore(str(tmp_path / "tombstones.sqlite")),
    )
    path = provider.history_db_path

    def say(agent, content, fact, **metadata):
        """One write, from which the fake LLM extracts ``fact``."""
        llm.facts = [fact]
        memory_id = write(pipeline, agent, content, user=U, **metadata)
        assert memory_id, content
        return memory_id

    say(PROFILE, "My lawyer is Greta Sandvik.", "Lawyer is Greta Sandvik",
        **STATEMENT)
    say(TASK, "Booked a call with Sandvik for Friday.",
        "Has a call with Sandvik on Friday", memory_type="task_context",
        fact_key="call", provenance_event="u0-e2")
    say(PROFILE, "I prefer green tea.", "Prefers green tea",
        fact_key="drink", provenance_event="u0-e3")
    assert carrier(last_k_messages(llm)) == VALUE  # the control
    carrying = [m for m in stored_messages(path) if carrier(m[2])]
    assert len(carrying) == 2  # the statement's and the echo's

    report = pipeline.forget(PROFILE, U, "lawyer")

    deleted = {entry["memory_id"] for entry in report["deleted"]}
    assert len(deleted) == 2  # the statement's row and the echo's
    assert report["scrubbed"]["messages"] == len(carrying)
    db = provider._get_client_for_user(U).db
    assert [m["content"] for m in db.get_last_messages(scope(U, PROFILE))] \
        == ["I prefer green tea."]
    assert db.get_last_messages(scope(U, TASK)) == []
    assert not [m for m in stored_messages(path) if carrier(m[2])]
    records = list(history_rows(path).values())
    cleared = [r for r in records if r["memory_id"] in deleted]
    assert len(cleared) == report["scrubbed"]["history"] == 4  # ADD, DELETE
    assert all(r["old_memory"] is None and r["new_memory"] is None
               for r in cleared)
    assert not [r for r in records
                if carrier(r["old_memory"]) or carrier(r["new_memory"])]

    say(PROFILE, "I moved to Tallinn.", "Lives in Tallinn",
        fact_key="home_city", provenance_event="u0-e4")
    section = last_k_messages(llm)
    assert "I prefer green tea." in section
    assert carrier(section) is None
    assert carrier(llm.prompts[-1][-1]["content"]) is None  # whole prompt
    provider.close()


def test_without_its_own_path_the_scrub_reaches_the_clients_file(tmp_path):
    """A Mem0 store with no ``history_db_path`` of its own (a vector
    store other than Chroma, no explicit path) still keeps messages, in
    the file its clients open. The scrub reads that file from the
    client, rather than finding no file and reporting nothing."""
    from types import SimpleNamespace

    path = str(tmp_path / "clients_history.db")
    db = SQLiteManager(path)
    db.save_messages([{"role": "user",
                       "content": "My lawyer is Greta Sandvik."}],
                     scope(U, PROFILE))
    db.close()
    provider = Mem0Provider()
    provider.client = SimpleNamespace(db=SimpleNamespace(db_path=path))
    assert provider.history_db_path is None
    counts = provider.scrub_history(U, ["Greta Sandvik"])
    assert counts == {"messages": 1, "history": 0}
    assert stored_messages(path) == []
