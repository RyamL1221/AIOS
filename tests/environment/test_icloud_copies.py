"""Collection leaves out iCloud's conflict copies (Subtask 17).

iCloud Drive writes a copy ``name 2.py`` beside a file it found changed
in two places. pytest's ``test_*.py`` matched the copies of test files,
so a stale copy failed as a new failure and the copies added their
tests to the suite's count. ``tests/conftest.py`` leaves out every
Python file whose name is not a module name.
"""
import importlib.util
from pathlib import Path

CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"


def _ignore_hook():
    spec = importlib.util.spec_from_file_location("_tests_conftest",
                                                  CONFTEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.pytest_ignore_collect


def test_a_copy_no_import_loads_is_left_out(tmp_path):
    hook = _ignore_hook()
    assert hook(collection_path=tmp_path / "test_x 2.py",
                config=None) is True
    assert hook(collection_path=tmp_path / "test_x.py", config=None) is None
    assert hook(collection_path=tmp_path / "data 2", config=None) is None


def test_the_session_collected_no_copy(request):
    """In a full run, where the tree holds copies, none was collected."""
    copies = sorted({item.path.name for item in request.session.items
                     if not item.path.stem.isidentifier()})
    assert copies == []
