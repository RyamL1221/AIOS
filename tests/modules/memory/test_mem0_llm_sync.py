"""Mem0Provider.sync_llm_from_query on Azure: the Mem0 LLM is built from
the kernel's AZURE_* variables and reaches the per-user clients."""

import logging
from types import SimpleNamespace

import pytest

from aios.memory.providers.mem0 import Mem0Provider

AZURE = [{"name": "gpt-4o", "backend": "azure"}]


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("AZURE_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_API_BASE", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_API_VERSION", "2024-06-01")
    for name in ("LLM_AZURE_OPENAI_API_KEY", "LLM_AZURE_ENDPOINT",
                 "LLM_AZURE_API_VERSION", "LLM_AZURE_DEPLOYMENT",
                 "OPENAI_API_VERSION"):
        monkeypatch.delenv(name, raising=False)
    provider = Mem0Provider()
    provider.client = SimpleNamespace(llm=None)
    provider._user_clients = {"u1": SimpleNamespace(llm=None)}
    return provider


def test_azure_sync_succeeds(provider, caplog):
    with caplog.at_level(logging.INFO):
        provider.sync_llm_from_query(AZURE)
    assert "Failed to sync" not in caplog.text
    assert "Mem0 LLM synced to azure_openai/gpt-4o" in caplog.text
    llm = provider.client.llm
    assert llm.config.model == "gpt-4o"
    kwargs = llm.config.azure_kwargs
    assert kwargs.api_version == "2024-06-01"
    assert kwargs.azure_endpoint == "https://example.openai.azure.com"
    assert kwargs.azure_deployment == "gpt-4o"


def test_sync_reaches_existing_per_user_clients(provider):
    provider.sync_llm_from_query(AZURE)
    assert provider.client.llm is not None
    assert provider._user_clients["u1"].llm is provider.client.llm


def test_sync_is_idempotent(provider):
    provider.sync_llm_from_query(AZURE)
    first = provider.client.llm
    provider.sync_llm_from_query(AZURE)
    assert provider.client.llm is first


def test_azure_kwargs_skip_unset_variables(monkeypatch):
    for name in ("AZURE_API_KEY", "AZURE_API_BASE", "AZURE_API_VERSION"):
        monkeypatch.delenv(name, raising=False)
    assert Mem0Provider._azure_kwargs("gpt-4o") == {
        "azure_deployment": "gpt-4o",
    }
