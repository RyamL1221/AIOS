# Memory write barrier: enforces write-before-read ordering by user_id.
#
# The barrier is owned by ``MemoryManager`` and consulted from
# ``SyscallExecutor`` (acceptance-time stamping) and
# ``ContextInjector`` (inline waits) so that a retrieval scoped to
# ``user_id = U`` cannot be served while one or more
# ``create_memory`` operations for the same ``user_id`` accepted before
# it remain uncommitted. Pending writes are tracked per user_id and
# ordered by a globally-monotonic sequence number issued at acceptance
# time. Retrievals capture a ``barrier_snapshot`` of the high-water
# mark and only wait on writes whose ``seq_no`` is at or below that
# snapshot, so later writes never block earlier reads. A bounded wait
# (``timeout_ms``) keeps a stuck provider commit from starving
# retrievals indefinitely.

import logging
import threading
import time
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class WaitOutcome(Enum):
    """Result of ``MemoryWriteBarrier.wait_until_drained``.

    ``DRAINED`` -- every relevant pending write committed (or failed)
        before the deadline.
    ``TIMEOUT`` -- the deadline elapsed with relevant pending writes
        still in flight; the retrieval is fail-open and proceeds.
    ``BYPASSED`` -- the barrier short-circuited (disabled, empty
        ``user_id``, or sentinel ``barrier_seq``) and never waited.
    """

    DRAINED = "drained"
    TIMEOUT = "timeout"
    BYPASSED = "bypassed"


# Sentinel sequence number used when the barrier is disabled or the
# call site has no ``user_id`` to scope ordering by. ``release`` and
# ``wait_until_drained`` treat this value as "nothing to wait for".
_SENTINEL_SEQ = 0


