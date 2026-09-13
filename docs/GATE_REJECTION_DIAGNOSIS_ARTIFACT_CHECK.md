# Artifact Verification — Gate-Rejection Diagnosis (Subtask 1)

Read-only pre-flight before any extraction/join work on the fresh 1×15
`kernel_shared_adaptive` run (commit `d3a79cb`, kernel PID 69841, run
window 2026-09-13 16:30:46–16:38:03). Confirms all three source
artifacts survive intact so the downstream diagnosis is not built on a
missing/partial input.

## Status: ALL THREE PRESENT AND INTACT

| # | Artifact | Status | Evidence |
|---|----------|--------|----------|
| 1 | `Cerebrum/results/subtask4_fresh_1x15/results_kernel_shared_adaptive.json` | **PRESENT / COMPLETE** | 15 trial records, interaction indices 0–14 (matches prior session); 102,027 bytes |
| 2 | `AIOS/logs/policy_trials.subtask4fresh_1x15_20260913_163934.jsonl` | **PRESENT / COMPLETE** | 599 lines (matches prior count); run-window events (after the 313-line pre-run baseline) = **167 select + 119 reward** (matches prior session) |
| 3 | `AIOS/kernel.log` | **PRESENT / COMPLETE for the run window** | Fail-open lines all fall inside 16:30–16:38; no restart; see below |

## Artifact 1 — harness results JSON
- Path: `../Cerebrum/results/subtask4_fresh_1x15/results_kernel_shared_adaptive.json`
  (the Cerebrum harness lives at the sibling checkout
  `/Users/ryan/Library/Mobile Documents/.../VSCode/Cerebrum`).
- 15 trial records, `interaction_index` 0–14 — the full run.

## Artifact 2 — preserved policy trial log
- Path: `logs/policy_trials.subtask4fresh_1x15_20260913_163934.jsonl`
- 599 total lines. The run's contribution is lines 314–599 (the first
  313 are the pre-run baseline that was present when the log was
  copied). Run-window event counts: **167 select, 119 reward** — byte-
  for-byte consistent with the prior session's analysis.

## Artifact 3 — kernel.log (highest-risk, explicitly cleared)
The concern was that kernel.log is a live process log that later kernel
activity could have rotated/overwritten/truncated. Verification shows it
did **not**:

- **File span:** 16:24:37 → 17:00:18 on 2026-09-13; 5,453,207 bytes.
- **Single kernel lifetime, no restart:** all startup markers
  (`Started server process` / `Application startup` / `Uvicorn running`)
  are at **16:24:42** only — one init, PID **69841**. There is no second
  startup, so the run's log was never overwritten by a fresh kernel.
- **Clean shutdown after the run:** the last real server line is
  `Finished server process [69841]` at **16:41:54** (the prior session's
  graceful stop). Timestamps out to 17:00 are trailing fsevents/DEBUG
  noise flushing after shutdown, not new kernel activity — which is why
  the file mtime (17:00) is later than the run end.
- **Fail-open lines fully preserved in the run window (16:3x):**
  - `still bootstrapping` (bootstrap fail-open): **44** total, **44**
    within `16:3[0-8]` — none outside the window, none lost.
  - `honoring converged arm` (strict-honor): **30** total, **30** within
    `16:3[0-8]`.
  - `report_reward: reward applied`: **17** total.

**No rotation/overwrite/truncation occurred; no preserved/rotated copy
was needed.** kernel.log fully covers the run's timestamp window, so it
does **not** block the downstream gate-rejection diagnosis.

## Conclusion
All three artifacts are present and complete. The gate-rejection
diagnosis can proceed on: the 15 harness trial records (scores +
retrieval/injection status), the 167/119 select/reward policy events,
and the 44 bootstrap-fail-open + 30 honoring-converged kernel gate lines
— all from the same single-kernel-lifetime run.
