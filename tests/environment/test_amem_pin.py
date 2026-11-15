"""A-MEM is pinned to one commit in both repos (NeurIPS Subtask 17,
docs/AMEM_BACKEND.md, "Versions and setup"): the kernel's provider and
the harness's native and replicated agents run the same A-MEM code
(WujiangXu/A-mem-sys), and this venv has that commit installed."""
import json
import re
from importlib import metadata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CEREBRUM = ROOT.parent / "Cerebrum"
REPO = "https://github.com/WujiangXu/A-mem-sys"


def pinned_commit(requirements: Path) -> str:
    for line in requirements.read_text().splitlines():
        match = re.match(r"\s*agentic-memory\s*@\s*git\+(\S+)@([0-9a-f]{40})",
                         line)
        if match:
            assert match.group(1) == REPO, match.group(1)
            return match.group(2)
    raise AssertionError(
        f"agentic-memory is not pinned by commit in {requirements}")


def test_kernel_requirements_pin_the_commit_and_the_venv_has_it():
    from cerebrum.utils import amem

    commit = pinned_commit(ROOT / "requirements.txt")
    assert commit == amem.PINNED_COMMIT
    dist = metadata.distribution("agentic-memory")
    installed = json.loads(dist.read_text("direct_url.json") or "{}")
    assert installed.get("url") == REPO + ".git" or installed.get(
        "url") == REPO
    assert (installed.get("vcs_info") or {}).get("commit_id") == commit
    assert amem.versions()["agentic_memory"] == commit


def test_both_repos_pin_the_same_commit():
    """Cerebrum pins A-MEM in ``requirements-amem.txt``: its
    ``requirements.txt`` is the SDK package's dependency list."""
    requirements = CEREBRUM / "requirements-amem.txt"
    if not CEREBRUM.exists():
        pytest.skip("no sibling Cerebrum checkout")
    assert pinned_commit(requirements) == pinned_commit(
        ROOT / "requirements.txt")


def test_the_sdk_package_keeps_no_direct_reference():
    """Cerebrum's package metadata is built from its ``requirements.txt``
    (hatch-requirements-txt), which refuses a ``git+`` reference, and a
    published package could not carry one: with A-MEM's pin there, the
    SDK no longer installs (``pip install ../Cerebrum``)."""
    requirements = CEREBRUM / "requirements.txt"
    if not requirements.exists():
        pytest.skip("no sibling Cerebrum checkout")
    direct = [line for line in requirements.read_text().splitlines()
              if not line.lstrip().startswith("#")
              and ("git+" in line or " @ " in line)]
    assert direct == []
