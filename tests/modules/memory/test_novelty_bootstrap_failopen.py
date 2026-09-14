"""Regression tests for the per-task-type novelty-gate fail-open.

The novelty (add) gate's bootstrap fail-open must fire ONLY when there
is not yet a single stored memory of the candidate's ``memory_type`` for
this ``user_id`` (``has_type`` is False). In that state the gate admits
the first-of-type write even if the bandit's selected novelty threshold
would otherwise reject it, so a strict exploring arm cannot permanently
starve a memory_type of its very first write. Once ≥1 memory of that
type exists for the user, ``has_type`` becomes True and the gate is
governed normally by the threshold again — the fail-open does NOT mask
steady-state gating. The check is per-``memory_type``, so bootstrapping
one type never disarms the gate for a different, already-populated type.

This is the add-gate analogue of the similarity-gate bootstrap fail-open
covered in ``test_bootstrap_failopen.py``; it is kept stylistically
consistent with that suite (adaptive MemoryManager built via __new__ +
real PolicyManager, provider mocking for the retrieve probe, a
select_threshold spy to pin the arm, unittest assertions).

Cases proven here:
  1. FIRST WRITE OF A TYPE: strict threshold would reject
     (max_sim >= threshold) but has_type is False -> ADMIT (fail-open),
     the dedicated fail-open log line fires, and a novelty decision is
     recorded so reward can flow (same bookkeeping as a normal admit).
  2. SECOND WRITE OF THE SAME TYPE: same strict threshold, but now a
     memory of this type exists (has_type True) -> REJECT (normal
     gating restored; fail-open does not fire).
  3. PER-TYPE INDEPENDENCE: a store holding profile memories but zero
     task_context memories -> a new task_context candidate fail-opens,
     while a new profile candidate (same strict threshold) is gated
     normally.

Run standalone (needs the cerebrum SDK from the venv):

    .venv/bin/python tests/modules/memory/test_novelty_bootstrap_failopen.py
"""
from __future__ import annotations

import os
import sys
import unittest
from collections import OrderedDict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cerebrum.memory.apis import MemoryResponse

from aios.memory.manager import MemoryManager
from aios.memory.note import MemoryNote
from aios.memory.policy import PolicyManager, build_context_vector


LLM = "gpt-4o"
USER = "u1"
# The dedicated fail-open log line's unique substring (Subtask 4).
_FAILOPEN_MARKER = "novelty gate BOOTSTRAP FAIL-OPEN"


def _make_adaptive_manager():
    """MemoryManager on the adaptive path with a real PolicyManager,
    no ConfigManager / provider factory (mirrors
    test_bootstrap_failopen._make_adaptive_manager)."""
    m = MemoryManager.__new__(MemoryManager)
    m.log_mode = "console"
    m._known_user_ids = OrderedDict()
    m.provider = None
    m._adaptive_enabled = True
    m._static_thresholds_enabled = False
    m._latest_llm_core = LLM
    m._pending_reward_decisions = {}
    m.policy_logger = None
    m.policy = PolicyManager(alpha=1.0)
    return m


class _StubProvider:
    """Minimal provider whose retrieve_memory returns a fixed result
    set, so _candidate_novelty_probe sees a controlled (max_sim,
    has_type). Each result dict carries ``similarity`` and a
    ``metadata.memory_type`` so both signals are derivable from the one
    call the gate already makes."""

    def __init__(self, rows):
        self._rows = rows

    def retrieve_memory(self, query):
        return MemoryResponse(success=True, search_results=self._rows)


def _row(memory_type, similarity, mid="x"):
    return {
        "memory_id": mid,
        "content": f"{memory_type} row",
        "similarity": similarity,
        "metadata": {"memory_type": memory_type, "user_id": USER},
    }


def _force_novelty_arm(m, threshold, arm):
    """Pin the novelty_threshold selection to a fixed (threshold, arm)
    so the fail-open can be tested deterministically without depending
    on LinUCB's state-dependent argmax. Uses the real context vector so
    decision recording / arm bookkeeping line up."""
    task_ctx = {}

    real = m.policy.select_threshold

    def spy(bandit_name, llm_core, task_type):
        if bandit_name == "novelty_threshold":
            ctx = task_ctx.setdefault(
                task_type, build_context_vector(llm_core, task_type)
            )
            return threshold, arm, ctx
        return real(bandit_name, llm_core, task_type)

    m.policy.select_threshold = spy


def _note(memory_type):
    return MemoryNote(
        content="I am working on the memory bootstrap fix",
        metadata={"memory_type": memory_type, "user_id": USER},
    )


