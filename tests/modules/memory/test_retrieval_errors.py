"""Failed retrievals are reported, not hidden (docs/BENCHMARK_V2.md,
Amendment 2, "Failed retrievals").

A provider search that raises leaves the selector without rows. Before,
``MemoryPipeline.inject`` dropped the error and the kernel's injector
caught everything else, so a failed fetch looked like an empty store:
an empty block, which passed the deletion and privacy probes. Now the
selector keeps each fetch's error (``error``, ``shared_error``),
injection reports them as one ``retrieval_error``, and the kernel's
injector reports its own failure as ``injection_error``. SDK search
still fails on the own fetch's error only, as before.
"""
import logging
from unittest.mock import MagicMock

import pytest

from cerebrum.llm.apis import LLMQuery
from cerebrum.memory.apis import MemoryQuery

from aios.memory.context_injector import ContextInjector
from aios.memory.manager import MemoryManager
from aios.memory.pipeline import MemoryPipeline
from aios.memory.pipeline.facade import retrieval_error
from aios.memory.providers.base import Candidate
from aios.memory.write_barrier import MemoryWriteBarrier
from aios.syscall.memory import MemorySyscall

AGENT = "assistant_agent"
USER = "alice"
OWN_DOWN = "RuntimeError: embedder timed out"
SHARED_DOWN = "RuntimeError: chroma down"
BOTH_DOWN = f"own: {OWN_DOWN}; shared: {SHARED_DOWN}"

OWN = Candidate(
    "own-1", "User: where is the sync?\nAssistant: Birch.",
    {"owner_agent": AGENT, "user_id": USER,
     "memory_type": "conversation", "sharing_policy": "private"},
    0.6,
)
SHARED = Candidate(
    "shared-1", "Lives in Tallinn.",
    {"owner_agent": "profile_agent", "user_id": USER,
     "memory_type": "profile", "sharing_policy": "shared"},
    0.5,
)


def provider(own_fails=False, shared_fails=False):
    """A provider whose first search (the own fetch) and second (the
    shared fetch) each return one row, or raise as an embedder or store
    failure does: neither real provider catches it."""
    store = MagicMock()
    store.search.side_effect = [
        RuntimeError("embedder timed out") if own_fails else [OWN],
        RuntimeError("chroma down") if shared_fails else [SHARED],
    ]
    return store


def chat(content="where is the sync?"):
    """A chat's messages: one user turn."""
    return [{"role": "user", "content": content}]


def kernel_manager(store):
    """A kernel manager over ``store``, as the injector and SDK search
    use it."""
    manager = MemoryManager.__new__(MemoryManager)
    manager.provider = store
    manager.barrier = MemoryWriteBarrier(config={})
    manager.relevance_threshold = 0.0
    return manager


def injector(manager, enabled=True):
    """The kernel's injector over ``manager``."""
    return ContextInjector(manager, {
        "auto_inject": enabled,
        "max_injected_memories": 5,
        "max_memory_tokens": 2000,
    })


# --- the selector -----------------------------------------------------


def test_selector_keeps_a_failed_shared_fetch_as_shared_error(caplog):
    pipeline = MemoryPipeline(provider(shared_fails=True), barrier=None)
    with caplog.at_level(
        logging.DEBUG, logger="aios.memory.pipeline.selector"
    ):
        rows, diagnostics = pipeline.retrieve(
            AGENT, USER, "sync", k=5, include_shared=True,
        )
    assert [r["memory_id"] for r in rows] == ["own-1"]
    assert diagnostics["error"] is None
    assert diagnostics["shared_error"] == SHARED_DOWN
    # The debug line stays.
    assert (
        f"Shared memory retrieval failed for user_id={USER}: {SHARED_DOWN}"
        in caplog.text
    )


def test_selector_reports_no_shared_error_for_a_good_or_skipped_fetch():
    _, fetched = MemoryPipeline(provider(), barrier=None).retrieve(
        AGENT, USER, "sync", k=5, include_shared=True,
    )
    assert (fetched["error"], fetched["shared_error"]) == (None, None)
    # No user: no shared fetch, so nothing to fail.
    store = provider()
    _, skipped = MemoryPipeline(store, barrier=None).retrieve(
        AGENT, None, "sync", k=5, include_shared=True,
    )
    assert store.search.call_count == 1
    assert skipped["shared_error"] is None


# --- MemoryPipeline.inject --------------------------------------------


