"""The Graphiti provider's own rules (NeurIPS Subtask 16;
docs/GRAPHITI_BACKEND.md), on the local Neo4j and the pinned embedder
with the scripted LLM (``_graphiti_script.py``): rows per fact and
write, metadata on every fact, merged restatements, deletion, updates,
the forget's scrub, and search as Graphiti's own ``search()``.
"""
from datetime import datetime, timezone

import pytest

from aios.memory.note import MemoryNote
from tests.modules.memory._graphiti_script import (
    drop, graphiti_provider, needs_neo4j, scripted_llm, topic,
)
from tests.modules.memory.test_provider_contract import needs_ollama

pytestmark = [needs_ollama, needs_neo4j]

USER = "graphiti_user@users.example"  # '@' and '.' are not group chars
KEYS = ("owner_agent", "user_id", "memory_type", "sharing_policy",
        "created_at", "fact_key", "provenance_event", "memory_note_id")


def note(content, owner="profile_agent", policy="shared", user=USER,
         memory_type="profile", event="u0-e01", slot="team_chat", **extra):
    memory = MemoryNote(content=content)
    memory.metadata = {
        "owner_agent": owner, "user_id": user, "memory_type": memory_type,
        "sharing_policy": policy,
        "created_at": "2026-11-02T00:00:00+00:00",
        "fact_key": slot, "provenance_event": event, **extra,
    }
    return memory


@pytest.fixture
def provider():
    provider = graphiti_provider()
    yield provider
    drop(provider)


@pytest.fixture
def splitting():
    provider = graphiti_provider(llm=scripted_llm(split=True))
    yield provider
    drop(provider)


def edges_of(provider, user=USER):
    async def query():
        records, _, _ = await provider.graphiti.driver.execute_query(
            "MATCH ()-[r:RELATES_TO {group_id: $group}]->() "
            "RETURN r.uuid AS uuid, r.fact AS fact, r.episodes AS episodes",
            params={"group": provider._group(user)})
        return {r["uuid"]: (r["fact"], list(r["episodes"])) for r in records}
    return provider.runner.run(query)


def episodes_of(provider, user=USER):
    """The user's episodes: uuid -> content."""
    async def query():
        records, _, _ = await provider.graphiti.driver.execute_query(
            "MATCH (ep:Episodic {group_id: $group}) "
            "RETURN ep.uuid AS uuid, ep.content AS content",
            params={"group": provider._group(user)})
        return {r["uuid"]: r["content"] for r in records}
    return provider.runner.run(query)


def episode_of(provider, memory_id):
    """The episode of a row: its content, source and valid_at."""
    async def query():
        records, _, _ = await provider.graphiti.driver.execute_query(
            "MATCH (ep:Episodic {uuid: $uuid}) RETURN ep.content AS "
            "content, ep.source AS source, ep.valid_at AS valid_at",
            params={"uuid": memory_id.split(":")[1]})
        return records[0]
    return provider.runner.run(query)


def entity_names(provider, user=USER):
    """The names of the user's entities."""
    async def query():
        records, _, _ = await provider.graphiti.driver.execute_query(
            "MATCH (n:Entity {group_id: $group}) RETURN n.name AS name",
            params={"group": provider._group(user)})
        return {r["name"] for r in records}
    return provider.runner.run(query)


def embedding_of(provider, memory_id, user=USER):
    """The stored embedding of a row's fact."""
    async def query():
        records, _, _ = await provider.graphiti.driver.execute_query(
            "MATCH ()-[r:RELATES_TO {uuid: $edge, group_id: $group}]->() "
            "RETURN r.fact_embedding AS vector",
            params={"edge": memory_id.split(":")[0],
                    "group": provider._group(user)})
        return list(records[0]["vector"])
    return provider.runner.run(query)


def test_every_fact_of_a_split_write_carries_the_writes_metadata(splitting):
    """One write that Graphiti splits into several facts: every fact is
    a row of that write, with all of its metadata, its slot included;
    ``add`` returns the first."""
    memory = note("My chat tool is Slack. I live in Utrecht. I am a "
                  "data engineer.", value_aliases=["slack"])
    first = splitting.add(memory)
    rows = splitting.list(USER, 100)
    assert [r.content for r in rows] == [
        "My chat tool is Slack.", "I live in Utrecht.",
        "I am a data engineer."]
    assert rows[0].memory_id == first
    for row in rows:
        for key in KEYS:
            assert row.metadata[key] == (memory.id if key == "memory_note_id"
                                         else memory.metadata[key]), key
        assert row.metadata["value_aliases"] == ["slack"]
        assert row.metadata["graphiti_episode_count"] == 1
    found = splitting.search("Where does the user live?", USER, 10)
    assert {r.memory_id for r in found} == {r.memory_id for r in rows}
    assert all(r.metadata["fact_key"] == "team_chat" for r in found)


