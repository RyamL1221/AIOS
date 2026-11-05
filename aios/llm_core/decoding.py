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
