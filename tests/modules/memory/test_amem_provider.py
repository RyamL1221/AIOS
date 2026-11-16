"""The A-MEM provider (NeurIPS Subtask 17, docs/AMEM_BACKEND.md): what
the contract tests cannot see. A-MEM's own code runs on the pinned
embedder with a scripted LLM (``_amem_script.py``) whose evolution
copies a new note's text into its neighbours' context."""
import json

import pytest

from aios.memory.note import MemoryNote
from tests.modules.memory._amem_script import amem_provider, needs_amem
from tests.modules.memory.test_provider_contract import needs_ollama

pytestmark = [needs_ollama, needs_amem]

USER = "amem_user"


def note(content, owner="profile_agent", event="e00", user=USER, **extra):
    memory = MemoryNote(content=content)
    memory.metadata = {
        "owner_agent": owner, "user_id": user, "memory_type": "profile",
        "sharing_policy": "shared", "provenance_event": event,
        "created_at": "2026-11-12T10:00:00+00:00", **extra}
    return memory


@pytest.fixture
def provider():
    provider = amem_provider()
    yield provider
    provider.close()


WRITES = [("My team chat app is Slack.", "profile_agent", "e00"),
          ("I work on the Weather Data API.", "task_agent", "e01"),
          ("My staging server is bittern-06.", "task_agent", "e02"),
          ("I meet Sofia Lindqvist every Monday.", "calendar_agent", "e03")]


def write_all(provider):
    return [provider.add(note(text, owner, event))
            for text, owner, event in WRITES]


def test_every_note_keeps_its_metadata_after_evolution(provider):
    """Risk 1: evolution rewrites the neighbours' context and tags; the
    metadata each note was written with (its ``category``) reaches every
    row ``search`` and ``list`` return."""
    ids = write_all(provider)
    store = provider.stores.store(USER)
    evolved = [n for n in store.memories.values()
               if "Related:" in (n.context or "")]
    assert evolved, "the scripted evolution changed no neighbour"
    by_id = {i: (owner, event) for i, (_, owner, event)
             in zip(ids, WRITES)}
    for rows in (provider.list(USER, 50),
                 provider.search("chat app staging", USER, 10)):
        assert {r.memory_id for r in rows} == set(ids)
        for row in rows:
            assert (row.metadata["owner_agent"],
                    row.metadata["provenance_event"]) == by_id[row.memory_id]
            assert row.metadata["user_id"] == USER


def test_search_is_amems_search_in_its_order_with_similarities(provider):
    """``search`` is A-MEM's ``search`` (the README's first example): its
    rows in its order, each with a similarity from its squared L2
    distance."""
    write_all(provider)
    store = provider.stores.store(USER)
    raw = store.search("Which chat app do I use?", 3)
    rows = provider.search("Which chat app do I use?", USER, 3)
    assert [r.memory_id for r in rows] == [x["id"] for x in raw]
    assert [r.score for r in rows] == pytest.approx(
        [1 - x["score"] / 2 for x in raw])
    assert rows[0].content == "My team chat app is Slack."


def test_a_write_reports_the_notes_its_evolution_changed(provider, caplog):
    """Each write logs the notes its evolution changed in the store
    helper's line, ``A-MEM evolved <n> note(s) at note <id>``, which the
    readings count once per write, and in the provider's own line,
    worded apart so that the count sees each kernel write once."""
    caplog.set_level("INFO")
    write_all(provider)
    helper = [r.getMessage() for r in caplog.records
              if r.getMessage().startswith("A-MEM evolved ")]
    assert len(helper) == len(WRITES)
    counts = [int(m.split(" evolved ")[1].split()[0]) for m in helper]
    assert counts[0] == 0 and sum(counts[1:]) > 0
    own = [r for r in caplog.records
           if r.name == "aios.memory.providers.amem"
           and " evolved " in r.getMessage()]
    assert len(own) == len(WRITES)


