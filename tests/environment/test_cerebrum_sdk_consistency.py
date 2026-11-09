"""The kernel venv's copy of the Cerebrum SDK matches the checkout.

The sibling ``../Cerebrum`` checkout is installed into this venv as a
plain copy (``pip install ../Cerebrum --no-deps --force-reinstall``),
so after an edit there the kernel keeps running the old copy until it is
reinstalled. A stale copy fails silently: the kernel parses ``/query``
with the copy's ``LLMQuery``, and pydantic drops a field the copy lacks
(benchmark v2's ``provenance_event``) without an error. This test hashes
every installed ``cerebrum`` module against its checkout counterpart and
names the reinstall command on drift. It is skipped when the checkout
is absent. iCloud's ``name 2.py`` duplicates and ``__pycache__`` are
ignored.
"""
import hashlib
import importlib.util
import re
from pathlib import Path

import pytest

CHECKOUT = Path(__file__).resolve().parents[2].parent / "Cerebrum"
REINSTALL = ".venv/bin/python -m pip install ../Cerebrum --no-deps " \
            "--force-reinstall"
# iCloud keeps conflicting copies as "name 2.py" (or "dir 2/").
DUPLICATE = re.compile(r" \d+(\.py)?$")


def _installed_root() -> Path:
    spec = importlib.util.find_spec("cerebrum")
    assert spec is not None and spec.submodule_search_locations, \
        "cerebrum is not installed in this venv"
    return Path(list(spec.submodule_search_locations)[0])


def _modules(root: Path):
    for path in sorted(root.rglob("*.py")):
        parts = path.relative_to(root).parts
        if "__pycache__" in parts or any(DUPLICATE.search(p)
                                         for p in parts):
            continue
        yield path.relative_to(root)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.skipif(not (CHECKOUT / "cerebrum").is_dir(),
                    reason="no ../Cerebrum checkout")
def test_the_installed_sdk_matches_the_checkout():
    installed = _installed_root()
    source = CHECKOUT / "cerebrum"
    drift = []
    for relative in _modules(source):
        # The wheel does not ship every top-level part (``example/``);
        # within a part it ships, every checkout module must be there.
        if not (installed / relative.parts[0]).exists():
            continue
        copy = installed / relative
        if not copy.exists():
            drift.append(f"missing: {relative}")
        elif _sha256(copy) != _sha256(source / relative):
            drift.append(f"differs: {relative}")
    assert not drift, (
        f"the installed cerebrum is stale ({len(drift)} files, e.g. "
        f"{drift[:5]}); from AIOS run: {REINSTALL}")


def test_the_installed_sdk_has_the_benchmark_v2_fields():
    """The fields the kernel reads with getattr, which a stale copy
    would drop without an error."""
    import typing

    from cerebrum.llm.apis import LLMQuery
    from cerebrum.memory.apis import MemoryQuery

    for name in ("session", "provenance_event"):
        assert name in LLMQuery.model_fields, (
            f"LLMQuery has no {name!r}; from AIOS run: {REINSTALL}")
    operations = typing.get_args(
        MemoryQuery.model_fields["operation_type"].annotation)
    assert "list_memory" in operations