def test_a_merged_restatement_gets_a_row_of_its_own(provider):
    """Graphiti merges a restated fact onto the existing one and appends
    the episode; the restating write still has its own row, with its own
    metadata, and ``add`` returns it."""
    a = provider.add(note("My team's chat tool is Mattermost.",
                          owner="profile_agent", event="u0-e01"))
    b = provider.add(note("My team's chat tool is Mattermost.",
                          owner="calendar_agent", policy="private",
                          event="u0-e05"))
    edges = edges_of(provider)
    assert len(edges) == 1
    (fact, episodes), = edges.values()
    assert len(episodes) == 2
    assert a.split(":")[0] == b.split(":")[0] and a != b
    rows = {r.memory_id: r for r in provider.list(USER, 100)}
    assert set(rows) == {a, b}
    assert rows[a].metadata["owner_agent"] == "profile_agent"
    assert rows[b].metadata["owner_agent"] == "calendar_agent"
    assert rows[b].metadata["sharing_policy"] == "private"
    assert rows[b].metadata["provenance_event"] == "u0-e05"
    assert {r.metadata["graphiti_episode_count"]
            for r in rows.values()} == {2}
    found = provider.search("team chat tool", USER, 10)
    assert {r.memory_id for r in found} == {a, b}


def test_deleting_a_writes_rows_removes_them_and_keeps_the_others(
        splitting):
    """Deleting a write's rows removes all of them from search and list;
    a fact another write also claims survives with that write's row; a
    fact goes when its last row does, and so does an episode left with
    no fact."""
    first = splitting.add(note("I live in Utrecht. My chat tool is Slack.",
                               event="u0-e01"))
    other = splitting.add(note("My chat tool is Slack.",
                               owner="calendar_agent", event="u0-e02"))
    mine = [r for r in splitting.list(USER, 100)
            if r.metadata["provenance_event"] == "u0-e01"]
    assert len(mine) == 2 and mine[0].memory_id == first
    for row in mine:
        assert splitting.delete(row.memory_id, USER)
        assert splitting.get(row.memory_id, USER) is None
        assert not splitting.delete(row.memory_id, USER)
    rows = splitting.list(USER, 100)
    assert [r.memory_id for r in rows] == [other]
    assert [r.memory_id for r in splitting.search("Slack Utrecht", USER,
                                                  10)] == [other]
    facts = {fact for fact, _ in edges_of(splitting).values()}
    assert facts == {"My chat tool is Slack."}

    async def episodes():
        records, _, _ = await splitting.graphiti.driver.execute_query(
            "MATCH (ep:Episodic {group_id: $group}) RETURN ep.uuid AS uuid",
            params={"group": splitting._group(USER)})
        return {r["uuid"] for r in records}
    assert splitting.runner.run(episodes) == {other.split(":")[1]}
    assert splitting.delete(other, USER)
    assert splitting.list(USER, 100) == []
    assert edges_of(splitting) == {}


def test_search_gives_a_facts_newest_claim_first(provider):
    """A fact's rows share its rank, and the selector keeps the first of
    rows with one text: newest first, the block shows the fact as last
    stated (its session age, its event), not as first stated."""
    first = provider.add(note("My team's chat tool is Mattermost.",
                              event="u0-e01", session=1))
    later = provider.add(note("My team's chat tool is Mattermost.",
                              owner="calendar_agent", slot="retro_room",
                              event="u0-e09", session=5))
    found = provider.search("team chat tool", USER, 10)
    assert [r.memory_id for r in found] == [later, first]


