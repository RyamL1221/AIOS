"""
Kernel-side memory syscall schemas.

This module defines pydantic payload schemas for memory syscalls that
are not (yet) part of the Cerebrum SDK's ``MemoryQuery`` operation
catalog. They follow the same ``operation_type`` field pattern as
``cerebrum.memory.apis.MemoryQuery`` / ``MemoryResponse`` so they slot
into the existing memory syscall routing in
``SyscallExecutor.execute_memory_syscall``.

Currently defines:
- ``ReportRewardQuery``: carries a completed trial's judge reward back
  into the kernel so it can be routed to the learned policy bandits
  (wired in later subtasks). This is the reverse-direction syscall that
  breaks the previously one-directional agent->kernel request flow.
- ``ReportRewardResponse``: the acknowledgement returned to the caller.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from typing_extensions import Literal


class ReportRewardQuery(BaseModel):
    """Payload schema for the ``report_reward`` memory syscall.

    A completed trial reports the judge's scalar reward together with
    the memory IDs that participated in producing the trial result and
    arbitrary trial metadata. The kernel routes this to the learned
    policy bandits (novelty-threshold, similarity, redundancy-filter)
    so future add/retrieve decisions can adapt.

    Attributes:
        operation_type: Fixed discriminator ``"report_reward"``,
            mirroring the ``MemoryQuery.operation_type`` pattern so the
            existing memory syscall router can dispatch on it.
        memory_ids_involved: IDs of the memories that contributed to
            the trial (the "arms pulled" whose reward is being
            reported). May be empty if no memory was involved.
        reward_value: Scalar judge reward for the trial. Convention is
            higher-is-better; callers typically normalize to ``[0, 1]``
            but no range is enforced here.
        trial_metadata: Arbitrary per-trial context (trial id, agent,
            user_id, decisions taken, etc.). Opaque to the schema;
            consumed by the policy layer.
    """

    operation_type: Literal["report_reward"] = "report_reward"
    memory_ids_involved: List[str] = Field(default_factory=list)
    reward_value: float
    trial_metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True


class ReportRewardResponse(BaseModel):
    """Response schema for the ``report_reward`` memory syscall.

    Attributes:
        response_class: Fixed ``"memory"`` to match the SDK response
            family convention.
        operation_type: Echoes ``"report_reward"``.
        success: Whether the reward was accepted by the kernel.
        error: Error message when ``success`` is ``False``.
    """

    response_class: str = "memory"
    operation_type: Literal["report_reward"] = "report_reward"
    success: bool = False
    error: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True
