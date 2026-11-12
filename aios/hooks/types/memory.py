from pydantic import BaseModel
from typing import Any, TypeAlias, Callable, Optional
from queue import Queue

MemoryRequestQueue: TypeAlias = Queue
# MemoryRequestQueue: TypeAlias = []

MemoryRequestQueueGetMessage: TypeAlias = Callable[[], None]
MemoryRequestQueueAddMessage: TypeAlias = Callable[[str], None]
MemoryRequestQueueCheckEmpty: TypeAlias = Callable[[], bool]

class MemoryManagerParams(BaseModel):
    log_mode: str
    # "in-house", "in-memory", "mem0" or "graphiti"
    provider: Optional[str] = None