# Re-validation of kernel_shared and mem0_default

Whether the workshop's `kernel_shared` results reproduce after Subtasks 1
and 2, on one commit with full provenance, and what `mem0_default` does.
The result is the paper's baseline. The workshop runs are not cited as
evidence again, because they span several code states and recorded no
commit, config or injected sets.

## Pre-registration

Committed before any trial ran. Analysis:
`benchmarks/shared_memory/revalidate.py` in Cerebrum, also committed
first.

### Workshop baseline

`kernel_shared`, 150 trials per model, judge scores 1-5. Computed from
the workshop result files (`Cerebrum/results/<model>_kernel_shared/`),
because Table 2 itself is in neither repo. Check these against the
paper's table.

| Model | Dimension | Mean | SD | 95% CI |
|---|---|---:|---:|---|
| GPT-4o | Profile | 4.693 | 0.504 | 4.612, 4.775 |
| GPT-4o | Task | 4.993 | 0.082 | 4.980, 5.007 |
| GPT-4o | Integration | 4.613 | 0.515 | 4.530, 4.696 |
| Llama-3.1:8B | Profile | 3.873 | 0.830 | 3.739, 4.007 |
| Llama-3.1:8B | Task | 4.327 | 0.746 | 4.206, 4.447 |
| Llama-3.1:8B | Integration | 3.633 | 0.798 | 3.505, 3.762 |
| Qwen-2.5:7B | Profile | 3.633 | 1.089 | 3.458, 3.809 |
| Qwen-2.5:7B | Task | 4.400 | 0.492 | 4.321, 4.479 |
| Qwen-2.5:7B | Integration | 3.580 | 0.936 | 3.429, 3.731 |

### Pass rule

- **Cell.** A cell reproduces if the new mean lies inside the workshop
  95% CI (two-sided t interval), or a TOST equivalence test at margin
  ±0.25 passes (two one-sided Welch t-tests, each at alpha 0.05).
- **Condition.** `kernel_shared` reproduces if at least 7 of 9 cells
  pass and no cell's mean shifts by more than 0.5.
- **Scope.** The rule applies to `kernel_shared`. `mem0_default` is
  reported the same way, but its evidence here is that the assistant sees
  no memories: `after_visibility` is 0 in all 450 trials.

### On failure

The paper reports the new numbers and explains the difference from the
behavior-change list in `docs/RETRIEVAL_PATH.md`. The workshop numbers
are not used.

### Run

150 trials each of `kernel_shared` and `mem0_default` on GPT-4o,
Llama-3.1:8B and Qwen-2.5:7B, 900 in total, by
`scripts/run_revalidation.sh`: `run_evaluation.py` unchanged, judge
`gpt-5.4:azure`, one fresh kernel per model, models in sequence. The
workshop files did not record their judge model, so GPT-5.4 is taken from
the project record. Each cell generates its own synthetic users, as in
the workshop. A failed trial makes that cell invalid; it is re-run whole
and the re-run is reported.

Provenance: `results/revalidation/PROVENANCE.md` in Cerebrum.

### Amendment, committed before the re-run

Added after the first run, before any re-run trial. The analysis rule,
margins and baseline do not change.

The first run left both GPT-4o cells invalid: 102 of 150 `kernel_shared`
and 100 of 150 `mem0_default` trials failed in synthetic data generation.
Azure gpt-4o wraps about a third of its JSON replies in a Markdown code
fence (4 of 12 in a direct reproduction), and the generator's
`json.loads` rejected them. `ProfileAgent` and `TaskAgent` had the same
bug, so a fenced agent reply lost that memory without failing the trial
(1 of the 48 completed GPT-4o trials injected no task context). The
driver counted trials, not failures, and reported success.

Under the rule above, both GPT-4o cells are re-run whole. Changes, none
in the kernel or the judge:

- Cerebrum: `parse_json_reply` strips the fence at the four generator
  sites and in both agents. This replaces "`run_evaluation.py` unchanged"
  to the extent of those parsers. `run_evaluation.py` itself is unchanged.
- `revalidate.py` skips failed trials in latency and exits non-zero if
  any trial failed.
- `run_revalidation.sh` rejects a cell with a failed trial or missing
  diagnostics, skips the kernel for finished models, and takes a
  `RUN_PREFIX`. The re-run uses `reval2` so its user ids cannot collide
  with the invalid run's stored memories.

The Llama and Qwen cells stand. Their code path did not change: all 600
trials completed, and all 300 `kernel_shared` trials injected a profile
and a task context, so no fenced reply reached either parser. They keep
the commits in `PROVENANCE.md`; each results file records the commits it
ran on. The invalid files are kept in
`repo-artifacts/Cerebrum/revalidation/invalid_first_run/`.

## Result

900 trials on the amended run: 0 failed, `injection_diagnostics` on all
900, every injection confirmed in the kernel log. GPT-4o ran on Cerebrum
`76dc9f1` / AIOS `672665e`; Llama and Qwen on Cerebrum `99933e4` / AIOS
`19c3ea9`. The two AIOS commits have the same kernel code. Judge
`gpt-5.4:azure`. Per-cell numbers: `results/revalidation/summary.csv` in
Cerebrum.

**`kernel_shared` reproduces: 8 of 9 cells pass, largest shift 0.20.**

**`mem0_default` behaves as specified: the assistant saw no memories in
all 450 trials (`after_visibility` = 0).** Its scores stay near the floor,
8 of 9 cells match the workshop, and its largest shift is 0.30.

