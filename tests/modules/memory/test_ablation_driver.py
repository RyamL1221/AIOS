"""The ablation driver (scripts/run_ablation.sh; NeurIPS Subtask 19,
docs/ABLATION.md): each switch against the full kernel, paired on the
same users, under its row's condition, kernel locus only.

The real script runs in a temporary tree with the stubs of
test_bench_v2_driver.py, and a harness stub that records its arguments.
"""
import os
import subprocess
import time
from pathlib import Path

from tests.modules.memory.test_bench_v2_driver import executable, tree

DRIVER = Path(__file__).resolve().parents[3] / "scripts" / "run_ablation.sh"

# The harness: records its arguments, then writes the cell's results.
HARNESS = """#!/bin/bash
echo "$*" >> "$SIM_HARNESS_LOG"
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

ALL = ("barrier identity visibility supersession forget_scope quota "
       "block_format block_order budget threshold consumer_config")


def launch(tmp_path, aios, mode="functional", **extra):
    time.sleep(1.1)
    executable(tmp_path / "Cerebrum" / ".venv" / "bin" / "python", HARNESS)
    env = {
        **os.environ,
        "PATH": f"{aios.parent / 'bin'}:{os.environ['PATH']}",
        "MODE": mode, "RUN_PREFIX": "a1", "OUTROOT": "results/abl",
        "SIM_MODE_LOG": str(tmp_path / "mode.log"),
        "SIM_HARNESS_LOG": str(tmp_path / "harness.log"),
        **extra,
    }
    return subprocess.run(["bash", str(DRIVER)], cwd=aios, env=env,
                          capture_output=True, text=True, timeout=300)


def cells(tmp_path):
    root = tmp_path / "Cerebrum" / "results" / "abl" / "qwen"
    return sorted(f"{phase.name}/{cell.name}" for phase in root.iterdir()
                  for cell in phase.iterdir())


def lines(tmp_path, name):
    path = tmp_path / name
    return path.read_text().splitlines() if path.exists() else []


def test_every_switch_runs_its_condition_against_the_full_kernel(tmp_path):
    aios = tree(tmp_path)
    result = launch(tmp_path, aios)
    assert result.returncode == 0, result.stdout + result.stderr
    full = ["n6conc", "n6wrong_user", "n6v2", "n6v3", "n6h0", "n6flood10",
            "n6flood50", "n6v4"]
    rows = {
        "barrier": ["n6conc"], "identity": ["n6wrong_user", "n6v2"],
        "visibility": ["n6v3"], "supersession": ["n6h0"],
        "forget_scope": ["n6h0"], "quota": ["n6flood10", "n6flood50"],
        "block_format": ["n6h0"], "block_order": ["n6h0"],
        "budget": ["n6h0"], "threshold": ["n6h0"],
        "consumer_config": ["n6v4"],
    }
    want = [f"kinh/{c}_kernel_shared" for c in full]
    for switch, conditions in rows.items():
        want += [f"kinh_{switch}/{c}_kernel_shared" for c in conditions]
    want.append("agent/n6v4_replicated_inhouse")
    assert cells(tmp_path) == sorted(want)


def test_the_ablated_kernel_and_harness_name_the_same_switch(tmp_path):
    """Each kernel runs ``--ablate <switch>`` (``none`` for the full
    kernel and the replicated reference), and its cells pass the same
    switch to the harness, whose pre-flight compares them; the flood
    conditions run on a kernel with the quota on, the others off."""
    aios = tree(tmp_path)
    result = launch(tmp_path, aios, ABLATE="barrier quota consumer_config")
    assert result.returncode == 0, result.stdout + result.stderr
    modes = [(line.split("--ablate ")[1],
              line.split("--write-quota ")[1].split()[0],
              "--kernel-memory on" in line)
             for line in lines(tmp_path, "mode.log")]
    assert modes == [
        ("none", "off", True),   # kinh: n6conc, n6v4
        ("none", "on", True),    # kinh: the floods
        ("barrier", "off", True),
        ("quota", "on", True),
        ("consumer_config", "off", True),
        ("none", "off", False),  # agent: replicated V4
    ]
    calls = lines(tmp_path, "harness.log")
    ablated = {c.split("--run-id ")[1].split()[0]:
               (c.split("--ablate ")[1].split()[0]
                if "--ablate " in c else None) for c in calls}
    assert ablated["a1-qwen-kinh_barrier-kernel_shared-n6conc"] == "barrier"
    assert ablated["a1-qwen-kinh_quota-kernel_shared-n6flood50"] == "quota"
    assert ablated["a1-qwen-kinh-kernel_shared-n6conc"] is None
    assert ablated["a1-qwen-agent-replicated_inhouse-n6v4"] is None
    assert all("--agents 6" in c and "--no-judge" in c for c in calls)
    v4 = [c for c in calls if "-n6v4" in c]
    assert all("--variants assistant_agent=V4" in c for c in v4)
    assert "kernel_memory_ops=0" in result.stdout


def test_the_smoke_runs_the_four_judge_free_switches_on_30_users(tmp_path):
    aios = tree(tmp_path)
    result = launch(tmp_path, aios, mode="smoke")
    assert result.returncode == 0, result.stdout + result.stderr
    assert cells(tmp_path) == sorted(
        [f"kinh/{c}_kernel_shared" for c in (
            "n6conc", "n6wrong_user", "n6flood10", "n6flood50", "n6h0")]
        + ["kinh_barrier/n6conc_kernel_shared",
           "kinh_identity/n6wrong_user_kernel_shared",
           "kinh_quota/n6flood10_kernel_shared",
           "kinh_quota/n6flood50_kernel_shared",
           "kinh_forget_scope/n6h0_kernel_shared"])
    assert all("--trials 30" in c for c in lines(tmp_path, "harness.log"))


def test_mem0_runs_the_same_cells_on_a_mem0_kernel(tmp_path):
    aios = tree(tmp_path)
    result = launch(tmp_path, aios, ABLATE="consumer_config",
                    BACKEND="mem0")
    assert result.returncode == 0, result.stdout + result.stderr
    assert cells(tmp_path) == ["agent/n6v4_replicated_mem0",
                               "kmem0/n6v4_kernel_shared",
                               "kmem0_consumer_config/n6v4_kernel_shared"]
    assert all("--provider mem0" in line
               for line in lines(tmp_path, "mode.log"))


def test_a_resume_skips_finished_cells_and_their_kernels(tmp_path):
    aios = tree(tmp_path)
    first = launch(tmp_path, aios, ABLATE="barrier",
                   SIM_FAIL_RUN="a1-qwen-kinh_barrier-kernel_shared-n6conc")
    assert first.returncode != 0
    (tmp_path / "mode.log").unlink()
    second = launch(tmp_path, aios, ABLATE="barrier")
    assert second.returncode == 0, second.stdout + second.stderr
    assert [line.split("--ablate ")[1]
            for line in lines(tmp_path, "mode.log")] == ["barrier"]


def test_an_unknown_switch_or_backend_is_refused(tmp_path):
    aios = tree(tmp_path)
    for extra in ({"ABLATE": "cache"}, {"BACKEND": "graphiti"}):
        result = launch(tmp_path, aios, **extra)
        assert result.returncode != 0
    assert not (tmp_path / "harness.log").exists()
