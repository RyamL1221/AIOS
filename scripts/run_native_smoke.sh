#!/bin/bash
# Subtask 6 behavior check: 30 trials per model of one agent-managed
# condition (docs/NATIVE_USAGE.md), one fresh kernel per model. The
# kernel must run with memory.auto_inject and auto_extract false; the
# harness pre-flight refuses otherwise. Afterwards each kernel log is
# checked for memory operations, which must be absent.
# Run from the AIOS repo, detached:
#   METHOD=native_mem0 bash scripts/run_native_smoke.sh
set -u
: "${METHOD:?set METHOD to native_mem0 or native_inhouse}"
AIOS="$(pwd)"
CEREBRUM="$AIOS/../Cerebrum"
OUT="results/native_smoke/$METHOD"
LOGS="$CEREBRUM/$OUT/logs"
TRIALS="${TRIALS:-30}"
JUDGE="gpt-5.4:azure"
RUN_PREFIX="${RUN_PREFIX:-ns6-$METHOD}"
# The kernel log lines a memory operation writes.
MEMORY_OPS='add_memory: agent=|retrieve_memory result|Injection pipeline|Stored conversation memory|Injected [0-9]+ memories'

case "$METHOD" in
    native_mem0|native_inhouse) ;;
    *) echo "METHOD must be native_mem0 or native_inhouse"; exit 1 ;;
esac
mkdir -p "$LOGS"

cell_done() {
    python3 "$AIOS/scripts/revalidation_cell_done.py" "$1" "$TRIALS"
}

stop_kernel() {
    kill "$KERNEL" 2>/dev/null
    wait "$KERNEL" 2>/dev/null
}

for entry in "gpt4o gpt-4o:azure" "llama llama3.1:8b:ollama" \
        "qwen qwen2.5:7b:ollama"; do
    read -r model assistant <<<"$entry"
    cell="$OUT/${model}_$METHOD"
    if cell_done "$CEREBRUM/$cell/results_$METHOD.json"; then
        echo "$(date) skip $model"
        continue
    fi
    "$AIOS/.venv/bin/python" -m uvicorn runtime.launch:app \
        --host 127.0.0.1 --port 8000 > "$LOGS/kernel_$model.log" 2>&1 &
    KERNEL=$!
    trap stop_kernel EXIT
    until curl -s -m 2 localhost:8000/status > /dev/null; do
        kill -0 "$KERNEL" 2>/dev/null || { echo "kernel died"; exit 1; }
        sleep 2
    done
    echo "$(date) start $model"
    # The agents call Mem0's internal LLM themselves, with the kernel's
    # Azure variables; exported to the harness only.
    (set -a; . "$AIOS/.env"; set +a
     export CEREBRUM_NATIVE_MEMORY_DIR="$CEREBRUM/.native_memory/$RUN_PREFIX"
     cd "$CEREBRUM" && .venv/bin/python \
        -m benchmarks.shared_memory.run_evaluation \
        --trials "$TRIALS" --method "$METHOD" \
        --assistant-model "$assistant" --judge-model "$JUDGE" \
        --run-id "$RUN_PREFIX-$model" --output "$cell" \
        > "$OUT/logs/${model}.log" 2>&1) || {
        echo "$(date) FAILED $model"; exit 1;
    }
    cell_done "$CEREBRUM/$cell/results_$METHOD.json" || {
        echo "$(date) INCOMPLETE $model"; exit 1;
    }
    ops=$(grep -cE "$MEMORY_OPS" "$LOGS/kernel_$model.log")
    echo "$(date) done $model kernel_memory_ops=$ops"
    [ "$ops" -eq 0 ] || { echo "$(date) MEMORY OPS IN KERNEL LOG $model"; exit 1; }
    stop_kernel
    trap - EXIT
done
echo "$(date) ALL DONE"
