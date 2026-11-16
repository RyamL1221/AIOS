"""The kernel prints no secret at startup.

``initialize_components`` prints the memory configuration, and the
kernel's log is archived with every run (``repo-artifacts``). Before,
that print included ``memory.zep.api_key`` in full. Importing
runtime.launch would start the whole kernel (it initializes every
component on import), so ``initialize_components`` is compiled from the
module's source and run with each component stubbed, as
tests/modules/syscall/test_v2_requests.py does for the /query handler.
"""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace

from aios.utils.redact import REDACTED, is_secret_key, redact_secrets

LAUNCH = Path(__file__).resolve().parents[2] / "runtime" / "launch.py"
SECRET = "zep-test-key-0123456789abcdef"


def test_secret_values_are_redacted_and_nothing_else():
    config = {
        "provider": "mem0",
        "max_memory_tokens": 500,
        "zep": {"api_key": SECRET, "base_url": "http://localhost:8000"},
        "mem0": {"llm": {"config": {"api_key": "", "model": "gpt-4o"}}},
        "backends": [{"auth_token": SECRET, "name": "hf"}],
        "pair": ("x", {"client_secret": SECRET}),
        "rotation": {"api_key": [SECRET], "token": {"value": SECRET}},
        "password": None,
        "access_key": [],
    }
    before = copy.deepcopy(config)
    redacted = redact_secrets(config)
    assert config == before  # the input is not changed
    assert SECRET not in repr(redacted)
    assert redacted["zep"] == {"api_key": REDACTED,
                               "base_url": "http://localhost:8000"}
    assert redacted["backends"] == [{"auth_token": REDACTED, "name": "hf"}]
    assert redacted["pair"] == ("x", {"client_secret": REDACTED})
    # A list or mapping under a secret-named key is a secret too.
    assert redacted["rotation"] == {"api_key": REDACTED, "token": REDACTED}
    # Unset secrets and counts stay as they are.
    assert redacted["mem0"]["llm"]["config"]["api_key"] == ""
    assert redacted["password"] is None
    assert redacted["access_key"] == []
    assert redacted["max_memory_tokens"] == 500


def test_which_keys_name_a_secret():
    for key in ("api_key", "apikey", "openai_api_key", "API_KEY", "token",
                "auth_token", "secret", "client_secret", "secret_key",
                "access_key", "private_key", "password"):
        assert is_secret_key(key), key
    for key in ("max_memory_tokens", "prompt_tokens", "api_base",
                "base_url", "key", "keyword", "tokenizer", None, 3):
        assert not is_secret_key(key), key


def initialize_components(memory_config):
    """runtime/launch.py's ``initialize_components``, compiled from its
    source and run with every component stubbed."""
    tree = ast.parse(LAUNCH.read_text())
    (node,) = [n for n in tree.body
               if getattr(n, "name", None) == "initialize_components"]
    sections = {"llms": {}, "storage": {}, "memory": memory_config,
                "scheduler": {}, "agent_factory": {}}
    namespace = {
        "__name__": "launch_under_test",
        "backend_usage": SimpleNamespace(
            install_litellm_logger=lambda: None),
        "config": SimpleNamespace(**{
            f"get_{name}_config": (lambda value=value: value)
            for name, value in sections.items()}),
        "initialize_llm_cores": lambda c: object(),
        "initialize_storage_manager": lambda c: object(),
        "initialize_memory_manager": lambda c, s: object(),
        "initialize_tool_manager": lambda: object(),
        "initialize_scheduler": lambda components, c: object(),
        "initialize_agent_factory": lambda c: object(),
        "PERSONALIZATION_PROVIDERS": (),
        "redact_secrets": redact_secrets,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(LAUNCH),
                 "exec"), namespace)
    return namespace["initialize_components"]()


def test_initialize_components_prints_the_memory_config_without_its_key(
        capsys):
    memory_config = {"provider": "zep",
                     "zep": {"api_key": SECRET,
                             "base_url": "http://localhost:8000"}}
    initialize_components(memory_config)
    out = capsys.readouterr().out
    assert SECRET not in out
    # The configuration is still printed, with the key marked.
    assert REDACTED in out and "http://localhost:8000" in out
    assert memory_config["zep"]["api_key"] == SECRET  # left as it was


