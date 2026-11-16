"""A test process holds no value of the checkout's .env that its caller
did not give it (known issue 51). LiteLLM's import loads .env in its
default DEV mode; the suite's conftest sets ``LITELLM_MODE`` to
PRODUCTION before anything imports LiteLLM, and the Graphiti tests'
``load_env`` copies the ``NEO4J_*`` names only. No value is printed."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("_dotenv_probe.py")


@pytest.mark.skipif(not (ROOT / ".env").is_file(),
                    reason="no .env in the checkout")
def test_a_test_that_imports_litellm_gets_no_dotenv_name():
    """A pytest of this suite, started without any name of .env, runs a
    test that imports LiteLLM: no name of .env is in its environment
    afterwards."""
    from dotenv import dotenv_values

    names = set(dotenv_values(ROOT / ".env")) | {"LITELLM_MODE"}
    env = {k: v for k, v in os.environ.items() if k not in names}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         str(PROBE)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    tail = "\n".join(run.stdout.splitlines()[-15:])
    assert run.returncode == 0, tail
    assert "1 passed" in run.stdout, tail


def test_load_env_copies_the_neo4j_names_only(tmp_path, monkeypatch):
    """The Graphiti tests' ``load_env`` takes ``NEO4J_*`` from .env and
    nothing else, and overrides no variable already set."""
    from tests.modules.memory import _graphiti_script as script

    (tmp_path / ".env").write_text(
        "NEO4J_URI=bolt://127.0.0.1:1\n"
        "NEO4J_USER=from-file\n"
        "AZURE_API_KEY=not-a-real-key-0123456789\n"
        "# NEO4J_PASSWORD=commented-out\n")
    monkeypatch.setattr(script, "AIOS_ROOT", tmp_path)
    for name in ("NEO4J_URI", "NEO4J_PASSWORD", "AZURE_API_KEY"):
        monkeypatch.setenv(name, "x")  # restored after the test
        monkeypatch.delenv(name)
    monkeypatch.setenv("NEO4J_USER", "from-caller")
    script.load_env()
    assert os.environ["NEO4J_URI"] == "bolt://127.0.0.1:1"
    assert os.environ["NEO4J_USER"] == "from-caller"
    assert "AZURE_API_KEY" not in os.environ
    assert "NEO4J_PASSWORD" not in os.environ
