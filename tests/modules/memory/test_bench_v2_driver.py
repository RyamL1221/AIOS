"""The benchmark v2 driver's end-of-phase checks (scripts/run_bench_v2.sh;
NeurIPS Subtask 15 review).

A phase's checks (no kernel memory operation in an agent phase; no
stored probe turn in a kernel phase) read every kernel log of the
phase, an earlier launch's included, and run again for a phase a
resumed launch finds finished; ``RUN_PREFIX`` is required.

The real script runs in a temporary tree, with stubs for git, lsof,
curl, the kernel, the harness, set_memory_mode.py and the cell check.
"""
import os
import stat
import subprocess
import time
from pathlib import Path

DRIVER = Path(__file__).resolve().parents[3] / "scripts" / "run_bench_v2.sh"

# The AIOS venv's python: as the kernel, prints $SIM_KERNEL_LINE once
# and waits to be stopped; as set_memory_mode.py, does nothing.
KERNEL = """#!/bin/bash
if [ "$1" = "-m" ] && [ "$2" = "uvicorn" ]; then
    [ -n "${SIM_KERNEL_LINE:-}" ] && echo "$SIM_KERNEL_LINE"
    exec sleep 600
fi
exit 0
"""

# The Cerebrum venv's python, as the harness: writes the cell's results
# file, unless the cell's run id is $SIM_FAIL_RUN.
HARNESS = """#!/bin/bash
while [ $# -gt 0 ]; do
    case $1 in
        --method) method=$2; shift ;;
        --run-id) run=$2; shift ;;
        --output) out=$2; shift ;;
    esac
    shift
done
[ "$run" = "${SIM_FAIL_RUN:-}" ] && exit 1
mkdir -p "$out" && echo done > "$out/results_$method.json"
"""

# pilot_cell_done.py: a cell is done when its results file says so.
CELL_DONE = """import sys
from pathlib import Path
path = Path(sys.argv[1])
sys.exit(0 if path.is_file() and path.read_text().strip() == "done" else 1)
"""

STUBS = {
    "git": 'case "$*" in *rev-parse*) echo 0123abc ;; esac\nexit 0\n',
    "lsof": "exit 1\n",  # nothing listens on port 8000
    "curl": "exit 0\n",  # the kernel answers /status at once
}


def executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def tree(tmp_path: Path) -> Path:
    """The stub AIOS and Cerebrum checkouts; returns the AIOS one."""
    aios = tmp_path / "AIOS"
    config = aios / "aios" / "config" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("memory: {}\n")
    (aios / ".env").write_text("")
    executable(aios / ".venv" / "bin" / "python", KERNEL)
    (aios / "scripts").mkdir()
    (aios / "scripts" / "pilot_cell_done.py").write_text(CELL_DONE)
    executable(tmp_path / "Cerebrum" / ".venv" / "bin" / "python", HARNESS)
    for name, body in STUBS.items():
        executable(tmp_path / "bin" / name, "#!/bin/bash\n" + body)
    return aios


def launch(aios: Path, phases: str, conditions: str,
           kernel_line: str = "", fail_run: str = "",
           prefix: str = "t1",
           outroot: str = "results/sim") -> subprocess.CompletedProcess:
    """One launch of the real driver over the stub tree. Launches a
    second apart, so each kernel log gets its own name."""
    time.sleep(1.1)
    env = {
        **os.environ,
        "PATH": f"{aios.parent / 'bin'}:{os.environ['PATH']}",
        "MODE": "functional", "MODELS": "qwen", "TRIALS": "1",
        "PHASES": phases, "CONDITIONS": conditions,
        "SIM_KERNEL_LINE": kernel_line, "SIM_FAIL_RUN": fail_run,
    }
    for key, value in (("RUN_PREFIX", prefix), ("OUTROOT", outroot)):
        if value:
            env[key] = value
        else:
            env.pop(key, None)
    return subprocess.run(
        ["bash", str(DRIVER)], cwd=aios, env=env, capture_output=True,
        text=True, timeout=120,
    )