def test_launch_imports_the_redaction_it_calls():
    """The compiled function above is given ``redact_secrets``; the
    module must import it, or the kernel fails at startup."""
    tree = ast.parse(LAUNCH.read_text())
    imported = {
        (n.module, alias.name) for n in tree.body
        if isinstance(n, ast.ImportFrom) for alias in n.names}
    assert ("aios.utils.redact", "redact_secrets") in imported


def test_the_config_update_request_is_logged_without_its_key(caplog):
    """``/core/config/update`` logs its request body, whose ``api_key``
    is the provider key being set. The handler is compiled from
    launch.py's source and run with the configuration stubbed."""
    import asyncio
    import logging

    from fastapi import HTTPException, Request

    tree = ast.parse(LAUNCH.read_text())
    (node,) = [n for n in tree.body
               if getattr(n, "name", None) == "update_config"]
    node.decorator_list = []  # @app.post("/core/config/update")
    saved = []

    async def refresh_configuration():
        return None

    namespace = {
        "__name__": "launch_under_test",
        "Request": Request, "HTTPException": HTTPException,
        "logger": logging.getLogger("launch_under_test"),
        "config": SimpleNamespace(config={"api_keys": {"openai": ""}},
                                  save_config=lambda: saved.append(1),
                                  refresh=lambda: None),
        "refresh_configuration": refresh_configuration,
        "redact_secrets": redact_secrets,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(LAUNCH),
                 "exec"), namespace)

    class Body:
        async def json(self):
            return {"provider": "openai", "api_key": SECRET}

    with caplog.at_level(logging.INFO, logger="launch_under_test"):
        reply = asyncio.run(namespace["update_config"](Body()))
    assert reply["status"] == "success" and saved == [1]
    assert "Received config update request" in caplog.text
    assert SECRET not in caplog.text and REDACTED in caplog.text
    # The key itself is stored, as before.
    assert namespace["config"].config["api_keys"]["openai"] == SECRET


def test_an_incomplete_llm_config_is_logged_without_its_key(caplog):
    """LLMAdapter skips an ``llms.models`` entry without a name or a
    backend and logs it; an entry may hold its own ``api_key``."""
    import logging

    from aios.llm_core.adapter import LLMAdapter

    adapter = LLMAdapter.__new__(LLMAdapter)
    adapter.llm_configs = [{"name": "", "backend": "openai",
                            "api_key": SECRET}]
    adapter.llms = []
    with caplog.at_level(logging.WARNING, logger="aios.llm_core.adapter"):
        adapter._initialize_llms()
    assert "Skipping incomplete LLM config" in caplog.text
    assert SECRET not in caplog.text and REDACTED in caplog.text
    assert adapter.llms == [] and adapter.llm_configs == []


# -- Key values in logs and test reports (Subtask 17, Decision 3) -----------

import html
import io
import logging
import os
import subprocess
import sys

import pytest

from aios.utils import redact

KEY = "azure-test-key-0123456789abcdef"
ROOT = Path(__file__).resolve().parents[2]


def test_secret_values_are_the_environments_and_the_configs():
    environ = {"AZURE_API_KEY": KEY, "AZURE_API_BASE": "https://base.test",
               "NEO4J_PASSWORD": "neo4j-password-123", "HF_TOKEN": "short"}
    config = {"memory": {"mem0": {"api_key": "mem0-key-0123456789",
                                  "model": "gpt-4o"}},
              "max_memory_tokens": 300}
    values = redact.secret_values(config, environ=environ)
    assert set(values) == {KEY, "neo4j-password-123", "mem0-key-0123456789"}
    assert [len(v) for v in values] == sorted(map(len, values),
                                              reverse=True)


@pytest.fixture
def redacting():
    factory = logging.getLogRecordFactory()
    yield redact.install_log_redaction
    logging.setLogRecordFactory(factory)
    redact._REDACTION["values"] = ()


def test_log_records_carry_no_key_in_message_or_traceback(redacting):
    """Every record's message, its arguments applied, and its traceback
    lose the key, on a logger made after the install too."""
    redacting([KEY])
    out = io.StringIO()
    handler = logging.StreamHandler(out)
    logger = logging.getLogger("test.redaction.made_later")
    logger.addHandler(handler)
    logger.propagate = False
    try:
        logger.warning("calling with api_key=%s", KEY)
        try:
            raise RuntimeError(f"auth failed for {KEY}")
        except RuntimeError:
            logger.exception("the call failed")
    finally:
        logger.removeHandler(handler)
    text = out.getvalue()
    assert KEY not in text
    assert text.count(redact.REDACTED) == 2
    assert "Traceback" in text and "RuntimeError" in text


