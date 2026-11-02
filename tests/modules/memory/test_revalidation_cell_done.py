"""The re-validation driver must not accept a cell with failed trials."""
import importlib.util
import json
from pathlib import Path

SCRIPT = (
    Path(__file__).parents[3] / "scripts" / "revalidation_cell_done.py"
)
spec = importlib.util.spec_from_file_location("cell_done", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

GOOD = {"failed": False, "injection_diagnostics": {"injected_count": 2}}


def write(tmp_path, trials):
    path = tmp_path / "results.json"
    path.write_text(json.dumps({"conditions": [{"trials": trials}]}))
    return str(path)


def test_complete_cell_is_done(tmp_path):
    assert module.cell_done(write(tmp_path, [GOOD, GOOD]), 2)


def test_failed_trial_is_not_done(tmp_path):
    bad = {"failed": True, "injection_diagnostics": None}
    assert not module.cell_done(write(tmp_path, [GOOD, bad]), 2)


def test_missing_diagnostics_is_not_done(tmp_path):
    bad = {"failed": False, "injection_diagnostics": None}
    assert not module.cell_done(write(tmp_path, [GOOD, bad]), 2)


def test_short_or_missing_cell_is_not_done(tmp_path):
    assert not module.cell_done(write(tmp_path, [GOOD]), 2)
    assert not module.cell_done(str(tmp_path / "none.json"), 2)
