# The thread pool the kernel's HTTP server awaits its requests on
# (NeurIPS Subtask 18, docs/STRESS_DIMENSIONS.md, "The load mode").
#
# A request the server awaits off its event loop (a chat, a memory
# request's reply, the audit, the cost read) holds one worker for as
# long as it waits on the scheduler. ``asyncio.to_thread`` uses the
# loop's default pool, min(32, CPUs + 4) workers: 12 on an 8-CPU
# machine. Under the load mode's 16 users a request could then wait for
# a worker after it arrived, and no diagnostic covered that wait
# (``kernel_overhead_ms`` starts later). This pool has workers to spare
# for every request the load mode keeps in flight.
import asyncio
import contextvars
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

REQUEST_WORKERS = 64

_POOL = ThreadPoolExecutor(
    max_workers=REQUEST_WORKERS, thread_name_prefix="aios-request"
)


async def off_loop(call: Callable[..., Any], *args: Any) -> Any:
    """``call(*args)`` on the request pool, awaited: as
    ``asyncio.to_thread`` (the caller's context goes with it), on a
    pool of its own rather than the loop's default."""
    loop = asyncio.get_running_loop()
    context = contextvars.copy_context()
    return await loop.run_in_executor(
        _POOL, functools.partial(context.run, call, *args)
    )
