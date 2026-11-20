"""The benchmark v2 driver's end-of-phase checks (scripts/run_bench_v2.sh;
NeurIPS Subtask 15 review).

A phase's checks (no kernel memory operation in an agent phase; no
stored probe turn in a kernel phase) read every kernel log of the
phase, an earlier launch's included, and run again for a phase a
resumed launch finds finished; ``RUN_PREFIX`` and ``OUTROOT`` are
required.

The real script runs in a temporary tree, with stubs for git, lsof,
curl, the kernel, the harness, set_memory_mode.py and the cell check.
"""
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

DRIVER = Path(__file__).resolve().parents[3] / "scripts" / "run_bench_v2.sh"

# The AIOS venv's python: as the kernel, prints $SIM_KERNEL_LINE once
# and waits to be stopped; as set_memory_mode.py, does nothing; as
# archive_artifacts.py, runs the real script ($SIM_ARCHIVE).
KERNEL = """#!/bin/bash
if [ "$1" = "scripts/archive_artifacts.py" ]; then
    shift; exec "$SIM_PYTHON" "$SIM_ARCHIVE" "$@"
fi
if [ "$1" = "scripts/set_memory_mode.py" ]; then
    [ -n "${SIM_MODE_LOG:-}" ] && echo "$*" >> "$SIM_MODE_LOG"
    exit 0
fi
if [ "$1" = "-m" ] && [ "$2" = "uvicorn" ]; then
    [ -n "${SIM_KERNEL_LINE:-}" ] && echo "$SIM_KERNEL_LINE"
    exec sleep 600
fi
exit 0
"""

# The Cerebrum venv's python, as the harness: writes the cell's results
# file, unless the cell's run id is $SIM_FAIL_RUN, and prints
# $SIM_HARNESS_LINE to the cell's log.
HARNESS = """#!/bin/bash
[ -n "${SIM_ARGS_LOG:-}" ] && echo "$*" >> "$SIM_ARGS_LOG"
while [ $# -gt 0 ]; do
    case $1 in
        --method) method=$2; shift ;;
        --run-id) run=$2; shift ;;
        --output) out=$2; shift ;;
    esac
    shift
done
[ "$run" = "${SIM_FAIL_RUN:-}" ] && exit 1
[ -n "${SIM_HARNESS_LINE:-}" ] && echo "$SIM_HARNESS_LINE"
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
           outroot: str = "results/sim",
           extra: dict = None) -> subprocess.CompletedProcess:
    """One launch of the real driver over the stub tree. Launches a
    second apart, so each kernel log gets its own name."""
    time.sleep(1.1)
    env = {
        **os.environ,
        "PATH": f"{aios.parent / 'bin'}:{os.environ['PATH']}",
        "MODE": "functional", "MODELS": "qwen", "TRIALS": "1",
        "PHASES": phases, "CONDITIONS": conditions,
        "SIM_KERNEL_LINE": kernel_line, "SIM_FAIL_RUN": fail_run,
        **(extra or {}),
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
    hold an earlier run's cells, which a run would overwrite or count
    as its own, and its kernel logs, which the checks read."""
    aios = tree(tmp_path)
    result = launch(aios, "kmem0", "h0", outroot="")
    assert result.returncode == 1
    assert "OUTROOT" in result.stderr
    assert not (tmp_path / "Cerebrum" / "results").exists()


def test_the_graphiti_phases_run_the_graphiti_cells(tmp_path):
    """The Graphiti phases (Subtask 16) run kernel_shared in ``kgra`` and
    the replicated and native Graphiti methods in ``agent_gra``, with the
    controls that apply: writer_scoped outside native, no_visibility in
    native only, no_memory never (it runs in kinh only)."""
    aios = tree(tmp_path)
    result = launch(aios, "kgra agent_gra",
                    "h0 no_memory no_visibility writer_scoped")
    assert result.returncode == 0, result.stdout + result.stderr
    root = tmp_path / "Cerebrum" / "results" / "sim" / "qwen"
    cells = sorted(f"{phase.name}/{cell.name}"
                   for phase in root.iterdir() if phase.name != "logs"
                   for cell in phase.iterdir())
    assert cells == [
        "agent_gra/h0_native_graphiti",
        "agent_gra/h0_replicated_graphiti",
        "agent_gra/no_visibility_native_graphiti",
        "agent_gra/writer_scoped_replicated_graphiti",
        "kgra/h0_kernel_shared",
        "kgra/writer_scoped_kernel_shared",
    ]
    assert "kernel_memory_ops=0" in result.stdout
    assert "stored_conversation_turns=0" in result.stdout


