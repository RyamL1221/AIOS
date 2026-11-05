"""mem0ai is pinned to one version in both repos (NeurIPS Subtask 9d).

The kernel ran mem0ai 2.0.0 and the harness's native and replicated
agents 2.0.2 until Subtask 9d, so the two loci ran different Mem0 code.
Both requirements files now pin the same version, and this venv must
have it installed.
"""
import re
from importlib.metadata import version
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CEREBRUM = ROOT.parent / "Cerebrum"


def pinned(requirements: Path) -> str:
    for line in requirements.read_text().splitlines():
        match = re.match(r"\s*mem0ai\s*==\s*([\w.]+)", line)
        if match:
            return match.group(1)
    raise AssertionError(f"mem0ai is not pinned with == in {requirements}")


def test_kernel_requirements_pin_mem0ai_and_the_venv_has_it():
    assert version("mem0ai") == pinned(ROOT / "requirements.txt")


def test_both_repos_pin_the_same_mem0ai():
    requirements = CEREBRUM / "requirements.txt"
    if not requirements.exists():
        pytest.skip("no sibling Cerebrum checkout")
    assert pinned(requirements) == pinned(ROOT / "requirements.txt")
