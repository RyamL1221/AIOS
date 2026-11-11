#!/bin/bash
# Subtasks 14 and 15: benchmark v2 runs (docs/BENCHMARK_V2.md,
# "Functional check and smoke"). For each model:
#   phase kmem0: Mem0 (infer), kernel injection on, extraction off:
#                kernel_shared
#   phase kinh:  in-house, kernel injection on, extraction off:
#                kernel_shared
#   phase agent: kernel memory off: replicated_mem0, replicated_inhouse,
#                native_mem0, native_inhouse; 0 kernel memory ops checked
#   phases kmem0_ns, kinh_ns, agent_ns: the same kernels with
#                memory.supersession off, for the no_supersession control
#                (kernel_shared; replicated_mem0, replicated_inhouse)
# Every phase runs with session ages on (memory.block_recency true, unit
# session), the write barrier at 60 s, k 10 and a 300-token budget, set
# through set_memory_mode.py; a probe writes nothing (Amendment 3: the
# kernel's auto_extract is off, the agents skip their probe writes);
# supersession is exclude, off in the _ns phases (Amendment 4); the
# harness's pre-flight refuses any other setting (supersession only in
# kernel and replicated cells: native runs none).
#
#   MODE=functional: pilot_v2 users 0-4, no judge, conditions h0, h2
#     (the seeded cycle) and the controls no_memory (kernel in-house
#     only: the guessing floor does not depend on the locus), no_delete
#     (every cell), no_visibility (native only), writer_scoped (kernel and
#     replicated) and no_supersession (kernel and replicated, _ns phases).
#   MODE=smoke: pilot_v2's 30 users, h0, judge v2 on the integration
#     probe.
#
# Code: both repos must have no tracked change; every finished cell must
# record exactly the current commits (no -dirty) and have no failed
# trial, or the driver stops. One fresh kernel per model per phase, on a
# port that must be free first; config.yaml restored byte for byte at
# exit. Resumable: a finished cell is skipped, an unfinished one is
# re-run whole. RUN_PREFIX is required and must be new for every run
# and every re-run of a cell: the stores and tombstones a run leaves
# are not reset (known issue 36). At the end of each phase, and for a
# phase a resumed launch finds finished, the checks read every kernel
# log of the phase in $OUTROOT/logs, earlier launches' included: move a
# discarded attempt's logs out of $OUTROOT before reusing it.
# Run from the AIOS repo, detached:
#   MODE=functional RUN_PREFIX=f16 nohup bash scripts/run_bench_v2.sh > ../repo-artifacts/Cerebrum/bench_v2_functional.log 2>&1 &
set -u
AIOS="$(pwd)"
CEREBRUM="$AIOS/../Cerebrum"
CONFIG="aios/config/config.yaml"
MODE="${MODE:-functional}"
case "$MODE" in
    functional)
        OUTROOT="${OUTROOT:-results/bench_v2_functional}"
        TRIALS="${TRIALS:-5}"
        CONDITIONS="${CONDITIONS:-h0 h2 no_memory no_delete no_visibility writer_scoped no_supersession}"
        JUDGE_ARGS=(--no-judge)
        PHASES="${PHASES:-kmem0 kinh agent kmem0_ns kinh_ns agent_ns}" ;;
    smoke)
        OUTROOT="${OUTROOT:-results/bench_v2_smoke}"
        TRIALS="${TRIALS:-30}"
        CONDITIONS="${CONDITIONS:-h0}"
        JUDGE_ARGS=(--judge-model "gpt-5.4:azure")
        PHASES="${PHASES:-kmem0 kinh agent}" ;;
    *) echo "MODE must be functional or smoke" >&2; exit 1 ;;
esac
[ -n "${RUN_PREFIX:-}" ] || {
    echo "set RUN_PREFIX, new for every run (known issue 36)" >&2; exit 1; }
LOGS="$CEREBRUM/$OUTROOT/logs"
DATASET="pilot_v2"
MODELS="${MODELS:-qwen}"
# Any kernel memory request: none in an agent phase.
MEMORY_OPS='add_memory: agent=|retrieve_memory result|Injection pipeline|Stored conversation memory|Injected [0-9]+ memories|MEMORY QUERY RECEIVED|forget_memory: agent=|list_memory: agent='
# The read guard's warnings (Amendment 4): a carrier escaped the forget.
GUARD='Selection guard dropped|Listing withheld|Read withheld'
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
SUPERSESSION=exclude
mode() {  # supersession from $SUPERSESSION (off in the _ns phases)
    "$AIOS/.venv/bin/python" scripts/set_memory_mode.py "$CONFIG" "$@" \
        --recency session --barrier-timeout-ms 60000 --k 10 --budget 300 \
        --supersession "$SUPERSESSION"
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

applies() {  # $1 = condition, $2 = phase, $3 = method
    case "$2" in  # the _ns phases run no_supersession only
        *_ns) [ "$1" = no_supersession ]; return ;;
    esac
    case "$1" in
        no_memory) [ "$2" = kinh ] ;;
        no_visibility) case "$3" in native_*) true ;; *) false ;; esac ;;
        writer_scoped) case "$3" in native_*) false ;; *) true ;; esac ;;
        no_supersession) false ;;  # its own phases
        *) true ;;
    esac
}
condition_args() {  # $1 = condition
    case "$1" in
        h0) echo "--heterogeneity 0" ;;
        h2) echo "--heterogeneity 2" ;;
        no_memory|no_delete|no_visibility|writer_scoped|no_supersession)
            echo "--heterogeneity 0 --control $1" ;;
        *) echo "unknown condition $1" >&2; exit 1 ;;
    esac
}

