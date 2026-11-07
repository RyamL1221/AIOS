#!/bin/bash
# Subtask 11: the pre-registered locus x heterogeneity pilot
# (docs/PILOT.md). For each model, Qwen first, then GPT-4o:
#   phase kmem0: Mem0 (infer), kernel memory on: kernel_shared
#   phase kinh:  in-house, kernel memory on: kernel_shared
#   phase agent: kernel memory off: replicated_mem0, replicated_inhouse,
#                native_mem0, native_inhouse; 0 kernel memory ops checked
# at H = 0, 1, 2 on pilot_v1's 30 users, variants from the committed
# schedule (benchmarks/shared_memory/data/pilot_v1_schedule.json), the
# greedy judge, fixed decoding. 18 cells, 540 trials per model.
#
# Frozen code: both repos must be at the pilot-v1-code tag with no
# tracked change, and every finished cell must record exactly those
# commits (no -dirty) and have no failed trial; otherwise the driver
# stops. One fresh kernel per model per phase; config.yaml restored byte
# for byte at exit. Resumable. Run from the AIOS repo, detached:
#   nohup bash scripts/run_pilot_v1.sh > ../repo-artifacts/Cerebrum/pilot_v1_driver.log 2>&1 &
set -u
AIOS="$(pwd)"
CEREBRUM="$AIOS/../Cerebrum"
CONFIG="aios/config/config.yaml"
TAG="pilot-v1-code"
OUTROOT="${OUTROOT:-results/pilot_v1_hetero}"
LOGS="$CEREBRUM/$OUTROOT/logs"
DATASET="pilot_v1"
SCHEDULE="benchmarks/shared_memory/data/pilot_v1_schedule.json"
TRIALS=30
JUDGE="gpt-5.4:azure"
RUN_PREFIX="${RUN_PREFIX:-pv1}"
MODELS="${MODELS:-qwen gpt4o}"
LEVELS="0 1 2"
MEMORY_OPS='add_memory: agent=|retrieve_memory result|Injection pipeline|Stored conversation memory|Injected [0-9]+ memories'
KERNEL=""

frozen() {  # $1 = repo: prints the tag's commit, or fails
    local tagged head
    tagged=$(git -C "$1" rev-parse "$TAG^{commit}" 2>/dev/null) || {
        echo "no $TAG tag in $1" >&2; return 1; }
    head=$(git -C "$1" rev-parse HEAD)
    [ "$head" = "$tagged" ] || { echo "$1 HEAD is not $TAG" >&2; return 1; }
    git -C "$1" diff --quiet HEAD || { echo "$1 has tracked changes" >&2; return 1; }
    echo "$tagged"
}
HARNESS_COMMIT=$(frozen "$CEREBRUM") || exit 1
KERNEL_COMMIT=$(frozen "$AIOS") || exit 1

SAVED="$(mktemp)"
cp "$CONFIG" "$SAVED"
mkdir -p "$LOGS"
stop_kernel() {
    [ -n "$KERNEL" ] && { kill "$KERNEL" 2>/dev/null; wait "$KERNEL" 2>/dev/null; }
    KERNEL=""
}
finish() { stop_kernel; cp "$SAVED" "$CONFIG"; rm -f "$SAVED"; }
trap finish EXIT
mode() { "$AIOS/.venv/bin/python" scripts/set_memory_mode.py "$CONFIG" "$@"; }
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
    for phase in kmem0 kinh agent; do
        case $phase in
            kmem0) mode --provider mem0 --kernel-memory on; provider=mem0
                   methods="kernel_shared" ;;
            kinh)  mode --provider in-house --kernel-memory on; provider=in-house
                   methods="kernel_shared" ;;
            agent) mode --provider mem0 --kernel-memory off; provider=""
                   methods="replicated_mem0 replicated_inhouse native_mem0 native_inhouse" ;;
        esac
        phase_needed "$model" "$phase" $methods || { echo "$(date) skip $model $phase"; continue; }
        start_kernel "${model}_$phase"
        for level in $LEVELS; do
            for method in $methods; do
                run_cell "$model" "$phase" "$method" "$level" "$provider"
            done
        done
        if [ "$phase" = agent ]; then
            ops=$(grep -cE "$MEMORY_OPS" "$KLOG")
            echo "$(date) $model $phase kernel_memory_ops=$ops"
            [ "$ops" -eq 0 ] || { echo "$(date) MEMORY OPS IN KERNEL LOG"; exit 1; }
        fi
        stop_kernel
    done
done
echo "$(date) PILOT V1 DONE"