LONG = "azure-test-key-0123456789abcdefGHIJKLMNOP"
FRAGMENT_CASES = {
    # LiteLLM's Azure debug line: the first 8 characters, then asterisks
    "head": (f"Api Key:{LONG[:8]}***************",
             f"Api Key:{redact.REDACTED}***************"),
    # a long string cut through the key, at either end
    "cut_head": (f"-H 'api-key: {LONG[:19]}...yyy",
                 f"-H 'api-key: {redact.REDACTED}...yyy"),
    "cut_tail": (f"xxx...{LONG[-13:]}' more",
                 f"xxx...{redact.REDACTED}' more"),
    "interior": (f"blob {LONG[10:21]} end", f"blob {redact.REDACTED} end"),
    # LiteLLM's masker: the first and last 4 beside asterisks
    "masked_ends": (f"api-key: {LONG[:4]}****{LONG[-4:]}",
                    f"api-key: {redact.REDACTED}****{redact.REDACTED}"),
    # Under 8 characters and beside no mask: not matched.
    "seven": (f"value {LONG[:7]} here", f"value {LONG[:7]} here"),
    "four": (f"the {LONG[:4]} and {LONG[-4:]} words",
             f"the {LONG[:4]} and {LONG[-4:]} words"),
    # Under 4 characters beside a mask: not matched.
    "three_masked": (f"api-key: {LONG[:3]}****{LONG[-3:]}",
                     f"api-key: {LONG[:3]}****{LONG[-3:]}"),
    # A short secret is matched whole only.
    "short_fragment": ("we use shortsec here", "we use shortsec here"),
    "short_whole": ("token=shortsecret1", f"token={redact.REDACTED}"),
}


@pytest.mark.parametrize("name", sorted(FRAGMENT_CASES))
def test_a_fragment_of_a_long_secret_is_redacted(name):
    """Eight consecutive characters of a secret of 20 or more, or a head
    or tail of 4 or more beside a mask, are redacted with the run they
    belong to; ``holds_secret`` (the archive scan's rule) agrees."""
    text, expected = FRAGMENT_CASES[name]
    values = (LONG, "shortsecret1")
    assert redact.redact_text(text, values) == expected
    assert redact.holds_secret(text, values) == (text != expected)


def test_the_kernel_installs_the_redaction():
    """runtime.launch installs it at import, after .env is loaded and
    before the app is made (the module cannot be imported here: it
    starts the kernel)."""
    tree = ast.parse(LAUNCH.read_text())
    calls = [i for i, node in enumerate(tree.body)
             if isinstance(node, ast.Expr)
             and isinstance(node.value, ast.Call)
             and getattr(node.value.func, "id", "") in (
                 "install_redaction", "load_dotenv")]
    names = [tree.body[i].value.func.id for i in calls]
    assert names == ["load_dotenv", "install_redaction"]
    install = tree.body[calls[1]].value
    assert ast.unparse(install.args[0]) == "secret_values(config.config)"


# A process's every text sink, each with a raised exception that carries
# the key: a print, a log record, a logged traceback, another thread's
# uncaught exception, LiteLLM's own traceback printed with its frames'
# locals (as a rich or a diagnose-mode handler prints it), and the main
# thread's uncaught exception; and LiteLLM's own debug log, on, whose
# Azure client logs the key's first 8 characters. Its stdout and stderr
# go to one file, as the drivers write a kernel's or the harness's log.
PROCESS = '''
import logging, os, sys, threading, traceback
from {module} import install_redaction, secret_values

if sys.argv[1] == "redact":
    install_redaction(secret_values())
KEY = os.environ["FAKE_SERVICE_API_KEY"]
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("sink")
print("sink-print", KEY)
log.warning("sink-log %s", KEY)
try:
    raise RuntimeError("sink-exception " + KEY)
except RuntimeError:
    log.exception("sink-logged-traceback")


def fail():
    raise RuntimeError("sink-thread " + KEY)


thread = threading.Thread(target=fail)
thread.start()
thread.join()


def call(api_key):
    import litellm

    litellm._turn_on_debug()
    return litellm.completion(
        model="azure/gpt-4o", api_key=api_key,
        api_base="http://127.0.0.1:9", api_version="2024-08-01-preview",
        num_retries=0, messages=[{{"role": "user", "content": "hi"}}])


try:
    call(KEY)
except Exception as error:
    print("sink-litellm", file=sys.stderr)
    sys.stderr.write("".join(traceback.TracebackException.from_exception(
        error, capture_locals=True).format()))
raise RuntimeError("sink-uncaught " + KEY)
'''
MARKERS = ("sink-print", "sink-log", "sink-exception",
           "sink-logged-traceback", "sink-thread", "sink-litellm",
           "sink-uncaught", "Initializing Azure OpenAI Client")


