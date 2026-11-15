# Test reports carry no key value (Subtask 17, Decision 3): the hook
# redacts every report before the terminal or a JUnit XML prints it.
from aios.utils.pytest_redact import (  # noqa: F401
    pytest_make_collect_report,
    pytest_runtest_makereport,
)


def pytest_ignore_collect(collection_path, config):
    """Leave out a Python file whose name is not a module name (Subtask
    17): iCloud's conflict copies, such as ``test_x 2.py``, beside the
    real file. Collected, a stale copy read as a new failure, and every
    copy added its tests to the count."""
    if (collection_path.suffix == ".py"
            and not collection_path.stem.isidentifier()):
        return True
    return None
