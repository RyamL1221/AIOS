#!/bin/bash
# Subtask 19: kernel ablations (docs/ABLATION.md). Each switch in ABLATE
# runs one kernel component off against the full kernel, paired on the
# same users (pilot_v2's first users at N = 6, agents_n6), kernel locus
# only, under the condition its row names:
#   barrier           n6conc        --concurrency concurrent
#   identity          n6wrong_user  --fault wrong_user
#                     n6v2          --variants profile_agent=V2 (functional)
#   visibility        n6v3          --variants assistant_agent=V3
#   supersession, forget_scope, block_format, block_order, budget,
#   threshold         n6h0          H = 0
#   quota             n6flood10, n6flood50   --fault flood10 / flood50
#   consumer_config   n6v4          --variants assistant_agent=V4, and the
#                     replicated V4 cell of the same backend (phase agent)
# Phases, for BACKEND inhouse (kinh) or mem0 (kmem0):
#   kinh            the full kernel (memory.ablate all on): every
#                   condition the switches need, once
#   kinh_<switch>   the kernel with that switch (set_memory_mode.py
#                   --ablate <switch>; the harness runs --ablate <switch>
#                   and its pre-flight checks the kernel's): its
#                   conditions
#   agent           kernel memory off, the full kernel's settings:
#                   replicated_<backend> under n6v4 (consumer_config
#                   only); 0 kernel memory ops checked
# Every kernel: session ages on, the barrier at 60 s, k 30, a 300-token
# budget, supersession exclude, as run_bench_v2.sh sets them; the write
# quota on for the flood conditions and off for the others, each on a
# fresh kernel of its own.
#   MODE=functional: users 0-4, Qwen, no judge, every switch.
#   MODE=smoke: users 0-29, Qwen, no judge, ABLATE barrier identity
#     quota forget_scope (identity under wrong_user only).
# As run_stress_s18.sh: both repos must have no tracked change and every
# finished cell must record the current commits with no failed trial;
# config.yaml restored byte for byte at exit; resumable (a finished cell
# is skipped). RUN_PREFIX (new for every run and resume) and OUTROOT
# (relative to the Cerebrum checkout) are required; ARCHIVE, when set,
# is a new directory OUTROOT is copied into through
# scripts/archive_artifacts.py. ABLATE, CONDITIONS and BACKEND narrow a
# run. Run from the AIOS repo, detached:
#   OUT=results/ablation_functional_f19; mkdir -p ../Cerebrum/$OUT
#   MODE=functional RUN_PREFIX=f19 OUTROOT=$OUT nohup bash scripts/run_ablation.sh > ../Cerebrum/$OUT/driver.log 2>&1 &
set -u
AIOS="$(pwd)"
CEREBRUM="$AIOS/../Cerebrum"
CONFIG="aios/config/config.yaml"
MODE="${MODE:-functional}"
ALL_SWITCHES="barrier identity visibility supersession forget_scope quota block_format block_order budget threshold consumer_config"
case "$MODE" in
    functional)
        TRIALS="${TRIALS:-5}"
        ABLATE="${ABLATE:-$ALL_SWITCHES}" ;;
    smoke)
        TRIALS="${TRIALS:-30}"
        ABLATE="${ABLATE:-barrier identity quota forget_scope}" ;;
    *) echo "MODE must be functional or smoke" >&2; exit 1 ;;
esac
BACKEND="${BACKEND:-inhouse}"
case "$BACKEND" in
    inhouse) KPHASE=kinh; PROVIDER=in-house ;;
    mem0) KPHASE=kmem0; PROVIDER=mem0 ;;
    *) echo "BACKEND must be inhouse or mem0" >&2; exit 1 ;;
esac
for switch in $ABLATE; do
    case " $ALL_SWITCHES " in *" $switch "*) ;;
        *) echo "unknown switch $switch" >&2; exit 1 ;; esac
done
[ -n "${RUN_PREFIX:-}" ] || {
    echo "set RUN_PREFIX, new for every run (known issue 36)" >&2; exit 1; }
[ -n "${OUTROOT:-}" ] || {
    echo "set OUTROOT, the run's own (a resume keeps it)" >&2; exit 1; }
LOGS="$CEREBRUM/$OUTROOT/logs"
[ -z "${ARCHIVE:-}" ] || [ ! -e "$ARCHIVE" ] || {
    echo "$ARCHIVE exists: set a new ARCHIVE" >&2; exit 1; }
