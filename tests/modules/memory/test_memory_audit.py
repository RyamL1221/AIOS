"""The kernel's raw audit listing and the barrier sequences of requests
that fail before the library runs.

- ``MemoryManager.audit_rows`` and ``GET /memory/audit`` list every row
  the store holds for a user, of every agent, with no visibility rule
  and no tombstone guard: the benchmark's audit of what a forget left
  (docs/DELETION_AND_SUPERSESSION.md, "The audit reads the store"). The
  agents' own paths leave a carrier of a forgotten value out; the audit
  must not.
- A ``forget_memory`` without a slot and an ``add_memory`` whose note
  cannot be built release the barrier sequence stamped when they were
  accepted: a held one would keep every later retrieval of the user
  waiting until the barrier's timeout.
"""
import ast
import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from aios.memory.note import MemoryNote
from aios.memory.pipeline import LIST_TOP_K
from aios.memory.providers.base import Candidate
from tests.modules.memory.test_list_and_delete import (
    USER,
    WRITER,
    Background,
    GatedStore,
    kernel,
    kernel_write,
    request,
)

LAUNCH = Path(__file__).resolve().parents[3] / "runtime" / "launch.py"
FACT = "pet"
VALUE = "Mochi"


def statement(manager, agent, content, fact_key, value, event,
              policy="shared", aliases=()):
    """A v2 statement through the kernel: its fact_key, structured value,
    value_aliases and provenance_event."""
    return kernel_write(
        manager, agent, content, fact_key=fact_key,
        structured=json.dumps({"fact_key": fact_key, "value": value,
                               "event_type": "add"}),
        value_aliases=json.dumps(list(aliases)),
        provenance_event=event, sharing_policy=policy,
    )


def plant(manager, agent, content, user=USER):
    """A row stored straight through the provider, as a carrier that
    escaped the forget would be: no library code runs."""
    return manager.provider.add(MemoryNote(content=content, metadata={
        "owner_agent": agent, "user_id": user, "memory_type": "conversation",
        "sharing_policy": "private", "created_at": "2026-11-10T00:00:00",
    }))


def audit_handler(active_components):
    """``get_memory_audit`` compiled from runtime/launch.py's source
    (importing the module would start the whole kernel)."""
    tree = ast.parse(LAUNCH.read_text())
    node = next(n for n in tree.body
                if getattr(n, "name", None) == "get_memory_audit")
    node.decorator_list = []  # @app.get("/memory/audit")
    namespace = {"asyncio": asyncio, "HTTPException": HTTPException,
                 "active_components": active_components}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(LAUNCH),
                 "exec"), namespace)
    return namespace["get_memory_audit"]


# --- MemoryManager.audit_rows --------------------------------------------


def test_the_audit_lists_every_row_the_guard_hides_from_the_agents():
    """After a forget, a carrier planted straight into the store is left
    out of the owner's listing, but the audit returns it with its text,
    with every other agent's rows, private ones included."""
    manager = kernel()
    statement(manager, WRITER, f"My cat is {VALUE}.", FACT, VALUE, "e1")
    private = kernel_write(manager, "task_agent", "My client is Norvik.",
                           sharing_policy="private")
    assert request(manager, WRITER, "forget_memory", user_id=USER,
                   fact_key=FACT).success
    carrier = plant(manager, "assistant_agent", f"{VALUE} purred.")

    listed = request(manager, "assistant_agent", "list_memory",
                     user_id=USER)
    assert carrier not in [r["memory_id"] for r in listed.search_results]

    audit = manager.audit_rows(USER)
    rows = {row["memory_id"]: row for row in audit["rows"]}
    assert set(rows) == {private, carrier}
    assert rows[carrier]["content"] == f"{VALUE} purred."
    assert rows[private]["metadata"]["owner_agent"] == "task_agent"
    assert audit["user_id"] == USER and audit["at_limit"] is False


def test_the_audit_canonicalizes_the_user():
    """The audit lists the partition the kernel stores under (its
    identity rules), as every request does."""
    manager = kernel({"identity": {"casefold": True}})
    memory_id = kernel_write(manager, WRITER, "I live in Tallinn.",
                             user="Alice")
    audit = manager.audit_rows("ALICE")
    assert audit["user_id"] == "alice"
    assert [row["memory_id"] for row in audit["rows"]] == [memory_id]


def test_an_audit_at_the_listing_limit_says_so():
    """A listing that reaches LIST_TOP_K may be cut: ``at_limit``."""
    manager = kernel()
    full = [Candidate(memory_id=str(i), content="x",
                      metadata={"user_id": USER})
            for i in range(LIST_TOP_K)]
    with patch.object(manager.provider, "list", return_value=full):
        audit = manager.audit_rows(USER)
    assert audit["at_limit"] is True and len(audit["rows"]) == LIST_TOP_K


def test_the_audit_waits_for_the_users_writes_accepted_before_it():
    """Like a listing, the audit waits for writes still committing, so
    it lists what the user's writes stored."""
    manager = kernel({"write_barrier": {"timeout_ms": 30_000}})
    manager.provider = GatedStore()
    manager.provider.initialize({})
    manager.provider.gate.clear()
    write = Background(kernel_write, manager, WRITER, "I live in Riga.")
    audit = Background(manager.audit_rows, USER)
    audit.thread.join(0.3)
    assert audit.thread.is_alive()  # waiting for the write
    manager.provider.gate.set()
    write.thread.join(5)
    audit.thread.join(5)
    assert [row["content"] for row in audit.result["rows"]] \
        == ["I live in Riga."]


# --- GET /memory/audit -------------------------------------------------


def test_the_route_answers_with_the_managers_audit():
    manager = kernel()
    memory_id = kernel_write(manager, WRITER, "I live in Riga.")
    handler = audit_handler({"memory": manager})
    body = asyncio.run(handler(user_id=USER))
    assert [row["memory_id"] for row in body["rows"]] == [memory_id]


def test_the_route_fails_loudly():
    """No manager: 400. An audit that raised: 500, never an empty
    listing that would read as a store with no carrier."""
    with pytest.raises(HTTPException) as missing:
        asyncio.run(audit_handler({})(user_id=USER))
    assert missing.value.status_code == 400

    manager = kernel()
    with patch.object(manager.provider, "list",
                      side_effect=RuntimeError("store unreadable")):
        with pytest.raises(HTTPException) as failed:
            asyncio.run(audit_handler({"memory": manager})(user_id=USER))
    assert failed.value.status_code == 500
    assert "store unreadable" in failed.value.detail


# --- barrier sequences of requests that fail early -----------------------


def test_a_forget_without_a_slot_releases_its_barrier_sequence():
    """The kernel stamps a forget's sequence when it is accepted; a
    forget the library refuses must release it."""
    manager = kernel()
    response = request(manager, WRITER, "forget_memory", user_id=USER)
    assert response.success is False and "fact_key" in response.error
    assert manager.barrier.stats()["total_pending"] == 0


def test_an_add_whose_note_cannot_be_built_releases_its_sequence():
    """An add that fails before the library runs releases the sequence
    stamped at acceptance, and answers instead of raising."""
    manager = kernel()
    with patch.object(manager, "_analyze_query_to_memory",
                      side_effect=ValueError("bad note")):
        response = request(manager, WRITER, "add_memory", content="x",
                           metadata={"owner_agent": WRITER,
                                     "user_id": USER})
    assert response.success is False and "bad note" in response.error
    assert manager.barrier.stats()["total_pending"] == 0
