"""The kernel's request pool (NeurIPS Subtask 18, docs/STRESS_DIMENSIONS.md,
"The load mode"): the HTTP server awaits every request it serves off
its event loop on a pool of its own, large enough that a request never
waits for a worker under the load mode, instead of the loop's default
pool (at most 32 workers, 12 on an 8-CPU machine)."""
import asyncio
import contextvars
import threading
from pathlib import Path

from aios.utils.request_pool import REQUEST_WORKERS, off_loop

LAUNCH = Path(__file__).resolve().parents[3] / "runtime" / "launch.py"


def test_requests_waiting_at_once_each_have_a_worker():
    """40 requests waiting at once (more than the default pool's 32
    workers) all run together: none waits for another to finish."""
    parties = 40
    assert REQUEST_WORKERS >= parties
    barrier = threading.Barrier(parties, timeout=5)

    async def main():
        return await asyncio.gather(
            *(off_loop(barrier.wait) for _ in range(parties)))

    assert sorted(asyncio.run(main())) == list(range(parties))


def test_a_request_runs_in_the_callers_context():
    """As ``asyncio.to_thread``: the caller's context variables (the
    request's usage tag, its kernel session) go with the call."""
    var = contextvars.ContextVar("var", default=None)

    async def main():
        var.set("set by the handler")
        return await off_loop(var.get)

    assert asyncio.run(main()) == "set by the handler"


def test_the_server_awaits_its_requests_on_the_request_pool():
    """No handler awaits the loop's default pool."""
    source = LAUNCH.read_text()
    assert "to_thread" not in source
    assert "run_in_executor" not in source
    assert source.count("await off_loop(") == 5
