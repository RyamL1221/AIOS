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


# -- Key values in logs (Subtask 17, Decision 3) ----------------------------
#
# A Subtask 16 mutation replay's test log held the Azure key: a LiteLLM
# traceback's locals. The values below are replaced wherever a log
# record or a test report could carry them.

# A secret shorter than this is not redacted: replacing a short common
# string everywhere would garble the logs, and no key is that short.
MIN_SECRET_LENGTH = 8


def _walk_secrets(value: Any, out: set) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if is_secret_key(key):
                _collect(item, out)
            else:
                _walk_secrets(item, out)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _walk_secrets(item, out)


def _collect(value: Any, out: set) -> None:
    if isinstance(value, str):
        out.add(value)
    elif isinstance(value, dict):
        for item in value.values():
            _collect(item, out)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect(item, out)


def secret_values(*configs: Any, environ: Any = None) -> tuple:
    """Every secret value: of each environment variable whose name names
    a secret (``AZURE_API_KEY``, ``NEO4J_PASSWORD``; ``is_secret_key``
    on the lower-cased name), and of every secret-named key in each of
    ``configs`` (mappings, walked as ``redact_secrets`` walks them), at
    least ``MIN_SECRET_LENGTH`` characters, longest first."""
    import os

    found: set = set()
    for name, value in (os.environ if environ is None else environ).items():
        if is_secret_key(str(name).lower()):
            found.add(value)
    for config in configs:
        _walk_secrets(config, found)
    return tuple(sorted((v for v in found
                         if isinstance(v, str)
                         and len(v) >= MIN_SECRET_LENGTH),
                        key=len, reverse=True))


def redact_text(text: str, values) -> str:
    """``text`` with every one of ``values`` replaced by ``REDACTED``."""
    for value in values:
        if value in text:
            text = text.replace(value, REDACTED)
    return text


_REDACTION = {"values": ()}


def _redact_record(record, values) -> None:
    import logging

    try:
        message = record.getMessage()
    except Exception:  # a record whose args do not fit its message
        message = str(record.msg)
    clean = redact_text(message, values)
    if clean != message:
        record.msg, record.args = clean, None
    if record.exc_info:
        text = logging.Formatter().formatException(record.exc_info)
        clean = redact_text(text, values)
        if clean != text:
            record.exc_text, record.exc_info = clean, None
    if record.stack_info:
        record.stack_info = redact_text(record.stack_info, values)


def install_log_redaction(values) -> None:
    """From now on every log record's message (its arguments applied)
    and traceback carry none of ``values``: each is replaced by
    ``REDACTED`` when the record is made, through the log-record
    factory, so every logger and handler, those made later included,
    sees the redacted record. A second call replaces the values."""
    import logging

    _REDACTION["values"] = tuple(sorted(
        {v for v in values if v}, key=len, reverse=True))
    base = logging.getLogRecordFactory()
    if getattr(base, "redacts_secrets", False):
        return

    def factory(*args, **kwargs):
        record = base(*args, **kwargs)
        if _REDACTION["values"]:
            _redact_record(record, _REDACTION["values"])
        return record

    factory.redacts_secrets = True
    logging.setLogRecordFactory(factory)


def redact_report(report, values) -> None:
    """A pytest report with none of ``values`` in its failure text
    (``longrepr``, with the locals ``--showlocals`` prints) or its
    captured output and logs (``sections``): what the terminal and a
    JUnit XML file print."""
    if not values:
        return
    longrepr = getattr(report, "longrepr", None)
    if longrepr is not None and not isinstance(longrepr, tuple):
        text = str(longrepr)
        clean = redact_text(text, values)
        if clean != text:
            report.longrepr = clean
    report.sections = [(title, redact_text(content, values))
                       for title, content in report.sections]
