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

from aios.utils.redact import (
    file_secret_configs,
    redact_report,
    secret_values,
)

ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def _file_configs() -> tuple:
    """``AIOS/.env`` and ``aios/config/config.yaml``, read once a
    session."""
    return file_secret_configs(ROOT)


def report_secrets() -> tuple:
    """The environment's secret values (read at each report: a test may
    load ``.env`` into it), ``AIOS/.env``'s and ``config.yaml``'s."""
    return secret_values(*_file_configs())


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    redact_report(outcome.get_result(), report_secrets())


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector):
    """A module that fails to import or raises while collected."""
    outcome = yield
    redact_report(outcome.get_result(), report_secrets())
