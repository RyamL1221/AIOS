"""
The memory pipeline library (NeurIPS Subtask 8).

The kernel's memory logic, importable without the kernel: identity
resolution, the write barrier, visibility, selection, formatting, and
the ``MemoryPipeline`` facade over them. It depends only on the provider
contract (``aios.memory.providers.base``) and its settings, never on
``MemoryManager``, syscalls or ``runtime/launch.py``. The kernel is a
thin client of it, and so is each replicated agent
(docs/REPLICATED_LOGIC.md).

``PIPELINE_VERSION`` is a hash of this package's source, recorded on
every trial, so two agents running different copies show as different
versions.
"""
import hashlib
from pathlib import Path

from .barrier import MemoryWriteBarrier, WaitOutcome, WriteBarrier
from .facade import (
    UPDATE_PROTECTED_METADATA,
    MemoryPipeline,
    conversation_note,
    conversation_request,
    note_from_request,
)
from .formatter import TYPE_ORDER, Formatter, estimate_tokens
from .identity import IdentityResolver, IdentityRules
from .selector import SHARED_FETCH_FACTOR, Selector
from .settings import PipelineSettings
from .visibility import Visibility, apply_sharing_filter


def _source_hash() -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


PIPELINE_VERSION = _source_hash()

__all__ = [
    "PIPELINE_VERSION",
    "SHARED_FETCH_FACTOR",
    "TYPE_ORDER",
    "UPDATE_PROTECTED_METADATA",
    "Formatter",
    "IdentityResolver",
    "IdentityRules",
    "MemoryPipeline",
    "MemoryWriteBarrier",
    "PipelineSettings",
    "Selector",
    "Visibility",
    "WaitOutcome",
    "WriteBarrier",
    "apply_sharing_filter",
    "conversation_note",
    "conversation_request",
    "estimate_tokens",
    "note_from_request",
]
