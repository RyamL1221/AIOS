"""
The memory pipeline library (NeurIPS Subtask 8).

The kernel's memory logic, importable without the kernel: identity
resolution, the write barrier, visibility, selection, formatting, and
the ``MemoryPipeline`` facade over them. It depends only on the provider
contract (``aios.memory.providers.base``) and its settings, never on
``MemoryManager``, syscalls or ``runtime/launch.py``. The kernel is a
thin client of it, and so is each replicated agent
(docs/REPLICATED_LOGIC.md).

``PIPELINE_VERSION`` is a hash of this package's source, the value
matcher it shares with the benchmark's scorer (``matching``) included,
recorded on every trial, so two agents running different copies show as
different versions. The package imports nothing but the standard
library and the provider contract: no ``cerebrum`` module (a test greps
for one); the caller passes the usage tag.
"""
import hashlib
from pathlib import Path

from .barrier import MemoryWriteBarrier, WaitOutcome, WriteBarrier
from .deletion import (
    LIST_TOP_K,
    MARKS,
    REASON_ALIAS,
    REASON_FACT_KEY,
    REASON_VALUE,
    ListingLimitError,
    after_write,
    forget_fact,
    partition,
)
from .facade import (
    UPDATE_PROTECTED_METADATA,
    MemoryPipeline,
    conversation_note,
    conversation_request,
    note_from_request,
)
from .formatter import (
    PROVENANCE_FIELDS,
    RECENCY_UNITS,
    TYPE_ORDER,
    Formatter,
    estimate_tokens,
    session_age,
)
from .identity import IdentityResolver, IdentityRules
from .matching import match_any, match_forms, normalize, value_in
from .selector import SHARED_FETCH_FACTOR, Selector
from .settings import SUPERSESSION_MODES, PipelineSettings
from .tombstones import (
    Tombstone,
    TombstoneStore,
    carried_form,
    statement_forms,
)
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
    "LIST_TOP_K",
    "MARKS",
    "PIPELINE_VERSION",
    "PROVENANCE_FIELDS",
    "RECENCY_UNITS",
    "REASON_ALIAS",
    "REASON_FACT_KEY",
    "REASON_VALUE",
    "SHARED_FETCH_FACTOR",
    "SUPERSESSION_MODES",
    "TYPE_ORDER",
    "UPDATE_PROTECTED_METADATA",
    "Formatter",
    "IdentityResolver",
    "IdentityRules",
    "ListingLimitError",
    "MemoryPipeline",
    "MemoryWriteBarrier",
    "PipelineSettings",
    "Selector",
    "Tombstone",
    "TombstoneStore",
    "Visibility",
    "WaitOutcome",
    "WriteBarrier",
    "after_write",
    "apply_sharing_filter",
    "carried_form",
    "conversation_note",
    "conversation_request",
    "estimate_tokens",
    "match_any",
    "match_forms",
    "normalize",
    "value_in",
    "forget_fact",
    "note_from_request",
    "partition",
    "session_age",
    "statement_forms",
]
