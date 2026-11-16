"""The FIFO scheduler's LLM thread is event-driven (NeurIPS Subtask 18,
docs/STRESS_DIMENSIONS.md, "Kernel and library additions" 3).

It blocks on its queue until a request arrives, takes every request
already queued with it and runs them as one batch, in arrival order;
requests that arrive while a batch runs form the next batch. Until
Subtask 18 it slept a fixed 1 s before each collection (known issue
15). No model is called: a fake adapter records the batches."""
import queue
import threading
import time

from aios.hooks.stores import queue as QueueStore
from aios.scheduler.fifo_scheduler import FIFOScheduler

# Well under the old fixed interval (1 s), well over a thread hop.
PROMPT = 0.5


class FakeSyscall:
    """What ``_execute_batch_syscalls`` touches on a syscall."""

    def __init__(self, name: str):
        self.agent_name = name
        self.done = threading.Event()
        self.enqueued_at = None
        self.started_at = None

    def set_status(self, status):
        self.status = status

    def set_start_time(self, value):
        self.started_at = value

    def get_pid(self):
        return self.agent_name


class FakeLLM:
    """Records each batch; ``hold`` keeps the first batch running until
    ``release`` is set."""

    def __init__(self, hold: bool = False):
        self.batches = []
        self.hold = hold
        self.running = threading.Event()
        self.release = threading.Event()

    def execute_llm_syscalls(self, batch):
        self.batches.append([syscall.agent_name for syscall in batch])
        for syscall in batch:
            syscall.ran_at = time.monotonic()
        if self.hold and len(self.batches) == 1:
            self.running.set()
            assert self.release.wait(5), "the test never released"
        for syscall in batch:
            syscall.done.set()


def scheduler_over(llm):
    """A scheduler whose LLM queue is a real queue read through the
    kernel's getter (``QueueStore.getMessage``), as the hooks build it."""
    queues = [queue.Queue() for _ in range(4)]

    def getter(q):
        def get(timeout: float = 0.1):
            return QueueStore.getMessage(q, timeout)
        return get

    llm_get, memory_get, storage_get, tool_get = map(getter, queues)
    scheduler = FIFOScheduler(
        llm=llm, memory_manager=None, storage_manager=None,
        tool_manager=None, log_mode="console",
        get_llm_syscall=llm_get, get_memory_syscall=memory_get,
        get_storage_syscall=storage_get, get_tool_syscall=tool_get,
    )
    return scheduler, queues[0]


def put(llm_queue, syscall):
    syscall.enqueued_at = time.monotonic()
    llm_queue.put(syscall)


def test_a_request_runs_as_soon_as_it_arrives():
    """No fixed wait: a request put on an idle queue runs at once (it
    waited about a second before)."""
    llm = FakeLLM()
    scheduler, llm_queue = scheduler_over(llm)
    scheduler.start()
    try:
        time.sleep(0.2)  # the thread is idle, waiting on the queue
        for name in ("a", "b", "c"):
            syscall = FakeSyscall(name)
            put(llm_queue, syscall)
            assert syscall.done.wait(5)
            assert syscall.ran_at - syscall.enqueued_at < PROMPT
    finally:
        scheduler.stop()
    assert llm.batches == [["a"], ["b"], ["c"]]


def test_requests_queued_while_a_batch_runs_form_the_next_batch():
    """Arrival order is kept, and the requests that queued behind a
    running batch run together, in the order they came."""
    llm = FakeLLM(hold=True)
    scheduler, llm_queue = scheduler_over(llm)
    scheduler.start()
    try:
        first = FakeSyscall("first")
        put(llm_queue, first)
        assert llm.running.wait(5)
        later = [FakeSyscall(name) for name in ("b", "c", "d")]
        for syscall in later:
            put(llm_queue, syscall)
        llm.release.set()
        for syscall in [first] + later:
            assert syscall.done.wait(5)
    finally:
        scheduler.stop()
    assert llm.batches == [["first"], ["b", "c", "d"]]


def test_requests_queued_together_run_as_one_batch_in_order():
    """Requests already queued when the thread starts are one batch."""
    llm = FakeLLM()
    scheduler, llm_queue = scheduler_over(llm)
    syscalls = [FakeSyscall(name) for name in ("x", "y", "z")]
    for syscall in syscalls:
        put(llm_queue, syscall)
    scheduler.start()
    try:
        for syscall in syscalls:
            assert syscall.done.wait(5)
    finally:
        scheduler.stop()
    assert llm.batches == [["x", "y", "z"]]


def test_stop_returns_promptly():
    """``stop`` ends every thread without waiting out an interval."""
    scheduler, _ = scheduler_over(FakeLLM())
    scheduler.start()
    time.sleep(0.2)
    started = time.monotonic()
    scheduler.stop()
    assert time.monotonic() - started < PROMPT
