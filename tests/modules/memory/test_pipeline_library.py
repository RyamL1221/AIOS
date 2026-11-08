"""The memory pipeline library (NeurIPS Subtask 8).

The equivalence test is the proof that "replicated" means replicated:
for 20 seeded users, the kernel path (``ContextInjector.inject`` and SDK
search through ``MemoryManager``) and a direct ``MemoryPipeline`` call
give byte-identical memory blocks and identical diagnostics, and kernel
writes and library writes store the same rows. Since Subtask 9d it runs
for both block formats: the default ``compact`` block and the ``legacy``
one kept behind ``memory.block_format``.
"""
import json
import random
import subprocess
import sys
from unittest.mock import patch

import pytest

from cerebrum.llm.apis import LLMQuery
from cerebrum.memory.apis import MemoryQuery

from aios.memory.context_injector import ContextInjector
from aios.memory.manager import MemoryManager
from aios.memory.pipeline.formatter import estimate_tokens, format_block
from aios.memory.pipeline import (
    TYPE_ORDER,
    MemoryPipeline,
    PipelineSettings,
    note_from_request,
)
from aios.memory.providers.in_house import InHouseProvider
from aios.syscall.memory import MemorySyscall

MEMORY_CONFIG = {
    "provider": "in-memory",
    "relevance_threshold": 0.05,
    "max_injected_memories": 4,
    "max_memory_tokens": 160,
    "write_barrier": {"enabled": True, "timeout_ms": 500},
    "auto_inject": True,
}
WORDS = (
    "python rust deploy kubernetes latency cache migration schema "
    "postgres benchmark profiler gradient tokenizer pipeline retry "
    "terraform dashboard alerting queue shard replica"
).split()
AGENTS = ("profile_agent", "task_agent", "assistant_agent")


def seeded_requests(seed: int) -> list:
    """(agent, add_memory params) for one user and a few distractors:
    shared profile and task memories, the assistant's private
    conversations, a writer's private note, another user's memory."""
    rng = random.Random(seed)
    user = f"user{seed:02d}"

    def text(n):
        return " ".join(rng.choice(WORDS) for _ in range(n))

    def request(agent, memory_type, policy, content, user_id=user):
        return agent, {
            "content": content,
            "metadata": {
                "owner_agent": agent, "user_id": user_id,
                "memory_type": memory_type, "sharing_policy": policy,
            },
        }

    requests = [
        request("profile_agent", "profile", "shared", json.dumps({
            "user_name": f"User {seed}",
            "preferred_tools": [rng.choice(WORDS), rng.choice(WORDS)],
            "preferred_language": rng.choice(WORDS),
            "response_style": text(3),
        })),
        request("task_agent", "task_context", "shared", json.dumps({
            "current_project": text(3), "active_experiment": text(2),
            "goals": [text(4)], "blockers": [text(3)],
            "next_steps": [text(4), text(3)],
        })),
        request("profile_agent", "profile", "private", text(6)),
        request("task_agent", "task_context", "shared", text(5),
                user_id=f"user{(seed + 1) % 20:02d}"),
    ]
    for _ in range(rng.randint(0, 4)):
        requests.append(request(
            "assistant_agent", "conversation", "private",
            f"User: {text(rng.randint(3, 12))}\nAssistant: {text(20)}",
        ))
    rng.shuffle(requests)
    return requests


def query_text(seed: int) -> str:
    rng = random.Random(1000 + seed)
    return " ".join(rng.choice(WORDS) for _ in range(5))


BLOCK_STARTS = {
    "compact": "Known about this user:\n- ",
    "legacy": "===== MEMORY CONTEXT =====",
}


@pytest.fixture(params=["compact", "legacy"])
def kernel(request):
    """A real MemoryManager on the in-memory provider, its injector, and
    every user's memories written through the kernel's write path; once
    per block format."""
    memory_config = dict(MEMORY_CONFIG, block_format=request.param)
    with patch("aios.memory.manager.global_config") as config:
        config.get_memory_config.return_value = memory_config
        config.get_storage_config.return_value = {}
        manager = MemoryManager()
    injector = ContextInjector(manager, memory_config)
    for seed in range(20):
        for agent, params in seeded_requests(seed):
            syscall = MemorySyscall(agent, MemoryQuery(
                operation_type="add_memory", params=params,
            ))
            manager.stamp_syscall(syscall)
            assert manager.address_request(syscall).success
    return manager, injector


def library_over(manager) -> MemoryPipeline:
    """A direct library call: its own barrier and resolver, with the
    settings the kernel reports at /memory/config (as a replicated agent
    builds them)."""
    return MemoryPipeline(
        manager.provider,
        PipelineSettings.from_memory_config(
            manager.pipeline_settings().as_dict()
        ),
    )


def without_timings(diagnostics: dict) -> dict:
    return {
        key: value for key, value in diagnostics.items()
        if not key.endswith("_ms")
    }


