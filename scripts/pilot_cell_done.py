"""
Exit 0 if a results file is a finished pilot cell: every trial present,
and the only failed trials are writer failures (Subtask 9: counted and
reported, not scored). A judge or pipeline failure needs a re-run.
"""
import json
import sys


def cell_done(path: str, trials: int) -> bool:
    """Return whether the cell at ``path`` needs no re-run."""
    try:
        with open(path) as handle:
            rows = json.load(handle)["conditions"][0]["trials"]
    except (OSError, ValueError, KeyError, IndexError):
        return False
    return len(rows) == trials and all(
        not row.get("failed") or row.get("writer_failed") for row in rows
    )


if __name__ == "__main__":
    sys.exit(0 if cell_done(sys.argv[1], int(sys.argv[2])) else 1)
