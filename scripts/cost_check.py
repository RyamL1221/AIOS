"""Subtask 7 acceptance check on one cell's results: every trial has
assistant, writer and backend token counts, and the latency breakdown
reconciles with the measured latency.

    python scripts/cost_check.py <results_<method>.json> --method <method>

Kernel conditions write with ``infer=False``, so they must make 0
backend LLM calls; native_mem0 makes one per write (>= 3 per trial).
"""
import argparse
import json
import statistics
import sys

TOLERANCE = 0.10


def check(trials: list, method: str) -> list:
    problems = []
    rows = []
    for t in trials:
        i = t["trial_index"]
        if t.get("failed"):
            problems.append(f"trial {i} failed: {t.get('error_message')}")
            continue
        backend = t["backend_llm_tokens"]
        if t["token_usage"]["total_tokens"] <= 0:
            problems.append(f"trial {i}: no assistant tokens")
        if t["writer_tokens"]["total_tokens"] <= 0:
            problems.append(f"trial {i}: no writer tokens")
        if t["embedding_tokens"]["calls"] <= 0:
            problems.append(f"trial {i}: no embedding calls")
        if method == "native_mem0":
            if backend["calls"] < 3 or backend["total_tokens"] <= 0:
                problems.append(f"trial {i}: backend {backend}")
        elif backend["calls"] != 0:
            problems.append(f"trial {i}: kernel made backend calls {backend}")
        latency = t["latency_breakdown"]
        measured = t["latency_seconds"] * 1000
        parts = latency["kernel_overhead_ms"] + latency["llm_ms"]
        wait = latency.get("schedule_wait_ms") or 0.0
        rows.append({
            "trial": i, "latency_ms": measured,
            "overhead_ms": latency["kernel_overhead_ms"],
            "llm_ms": latency["llm_ms"], "schedule_wait_ms": wait,
            # kernel_overhead_ms includes the scheduler's wait; the gap
            # without it is what the four memory stages alone leave.
            "gap": (measured - parts) / measured,
            "gap_without_wait": (measured - parts + wait) / measured,
            "backend_calls": backend["calls"],
            "backend_tokens": backend["total_tokens"],
            "embedding_calls": t["embedding_tokens"]["calls"],
            "embedding_tokens": t["embedding_tokens"]["total_tokens"],
            "assistant_tokens": t["token_usage"]["total_tokens"],
            "writer_tokens": t["writer_tokens"]["total_tokens"],
        })
        if abs(rows[-1]["gap"]) > TOLERANCE:
            problems.append(
                f"trial {i}: overhead + llm = {parts:.0f} ms vs "
                f"latency {measured:.0f} ms ({rows[-1]['gap']:+.1%})"
            )
    return problems, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results")
    parser.add_argument("--method", required=True)
    args = parser.parse_args()
    with open(args.results) as handle:
        trials = json.load(handle)["conditions"][0]["trials"]
    problems, rows = check(trials, args.method)
    for row in rows:
        print(json.dumps({k: round(v, 3) if isinstance(v, float) else v
                          for k, v in row.items()}))
    if rows:
        for key in ("gap", "gap_without_wait", "overhead_ms", "llm_ms",
                    "schedule_wait_ms"):
            values = [r[key] for r in rows]
            print(f"{key}: mean {statistics.mean(values):.3f} "
                  f"min {min(values):.3f} max {max(values):.3f}")
    print(f"{len(rows)} trials checked, {len(problems)} problems")
    for problem in problems:
        print("PROBLEM", problem)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
