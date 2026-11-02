"""The kernel reports what the native conditions need from it: whether
it injects and extracts, and the pinned internal backend LLM."""
from unittest.mock import patch

from aios.memory.manager import MemoryManager

MEMORY = {
    "provider": "in-memory",
    "auto_inject": False,
    "auto_extract": False,
    "backend_llm": {"provider": "azure_openai", "model": "gpt-4o"},
}


def build(memory):
    with patch("aios.memory.manager.global_config") as config:
        config.get_memory_config.return_value = memory
        config.get_storage_config.return_value = {}
        return MemoryManager()


def test_manager_reports_injection_mode_and_backend_llm():
    manager = build(MEMORY)
    assert manager.auto_inject is False
    assert manager.auto_extract is False
    assert manager.backend_llm == MEMORY["backend_llm"]


def test_defaults_are_off_and_empty():
    manager = build({"provider": "in-memory"})
    assert (manager.auto_inject, manager.auto_extract) == (False, False)
    assert manager.backend_llm == {}

