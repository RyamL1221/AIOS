# Test reports without key values (Subtask 17, Decision 3).
"""A pytest plugin that removes key values from every test report.

The AIOS tests load ``AIOS/.env`` into the environment, so a call a
test leaves unmocked carries the Azure key, and a traceback's locals
print it: a Subtask 16 mutation replay's JUnit XML held it. Every
report's failure text and captured output are redacted before the
terminal or a JUnit XML file prints them. ``tests/conftest.py`` imports
the hook; ``-p aios.utils.pytest_redact`` loads it elsewhere.
"""
from functools import lru_cache
from pathlib import Path

import pytest

from aios.utils.redact import redact_report, secret_values

ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def _file_configs() -> tuple:
    """``AIOS/.env`` and ``aios/config/config.yaml`` (each when it
    exists), read once a session."""
    configs = []
    env_file = ROOT / ".env"
    if env_file.is_file():
        from dotenv import dotenv_values

        configs.append({name.lower(): value for name, value
                        in dotenv_values(env_file).items()})
    config_file = ROOT / "aios" / "config" / "config.yaml"
    if config_file.is_file():
        import yaml

        try:
            configs.append(yaml.safe_load(config_file.read_text()) or {})
        except yaml.YAMLError:
            pass
    return tuple(configs)


def report_secrets() -> tuple:
    """The environment's secret values (read at each report: a test may
    load ``.env`` into it), ``AIOS/.env``'s and ``config.yaml``'s."""
    return secret_values(*_file_configs())


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    redact_report(outcome.get_result(), report_secrets())
