"""Kernel ablation switches (NeurIPS Subtask 19, docs/ABLATION.md).

One ``memory.ablate`` block, one switch per kernel responsibility, each
removing that component alone; every switch defaults to the full
kernel. Each test runs the same requests with the switch on and off.
The library runs on the in-memory provider; tests of a wait use a store
whose writes a read must wait for (``AsyncCommit``).
"""
import dataclasses
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from cerebrum.llm.apis import LLMQuery
from cerebrum.memory.apis import MemoryQuery

from aios.memory.context_injector import ContextInjector
from aios.memory.manager import MemoryManager
from aios.memory.pipeline import (
    ALIASES,
    SWITCHES,
    Ablation,
    MemoryPipeline,
    PipelineSettings,
    parse_switch,
)
from aios.memory.pipeline.formatter import BLOCK_HEADER
from aios.memory.providers.in_house import InHouseProvider
from tests.modules.memory.test_forget_and_supersession import (
    ALIAS,
    SLOT,
    VALUE,
    stated,
    stored,
)
from tests.modules.memory.test_list_and_delete import (
    ASSISTANT,
    USER,
    WRITER,
    store,
    write,
)

ROOT = Path(__file__).resolve().parents[3]
TASK = "task_agent"
CONFIG = {
    "provider": "in-memory",
    "relevance_threshold": 0.0,
    "max_injected_memories": 30,
    "max_memory_tokens": 300,
    "write_barrier": {"enabled": True, "timeout_ms": 5000},
    "auto_inject": True,
    "identity": {"casefold": True, "email_domains": ["users.example"]},
}


class AsyncCommit(InHouseProvider):
    """The in-memory provider, as a store whose writes a read must wait
    for (Chroma, Mem0)."""

    synchronous_commit = False


def kernel(provider=None, **memory_config):
    """A MemoryManager on ``CONFIG`` with ``memory_config`` over it."""
    config_block = dict(CONFIG, **memory_config)
    with patch("aios.memory.manager.global_config") as config:
        config.get_memory_config.return_value = config_block
        config.get_storage_config.return_value = {}
        manager = MemoryManager()
    if provider is not None:
        manager.provider = provider
    return manager, ContextInjector(manager, config_block)


def syscall(agent, operation, params):
    from aios.syscall.memory import MemorySyscall as Call

    call = Call(agent, MemoryQuery(operation_type=operation, params=params))
    return call


def add(manager, agent, content, user=USER, policy="shared",
        memory_type="profile", **metadata):
    """A write through the kernel: stamped, then served."""
    call = syscall(agent, "add_memory", {"content": content, "metadata": {
        "owner_agent": agent, "user_id": user, "memory_type": memory_type,
        "sharing_policy": policy, **metadata,
    }})
    manager.stamp_syscall(call)
    response = manager.address_request(call)
    assert response.success, response.error
    return response


def chat(injector, text, user=USER, agent=ASSISTANT, **kwargs):
    query = LLMQuery(messages=[{"role": "user", "content": text}],
                     action_type="chat")
    return injector.inject(agent, query, user_id=user, **kwargs)[1]


def block_ids(diagnostics):
    return [m["memory_id"] for m in diagnostics["injected_memories"]]


# --- the block -------------------------------------------------------------


def test_every_switch_defaults_to_the_full_kernel():
    full = Ablation()
    assert full.full and full.changed() == {}
    assert {name: value for name, (value, _, _) in SWITCHES.items()} == (
        full.as_dict())
    assert Ablation.from_config(None) == Ablation.from_config({}) == full


def test_yaml_on_and_off_read_as_the_switch_values():
    """YAML 1.1 reads a bare ``on`` / ``off`` as a boolean."""
    block = yaml.safe_load("barrier: off\nquota: on\nthreshold: 0.3\n")
    ablation = Ablation.from_config(block)
    assert ablation.changed() == {"barrier": "off", "threshold": 0.3}