def test_updating_a_shared_fact_splits_it(provider):
    """New content replaces the row's fact and is re-embedded; another
    write's row keeps the old sentence on a copy, with its own changes,
    under a new id."""
    a = provider.add(note("My chat tool is Slack.", event="u0-e01"))
    b = provider.add(note("My chat tool is Slack.", owner="calendar_agent",
                          event="u0-e02"))
    assert provider.update_metadata(b, USER, {"superseded_by": "u0-e09"})
    assert provider.update(a, USER, "My chat tool is Mattermost.",
                           {"sharing_policy": "private"})
    got = provider.get(a, USER)
    assert got.content == "My chat tool is Mattermost."
    assert got.metadata["sharing_policy"] == "private"
    assert got.metadata["owner_agent"] == "profile_agent"
    assert provider.get(b, USER) is None
    rows = {r.metadata["provenance_event"]: r for r in provider.list(USER,
                                                                     100)}
    assert rows["u0-e02"].content == "My chat tool is Slack."
    assert rows["u0-e02"].metadata["superseded_by"] == "u0-e09"
    assert rows["u0-e02"].memory_id != b
    assert provider.search("Mattermost", USER, 1)[0].memory_id == a
    assert not provider.update("missing:id", USER, "x", None)


def test_an_updated_write_keeps_no_row_on_the_old_sentence(provider):
    """Updating a fact another write also claims splits it: the copy
    with the old sentence is the other write's alone, so the updating
    write has one row, with the new sentence, and none on the copy
    (docs/GRAPHITI_BACKEND.md, "list, get, update, delete")."""
    a = provider.add(note("My chat tool is Slack.", event="u0-e01"))
    b = provider.add(note("My chat tool is Slack.", owner="calendar_agent",
                          event="u0-e02"))
    assert provider.update(a, USER, "My chat tool is Mattermost.", None)
    mine = [r for r in provider.list(USER, 100)
            if r.metadata["provenance_event"] == "u0-e01"]
    assert [(r.memory_id, r.content) for r in mine] == [
        (a, "My chat tool is Mattermost.")]
    assert dict(edges_of(provider).values()) == {
        "My chat tool is Mattermost.": [a.split(":")[1]],
        "My chat tool is Slack.": [b.split(":")[1]],
    }


def test_an_update_re_embeds_the_new_sentence(provider):
    """``update`` stores the new sentence's embedding on the fact, so the
    cosine half of search ranks the row by what it now says, not by the
    sentence it replaced (docs/GRAPHITI_BACKEND.md, "list, get, update,
    delete": the new content "re-embeds it")."""
    a = provider.add(note("My chat tool is Slack."))
    old = embedding_of(provider, a)
    assert provider.update(a, USER, "I live in Utrecht.", None)
    new = provider.runner.run(provider.graphiti.embedder.create,
                              "I live in Utrecht.")
    stored = embedding_of(provider, a)
    assert stored == pytest.approx(new, abs=1e-6)
    assert stored != pytest.approx(old, abs=1e-6)


def test_a_mark_writes_the_metadata_alone(provider, monkeypatch):
    """``update_metadata`` merges into the row's own changes and makes
    no embedding call."""
    a = provider.add(note("My chat tool is Slack."))
    calls = []
    real = provider.graphiti.embedder.create

    async def counted(*args, **kwargs):
        calls.append(args)
        return await real(*args, **kwargs)
    monkeypatch.setattr(provider.graphiti.embedder, "create", counted)
    assert provider.update_metadata(a, USER, {"superseded_by": "u0-e09"})
    assert calls == []
    got = provider.get(a, USER)
    assert got.metadata["superseded_by"] == "u0-e09"
    assert got.content == "My chat tool is Slack."
    assert got.metadata["memory_type"] == "profile"


def test_the_scrub_reaches_episodes_names_and_summaries(provider):
    """``scrub_history`` blanks the episodes that carry a form (and the
    deleted rows' episodes), deletes an episode left with no fact and no
    text, deletes entities named by a form and blanks summaries that
    carry one; no LLM call."""
    from graphiti_core.nodes import EntityNode

    kept = provider.add(note("I live in Utrecht.", slot="home_city",
                             event="u0-e01"))
    gone = provider.add(note("My chat tool is Mattermost.", event="u0-e02"))
    echo = provider.add(note("Retro notes go in Mattermost #retro.",
                             owner="calendar_agent", event="u0-e03"))
    group = provider._group(USER)
    provider.runner.run(provider.graphiti.nodes.entity.save, EntityNode(
        name="Mattermost", group_id=group, summary="A chat tool."))
    assert provider.delete(gone, USER)
    calls = len(provider.graphiti.llm_client.calls)
    counts = provider.scrub_history(USER, ["Mattermost"], [gone], [kept])

    async def state():
        driver = provider.graphiti.driver
        episodes, _, _ = await driver.execute_query(
            "MATCH (ep:Episodic {group_id: $group}) "
            "RETURN ep.uuid AS uuid, ep.content AS content",
            params={"group": group})
        entities, _, _ = await driver.execute_query(
            "MATCH (n:Entity {group_id: $group}) "
            "RETURN n.name AS name, n.summary AS summary",
            params={"group": group})
        return ({r["uuid"]: r["content"] for r in episodes},
                {r["name"]: r["summary"] for r in entities})
    episodes, entities = provider.runner.run(state)
    # The deleted write's episode had no fact left: deleted with it.
    assert gone.split(":")[1] not in episodes
    assert episodes[echo.split(":")[1]] == ""
    assert "Utrecht" in episodes[kept.split(":")[1]]
    assert "Mattermost" not in entities
    assert all("Mattermost" not in (s or "") for s in entities.values())
    assert entities["user"] == ""  # its summary held the echo's fact
    # Episodes: the deleted write's, gone with its last fact, and the
    # echo's, blanked. Graphiti appends a fact to the summary of each
    # entity it touches: the Mattermost entity by name, and the
    # summaries of the user and of both facts' entities.
    assert counts == {"messages": 2, "history": 4}
    assert len(provider.graphiti.llm_client.calls) == calls
    # The echo's row is the forget's to delete; the scrub keeps rows.
    assert {r.memory_id for r in provider.list(USER, 100)} == {kept, echo}


