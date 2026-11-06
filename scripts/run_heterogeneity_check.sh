#!/bin/bash
# Subtask 10 functional check of the heterogeneity variants
# (docs/HETEROGENEITY.md): every locus x backend x H on Qwen, the judge
# disabled, the first TRIALS users of pilot_v1. No scored trial runs.
#   phase kmem0: Mem0 (infer), kernel memory on: kernel_shared
#   phase kinh:  in-house, kernel memory on: kernel_shared
#   phase agent: kernel memory off: replicated_mem0, replicated_inhouse,
#                native_mem0, native_inhouse; 0 kernel memory ops checked
# Each cell runs at H = 0, 1, 2 with the same --variant-seed, so cells
# pair by trial index. One fresh kernel per phase; config.yaml restored
# byte for byte at exit. Resumable. Run from the AIOS repo, detached:
#   bash scripts/run_heterogeneity_check.sh
# then: python -m benchmarks.shared_memory.heterogeneity_report <root>
set -u
AIOS="$(pwd)"
CEREBRUM="$AIOS/../Cerebrum"
CONFIG="aios/config/config.yaml"
SAVED="$(mktemp)"
cp "$CONFIG" "$SAVED"
OUTROOT="${OUTROOT:-results/heterogeneity_check}"
LOGS="$CEREBRUM/$OUTROOT/logs"
DATASET="${DATASET:-pilot_v1}"
TRIALS="${TRIALS:-5}"
MODEL="qwen2.5:7b:ollama"
RUN_PREFIX="${RUN_PREFIX:-h10}"
LEVELS="${LEVELS:-0 1 2}"
PHASES="${PHASES:-kmem0 kinh agent}"
VARIANT_SEED="${VARIANT_SEED:-20261106}"
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

start_kernel() {  # $1 = log name
    "$AIOS/.venv/bin/python" -m uvicorn runtime.launch:app \
        --host 127.0.0.1 --port 8000 > "$LOGS/kernel_$1.log" 2>&1 &
    KERNEL=$!
    until curl -s -m 2 localhost:8000/status > /dev/null; do
        kill -0 "$KERNEL" 2>/dev/null || { echo "kernel died"; exit 1; }
        sleep 2
    done
}

run_cell() {  # $1 = phase, $2 = method, $3 = level, [$4 = provider]
    local phase=$1 method=$2 level=$3 provider=${4:-}
    local cell="$OUTROOT/$phase/h${level}_$method"
    local file="$CEREBRUM/$cell/results_$method.json"
    cell_done "$file" && { echo "$(date) skip $phase $method H$level"; return 0; }
    local check=()
    [ -n "$provider" ] && check=(--provider "$provider")
    echo "$(date) start $phase $method H$level"
    (set -a; . "$AIOS/.env"; set +a
     export CEREBRUM_NATIVE_MEMORY_DIR="$CEREBRUM/.native_memory/$RUN_PREFIX"
     export CEREBRUM_REPLICATED_MEMORY_DIR="$CEREBRUM/.replicated_memory/$RUN_PREFIX"
     export AIOS_ROOT="$AIOS"
     cd "$CEREBRUM" && .venv/bin/python \
        -m benchmarks.shared_memory.run_evaluation \
        --dataset "$DATASET" --trials "$TRIALS" --method "$method" \
        ${check[@]+"${check[@]}"} --assistant-model "$MODEL" \
        --no-judge --heterogeneity "$level" --variant-seed "$VARIANT_SEED" \
        --run-id "$RUN_PREFIX-$phase-$method-h$level" \
        --output "$cell" > "$LOGS/${phase}_${method}_h$level.log" 2>&1) || {
        echo "$(date) FAILED $phase $method H$level"; exit 1;
    }
    cell_done "$file" || { echo "$(date) INCOMPLETE $phase $method H$level"; exit 1; }
    echo "$(date) done $phase $method H$level"
}

for phase in $PHASES; do
    case $phase in
        kmem0) mode --provider mem0 --kernel-memory on; provider=mem0
               methods="kernel_shared" ;;
        kinh)  mode --provider in-house --kernel-memory on; provider=in-house
               methods="kernel_shared" ;;
        agent) mode --provider mem0 --kernel-memory off; provider=""
               methods="replicated_mem0 replicated_inhouse native_mem0 native_inhouse" ;;
        *) echo "unknown phase $phase"; exit 1 ;;
    esac
    start_kernel "$phase"
    for level in $LEVELS; do
        for method in $methods; do
            run_cell "$phase" "$method" "$level" "$provider"
        done
    done
    if [ "$phase" = agent ]; then
        ops=$(grep -cE "$MEMORY_OPS" "$LOGS/kernel_$phase.log")
        echo "$(date) $phase kernel_memory_ops=$ops"
        [ "$ops" -eq 0 ] || { echo "$(date) MEMORY OPS IN KERNEL LOG"; exit 1; }
    fi
    stop_kernel
done
echo "$(date) HETEROGENEITY CHECK DONE"
