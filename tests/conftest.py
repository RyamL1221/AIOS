# Test reports carry no key value (Subtask 17, Decision 3): the hook
# redacts every report before the terminal or a JUnit XML prints it.
from aios.utils.pytest_redact import pytest_runtest_makereport  # noqa: F401