def test_the_scrub_reports_the_facts_it_deletes_with_an_entity(provider):
    """An entity named by a form is deleted with the facts still
    attached to it; a fact whose sentence does not carry the form (no
    carrier, so the forget kept it) goes with it, and the scrub reports
    each of its rows as ``detached``, so the forget can count them."""
    sentence = "Our team moved chat tools last week."
    row = provider.add(note(sentence, event="u0-e01"))
    kept = provider.add(note("I live in Utrecht.", slot="home_city",
                             event="u0-e02"))

    async def rename():
        await provider.graphiti.driver.execute_query(
            "MATCH (n:Entity {group_id: $group, name: $name}) "
            "SET n.name = 'Mattermost'",
            params={"group": provider._group(USER),
                    "name": topic(sentence)})
    provider.runner.run(rename)
    counts = provider.scrub_history(USER, ["Mattermost"], [], [row, kept])
    assert counts["detached"] == [
        {"memory_id": row, "owner_agent": "profile_agent"}]
    assert {r.memory_id for r in provider.list(USER, 100)} == {kept}


def test_the_scrub_blanks_a_deleted_rows_episode_that_keeps_a_fact(
        splitting):
    """A deleted row's episode is blanked whatever it holds: here its
    text carries no form and it still holds the write's other fact, so
    it is blanked, kept with that fact, and counted once
    (docs/GRAPHITI_BACKEND.md, "The forget on Graphiti", step 1)."""
    splitting.add(note("I live in Utrecht. My lawyer is Greta."))
    city, lawyer = splitting.list(USER, 100)
    assert lawyer.content == "My lawyer is Greta."
    assert splitting.delete(lawyer.memory_id, USER)
    counts = splitting.scrub_history(USER, ["Sandvik"], [lawyer.memory_id],
                                     [city.memory_id])
    assert episodes_of(splitting) == {city.memory_id.split(":")[1]: ""}
    assert counts == {"messages": 1, "history": 0}
    assert [r.memory_id for r in splitting.list(USER, 100)] == [
        city.memory_id]


def test_the_scrub_counts_an_entity_once(provider):
    """``history`` counts each entity once: an entity whose name and
    summary both carry a form is deleted and counted once, not again as
    a blanked summary (``GraphitiProvider.scrub_history``;
    docs/GRAPHITI_BACKEND.md, "The forget on Graphiti")."""
    from graphiti_core.nodes import EntityNode

    provider.add(note("I live in Utrecht.", slot="home_city"))
    provider.runner.run(provider.graphiti.nodes.entity.save, EntityNode(
        name="Mattermost", group_id=provider._group(USER),
        summary="Mattermost is a chat tool."))
    counts = provider.scrub_history(USER, ["Mattermost"], [], [])
    assert counts == {"messages": 0, "history": 1}
    assert "Mattermost" not in entity_names(provider)


def test_the_scrub_matches_forms_as_the_scorer_does(provider):
    """The scrub's "carries a form" is the scorer's matcher
    (``aios.memory.pipeline.matching``; docs/GRAPHITI_BACKEND.md, "The
    forget on Graphiti"): a form in another case is a match, a form
    inside a longer word is not."""
    lower = provider.add(note("Our team chat is slack now.", event="u0-e01"))
    longer = provider.add(note("Slackware is my distro.", slot="distro",
                               event="u0-e02"))
    provider.scrub_history(USER, ["Slack"], [], [lower, longer])
    texts = episodes_of(provider)
    assert texts[lower.split(":")[1]] == ""
    assert texts[longer.split(":")[1]] == "user: Slackware is my distro."