def test_kernel_injection_equals_the_library_for_20_users(kernel):
    manager, injector = kernel
    library = library_over(manager)
    injected_somewhere = 0
    for seed in range(20):
        user = f"user{seed:02d}"
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": query_text(seed)},
        ]
        query = LLMQuery(messages=list(messages), action_type="chat")
        query, kernel_diag = injector.inject(
            "assistant_agent", query, user_id=user
        )
        library_messages, library_diag = library.inject(
            "assistant_agent", list(messages), user_id=user
        )
        # Byte-identical prompts, blocks included.
        assert query.messages == library_messages
        assert without_timings(kernel_diag) == without_timings(library_diag)
        if kernel_diag["injected_count"]:
            injected_somewhere += 1
            block = query.messages[0]["content"]
            assert block.startswith(BLOCK_STARTS[manager.block_format])
            if manager.block_format == "compact":
                bullets = [line for line in block.split("\n")[1:]
                           if line.startswith("- ")]
                assert len(bullets) == kernel_diag["injected_count"]
                assert not any(line.startswith("- [") for line in bullets)
                assert "MEMORY CONTEXT" not in block
        # The private note of another agent and the other user's memory
        # never reach the block.
        for mem in kernel_diag["injected_memories"]:
            assert (mem["owner_agent"] == "assistant_agent"
                    or mem["memory_type"] in ("profile", "task_context"))
    assert injected_somewhere == 20


def test_kernel_sdk_search_equals_the_library_for_20_users(kernel):
    manager, _ = kernel
    library = library_over(manager)
    for seed in range(20):
        user = f"user{seed:02d}"
        for agent in AGENTS:
            for policy in (None, "shared", "private"):
                params = {"content": query_text(seed), "k": 5,
                          "user_id": user}
                if policy:
                    params["sharing_policy"] = policy
                response = manager.address_request(MemorySyscall(
                    agent, MemoryQuery(
                        operation_type="retrieve_memory", params=params,
                    ),
                ))
                rows, _ = library.retrieve(
                    agent, user, query_text(seed), k=5,
                    include_shared=policy == "shared",
                    sharing_policy=policy,
                )
                assert response.search_results == rows


def stored_rows(provider, user: str) -> list:
    """A user's stored rows without the per-write ids and times."""
    volatile = {"created_at", "memory_note_id", "timestamp"}
    return sorted(
        (row.content, json.dumps({
            k: v for k, v in row.metadata.items() if k not in volatile
        }, sort_keys=True))
        for row in provider.list(user, 1000)
    )


def test_kernel_writes_equal_library_writes(kernel):
    manager, _ = kernel
    store = InHouseProvider()
    store.initialize({})
    library = MemoryPipeline(store, PipelineSettings())
    for seed in range(20):
        for agent, params in seeded_requests(seed):
            library.write(agent, None, note_from_request(params))
    for seed in range(20):
        user = f"user{seed:02d}"
        assert stored_rows(manager.provider, user) == stored_rows(store, user)
        assert stored_rows(store, user)


@pytest.mark.parametrize("block_format", ["compact", "legacy"])
def test_block_is_printed_in_type_order_after_ranking(block_format):
    store = InHouseProvider()
    store.initialize({})
    library = MemoryPipeline(store, PipelineSettings(
        max_memory_tokens=10_000, block_format=block_format,
    ))
    rows = [
        {"memory_id": "c", "content": "chat", "score": 0.9, "timestamp": "t",
         "metadata": {"memory_type": "conversation", "owner_agent": "a"}},
        {"memory_id": "t", "content": "task", "score": 0.8, "timestamp": "t",
         "metadata": {"memory_type": "task_context", "owner_agent": "b"}},
        {"memory_id": "x", "content": "other", "score": 0.7, "timestamp": "t",
         "metadata": {"memory_type": "", "owner_agent": "b"}},
        {"memory_id": "p", "content": "profile", "score": 0.1,
         "timestamp": "t",
         "metadata": {"memory_type": "profile", "owner_agent": "b"}},
    ]
    text, diagnostics = library.build_block(rows)
    assert [m["memory_id"] for m in diagnostics["injected_memories"]] == [
        "p", "t", "c", "x",
    ]
    assert TYPE_ORDER == (
        "profile", "task_context", "calendar", "conversation",
    )
    assert text.index("profile") < text.index("task") < text.index("chat")
    # The budget drops the lowest-ranked first (the profile here), not
    # the last printed: a budget that fits three of the four memories
    # keeps the three best-ranked.
    three = estimate_tokens(format_block(rows[:3], block_format))
    four = estimate_tokens(format_block(rows, block_format))
    assert three < four
    small = MemoryPipeline(store, PipelineSettings(
        max_memory_tokens=three, block_format=block_format,
    ))
    _, diagnostics = small.build_block(rows)
    kept = [m["memory_id"] for m in diagnostics["injected_memories"]]
    assert kept == ["t", "c", "x"]


LIBRARY_ONLY = """
import sys
from aios.memory.pipeline import MemoryPipeline, PipelineSettings, note_from_request
from aios.memory.providers.in_house import InHouseProvider
store = InHouseProvider()
store.initialize({})
pipeline = MemoryPipeline(store, PipelineSettings())
pipeline.write("w", "u", note_from_request({"content": "likes rust",
    "metadata": {"memory_type": "profile", "sharing_policy": "shared"}}))
messages, diagnostics = pipeline.inject(
    "assistant", [{"role": "user", "content": "rust"}], user_id="u")
assert diagnostics["injected_count"] == 1, diagnostics
loaded = [m for m in sys.modules if m.startswith(("aios.syscall",
    "aios.memory.manager", "aios.memory.context_injector",
    "aios.config", "aios.scheduler", "aios.llm_core", "runtime"))]
assert not loaded, loaded
print("ok")
"""


def test_library_imports_and_runs_without_the_kernel():
    result = subprocess.run(
        [sys.executable, "-c", LIBRARY_ONLY],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
