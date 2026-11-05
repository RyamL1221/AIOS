"""
Before/after check for the kernel retrieval path.

Replays a seeded, fixed set of kernel_shared-shaped writes and one chat
query per user over real HTTP against a running kernel. The benchmark
harness cannot do this: it has no seed, and its agents write LLM-generated
text, so two of its runs never hold the same memories.

The injected block is captured on the kernel side (see
docs/RETRIEVAL_PATH.md for the temporary capture patch). Run once per code
state with its own label, then compare:

    python scripts/retrieval_behavior_check.py run --label before --out a.json
    python scripts/retrieval_behavior_check.py run --label after --out b.json
    python scripts/retrieval_behavior_check.py compare a.json b.json
"""
import argparse
import json
import random
import re
import sys
import time

import requests

SEED = 20261101
TRIALS = 10
MODEL = {"name": "qwen2.5:7b", "backend": "ollama"}

NAMES = ["Ana", "Bo", "Chen", "Dee", "Eli", "Fay", "Gus", "Hana", "Ivo", "Jo"]
ROLES = ["analyst", "nurse", "teacher", "pilot", "chef", "editor"]
TOOLS = ["Python", "Excel", "Figma", "Jira", "Notion", "Rust"]
PROJECTS = ["budget", "migration", "launch", "audit", "survey", "roadmap"]


def build_trial(index: int) -> dict:
    """Return the memories and the chat query of one seeded trial."""
    rng = random.Random(SEED + index)
    name = NAMES[index % len(NAMES)]
    project = rng.choice(PROJECTS)
    profile = json.dumps({
        "user_name": name,
        "role": rng.choice(ROLES),
        "preferred_tool": rng.choice(TOOLS),
    })
    task = json.dumps({
        "project": project,
        "status": rng.choice(["blocked", "on track", "late"]),
        "next_step": f"review the {project} draft",
    })
    memories = [
        ("profile_agent", profile, "profile", "shared"),
        ("task_agent", task, "task_context", "shared"),
        ("profile_agent", f"private note {index} about {name}",
         "profile", "private"),
    ]
    for turn in range(rng.randint(0, 3)):
        memories.append((
            "assistant_agent",
            f"User: question {turn} on {project}\nAssistant: answer {turn}",
            "conversation",
            "private",
        ))
    if index % 3 == 0:
        # Exact-content duplicate across two writers.
        memories.append(("task_agent", profile, "profile", "shared"))
    return {
        "memories": memories,
        "query": f"What should I do next on the {project} work?",
    }


def post_query(base_url: str, body: dict) -> dict:
    """POST one request to the kernel's /query endpoint."""
    resp = requests.post(f"{base_url}/query", json=body, timeout=300)
    resp.raise_for_status()
    return resp.json()


def write_memory(base_url, user_id, agent, content, mtype, policy) -> None:
    """Write one memory through the agent-facing path."""
    post_query(base_url, {
        "query_type": "memory",
        "agent_name": agent,
        "query_data": {
            "query_class": "memory",
            "operation_type": "add_memory",
            "params": {
                "content": content,
                "metadata": {
                    "user_id": user_id,
                    "owner_agent": agent,
                    "memory_type": mtype,
                    "sharing_policy": policy,
                },
            },
        },
    })


def chat(base_url: str, user_id: str, query: str) -> dict:
    """Send the chat query that triggers injection."""
    return post_query(base_url, {
        "query_type": "llm",
        "agent_name": "assistant_agent",
        "user_id": user_id,
        "query_data": {
            "query_class": "llm",
            "llms": [MODEL],
            "messages": [{"role": "user", "content": query}],
            "action_type": "chat",
            "max_new_tokens": 16,
            "temperature": 0.0,
        },
    })


def parse_block(block) -> list:
    """Return a block's memory lines, without bullets or timestamps, in
    either block format (``aios.memory.pipeline.formatter``)."""
    from aios.memory.pipeline.formatter import (
        BLOCK_FOOTER, BLOCK_HEADER, COMPACT_HEADER,
    )
    if not block:
        return []
    if block.startswith(COMPACT_HEADER + "\n"):
        body = block.split("\n", 1)[1]
        pattern = r"(?m)^- "
    elif block.startswith(BLOCK_HEADER):
        body = block.split("\n", 3)[3].rsplit(BLOCK_FOOTER, 1)[0]
        pattern = r"(?m)^- \[[^\]]*\] "
    else:
        return []
    return [
        part.strip() for part in re.split(pattern, body) if part.strip()
    ]


def run(args) -> int:
    """Replay every trial and save the injected sets."""
    capture = {}
    open(args.capture, "w").close()
    results = []
    for index in range(TRIALS):
        trial = build_trial(index)
        user_id = f"rbc_{args.label}_{int(time.time())}_{index}"
        for agent, content, mtype, policy in trial["memories"]:
            write_memory(args.base_url, user_id, agent, content, mtype, policy)
        response = chat(args.base_url, user_id, trial["query"])
        results.append({
            "index": index,
            "user_id": user_id,
            "written": len(trial["memories"]),
            "diagnostics": response.get("injection_diagnostics"),
        })

    with open(args.capture) as handle:
        for line in handle:
            row = json.loads(line)
            capture[row["user_id"]] = row["block"]
    for row in results:
        row["injected"] = parse_block(capture.get(row["user_id"]))
    with open(args.out, "w") as handle:
        json.dump(results, handle, indent=2)
    print(f"wrote {args.out}: {len(results)} trials, injected counts "
          f"{[len(r['injected']) for r in results]}")
    return 0


def compare(args) -> int:
    """Compare two saved runs; exit non-zero on any set difference."""
    with open(args.before) as handle:
        before = json.load(handle)
    with open(args.after) as handle:
        after = json.load(handle)
    bad = 0
    for old, new in zip(before, after):
        same_set = sorted(old["injected"]) == sorted(new["injected"])
        same_order = old["injected"] == new["injected"]
        diag = new.get("diagnostics") or {}
        fired_cap = diag.get("after_threshold", 0) > diag.get("after_cap", 0)
        fired_top_k = diag.get("shared_fetched", 0) > 20
        bad += not same_set
        print(f"trial {old['index']}: n={len(old['injected'])}/"
              f"{len(new['injected'])} set={'same' if same_set else 'DIFF'} "
              f"order={'same' if same_order else 'DIFF'} "
              f"cap_fired={fired_cap} top_k_fired={fired_top_k}")
    print("MATCH" if not bad else f"{bad} TRIALS DIFFER")
    return 1 if bad else 0


def main() -> int:
    """Parse arguments and dispatch."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--label", required=True)
    run_parser.add_argument("--out", required=True)
    run_parser.add_argument("--capture", required=True)
    run_parser.add_argument("--base-url", default="http://localhost:8000")
    compare_parser = sub.add_parser("compare")
    compare_parser.add_argument("before")
    compare_parser.add_argument("after")
    args = parser.parse_args()
    return run(args) if args.command == "run" else compare(args)


if __name__ == "__main__":
    sys.exit(main())