@pytest.mark.parametrize("block, message", [
    ({"barier": "off"}, "unknown keys"),
    ({"barrier": "of"}, "barrier must be one of"),
    ({"forget_scope": "agent"}, "forget_scope must be one of"),
    ({"threshold": "high"}, "threshold must be null or a number"),
    ({"threshold": True}, "threshold must be null or a number"),
    ("off", "must be a mapping"),
])
def test_an_unknown_switch_or_value_is_refused(block, message):
    with pytest.raises(ValueError, match=message):
        Ablation.from_config(block)


def test_a_bad_block_fails_the_kernel_at_startup():
    with pytest.raises(ValueError, match="memory.ablate"):
        kernel(ablate={"visibility": "partial"})


@pytest.mark.parametrize("text, switch", [
    ("barrier", ("barrier", "off")),
    ("identity", ("identity", "claim")),
    ("forget_scope", ("forget_scope", "writer")),
    ("forget_scope=none", ("forget_scope", "none")),
    ("threshold", ("threshold", 0.3)),
    ("threshold=0.45", ("threshold", 0.45)),
    ("consumer_config", ("consumer_config", "honor")),
])
def test_a_bare_switch_takes_its_ablated_value(text, switch):
    assert parse_switch(text) == switch


def test_parse_switch_refuses_an_unknown_switch_or_value():
    with pytest.raises(ValueError, match="unknown ablation switch"):
        parse_switch("cache")
    with pytest.raises(ValueError, match="must be one of"):
        parse_switch("barrier=maybe")


def test_the_old_controls_are_ablations():
    assert ALIASES == {
        "no_visibility": {"visibility": "off"},
        "no_delete": {"forget_scope": "none"},
        "writer_scoped": {"forget_scope": "writer"},
        "no_supersession": {"supersession": "off"},
    }
    for switches in ALIASES.values():
        assert Ablation.from_config(switches).changed() == switches


def test_the_kernel_reports_the_block_and_a_replicated_copy_keeps_it():
    """``/memory/config`` ``pipeline.ablate``, with defaults filled in;
    the settings a replicated agent builds from the report carry it."""
    manager, _ = kernel(ablate={"quota": "off", "threshold": 0.3})
    report = manager.pipeline_settings().as_dict()
    assert report["ablate"] == dict(Ablation().as_dict(), quota="off",
                                    threshold=0.3)
    copy = PipelineSettings.from_memory_config(report)
    assert copy.ablation.changed() == {"quota": "off", "threshold": 0.3}
    assert kernel()[0].pipeline_settings().as_dict()["ablate"] == (
        Ablation().as_dict())


def test_a_switch_never_rewrites_another_setting():
    """The reported settings are the configured ones; only the
    ``effective_*`` values change."""
    settings = PipelineSettings(
        supersession="exclude", relevance_threshold=0.0,
        write_barrier={"enabled": True}, write_quota={"enabled": True},
        ablate={"supersession": "off", "threshold": 0.3, "barrier": "off",
                "quota": "off", "block_format": "legacy"},
    )
    assert (settings.supersession, settings.relevance_threshold,
            settings.block_format) == ("exclude", 0.0, "compact")
    assert settings.write_barrier["enabled"] is True
    assert settings.write_quota["enabled"] is True
    assert (settings.effective_supersession, settings.effective_threshold,
            settings.effective_block_format) == ("off", 0.3, "legacy")
    assert settings.effective_write_barrier["waits"] is False
    assert settings.effective_write_barrier["enabled"] is True
    assert settings.effective_write_quota["enabled"] is False


def test_both_config_files_ship_the_full_kernel():
    for name in ("config.yaml.example", "config.yaml"):
        path = ROOT / "aios" / "config" / name
        if not path.exists():
            continue
        block = yaml.safe_load(path.read_text())["memory"]["ablate"]
        assert set(block) == set(SWITCHES)
        assert Ablation.from_config(block).full, name


# --- barrier: off ----------------------------------------------------------


