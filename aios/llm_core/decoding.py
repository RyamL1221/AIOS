"""
Per-request decoding settings (NeurIPS Subtask 9d).

The ``/query`` handler rebuilds every ``LLMQuery`` without its
``temperature``, so a caller's temperature never reached the model and
every call ran at the kernel default 1.0. Decoding therefore rides on
the request's ``llms`` entries, which the handler keeps: an entry may
carry ``temperature`` and ``seed`` next to ``name`` and ``backend``, and
the adapter applies them to the call for that model. The seed is passed
where the backend accepts one (LiteLLM forwards it to Ollama and to
Azure/OpenAI; Azure treats it as best effort).
"""
from typing import Any, Dict, List, Optional

DECODING_KEYS = ("temperature", "seed")

# Ollama's context window (known issue 29). Without ``num_ctx`` Ollama
# runs at its own default and drops the start of a longer prompt without
# an error, and the start is where the memory block is.
DEFAULT_CONTEXT_WINDOW = 16384
OLLAMA_PREFIXES = ("ollama/", "ollama_chat/")


def decoding_for(
    llms: Optional[List[Dict[str, Any]]], model_name: str
) -> Dict[str, Any]:
    """The ``temperature`` / ``seed`` the request's ``llms`` entry for
    ``model_name`` sets; ``{}`` when none does. A ``None`` value counts
    as unset."""
    for entry in llms or []:
        if isinstance(entry, dict) and entry.get("name") == model_name:
            return {
                key: entry[key] for key in DECODING_KEYS
                if entry.get(key) is not None
            }
    return {}


def ollama_num_ctx(
    model: Any, llms_config: Optional[Dict[str, Any]] = None
) -> Optional[int]:
    """The ``num_ctx`` for a LiteLLM Ollama model: ``llms.context_window``
    (default 16384). ``None`` for any other model, and when the setting
    is not a positive integer (Ollama's default then applies)."""
    if not isinstance(model, str) or not model.startswith(OLLAMA_PREFIXES):
        return None
    if llms_config is None:
        from aios.config.config_manager import config

        llms_config = config.get_llms_config() or {}
    value = llms_config.get("context_window", DEFAULT_CONTEXT_WINDOW)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value
