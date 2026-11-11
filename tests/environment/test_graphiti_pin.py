"""graphiti-core is pinned to one version in both repos (NeurIPS
Subtask 16, docs/GRAPHITI_BACKEND.md), as mem0ai is: the kernel's
provider and the harness's native and replicated agents run the same
Graphiti code, with the same Neo4j driver, and this venv has them."""
import re
from importlib.metadata import version
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CEREBRUM = ROOT.parent / "Cerebrum"


def pinned(requirements: Path, package: str) -> str:
    for line in requirements.read_text().splitlines():
        match = re.match(rf"\s*{re.escape(package)}\s*==\s*([\w.]+)", line)
        if match:
            return match.group(1)
    raise AssertionError(f"{package} is not pinned with == in {requirements}")


@pytest.mark.parametrize("package", ["graphiti-core", "neo4j"])
def test_kernel_requirements_pin_it_and_the_venv_has_it(package):
    assert version(package) == pinned(ROOT / "requirements.txt", package)


@pytest.mark.parametrize("package", ["graphiti-core", "neo4j"])
def test_both_repos_pin_the_same_version(package):
    requirements = CEREBRUM / "requirements.txt"
    if not requirements.exists():
        pytest.skip("no sibling Cerebrum checkout")
    assert pinned(requirements, package) == pinned(
        ROOT / "requirements.txt", package)