def test_without_the_barrier_a_chat_reads_before_a_write_accepted_first():
    """Full kernel: a chat arriving after a write was accepted waits for
    it, and its block holds the write. ``barrier: off``: the write is
    still stamped and the chat still gets its arrival snapshot (so
    which writes it could have waited for is known), but it reads at
    once, before the write is served."""
    for barrier, waits in (("on", True), ("off", False)):
        manager, injector = kernel(AsyncCommit(), ablate={"barrier": barrier})
        call = syscall(WRITER, "add_memory", {
            "content": "Trip to Porto in May.",
            "metadata": {"owner_agent": WRITER, "user_id": USER,
                         "memory_type": "calendar",
                         "sharing_policy": "shared"},
        })
        manager.stamp_syscall(call)
        assert call.barrier_seq >= 1
        snapshot = manager.arrival_snapshot(USER)
        assert snapshot == call.barrier_seq
        done = {}
        reader = threading.Thread(target=lambda: done.update(
            d=chat(injector, "which trip?", barrier_snapshot=snapshot),
            at=time.monotonic()))
        reader.start()
        time.sleep(0.3)
        served_at = time.monotonic()
        assert manager.address_request(call).success
        reader.join(5)
        if waits:
            assert done["at"] >= served_at
            assert "Porto" in done["d"]["block_text"]
        else:
            assert done["at"] < served_at
            assert done["d"]["block_text"] == ""
            assert done["d"]["barrier_waits"] == []
            assert done["d"]["barrier_snapshot"] == snapshot


@pytest.mark.parametrize("read", ["audit", "cost"])
def test_without_the_barrier_the_harness_reads_still_wait(read):
    """The audit and the cost reads are measurements, not agents' reads:
    under ``barrier: off`` they still wait for the writes accepted
    before them."""
    manager, _ = kernel(AsyncCommit(), ablate={"barrier": "off"})
    call = syscall(WRITER, "add_memory", {
        "content": "Trip to Porto in May.",
        "metadata": {"owner_agent": WRITER, "user_id": USER,
                     "memory_type": "calendar", "sharing_policy": "shared"},
    })
    manager.stamp_syscall(call)
    done = {}

    def run():
        done["value"] = (manager.audit_rows(USER) if read == "audit"
                         else manager.await_writes(USER))
        done["at"] = time.monotonic()

    reader = threading.Thread(target=run)
    reader.start()
    time.sleep(0.3)
    assert "at" not in done, "the read did not wait"
    served_at = time.monotonic()
    assert manager.address_request(call).success
    reader.join(5)
    assert done["at"] >= served_at
    if read == "audit":
        assert [r["content"] for r in done["value"]["rows"]] == [
            "Trip to Porto in May."]


def test_a_replicated_copy_keeps_its_bookkeeping_and_skips_its_waits():
    settings = PipelineSettings(write_barrier={"enabled": True},
                                ablate={"barrier": "off"})
    pipeline = MemoryPipeline(AsyncCommit(), settings)
    seq = pipeline.barrier.acquire(USER)
    assert seq >= 1 and pipeline.barrier.snapshot(USER) == seq
    started = time.monotonic()
    assert pipeline.selector.await_pending_writes(USER).name == "BYPASSED"
    assert time.monotonic() - started < 0.5
    full = MemoryPipeline(AsyncCommit(), PipelineSettings(
        write_barrier={"enabled": True, "timeout_ms": 200}))
    full.barrier.acquire(USER)
    assert full.selector.await_pending_writes(USER).name == "TIMEOUT"


# --- identity: claim ------------------------------------------------------


def handler(manager, seen):
    from tests.modules.syscall.test_v2_requests import launch_handler

    def execute_request(agent_name, query):
        seen.append(query)
        return {"response": "ok"}

    return launch_handler(execute_request, manager=manager)