def test_every_phase_sets_k_30_and_the_300_token_budget(tmp_path):
    """Amendment 6 (docs/BENCHMARK_V2.md): every v2 phase's kernel runs
    with k 30 and a 300-token budget, so the budget, not the cap,
    limits a kernel or replicated block."""
    aios = tree(tmp_path)
    log = tmp_path / "mode.log"
    result = launch(aios, "kgra agent_gra", "h0",
                    extra={"SIM_MODE_LOG": str(log)})
    assert result.returncode == 0, result.stdout + result.stderr
    calls = log.read_text().splitlines()
    assert len(calls) == 2
    assert all("--k 30 --budget 300" in call for call in calls), calls


def test_methods_runs_only_the_named_cells(tmp_path):
    """``METHODS`` runs only the methods it names (Amendment 6's
    re-verification ran the kernel and replicated cells, not native)."""
    aios = tree(tmp_path)
    result = launch(aios, "kgra agent_gra", "h0", extra={
        "METHODS": "kernel_shared replicated_graphiti"})
    assert result.returncode == 0, result.stdout + result.stderr
    root = tmp_path / "Cerebrum" / "results" / "sim" / "qwen"
    cells = sorted(f"{phase.name}/{cell.name}"
                   for phase in root.iterdir() if phase.name != "logs"
                   for cell in phase.iterdir())
    assert cells == ["agent_gra/h0_replicated_graphiti",
                     "kgra/h0_kernel_shared"]


def test_the_amem_phases_run_the_amem_cells(tmp_path):
    """The A-MEM phases (Subtask 17) run kernel_shared in ``kamem`` and
    the replicated and native A-MEM methods in ``agent_amem``, on an
    A-MEM kernel, with the controls that apply."""
    aios = tree(tmp_path)
    log = tmp_path / "mode.log"
    result = launch(aios, "kamem agent_amem",
                    "h0 no_memory no_visibility writer_scoped",
                    extra={"SIM_MODE_LOG": str(log)})
    assert result.returncode == 0, result.stdout + result.stderr
    root = tmp_path / "Cerebrum" / "results" / "sim" / "qwen"
    cells = sorted(f"{phase.name}/{cell.name}"
                   for phase in root.iterdir() if phase.name != "logs"
                   for cell in phase.iterdir())
    assert cells == [
        "agent_amem/h0_native_amem",
        "agent_amem/h0_replicated_amem",
        "agent_amem/no_visibility_native_amem",
        "agent_amem/writer_scoped_replicated_amem",
        "kamem/h0_kernel_shared",
        "kamem/writer_scoped_kernel_shared",
    ]
    # Since Subtask 19 each control runs on a kernel of its own with its
    # ablation switch (docs/ABLATION.md): kamem's full kernel and
    # writer_scoped's, agent_amem's full kernel, no_visibility's and
    # writer_scoped's.
    calls = log.read_text().splitlines()
    assert ["--provider amem --kernel-memory on --extract off" in c
            for c in calls] == [True, True, False, False, False]
    assert all("--provider amem --kernel-memory off" in c
               for c in calls[2:])
    assert [c.split("--ablate ")[1] for c in calls] == [
        "none", "forget_scope=writer", "none", "visibility",
        "forget_scope=writer"]
    assert "kernel_memory_ops=0" in result.stdout


def test_each_control_runs_on_a_kernel_with_its_switch(tmp_path):
    """Subtask 19 (docs/ABLATION.md): a control's cells run on a fresh
    kernel whose ``memory.ablate`` is its switch, the other cells on the
    full kernel, in the same phase directory; supersession is exclude
    in every one, no_supersession's included."""
    aios = tree(tmp_path)
    log = tmp_path / "mode.log"
    result = launch(aios, "kinh kinh_ns",
                    "h0 no_delete writer_scoped no_supersession",
                    extra={"SIM_MODE_LOG": str(log)})
    assert result.returncode == 0, result.stdout + result.stderr
    calls = log.read_text().splitlines()
    assert [c.split("--ablate ")[1] for c in calls] == [
        "none", "forget_scope=none", "forget_scope=writer", "supersession"]
    assert all("--supersession exclude" in c for c in calls)
    logs = sorted((tmp_path / "Cerebrum" / "results" / "sim" / "logs")
                  .glob("kernel_qwen_kinh*_2*.log"))
    assert len(logs) == 4
    root = tmp_path / "Cerebrum" / "results" / "sim" / "qwen"
    assert sorted(cell.name for cell in (root / "kinh").iterdir()) == [
        "h0_kernel_shared", "no_delete_kernel_shared",
        "writer_scoped_kernel_shared"]


