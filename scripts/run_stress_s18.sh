#!/bin/bash
# Subtask 18: the stress dimensions' judge-free runs
# (docs/STRESS_DIMENSIONS.md, "Functional check and smoke"), on benchmark
# v2's pilot users at an agent count N (agents_nN, derived from users_v2).
#   phase kinh:   in-house, kernel injection on, extraction off, write
#                 quota off: kernel_shared
#   phase kmem0:  the same on Mem0
#   phase agent:  kernel memory off, quota off: replicated_mem0,
#                 replicated_inhouse, native_mem0, native_inhouse; 0
#                 kernel memory ops checked
#   phases kinh_q, kmem0_q, agent_q: the same with the write quota on,
#                 for the flood conditions only (the replicated agents
#                 copy the kernel's pipeline settings, quota included;
#                 a flooding replicated writer runs without it)
# Every phase: session ages on, the write barrier at 60 s, k 30, a
# 300-token budget and supersession exclude, as run_bench_v2.sh sets them.
# Conditions (each its own cell per method):
#   nNhH          --agents N --heterogeneity H        (N 3, 6, 12; H 0, 2)
#   n6conc        --agents 6 --concurrency concurrent
#   n6<fault>     --agents 6 --fault <fault>  (wrong_user, missing_metadata,
#                 flood10, flood50; the floods in the _q phases)
#   n6loadM       --agents 6 --load M --trials LOAD_TRIALS (M 1, 4, 16;
#                 kernel_shared only)
#   MODE=functional: users 0-4 (LOAD_TRIALS 16), Qwen, no judge, every
#     condition in kinh, kmem0, agent and their _q phases.
#   MODE=smoke: 30 users, Qwen, no judge, in-house only: n6h0, n6conc,
#     n6flood10, n6flood50.
# As run_bench_v2.sh: both repos must have no tracked change and every
# finished cell must record the current commits; one fresh kernel per
# phase on a free port 8000; config.yaml restored byte for byte at exit;
# resumable (a finished cell is skipped). RUN_PREFIX (new for every run
# and resume) and OUTROOT (relative to the Cerebrum checkout) are
# required; ARCHIVE, when set, is a new directory the run's OUTROOT is
# copied into through scripts/archive_artifacts.py. CONDITIONS, PHASES
# and METHODS narrow a run. Run from the AIOS repo, detached:
#   OUT=results/stress_functional_f18; mkdir -p ../Cerebrum/$OUT
#   MODE=functional RUN_PREFIX=f18 OUTROOT=$OUT nohup bash scripts/run_stress_s18.sh > ../Cerebrum/$OUT/driver.log 2>&1 &
set -u
AIOS="$(pwd)"
CEREBRUM="$AIOS/../Cerebrum"
CONFIG="aios/config/config.yaml"
MODE="${MODE:-functional}"
case "$MODE" in
    functional)
        TRIALS="${TRIALS:-5}"
        LOAD_TRIALS="${LOAD_TRIALS:-16}"
        CONDITIONS="${CONDITIONS:-n3h0 n3h2 n6h0 n6h2 n12h0 n12h2 n6conc n6wrong_user n6missing_metadata n6flood10 n6flood50 n6load1 n6load4 n6load16}"
        PHASES="${PHASES:-kinh kmem0 agent kinh_q kmem0_q agent_q}"
        AGENT_METHODS="replicated_mem0 replicated_inhouse native_mem0 native_inhouse" ;;
    smoke)
        TRIALS="${TRIALS:-30}"
        LOAD_TRIALS="${LOAD_TRIALS:-16}"
        CONDITIONS="${CONDITIONS:-n6h0 n6conc n6flood10 n6flood50}"
        PHASES="${PHASES:-kinh agent kinh_q agent_q}"
        AGENT_METHODS="replicated_inhouse native_inhouse" ;;
    *) echo "MODE must be functional or smoke" >&2; exit 1 ;;
esac
[ -n "${RUN_PREFIX:-}" ] || {
    echo "set RUN_PREFIX, new for every run (known issue 36)" >&2; exit 1; }
[ -n "${OUTROOT:-}" ] || {
    echo "set OUTROOT, the run's own (a resume keeps it)" >&2; exit 1; }
LOGS="$CEREBRUM/$OUTROOT/logs"
[ -z "${ARCHIVE:-}" ] || [ ! -e "$ARCHIVE" ] || {
    echo "$ARCHIVE exists: set a new ARCHIVE" >&2; exit 1; }
DATASET="pilot_v2"
MODELS="${MODELS:-qwen}"
MEMORY_OPS='add_memory: agent=|retrieve_memory result|Injection pipeline|Stored conversation memory|Injected [0-9]+ memories|MEMORY QUERY RECEIVED|forget_memory: agent=|list_memory: agent='
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
mode() {  # $@ = provider and kernel-memory flags; QUOTA = on|off
    "$AIOS/.venv/bin/python" scripts/set_memory_mode.py "$CONFIG" "$@" \
        --recency session --barrier-timeout-ms 60000 --k 30 --budget 300 \
        --supersession exclude --write-quota "$QUOTA"
}
trials_of() {  # $1 = condition
    case "$1" in n6load*) echo "$LOAD_TRIALS" ;; *) echo "$TRIALS" ;; esac
}
cell_done() {  # $1 = file, $2 = trials
    python3 "$AIOS/scripts/pilot_cell_done.py" "$1" "$2" --strict \
        --commit "$HARNESS_COMMIT" --kernel-commit "$KERNEL_COMMIT"
}
assistant_of() {
    case "$1" in
        qwen) echo "qwen2.5:7b:ollama" ;;
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

