# Secrets kept out of printed configuration.
"""Secrets kept out of printed configuration.

The kernel prints its memory configuration at startup, and its logs are
archived with every run, so a key in that configuration (such as
``memory.zep.api_key``) would be copied into each log. ``redact_secrets``
returns a copy that is safe to print.
"""
import re
from functools import lru_cache
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
    a list or mapping under such a key included, and every set string
    directly under a section of provider keys (``api_keys``). Mappings,
    lists and tuples are walked; the input is not changed."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if is_secret_key(key) and item not in (None, "", [], (), {}):
                out[key] = REDACTED
            elif is_key_section(key) and isinstance(item, dict):
                out[key] = {
                    name: (REDACTED if isinstance(entry, str) and entry
                           else redact_secrets(entry))
                    for name, entry in item.items()}
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


# config.yaml's section of provider keys (``api_keys.openai`` and so on,
# configuration.md): a string directly under it is a key, whatever its
# name; a mapping under it (``huggingface``) is walked as any other, so
# its ``auth_token`` is a secret and its ``cache_dir`` is not.
KEY_SECTIONS = ("api_keys",)


def is_key_section(key: Any) -> bool:
    """Whether a mapping key names a section of provider keys."""
    return isinstance(key, str) and key.lower() in KEY_SECTIONS


def _walk_secrets(value: Any, out: set) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if is_secret_key(key):
                _collect(item, out)
            elif is_key_section(key) and isinstance(item, dict):
                for entry in item.values():
                    if isinstance(entry, str):
                        out.add(entry)
                    else:
                        _walk_secrets(entry, out)
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


# A fragment of a secret is key material too. LiteLLM's Azure client
# logs a key's first 8 characters at DEBUG (litellm 1.83.0,
# ``llms/azure/common_utils.py:617-623``), its masker prints a value's
# first and last 4 beside asterisks
# (``litellm_core_utils/sensitive_data_masker.py``), and a report that
# shortens a long string (pytest cuts a local's repr at 240 characters)
# can cut through a key. So for a secret of FRAGMENT_SECRET_LENGTH
# characters or more, any FRAGMENT_LENGTH consecutive characters of it
# are redacted, with the run of the secret they belong to, and so is a
# head or tail of MASKED_END_LENGTH or more beside a mask ("**", "...").
# A shorter secret is matched whole only (its fragments could be common
# words), and so is a fragment under FRAGMENT_LENGTH away from a mask.
FRAGMENT_LENGTH = 8
MASKED_END_LENGTH = 4
FRAGMENT_SECRET_LENGTH = 20
_MASK = r"(?:[*\u2022]{2,}|\.{3,}|\u2026)"


@lru_cache(maxsize=64)
def _fragment_patterns(value: str) -> tuple:
    """``value``'s runs of FRAGMENT_LENGTH characters with their
    offsets, and the patterns of its masked heads and tails."""
    grams = tuple((value[k:k + FRAGMENT_LENGTH], k)
                  for k in range(len(value) - FRAGMENT_LENGTH + 1))
    lengths = range(FRAGMENT_LENGTH - 1, MASKED_END_LENGTH - 1, -1)
    heads = re.compile("(" + "|".join(
        re.escape(value[:n]) for n in lengths) + ")(?=" + _MASK + ")")
    tails = re.compile(_MASK + "(" + "|".join(
        re.escape(value[-n:]) for n in lengths) + ")")
    return grams, heads, tails


def _fragment_spans(text: str, value: str) -> list:
    """The spans of ``text`` that hold a fragment of ``value``, sorted
    and merged."""
    grams, heads, tails = _fragment_patterns(value)
    spans = set()
    for gram, offset in grams:
        at = text.find(gram)
        while at >= 0:
            start, i = at, offset
            while start > 0 and i > 0 and text[start - 1] == value[i - 1]:
                start, i = start - 1, i - 1
            end, j = at + len(gram), offset + len(gram)
            while (end < len(text) and j < len(value)
                   and text[end] == value[j]):
                end, j = end + 1, j + 1
            spans.add((start, end))
            at = text.find(gram, at + 1)
    # Every masked head starts with the secret's first characters and
    # every masked tail ends with its last: skip the patterns without.
    if value[:MASKED_END_LENGTH] in text:
        spans.update(match.span(1) for match in heads.finditer(text))
    if value[-MASKED_END_LENGTH:] in text:
        spans.update(match.span(1) for match in tails.finditer(text))
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def _fragmented(value) -> bool:
    return isinstance(value, str) and len(value) >= FRAGMENT_SECRET_LENGTH