def test_a_resume_reruns_only_the_unfinished_controls_kernel(tmp_path):
    aios = tree(tmp_path)
    log = tmp_path / "mode.log"
    first = launch(aios, "kinh", "h0 no_delete",
                   fail_run="t1-qwen-kinh-kernel_shared-no_delete")
    assert first.returncode != 0
    second = launch(aios, "kinh", "h0 no_delete",
                    extra={"SIM_MODE_LOG": str(log)})
    assert second.returncode == 0, second.stdout + second.stderr
    assert [c.split("--ablate ")[1]
            for c in log.read_text().splitlines()] == ["forget_scope=none"]


def test_the_amem_no_supersession_phases_run_their_control(tmp_path):
    aios = tree(tmp_path)
    result = launch(aios, "kamem_ns agent_amem_ns", "no_supersession")
    assert result.returncode == 0, result.stdout + result.stderr
    root = tmp_path / "Cerebrum" / "results" / "sim" / "qwen"
    cells = sorted(f"{phase.name}/{cell.name}"
                   for phase in root.iterdir() if phase.name != "logs"
                   for cell in phase.iterdir())
    assert cells == ["agent_amem_ns/no_supersession_replicated_amem",
                     "kamem_ns/no_supersession_kernel_shared"]


# -- ARCHIVE (Subtask 17) -----------------------------------------------------

ARCHIVE_SCRIPT = DRIVER.parents[1] / "scripts" / "archive_artifacts.py"
KEY = "azure-test-key-0123456789abcdef"


def archiving(tmp_path: Path, **extra) -> dict:
    """The additions to a launch's environment that make it archive its
    logs with the real archive script, the synthetic key configured (the
    stub tree's .env and config.yaml hold none)."""
    return {"FAKE_SERVICE_API_KEY": KEY, "SIM_PYTHON": sys.executable,
            "SIM_ARCHIVE": str(ARCHIVE_SCRIPT),
            "ARCHIVE": str(tmp_path / "artifacts" / "run1"), **extra}


