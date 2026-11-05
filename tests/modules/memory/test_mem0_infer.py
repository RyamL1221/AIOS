"""Kernel Mem0 with extraction (``memory.mem0.infer``, Subtask 9).

A real Mem0 store and Chroma in a temp directory, the pinned embedding
model on a local Ollama (skipped without one), and Mem0's LLM replaced
by a fake that returns fixed facts, so the test sees what Mem0 itself
stores for each extracted fact.
"""
import json

import pytest

from aios.memory.embedding import EmbeddingConfig
from aios.memory.note import MemoryNote
from aios.memory.providers.factory import provider_config
from aios.memory.providers.mem0 import Mem0Provider
from tests.modules.memory.test_provider_contract import needs_ollama

USER = "infer_user"
EMBEDDING = EmbeddingConfig.from_memory_config({})
BACKEND_LLM = {"provider": "azure_openai", "model": "gpt-4o",
               "temperature": 0.1}
REQUIRED = ("owner_agent", "user_id", "memory_type", "sharing_policy")


class FakeLLM:
    """Mem0's LLM: returns ``facts`` and records each prompt."""

    def __init__(self, facts):
        self.facts = facts
        self.prompts = []

    def generate_response(self, messages, response_format=None, **_):
        self.prompts.append(messages)
        return json.dumps({"memory": [{"text": f} for f in self.facts]})


def build(tmp_path, infer=True):
    memory_config = {
        "mem0": {
            "user_id": "default",
            "infer": infer,
            "vector_store": {"provider": "chroma", "config": {
                "collection_name": "infer",
                "path": str(tmp_path / "mem0"),
            }},
        },
        "backend_llm": BACKEND_LLM,
    }
    if not infer:  # Mem0 needs some LLM to construct; never called
        memory_config["mem0"]["llm"] = {"provider": "litellm", "config": {
            "model": "ollama/qwen2.5:7b",
        }}
    provider = Mem0Provider()
    provider.initialize(provider_config("mem0", memory_config))
    return provider


def with_llm(provider, facts, user=USER):
    llm = FakeLLM(facts)
    provider._get_client_for_user(user).llm = llm
    return llm


def note(content, memory_type="profile", owner="profile_agent",
         policy="shared", user=USER):
    memory = MemoryNote(content=content)
    memory.metadata = {
        "owner_agent": owner, "user_id": user, "memory_type": memory_type,
        "sharing_policy": policy, "created_at": "2026-11-04T00:00:00+00:00",
        "structured": json.dumps({"user_name": "Ana Li"}),
    }
    return memory


def test_provider_config_pins_the_backend_llm_with_infer():
    config = provider_config("mem0", {
        "mem0": {"infer": True}, "backend_llm": BACKEND_LLM,
    })
    assert config["llm"] == {"provider": "litellm", "config": {
        "model": "azure/gpt-4o", "temperature": 0.1,
    }}
    assert "llm" not in provider_config("mem0", {"mem0": {}})


@needs_ollama
def test_every_extracted_fact_carries_the_full_metadata(tmp_path):
    provider = build(tmp_path)
    assert provider.backend_extraction
    facts = ["Name is Ana Li", "Prefers vim and git", "Prefers Go",
             "Likes terse responses"]
    with_llm(provider, facts)
    first = provider.add(note(
        "My name is Ana Li. I prefer to use vim; git. My preferred "
        "programming language is Go. I like terse responses."
    ))
    rows = provider.list(USER, 100)
    assert sorted(r.content for r in rows) == sorted(facts)
    assert first in {r.memory_id for r in rows}
    for row in rows:
        for key in REQUIRED:
            assert row.metadata.get(key), (row.content, key)
        assert row.metadata["user_id"] == USER
        assert row.metadata["owner_agent"] == "profile_agent"
        assert row.metadata["memory_type"] == "profile"
        assert row.metadata["sharing_policy"] == "shared"
        assert json.loads(row.metadata["structured"]) == {
            "user_name": "Ana Li"
        }
    # Search returns the same metadata on every fact.
    for hit in provider.search("which editor", USER, 10):
        assert all(hit.metadata.get(key) for key in REQUIRED)
    provider.close()


@needs_ollama
def test_conversation_turn_goes_to_mem0_as_two_messages(tmp_path):
    provider = build(tmp_path)
    llm = with_llm(provider, ["Asked what to do next"])
    provider.add(note(
        "User: What should I do next?\nAssistant: Fix the flaky test.",
        memory_type="conversation", owner="assistant_agent",
        policy="private",
    ))
    prompt = llm.prompts[-1][-1]["content"]
    assert "user: What should I do next?" in prompt
    assert "assistant: Fix the flaky test." in prompt
    provider.close()


@needs_ollama
def test_nothing_extracted_returns_no_id_without_error(tmp_path):
    provider = build(tmp_path)
    with_llm(provider, [])
    assert provider.add(note("Hello.")) == ""
    assert provider.list(USER, 10) == []
    provider.close()


@needs_ollama
def test_the_assistant_model_does_not_replace_the_pinned_llm(tmp_path):
    provider = build(tmp_path)
    llm = with_llm(provider, ["x"])
    provider.sync_llm_from_query([{"name": "qwen2.5:7b",
                                   "backend": "ollama"}])
    assert provider._get_client_for_user(USER).llm is llm
    assert provider.client.llm.config.model == "azure/gpt-4o"
    provider.close()


@needs_ollama
def test_without_infer_content_is_stored_verbatim(tmp_path):
    provider = build(tmp_path, infer=False)
    assert not provider.backend_extraction
    llm = with_llm(provider, ["should not be used"])
    provider.add(note("My name is Ana Li."))
    assert [r.content for r in provider.list(USER, 10)] == [
        "My name is Ana Li."
    ]
    assert llm.prompts == []
    provider.close()