### `kernel_shared`

| Model | Dimension | New | Workshop | Diff | Welch p | TOST p | Result |
|---|---|---:|---:|---:|---:|---:|---|
| GPT-4o | Profile | 4.587 ± 0.546 | 4.693 ± 0.504 | -0.107 | 0.0798 | 0.0094 | pass |
| GPT-4o | Task | 4.993 ± 0.082 | 4.993 ± 0.082 | 0.000 | 1.0000 | <0.0001 | pass |
| GPT-4o | Integration | 4.560 ± 0.524 | 4.613 ± 0.515 | -0.053 | 0.3750 | 0.0006 | pass |
| Llama-3.1:8B | Profile | 3.927 ± 0.778 | 3.873 ± 0.830 | +0.053 | 0.5662 | 0.0175 | pass |
| Llama-3.1:8B | Task | 4.320 ± 0.885 | 4.327 ± 0.746 | -0.007 | 0.9438 | 0.0053 | pass |
| Llama-3.1:8B | Integration | 3.667 ± 0.841 | 3.633 ± 0.798 | +0.033 | 0.7249 | 0.0114 | pass |
| Qwen-2.5:7B | Profile | 3.707 ± 1.190 | 3.633 ± 1.089 | +0.073 | 0.5782 | 0.0905 | pass |
| Qwen-2.5:7B | Task | 4.600 ± 0.492 | 4.400 ± 0.492 | +0.200 | 0.0005 | 0.1895 | **fail** |
| Qwen-2.5:7B | Integration | 3.547 ± 1.001 | 3.580 ± 0.936 | -0.033 | 0.7659 | 0.0269 | pass |

### `mem0_default`

Reported the same way; the pass rule does not apply to it.

| Model | Dimension | New | Workshop | Diff | Welch p | TOST p | Result |
|---|---|---:|---:|---:|---:|---:|---|
| GPT-4o | Profile | 1.067 ± 0.250 | 1.047 ± 0.212 | +0.020 | 0.4555 | <0.0001 | match |
| GPT-4o | Task | 1.020 ± 0.140 | 1.027 ± 0.162 | -0.007 | 0.7033 | <0.0001 | match |
| GPT-4o | Integration | 1.007 ± 0.082 | 1.000 ± 0.000 | +0.007 | 0.3189 | <0.0001 | match |
| Llama-3.1:8B | Profile | 1.100 ± 0.301 | 1.067 ± 0.250 | +0.033 | 0.2979 | <0.0001 | match |
| Llama-3.1:8B | Task | 1.273 ± 0.447 | 1.313 ± 0.465 | -0.040 | 0.4484 | <0.0001 | match |
| Llama-3.1:8B | Integration | 1.020 ± 0.140 | 1.040 ± 0.197 | -0.020 | 0.3116 | <0.0001 | match |
| Qwen-2.5:7B | Profile | 1.167 ± 0.374 | 1.240 ± 0.429 | -0.073 | 0.1154 | 0.0001 | match |
| Qwen-2.5:7B | Task | 1.300 ± 0.460 | 1.600 ± 0.505 | -0.300 | <0.0001 | 0.8147 | **differs** |
| Qwen-2.5:7B | Integration | 1.087 ± 0.282 | 1.187 ± 0.391 | -0.100 | 0.0116 | 0.0001 | match |

### The Qwen task cell

No listed behavior change explains it. They need many memories per user,
and each `kernel_shared` user had 2 after dedupe, so neither the top-k
change nor the cap fired. The cell's scores are all 4 or 5, and the share
of 5s rose from 40% to 60%.

The most likely cause is a Qwen-specific difference between the runs,
not retrieval. Qwen's task score also moved in `mem0_default`, in the
opposite direction, where nothing is injected, and its median reply there
fell from 2,010 to 859 characters. Llama's did not move (656 to 674),
which argues against a harness-wide change. The workshop recorded no
Ollama or model version, so this cannot be confirmed.

### Truncation and scores

- **Paper TODO.** The cap and the token budget bound in 0 of 450
  `kernel_shared` trials. `after_cap` and `after_budget` were 2 in all
  450, about 150-175 estimated tokens at the median. This shows only that
  a one-interaction trial cannot reach them, not that they never matter.
- **`scores_present`** was false in all 900 trials, as expected.
  `relevance_threshold` filtered nothing.
- **Injected set.** Every `kernel_shared` trial injected one profile and
  one task context.

### Latency

Mean assistant latency in seconds, new against workshop.

| Model | `kernel_shared` | `mem0_default` |
|---|---:|---:|
| GPT-4o | 6.28 / 7.51 | 3.05 / 3.94 |
| Llama-3.1:8B | 24.81 / 21.73 | 11.51 / 10.47 |
| Qwen-2.5:7B | 22.75 / 26.31 | 17.39 / 26.88 |

### Notes

- `revalidate.py` now exits non-zero on any failed trial; it exited 0
  on this result.
- `memory_counts` is 0 in every trial, new and workshop, so that field
  was never a usable measure. Use `injection_diagnostics`.
- The harness's `shared_memory_count` is 2 here and 4 in the workshop.
  The workshop recorded no diagnostics, so whether it injected the two
  duplicates cannot be determined from its files.
- The kernel logged "Failed to sync Mem0 LLM to azure_openai/gpt-4o" on
  each GPT-4o chat (no `api_version`). Kernel mode stores with
  `infer=False`, so Mem0's LLM is not called and scores are unaffected.
  It would matter in native mode.
