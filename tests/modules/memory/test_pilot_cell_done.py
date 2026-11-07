"""The pilot and heterogeneity drivers re-run a cell unless its only
failed trials are writer failures. A trial whose memory backend failed
silently (``backend_extraction_failed``, Subtask 10) is not done: the
driver stops instead of moving on with an empty store."""
import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).parents[3] / "scripts" / "pilot_cell_done.py"
spec = importlib.util.spec_from_file_location("pilot_cell_done", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

GOOD = {"failed": False}


def write(tmp_path, trials):
    path = tmp_path / "results.json"
    path.write_text(json.dumps({"conditions": [{"trials": trials}]}))
    return str(path)


def test_writer_failure_is_done(tmp_path):
    writer = {"failed": True, "writer_failed": ["task_agent"]}
    assert module.cell_done(write(tmp_path, [GOOD, writer]), 2)


def test_silent_backend_failure_is_not_done(tmp_path):
    silent = {"failed": True, "writer_failed": [],
              "error_message": "backend_extraction_failed: no backend "
                               "LLM calls recorded"}
    assert not module.cell_done(write(tmp_path, [GOOD, silent]), 2)


def write_meta(tmp_path, trials, commit, kernel):
    path = tmp_path / "results.json"
    path.write_text(json.dumps({
        "experiment_metadata": {"git_commit": commit,
                                "kernel_git_commit": kernel},
        "conditions": [{"trials": trials}],
    }))
    return str(path)


def test_strict_refuses_any_failed_trial(tmp_path):
    writer = {"failed": True, "writer_failed": ["task_agent"]}
    path = write(tmp_path, [GOOD, writer])
    assert module.cell_done(path, 2)
    assert not module.cell_done(path, 2, strict=True)
    assert module.cell_done(write(tmp_path, [GOOD, GOOD]), 2, strict=True)


def test_commits_must_match_and_never_be_dirty(tmp_path):
    ok = write_meta(tmp_path, [GOOD], "abc", "def")
    assert module.cell_done(ok, 1, True, "abc", "def")
    assert not module.cell_done(ok, 1, True, "abc", "xyz")
    dirty = write_meta(tmp_path, [GOOD], "abc-dirty", "def")
    assert not module.cell_done(dirty, 1, True, "abc", "def")
