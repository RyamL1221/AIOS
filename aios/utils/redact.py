# Secrets kept out of printed configuration.
"""Secrets kept out of printed configuration.

The kernel prints its memory configuration at startup, and its logs are
archived with every run, so a key in that configuration (such as
``memory.zep.api_key``) would be copied into each log. ``redact_secrets``
returns a copy that is safe to print.
"""
import re
from typing import Any

REDACTED = "<redacted>"

# A configuration key that names a secret: api_key, apikey, any
# ``*_api_key``, token, ``*_token``, secret, ``*_secret``, secret_key,
# access_key, private_key, password. A count such as max_memory_tokens
# or prompt_tokens is not one.
_SECRET_KEY = re.compile(
    r"(^|_)(api_?key|token|secret|secret_key|access_key|private_key"
    r"|password)$",
    re.IGNORECASE,
)


def is_secret_key(key: Any) -> bool:
    """Whether a mapping key names a secret."""
    return isinstance(key, str) and bool(_SECRET_KEY.search(key))


def redact_secrets(value: Any) -> Any:
    """A copy of ``value`` with the value of every key that names a
    secret replaced by ``REDACTED`` when it is set (not None or empty),
    a list or mapping under such a key included. Mappings, lists and
    tuples are walked; the input is not changed."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if is_secret_key(key) and item not in (None, "", [], (), {}):
                out[key] = REDACTED
            else:
                out[key] = redact_secrets(item)
        return out
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    return value