@pytest.mark.parametrize("identity", ["session", "claim"])
def test_under_claim_a_session_binds_nothing(identity):
    """Through the ``/query`` handler, with a real session token. Full
    kernel: a wrong-user write and chat are served for the session's
    user and the claim is reported. ``identity: claim``: both keep the
    user they claim and nothing is reported."""
    import asyncio

    manager, _ = kernel(ablate={"identity": identity})
    token = manager.open_session(USER)
    seen = []
    QueryRequest, handle_query = handler(manager, seen)
    write = asyncio.run(handle_query(QueryRequest(
        agent_name=WRITER, query_type="memory", session_token=token,
        query_data=MemoryQuery(operation_type="add_memory", params={
            "content": "x", "metadata": {"user_id": "bob"},
        }).model_dump())))
    asyncio.run(handle_query(QueryRequest(
        agent_name=ASSISTANT, query_type="llm", session_token=token,
        user_id="bob", query_data=json.loads(LLMQuery(
            messages=[{"role": "user", "content": "hi"}],
            action_type="chat").model_dump_json()))))
    filed, chatted = seen
    if identity == "session":
        assert filed.params["metadata"]["user_id"] == USER
        assert write["identity_overridden"] == {"claimed": "bob",
                                                "bound": USER}
        assert chatted._request_user_id == USER
        assert chatted._identity_overridden
    else:
        assert filed.params["metadata"]["user_id"] == "bob"
        assert "identity_overridden" not in write
        assert chatted._request_user_id == "bob"
        assert getattr(chatted, "_identity_overridden", None) is None


def test_under_claim_the_quota_still_buckets_by_the_session():
    """``identity: claim`` drops the binding only: the token still goes
    with the request as the write quota's bucket key."""
    import ast

    tree = ast.parse((ROOT / "runtime" / "launch.py").read_text())
    node = next(n for n in tree.body
                if getattr(n, "name", None) == "accept_memory_request")
    seen = {}

    class Executor:
        def accept_memory(self, agent_name, query, session_token=None):
            seen["token"] = session_token

    manager, _ = kernel(ablate={"identity": "claim"})
    namespace = {"syscall_executor": Executor(),
                 "active_components": {"memory": manager}}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "launch",
                 "exec"), namespace)
    namespace["accept_memory_request"](WRITER, None, "tok-1")
    assert seen["token"] == "tok-1"


def test_the_handler_ignores_a_session_under_claim():
    """Through the ``/query`` handler: the faulty writer's write goes to
    the user it claims, even an unknown token is not refused, and the
    configured identity rules are still reported."""
    import asyncio

    from aios.memory.pipeline import UnknownSession

    manager, _ = kernel(ablate={"identity": "claim"})
    seen = []
    QueryRequest, handle_query = handler(manager, seen)
    body = {
        "agent_name": WRITER, "query_type": "memory",
        "session_token": "not-a-token",
        "query_data": MemoryQuery(operation_type="add_memory", params={
            "content": "x", "metadata": {"user_id": "bob"},
        }).model_dump(),
    }
    result = asyncio.run(handle_query(QueryRequest(**body)))
    assert "identity_overridden" not in result
    assert seen[-1].params["metadata"]["user_id"] == "bob"
    assert manager.configured_identity_rules.as_dict()["email_domains"] == [
        "users.example"]
    assert UnknownSession  # the full kernel refuses it (test_kernel_sessions)


def test_under_claim_ids_are_not_canonicalized():
    """Full kernel: a V2 alias is stored under the canonical id.
    ``identity: claim``: under the alias, so the user's reads miss it."""
    alias = "Alice@users.example"
    for identity, filed in (("session", USER), ("claim", alias)):
        manager, injector = kernel(ablate={"identity": identity})
        add(manager, WRITER, "My cat is Mochi.", user=alias)
        assert [r.memory_id for r in manager.provider.list(filed, 10)]
        found = "Mochi" in chat(injector, "my cat")["block_text"]
        assert found is (identity == "session")


# --- visibility: off ------------------------------------------------------


