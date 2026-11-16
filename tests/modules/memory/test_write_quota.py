"""The write quota (NeurIPS Subtask 18, docs/STRESS_DIMENSIONS.md,
"flood10, flood50"): at most ``max_writes`` accepted writes per writer,
per user, per session; with ``dedupe``, a write whose normalized text
the writer already stored for the user in that session is rejected and
not counted. Off by default. Tested on the quota, on the library's
write path and on the kernel's, where the session is the kernel
session the request was bound to."""
import threading
import time
from unittest.mock import patch

import pytest

from cerebrum.memory.apis import MemoryQuery

from aios.memory.manager import MemoryManager
from aios.memory.note import MemoryNote
from aios.memory.pipeline import (
    MemoryPipeline,
    PipelineSettings,
    QuotaSettings,
    WriteQuota,
)
from aios.memory.providers.in_house import InHouseProvider
from aios.syscall.memory import MemorySyscall

USER = "alice"
FLOODER = "travel_agent"
OTHER = "profile_agent"
ON = {"enabled": True, "max_writes": 4, "dedupe": True}


# --- settings -----------------------------------------------------------

def test_the_quota_is_off_by_default_and_reported_with_the_pipeline():
    settings = PipelineSettings.from_memory_config({})
    assert settings.write_quota == {
        "enabled": False, "max_writes": 4, "dedupe": True,
    }
    assert PipelineSettings().write_quota == settings.write_quota
    copied = PipelineSettings.from_memory_config(
        PipelineSettings.from_memory_config(
            {"write_quota": {"enabled": True, "max_writes": 2}}
        ).as_dict()
    )
    assert copied.write_quota == {
        "enabled": True, "max_writes": 2, "dedupe": True,
    }


@pytest.mark.parametrize("block", [
    {"enabled": "yes"},
    {"max_writes": 0},
    {"max_writes": True},
    {"dedupe": 1},
    {"limit": 4},
])
def test_a_bad_quota_block_is_refused(block):
    with pytest.raises(ValueError):
        QuotaSettings.from_config(block)
    with pytest.raises(ValueError):
        PipelineSettings.from_memory_config({"write_quota": block})


# --- the quota ----------------------------------------------------------

def test_the_quota_counts_per_user_writer_and_session():
    quota = WriteQuota(QuotaSettings(enabled=True, max_writes=2))
    assert quota.admit(USER, FLOODER, 1, "a") is None
    assert quota.admit(USER, FLOODER, 1, "b") is None
    assert quota.admit(USER, FLOODER, 1, "c") == "quota"
    # Each other bucket has its own count.
    assert quota.admit(USER, FLOODER, 2, "c") is None
    assert quota.admit(USER, OTHER, 1, "c") is None
    assert quota.admit("bob", FLOODER, 1, "c") is None
    assert quota.counts()[(USER, FLOODER, "1")] == 2


def test_a_duplicate_is_rejected_and_not_counted():
    """Re-cased or re-punctuated, a text normalizes to the stored one;
    a prefix makes it another text."""
    quota = WriteQuota(QuotaSettings(enabled=True, max_writes=2))
    assert quota.admit(USER, FLOODER, 1, "I fly with Wizzair.") is None
    assert quota.admit(USER, FLOODER, 1, "i  fly with wizzair") == \
        "duplicate"
    assert quota.admit(USER, FLOODER, 1, "Again: I fly with Wizzair.") \
        is None
    assert quota.admit(USER, FLOODER, 1, "Reminder: I fly with Wizzair.") \
        == "quota"
    assert quota.counts()[(USER, FLOODER, "1")] == 2


def test_without_dedupe_a_duplicate_counts():
    quota = WriteQuota(QuotaSettings(enabled=True, max_writes=2,
                                     dedupe=False))
    assert quota.admit(USER, FLOODER, 1, "x") is None
    assert quota.admit(USER, FLOODER, 1, "x") is None
    assert quota.admit(USER, FLOODER, 1, "x") == "quota"


def test_a_disabled_quota_admits_everything():
    quota = WriteQuota()
    for _ in range(10):
        assert quota.admit(USER, FLOODER, 1, "same") is None
    assert quota.counts() == {}


def test_a_refund_frees_the_slot_and_the_text():
    quota = WriteQuota(QuotaSettings(enabled=True, max_writes=1))
    assert quota.admit(USER, FLOODER, 1, "x") is None
    quota.refund(USER, FLOODER, 1, "x")
    assert quota.admit(USER, FLOODER, 1, "x") is None


