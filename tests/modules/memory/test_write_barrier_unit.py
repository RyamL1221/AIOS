"""
Unit tests for ``MemoryWriteBarrier`` in isolation.

Validates the barrier primitive (``aios/memory/write_barrier.py``)
without any kernel wiring -- no ``MemoryManager``, ``SyscallExecutor``,
``ContextInjector``, or provider double is involved.  The barrier is
exercised directly so that any later wiring failures can be diagnosed
against a known-good primitive.

Cases covered (one per ``unittest.TestCase`` test method):

1. ``acquire`` is monotonic under concurrent calls (N=20 threads;
   every returned ``seq_no`` is distinct and the set is ``{1..N}``).
2. ``release`` notifies waiters even when ``success=False``.
3. ``snapshot`` returns the current high-water mark and ignores
   ``user_id`` values that have never had a pending write.
4. ``wait_until_drained`` returns ``BYPASSED`` for empty / ``None``
   ``user_id``.
5. ``wait_until_drained`` returns ``BYPASSED`` when ``_enabled`` is
   ``False``.
6. ``wait_until_drained`` returns ``TIMEOUT`` when ``release`` is
   never called and the configured timeout elapses; a WARNING log
   record naming the stuck sequence numbers is emitted.
7. ``wait_until_drained`` returns ``DRAINED`` when every relevant
   pending write is released before the deadline.
8. Pending writes for ``user_id=U_a`` do not block a wait on
   ``user_id=U_b`` -- the disjoint wait returns within ~50 ms while
   the ``U_a`` writes remain parked.
"""

import logging
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed

from aios.memory.write_barrier import MemoryWriteBarrier, WaitOutcome