DATASET="pilot_v2"
MODEL="${MODEL:-qwen}"
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
mode() {  # $1 = kernel memory on|off, $2 = quota on|off, $3 = ablation
    local memory=(--kernel-memory on --extract off)
    [ "$1" = off ] && memory=(--kernel-memory off)
    "$AIOS/.venv/bin/python" scripts/set_memory_mode.py "$CONFIG" \
        --provider "$PROVIDER" "${memory[@]}" \
        --recency session --barrier-timeout-ms 60000 --k 30 --budget 300 \
        --supersession exclude --write-quota "$2" --ablate "$3"
}
cell_done() {  # $1 = results file
    python3 "$AIOS/scripts/pilot_cell_done.py" "$1" "$TRIALS" --strict \
        --commit "$HARNESS_COMMIT" --kernel-commit "$KERNEL_COMMIT"
}
assistant_of() {
    case "$1" in
        qwen) echo "qwen2.5:7b:ollama" ;;
        *) echo "unknown model $1" >&2; exit 1 ;;
    esac
}

KLOG=""
start_kernel() {  # $1 = log name; never two kernels on one log
    if lsof -nP -iTCP:8000 -sTCP:LISTEN > /dev/null 2>&1; then
        echo "port 8000 is in use: stop that process first" >&2; exit 1
    fi
    local stamp n=1
    stamp=$(date +%Y%m%dT%H%M%S)
    KLOG="$LOGS/kernel_$1_$stamp.log"
    while [ -e "$KLOG" ]; do
        KLOG="$LOGS/kernel_$1_${stamp}_$n.log"; n=$((n + 1))
    done
    "$AIOS/.venv/bin/python" -m uvicorn runtime.launch:app \
        --host 127.0.0.1 --port 8000 > "$KLOG" 2>&1 &
    KERNEL=$!
    until curl -s -m 2 localhost:8000/status > /dev/null; do
        kill -0 "$KERNEL" 2>/dev/null || { echo "kernel died"; exit 1; }
        sleep 2
    done
}

conditions_of() {  # $1 = switch: the conditions its row names
    case "$1" in
        barrier) echo "n6conc" ;;
        identity)
            if [ "$MODE" = smoke ]; then echo "n6wrong_user"
            else echo "n6wrong_user n6v2"; fi ;;
        visibility) echo "n6v3" ;;
        quota) echo "n6flood10 n6flood50" ;;
        consumer_config) echo "n6v4" ;;
        *) echo "n6h0" ;;
    esac
}
wanted() {  # $1 = condition: false when CONDITIONS leaves it out
    case " ${CONDITIONS:-$1} " in *" $1 "*) true ;; *) false ;; esac
}
quota_of() {  # $1 = condition: the write quota its kernel runs with
    case "$1" in *flood*) echo on ;; *) echo off ;; esac
}
condition_args() {  # $1 = condition
    case "$1" in
        n6h0) echo "--agents 6 --heterogeneity 0" ;;
        n6conc) echo "--agents 6 --concurrency concurrent" ;;
        n6wrong_user|n6flood10|n6flood50)
            echo "--agents 6 --fault ${1#n6}" ;;
        n6v2) echo "--agents 6 --variants profile_agent=V2" ;;
        n6v3) echo "--agents 6 --variants assistant_agent=V3" ;;
        n6v4) echo "--agents 6 --variants assistant_agent=V4" ;;
        *) echo "unknown condition $1" >&2; exit 1 ;;
    esac
}

cell_path() { echo "$OUTROOT/$MODEL/$1/$2_$3"; }  # phase condition method

