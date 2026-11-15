#!/bin/bash
# Subtask 17: the pilot_v1 smoke on A-MEM (docs/AMEM_BACKEND.md):
# scripts/run_pilot_v1_graphiti.sh with BACKEND=amem (phases kamem and
# agent_amem), ARCHIVE included. Run from the AIOS repo, detached, the
# driver's log in OUTROOT:
#   OUT=results/pilot_v1_amem; mkdir -p ../Cerebrum/$OUT
#   RUN_PREFIX=pa17 OUTROOT=$OUT ARCHIVE=../repo-artifacts/Cerebrum/pilot_v1_amem nohup bash scripts/run_pilot_v1_amem.sh > ../Cerebrum/$OUT/driver.log 2>&1 &
BACKEND=amem exec bash "$(dirname "$0")/run_pilot_v1_graphiti.sh"