is_flood() { case "$1" in *flood*) true ;; *) false ;; esac; }
applies() {  # $1 = condition, $2 = phase, $3 = method
    case "$2" in  # the _q phases run the floods only, the others none
        *_q) is_flood "$1" || return 1 ;;
        *) is_flood "$1" && return 1 ;;
    esac
    case "$1" in
        n6load*) [ "$3" = kernel_shared ] ;;
        *) true ;;
    esac
}
condition_args() {  # $1 = condition
    case "$1" in
        n3h0) echo "--agents 3 --heterogeneity 0" ;;
        n3h2) echo "--agents 3 --heterogeneity 2" ;;
        n6h0) echo "--agents 6 --heterogeneity 0" ;;
        n6h2) echo "--agents 6 --heterogeneity 2" ;;
        n12h0) echo "--agents 12 --heterogeneity 0" ;;
        n12h2) echo "--agents 12 --heterogeneity 2" ;;
        n6conc) echo "--agents 6 --concurrency concurrent" ;;
        n6wrong_user|n6missing_metadata|n6flood10|n6flood50)
            echo "--agents 6 --fault ${1#n6}" ;;
        n6load1|n6load4|n6load16) echo "--agents 6 --load ${1#n6load}" ;;
        *) echo "unknown condition $1" >&2; exit 1 ;;
    esac
}

cell_path() { echo "$OUTROOT/$1/$2/$3_$4"; }  # model phase condition method

run_cell() {  # $1 = model, $2 = phase, $3 = method, $4 = condition, [$5 = provider]
    local model=$1 phase=$2 method=$3 cond=$4 provider=${5:-}
    local cell; cell=$(cell_path "$model" "$phase" "$cond" "$method")
    local file="$CEREBRUM/$cell/results_$method.json"
    local name="${model}_${phase}_${method}_$cond"
    local trials; trials=$(trials_of "$cond")
    cell_done "$file" "$trials" && { echo "$(date) skip $name"; return 0; }
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
        --dataset "$DATASET" --trials "$trials" --method "$method" \
        ${check[@]+"${check[@]}"} --assistant-model "$(assistant_of "$model")" \
        --no-judge $(condition_args "$cond") \
        --run-id "$RUN_PREFIX-$model-$phase-$method-$cond" \
        --output "$cell" > "$LOGS/$name.log" 2>&1) || {
        echo "$(date) FAILED $name"; exit 1;
    }
    cell_done "$file" "$trials" || { echo "$(date) INCOMPLETE $name"; exit 1; }
    echo "$(date) done $name"
}

methods_of() {  # $1 = phase; with $METHODS set, only those methods
    local all method
    case "$1" in
        kinh|kinh_q|kmem0|kmem0_q) all="kernel_shared" ;;
        agent|agent_q) all="$AGENT_METHODS" ;;
    esac
    for method in $all; do
        case " ${METHODS:-$all} " in *" $method "*) echo "$method" ;; esac
    done
}

check_phase() {  # $1 = model, $2 = phase: every kernel log of the phase
    local model=$1 phase=$2
    set -- "$LOGS"/kernel_${model}_${phase}_2*.log
    [ -e "$1" ] || { echo "$(date) NO KERNEL LOG $model $phase"; exit 1; }
    case $phase in
    agent|agent_q)
        ops=$(cat "$@" | grep -cE "$MEMORY_OPS")
        echo "$(date) $model $phase kernel_memory_ops=$ops"
        [ "$ops" -eq 0 ] || { echo "$(date) MEMORY OPS IN KERNEL LOG"; exit 1; } ;;
    *)
        turns=$(cat "$@" | grep -c "Stored conversation memory")
        echo "$(date) $model $phase stored_conversation_turns=$turns"
        [ "$turns" -eq 0 ] || { echo "$(date) PROBE TURNS STORED"; exit 1; }
        guard=$(cat "$@" | grep -cE "$GUARD")
        echo "$(date) $model $phase guard_warnings=$guard" ;;
    esac
}

phase_needed() {  # $1 = model, $2 = phase: true if a cell is unfinished
    local model=$1 phase=$2
    for cond in $CONDITIONS; do
        for method in $(methods_of "$phase"); do
            applies "$cond" "$phase" "$method" || continue
            cell_done "$CEREBRUM/$(cell_path "$model" "$phase" "$cond" "$method")/results_$method.json" "$(trials_of "$cond")" || return 0
        done
    done
    return 1
}

for model in $MODELS; do
    for phase in $PHASES; do
        case $phase in *_q) QUOTA=on ;; *) QUOTA=off ;; esac
        case $phase in
            kinh|kinh_q) mode --provider in-house --kernel-memory on --extract off
                   provider=in-house ;;
            kmem0|kmem0_q) mode --provider mem0 --kernel-memory on --extract off
                   provider=mem0 ;;
            agent|agent_q) mode --provider mem0 --kernel-memory off; provider="" ;;
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
echo "$(date) STRESS $MODE DONE"
if [ -n "${ARCHIVE:-}" ]; then
    echo "$(date) archiving $OUTROOT to $ARCHIVE"
    "$AIOS/.venv/bin/python" scripts/archive_artifacts.py --root "$AIOS" \
        --sums --dest "$ARCHIVE" "$CEREBRUM/$OUTROOT"/* || {
        echo "$(date) ARCHIVE REFUSED: nothing copied"; exit 1; }
fi
