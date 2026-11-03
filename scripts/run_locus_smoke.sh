#!/bin/bash
# Subtask 8 smoke: 30 trials per model of kernel_shared (Mem0 and
# in-house, re-run under the pipeline library's type-ordered block) and
# of replicated_mem0 and replicated_inhouse (docs/REPLICATED_LOGIC.md).
# Sets memory.provider and the kernel memory mode between runs, never
# during one, and restores config.yaml byte for byte at exit. Resumable:
# finished cells are skipped. Run from the AIOS repo, detached:
#   bash scripts/run_locus_smoke.sh
set -u
AIOS="$(pwd)"
CONFIG="aios/config/config.yaml"
SAVED="$(mktemp)"
cp "$CONFIG" "$SAVED"
restore() { cp "$SAVED" "$CONFIG"; rm -f "$SAVED"; }
trap restore EXIT
OUTROOT="results/locus_smoke"
mode() { "$AIOS/.venv/bin/python" scripts/set_memory_mode.py "$CONFIG" "$@"; }

mode --provider mem0 --kernel-memory on
PROVIDER=mem0 OUT="$OUTROOT/kernel_mem0" RUN_PREFIX=ls8-kmem0 \
    bash scripts/run_provider_smoke.sh || exit 1
mode --provider in-house --kernel-memory on
PROVIDER=in-house OUT="$OUTROOT/kernel_inhouse" RUN_PREFIX=ls8-kinh \
    bash scripts/run_provider_smoke.sh || exit 1
mode --provider mem0 --kernel-memory off
for method in replicated_inhouse replicated_mem0; do
    METHOD=$method OUT="$OUTROOT/$method" RUN_PREFIX="ls8-$method" \
        bash scripts/run_native_smoke.sh || exit 1
done
echo "$(date) LOCUS SMOKE DONE"
