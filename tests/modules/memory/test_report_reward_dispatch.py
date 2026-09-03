"""
End-to-end dispatch test for the ``report_reward`` memory syscall.

Proves that a ``ReportRewardQuery`` submitted through the real request
entry point (``SyscallExecutor.execute_request``) travels through the
*real* scheduler machinery -- it is enqueued on the process-wide global
memory request queue, dequeued by ``FIFOScheduler.process_memory_requests``
in a scheduler-owned thread, dispatched to
``MemoryManager.address_request`` -> ``MemoryManager.report_reward``, and
returns a valid ``ReportRewardResponse``.

This is deliberately NOT the ``_MemoryDispatcher`` stand-in used by the
write-barrier integration suite: the acceptance criterion for this
subtask is evidence the syscall goes through the actual
``FIFOScheduler`` queue/worker rather than an inline call. We therefore
instantiate a real ``FIFOScheduler`` and run only its memory-processing
thread (LLM/storage/tool managers are unused because we never submit
those syscall types).

Run standalone:

    python tests/modules/memory/test_report_reward_dispatch.py
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
import unittest
from collections import OrderedDict
from queue import Empty
from typing import Any, List, Optional

# Ensure project root on sys.path when invoked directly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from aios.hooks.stores._global import (
    global_memory_req_queue,
    global_memory_req_queue_get_message,
)
from aios.memory.manager import MemoryManager
from aios.memory.schemas import ReportRewardQuery, ReportRewardResponse
from aios.memory.write_barrier import MemoryWriteBarrier
from aios.scheduler.fifo_scheduler import FIFOScheduler
from aios.syscall.syscall import SyscallExecutor

logger = logging.getLogger(__name__)


class _RecordingMemoryManager(MemoryManager):
    """A MemoryManager built without ConfigManager/provider wiring.

    Records every ``report_reward`` invocation so the test can assert
    the scheduler thread (not the submitting thread) delivered the
    reward. Reuses the real ``MemoryManager.address_request`` routing
    and the real ``report_reward`` handler from the parent class.
    """

    def __init__(self) -> None:  # noqa: D401 - intentional bypass
        # Bypass the heavy __init__ (provider factory, config). We only
        # need the routing method + report_reward handler + a barrier.
        self.log_mode = "console"
        self._known_user_ids = OrderedDict()
        self.provider = None  # never used: report_reward hits no provider
        self.barrier = MemoryWriteBarrier(config={})
        self.calls: List[dict] = []
        self.call_threads: List[str] = []

    def report_reward(
        self,
        memory_ids_involved: list,
        reward_value: float,
        trial_metadata: Optional[dict] = None,
    ) -> None:
        # Record the thread name so the test can prove dispatch happened
        # on a scheduler-owned worker thread, not inline.
        self.call_threads.append(threading.current_thread().name)
        self.calls.append(
            {
                "memory_ids_involved": memory_ids_involved,
                "reward_value": reward_value,
                "trial_metadata": trial_metadata or {},
            }
        )
        # Delegate to the real stub so its log line is emitted too.
        super().report_reward(
            memory_ids_involved, reward_value, trial_metadata
        )


def _drain_global_memory_queue() -> None:
    """Empty the process-wide memory queue for a clean start."""
    while True:
        try:
            global_memory_req_queue.get(block=False)
        except Empty:
            return


class ReportRewardDispatchTest(unittest.TestCase):
    """report_reward travels through the real FIFOScheduler queue."""

    def setUp(self) -> None:
        _drain_global_memory_queue()
        self.manager = _RecordingMemoryManager()

        # Real FIFOScheduler wired to the real global memory queue.
        # llm/storage/tool managers are None: we only start the memory
        # thread and only submit memory syscalls, so they are never
        # touched.
        self.scheduler = FIFOScheduler(
            llm=None,
            memory_manager=self.manager,
            storage_manager=None,
            tool_manager=None,
            log_mode="console",
            get_llm_syscall=None,
            get_memory_syscall=global_memory_req_queue_get_message,
            get_storage_syscall=None,
            get_tool_syscall=None,
            batch_interval=0.05,
        )
        # Start ONLY the memory-processing thread (the real scheduler
        # worker), not the whole scheduler, to avoid LLM/storage/tool
        # setup. This is the exact method the production scheduler runs.
        self.scheduler.active = True
        self.scheduler.start_processing_threads(
            [self.scheduler.process_memory_requests]
        )

        # Executor wired with the manager so acceptance-time barrier
        # stamping resolves (report_reward is inert to the barrier).
        self.executor = SyscallExecutor()
        self.executor.memory_manager = self.manager

    def tearDown(self) -> None:
        self.scheduler.active = False
        self.scheduler.stop_processing_threads()
        _drain_global_memory_queue()

    def test_report_reward_dispatched_through_scheduler(self) -> None:
        query = ReportRewardQuery(
            memory_ids_involved=["mem_a", "mem_b"],
            reward_value=0.77,
            trial_metadata={"trial_id": "t-1", "agent": "JudgeAgent"},
        )

        submitting_thread = threading.current_thread().name

        result = self.executor.execute_request("JudgeAgent", query)

        # execute_memory_syscall returns the timing-metrics dict with
        # the handler response under "response".
        self.assertIsInstance(result, dict)
        response = result["response"]

        self.assertIsInstance(response, ReportRewardResponse)
        self.assertTrue(response.success)
        self.assertIsNone(response.error)
        self.assertEqual(response.operation_type, "report_reward")

        # The handler ran exactly once, with the payload intact.
        self.assertEqual(len(self.manager.calls), 1)
        call = self.manager.calls[0]
        self.assertEqual(call["memory_ids_involved"], ["mem_a", "mem_b"])
        self.assertEqual(call["reward_value"], 0.77)
        self.assertEqual(call["trial_metadata"]["trial_id"], "t-1")

        # Proof it went through the scheduler queue/worker rather than
        # an inline call: dispatch happened on the scheduler's
        # process_memory_requests thread, NOT the submitting thread.
        dispatch_thread = self.manager.call_threads[0]
        self.assertEqual(dispatch_thread, "process_memory_requests")
        self.assertNotEqual(dispatch_thread, submitting_thread)

        logger.info(
            "report_reward dispatched on thread=%s (submitted from=%s); "
            "response=%s",
            dispatch_thread,
            submitting_thread,
            response.model_dump(),
        )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
    unittest.main(verbosity=2)