def test_delete_removes_the_note_from_the_store_and_chroma(provider):
    """Risk 2: ``delete`` removes the note from A-MEM's notes and its
    Chroma collection; other notes keep its id in their links."""
    ids = write_all(provider)
    store = provider.stores.store(USER)
    assert provider.delete(ids[0], USER)
    assert ids[0] not in store.memories
    assert store.retriever.collection.get(ids=[ids[0]])["ids"] == []
    assert ids[0] not in {r.memory_id for r in provider.list(USER, 50)}
    assert any(ids[0] in n.links for n in store.memories.values())
    assert not provider.delete(ids[0], USER)


def test_the_scrub_deletes_notes_whose_derived_text_carries_a_form(
        provider):
    """Risk 2: after the forget deleted the note stating a value, another
    note whose evolved context carries it is a carrier: the scrub deletes
    it and reports it as detached with the reason ``derived``. (Three
    writes: A-MEM shows evolution each neighbour's Chroma copy, written
    with the neighbour, so a fourth write's evolution rewrites the
    context from that and drops the third's.)"""
    ids = [provider.add(note(text, owner, event))
           for text, owner, event in WRITES[:3]]
    store = provider.stores.store(USER)
    assert provider.delete(ids[2], USER)  # "My staging server is bittern-06."
    carriers = [n.id for n in store.memories.values()
                if "bittern-06" in n.context]
    assert carriers, "evolution copied no value into a neighbour"
    counts = provider.scrub_history(USER, ["bittern-06"], [ids[2]], [])
    assert counts["messages"] == 0
    assert counts["history"] == len(carriers)
    assert sorted(d["memory_id"] for d in counts["detached"]) == \
        sorted(carriers)
    assert {d["reason"] for d in counts["detached"]} == {"derived"}
    # Each names its note's owner, so the forget reading counts it in
    # other_agents only when another agent wrote the note.
    owners = {i: owner for i, (_, owner, _) in zip(ids, WRITES)}
    assert {d["memory_id"]: d["owner_agent"]
            for d in counts["detached"]} == {i: owners[i] for i in carriers}
    remaining = provider.list(USER, 50)
    assert all("bittern-06" not in r.content + store.memories[
        r.memory_id].context for r in remaining)


def test_the_scrub_reads_the_stale_chroma_copy_too(provider):
    """A note whose Chroma copy (written before evolution changed the
    note) carries a form is a carrier, though the note no longer does."""
    ids = write_all(provider)
    store = provider.stores.store(USER)
    first = store.memories[ids[0]]
    # The note changed (its keywords held "Slack" too); Chroma kept the
    # old copy.
    first.context, first.keywords, first.tags = "Cleared.", [], []
    copy = store.retriever.collection.get(
        ids=[ids[0]], include=["documents"])["documents"][0]
    assert "Slack" in copy
    counts = provider.scrub_history(USER, ["Slack"], [], [])
    assert ids[0] in {d["memory_id"] for d in counts.get("detached", [])}


def test_a_value_split_over_two_tags_is_carried(provider):
    """Tags and keywords are read as one text, the items joined by
    spaces: a value split over two adjacent tags is carried
    (docs/AMEM_BACKEND.md, "The forget on A-MEM")."""
    first = provider.add(note("I work on the Weather Data API."))
    stored = provider.stores.store(USER).memories[first]
    stored.context, stored.keywords = "", []
    stored.tags = ["Larkspur", "migration"]
    counts = provider.scrub_history(USER, ["Larkspur migration"], [], [])
    assert [d["memory_id"] for d in counts.get("detached", [])] == [first]


def test_a_failed_search_raises(provider, monkeypatch):
    """A failed A-MEM search raises, so the kernel reports a
    ``retrieval_error``, not an empty store; and the provider calls
    ``search``, not ``search_agentic``, which returns [] on any error
    (docs/AMEM_BACKEND.md)."""
    from aios.memory.providers.base import ProviderError

    write_all(provider)
    store = provider.stores.store(USER)

    def fail(*args, **kwargs):
        raise RuntimeError("Chroma query failed")

    monkeypatch.setattr(store, "search", fail)
    with pytest.raises(ProviderError):
        provider.search("Which chat app do I use?", USER, 3)


