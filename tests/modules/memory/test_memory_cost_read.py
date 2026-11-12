"""``GET /memory/cost`` reads a trial's backend usage after the writes
accepted before it (NeurIPS Subtask 16).

The kernel stores a chat turn after the reply, in the background
(``ConversationExtractor``), and a Graphiti write makes its LLM calls one
after another, so between two of them none is in flight for
``UsageAccumulator.take`` to wait on: a read taken mid-write missed the
write's later calls, which were then recorded under a tag nobody read.
The read now waits for the user's writes first, as a retrieval does.
"""
import ast
import asyncio
from pathlib import Path

from cerebrum.utils import usage

from aios.memory.conversation_extractor import ConversationExtractor
from tests.modules.memory.test_list_and_delete import (
    ASSISTANT,
    USER,
    WAIT,
    Background,
    GatedStore,
    kernel,
)

LAUNCH = Path(__file__).resolve().parents[3] / "runtime" / "launch.py"


def cost_handler(active_components):
    """``get_memory_cost`` compiled from runtime/launch.py's source
    (importing the module would start the whole kernel)."""
    tree = ast.parse(LAUNCH.read_text())
    node = next(n for n in tree.body
                if getattr(n, "name", None) == "get_memory_cost")
    node.decorator_list = []  # @app.get("/memory/cost")
    namespace = {"asyncio": asyncio, "backend_usage": usage,
                 "active_components": active_components}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(LAUNCH),
                 "exec"), namespace)
    return namespace["get_memory_cost"]


class CallingStore(GatedStore):
    """The gated store, recording one backend LLM call under the
    current usage tag once the gate opens, as a write's extraction
    would, with nothing in flight before it."""

    def add(self, memory_note):
        assert self.gate.wait(WAIT)
        usage.ACCUMULATOR.record(usage.current_tag(),
                                 usage.BACKEND_EXTRACTION, "azure/gpt-4o",
                                 100, 10)
        return super(GatedStore, self).add(memory_note)


def test_the_cost_read_waits_for_the_turn_still_being_stored():
    manager = kernel()
    provider = manager.provider = CallingStore()
    read = cost_handler({"memory": manager})
    provider.gate.clear()
    ConversationExtractor(manager, {"auto_extract": True}).extract_async(
        ASSISTANT, "Who is my lawyer?", "Greta Sandvik.", user_id=USER,
    )
    cost = Background(lambda: asyncio.run(read(USER, 0.0)))
    assert not cost.done(0.3)  # waiting on the turn
    provider.gate.set()
    assert cost.done(WAIT)
    assert cost.result["backend_llm_tokens"]["calls"] == 1
    assert cost.result["barrier_wait"] == "DRAINED"
    assert usage.ACCUMULATOR.take(USER, 0.0) == []  # nothing left behind


def test_the_cost_read_of_a_user_with_no_write_does_not_wait():
    manager = kernel()
    manager.provider = CallingStore()
    cost = Background(lambda: asyncio.run(
        cost_handler({"memory": manager})("nobody", 0.0)))
    assert cost.done(1)
    assert cost.result["backend_llm_tokens"]["calls"] == 0
    assert cost.result["barrier_wait"] == "BYPASSED"
