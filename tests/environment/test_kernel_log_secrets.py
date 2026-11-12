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


def test_the_kernel_installs_the_log_redaction():
    """runtime.launch installs it at import, after .env is loaded and
    before the app is made (the module cannot be imported here: it
    starts the kernel)."""
    tree = ast.parse(LAUNCH.read_text())
    calls = [i for i, node in enumerate(tree.body)
             if isinstance(node, ast.Expr)
             and isinstance(node.value, ast.Call)
             and getattr(node.value.func, "id", "") in (
                 "install_log_redaction", "load_dotenv")]
    names = [tree.body[i].value.func.id for i in calls]
    assert names == ["load_dotenv", "install_log_redaction"]
    install = tree.body[calls[1]].value
    assert ast.unparse(install.args[0]) == "secret_values(config.config)"


FAILING_TEST = '''
import os

def test_a_call_that_leaks():
    api_key = os.environ["FAKE_SERVICE_API_KEY"]
    assert api_key == "something else"
'''


def run_pytest(tmp_path, *plugin):
    (tmp_path / "test_leak.py").write_text(FAILING_TEST)
    xml = tmp_path / "report.xml"
    env = {**os.environ, "FAKE_SERVICE_API_KEY": KEY,
           "PYTHONPATH": str(ROOT)}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "test_leak.py", "-p",
         "no:cacheprovider", "--showlocals", f"--junitxml={xml}", *plugin],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    return result.stdout + result.stderr, xml.read_text()


def test_a_test_report_carries_no_key(tmp_path):
    """A failing test whose locals hold a key: without the plugin both
    the terminal and the JUnit XML print it; with it, neither does."""
    terminal, xml = run_pytest(tmp_path)
    assert KEY in terminal and KEY in xml
    terminal, xml = run_pytest(tmp_path, "-p", "aios.utils.pytest_redact")
    assert "1 failed" in terminal
    assert KEY not in terminal and KEY not in xml
    assert html.escape(redact.REDACTED) in xml  # the XML escapes it
