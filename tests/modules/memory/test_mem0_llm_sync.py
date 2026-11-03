"""Mem0Provider.sync_llm_from_query: Mem0's LLM is its litellm provider
with the kernel's own ``<backend>/<model>`` name, so its calls reach
LiteLLM's callbacks (Subtask 7), and it reaches the per-user clients."""

import logging
from types import SimpleNamespace

import pytest

from aios.memory.providers.mem0 import Mem0Provider

AZURE = [{"name": "gpt-4o", "backend": "azure"}]


@pytest.fixture
def provider():
    provider = Mem0Provider()
    provider.client = SimpleNamespace(llm=None)
    provider._user_clients = {"u1": SimpleNamespace(llm=None)}
    return provider


def test_azure_sync_routes_through_litellm(provider, caplog):
    from mem0.llms.litellm import LiteLLM

    with caplog.at_level(logging.INFO):
        provider.sync_llm_from_query(AZURE)
    assert "Failed to sync" not in caplog.text
    assert "Mem0 LLM synced to litellm/azure/gpt-4o" in caplog.text
    llm = provider.client.llm
    assert isinstance(llm, LiteLLM)
    assert llm.config.model == "azure/gpt-4o"


def test_sync_reaches_existing_per_user_clients(provider):
    provider.sync_llm_from_query(AZURE)
    assert provider.client.llm is not None
    assert provider._user_clients["u1"].llm is provider.client.llm


def test_sync_is_idempotent(provider):
    provider.sync_llm_from_query(AZURE)
    first = provider.client.llm
    provider.sync_llm_from_query(AZURE)
    assert provider.client.llm is first


def test_backend_without_litellm_route_is_skipped(provider):
    provider.sync_llm_from_query([{"name": "m", "backend": "huggingface"}])
    assert provider.client.llm is None