def test_a_resumed_kernel_phase_checks_the_earlier_launchs_log(tmp_path):
    """A kernel phase stopped by a failed cell, then resumed: the resumed
    launch's check also reads the first launch's kernel log, so a probe
    turn stored there stops the driver."""
    aios = tree(tmp_path)
    first = launch(aios, "kmem0", "h0 h2",
                   kernel_line="Stored conversation memory for u0",
                   fail_run="t1-qwen-kmem0-kernel_shared-h2")
    assert first.returncode == 1 and "FAILED" in first.stdout
    second = launch(aios, "kmem0", "h0 h2")
    assert "skip qwen_kmem0_kernel_shared_h0" in second.stdout
    assert second.returncode == 1, second.stdout
    assert "stored_conversation_turns=1" in second.stdout
    assert "PROBE TURNS STORED" in second.stdout
    assert (aios / "aios" / "config" / "config.yaml").read_text() == \
        "memory: {}\n"


def test_a_phase_found_finished_is_checked_again(tmp_path):
    """A phase whose cells all finished but whose check stopped the
    driver: a re-launch finds it finished and still fails its check."""
    aios = tree(tmp_path)
    first = launch(aios, "kmem0", "h0",
                   kernel_line="Stored conversation memory for u0")
    assert first.returncode == 1 and "PROBE TURNS STORED" in first.stdout
    second = launch(aios, "kmem0", "h0")
    assert "skip qwen kmem0" in second.stdout
    assert second.returncode == 1, second.stdout
    assert "PROBE TURNS STORED" in second.stdout


def test_a_resumed_agent_phase_checks_the_earlier_launchs_log(tmp_path):
    """The agent phase's zero-memory-operations check, resumed after a
    failed cell, also reads the first launch's kernel log."""
    aios = tree(tmp_path)
    first = launch(aios, "agent", "h0",
                   kernel_line="add_memory: agent=profile_agent",
                   fail_run="t1-qwen-agent-replicated_inhouse-h0")
    assert first.returncode == 1 and "FAILED" in first.stdout
    second = launch(aios, "agent", "h0")
    assert second.returncode == 1, second.stdout
    assert "kernel_memory_ops=1" in second.stdout
    assert "MEMORY OPS IN KERNEL LOG" in second.stdout


def test_clean_logs_over_two_launches_pass(tmp_path):
    """Clean kernel logs over two launches pass every check (the counts
    are summed, not one per file) and the run finishes."""
    aios = tree(tmp_path)
    first = launch(aios, "kmem0 agent", "h0",
                   fail_run="t1-qwen-agent-replicated_inhouse-h0")
    assert first.returncode == 1
    second = launch(aios, "kmem0 agent", "h0")
    assert second.returncode == 0, second.stdout + second.stderr
    assert "skip qwen kmem0" in second.stdout
    assert "stored_conversation_turns=0" in second.stdout
    assert "kernel_memory_ops=0" in second.stdout
    assert "BENCH V2 functional DONE" in second.stdout


def test_a_run_needs_its_own_prefix(tmp_path):
    """Without RUN_PREFIX the driver refuses to start: a reused prefix
    would inherit an earlier run's stores and tombstones."""
    aios = tree(tmp_path)
    result = launch(aios, "kmem0", "h0", prefix="")
    assert result.returncode == 1
    assert "RUN_PREFIX" in result.stderr
    assert not (tmp_path / "Cerebrum" / "results").exists()


def test_a_run_needs_its_own_outroot(tmp_path):
    """Without OUTROOT the driver refuses to start: a default one would
    hold an earlier run's cells, which a run overwrites, and its kernel
    logs, which the checks read."""
    aios = tree(tmp_path)
    result = launch(aios, "kmem0", "h0", outroot="")
    assert result.returncode == 1
    assert "OUTROOT" in result.stderr
    assert not (tmp_path / "Cerebrum" / "results").exists()
