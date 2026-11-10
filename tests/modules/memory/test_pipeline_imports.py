"""The memory pipeline library imports no ``cerebrum`` module.

The library (``aios/memory/pipeline``) depends on the standard library
and the provider contract only. The benchmark's scorer re-exports the
library's matcher (``matching.py``), never the other way round, and the
callers pass the usage tag (docs/DELETION_AND_SUPERSESSION.md, "The
matcher, shared"). This greps every module of the package for an import
of ``cerebrum``: a statement (``import cerebrum...``, ``from cerebrum...
import``, at any depth of the file) or a dynamic one
(``importlib.import_module("cerebrum...")``, ``__import__``).
"""
import ast
from pathlib import Path

import aios.memory.pipeline as pipeline

LIBRARY = Path(pipeline.__file__).resolve().parent


def sdk_imports(path: Path) -> list:
    """``"<file>:<line>: <module>"`` for every import of a ``cerebrum``
    module in ``path``."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found = []
    for node in ast.walk(tree):
        modules = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            modules = [node.module or ""]
        elif isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", "")
            if (name in ("import_module", "__import__") and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                modules = [node.args[0].value]
        for module in modules:
            if module == "cerebrum" or module.startswith("cerebrum."):
                found.append(f"{path.name}:{node.lineno}: {module}")
    return found


def test_the_pipeline_library_imports_no_cerebrum_module():
    """Fails on any ``cerebrum`` import in ``aios/memory/pipeline``."""
    files = sorted(LIBRARY.rglob("*.py"))
    assert files, LIBRARY
    found = [line for path in files for line in sdk_imports(path)]
    assert not found, found


def test_the_scan_finds_every_form_of_a_cerebrum_import(tmp_path):
    """The scan is not vacuous: it finds a planted import in each form,
    including one inside a function, and ignores the word in text."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        '"""Mentions cerebrum.utils in a docstring."""\n'
        "import importlib\n"
        "import cerebrum\n"
        "from cerebrum.utils.usage import tagged\n"
        "def later():\n"
        "    from cerebrum.memory import apis\n"
        "    importlib.import_module('cerebrum.utils.matching')\n"
        "    __import__('cerebrum.config')\n"
        "# import cerebrum.in_a_comment\n"
    )
    assert sdk_imports(planted) == [
        "planted.py:3: cerebrum",
        "planted.py:4: cerebrum.utils.usage",
        "planted.py:6: cerebrum.memory",
        "planted.py:7: cerebrum.utils.matching",
        "planted.py:8: cerebrum.config",
    ]
