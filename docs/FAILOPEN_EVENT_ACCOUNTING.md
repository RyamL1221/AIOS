# Fail-Open Event Accounting Across Trials 0–14 (1×15 run)

Extraction + reconciliation only (no files changed). Accounts for **all
74** similarity-gate fail-open-adjacent kernel.log events (44 `still
bootstrapping` + 30 `honoring converged arm`) across the fresh 1×15
`kernel_shared_adaptive` run (commit `d3a79cb`, kernel PID 69841, window
2026-09-13 16:30:47–16:38:03). Joins kernel.log against the anchored
trial↔select-block↔arm mapping from
`docs/TRIAL_TO_SIMILARITY_ARM_MAPPING.md`.

## Headline finding (shifts the diagnosis)

Gate over-rejection is **NOT** confined to the 3 trailing zero-injection
trials. **Trials 5–10 (similarity arms 0.5–0.95) all had raw-retrieval
wipeouts that were silently rescued by the bootstrap fail-open** — their
`audit_inferred` / 1-injected status in the harness table is a
fail-open rescue, **not** a clean retrieval. Only trials 0–4 and 11 (low
arms 0.0–0.4 and back to 0.0) were genuine clean successes that never
hit the gate.

So the correct reading is **"gate over-rejection is happening throughout
the high-threshold trials, masked by fail-open"** — not "only the last 3
trials had a problem."

## Per-trial fail-open table (all 74 events, 0 unassigned, 0 arm mismatches)

| trial | sim arm (value) | bootstrap | honored | retrieval outcome |
|------:|-----------------|----------:|--------:|-------------------|
| 0  | 0 (0.0)  | 0  | 0  | **never_wiped (clean)** |
| 1  | 1 (0.1)  | 0  | 0  | never_wiped (clean) |
| 2  | 2 (0.2)  | 0  | 0  | never_wiped (clean) |
| 3  | 3 (0.3)  | 0  | 0  | never_wiped (clean) |
| 4  | 4 (0.4)  | 0  | 0  | never_wiped (clean) |
| 5  | 5 (0.5)  | 2  | 0  | **rescued (bootstrap fail-open)** |
| 6  | 6 (0.6)  | 5  | 0  | rescued (bootstrap fail-open) |
| 7  | 7 (0.7)  | 7  | 0  | rescued (bootstrap fail-open) |
| 8  | 8 (0.8)  | 10 | 0  | rescued (bootstrap fail-open) |
| 9  | 9 (0.9)  | 10 | 0  | rescued (bootstrap fail-open) |
| 10 | 10 (0.95)| 10 | 0  | rescued (bootstrap fail-open) |
| 11 | 0 (0.0)  | 0  | 0  | never_wiped (clean) |
| 12–14 | 8 (0.8) | 0 | 30 | **permanently_wiped (honored)** |
| **TOTAL** | | **44** | **30** | |

Totals reconcile exactly to the 44 / 30 counts verified in Subtask 1.

## How each event was assigned (and validated)

- The 74 lines were extracted from kernel.log restricted to the run
  window `16:3[0-8]`; every line parsed a `similarity_threshold=V
  (arm A)` token (0 lines lacked one — the fail-open branch exists only
  on the similarity gate, so there are no redundancy/novelty fail-open
  lines to confuse the count).
- Each line was joined to the same-arm select block it falls within,
  using the 15 anchored same-arm select blocks from Subtask 2
  (sblocks 0–10 = trials 0–10; sblocks 11+12 = trial 11's two arm-0
  retrieval bursts; sblocks 13+14 = the trials 12–14 arm-8 group).
- **Arm cross-check: 0 mismatches.** Every fail-open line's logged arm
  equals the anchored select-block arm for the trial it was assigned to.
  No mismatch had to be silently reconciled.

## The rescue detail (the diagnostically important part)

For trials 5–10 the harness table shows `audit_inferred` / 1 injected —
which *looks* like a normal success. It was not:

- Each of these trials logged `similarity_threshold=V (arm A) would drop
  all N result(s) but this arm is still bootstrapping … failing open`
  (the `still bootstrapping` branch). That means the raw retrieval at
  that arm's threshold matched **zero** rows above threshold, and the
  bootstrap fail-open (selected arm's `arm_update_count <
  BOOTSTRAP_MIN_UPDATES`) forced the full set to be kept so ≥1 id could
  reach `report_reward`.
- The bootstrap-event count **rises with the arm/threshold** (arm 5: 2,
  arm 6: 5, arm 7: 7, arms 8/9/10: 10 each) — i.e. the higher the
  similarity threshold the bandit picked, the more retrieval attempts
  within that trial wiped out and needed rescuing. This is the
  gate-over-rejection signal: at thresholds ≥0.5 the genuinely-relevant
  rows (similarities ~0.45–0.65, the documented calibration band) fall
  below the bar and only survive because the arm wasn't yet validated.
- Once arm 8 (0.8) accrued reward and passed bootstrap, trials 12–14
  flipped to the `honoring converged arm` branch: the same wipeout is
  now **honored** (30 events, 0 rescued) → 0 injected → `unknown`.

So the *same* over-rejection is present in trials 5–14; the only thing
that changes at trial 12 is that fail-open stops masking it because the
arm is now trusted.

## Why the counts are what they are (not 15 = 74)

74 events ≠ 15 selects because each interaction issues multiple
retrieval attempts (audit + injection retrievals, ~5 select calls per
trial), and every attempt that would wipe out logs one fail-open line.
Low-arm trials (0–4, 11) logged **zero** fail-open lines (nothing wiped),
so the 74 events concentrate entirely in the six rescued trials (5–10 =
44) and the three honored trials (12–14 = 30).

## Caveats

- **Kernel.log timestamps are second-resolution**, while some select
  events share a second; assignment used same-arm + windowed-time match,
  which is unambiguous here (arms are monotonic across the sweep, so a
  given arm value maps to exactly one trial window except arm 0 and
  arm 8, which recur — those were disambiguated by the non-overlapping
  time windows: arm-0 at trials 0 & 11, arm-8 at trial 8 (bootstrap) vs
  trials 12–14 (honored), and the boot/honor branch label itself
  separates them).
- Per-trial split **within** the 12–14 group is still LOW-confidence
  (no reward anchor, per Subtask 2); the 30 honored events are reported
  as a group, not split 10/10/10. The group total and its arm (8/0.8)
  are HIGH-confidence.
- This is a single 1×15 run; the rescue pattern is evidence about *this*
  run's gate behavior, consistent with the documented embedding-space
  calibration caveat, not a new general claim.