run_cell() {  # $1 = phase, $2 = method, $3 = condition, $4 = ablation
    local phase=$1 method=$2 cond=$3 switch=$4
    local cell; cell=$(cell_path "$phase" "$cond" "$method")
    local file="$CEREBRUM/$cell/results_$method.json"
    local name="${MODEL}_${phase}_${method}_$cond"
    cell_done "$file" && { echo "$(date) skip $name"; return 0; }
    local extra=()
    [ "$switch" != none ] && extra=(--ablate "$switch")
    [ "$method" = kernel_shared ] && extra+=(--provider "$PROVIDER")
    echo "$(date) start $name"
    (set -a; . "$AIOS/.env"; set +a
     export CEREBRUM_NATIVE_MEMORY_DIR="$CEREBRUM/.native_memory/$RUN_PREFIX"
     export CEREBRUM_REPLICATED_MEMORY_DIR="$CEREBRUM/.replicated_memory/$RUN_PREFIX"
     export AIOS_ROOT="$AIOS"
     # shellcheck disable=SC2046
     cd "$CEREBRUM" && .venv/bin/python \
        -m benchmarks.shared_memory.run_evaluation \
        --dataset "$DATASET" --trials "$TRIALS" --method "$method" \
        ${extra[@]+"${extra[@]}"} --assistant-model "$(assistant_of "$MODEL")" \
        --no-judge $(condition_args "$cond") \
        --run-id "$RUN_PREFIX-$MODEL-$phase-$method-$cond" \
        --output "$cell" > "$LOGS/$name.log" 2>&1) || {
        echo "$(date) FAILED $name"; exit 1;
    }
    cell_done "$file" || { echo "$(date) INCOMPLETE $name"; exit 1; }
    echo "$(date) done $name"
}

check_phase() {  # $1 = phase: every kernel log of the phase
    local phase=$1
    set -- "$LOGS"/kernel_${MODEL}_${phase}_2*.log
    [ -e "$1" ] || { echo "$(date) NO KERNEL LOG $phase"; exit 1; }
    case $phase in
    agent)
        ops=$(cat "$@" | grep -cE "$MEMORY_OPS")
        echo "$(date) $MODEL $phase kernel_memory_ops=$ops"
        [ "$ops" -eq 0 ] || { echo "$(date) MEMORY OPS IN KERNEL LOG"; exit 1; } ;;
    *)  # Amendment 3: the kernel stored no probe turn
        turns=$(cat "$@" | grep -c "Stored conversation memory")
        echo "$(date) $MODEL $phase stored_conversation_turns=$turns"
        [ "$turns" -eq 0 ] || { echo "$(date) PROBE TURNS STORED"; exit 1; }
        guard=$(cat "$@" | grep -cE "$GUARD")
        echo "$(date) $MODEL $phase guard_warnings=$guard" ;;
    esac
}

run_phase() {  # $1 = phase, $2 = kernel memory, $3 = ablation, $4 = method,
    # then the conditions: one kernel per write quota the conditions need
    local phase=$1 memory=$2 switch=$3 method=$4 quota cond ran=""
    shift 4
    for quota in off on; do
        local todo=()  # bash 3.2: an empty array is unbound under set -u
        for cond in "$@"; do
            [ "$(quota_of "$cond")" = "$quota" ] || continue
            wanted "$cond" || continue
            cell_done "$CEREBRUM/$(cell_path "$phase" "$cond" "$method")/results_$method.json" \
                && { echo "$(date) skip ${MODEL}_${phase}_${method}_$cond"; continue; }
            todo+=("$cond")
        done
        [ -n "${todo[*]+x}" ] && [ ${#todo[@]} -gt 0 ] || continue
        mode "$memory" "$quota" "$switch"
        start_kernel "${MODEL}_$phase"
        for cond in "${todo[@]}"; do
            run_cell "$phase" "$method" "$cond" "$switch"
        done
        stop_kernel
        ran=1
    done
    if [ -n "$ran" ] || ls "$LOGS"/kernel_${MODEL}_${phase}_2*.log \
            > /dev/null 2>&1; then
        check_phase "$phase"
    fi
}

# The full kernel: every condition the switches need, once.
FULL=""
for switch in $ABLATE; do
    for cond in $(conditions_of "$switch"); do
        case " $FULL " in *" $cond "*) ;; *) FULL="$FULL $cond" ;; esac
    done
done
# shellcheck disable=SC2086
run_phase "$KPHASE" on none kernel_shared $FULL
for switch in $ABLATE; do
    # shellcheck disable=SC2046
    run_phase "${KPHASE}_$switch" on "$switch" kernel_shared \
        $(conditions_of "$switch")
done
case " $ABLATE " in *" consumer_config "*)
    run_phase agent off none "replicated_$BACKEND" n6v4 ;;
esac
echo "$(date) ABLATION $MODE DONE"
if [ -n "${ARCHIVE:-}" ]; then
    echo "$(date) archiving $OUTROOT to $ARCHIVE"
    "$AIOS/.venv/bin/python" scripts/archive_artifacts.py --root "$AIOS" \
        --sums --dest "$ARCHIVE" "$CEREBRUM/$OUTROOT"/* || {
        echo "$(date) ARCHIVE REFUSED: nothing copied"; exit 1; }
fi
