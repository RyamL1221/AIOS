#!/bin/bash
# Run the Subtask 3 re-validation: kernel_shared and mem0_default, 150
# trials each, on three models, one fresh kernel per model. Resumable: a
# cell whose results file already holds every trial is skipped. Stops at
# the first cell that fails. Run from the AIOS repo, detached.
set -u
AIOS="$(pwd)"
CEREBRUM="$AIOS/../Cerebrum"
OUT="results/revalidation"
LOGS="$CEREBRUM/$OUT/logs"
TRIALS=150
JUDGE="gpt-5.4:azure"
# A re-run needs its own prefix: user ids embed the run id, and a reused
# id could land a new trial on an invalid run's memories.
RUN_PREFIX="${RUN_PREFIX:-reval}"
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
    if cell_done "$CEREBRUM/$OUT/${model}_kernel_shared/results_kernel_shared.json" \
        && cell_done "$CEREBRUM/$OUT/${model}_mem0_default/results_mem0_default.json"; then
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
    for method in kernel_shared mem0_default; do
        cell="$OUT/${model}_$method"
        if cell_done "$CEREBRUM/$cell/results_$method.json"; then
            echo "$(date) skip $model $method"
            continue
        fi
        echo "$(date) start $model $method"
        (cd "$CEREBRUM" && .venv/bin/python \
            -m benchmarks.shared_memory.run_evaluation \
            --trials "$TRIALS" --method "$method" \
            --assistant-model "$assistant" --judge-model "$JUDGE" \
            --run-id "$RUN_PREFIX-$model-$method" --output "$cell" \
            > "$OUT/logs/${model}_$method.log" 2>&1) || {
            echo "$(date) FAILED $model $method"; exit 1;
        }
        cell_done "$CEREBRUM/$cell/results_$method.json" || {
            echo "$(date) INCOMPLETE $model $method"; exit 1;
        }
        echo "$(date) done $model $method"
    done
    stop_kernel
    trap - EXIT
done
echo "$(date) ALL DONE"
