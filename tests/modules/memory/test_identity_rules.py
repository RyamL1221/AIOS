"""Identity canonicalization and the judge-free diagnostics (NeurIPS
Subtask 10, docs/HETEROGENEITY.md).

The kernel canonicalizes a user id once, at acceptance, under
``memory.identity``; the library's default resolver leaves ids as they
are, which is what a replicated agent runs. The V2 identity-convention
variant (an email form or a case change of the user id) therefore lands
in the right partition under the kernel and not under the library's
defaults.
"""
from unittest.mock import patch

import pytest
from cerebrum.llm.apis import LLMQuery
from cerebrum.memory.apis import MemoryQuery

from aios.memory.context_injector import ContextInjector
from aios.memory.manager import MemoryManager
from aios.memory.pipeline import (
    IdentityResolver,
    IdentityRules,
    MemoryPipeline,
    PipelineSettings,
    note_from_request,
)
from aios.syscall.memory import MemorySyscall

USER = "jordan_mcallister_run1_t0__kernel_shared"
EMAIL = f"{USER}@users.example"
RULES = {"casefold": True, "email_domains": ["users.example"]}
MEMORY_CONFIG = {
    "provider": "in-memory",
    "relevance_threshold": 0.0,
    "max_injected_memories": 10,
    "max_memory_tokens": 2000,
    "write_barrier": {"enabled": True, "timeout_ms": 500},
    "auto_inject": True,
    "identity": RULES,
}


def kernel(memory_config=MEMORY_CONFIG):
    with patch("aios.memory.manager.global_config") as config:
        config.get_memory_config.return_value = memory_config
        config.get_storage_config.return_value = {}
        manager = MemoryManager()
    return manager, ContextInjector(manager, memory_config)


def add(manager, agent, user_id, content, memory_type, policy="shared",
        **extra):
    syscall = MemorySyscall(agent, MemoryQuery(
        operation_type="add_memory",
        params={"content": content, "metadata": {
            "owner_agent": agent, "user_id": user_id,
            "memory_type": memory_type, "sharing_policy": policy,
            **extra,
        }},
    ))
    manager.stamp_syscall(syscall)
    response = manager.address_request(syscall)
    assert response.success
    return syscall


def inject(injector, user_id, text="what should I do next?"):
    query = LLMQuery(
        messages=[{"role": "user", "content": text}], action_type="chat",
    )
    return injector.inject("assistant_agent", query, user_id=user_id)


# -- the rules ------------------------------------------------------------


@pytest.mark.parametrize("raw, canonical", [
    (EMAIL, USER),
    (USER.upper(), USER),
    (f"  {USER} ", USER),
    (f"{USER}@USERS.EXAMPLE", USER),
    (f"{USER}@other.example", f"{USER}@other.example"),
    ("", ""),
    (None, None),
])
def test_kernel_rules_canonicalize_the_v2_conventions(raw, canonical):
    assert IdentityRules.from_config(RULES).canonical(raw) == canonical


def test_default_rules_leave_ids_alone():
    resolver = IdentityResolver()
    for raw in (EMAIL, USER.upper(), USER):
        assert resolver.canonical(raw) == raw
    assert resolver.resolve("assistant_agent", EMAIL) == EMAIL


def test_rules_resolve_a_request_id_to_canonical():
    resolver = IdentityResolver(rules=IdentityRules.from_config(RULES))
    assert resolver.resolve("assistant_agent", EMAIL) == USER
    assert resolver.resolve("assistant_agent", "Assistant_Agent") is None


def test_identity_config_is_validated():
    with pytest.raises(ValueError, match="unknown keys"):
        IdentityRules.from_config({"case_fold": True})
    assert IdentityRules.from_config(None) == IdentityRules()
    assert IdentityRules.from_config(
        {"email_domains": "@Users.Example"}
    ).email_domains == ("users.example",)


# -- the kernel -----------------------------------------------------------


@pytest.mark.parametrize("alias", [EMAIL, USER.upper()])
def test_kernel_stores_a_v2_writer_under_the_canonical_id(alias):
    manager, injector = kernel()
    add(manager, "profile_agent", alias, "My name is Jordan.", "profile")
    _, diagnostics = inject(injector, USER)
    assert diagnostics["injected_count"] == 1
    assert diagnostics["injected_memories"][0]["user_id"] == USER
    assert manager.known_user_ids == {USER}