def test_the_provider_reports_what_amem_does(provider):
    """The write barrier waits for an A-MEM write (two LLM calls);
    A-MEM's LLM annotates every write, which arms Amendment 8's checks;
    its search is scored; /memory/config reports the installed commit
    (docs/AMEM_BACKEND.md)."""
    from cerebrum.utils import amem as clients

    assert provider.synchronous_commit is False
    assert provider.backend_extraction is True
    assert provider.capabilities() == {
        "scored_search": True, "semantic_search": True,
        "internal_llm": True, "native_sdk": True}
    assert provider.versions == clients.versions()
    assert provider.versions["agentic_memory"]


def test_a_write_time_is_amems_own_format():
    """A-MEM's ``YYYYMMDDHHMM`` (memory_system.py:56), which its
    evolution prompt shows the LLM as each neighbour's "talk start
    time"."""
    from aios.memory.providers.amem import _time

    assert _time("2026-11-12T10:05:00+00:00") == "202611121005"


def test_providers_of_one_configuration_share_the_stores():
    """A replicated cell's agents each build a provider from one
    configuration (Cerebrum ``ReplicatedMemory``), and the assistant
    reads what the writers wrote: the providers share the stores.
    Building them makes no call."""
    import uuid

    from aios.memory.providers.factory import (ProviderFactory,
                                               provider_config)

    config = provider_config("amem", {
        "amem": {"namespace": uuid.uuid4().hex[:8]},
        "backend_llm": {"provider": "azure_openai", "model": "gpt-4o",
                        "temperature": 0.0, "seed": 20261105},
        "embedding": {"provider": "ollama", "model": "nomic-embed-text",
                      "dimension": 768}})
    first = ProviderFactory.create("amem", config)
    second = ProviderFactory.create("amem", config)
    try:
        assert first.stores is second.stores
        first.stores.store(USER)
        assert second.stores.has(USER)
    finally:
        first.close()
        second.close()


def test_a_mark_changes_the_category_alone(provider):
    """``update_metadata`` (a supersession mark) merges into the note's
    ``category``, in the note and in Chroma's metadata, and leaves the
    document and its embedding as they were."""
    ids = write_all(provider)
    store = provider.stores.store(USER)
    collection = store.retriever.collection
    before = collection.get(ids=[ids[0]],
                            include=["documents", "embeddings"])
    assert provider.update_metadata(ids[0], USER,
                                    {"superseded_by": "e05"})
    after = collection.get(ids=[ids[0]],
                           include=["documents", "embeddings", "metadatas"])
    assert after["documents"] == before["documents"]
    assert list(after["embeddings"][0]) == list(before["embeddings"][0])
    category = after["metadatas"][0]["category"]
    stored = category if isinstance(category, dict) else json.loads(category)
    assert stored["superseded_by"] == "e05"
    assert stored["owner_agent"] == "profile_agent"
    row = provider.get(ids[0], USER)
    assert row.metadata["superseded_by"] == "e05"
    hit = provider.search("chat app", USER, 1)[0]
    assert hit.memory_id == ids[0]
    assert hit.metadata["superseded_by"] == "e05"


def test_an_update_replaces_the_content(provider):
    ids = write_all(provider)
    assert provider.update(ids[0], USER, "My team chat app is Zulip.", None)
    row = provider.get(ids[0], USER)
    assert row.content == "My team chat app is Zulip."
    assert row.metadata["owner_agent"] == "profile_agent"
    assert provider.search("Zulip", USER, 1)[0].memory_id == ids[0]