cell_path() { echo "$OUTROOT/$1/$2/$3_$4"; }  # model phase condition method

run_cell() {  # $1 = model, $2 = phase, $3 = method, $4 = condition, [$5 = provider]
    local model=$1 phase=$2 method=$3 cond=$4 provider=${5:-}
    local cell; cell=$(cell_path "$model" "$phase" "$cond" "$method")
    local file="$CEREBRUM/$cell/results_$method.json"
    local name="${model}_${phase}_${method}_$cond"
    cell_done "$file" && { echo "$(date) skip $name"; return 0; }
    local check=()
    [ -n "$provider" ] && check=(--provider "$provider")
    echo "$(date) start $name"
    (set -a; . "$AIOS/.env"; set +a
     export CEREBRUM_NATIVE_MEMORY_DIR="$CEREBRUM/.native_memory/$RUN_PREFIX"
     export CEREBRUM_REPLICATED_MEMORY_DIR="$CEREBRUM/.replicated_memory/$RUN_PREFIX"
     export AIOS_ROOT="$AIOS"
     # shellcheck disable=SC2046
     cd "$CEREBRUM" && .venv/bin/python \
        -m benchmarks.shared_memory.run_evaluation \
        --dataset "$DATASET" --trials "$TRIALS" --method "$method" \
        ${check[@]+"${check[@]}"} --assistant-model "$(assistant_of "$model")" \
        "${JUDGE_ARGS[@]}" $(condition_args "$cond") \
        --run-id "$RUN_PREFIX-$model-$phase-$method-$cond" \
        --output "$cell" > "$LOGS/$name.log" 2>&1) || {
        echo "$(date) FAILED $name"; exit 1;
    }
    cell_done "$file" || { echo "$(date) INCOMPLETE $name"; exit 1; }
    echo "$(date) done $name"
}

methods_of() {  # $1 = phase
    case "$1" in
        kmem0|kinh|kmem0_ns|kinh_ns) echo "kernel_shared" ;;
        agent) echo "replicated_mem0 replicated_inhouse native_mem0 native_inhouse" ;;
        agent_ns) echo "replicated_mem0 replicated_inhouse" ;;
    esac
}

check_phase() {  # $1 = model, $2 = phase: every kernel log of the phase
    # in $LOGS, earlier launches' included (`_2`: kmem0 never matches
    # kmem0_ns); counts are summed through cat, as grep -c over several
    # files prints one count per file.
    local model=$1 phase=$2
    set -- "$LOGS"/kernel_${model}_${phase}_2*.log
    [ -e "$1" ] || { echo "$(date) NO KERNEL LOG $model $phase"; exit 1; }
    case $phase in
    agent|agent_ns)
        ops=$(cat "$@" | grep -cE "$MEMORY_OPS")
        echo "$(date) $model $phase kernel_memory_ops=$ops"
        [ "$ops" -eq 0 ] || { echo "$(date) MEMORY OPS IN KERNEL LOG"; exit 1; } ;;
    *)  # Amendment 3: the kernel stored no probe turn
        turns=$(cat "$@" | grep -c "Stored conversation memory")
        echo "$(date) $model $phase stored_conversation_turns=$turns"
        [ "$turns" -eq 0 ] || { echo "$(date) PROBE TURNS STORED"; exit 1; }
        # Amendment 4: reported here, judged by the analysis.
        guard=$(cat "$@" | grep -cE "$GUARD")
        echo "$(date) $model $phase guard_warnings=$guard" ;;
    esac
}

phase_needed() {  # $1 = model, $2 = phase: true if a cell is unfinished
    local model=$1 phase=$2
    for cond in $CONDITIONS; do
        for method in $(methods_of "$phase"); do
            applies "$cond" "$phase" "$method" || continue
            cell_done "$CEREBRUM/$(cell_path "$model" "$phase" "$cond" "$method")/results_$method.json" || return 0
        done
    done
    return 1
}

for model in $MODELS; do
    for phase in $PHASES; do
        case $phase in
            *_ns) SUPERSESSION=off ;;
            *) SUPERSESSION=exclude ;;
        esac
        case $phase in
            kmem0|kmem0_ns) mode --provider mem0 --kernel-memory on --extract off
                   provider=mem0 ;;
            kinh|kinh_ns)  mode --provider in-house --kernel-memory on --extract off
                   provider=in-house ;;
            agent|agent_ns) mode --provider mem0 --kernel-memory off; provider="" ;;
            *) echo "unknown phase $phase" >&2; exit 1 ;;
        esac
        phase_needed "$model" "$phase" || {
            echo "$(date) skip $model $phase"
            check_phase "$model" "$phase"
            continue
        }
        start_kernel "${model}_$phase"
        for cond in $CONDITIONS; do
            for method in $(methods_of "$phase"); do
                applies "$cond" "$phase" "$method" || continue
                run_cell "$model" "$phase" "$method" "$cond" "$provider"
            done
        done
        stop_kernel
        check_phase "$model" "$phase"
    done
done
echo "$(date) BENCH V2 $MODE DONE"