@pytest.mark.parametrize("own_fails, shared_fails, expected, injected", [
    (True, False, f"own: {OWN_DOWN}", ["shared-1"]),
    (False, True, f"shared: {SHARED_DOWN}", ["own-1"]),
    (True, True, BOTH_DOWN, []),
])
def test_inject_reports_failed_fetches_as_retrieval_error(
    own_fails, shared_fails, expected, injected,
):
    pipeline = MemoryPipeline(
        provider(own_fails, shared_fails), barrier=None,
    )
    messages, diagnostics = pipeline.inject(AGENT, chat(), user_id=USER)
    assert diagnostics["retrieval_error"] == expected
    # The selector's two keys become this one.
    assert "error" not in diagnostics
    assert "shared_error" not in diagnostics
    # Injection otherwise as before: whatever was fetched is injected.
    assert [m["memory_id"] for m in diagnostics["injected_memories"]] \
        == injected
    assert diagnostics["injected_count"] == len(injected)
    if not injected:
        assert messages == chat() and diagnostics["block_text"] == ""


def test_inject_reports_no_retrieval_error_when_both_fetches_succeed():
    pipeline = MemoryPipeline(provider(), barrier=None)
    _, diagnostics = pipeline.inject(AGENT, chat(), user_id=USER)
    assert diagnostics["retrieval_error"] is None
    assert diagnostics["injected_count"] == 2
    assert "error" not in diagnostics
    # On every path: without a user message nothing is fetched.
    system_only = [{"role": "system", "content": "You are helpful."}]
    _, untouched = pipeline.inject(AGENT, system_only, user_id=USER)
    assert untouched["retrieval_error"] is None


def test_retrieval_error_names_each_failed_fetch():
    assert retrieval_error(None, None) is None
    assert retrieval_error("", None) is None
    assert retrieval_error("a", None) == "own: a"
    assert retrieval_error(None, "b") == "shared: b"
    assert retrieval_error("a", "b") == "own: a; shared: b"


# --- the kernel's ContextInjector -------------------------------------


def test_kernel_injection_reports_a_failed_fetch(caplog):
    manager = kernel_manager(provider(own_fails=True, shared_fails=True))
    query = LLMQuery(messages=chat(), action_type="chat")
    with caplog.at_level(
        logging.WARNING, logger="aios.memory.context_injector"
    ):
        query, diagnostics = injector(manager).inject(
            AGENT, query, user_id=USER,
        )
    assert diagnostics["retrieval_error"] == BOTH_DOWN
    assert diagnostics["injected_count"] == 0
    # The injection itself ran; only the fetches failed.
    assert "injection_error" not in diagnostics
    assert query.messages == chat()
    assert (
        f"Memory retrieval failed for agent={AGENT} "
        f"(resolved_user_id={USER}): {BOTH_DOWN}"
    ) in caplog.text


def test_injector_reports_an_exception_as_injection_error():
    manager = MagicMock()
    manager.memory_pipeline.return_value.inject.side_effect = ValueError(
        "bad block"
    )
    query = LLMQuery(messages=chat(), action_type="chat")
    query, diagnostics = injector(manager).inject(
        AGENT, query, user_id=USER,
    )
    assert diagnostics["injection_error"] == "ValueError: bad block"
    assert diagnostics["injected_count"] == 0
    assert diagnostics["prompt_tokens_after"] == (
        diagnostics["prompt_tokens_before"]
    )
    assert query.messages == chat()


def test_disabled_injection_reports_no_retrieval_error():
    query = LLMQuery(messages=chat(), action_type="chat")
    _, diagnostics = injector(MagicMock(), enabled=False).inject(
        AGENT, query, user_id=USER,
    )
    assert diagnostics["auto_inject_enabled"] is False
    assert diagnostics["retrieval_error"] is None
    assert "injection_error" not in diagnostics


# --- SDK search, unchanged --------------------------------------------


def sdk_search(manager):
    """An SDK ``search_memories`` of shared memories, through
    acceptance and ``address_request``."""
    syscall = MemorySyscall(AGENT, MemoryQuery(
        operation_type="retrieve_memory",
        params={"content": "sync", "k": 5, "user_id": USER,
                "sharing_policy": "shared"},
    ))
    manager.stamp_syscall(syscall)
    return manager.address_request(syscall)


def test_sdk_search_still_fails_on_the_own_fetch_error_only():
    failed = sdk_search(kernel_manager(provider(own_fails=True)))
    assert (failed.success, failed.error) == (False, OWN_DOWN)
    shared_down = sdk_search(kernel_manager(provider(shared_fails=True)))
    assert shared_down.success
    assert [r["memory_id"] for r in shared_down.search_results] == [
        "own-1",
    ]