def test_without_visibility_another_agents_private_row_is_selected():
    for visibility, leaks in (("on", False), ("off", True)):
        manager, injector = kernel(ablate={"visibility": visibility})
        private = add(manager, WRITER, "Just between us: an interview.",
                      policy="private").memory_id
        diagnostics = chat(injector, "between us an interview")
        assert (private in block_ids(diagnostics)) is leaks
        found = manager.memory_pipeline().read(ASSISTANT, USER, private)
        assert (found is not None) is leaks


def test_without_visibility_writes_stay_owner_only():
    manager, _ = kernel(ablate={"visibility": "off"})
    private = add(manager, WRITER, "Just between us: an interview.",
                  policy="private").memory_id
    call = syscall(ASSISTANT, "remove_memory", {
        "memory_id": private, "user_id": USER})
    manager.stamp_syscall(call)
    assert not manager.address_request(call).success
    assert private in stored(manager.provider)


# --- supersession: off ----------------------------------------------------


def test_without_supersession_an_earlier_statement_stays_selected():
    """``memory.supersession: exclude`` with ``supersession: off``: the
    later statement retires nothing, and both rows are selected."""
    for switch, retired in (("on", True), ("off", False)):
        pipeline = MemoryPipeline(store(), PipelineSettings(
            supersession="exclude", ablate={"supersession": switch}))
        first = write(pipeline, WRITER, "My lawyer is Greta Sandvik.",
                      **stated(VALUE, "e1"))
        write(pipeline, WRITER, "My lawyer is now Ivo Berg.",
              **stated("Ivo Berg", "e2", aliases=()))
        marks = stored(pipeline.provider)[first].metadata
        assert bool(marks.get("superseded_by")) is retired
        rows, diagnostics = pipeline.retrieve(ASSISTANT, USER, "my lawyer")
        assert (first in [r["memory_id"] for r in rows]) is not retired
        assert bool(diagnostics["superseded_rows"]) is retired


# --- forget_scope ---------------------------------------------------------


def echo_store(forget_scope):
    """The writer's statement, its own fold of the value under another
    slot, and another writer's echo of it."""
    pipeline = MemoryPipeline(store(), PipelineSettings(
        ablate={"forget_scope": forget_scope}))
    rows = {
        "statement": write(pipeline, WRITER, "My lawyer is Greta Sandvik.",
                           **stated(VALUE, "e1")),
        "own_fold": write(pipeline, WRITER,
                          "I live near Greta Sandvik's office.",
                          fact_key="home"),
        "echo": write(pipeline, TASK, "Meeting with Sandvik on Friday.",
                      memory_type="task_context", fact_key="meeting"),
    }
    return pipeline, rows


def test_a_writer_scoped_forget_leaves_other_agents_carriers():
    """``forget_scope: writer``: the writer's own rows (its statement and
    its own carrier) go; another agent's echo stays; no tombstone, so no
    later read or write hides the echo."""
    pipeline, rows = echo_store("writer")
    report = pipeline.forget(WRITER, USER, SLOT)
    assert sorted(e["memory_id"] for e in report["deleted"]) == sorted(
        [rows["statement"], rows["own_fold"]])
    assert report["forget_scope"] == "writer"
    assert list(stored(pipeline.provider)) == [rows["echo"]]
    assert pipeline.tombstones.entries(USER) == []
    found, _ = pipeline.retrieve(ASSISTANT, USER, "meeting with Sandvik")
    assert rows["echo"] in [r["memory_id"] for r in found]


def test_a_user_scoped_forget_deletes_every_carrier():
    pipeline, rows = echo_store("user")
    report = pipeline.forget(WRITER, USER, SLOT)
    assert sorted(e["memory_id"] for e in report["deleted"]) == sorted(
        rows.values())
    assert "forget_scope" not in report  # the full kernel's report
    assert pipeline.tombstones.forms(USER) == [VALUE, ALIAS]


def test_a_forget_scoped_to_none_deletes_and_records_nothing():
    pipeline, rows = echo_store("none")
    report = pipeline.forget(WRITER, USER, SLOT)
    assert (report["deleted"], report["forget_scope"]) == ([], "none")
    assert sorted(stored(pipeline.provider)) == sorted(rows.values())
    assert pipeline.tombstones.entries(USER) == []


