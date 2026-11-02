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
