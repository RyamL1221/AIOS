"""
Exit 0 if a results file is a finished pilot cell: every trial present,
and the only failed trials are writer failures (Subtask 9: counted and
reported, not scored). A judge or pipeline failure, or a memory backend
that failed silently (``backend_extraction_failed``), needs a re-run.

``--strict`` (the pre-registered pilot, Subtask 11, docs/PILOT.md): no
trial may fail at all. ``--commit`` / ``--kernel-commit``: the results
file must record exactly that harness / kernel commit, never ``-dirty``.

    python3 scripts/pilot_cell_done.py <results.json> <trials>
        [--strict] [--commit SHA] [--kernel-commit SHA]
"""
import argparse
import json
import sys
from typing import Optional


def cell_done(path: str, trials: int, strict: bool = False,
              commit: Optional[str] = None,
              kernel_commit: Optional[str] = None) -> bool:
    """Return whether the cell at ``path`` needs no re-run."""
    try:
        with open(path) as handle:
            data = json.load(handle)
        rows = data["conditions"][0]["trials"]
    except (OSError, ValueError, KeyError, IndexError):
        return False
    meta = data.get("experiment_metadata") or {}
    if commit and meta.get("git_commit") != commit:
        return False
    if kernel_commit and meta.get("kernel_git_commit") != kernel_commit:
        return False
    if strict:
        return len(rows) == trials and not any(r.get("failed") for r in rows)
    return len(rows) == trials and all(
        not row.get("failed") or row.get("writer_failed") for row in rows
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("trials", type=int)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--commit")
    parser.add_argument("--kernel-commit")
    args = parser.parse_args(argv)
    done = cell_done(args.path, args.trials, args.strict, args.commit,
                     args.kernel_commit)
    return 0 if done else 1


if __name__ == "__main__":
    sys.exit(main())
