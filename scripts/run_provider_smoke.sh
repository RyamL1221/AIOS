#!/bin/bash
# Subtask 5 behavior check: 30 kernel_shared trials per model on one
# memory provider, one fresh kernel per model. The provider is whatever
# aios/config/config.yaml names; PROVIDER must match it and the harness
# checks the live kernel (--provider). Resumable like run_revalidation.sh.
# Run from the AIOS repo, detached:  PROVIDER=mem0 bash scripts/run_provider_smoke.sh
set -u
: "${PROVIDER:?set PROVIDER to memory.provider in config.yaml}"
AIOS="$(pwd)"
CEREBRUM="$AIOS/../Cerebrum"
OUT="results/provider_smoke/$PROVIDER"
LOGS="$CEREBRUM/$OUT/logs"
TRIALS="${TRIALS:-30}"
JUDGE="gpt-5.4:azure"
RUN_PREFIX="${RUN_PREFIX:-ps5-$PROVIDER}"
mkdir -p "$LOGS"

configured=$("$AIOS/.venv/bin/python" -c 'import sys, yaml; print(yaml.safe_load(open(sys.argv[1]))["memory"]["provider"])' aios/config/config.yaml)
if [ "$configured" != "$PROVIDER" ]; then
    echo "config.yaml names provider $configured, not $PROVIDER"; exit 1
fi

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
    cell="$OUT/${model}_kernel_shared"
    if cell_done "$CEREBRUM/$cell/results_kernel_shared.json"; then
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
    (cd "$CEREBRUM" && .venv/bin/python \
        -m benchmarks.shared_memory.run_evaluation \
        --trials "$TRIALS" --method kernel_shared --provider "$PROVIDER" \
        --assistant-model "$assistant" --judge-model "$JUDGE" \
        --run-id "$RUN_PREFIX-$model" --output "$cell" \
        > "$OUT/logs/${model}.log" 2>&1) || {
        echo "$(date) FAILED $model"; exit 1;
    }
    cell_done "$CEREBRUM/$cell/results_kernel_shared.json" || {
        echo "$(date) INCOMPLETE $model"; exit 1;
    }
    echo "$(date) done $model"
    stop_kernel
    trap - EXIT
done
echo "$(date) ALL DONE"
