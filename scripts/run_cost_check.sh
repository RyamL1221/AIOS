#!/bin/bash
# Subtask 7 cost check: 10 GPT-4o trials of one condition with the cost
# instrumentation, then scripts/cost_check.py over the results. The
# kernel's memory mode must match the condition (kernel_shared: auto_inject
# and auto_extract true; native_mem0: both false); the harness pre-flight
# refuses otherwise. Run from the AIOS repo, detached:
#   METHOD=kernel_shared bash scripts/run_cost_check.sh
set -u
: "${METHOD:?set METHOD to kernel_shared or native_mem0}"
AIOS="$(pwd)"
CEREBRUM="$AIOS/../Cerebrum"
OUT="results/cost_check"
LOGS="$CEREBRUM/$OUT/logs"
TRIALS="${TRIALS:-10}"
JUDGE="gpt-5.4:azure"
RUN_PREFIX="${RUN_PREFIX:-cc7-$METHOD}"
cell="$OUT/gpt4o_$METHOD"
mkdir -p "$LOGS"

stop_kernel() {
    kill "$KERNEL" 2>/dev/null
    wait "$KERNEL" 2>/dev/null
}

"$AIOS/.venv/bin/python" -m uvicorn runtime.launch:app \
    --host 127.0.0.1 --port 8000 > "$LOGS/kernel_$METHOD.log" 2>&1 &
KERNEL=$!
trap stop_kernel EXIT
until curl -s -m 2 localhost:8000/status > /dev/null; do
    kill -0 "$KERNEL" 2>/dev/null || { echo "kernel died"; exit 1; }
    sleep 2
done
echo "$(date) start $METHOD"
# Native agents call Mem0's LLM (through LiteLLM) themselves, with the
# kernel's Azure variables; exported to the harness only.
(set -a; . "$AIOS/.env"; set +a
 export CEREBRUM_NATIVE_MEMORY_DIR="$CEREBRUM/.native_memory/$RUN_PREFIX"
 cd "$CEREBRUM" && .venv/bin/python \
    -m benchmarks.shared_memory.run_evaluation \
    --trials "$TRIALS" --method "$METHOD" \
    --assistant-model gpt-4o:azure --judge-model "$JUDGE" \
    --run-id "$RUN_PREFIX" --output "$cell" \
    > "$OUT/logs/$METHOD.log" 2>&1) || { echo "$(date) FAILED"; exit 1; }
stop_kernel
trap - EXIT
"$AIOS/.venv/bin/python" scripts/cost_check.py \
    "$CEREBRUM/$cell/results_$METHOD.json" --method "$METHOD"
echo "$(date) DONE"