class MemoryWriteBarrier:
    """Per-user_id write barrier for the memory subsystem.

    Tracks ``create_memory`` operations the kernel has accepted but
    whose provider commits have not yet returned, and lets retrievals
    scoped to the same ``user_id`` wait until those writes drain.

    Configuration is sourced from ``memory.write_barrier.*``:

    - ``enabled`` (default ``True``): global on/off switch. When
      ``False``, every public method takes a constant-time fast path.
    - ``timeout_ms`` (default ``5000``): maximum time a single
      ``wait_until_drained`` call will block before returning
      ``WaitOutcome.TIMEOUT``.
    """

    def __init__(self, config: dict):
        """Initialize the barrier from a config dict.

        Args:
            config: The ``memory.write_barrier`` section (or an empty
                dict). Unknown keys are ignored; missing keys fall
                back to the documented defaults.
        """
        cfg = config or {}
        self._enabled: bool = bool(cfg.get("enabled", True))
        timeout_ms = cfg.get("timeout_ms", 5000)
        self._timeout_seconds: float = float(timeout_ms) / 1000.0

        # Protects ``_seq_counter``, ``_pending``, and ``_cv`` for
        # mutation; per-user condition variables are acquired
        # separately when waiting / notifying.
        self._lock: threading.Lock = threading.Lock()
        self._seq_counter: int = 0
        # Highest ``seq_no`` ever drained from ``_pending`` via
        # ``release``. Updated under ``_lock`` so ``stats`` can read a
        # consistent (acquired, released) pair. Stays at ``0`` until
        # the first release; tests use it to confirm a drain ran.
        self._last_released_seq: int = 0
        # ``_pending[user_id][seq_no] = acceptance_timestamp``
        self._pending: Dict[str, Dict[int, float]] = {}
        # Lazily-created per-user condition variables. Each condition
        # is constructed with the shared ``_lock`` so waiters and
        # notifiers serialize on the same primitive.
        self._cv: Dict[str, threading.Condition] = {}

    def acquire(self, user_id: Optional[str]) -> int:
        """Stamp an accepted ``create_memory`` with a sequence number.

        Returns the assigned ``seq_no`` so the caller can pass it to
        ``release`` once the provider commit returns. Returns the
        sentinel (``0``) and records nothing when the barrier is
        disabled or ``user_id`` is empty/``None`` so downstream
        ``release`` calls are no-ops.

        Args:
            user_id: The end-user the write is scoped to.

        Returns:
            A monotonically-increasing positive integer, or the
            sentinel ``0`` on the fast path.
        """
        # Fast path: barrier disabled or no ``user_id`` to scope by.
        # ``release`` is also a no-op on the sentinel, so callers can
        # forward the returned value without conditional logic.
        if not self._enabled or not user_id:
            return _SENTINEL_SEQ

        # Sequence numbers are globally monotonic (not per-user) so a
        # retrieval's ``snapshot`` can be a single integer read; later
        # writes for *any* user_id will be stamped strictly higher and
        # cannot retroactively block the retrieval.
        with self._lock:
            self._seq_counter += 1
            seq_no = self._seq_counter
            user_pending = self._pending.get(user_id)
            if user_pending is None:
                user_pending = {}
                self._pending[user_id] = user_pending
            user_pending[seq_no] = time.monotonic()
            # Per-user condition variables are created lazily by
            # ``release``/``wait_until_drained`` instead, so the
            # ``acquire`` fast path stays as small as possible.
        return seq_no

    def release(
        self,
        user_id: Optional[str],
        seq_no: int,
        success: bool,
    ) -> None:
        """Drain a pending write and notify waiters.

        No-op when called with the sentinel ``seq_no`` (the disabled /
        no-user_id fast path). The ``success`` flag is logged only;
        failed writes still release waiters so a provider error does
        not strand retrievals.

        Args:
            user_id: The end-user the write was scoped to.
            seq_no: The sequence number returned by ``acquire``.
            success: Whether the provider commit returned
                ``MemoryResponse(success=True)``.
        """
        # Sentinel path: ``acquire`` returned ``_SENTINEL_SEQ`` because
        # the barrier was disabled or no ``user_id`` was supplied, so
        # nothing was ever recorded. Skip locking entirely.
        if seq_no == _SENTINEL_SEQ:
            return

        # Lazily create the per-user condition variable under the
        # shared ``_lock`` so concurrent acquirers / releasers /
        # waiters for the same ``user_id`` all serialize on the same
        # primitive. The condition is bound to ``_lock`` so the
        # registry mutation below also synchronizes with ``acquire``.
        with self._lock:
            cv = self._cv.get(user_id) if user_id else None
            if cv is None:
                cv = threading.Condition(self._lock)
                if user_id:
                    self._cv[user_id] = cv

            user_pending = self._pending.get(user_id) if user_id else None
            if user_pending is None or seq_no not in user_pending:
                # Defensive: double release, never-acquired seq_no, or
                # a release after the per-user dict was already pruned.
                # Surfacing this as an error would mask real bugs in
                # the caller, so log and return without notifying.
                logger.debug(
                    "MemoryWriteBarrier.release: no pending entry for "
                    "user_id=%r seq_no=%d (already released?)",
                    user_id,
                    seq_no,
                )
                return

            del user_pending[seq_no]
            if not user_pending:
                # Prune the empty per-user dict so ``stats`` and the
                # condition-variable map don't accumulate stale keys
                # for users with no in-flight writes.
                self._pending.pop(user_id, None)

            # Track the high-water mark of released sequence numbers
            # so ``stats`` can surface a (last_acquired, last_released)
            # pair without extra bookkeeping. Releases can arrive out
            # of order, so we keep the maximum rather than overwrite.
            if seq_no > self._last_released_seq:
                self._last_released_seq = seq_no

            if success:
                logger.debug(
                    "MemoryWriteBarrier.release: drained user_id=%r "
                    "seq_no=%d (success)",
                    user_id,
                    seq_no,
                )
            else:
                # Failed writes still release waiters so a provider
                # error does not strand retrievals; surface the
                # failure at WARNING so operators can correlate it
                # with retrieval gaps.
                logger.warning(
                    "MemoryWriteBarrier.release: drained user_id=%r "
                    "seq_no=%d after FAILED write (waiters notified)",
                    user_id,
                    seq_no,
                )

            # Wake every waiter on this user_id; each will re-check
            # its ``barrier_seq`` against the remaining ``_pending``
            # entries and either return ``DRAINED`` or wait again.
            cv.notify_all()

    def snapshot(self, user_id: Optional[str]) -> int:
        """Capture the high-water mark a retrieval will wait on.

        Returns the sentinel (``0``) when the barrier is disabled or
        ``user_id`` is empty/``None``; ``wait_until_drained`` treats
        the sentinel as "nothing to wait for". Otherwise returns the
        current ``_seq_counter`` value, so later writes (stamped with
        a strictly-higher ``seq_no``) cannot block this retrieval.

        Args:
            user_id: The end-user the retrieval is scoped to.

        Returns:
            The current high-water mark, or the sentinel ``0``.
        """
        # Fast path: barrier disabled or no ``user_id`` to scope by.
        # ``wait_until_drained`` treats the sentinel as "nothing to
        # wait for", so callers can forward the returned value
        # without conditional logic.
        if not self._enabled or not user_id:
            return _SENTINEL_SEQ

        # Read under ``_lock`` so the snapshot is consistent with any
        # concurrent ``acquire`` call that is mutating ``_seq_counter``.
        # No mutation of ``_seq_counter`` or ``_pending`` -- this is a
        # pure read; later writes will be stamped strictly higher and
        # cannot retroactively block a retrieval that captured this
        # high-water mark.
        with self._lock:
            return self._seq_counter

    def wait_until_drained(
        self,
        user_id: Optional[str],
        barrier_seq: int,
        deadline: Optional[float] = None,
    ) -> WaitOutcome:
        """Block until all pending writes at or below ``barrier_seq`` drain.

        Returns ``WaitOutcome.BYPASSED`` immediately when the barrier
        is disabled, ``user_id`` is empty/``None``, or ``barrier_seq``
        is the sentinel. Otherwise waits on the per-user condition
        variable, returning ``WaitOutcome.DRAINED`` when every
        relevant pending write has been released, or
        ``WaitOutcome.TIMEOUT`` when the deadline elapses with writes
        still pending (the retrieval then proceeds fail-open).

        Args:
            user_id: The end-user the retrieval is scoped to.
            barrier_seq: The high-water mark from ``snapshot``.
            deadline: Optional override for the configured timeout, in
                seconds. Used by tests to surface bounded-wait
                behavior quickly.

        Returns:
            One of ``WaitOutcome.DRAINED``, ``WaitOutcome.TIMEOUT``,
            or ``WaitOutcome.BYPASSED``.
        """
        # Fast path: barrier disabled, no ``user_id`` to scope by, or
        # the caller never captured a real high-water mark. ``snapshot``
        # returns ``_SENTINEL_SEQ`` for all of these cases too, so this
        # branch covers both "barrier off" and "nothing to wait for".
        if not self._enabled or not user_id or barrier_seq == _SENTINEL_SEQ:
            return WaitOutcome.BYPASSED

        # Resolve the effective per-call timeout. ``deadline`` is
        # documented as a maximum *total wait* (not an absolute
        # monotonic deadline), so tests can pass a small float to
        # surface bounded-wait behavior quickly without coordinating
        # with the configured default.
        effective_timeout = (
            self._timeout_seconds if deadline is None else float(deadline)
        )
        # Compute the absolute deadline once so spurious wakeups in
        # the wait loop don't reset the budget.
        abs_deadline = time.monotonic() + effective_timeout

        # Lazily create the per-user condition variable under the
        # shared ``_lock`` so concurrent acquirers / releasers /
        # waiters for the same ``user_id`` all serialize on the same
        # primitive. The condition is bound to ``_lock`` so the
        # ``_pending`` reads below are consistent with concurrent
        # ``acquire`` / ``release`` mutations.
        with self._lock:
            cv = self._cv.get(user_id)
            if cv is None:
                cv = threading.Condition(self._lock)
                self._cv[user_id] = cv

            # Loop until either no relevant pending writes remain or
            # the absolute deadline passes. Re-checking ``_pending``
            # on every wakeup handles spurious wakeups and the case
            # where a notify wakes us but later writes (with
            # ``seq_no > barrier_seq``) are still parked.
            while True:
                user_pending = self._pending.get(user_id)
                if not user_pending or all(
                    s > barrier_seq for s in user_pending
                ):
                    return WaitOutcome.DRAINED

                remaining = abs_deadline - time.monotonic()
                if remaining <= 0:
                    # Deadline passed with relevant writes still in
                    # flight. Surface the stuck sequence numbers at
                    # WARNING so operators can correlate them with
                    # retrieval latency; the retrieval then proceeds
                    # fail-open.
                    stuck = sorted(
                        s for s in user_pending if s <= barrier_seq
                    )
                    logger.warning(
                        "MemoryWriteBarrier.wait_until_drained: "
                        "TIMEOUT after %.3fs for user_id=%r "
                        "barrier_seq=%d still_pending_seq_nos=%s",
                        effective_timeout,
                        user_id,
                        barrier_seq,
                        stuck,
                    )
                    return WaitOutcome.TIMEOUT

                # ``cv.wait`` releases ``_lock`` while sleeping and
                # re-acquires it before returning, so the next
                # iteration's ``_pending`` read is consistent with
                # any ``release`` that happened during the sleep.
                cv.wait(timeout=remaining)

    def stats(self) -> dict:
        """Return a read-only snapshot of barrier state for diagnostics.

        Safe to call concurrently. Used by tests to assert that the
        pending-write registry is empty after a drain and by operators
        to correlate stuck writes with retrieval latency. Acquires
        ``_lock`` for the duration of the read so the returned counts,
        ``last_acquired_seq``, and ``last_released_seq`` are mutually
        consistent.

        Returns:
            A dict with the following keys:

            - ``enabled`` (``bool``): whether the barrier is active.
            - ``last_acquired_seq`` (``int``): the current
              ``_seq_counter`` value (``0`` before any acquire).
            - ``last_released_seq`` (``int``): the highest ``seq_no``
              ever drained via ``release`` (``0`` before any release).
            - ``pending_by_user`` (``dict[str, int]``): per-user count
              of in-flight writes; users with no pending writes are
              omitted.
            - ``total_pending`` (``int``): sum of ``pending_by_user``
              values.
            - ``timeout_seconds`` (``float``): the configured
              bounded-wait threshold.
        """
        # Acquire ``_lock`` so the snapshot is consistent with any
        # concurrent ``acquire`` / ``release`` mutation. This is a
        # pure read -- no fields are modified.
        with self._lock:
            pending_by_user = {
                user_id: len(seq_map)
                for user_id, seq_map in self._pending.items()
                if seq_map
            }
            total_pending = sum(pending_by_user.values())
            return {
                "enabled": self._enabled,
                "last_acquired_seq": self._seq_counter,
                "last_released_seq": self._last_released_seq,
                "pending_by_user": pending_by_user,
                "total_pending": total_pending,
                "timeout_seconds": self._timeout_seconds,
            }