def test_a_writer_scoped_forget_scrubs_only_what_it_deleted():
    calls = []

    class Scrubbed(InHouseProvider):
        def scrub_history(self, user_id, forms, deleted_ids=(),
                          kept_ids=()):
            calls.append((list(forms), sorted(deleted_ids), list(kept_ids)))
            return {"messages": 0, "history": 0}

    provider = Scrubbed()
    provider.initialize({})
    pipeline = MemoryPipeline(provider, PipelineSettings(
        ablate={"forget_scope": "writer"}))
    statement = write(pipeline, WRITER, "My lawyer is Greta Sandvik.",
                      **stated(VALUE, "e1"))
    write(pipeline, TASK, "Meeting with Sandvik on Friday.",
          memory_type="task_context", fact_key="meeting")
    pipeline.forget(WRITER, USER, SLOT)
    assert calls == [([], [statement], [])]


# --- quota: off -----------------------------------------------------------


def test_without_the_quota_a_flood_is_stored_whole():
    """``memory.write_quota`` on: four writes of a writer per user and
    session, then rejections. ``quota: off``: every write stored, and
    the quota is still reported on."""
    quota = {"enabled": True, "max_writes": 4, "dedupe": True}
    for switch, kept in (("on", 4), ("off", 10)):
        manager, _ = kernel(write_quota=quota, ablate={"quota": switch})
        for i in range(10):
            add(manager, WRITER, f"Flood note number {i}.", session=1)
        assert len(stored(manager.provider)) == kept
        assert manager.pipeline_settings().write_quota["enabled"] is True


# --- block format, order, budget, threshold ------------------------------


def block_of(settings, rows, query):
    pipeline = MemoryPipeline(store(), settings)
    for agent, content, memory_type in rows:
        write(pipeline, agent, content, memory_type=memory_type)
    return pipeline.inject(ASSISTANT, [{"role": "user", "content": query}],
                           user_id=USER)[1]


ROWS = [
    (TASK, "Trip planning: Porto flights booked.", "task_context"),
    (WRITER, "Name: Ana. Likes Porto and trains.", "profile"),
    (TASK, "Porto trip budget is tight.", "task_context"),
]


def test_legacy_format_switch_prints_the_pre_9d_block():
    compact = block_of(PipelineSettings(), ROWS, "Porto trip")
    legacy = block_of(PipelineSettings(ablate={"block_format": "legacy"}),
                      ROWS, "Porto trip")
    assert compact["block_text"].startswith("Known about this user:")
    assert legacy["block_text"].startswith(BLOCK_HEADER)
    assert legacy["block_format"] == "legacy"


def test_similarity_order_keeps_the_selectors_score_order():
    """Type order prints the profile first; score order keeps the rows
    as ranked, whatever their type."""
    typed = block_of(PipelineSettings(), ROWS, "Porto trip budget tight")
    scored = block_of(PipelineSettings(ablate={"block_order": "similarity"}),
                      ROWS, "Porto trip budget tight")
    def types(diagnostics):
        return [m["memory_type"] for m in diagnostics["injected_memories"]]

    assert types(typed) == ["profile", "task_context", "task_context"]
    assert "block_order" not in typed  # the full kernel's, as before
    assert scored["block_order"] == "similarity"
    assert types(scored) == ["task_context", "task_context", "profile"]
    assert scored["block_text"].index("budget is tight") < (
        scored["block_text"].index("Name: Ana"))


def test_without_the_budget_k_alone_limits_the_block():
    rows = [(WRITER, f"Porto note {i}: " + "word " * 40, "profile")
            for i in range(12)]
    budgeted = block_of(PipelineSettings(max_memory_tokens=300,
                                         max_injected_memories=30),
                        rows, "Porto note")
    unbounded = block_of(PipelineSettings(max_memory_tokens=300,
                                          max_injected_memories=30,
                                          ablate={"budget": "off"}),
                         rows, "Porto note")
    assert budgeted["after_budget"] < budgeted["after_cap"] == 12
    assert unbounded["after_budget"] == unbounded["after_cap"] == 12
    assert unbounded["tokens_estimated"] > 300