@pytest.mark.parametrize("alias", [EMAIL, USER.upper()])
def test_kernel_serves_a_v2_consumer_the_canonical_partition(alias):
    manager, injector = kernel()
    add(manager, "profile_agent", USER, "My name is Jordan.", "profile")
    add(manager, "task_agent", USER, "I'm working on Weather API.",
        "task_context")
    _, diagnostics = inject(injector, alias)
    assert diagnostics["resolved_user_id"] == USER
    assert diagnostics["injected_count"] == 2


def test_kernel_canonicalizes_at_acceptance_so_barrier_keys_agree():
    """A write accepted under the alias is pending under the canonical
    id, so a retrieval for the reference id waits for it."""
    manager, _ = kernel()
    syscall = MemorySyscall("profile_agent", MemoryQuery(
        operation_type="add_memory",
        params={"content": "x", "metadata": {
            "owner_agent": "profile_agent", "user_id": EMAIL,
            "memory_type": "profile", "sharing_policy": "shared",
        }},
    ))
    manager.stamp_syscall(syscall)
    assert syscall.query.params["metadata"]["user_id"] == USER
    assert syscall.barrier_seq > 0
    assert manager.barrier.stats()["pending_by_user"] == {USER: 1}
    manager.address_request(syscall)  # releases it
    assert manager.barrier.stats()["total_pending"] == 0


def test_kernel_search_with_an_alias_finds_the_canonical_rows():
    manager, _ = kernel()
    add(manager, "profile_agent", USER, "My name is Jordan.", "profile")
    syscall = MemorySyscall("profile_agent", MemoryQuery(
        operation_type="retrieve_memory",
        params={"content": "profile", "user_id": EMAIL, "k": 5},
    ))
    manager.stamp_syscall(syscall)
    response = manager.address_request(syscall)
    assert [r["content"] for r in response.search_results] == [
        "My name is Jordan."
    ]


def test_without_rules_the_kernel_keeps_ids_as_given():
    config = {k: v for k, v in MEMORY_CONFIG.items() if k != "identity"}
    manager, injector = kernel(config)
    add(manager, "profile_agent", EMAIL, "My name is Jordan.", "profile")
    assert inject(injector, USER)[1]["injected_count"] == 0


# -- the library's defaults (a replicated agent) --------------------------


def test_library_defaults_file_a_v2_write_under_the_alias():
    """A replicated agent's own resolver has no rules: the alias is
    another user, so the consumer's reference id misses the memory."""
    manager, _ = kernel()
    writer = MemoryPipeline(manager.provider, PipelineSettings())
    reader = MemoryPipeline(manager.provider, PipelineSettings())
    note = note_from_request({"content": "My name is Jordan.", "metadata": {
        "owner_agent": "profile_agent", "user_id": EMAIL,
        "memory_type": "profile", "sharing_policy": "shared",
    }})
    writer.write("profile_agent", EMAIL, note)
    assert note.metadata["user_id"] == EMAIL
    rows, _ = reader.retrieve("assistant_agent", USER, "name",
                              request_user_id=USER)
    assert rows == []
    rows, _ = reader.retrieve("assistant_agent", EMAIL, "name",
                              request_user_id=EMAIL)
    assert len(rows) == 1


# -- the judge-free diagnostics ---------------------------------------------


def test_diagnostics_carry_block_text_and_row_provenance():
    manager, injector = kernel()
    add(manager, "profile_agent", USER, "My name is Jordan.", "profile",
        provenance_agent="profile_agent", provenance_user=USER)
    add(manager, "task_agent", USER, "I'm working on Weather API.",
        "task_context")
    query, diagnostics = inject(injector, USER)
    block = query.messages[0]["content"]
    assert diagnostics["block_text"] == block
    rows = {r["memory_type"]: r for r in diagnostics["injected_memories"]}
    assert rows["profile"]["user_id"] == USER
    assert rows["profile"]["sharing_policy"] == "shared"
    assert rows["profile"]["provenance_agent"] == "profile_agent"
    assert rows["profile"]["provenance_user"] == USER
    assert rows["task_context"]["provenance_agent"] is None


def test_empty_injection_has_empty_block_text():
    _, injector = kernel()
    _, diagnostics = inject(injector, USER)
    assert diagnostics["injected_count"] == 0
    assert diagnostics["block_text"] == ""
