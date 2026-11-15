#!/bin/bash
# Subtask 16: the pilot_v1 smoke on Graphiti (docs/GRAPHITI_BACKEND.md),
# the locus pattern of the Subtask 11 pilot (docs/PILOT.md) on a third
# backend; BACKEND=amem (Subtask 17, docs/AMEM_BACKEND.md;
# scripts/run_pilot_v1_amem.sh) runs it on A-MEM. For each model:
#   phase kgra:      Graphiti, kernel memory on: kernel_shared
#   phase agent_gra: a Graphiti kernel with memory off: replicated_graphiti,
#                    native_graphiti; 0 kernel memory ops checked
#   (A-MEM: phases kamem and agent_amem, methods replicated_amem and
#   native_amem.)
# at H = 0 and 2 (LEVELS) on pilot_v1's 30 users, variants from the
# committed schedule (benchmarks/shared_memory/data/pilot_v1_schedule.json),
# the greedy judge, fixed decoding.
#
# As scripts/run_pilot_v1.sh, but on the current code, not the frozen
# pilot-v1-code tag (which has no Graphiti): both repos must have no
# tracked change, and every finished cell must record exactly the current
# commits (no -dirty) and have no failed trial; otherwise the driver
# stops. One fresh kernel per model per phase, on a port that must be
# free first; config.yaml restored byte for byte at exit. Resumable.
# RUN_PREFIX and OUTROOT are required, new for every run (known issue
# 36). METHODS, when set, runs only those methods' cells (Subtask 17's
# Decision 2 re-ran native_graphiti).
# ARCHIVE, when set, is a new directory the run's OUTROOT (results, logs,
# and the driver's own log when written there) is copied into at the
# end, with SHA256SUMS, through scripts/archive_artifacts.py, which
# refuses the copy when a file holds a configured key value: then the
# driver fails and nothing is copied (Subtask 17). The archived driver
# log ends before the archive's own lines.
# Run from the AIOS repo, detached, the driver's log in OUTROOT:
#   OUT=results/pilot_v1_graphiti; mkdir -p ../Cerebrum/$OUT
#   RUN_PREFIX=pg16 OUTROOT=$OUT ARCHIVE=../repo-artifacts/Cerebrum/pilot_v1_graphiti nohup bash scripts/run_pilot_v1_graphiti.sh > ../Cerebrum/$OUT/driver.log 2>&1 &
set -u
AIOS="$(pwd)"
CEREBRUM="$AIOS/../Cerebrum"
CONFIG="aios/config/config.yaml"
[ -n "${RUN_PREFIX:-}" ] || {
    echo "set RUN_PREFIX, new for every run (known issue 36)" >&2; exit 1; }
[ -n "${OUTROOT:-}" ] || {
    echo "set OUTROOT, the run's own (a resume keeps it)" >&2; exit 1; }
LOGS="$CEREBRUM/$OUTROOT/logs"
[ -z "${ARCHIVE:-}" ] || [ ! -e "$ARCHIVE" ] || {
    echo "$ARCHIVE exists: set a new ARCHIVE" >&2; exit 1; }
DATASET="pilot_v1"
SCHEDULE="benchmarks/shared_memory/data/pilot_v1_schedule.json"
TRIALS="${TRIALS:-30}"
JUDGE="gpt-5.4:azure"
MODELS="${MODELS:-qwen}"
LEVELS="${LEVELS:-0 2}"
BACKEND="${BACKEND:-graphiti}"
case "$BACKEND" in  # the kernel phase and the agent phase
    graphiti) KPHASE=kgra; APHASE=agent_gra ;;
    amem) KPHASE=kamem; APHASE=agent_amem ;;
    *) echo "BACKEND must be graphiti or amem" >&2; exit 1 ;;
esac
MEMORY_OPS='add_memory: agent=|retrieve_memory result|Injection pipeline|Stored conversation memory|Injected [0-9]+ memories|MEMORY QUERY RECEIVED|forget_memory: agent=|list_memory: agent='
KERNEL=""

clean() {  # $1 = repo: prints HEAD, or fails on tracked changes
    git -C "$1" diff --quiet HEAD || {
        echo "$1 has tracked changes" >&2; return 1; }
    git -C "$1" rev-parse HEAD
}
HARNESS_COMMIT=$(clean "$CEREBRUM") || exit 1
KERNEL_COMMIT=$(clean "$AIOS") || exit 1

SAVED="$(mktemp)"
cp "$CONFIG" "$SAVED"
mkdir -p "$LOGS"
stop_kernel() {
    [ -n "$KERNEL" ] && { kill "$KERNEL" 2>/dev/null; wait "$KERNEL" 2>/dev/null; }
    KERNEL=""
}
finish() { stop_kernel; cp "$SAVED" "$CONFIG"; rm -f "$SAVED"; }
trap finish EXIT
# A 60 s write barrier, as benchmark v2's: the kernel's cost read waits on
# it for the chat turn it stores in the background, and a Graphiti turn
# takes longer than the config's 5 s (Subtask 16).
mode() {
    "$AIOS/.venv/bin/python" scripts/set_memory_mode.py "$CONFIG" "$@" \
        --barrier-timeout-ms 60000
}
cell_done() {
    python3 "$AIOS/scripts/pilot_cell_done.py" "$1" "$TRIALS" --strict \
        --commit "$HARNESS_COMMIT" --kernel-commit "$KERNEL_COMMIT"
}
assistant_of() {
    case "$1" in
        gpt4o) echo "gpt-4o:azure" ;; qwen) echo "qwen2.5:7b:ollama" ;;
        *) echo "unknown model $1" >&2; exit 1 ;;
    esac
}