def test_search_is_graphitis_own_and_leaves_its_recipe_alone(provider):
    """``search`` returns Graphiti's ``search()`` facts in its order,
    unscored, and never changes the shared recipe ``search()`` and
    ingestion read."""
    from graphiti_core.search.search_config_recipes import (
        EDGE_HYBRID_SEARCH_RRF,
    )

    for text, event in (("I edit code in VS Code with Python.", "e1"),
                        ("My project is a Rust web server.", "e2"),
                        ("A lasagna needs ricotta and basil.", "e3")):
        provider.add(note(text, event=event))
    limit = EDGE_HYBRID_SEARCH_RRF.limit
    query = "Which editor does the user prefer"
    found = provider.search(query, USER, 40)
    assert EDGE_HYBRID_SEARCH_RRF.limit == limit
    assert all(r.score is None for r in found)
    plain = provider.runner.run(provider.graphiti.search, query,
                                group_ids=[provider._group(USER)],
                                num_results=limit)
    assert [r.content for r in found] == [e.fact for e in plain]
    assert provider.search(query, USER, 1) == found[:1]
    assert provider.search("   ", USER, 10) == []


def test_groups_are_valid_and_one_per_user(provider):
    """Group ids hold only Graphiti's characters, and two user ids that
    read alike never share one."""
    from cerebrum.utils.graphiti import GROUP_ID, group_id

    a, b = group_id("ana@users.example"), group_id("ana_users_example")
    assert GROUP_ID.match(a) and GROUP_ID.match(b) and a != b
    provider.add(note("I live in Utrecht.", user="ana@users.example"))
    assert provider.list("ana_users_example", 10) == []
    assert len(provider.list("ana@users.example", 10)) == 1
    assert provider.list(None, 10) == []  # the default scope, not all


def test_capabilities_and_extraction():
    from aios.memory.providers.graphiti import GraphitiProvider

    provider = GraphitiProvider()
    assert provider.capabilities() == {
        "scored_search": False, "semantic_search": True,
        "internal_llm": True, "native_sdk": True}
    assert provider.backend_extraction is True
    assert GraphitiProvider.synchronous_commit is False
    assert topic("x") != topic("y")


def test_json_is_written_as_the_users_message(provider):
    """A JSON write (the V5 writer stores its structured JSON) is the
    user's message, as any other statement: as a ``json`` episode it has
    no subject, and Graphiti extracted no fact from one."""
    content = '{"fact_key": "project", "value": "Larkspur migration"}'
    first = provider.add(note(content, event="u0-e07"))
    assert first

    async def episode():
        records, _, _ = await provider.graphiti.driver.execute_query(
            "MATCH (ep:Episodic {uuid: $uuid}) "
            "RETURN ep.content AS content, ep.source AS source",
            params={"uuid": first.split(":")[1]})
        return records[0]
    stored = provider.runner.run(episode)
    assert stored["content"] == f"user: {content}"
    assert stored["source"] == "message"


def test_a_conversation_turn_is_written_as_its_two_messages(provider):
    """A stored conversation turn (``User: ...\\nAssistant: ...``) is one
    episode of two chat lines, ``user:`` and ``assistant:``, the
    documented message format (docs/GRAPHITI_BACKEND.md, "One episode
    per write")."""
    turn = "User: I moved to Utrecht.\nAssistant: Welcome to Utrecht!"
    first = provider.add(note(turn, owner="assistant_agent",
                              memory_type="conversation", event="u0-e03"))
    assert first
    stored = episode_of(provider, first)
    assert stored["content"] == (
        "user: I moved to Utrecht.\nassistant: Welcome to Utrecht!")
    assert stored["source"] == "message"


def test_the_episodes_reference_time_is_the_notes_created_at(provider):
    """An episode's reference time is the note's ``created_at`` (UTC, set
    by the kernel at acceptance), not the time the write is processed,
    so later writes have later reference times (docs/GRAPHITI_BACKEND.md,
    "One episode per write")."""
    first = provider.add(note("I live in Utrecht.",
                              created_at="2026-03-04T05:06:07+00:00"))
    assert first
    valid_at = episode_of(provider, first)["valid_at"].to_native()
    assert valid_at == datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone.utc)