class MemoryWriteBarrierUnitTests(unittest.TestCase):
    """Isolated unit tests for ``MemoryWriteBarrier``."""

    # ------------------------------------------------------------------
    # 1. Monotonic acquire under concurrency
    # ------------------------------------------------------------------
    def test_acquire_is_monotonic_under_concurrent_calls(self):
        """Concurrent ``acquire`` calls return distinct seq_nos covering [1..N]."""
        barrier = MemoryWriteBarrier(config={})
        n = 20

        # Stagger the start of every worker on a barrier so all 20
        # threads contend on ``_lock`` at the same instant rather than
        # serializing through ThreadPoolExecutor's queue.
        start_gate = threading.Barrier(n)

        def _do_acquire(i: int) -> int:
            start_gate.wait()
            return barrier.acquire(f"user_{i}")

        with ThreadPoolExecutor(max_workers=n) as pool:
            futures = [pool.submit(_do_acquire, i) for i in range(n)]
            results = [f.result() for f in as_completed(futures)]

        self.assertEqual(
            len(set(results)),
            n,
            f"expected {n} distinct seq_nos, got {sorted(results)}",
        )
        self.assertEqual(
            sorted(results),
            list(range(1, n + 1)),
            "seq_nos must cover [1..N] with no gaps",
        )

        stats = barrier.stats()
        self.assertEqual(stats["last_acquired_seq"], n)
        self.assertEqual(stats["total_pending"], n)

    # ------------------------------------------------------------------
    # 2. release notifies waiters even on failure
    # ------------------------------------------------------------------
    def test_release_notifies_waiters_when_success_false(self):
        """A failed write still wakes a parked ``wait_until_drained``."""
        barrier = MemoryWriteBarrier(config={"timeout_ms": 5000})
        user_id = "alex"
        seq_no = barrier.acquire(user_id)
        snapshot = barrier.snapshot(user_id)

        outcomes: list[WaitOutcome] = []

        def _waiter() -> None:
            outcomes.append(
                barrier.wait_until_drained(user_id, snapshot)
            )

        waiter = threading.Thread(target=_waiter, daemon=True)
        waiter.start()

        # Give the waiter a chance to park on the condition variable
        # before we release.  100 ms is far below the 5 s timeout, so
        # if the notify fails the test surfaces a clear TIMEOUT.
        time.sleep(0.1)
        barrier.release(user_id, seq_no, success=False)

        waiter.join(timeout=2.0)
        self.assertFalse(
            waiter.is_alive(),
            "waiter should be released by the failure notify",
        )
        self.assertEqual(outcomes, [WaitOutcome.DRAINED])

    # ------------------------------------------------------------------
    # 3. snapshot returns the current high-water mark
    # ------------------------------------------------------------------
    def test_snapshot_returns_high_water_mark_and_ignores_unknown_users(
        self,
    ):
        """``snapshot`` reads the global counter regardless of user_id."""
        barrier = MemoryWriteBarrier(config={})

        # No acquires yet -> snapshot for any user is the initial
        # counter value (0).  The barrier still treats this as a
        # bypass because the seq is the sentinel.
        self.assertEqual(barrier.snapshot("nobody"), 0)

        seq_a = barrier.acquire("alex")
        seq_b = barrier.acquire("alex")

        # Snapshot for a *different* user reflects the global high-
        # water mark, not a per-user counter.  This is the contract
        # ``wait_until_drained`` relies on so later writes never
        # retroactively block earlier reads.
        self.assertEqual(barrier.snapshot("bob"), seq_b)
        self.assertEqual(barrier.snapshot("alex"), seq_b)

        # And acquires keep advancing the counter.
        seq_c = barrier.acquire("carol")
        self.assertEqual(seq_c, seq_b + 1)
        self.assertEqual(barrier.snapshot("nobody"), seq_c)

        # snapshot is a pure read -- no pending entry was created
        # for "nobody" or "bob".
        stats = barrier.stats()
        self.assertNotIn("nobody", stats["pending_by_user"])
        self.assertNotIn("bob", stats["pending_by_user"])

        # Drain so the test exits clean.
        barrier.release("alex", seq_a, success=True)
        barrier.release("alex", seq_b, success=True)
        barrier.release("carol", seq_c, success=True)

    # ------------------------------------------------------------------
    # 4. wait_until_drained BYPASSED for empty / None user_id
    # ------------------------------------------------------------------
    def test_wait_until_drained_bypassed_for_empty_user_id(self):
        """Empty / None user_id short-circuits to BYPASSED."""
        barrier = MemoryWriteBarrier(config={})

        # ``snapshot`` on the empty / None paths returns the sentinel,
        # which ``wait_until_drained`` also treats as BYPASSED.  Pass
        # a non-sentinel ``barrier_seq`` to prove the user_id check
        # alone is sufficient.
        self.assertEqual(
            barrier.wait_until_drained(None, barrier_seq=1),
            WaitOutcome.BYPASSED,
        )
        self.assertEqual(
            barrier.wait_until_drained("", barrier_seq=1),
            WaitOutcome.BYPASSED,
        )

    # ------------------------------------------------------------------
    # 5. wait_until_drained BYPASSED when barrier disabled
    # ------------------------------------------------------------------
    def test_wait_until_drained_bypassed_when_disabled(self):
        """When ``_enabled=False`` every wait returns BYPASSED."""
        barrier = MemoryWriteBarrier(config={"enabled": False})

        # Even a "real-looking" user_id and barrier_seq must short-
        # circuit when the global kill-switch is off.
        self.assertEqual(
            barrier.wait_until_drained("alex", barrier_seq=42),
            WaitOutcome.BYPASSED,
        )

        # And acquire also returns the sentinel on the disabled path,
        # so a wait against that sentinel is BYPASSED too.
        seq = barrier.acquire("alex")
        self.assertEqual(seq, 0)
        self.assertEqual(
            barrier.wait_until_drained("alex", barrier_seq=seq),
            WaitOutcome.BYPASSED,
        )

    # ------------------------------------------------------------------
    # 6. wait_until_drained TIMEOUT + WARNING log
    # ------------------------------------------------------------------
    def test_wait_until_drained_timeout_logs_warning_with_stuck_seqs(
        self,
    ):
        """Deadline elapses -> TIMEOUT + WARNING naming stuck seq_nos."""
        # 50 ms timeout keeps the test fast while still giving the
        # wait loop a real chance to park on the condition variable.
        barrier = MemoryWriteBarrier(config={"timeout_ms": 50})
        user_id = "alex"
        seq_a = barrier.acquire(user_id)
        seq_b = barrier.acquire(user_id)
        snapshot = barrier.snapshot(user_id)

        # ``release`` is never called -- both writes stay parked --
        # so the wait must hit the deadline and TIMEOUT.
        with self.assertLogs(
            "aios.memory.write_barrier", level=logging.WARNING
        ) as captured:
            t0 = time.monotonic()
            outcome = barrier.wait_until_drained(user_id, snapshot)
            elapsed = time.monotonic() - t0

        self.assertEqual(outcome, WaitOutcome.TIMEOUT)
        # A 50 ms timeout should not blow past 1 s even on a loaded
        # CI worker; the lower bound proves we actually waited.
        self.assertGreaterEqual(elapsed, 0.04)
        self.assertLess(elapsed, 1.0)

        # The WARNING record must name the still-pending sequence
        # numbers so operators can correlate stuck writes with
        # retrieval latency.
        warning_records = [
            r for r in captured.records if r.levelno == logging.WARNING
        ]
        self.assertTrue(warning_records, "expected a WARNING record")
        joined = "\n".join(r.getMessage() for r in warning_records)
        self.assertIn(repr(user_id), joined)
        self.assertIn(str(seq_a), joined)
        self.assertIn(str(seq_b), joined)
        self.assertIn("TIMEOUT", joined)

        # Drain so subsequent tests on the same module see a clean
        # registry; release on a stale snapshot is fine because we
        # captured the seq_nos directly.
        barrier.release(user_id, seq_a, success=True)
        barrier.release(user_id, seq_b, success=True)

    # ------------------------------------------------------------------
    # 7. wait_until_drained DRAINED when releases land before deadline
    # ------------------------------------------------------------------
    def test_wait_until_drained_drained_when_releases_arrive(self):
        """All relevant releases before deadline -> DRAINED."""
        barrier = MemoryWriteBarrier(config={"timeout_ms": 5000})
        user_id = "alex"
        seq_a = barrier.acquire(user_id)
        seq_b = barrier.acquire(user_id)
        snapshot = barrier.snapshot(user_id)

        # Release both writes from a background thread after a brief
        # pause so the waiter actually parks on the condition variable
        # (rather than racing through the initial pending check).
        def _drain() -> None:
            time.sleep(0.05)
            barrier.release(user_id, seq_a, success=True)
            time.sleep(0.02)
            barrier.release(user_id, seq_b, success=True)

        drainer = threading.Thread(target=_drain, daemon=True)
        drainer.start()

        outcome = barrier.wait_until_drained(user_id, snapshot)
        drainer.join(timeout=2.0)

        self.assertEqual(outcome, WaitOutcome.DRAINED)

        stats = barrier.stats()
        self.assertEqual(stats["total_pending"], 0)
        self.assertEqual(stats["last_released_seq"], seq_b)

    # ------------------------------------------------------------------
    # 8. Per-user_id keying: U_a writes don't block U_b waits
    # ------------------------------------------------------------------
    def test_pending_writes_do_not_block_disjoint_user_id_waits(self):
        """A wait on U_b returns ~immediately while U_a writes are parked."""
        # Generous global timeout so a bug that *did* block disjoint
        # users would still surface as a slow return rather than
        # being masked by an early TIMEOUT.
        barrier = MemoryWriteBarrier(config={"timeout_ms": 5000})

        # Park two writes for U_a -- never released.
        u_a = "alex"
        seq_a1 = barrier.acquire(u_a)
        seq_a2 = barrier.acquire(u_a)

        # Snapshot for U_b is taken *after* U_a's writes are parked,
        # so the global high-water mark covers both U_a seq_nos.  The
        # barrier must still treat U_b as drained because ``_pending``
        # is keyed by user_id and contains no entries for U_b.
        u_b = "bob"
        snapshot_b = barrier.snapshot(u_b)
        self.assertGreaterEqual(snapshot_b, seq_a2)

        t0 = time.monotonic()
        outcome = barrier.wait_until_drained(u_b, snapshot_b)
        elapsed = time.monotonic() - t0

        self.assertEqual(outcome, WaitOutcome.DRAINED)
        # 50 ms is comfortable headroom over the no-op fast path
        # while still being tight enough to catch a regression that
        # parks the U_b waiter on U_a's pending writes.
        self.assertLess(
            elapsed,
            0.05,
            f"disjoint-user wait took {elapsed:.4f}s; expected <50 ms",
        )

        # U_a's pending writes should still be in the registry --
        # the U_b wait must not have drained them as a side effect.
        stats = barrier.stats()
        self.assertEqual(stats["pending_by_user"].get(u_a), 2)
        self.assertNotIn(u_b, stats["pending_by_user"])

        # Drain U_a so we leave the barrier clean.
        barrier.release(u_a, seq_a1, success=True)
        barrier.release(u_a, seq_a2, success=True)


if __name__ == "__main__":
    unittest.main()