KLOG=""
start_kernel() {  # $1 = log name; a resume never overwrites a log
    if lsof -nP -iTCP:8000 -sTCP:LISTEN > /dev/null 2>&1; then
        echo "port 8000 is in use: stop that process first" >&2; exit 1
    fi
    KLOG="$LOGS/kernel_$1_$(date +%Y%m%dT%H%M%S).log"
    "$AIOS/.venv/bin/python" -m uvicorn runtime.launch:app \
        --host 127.0.0.1 --port 8000 > "$KLOG" 2>&1 &
    KERNEL=$!
    until curl -s -m 2 localhost:8000/status > /dev/null; do
        kill -0 "$KERNEL" 2>/dev/null || { echo "kernel died"; exit 1; }
        sleep 2
    done
}

cell_path() { echo "$OUTROOT/$1/$2/h$3_$4"; }  # model phase level method

run_cell() {  # $1 = model, $2 = phase, $3 = method, $4 = level, [$5 = provider]
    local model=$1 phase=$2 method=$3 level=$4 provider=${5:-}
    local cell; cell=$(cell_path "$model" "$phase" "$level" "$method")
    local file="$CEREBRUM/$cell/results_$method.json"
    local name="${model}_${phase}_${method}_h$level"
    cell_done "$file" && { echo "$(date) skip $name"; return 0; }
    local check=()
    [ -n "$provider" ] && check=(--provider "$provider")
    echo "$(date) start $name"
    (set -a; . "$AIOS/.env"; set +a
     export CEREBRUM_NATIVE_MEMORY_DIR="$CEREBRUM/.native_memory/$RUN_PREFIX"
     export CEREBRUM_REPLICATED_MEMORY_DIR="$CEREBRUM/.replicated_memory/$RUN_PREFIX"
     export AIOS_ROOT="$AIOS"
     cd "$CEREBRUM" && .venv/bin/python \
        -m benchmarks.shared_memory.run_evaluation \
        --dataset "$DATASET" --trials "$TRIALS" --method "$method" \
        ${check[@]+"${check[@]}"} --assistant-model "$(assistant_of "$model")" \
        --judge-model "$JUDGE" --heterogeneity "$level" \
        --schedule "$SCHEDULE" \
        --run-id "$RUN_PREFIX-$model-$phase-$method-h$level" \
        --output "$cell" > "$LOGS/$name.log" 2>&1) || {
        echo "$(date) FAILED $name"; exit 1;
    }
    cell_done "$file" || { echo "$(date) INCOMPLETE $name"; exit 1; }
    echo "$(date) done $name"
}

phase_needed() {  # model phase methods...: true if a cell is unfinished
    local model=$1 phase=$2; shift 2
    for level in $LEVELS; do
        for method in "$@"; do
            cell_done "$CEREBRUM/$(cell_path "$model" "$phase" "$level" "$method")/results_$method.json" || return 0
        done
    done
    return 1
}

for model in $MODELS; do
    for phase in ${PHASES:-$KPHASE $APHASE}; do
        case $phase in
            "$KPHASE") mode --provider "$BACKEND" --kernel-memory on
                  provider=$BACKEND; methods="kernel_shared" ;;
            "$APHASE") mode --provider "$BACKEND" --kernel-memory off
                  provider=""
                  methods="replicated_$BACKEND native_$BACKEND" ;;
            *) echo "unknown phase $phase" >&2; exit 1 ;;
        esac
        if [ -n "${METHODS:-}" ]; then  # only these methods' cells
            kept=""
            for method in $methods; do
                case " $METHODS " in *" $method "*) kept="$kept $method" ;; esac
            done
            methods=$kept
        fi
        [ -n "$methods" ] || { echo "$(date) skip $model $phase: no method in METHODS"; continue; }
        phase_needed "$model" "$phase" $methods || { echo "$(date) skip $model $phase"; continue; }
        start_kernel "${model}_$phase"
        for level in $LEVELS; do
            for method in $methods; do
                run_cell "$model" "$phase" "$method" "$level" "$provider"
            done
        done
        if [ "$phase" = "$APHASE" ]; then
            ops=$(cat "$LOGS"/kernel_${model}_${APHASE}_2*.log | grep -cE "$MEMORY_OPS")
            echo "$(date) $model $phase kernel_memory_ops=$ops"
            [ "$ops" -eq 0 ] || { echo "$(date) MEMORY OPS IN KERNEL LOG"; exit 1; }
        fi
        stop_kernel
    done
done
echo "$(date) PILOT V1 GRAPHITI DONE"
if [ -n "${ARCHIVE:-}" ]; then
    echo "$(date) archiving $OUTROOT to $ARCHIVE"
    "$AIOS/.venv/bin/python" scripts/archive_artifacts.py --root "$AIOS" \
        --sums --dest "$ARCHIVE" "$CEREBRUM/$OUTROOT"/* || {
        echo "$(date) ARCHIVE REFUSED: nothing copied"; exit 1; }
fi
