"""The stress dimensions' driver (scripts/run_stress_s18.sh; NeurIPS
Subtask 18, docs/STRESS_DIMENSIONS.md): each condition's harness flags,
the write quota on in the flood phases only, the load conditions on the
kernel locus only, the smoke's in-house cells, and config.yaml restored.

The real script runs in the stub tree of ``test_bench_v2_driver``, with
a harness stub that records its arguments."""
import os
import subprocess
from pathlib import Path

from tests.modules.memory.test_bench_v2_driver import executable, tree

DRIVER = Path(__file__).resolve().parents[3] / "scripts" / "run_stress_s18.sh"

# The Cerebrum venv's python, as the harness: records its arguments, one
# line per cell, then writes the cell's results file.
HARNESS = """#!/bin/bash
echo "$*" >> "$SIM_ARGS_LOG"
while [ $# -gt 0 ]; do
    case $1 in
        --method) method=$2; shift ;;
        --output) out=$2; shift ;;
    esac
    shift
done
mkdir -p "$out" && echo done > "$out/results_$method.json"
"""


def launch(tmp_path: Path, mode: str, phases: str, conditions: str):
    aios = tree(tmp_path)
    executable(tmp_path / "Cerebrum" / ".venv" / "bin" / "python", HARNESS)
    args_log, mode_log = tmp_path / "args.log", tmp_path / "mode.log"
    env = {
        **os.environ,
        "PATH": f"{aios.parent / 'bin'}:{os.environ['PATH']}",
        "MODE": mode, "MODELS": "qwen", "PHASES": phases,
        "CONDITIONS": conditions, "RUN_PREFIX": "t1",
        "OUTROOT": "results/sim", "SIM_ARGS_LOG": str(args_log),
        "SIM_MODE_LOG": str(mode_log),
    }
    run = subprocess.run(["bash", str(DRIVER)], cwd=aios, env=env,
                         capture_output=True, text=True, timeout=120)
    args = args_log.read_text().splitlines() if args_log.exists() else []
    modes = mode_log.read_text().splitlines() if mode_log.exists() else []
    return aios, run, args, modes


def cell(args, method, flag):
    return [line for line in args if f"--method {method} " in line
            and flag in line]


def test_each_condition_runs_with_its_flags(tmp_path):
    aios, run, args, modes = launch(
        tmp_path, "functional", "kinh agent",
        "n3h2 n12h0 n6conc n6wrong_user n6load4")
    assert run.returncode == 0, run.stdout + run.stderr
    assert cell(args, "kernel_shared", "--agents 3 --heterogeneity 2")
    assert cell(args, "native_mem0", "--agents 12 --heterogeneity 0")
    assert cell(args, "replicated_inhouse",
                "--agents 6 --concurrency concurrent")
    assert cell(args, "native_inhouse", "--agents 6 --fault wrong_user")
    load = cell(args, "kernel_shared", "--agents 6 --load 4")
    assert load and "--trials 16" in load[0]
    assert not [line for line in args if "--load" in line
                and "--method kernel_shared" not in line]
    assert all("--no-judge" in line for line in args)
    assert all("--write-quota off" in m for m in modes)
    assert (aios / "aios" / "config" / "config.yaml").read_text() == \
        "memory: {}\n"


def test_the_floods_run_in_the_quota_phases_only(tmp_path):
    _, run, args, modes = launch(
        tmp_path, "functional", "kinh kinh_q agent_q",
        "n6h0 n6flood10 n6flood50")
    assert run.returncode == 0, run.stdout + run.stderr
    floods = [line for line in args if "--fault flood" in line]
    assert len(floods) == 2 + 2 * 4  # kinh_q, then agent_q's four methods
    assert not [line for line in args if "--fault flood" not in line
                and "n6h0" not in line and "--heterogeneity 0" not in line]
    quota = {m.split("--provider ")[1].split()[0] + (
        " on" if "--write-quota on" in m else " off") for m in modes}
    assert quota == {"in-house off", "in-house on", "mem0 on"}


def test_the_smoke_runs_the_in_house_cells(tmp_path):
    _, run, args, _ = launch(tmp_path, "smoke", "kinh agent",
                             "n6h0 n6conc")
    assert run.returncode == 0, run.stdout + run.stderr
    methods = {line.split("--method ")[1].split()[0] for line in args}
    assert methods == {"kernel_shared", "replicated_inhouse",
                       "native_inhouse"}
    assert all("--trials 30" in line for line in args)