def redact_text(text: str, values) -> str:
    """``text`` with every one of ``values`` replaced by ``REDACTED``,
    and with it every fragment of one that is long enough to be matched
    by fragment (above)."""
    for value in values:
        if value in text:
            text = text.replace(value, REDACTED)
    for value in values:
        if not _fragmented(value):
            continue
        spans = _fragment_spans(text, value)
        if spans:
            parts, last = [], 0
            for start, end in spans:
                parts += [text[last:start], REDACTED]
                last = end
            text = "".join(parts) + text[last:]
    return text


def holds_secret(text: str, values) -> bool:
    """Whether ``redact_text`` would change ``text``: it holds one of
    ``values`` or a fragment of one."""
    return any(value in text
               or (_fragmented(value) and _fragment_spans(text, value))
               for value in values if value)


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


class _RedactingStream:
    """A text stream that writes with every redacted value replaced. A
    partial line waits for its newline (or a flush), so a value split
    across two writes is still caught. A re-entrant lock keeps the
    threads' writes whole and lets a write made from inside a write (a
    signal handler's, a finalizer's) go through; at interpreter exit,
    when a frozen daemon thread may hold it, the lock is waited for
    briefly and then skipped, so the final flush cannot hang."""

    def __init__(self, stream):
        import threading

        self._stream = stream
        self._pending = ""
        self._lock = threading.RLock()

    def _locked(self):
        import contextlib
        import sys

        if not sys.is_finalizing():
            return self._lock
        held = self._lock.acquire(timeout=0.5)

        @contextlib.contextmanager
        def finalizing():
            try:
                yield
            finally:
                if held:
                    self._lock.release()

        return finalizing()

    def write(self, text) -> int:
        text = str(text)
        with self._locked():
            values = _REDACTION["values"]
            if not values:
                self._drain()
                self._stream.write(text)
                return len(text)
            self._pending += text
            if "\n" in self._pending:
                complete, self._pending = self._pending.rsplit("\n", 1)
                self._stream.write(redact_text(complete + "\n", values))
            if len(self._pending) > 65536:
                self._drain()
        return len(text)

    def writelines(self, lines) -> None:
        for line in lines:
            self.write(line)

    def _drain(self) -> None:
        if self._pending:
            pending, self._pending = self._pending, ""
            self._stream.write(redact_text(pending, _REDACTION["values"]))

    def flush(self) -> None:
        with self._locked():
            self._drain()
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def install_stream_redaction() -> None:
    """``sys.stdout`` and ``sys.stderr`` write with the redacted values
    replaced (those ``install_log_redaction`` set): ``print``, uncaught
    tracebacks (the main thread's and other threads'), and any library
    that writes to them. A write to their ``buffer`` (bytes) is not
    redacted. Idempotent."""
    import sys

    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is not None and not isinstance(stream, _RedactingStream):
            setattr(sys, name, _RedactingStream(stream))


def install_redaction(values) -> None:
    """Every text sink of the process: log records and their tracebacks
    (``install_log_redaction``) and the standard streams
    (``install_stream_redaction``)."""
    install_log_redaction(values)
    install_stream_redaction()


def file_secret_configs(root) -> tuple:
    """The kernel checkout's ``.env`` (its names lower-cased) and
    ``aios/config/config.yaml``, each when it exists, as mappings for
    ``secret_values``. ``root`` is the AIOS checkout."""
    from pathlib import Path

    root = Path(root)
    configs = []
    env_file = root / ".env"
    if env_file.is_file():
        from dotenv import dotenv_values

        configs.append({str(name).lower(): value for name, value
                        in dotenv_values(env_file).items()})
    config_file = root / "aios" / "config" / "config.yaml"
    if config_file.is_file():
        import yaml

        try:
            configs.append(yaml.safe_load(config_file.read_text()) or {})
        except yaml.YAMLError:
            pass
    return tuple(configs)


def redact_report(report, values) -> None:
    """A pytest report (of a test or of a collection) with none of
    ``values`` in its failure text (``longrepr``, with the arguments and
    locals a long traceback prints) or its captured output and logs
    (``sections``): what the terminal and a JUnit XML file print."""
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
