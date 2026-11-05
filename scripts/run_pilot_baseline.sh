#!/bin/bash
# Subtask 9 re-baseline on pilot_v1 (the first 30 users of users_v1):
# every cell scores the same users, so cells pair by trial index.
#   phase kmem0: Mem0 (infer), kernel memory on: kernel_shared,
#                kernel_private
#   phase kinh:  in-house, kernel memory on: kernel_shared, kernel_private
#   phase agent: kernel memory off: replicated_mem0, replicated_inhouse,
#                native_mem0, native_inhouse, and the two memory-less
#                baselines naive_concat and vanilla_rag (with kernel
#                memory on the kernel would store and extract their
#                chat turn); 0 kernel memory ops checked
# One fresh kernel per phase and model. Sets memory.provider and the
# kernel memory mode between kernels, never during one, and restores
# config.yaml byte for byte at exit. Resumable: finished cells are
# skipped. Run from the AIOS repo, detached:
#   MODELS="gpt4o qwen" bash scripts/run_pilot_baseline.sh
set -u
AIOS="$(pwd)"
CEREBRUM="$AIOS/../Cerebrum"
CONFIG="aios/config/config.yaml"
SAVED="$(mktemp)"
cp "$CONFIG" "$SAVED"
OUTROOT="${OUTROOT:-results/pilot_v1}"
LOGS="$CEREBRUM/$OUTROOT/logs"
DATASET="${DATASET:-pilot_v1}"
TRIALS="${TRIALS:-30}"
JUDGE="gpt-5.4:azure"
RUN_PREFIX="${RUN_PREFIX:-p9}"
MODELS="${MODELS:-gpt4o qwen llama}"
PHASES="${PHASES:-kmem0 kinh agent}"
MEMORY_OPS='add_memory: agent=|retrieve_memory result|Injection pipeline|Stored conversation memory|Injected [0-9]+ memories'
KERNEL=""
mkdir -p "$LOGS"

stop_kernel() {
    [ -n "$KERNEL" ] && { kill "$KERNEL" 2>/dev/null; wait "$KERNEL" 2>/dev/null; }
    KERNEL=""
}
finish() { stop_kernel; cp "$SAVED" "$CONFIG"; rm -f "$SAVED"; }
trap finish EXIT
mode() { "$AIOS/.venv/bin/python" scripts/set_memory_mode.py "$CONFIG" "$@"; }
cell_done() { python3 "$AIOS/scripts/pilot_cell_done.py" "$1" "$TRIALS"; }
assistant_of() {
    case "$1" in
        gpt4o) echo "gpt-4o:azure" ;; llama) echo "llama3.1:8b:ollama" ;;
        qwen) echo "qwen2.5:7b:ollama" ;; *) echo "unknown model $1" >&2; exit 1 ;;
    esac
}

start_kernel() {  # $1 = log name
    "$AIOS/.venv/bin/python" -m uvicorn runtime.launch:app \
        --host 127.0.0.1 --port 8000 > "$LOGS/kernel_$1.log" 2>&1 &
    KERNEL=$!
    until curl -s -m 2 localhost:8000/status > /dev/null; do
        kill -0 "$KERNEL" 2>/dev/null || { echo "kernel died"; exit 1; }
        sleep 2
    done
}

run_cell() {  # $1 = phase, $2 = method, $3 = model, [$4 = provider]
    local phase=$1 method=$2 model=$3 provider=${4:-}
    local cell="$OUTROOT/$phase/${model}_$method"
    local file="$CEREBRUM/$cell/results_$method.json"
    cell_done "$file" && { echo "$(date) skip $phase $method $model"; return 0; }
    local check=()
    [ -n "$provider" ] && check=(--provider "$provider")
    echo "$(date) start $phase $method $model"
    (set -a; . "$AIOS/.env"; set +a
     export CEREBRUM_NATIVE_MEMORY_DIR="$CEREBRUM/.native_memory/$RUN_PREFIX"
     export CEREBRUM_REPLICATED_MEMORY_DIR="$CEREBRUM/.replicated_memory/$RUN_PREFIX"
     export AIOS_ROOT="$AIOS"
     cd "$CEREBRUM" && .venv/bin/python \
        -m benchmarks.shared_memory.run_evaluation \
        --dataset "$DATASET" --trials "$TRIALS" --method "$method" \
        ${check[@]+"${check[@]}"} --assistant-model "$(assistant_of "$model")" \
        --judge-model "$JUDGE" --run-id "$RUN_PREFIX-$phase-$method-$model" \
        --output "$cell" > "$LOGS/${phase}_${method}_${model}.log" 2>&1) || {
        echo "$(date) FAILED $phase $method $model"; exit 1;
    }
    cell_done "$file" || { echo "$(date) INCOMPLETE $phase $method $model"; exit 1; }
    echo "$(date) done $phase $method $model"
}

phase_needed() {  # $1 = phase, rest = methods; true if a cell is unfinished
    local phase=$1 model=$2; shift 2
    for method in "$@"; do
        cell_done "$CEREBRUM/$OUTROOT/$phase/${model}_$method/results_$method.json" || return 0
    done
    return 1
}

for phase in $PHASES; do
    case $phase in
        kmem0) mode --provider mem0 --kernel-memory on; provider=mem0
               methods="kernel_shared kernel_private" ;;
        kinh)  mode --provider in-house --kernel-memory on; provider=in-house
               methods="kernel_shared kernel_private" ;;
        agent) mode --provider mem0 --kernel-memory off; provider=""
               methods="replicated_mem0 replicated_inhouse native_mem0 native_inhouse naive_concat vanilla_rag" ;;
        *) echo "unknown phase $phase"; exit 1 ;;
    esac
    for model in $MODELS; do
        phase_needed "$phase" "$model" $methods || { echo "$(date) skip $phase $model"; continue; }
        start_kernel "${phase}_$model"
        for method in $methods; do
            run_cell "$phase" "$method" "$model" "$provider"
        done
        if [ "$phase" = agent ]; then
            ops=$(grep -cE "$MEMORY_OPS" "$LOGS/kernel_${phase}_$model.log")
            echo "$(date) $phase $model kernel_memory_ops=$ops"
            [ "$ops" -eq 0 ] || { echo "$(date) MEMORY OPS IN KERNEL LOG"; exit 1; }
        fi
        stop_kernel
    done
done
echo "$(date) PILOT BASELINE DONE"