def test_the_threshold_switch_drops_rows_below_it():
    full = block_of(PipelineSettings(), ROWS, "Porto trip budget tight")
    ablated = block_of(PipelineSettings(ablate={"threshold": 0.3}),
                       ROWS, "Porto trip budget tight")
    assert ablated["threshold_used"] == 0.3 and full["threshold_used"] == 0.0
    assert ablated["after_threshold"] < full["after_threshold"]


# --- consumer_config: honor -----------------------------------------------

V4 = {"k": 5, "relevance_threshold": 0.5, "max_memory_tokens": 1500}


V4_QUERY = "Porto tram line"
STOPS = ("one", "two", "three", "four", "five", "six", "seven", "eight")


def v4_kernel(consumer_config):
    """Eight rows that score above V4's 0.5 against ``V4_QUERY`` (so its
    k of 5 binds) and one that scores 0 (so its threshold drops it)."""
    manager, injector = kernel(ablate={"consumer_config": consumer_config})
    for stop in STOPS:
        add(manager, WRITER, f"Porto tram line {stop}.")
    add(manager, TASK, "Tax return due in April.",
        memory_type="task_context")
    return manager, injector


def test_the_kernel_ignores_a_consumers_own_config_by_default():
    manager, injector = v4_kernel("kernel")
    sent = chat(injector, V4_QUERY, consumer_config=V4)
    plain = chat(injector, V4_QUERY)
    assert sent["consumer_config"] == {"sent": V4, "applied": False}
    assert "consumer_config" not in plain
    assert block_ids(sent) == block_ids(plain)


def test_under_honor_the_kernel_block_is_the_replicated_v4_block():
    """``consumer_config: honor``: the kernel applies the consumer's k,
    threshold and budget, and its block is the one a replicated V4
    consumer builds over the same store (Cerebrum
    ``variants.base._replicated_pipeline``)."""
    manager, injector = v4_kernel("honor")
    honored = chat(injector, V4_QUERY, consumer_config=V4)
    assert honored["consumer_config"] == {"sent": V4, "applied": True}
    assert honored["threshold_used"] == 0.5
    assert (honored["after_threshold"], honored["after_cap"]) == (8, 5)
    replicated = MemoryPipeline(
        manager.provider,
        dataclasses.replace(
            PipelineSettings.from_memory_config(
                manager.pipeline_settings().as_dict()),
            max_injected_memories=5, relevance_threshold=0.5,
            max_memory_tokens=1500,
        ),
    )
    _, own = replicated.inject(
        ASSISTANT, [{"role": "user", "content": V4_QUERY}], user_id=USER)
    assert honored["block_text"] and honored["block_text"] == own[
        "block_text"]
    assert block_ids(honored) == block_ids(own)
    full = chat(injector, V4_QUERY)
    assert (full["after_threshold"], full["after_cap"]) == (9, 9)


CEREBRUM_VARIANTS = (ROOT.parent / "Cerebrum" / "cerebrum" / "example"
                     / "agents" / "variants")


def cerebrum_variants():
    """Cerebrum's variant modules ``base`` and ``v4_tuned_consumer``,
    loaded by path as a package of their own (they import only the
    standard library), so this test runs the replicated locus's own
    ``_replicated_pipeline``."""
    import importlib
    import sys
    import types

    if not CEREBRUM_VARIANTS.is_dir():
        pytest.skip("no Cerebrum checkout beside AIOS")
    name = "_cerebrum_variants_under_test"
    if name not in sys.modules:
        package = types.ModuleType(name)
        package.__path__ = [str(CEREBRUM_VARIANTS)]
        sys.modules[name] = package
    base = importlib.import_module(f"{name}.base")
    v4 = importlib.import_module(f"{name}.v4_tuned_consumer")
    return base, v4