def fragments(text, key=None):
    """How many of the key's runs of 8 characters ``text`` holds: the
    whole key, or any part of it a mask or a cut left."""
    key = key or KEY
    return sum(key[i:i + 8] in text for i in range(len(key) - 7))


def run_process(tmp_path, module, mode):
    log = tmp_path / f"process_{mode}.log"
    env = {**os.environ, "FAKE_SERVICE_API_KEY": KEY,
           "LITELLM_LOCAL_MODEL_COST_MAP": "True",
           "PYTHONPATH": str(ROOT)}
    with open(log, "w") as out:
        code = subprocess.run(
            [sys.executable, "-c", PROCESS.format(module=module), mode],
            cwd=tmp_path, env=env, stdout=out, stderr=subprocess.STDOUT,
            timeout=120).returncode
    return code, log.read_text()


def test_a_process_log_carries_no_key_in_any_sink(tmp_path):
    """The kernel's log (its stdout and stderr): without the redaction
    every sink above prints the key; with it, none does."""
    code, text = run_process(tmp_path, "aios.utils.redact", "plain")
    assert code == 1 and all(m in text for m in MARKERS)
    assert text.count(KEY) >= len(MARKERS) - 1
    # LiteLLM's own line: the head of the key, then asterisks.
    assert f"Api Key:{KEY[:8]}***************" in text
    code, text = run_process(tmp_path, "aios.utils.redact", "redact")
    assert code == 1 and all(m in text for m in MARKERS), text[-2000:]
    assert not fragments(text)
    assert f"Api Key:{redact.REDACTED}***************" in text
    assert text.count(redact.REDACTED) >= len(MARKERS)


# Test sources whose report would print the key: a failing test's locals
# and captured output, an unmocked LiteLLM call (a long traceback prints
# each frame's arguments: the Subtask 16 replay log's leak), a module
# that raises while it is collected, and a long string local, which the
# report cuts at 240 characters, here through the key: its head stays.
SOURCES = {
    "locals": ('''
import logging
import os

def test_a_call_that_leaks():
    api_key = os.environ["FAKE_SERVICE_API_KEY"]
    print("captured", api_key)
    logging.getLogger("t").warning("logged %s", api_key)
    assert api_key == "something else"
''', "1 failed"),
    "litellm": ('''
import os

import litellm

def test_an_unmocked_litellm_call():
    litellm.completion(
        model="azure/gpt-4o", api_key=os.environ["FAKE_SERVICE_API_KEY"],
        api_base="http://127.0.0.1:9", api_version="2024-08-01-preview",
        num_retries=0, messages=[{"role": "user", "content": "hi"}])
''', "1 failed"),
    "collection": ('''
import os

raise RuntimeError("cannot import: " + os.environ["FAKE_SERVICE_API_KEY"])
''', "1 error"),
    "truncated": ('''
import os

def test_a_long_string_cut_through_the_key():
    command = ("curl " + "x" * 80 + " -H 'api-key: "
               + os.environ["FAKE_SERVICE_API_KEY"] + "' " + "y" * 300)
    raise RuntimeError("the call failed")
''', "1 failed"),
}


