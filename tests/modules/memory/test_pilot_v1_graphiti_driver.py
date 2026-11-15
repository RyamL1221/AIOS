"""The pilot_v1 Graphiti driver (scripts/run_pilot_v1_graphiti.sh;
NeurIPS Subtask 16).

The kernel stores a v1 chat turn after the reply, in the background, and
``GET /memory/cost`` waits on the user's write barrier for it. A Graphiti
turn takes longer than the config's 5 s barrier timeout, so the driver
sets 60 s, as the benchmark v2 driver does: at 5 s, 7 of the first 12
cost reads of the smoke's first launch timed out and missed calls.

The real script runs in the v2 driver test's stub tree, with a
``set_memory_mode.py`` stub that records its arguments.
"""
import os
import subprocess
from pathlib import Path

from tests.modules.memory import test_bench_v2_driver as v2

DRIVER = (Path(__file__).resolve().parents[3] / "scripts"
          / "run_pilot_v1_graphiti.sh")

# The AIOS venv's python: as the kernel, waits to be stopped; as
# set_memory_mode.py, records its arguments; as archive_artifacts.py,
# runs the real script.
RECORDING = """#!/bin/bash
if [ "$1" = "scripts/archive_artifacts.py" ]; then
    shift; exec "$SIM_PYTHON" "$SIM_ARCHIVE" "$@"
fi
if [ "$1" = "-m" ] && [ "$2" = "uvicorn" ]; then
    exec sleep 600
fi
echo "$*" >> "$MODE_LOG"
exit 0
"""


def test_every_phase_sets_the_barrier_timeout(tmp_path):
    aios = v2.tree(tmp_path)
    v2.executable(aios / ".venv" / "bin" / "python", RECORDING)
    modes = tmp_path / "modes.log"
    env = {**os.environ,
           "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
           "MODELS": "qwen", "TRIALS": "1", "LEVELS": "0",
           "RUN_PREFIX": "t1", "OUTROOT": "results/sim",
           "MODE_LOG": str(modes)}
    result = subprocess.run(["bash", str(DRIVER)], cwd=aios, env=env,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    calls = modes.read_text().splitlines()
    assert [c for c in calls if "--kernel-memory on" in c]
    assert [c for c in calls if "--kernel-memory off" in c]
    assert all("--barrier-timeout-ms 60000" in c for c in calls), calls


def test_methods_runs_only_the_named_cells(tmp_path):
    """``METHODS`` runs only the methods it names (Subtask 17's Decision
    2 re-ran native Graphiti alone, at H = 0 and 2)."""
    aios = v2.tree(tmp_path)
    v2.executable(aios / ".venv" / "bin" / "python", RECORDING)
    env = {**os.environ,
           "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
           "MODELS": "qwen", "TRIALS": "1", "PHASES": "agent_gra",
           "METHODS": "native_graphiti", "RUN_PREFIX": "t1",
           "OUTROOT": "results/sim",
           "MODE_LOG": str(tmp_path / "modes.log")}
    result = subprocess.run(["bash", str(DRIVER)], cwd=aios, env=env,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    root = tmp_path / "Cerebrum" / "results" / "sim" / "qwen"
    cells = sorted(f"{phase.name}/{cell.name}"
                   for phase in root.iterdir() if phase.name != "logs"
                   for cell in phase.iterdir())
    assert cells == ["agent_gra/h0_native_graphiti",
                     "agent_gra/h2_native_graphiti"]


def test_backend_amem_runs_the_amem_cells(tmp_path):
    """``BACKEND=amem`` (scripts/run_pilot_v1_amem.sh; Subtask 17) runs
    the pilot on an A-MEM kernel: kernel_shared in ``kamem``, the
    replicated and native A-MEM methods in ``agent_amem``."""
    aios = v2.tree(tmp_path)
    v2.executable(aios / ".venv" / "bin" / "python", RECORDING)
    modes = tmp_path / "modes.log"
    env = {**os.environ,
           "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
           "MODELS": "qwen", "TRIALS": "1", "LEVELS": "0",
           "BACKEND": "amem", "RUN_PREFIX": "t1",
           "OUTROOT": "results/sim", "MODE_LOG": str(modes)}
    result = subprocess.run(["bash", str(DRIVER)], cwd=aios, env=env,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    root = tmp_path / "Cerebrum" / "results" / "sim" / "qwen"
    cells = sorted(f"{phase.name}/{cell.name}"
                   for phase in root.iterdir() if phase.name != "logs"
                   for cell in phase.iterdir())
    assert cells == ["agent_amem/h0_native_amem",
                     "agent_amem/h0_replicated_amem",
                     "kamem/h0_kernel_shared"]
    calls = modes.read_text().splitlines()
    assert all("--provider amem" in c for c in calls), calls
    assert "kernel_memory_ops=0" in result.stdout


def test_archive_refuses_a_log_holding_a_key(tmp_path):
    """``ARCHIVE`` (Subtask 17): a cell's log holds a configured key, so
    the driver fails and copies nothing."""
    aios = v2.tree(tmp_path)
    v2.executable(aios / ".venv" / "bin" / "python", RECORDING)
    env = {**os.environ,
           "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
           "MODELS": "qwen", "TRIALS": "1", "LEVELS": "0",
           "PHASES": "agent_gra", "RUN_PREFIX": "t1",
           "OUTROOT": "results/sim", "MODE_LOG": str(tmp_path / "m.log"),
           **v2.archiving(tmp_path, SIM_HARNESS_LINE=f"api_key={v2.KEY}")}
    result = subprocess.run(["bash", str(DRIVER)], cwd=aios, env=env,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "ARCHIVE REFUSED" in result.stdout
    assert v2.KEY not in result.stdout + result.stderr
    assert not (tmp_path / "artifacts" / "run1").exists()
