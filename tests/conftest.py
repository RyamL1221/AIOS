import os

# LiteLLM loads the checkout's .env into the environment when it is
# imported in DEV mode, its default (litellm 1.83.0, ``__init__.py``,
# lines 19-20), so every test process held the Azure key and the Neo4j
# password whatever its caller removed (known issue 51). Set before
# anything imports LiteLLM. A test that needs a value of .env reads it
# itself (``_graphiti_script.load_env``: ``NEO4J_*`` only).
os.environ["LITELLM_MODE"] = "PRODUCTION"

# Test reports carry no key value (Subtask 17, Decision 3): the hook
# redacts every report before the terminal or a JUnit XML prints it.
from aios.utils.pytest_redact import (  # noqa: F401,E402
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
