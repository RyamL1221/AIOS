from queue import Queue
from typing import List
REQUEST_QUEUE: dict[str, Queue] = {}
# REQUEST_QUEUE: dict[str, []] = {}


def getMessage(q: List, timeout: float = 0.1):
    """The next message, waiting up to ``timeout`` seconds for one
    (``queue.Empty`` when none came). The wait ends as soon as a message
    is put: ``Queue.get`` waits on the queue's condition variable.
    ``timeout=0`` takes a queued message without waiting."""
    return q.get(block=True, timeout=timeout)

def addMessage(q: List, message: str):
    # q.append(message)
    q.put(message)
    return None

def isEmpty(q: List):
    # return len(q) == 0
    return q.empty()