def test_each_user_has_a_store_of_their_own(provider):
    """Building a second user's store deletes nothing of the first's,
    and a search reads only the user's own notes."""
    ids = write_all(provider)
    other = provider.add(note("I use Rust.", user="amem_other"))
    assert {r.memory_id for r in provider.list(USER, 50)} == set(ids)
    assert [r.memory_id for r in provider.search("Rust", "amem_other", 5)
            ] == [other]
    store = provider.stores.store(USER)
    assert store.retriever.collection.count() == len(ids)
    assert provider.get(other, USER) is None
    assert not provider.delete(other, USER)


def test_a_user_with_no_store_reads_nothing(provider):
    assert provider.search("anything", "nobody", 5) == []
    assert provider.list("nobody", 5) == []
    assert provider.get("x", "nobody") is None
    assert not provider.stores.has("nobody")


@pytest.mark.parametrize("k", [2, 10])
def test_search_agentic_returns_searchs_notes(provider, k):
    """The check the design rests on (docs/AMEM_BACKEND.md, "Search"):
    ``search_agentic`` returns ``search``'s notes in its order, with a
    store larger and smaller than k: the linked notes it adds never
    survive its cut at k."""
    write_all(provider)
    store = provider.stores.store(USER)
    assert any(n.links for n in store.memories.values()), "no links made"
    for query in ("Which chat app do I use?", "staging", "Monday"):
        assert [x["id"] for x in store.search_agentic(query, k)] == [
            x["id"] for x in store.search(query, k)]


def test_rows_carry_no_derived_text(provider):
    """Evolution writes a note's tags and context from the user's other
    notes, private ones included, and the kernel's visibility rule keeps
    or drops whole rows: a row carries A-MEM's note id and links, not its
    keywords, context or tags (review finding)."""
    ids = write_all(provider)
    rows = (provider.list(USER, 50) + provider.search("chat", USER, 4)
            + [provider.get(ids[0], USER)])
    for row in rows:
        assert {"amem_keywords", "amem_context", "amem_tags"}.isdisjoint(
            row.metadata)
        assert row.metadata["amem_note_id"] == row.memory_id
        assert isinstance(row.metadata["amem_links"], list)


@pytest.mark.parametrize("place", ["Utrecht", "Zürich"])
def test_the_scrub_finds_a_form_in_a_neighbours_tags_alone(place):
    """Evolution can carry a value into another note's tags only (in the
    store; Chroma keeps the tags the note was written with): that note is
    a carrier. A non-ASCII value is found too (``json.dumps`` would
    escape it)."""
    provider = amem_provider(evolve="tags")
    try:
        first = provider.add(note("I work on the Weather Data API."))
        second = provider.add(note(f"My office is in {place}.",
                                   owner="task_agent", event="e01"))
        store = provider.stores.store(USER)
        assert store.memories[first].tags == [place]
        assert place not in store.memories[first].context
        copy = store.retriever.collection.get(
            ids=[first], include=["documents"])["documents"][0]
        assert place not in copy
        assert provider.delete(second, USER)
        counts = provider.scrub_history(USER, [place], [second], [])
        assert [d["memory_id"] for d in counts["detached"]] == [first]
        assert counts["detached"][0]["reason"] == "derived"
        assert first not in store.memories
    finally:
        provider.close()


def test_a_failed_write_leaves_no_note(provider, monkeypatch):
    """A-MEM puts a note in its dict before it embeds it: when the
    Chroma write fails, the provider raises and leaves no note that
    lists but never searches (review finding)."""
    from aios.memory.providers.base import ProviderError

    ids = write_all(provider)
    store = provider.stores.store(USER)

    def fail(*args, **kwargs):
        raise RuntimeError("embedding failed")

    monkeypatch.setattr(store.retriever, "add_document", fail)
    with pytest.raises(ProviderError):
        provider.add(note("My laptop is a ThinkPad.", event="e09"))
    assert set(store.memories) == set(ids)
    assert {r.memory_id for r in provider.list(USER, 50)} == set(ids)
