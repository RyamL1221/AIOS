"""Known issue 31: the kernel's Mem0 per-user collection names kept only
the first 49 characters of a long user id, so two ids sharing that
prefix shared a collection. Long ids now keep a hash of the full id;
ids that fit keep their old name."""
import re

from aios.memory.providers.mem0 import Mem0Provider

VALID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,61}[a-zA-Z0-9]$")


def provider(prefix="mem0_memories"):
    p = Mem0Provider.__new__(Mem0Provider)
    p._default_collection_prefix = prefix
    return p


def test_long_ids_sharing_a_prefix_get_different_collections():
    p = provider()
    base = "jordan_mcallister_pilot-qwen-kmem0-kernel_shared-h2"
    a = p._collection_name_for_user(base + "_t10__kernel_shared")
    b = p._collection_name_for_user(base + "_t11__kernel_shared")
    assert a != b
    assert len(a) <= 63 and VALID.match(a) and VALID.match(b)


def test_ids_that_fit_keep_their_name():
    p = provider()
    assert p._collection_name_for_user("alice") == "mem0_memories_alice"
    uid = "jordan_mcallister_h10-kmem0-kernel_shared-h0_t0"  # 47 chars
    assert p._collection_name_for_user(uid) == f"mem0_memories_{uid}"


def test_the_name_is_stable():
    p = provider()
    uid = "x" * 80
    assert p._collection_name_for_user(uid) == \
        p._collection_name_for_user(uid)


def test_a_long_prefix_still_gives_valid_distinct_names():
    p = provider(prefix="p" * 52)
    a = p._collection_name_for_user("user_" + "a" * 40 + "1")
    b = p._collection_name_for_user("user_" + "a" * 40 + "2")
    assert a != b and VALID.match(a) and VALID.match(b)