def test_archive_copies_a_clean_runs_outroot(tmp_path):
    """The run's OUTROOT, its results and logs, with SHA256SUMS."""
    aios = tree(tmp_path)
    result = launch(aios, "kmem0", "h0", extra=archiving(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "none holds a key value; copied to" in result.stdout
    copied = tmp_path / "artifacts" / "run1"
    assert [p.name for p in (copied / "logs").glob("kernel_qwen_kmem0_*")]
    assert (copied / "logs" / "qwen_kmem0_kernel_shared_h0.log").is_file()
    assert (copied / "qwen" / "kmem0" / "h0_kernel_shared"
            / "results_kernel_shared.json").is_file()
    sums = (copied / "SHA256SUMS").read_text()
    assert "./qwen/kmem0/h0_kernel_shared/results_kernel_shared.json" in sums


def test_archive_refuses_a_log_holding_a_key(tmp_path):
    """A cell's log holds the key: the driver fails, names the file, and
    copies nothing; the run's logs stay where they were."""
    aios = tree(tmp_path)
    env = archiving(tmp_path, SIM_HARNESS_LINE=f"api_key={KEY}")
    result = launch(aios, "kmem0", "h0", extra=env)
    assert result.returncode == 1
    assert "ARCHIVE REFUSED" in result.stdout
    assert "holds a configured key value" in result.stderr
    assert KEY not in result.stdout + result.stderr
    assert not (tmp_path / "artifacts" / "run1").exists()
    logs = tmp_path / "Cerebrum" / "results" / "sim" / "logs"
    assert any(KEY in p.read_text() for p in logs.glob("*.log"))


def test_archive_must_be_new(tmp_path):
    """An existing ARCHIVE stops the driver before any cell, not after
    the run."""
    aios = tree(tmp_path)
    (tmp_path / "artifacts" / "run1").mkdir(parents=True)
    result = launch(aios, "kmem0", "h0", extra=archiving(tmp_path))
    assert result.returncode == 1
    assert "set a new ARCHIVE" in result.stderr
    assert "start" not in result.stdout


def test_the_decision_check_runs_its_cells_in_house(tmp_path):
    """MODE=decision (Subtask 20, Amendment 10): no_memory in every
    cell, writer_scoped and no_supersession in the kernel and
    replicated cells, wrong_user everywhere, through the harness's
    ``--fault``; PHASES and METHODS pick the in-house cells."""
    aios = tree(tmp_path)
    args = tmp_path / "args.log"
    result = launch(aios, "kinh agent kinh_ns agent_ns", "", extra={
        "MODE": "decision", "CONDITIONS": "", "TRIALS": "",
        "METHODS": "kernel_shared replicated_inhouse native_inhouse",
        "SIM_ARGS_LOG": str(args)})
    assert result.returncode == 0, result.stdout + result.stderr
    root = tmp_path / "Cerebrum" / "results" / "sim" / "qwen"
    cells = sorted(f"{phase.name}/{cell.name}"
                   for phase in root.iterdir() if phase.name != "logs"
                   for cell in phase.iterdir())
    assert cells == [
        "agent/h0_native_inhouse", "agent/h0_replicated_inhouse",
        "agent/no_memory_native_inhouse",
        "agent/no_memory_replicated_inhouse",
        "agent/writer_scoped_replicated_inhouse",
        "agent/wrong_user_native_inhouse",
        "agent/wrong_user_replicated_inhouse",
        "agent_ns/no_supersession_replicated_inhouse",
        "kinh/h0_kernel_shared", "kinh/no_memory_kernel_shared",
        "kinh/writer_scoped_kernel_shared",
        "kinh/wrong_user_kernel_shared",
        "kinh_ns/no_supersession_kernel_shared",
    ]
    calls = args.read_text().splitlines()
    wrong = [c for c in calls if "-wrong_user " in c + " "]
    assert len(wrong) == 3
    assert all("--heterogeneity 0 --fault wrong_user" in c for c in wrong)
    assert all("--no-judge" in c for c in calls)
    assert all("--trials 5" in c for c in calls)
    assert all("--dataset pilot_v2 " in c for c in calls)


def test_the_no_memory_check_runs_every_user_of_users_v2(tmp_path):
    """Amendment 10's no-memory check over every user: DATASET and
    TRIALS reach the harness, one kernel in-house no_memory cell."""
    aios = tree(tmp_path)
    args = tmp_path / "args.log"
    result = launch(aios, "kinh", "no_memory", extra={
        "MODE": "decision", "DATASET": "users_v2", "TRIALS": "150",
        "SIM_ARGS_LOG": str(args)})
    assert result.returncode == 0, result.stdout + result.stderr
    root = tmp_path / "Cerebrum" / "results" / "sim" / "qwen"
    assert sorted(c.name for c in (root / "kinh").iterdir()) == [
        "no_memory_kernel_shared"]
    (call,) = args.read_text().splitlines()
    assert "--dataset users_v2 --trials 150 " in call
    assert "--no-judge" in call


def test_the_decision_checks_default_phases_hold_its_ns_cells(tmp_path):
    """MODE=decision without PHASES runs the ``_ns`` phases too, so the
    no_supersession cells D3 reads are there by default."""
    aios = tree(tmp_path)
    result = launch(aios, "", "h0 no_supersession", extra={
        "MODE": "decision", "TRIALS": "",
        "METHODS": "kernel_shared replicated_inhouse"})
    assert result.returncode == 0, result.stdout + result.stderr
    root = tmp_path / "Cerebrum" / "results" / "sim" / "qwen"
    cells = sorted(f"{phase.name}/{cell.name}"
                   for phase in root.iterdir() if phase.name != "logs"
                   for cell in phase.iterdir())
    assert cells == [
        "agent/h0_replicated_inhouse",
        "agent_ns/no_supersession_replicated_inhouse",
        "kinh/h0_kernel_shared", "kinh_ns/no_supersession_kernel_shared",
        "kmem0/h0_kernel_shared", "kmem0_ns/no_supersession_kernel_shared",
    ]