def test_honor_gives_the_block_cerebrums_replicated_v4_pipeline_gives():
    """The comparison above, with the replicated pipeline built by
    Cerebrum's ``variants.base._replicated_pipeline`` from the V4
    variant (its key mapping, its ``dataclasses.replace``, the same
    provider, barrier, resolver and tombstones) and injected as the
    replicated assistant injects (``pipeline.inject(agent, messages,
    user_id=...)``)."""
    import types

    import aios.memory.pipeline as library

    base, v4 = cerebrum_variants()
    manager, injector = v4_kernel("honor")
    honored = chat(injector, V4_QUERY, consumer_config=dict(v4.TUNED))
    assert honored["after_cap"] == 5
    agent = types.SimpleNamespace(memory=types.SimpleNamespace(
        library=library,
        pipeline=MemoryPipeline(
            manager.provider,
            PipelineSettings.from_memory_config(
                manager.pipeline_settings().as_dict()),
        ),
    ))
    restore = base._Restore()
    tuned = base._replicated_pipeline(v4.VARIANT, agent, "consumer",
                                      restore)
    _, own = tuned.inject(ASSISTANT, [{"role": "user",
                                       "content": V4_QUERY}],
                          user_id=USER)
    assert honored["block_text"] and honored["block_text"] == own[
        "block_text"]
    assert block_ids(honored) == block_ids(own)
    restore.undo()


def test_a_consumer_config_with_an_unknown_key_is_an_injection_error():
    _, injector = v4_kernel("honor")
    diagnostics = chat(injector, V4_QUERY, consumer_config={"top_p": 1})
    assert "unknown keys" in diagnostics["injection_error"]


# --- set_memory_mode.py --ablate ------------------------------------------


def run_set_mode(path, *ablate):
    from scripts.set_memory_mode import main

    args = [str(path), "--provider", "in-house", "--kernel-memory", "on"]
    for value in ablate:
        args += ["--ablate", value]
    main(args)
    return yaml.safe_load(path.read_text())["memory"]["ablate"]


def test_set_memory_mode_sets_and_resets_the_block(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        (ROOT / "aios" / "config" / "config.yaml.example").read_text())
    run_set_mode(path)  # the mode alone: the text to come back to
    original = path.read_text()
    block = run_set_mode(path, "barrier", "threshold=0.3")
    assert Ablation.from_config(block).changed() == {
        "barrier": "off", "threshold": 0.3}
    block = run_set_mode(path, "forget_scope=none")
    assert Ablation.from_config(block).changed() == {"forget_scope": "none"}
    run_set_mode(path, "none")
    assert path.read_text() == original


@pytest.mark.parametrize("ablate", [
    ("none", "barrier"), ("barrier", "barrier=on"), ("cache",),
])
def test_set_memory_mode_refuses_a_bad_ablation(tmp_path, ablate):
    path = tmp_path / "config.yaml"
    path.write_text(
        (ROOT / "aios" / "config" / "config.yaml.example").read_text())
    with pytest.raises(SystemExit):
        run_set_mode(path, *ablate)


# --- what the chat request carries ---------------------------------------


def test_the_handler_carries_a_consumers_retrieval_config():
    import asyncio

    from tests.modules.syscall.test_v2_requests import launch_handler

    seen = []

    def execute_request(agent_name, query):
        seen.append(query)
        return {"response": "ok"}

    QueryRequest, handle_query = launch_handler(execute_request)
    body = {
        "agent_name": ASSISTANT, "query_type": "llm",
        "query_data": json.loads(LLMQuery(
            messages=[{"role": "user", "content": "hi"}],
            action_type="chat", retrieval=V4,
        ).model_dump_json()),
    }
    asyncio.run(handle_query(QueryRequest(**body)))
    assert seen[-1]._request_retrieval == V4
    body["query_data"].pop("retrieval")
    asyncio.run(handle_query(QueryRequest(**body)))
    assert seen[-1]._request_retrieval is None
