#!/usr/bin/env python3
"""Empirical collision re-check across ALL real trial identities post-fix.

Subtask 3 (truncation-collision fix verification). Confirms, at the scale
the 450-trial re-run operates at, that the patched
``Mem0Provider._collection_name_for_user`` (hash-suffix on truncation)
eliminates every previously-found collision and introduces no new one.

Methodology (identical to the original investigation):
  1. Extract all distinct ``user_id`` values from ``kernel.log`` with the
     same ``grep -oE "user_id=..."`` approach (char class includes the
     period so ids like ``aiden_b._jenkins…`` are captured) — yielding
     the same 453-identity set used before.
  2. Import and call the ACTUAL patched ``_collection_name_for_user``
     (loaded by file path, no reimplementation) against all 453.
  3. Compare against a faithful reproduction of the PRE-FIX naming to
     report the collision delta (pre 451 distinct / 2 collision groups
     vs post 453 distinct / 0).
  4. Confirm no NEW collision among the previously-safe identities and
     that every post-fix name still meets ChromaDB naming constraints.

Verification-only: imports the provider as-is, modifies no production
code. Reads ``kernel.log`` from the repo root.

Run:
    .venv/bin/python scripts/verify_collision_free_real_user_ids.py
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from collections import defaultdict

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Same regex as the `grep -oE "user_id=[A-Za-z0-9_.-]+"` extraction that
# produced the documented 453-identity set (the period matters — ids like
# "aiden_b._jenkins…" contain one).
_USER_ID_RE = re.compile(r"user_id=([A-Za-z0-9_.-]+)")


def _load_module(name: str, rel_path: str):
    """Load a module by file path, bypassing package __init__ side effects
    (the providers __init__ pulls in sentence_transformers via the
    in-house provider, unneeded here)."""
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(_ROOT, rel_path)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _extract_real_user_ids(log_path: str) -> list[str]:
    """Return the sorted distinct user_ids found in kernel.log."""
    seen = set()
    with open(log_path, "r", errors="ignore") as fh:
        for line in fh:
            for m in _USER_ID_RE.findall(line):
                seen.add(m)
    return sorted(seen)


def _pre_fix_collection_name(provider, user_id: str) -> str:
    """Faithful reproduction of the PRE-FIX _collection_name_for_user
    (bare truncation, no hash suffix) — for the pre/post delta only."""
    s = provider._sanitize_collection_component(user_id)
    prefix = provider._sanitize_collection_component(
        provider._default_collection_prefix
    )
    max_user_len = 63 - len(prefix) - 1
    if max_user_len < 3:
        prefix = "mem0"
        max_user_len = 63 - len(prefix) - 1
    s = s[:max_user_len].strip("_-")
    if not s:
        s = "default"
    if not s[-1].isalnum():
        s = f"{s}u"
    name = f"{prefix}_{s}"
    if len(name) < 3:
        name = "mem0_default"
    name = name[:63].rstrip("_-")
    if not name[-1].isalnum():
        name = f"{name}u"
    return name


def _collisions(ids, name_fn):
    buckets = defaultdict(list)
    for uid in ids:
        buckets[name_fn(uid)].append(uid)
    colliding = {n: us for n, us in buckets.items() if len(us) > 1}
    return len(buckets), colliding


def main() -> int:
    _load_module(
        "aios.memory.providers.base", "aios/memory/providers/base.py"
    )
    mem0 = _load_module(
        "aios.memory.providers.mem0", "aios/memory/providers/mem0.py"
    )
    provider = mem0.Mem0Provider.__new__(mem0.Mem0Provider)
    provider._default_collection_prefix = "mem0_memories"

    ids = _extract_real_user_ids(os.path.join(_ROOT, "kernel.log"))
    print(f"distinct real user_ids extracted from kernel.log: {len(ids)}")

    pre_distinct, pre_coll = _collisions(
        ids, lambda u: _pre_fix_collection_name(provider, u)
    )
    print(f"\nPRE-FIX : {pre_distinct} distinct collection names, "
          f"{len(pre_coll)} collision group(s)")
    for name, us in pre_coll.items():
        print(f"    COLLISION -> {name!r}")
        for u in us:
            print(f"        {u}")

    post_distinct, post_coll = _collisions(
        ids, provider._collection_name_for_user
    )
    print(f"\nPOST-FIX: {post_distinct} distinct collection names, "
          f"{len(post_coll)} collision group(s)")
    for name, us in post_coll.items():
        print(f"    COLLISION -> {name!r}: {us}")

    # No NEW collision among identities that were safe pre-fix.
    pre_colliding = {u for us in pre_coll.values() for u in us}
    safe_ids = [u for u in ids if u not in pre_colliding]
    _, new_coll = _collisions(
        safe_ids, provider._collection_name_for_user
    )

    # ChromaDB naming constraints on every post-fix name.
    bad = []
    for u in ids:
        n = provider._collection_name_for_user(u)
        if not (3 <= len(n) <= 63 and n[0].isalnum() and n[-1].isalnum()):
            bad.append((u, n))

    print(f"\nPreviously-safe identities (non-colliding pre-fix): "
          f"{len(safe_ids)}")
    print(f"NEW collisions among previously-safe set: {len(new_coll)}")
    print(f"Post-fix names violating ChromaDB constraints: {len(bad)}")

    ok = (
        post_distinct == len(ids)
        and len(post_coll) == 0
        and len(new_coll) == 0
        and len(bad) == 0
    )
    print("\n=== RESULT ===")
    print(f"pre-fix : {pre_distinct} distinct / {len(pre_coll)} collisions")
    print(f"post-fix: {post_distinct} distinct / {len(post_coll)} collisions")
    print("Zero remaining collisions across all real identities:",
          "CONFIRMED" if len(post_coll) == 0 else "FAIL")
    print("No new collision among previously-safe identities:",
          "CONFIRMED" if len(new_coll) == 0 else "FAIL")
    print("OVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