def run_pytest(tmp_path, source, *plugin):
    (tmp_path / "test_leak.py").write_text(source)
    xml = tmp_path / "report.xml"
    env = {**os.environ, "FAKE_SERVICE_API_KEY": KEY,
           "LITELLM_LOCAL_MODEL_COST_MAP": "True",
           "PYTHONPATH": str(ROOT)}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "test_leak.py", "-p",
         "no:cacheprovider", "--showlocals", f"--junitxml={xml}", *plugin],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    return result.stdout + result.stderr, xml.read_text()


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_a_test_report_carries_no_key(tmp_path, name):
    """The terminal (what a mutation replay log keeps) and the JUnit XML:
    without the plugin both print the key; with it, neither does."""
    source, outcome = SOURCES[name]
    terminal, xml = run_pytest(tmp_path, source)
    assert fragments(terminal) and fragments(xml)
    terminal, xml = run_pytest(tmp_path, source, "-p",
                               "aios.utils.pytest_redact")
    assert outcome in terminal, terminal[-2000:]
    assert not fragments(terminal) and not fragments(xml)
    assert html.escape(redact.REDACTED) in xml  # the XML escapes it


def test_the_suites_load_the_report_hooks():
    """tests/conftest.py imports both hooks, so every run of the suite
    (a mutation replay's included) loads them."""
    tree = ast.parse((ROOT / "tests" / "conftest.py").read_text())
    imported = {
        (n.module, alias.name) for n in tree.body
        if isinstance(n, ast.ImportFrom) for alias in n.names}
    assert {("aios.utils.pytest_redact", "pytest_runtest_makereport"),
            ("aios.utils.pytest_redact", "pytest_make_collect_report")
            } <= imported


def test_every_store_provider_gets_the_injector_and_the_extractor():
    """The kernel wires its injector and extractor for every provider
    the factory offers but the in-memory test double (Graphiti, Subtask
    16; A-MEM, Subtask 17): a provider left out would inject nothing,
    and its kernel cells would run with no memory."""
    from aios.memory.providers.factory import ProviderFactory

    tree = ast.parse(LAUNCH.read_text())
    (node,) = [n for n in tree.body if isinstance(n, ast.Assign)
               and getattr(n.targets[0], "id", "") ==
               "PERSONALIZATION_PROVIDERS"]
    wired = set(ast.literal_eval(node.value))
    offered = set(ProviderFactory.get_available_providers()) - {"in-memory"}
    assert wired == offered

# -- Review fixes (Subtask 17) ------------------------------------------------

def test_the_configs_provider_keys_are_secrets():
    """``api_keys.<provider>`` is where config.yaml keeps provider keys
    (configuration.md): every string directly under it is a key, and a
    mapping under it is walked by key name, so ``huggingface``'s
    ``auth_token`` is one and its ``cache_dir`` path is not."""
    config = {"api_keys": {
        "openai": "sk-synthetic-0123456789abcdef", "gemini": "",
        "huggingface": {"auth_token": "hf-synthetic-0123456789",
                        "cache_dir": "/Users/someone/.cache/huggingface"}}}
    assert set(redact.secret_values(config, environ={})) == {
        "sk-synthetic-0123456789abcdef", "hf-synthetic-0123456789"}


def test_the_printed_config_hides_the_provider_keys():
    config = {"api_keys": {"openai": "sk-synthetic-0123456789abcdef",
                           "gemini": "",
                           "huggingface": {"auth_token": "hf-synth-0123",
                                           "cache_dir": "/cache"}}}
    assert redact.redact_secrets(config) == {"api_keys": {
        "openai": redact.REDACTED, "gemini": "",
        "huggingface": {"auth_token": redact.REDACTED,
                        "cache_dir": "/cache"}}}


def test_a_write_from_inside_a_write_neither_deadlocks_nor_leaks():
    """A handler that writes to the stream while the stream writes (a
    signal handler, a finalizer) re-enters its lock in the same thread:
    the lock must let it through."""
    import threading

    out = io.StringIO()

    class Reentering:
        fired = False

        def write(self, text):
            if not Reentering.fired:
                Reentering.fired = True
                wrapper.write(f"inner {KEY}\n")
            return out.write(text)

        def flush(self):
            pass

    values = redact._REDACTION["values"]
    redact._REDACTION["values"] = (KEY,)
    try:
        wrapper = redact._RedactingStream(Reentering())
        thread = threading.Thread(
            target=lambda: wrapper.write(f"outer {KEY}\n"), daemon=True)
        thread.start()
        thread.join(5)
        assert not thread.is_alive(), "the stream deadlocked"
        wrapper.writelines([f"first {KEY}\n", "second\n"])
        wrapper.flush()
    finally:
        redact._REDACTION["values"] = values
    text = out.getvalue()
    assert "inner" in text and "outer" in text and "second" in text
    assert KEY not in text