# A strict novelty arm: admit iff max_sim < 0.20. Real task_context
# candidates sit ~0.5, so this arm would reject them (the trap).
STRICT_THRESHOLD = 0.20
STRICT_ARM = 0  # value pinned via the spy; index only needs to be valid


class NoveltyBootstrapFailOpenTest(unittest.TestCase):

    def test_first_write_of_type_admitted_despite_strict_threshold(self):
        """has_type False + max_sim >= threshold -> fail-open ADMIT,
        dedicated log line fires, novelty decision recorded."""
        m = _make_adaptive_manager()
        _force_novelty_arm(m, STRICT_THRESHOLD, STRICT_ARM)
        # Store holds a *different* type only (profile), so the
        # task_context candidate has has_type=False, but max_sim (0.55)
        # is well above the strict 0.20 threshold -> would normally
        # reject.
        m.provider = _StubProvider(
            [_row("profile", 0.55, mid="p1")]
        )
        note = _note("task_context")
        with self.assertLogs(
            "aios.memory.manager", level="INFO"
        ) as cm:
            admit, decision = m._novelty_gate_admits(note, USER)
        self.assertTrue(admit)
        # The dedicated fail-open line fired exactly once.
        failopen_lines = [
            r for r in cm.output if _FAILOPEN_MARKER in r
        ]
        self.assertEqual(len(failopen_lines), 1)
        self.assertIn("task_type=task_context", failopen_lines[0])
        # Same decision bookkeeping shape as a normal admit.
        self.assertEqual(decision[0], "novelty_threshold")
        self.assertEqual(len(decision), 4)

    def test_second_write_of_type_is_gated_normally(self):
        """has_type True + max_sim >= threshold -> REJECT (fail-open
        does not fire once the type is bootstrapped)."""
        m = _make_adaptive_manager()
        _force_novelty_arm(m, STRICT_THRESHOLD, STRICT_ARM)
        # A task_context memory already exists, at high similarity to
        # the candidate.
        m.provider = _StubProvider(
            [_row("task_context", 0.55, mid="t1")]
        )
        note = _note("task_context")
        with self.assertLogs(
            "aios.memory.manager", level="INFO"
        ) as cm:
            admit, _decision = m._novelty_gate_admits(note, USER)
        # Normal gating: max_sim 0.55 >= threshold 0.20 -> reject.
        self.assertFalse(admit)
        # Fail-open line must NOT fire.
        self.assertFalse(
            any(_FAILOPEN_MARKER in r for r in cm.output)
        )

    def test_per_type_independence(self):
        """A store with profile memories but zero task_context: a new
        task_context fail-opens; a new profile (same strict threshold)
        is gated normally."""
        m = _make_adaptive_manager()
        _force_novelty_arm(m, STRICT_THRESHOLD, STRICT_ARM)
        # Store: only profile memories exist.
        rows = [_row("profile", 0.55, mid="p1")]
        m.provider = _StubProvider(rows)

        # task_context candidate: has_type=False -> fail-open ADMIT.
        with self.assertLogs(
            "aios.memory.manager", level="INFO"
        ) as cm_task:
            admit_task, _ = m._novelty_gate_admits(
                _note("task_context"), USER
            )
        self.assertTrue(admit_task)
        self.assertTrue(
            any(
                _FAILOPEN_MARKER in r and "task_type=task_context" in r
                for r in cm_task.output
            )
        )

        # profile candidate: has_type=True (p1 exists) and max_sim 0.55
        # >= 0.20 -> normal REJECT, no fail-open.
        with self.assertLogs(
            "aios.memory.manager", level="INFO"
        ) as cm_prof:
            admit_prof, _ = m._novelty_gate_admits(
                _note("profile"), USER
            )
        self.assertFalse(admit_prof)
        self.assertFalse(
            any(_FAILOPEN_MARKER in r for r in cm_prof.output)
        )

    def test_normal_admit_below_threshold_is_not_a_failopen(self):
        """Sanity: a genuinely-novel candidate (max_sim < threshold) is
        admitted by the threshold itself, NOT via the fail-open, even
        when has_type is False."""
        m = _make_adaptive_manager()
        # Lenient arm: admit iff max_sim < 0.90.
        _force_novelty_arm(m, 0.90, STRICT_ARM)
        m.provider = _StubProvider(
            [_row("profile", 0.30, mid="p1")]
        )
        with self.assertLogs(
            "aios.memory.manager", level="INFO"
        ) as cm:
            admit, _ = m._novelty_gate_admits(
                _note("task_context"), USER
            )
        self.assertTrue(admit)
        # Admitted by threshold, so the fail-open line must NOT fire.
        self.assertFalse(
            any(_FAILOPEN_MARKER in r for r in cm.output)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
