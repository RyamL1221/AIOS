"""Check that every row a backend stored for a run's users carries the
cross-agent metadata (Subtask 9). With Mem0 extraction one write can
become several fact rows; each must have ``owner_agent``, ``user_id``,
``memory_type`` and ``sharing_policy``, and a profile or task-context
fact also the writer's ``structured`` fields.

    python scripts/check_fact_metadata.py <chroma dir> <results.json>...

Reads every collection in the Chroma directory and keeps the rows of
the users the results files wrote for. Exit 1 on any incomplete row.
"""
import json
import sys
from collections import Counter

import chromadb
from chromadb.config import Settings

REQUIRED = ("owner_agent", "user_id", "memory_type", "sharing_policy")


def run_users(paths):
    users = set()
    for path in paths:
        data = json.load(open(path))
        for condition in data["conditions"]:
            for trial in condition["trials"]:
                users |= {w["user_id"] for w in trial["written_memories"]}
    return users


def main() -> int:
    store, results = sys.argv[1], sys.argv[2:]
    users = run_users(results)
    client = chromadb.PersistentClient(
        path=store, settings=Settings(anonymized_telemetry=False)
    )
    rows, bad = Counter(), []
    per_user = Counter()
    for collection in client.list_collections():
        got = client.get_collection(collection.name).get(
            include=["metadatas", "documents"]
        )
        for doc, meta in zip(got["documents"], got["metadatas"]):
            meta = meta or {}
            if meta.get("user_id") not in users:
                continue
            kind = meta.get("memory_type", "")
            rows[kind] += 1
            per_user[(meta["user_id"], kind)] += 1
            missing = [k for k in REQUIRED if not meta.get(k)]
            if kind in ("profile", "task_context") and \
                    not meta.get("structured"):
                missing.append("structured")
            if missing:
                bad.append((meta.get("user_id"), kind, doc[:60], missing))
    seen = {u for u, _ in per_user}
    print(f"users {len(users)}, with rows {len(seen)}; rows by type "
          f"{dict(rows)}")
    for kind in sorted(rows):
        counts = [n for (u, k), n in per_user.items() if k == kind]
        print(f"  {kind}: {min(counts)}-{max(counts)} rows per user")
    for row in bad:
        print("INCOMPLETE", row)
    print("OK" if not bad and seen == users else "PROBLEMS")
    return 0 if not bad and seen == users else 1


if __name__ == "__main__":
    sys.exit(main())
