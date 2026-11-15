# Test reports carry no key value (Subtask 17, Decision 3): the hook
# redacts every report before the terminal or a JUnit XML prints it.
from aios.utils.pytest_redact import (  # noqa: F401
    pytest_make_collect_report,
    pytest_runtest_makereport,
)