def test_concurrent_writes_are_counted_once_each():
    """Eight threads of one writer race 10 writes each: exactly
    ``max_writes`` are admitted."""
    quota = WriteQuota(QuotaSettings(enabled=True, max_writes=4,
                                     dedupe=False))
    admitted = []
    start = threading.Barrier(8)

    def flood(n):
        start.wait()
        for k in range(10):
            if quota.admit(USER, FLOODER, 1, f"{n}-{k}") is None:
                admitted.append((n, k))

    threads = [threading.Thread(target=flood, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(admitted) == 4


# --- the library's write path ------------------------------------------

def note(content, writer=FLOODER, session=1, user=USER):
    return MemoryNote(content=content, metadata={
        "owner_agent": writer, "user_id": user, "memory_type": "calendar",
        "sharing_policy": "shared", "session": session,
    })


def pipeline(block=ON):
    return MemoryPipeline(
        InHouseProvider(),
        PipelineSettings.from_memory_config({"write_quota": block}),
    )


def test_a_rejected_write_stores_nothing_and_says_why():
    memory = pipeline()
    stored = [memory.write(FLOODER, USER, note(f"Note {k}.")) for k in
              range(4)]
    assert all(stored)
    outcome = {}
    assert memory.write(FLOODER, USER, note("Note 4."),
                        outcome=outcome) == ""
    assert outcome["quota_rejected"] == "quota"
    assert outcome["suppressed"] is False
    duplicate = {}
    assert memory.write(FLOODER, USER, note("note 0"),
                        outcome=duplicate) == ""
    assert duplicate["quota_rejected"] == "duplicate"
    rows = memory.provider.list(USER, 100)
    assert sorted(r.content for r in rows) == [
        "Note 0.", "Note 1.", "Note 2.", "Note 3.",
    ]
    # Another writer and another session are not limited by it.
    assert memory.write(OTHER, USER, note("Mine.", writer=OTHER))
    assert memory.write(FLOODER, USER, note("Later.", session=2))


def test_a_rejected_write_releases_its_barrier_sequence():
    """A retrieval after a rejected write does not wait for it."""
    memory = MemoryPipeline(
        _AsyncCommit(),
        PipelineSettings.from_memory_config({
            "write_quota": dict(ON, max_writes=1),
            "write_barrier": {"enabled": True, "timeout_ms": 3000},
        }),
    )
    assert memory.write(FLOODER, USER, note("One."))
    assert memory.write(FLOODER, USER, note("Two.")) == ""
    started = time.monotonic()
    _, diagnostics = memory.retrieve("assistant_agent", USER, "one")
    assert time.monotonic() - started < 1.0
    assert diagnostics["barrier_waits"] == [
        {"user_id": USER, "outcome": "DRAINED"},
    ]


def test_a_failed_write_is_refunded():
    memory = pipeline(dict(ON, max_writes=1))
    with patch.object(memory.provider, "add",
                      side_effect=RuntimeError("store down")):
        with pytest.raises(RuntimeError):
            memory.write(FLOODER, USER, note("One."))
    assert memory.write(FLOODER, USER, note("One."))


def test_the_session_key_wins_over_the_notes_session():
    memory = pipeline(dict(ON, max_writes=1))
    assert memory.write(FLOODER, USER, note("A.", session=1),
                        session_key="token-1")
    # Same metadata.session, another kernel session: another bucket.
    assert memory.write(FLOODER, USER, note("B.", session=1),
                        session_key="token-2")
    assert memory.write(FLOODER, USER, note("C.", session=1),
                        session_key="token-1") == ""


def test_a_write_reports_its_barrier_sequence_and_commit_time():
    memory = pipeline({})
    before = time.time()
    outcome = {}
    assert memory.write(FLOODER, USER, note("A."), outcome=outcome)
    assert before <= outcome["committed_at"] <= time.time()
    assert outcome["barrier_seq"] >= 1
    assert "quota_rejected" not in outcome


class _AsyncCommit(InHouseProvider):
    """The in-memory provider, as a store whose writes the barrier must
    wait for."""

    synchronous_commit = False


# --- the kernel ---------------------------------------------------------

def kernel(block=ON):
    with patch("aios.memory.manager.global_config") as config:
        config.get_memory_config.return_value = {
            "provider": "in-memory", "write_quota": block,
        }
        config.get_storage_config.return_value = {}
        return MemoryManager()


def kernel_add(manager, content, writer=FLOODER, session=1, token=None):
    syscall = MemorySyscall(writer, MemoryQuery(
        operation_type="add_memory",
        params={"content": content, "metadata": {
            "owner_agent": writer, "user_id": USER,
            "memory_type": "calendar", "sharing_policy": "shared",
            "session": session,
        }},
    ))
    syscall.session_token = token
    manager.stamp_syscall(syscall)
    return manager.address_request(syscall)


def test_the_kernel_holds_one_quota_for_every_request():
    """Each request gets its own pipeline, over the kernel's one quota,
    so the count carries across requests."""
    manager = kernel()
    for k in range(4):
        response = kernel_add(manager, f"Note {k}.")
        assert response.success and response.memory_id
    response = kernel_add(manager, "Note 4.")
    assert response.success and response.memory_id == ""
    assert response.metadata["quota_rejected"] == "quota"
    assert manager.pipeline_settings().write_quota == ON


def test_the_kernel_counts_per_kernel_session():
    manager = kernel(dict(ON, max_writes=1))
    assert kernel_add(manager, "A.", token="s1").memory_id
    assert kernel_add(manager, "B.", token="s2").memory_id
    assert kernel_add(manager, "C.", token="s1").memory_id == ""


def test_the_kernel_quota_is_off_by_default():
    manager = kernel({})
    for k in range(8):
        assert kernel_add(manager, "Same text.").memory_id
