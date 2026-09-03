"""
Adaptive threshold policy for AIOS memory operations.

This module provides ``PolicyManager`` — a standalone learning
component that decides the *thresholds* used by three memory-control
decisions using independent LinUCB contextual bandits:

- ``novelty_threshold``  — admission gate for ``add_memory``: how novel
  a candidate memory must be (vs. what's already stored) to be written.
- ``similarity_threshold`` — relevance gate for ``retrieve_memory``: the
  minimum similarity a retrieved memory must have to be injected.
- ``redundancy_threshold`` — de-duplication gate for ``retrieve_memory``:
  the pairwise-similarity above which two retrieved memories are
  considered redundant (and one is dropped).

Each decision is a *contextual bandit*: given a context (which LLM the
agent runs, and the task type), the bandit picks one discrete threshold
value (an "arm"), and later receives a scalar reward describing how well
that choice served the trial. Over many trials each bandit learns which
threshold works best for each context.

Design notes / decisions
-------------------------
* **LinUCB** (Li et al., 2010) is used because thresholds are chosen
  from a small discrete set and the reward signal is contextual and
  delayed (a judge scores the trial after the fact). LinUCB balances
  exploration/exploitation with a closed-form per-arm ridge regression
  and a UCB bonus, so no arm is starved at initialization.

* **Three independent bandits.** The decisions are semantically
  distinct and their rewards are attributed separately, so they do not
  share parameters. A single reusable ``LinUCBBandit`` class is
  instantiated three times.

* **Action spaces are cosine-similarity-scaled.** All three thresholds
  operate on the same underlying scale as the retriever's exposed
  ``similarity`` field (see ``aios/memory/retrievers.py``), i.e. a
  cosine-similarity-like value in roughly ``[0, 1]`` where higher means
  "more similar / less novel". We discretize each into 6 buckets over a
  sensible sub-range (documented per bandit below) rather than the full
  ``[0, 1]`` because the extreme ends are degenerate (a novelty
  threshold of 0 admits everything; 1 admits nothing).

* **Context vector.** Built deterministically from ``(llm_core,
  task_type)`` as the concatenation of two one-hot blocks plus a bias
  term. ``pipeline_stage`` is deliberately **not** encoded: each bandit
  is already stage-specific (novelty→add, similarity/redundancy→
  retrieve), so a stage feature would be constant within a given
  bandit and carry no information. Keeping it out lowers dimensionality
  and avoids a rank-deficient feature.

* **In-memory only (v1).** State lives for the lifetime of the
  ``PolicyManager`` instance. No checkpointing/persistence.

This module has *no* dependencies on ``MemoryManager``, the kernel
config, or the scheduler — it is importable and testable in isolation.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Context feature space
# ---------------------------------------------------------------------

# Known LLM cores, one-hot encoded. Unrecognized model strings fall into
# the trailing "other" slot so the feature vector is always fixed-length
# regardless of the exact model configured. Matching is done on a
# normalized (lowercased) family prefix so e.g. "qwen2.5:7b" and
# "qwen3:4b" both map to the "qwen" family.
KNOWN_LLM_FAMILIES: Tuple[str, ...] = ("qwen", "llama", "gpt")

# Known task types, one-hot encoded. "other" trailing slot as above.
KNOWN_TASK_TYPES: Tuple[str, ...] = ("profile", "task")

# Feature vector layout:
#   [ llm one-hot (len(KNOWN_LLM_FAMILIES) + 1) ]
#   [ task one-hot (len(KNOWN_TASK_TYPES) + 1)   ]
#   [ bias term (1)                              ]
CONTEXT_DIM: int = (
    (len(KNOWN_LLM_FAMILIES) + 1)
    + (len(KNOWN_TASK_TYPES) + 1)
    + 1
)


def _one_hot(value: str, categories: Tuple[str, ...]) -> List[float]:
    """One-hot encode *value* over *categories* with a trailing
    "other" slot.

    Matching is a case-insensitive substring test against each
    category (so ``"qwen2.5:7b"`` matches the ``"qwen"`` family). The
    first matching category wins; if none match, the trailing slot is
    set. Exactly one slot is ever hot.

    Args:
        value: The raw string to encode (may be ``None``/empty).
        categories: Ordered known categories.

    Returns:
        A list of ``len(categories) + 1`` floats with exactly one 1.0.
    """
    vec = [0.0] * (len(categories) + 1)
    normalized = (value or "").strip().lower()
    for i, cat in enumerate(categories):
        if cat in normalized:
            vec[i] = 1.0
            return vec
    vec[-1] = 1.0  # "other"
    return vec


def build_context_vector(llm_core: str, task_type: str) -> np.ndarray:
    """Build the fixed-length context feature vector.

    Deterministic: identical ``(llm_core, task_type)`` always yields
    an identical vector. ``pipeline_stage`` is intentionally excluded
    (see module docstring — each bandit is already stage-specific).

    Args:
        llm_core: The agent's LLM model string (e.g. "qwen2.5:7b").
        task_type: The task type (e.g. "profile" or "task").

    Returns:
        A 1-D ``np.ndarray`` of length ``CONTEXT_DIM``.
    """
    features: List[float] = []
    features.extend(_one_hot(llm_core, KNOWN_LLM_FAMILIES))
    features.extend(_one_hot(task_type, KNOWN_TASK_TYPES))
    features.append(1.0)  # bias
    return np.asarray(features, dtype=float)


# ---------------------------------------------------------------------
# LinUCB bandit
# ---------------------------------------------------------------------


class LinUCBBandit:
    """A single LinUCB contextual bandit over a discrete action set.

    Implements the disjoint-model LinUCB algorithm: each arm ``a`` keeps
    a ridge-regression estimate of ``E[reward | context]`` via a matrix
    ``A_a`` (``d x d``, initialized to identity) and a vector ``b_a``
    (``d``, initialized to zero). For a context ``x`` the arm's score is

        p_a = theta_a . x + alpha * sqrt(x . A_a^{-1} . x)

    where ``theta_a = A_a^{-1} b_a``. The first term is the expected
    reward; the second is the exploration (UCB) bonus. The arm with the
    highest score is selected. Because the exploration bonus is large
    while an arm's ``A_a`` is still near-identity, every arm is tried
    before the policy commits — no arm is starved at initialization.

    State is in-memory and lives for the object's lifetime.

    Attributes:
        actions: The discrete action values (threshold buckets).
        n_arms: Number of arms (== ``len(actions)``).
        d: Context dimensionality.
        alpha: Exploration parameter (higher = more exploration).
    """

    def __init__(
        self,
        actions: List[float],
        context_dim: int,
        alpha: float = 1.0,
    ):
        """Initialize the bandit.

        Args:
            actions: Discrete action values (each an "arm"). Must be
                non-empty.
            context_dim: Dimensionality ``d`` of the context vectors.
            alpha: Exploration parameter (must be >= 0). Defaults to 1.0.

        Raises:
            ValueError: If ``actions`` is empty, ``context_dim`` < 1,
                or ``alpha`` < 0.
        """
        if not actions:
            raise ValueError("actions must be a non-empty list")
        if context_dim < 1:
            raise ValueError("context_dim must be >= 1")
        if alpha < 0:
            raise ValueError("alpha must be >= 0")

        self.actions: List[float] = list(actions)
        self.n_arms: int = len(self.actions)
        self.d: int = context_dim
        self.alpha: float = float(alpha)

        # Per-arm ridge-regression state.
        self._A: List[np.ndarray] = [
            np.identity(self.d) for _ in range(self.n_arms)
        ]
        self._b: List[np.ndarray] = [
            np.zeros(self.d) for _ in range(self.n_arms)
        ]

    def _validate_context(self, context: np.ndarray) -> np.ndarray:
        """Coerce and validate a context vector to shape ``(d,)``."""
        x = np.asarray(context, dtype=float).reshape(-1)
        if x.shape[0] != self.d:
            raise ValueError(
                f"context has dim {x.shape[0]}, expected {self.d}"
            )
        return x

    def arm_scores(self, context: np.ndarray) -> np.ndarray:
        """Return the LinUCB score for every arm given *context*.

        The score is ``mean + alpha * bonus`` — the exploitation
        estimate plus the exploration (UCB) bonus. The selected arm is
        ``argmax`` of this vector. Note that early on, untried arms
        carry a large bonus (optimism), so a freshly-rewarded arm may
        still score below untried ones until they are explored — this
        is the intended LinUCB behavior. To inspect *learning*
        specifically, use ``arm_mean_estimates`` (the exploitation term
        alone).

        Args:
            context: Context vector of length ``d``.

        Returns:
            ``np.ndarray`` of length ``n_arms`` with each arm's score.
        """
        x = self._validate_context(context)
        scores = np.empty(self.n_arms)
        for a in range(self.n_arms):
            A_inv = np.linalg.inv(self._A[a])
            theta = A_inv @ self._b[a]
            mean = float(theta @ x)
            bonus = self.alpha * float(np.sqrt(x @ A_inv @ x))
            scores[a] = mean + bonus
        return scores

    def arm_mean_estimates(self, context: np.ndarray) -> np.ndarray:
        """Return the exploitation term (theta_a . x) for every arm.

        This is the learned expected-reward estimate without the
        exploration bonus, useful for verifying that reward actually
        moves an arm's estimate (learning) independent of UCB optimism.

        Args:
            context: Context vector of length ``d``.

        Returns:
            ``np.ndarray`` of length ``n_arms`` with each arm's mean.
        """
        x = self._validate_context(context)
        means = np.empty(self.n_arms)
        for a in range(self.n_arms):
            theta = np.linalg.inv(self._A[a]) @ self._b[a]
            means[a] = float(theta @ x)
        return means

    def select_arm(self, context: np.ndarray) -> Tuple[float, int]:
        """Select the best arm for *context*.

        Ties are broken by the lowest arm index (via ``argmax``), which
        is deterministic.

        Args:
            context: Context vector of length ``d``.

        Returns:
            Tuple ``(action_value, arm_index)``.
        """
        scores = self.arm_scores(context)
        arm_index = int(np.argmax(scores))
        return self.actions[arm_index], arm_index

    def update(
        self,
        arm_index: int,
        context: np.ndarray,
        reward: float,
    ) -> None:
        """Update the chosen arm with an observed reward.

        Applies the standard LinUCB rank-1 update:
        ``A_a += x x^T`` and ``b_a += reward * x``.

        Args:
            arm_index: Index of the arm that was played.
            context: The context the decision was made under.
            reward: Observed scalar reward.

        Raises:
            IndexError: If ``arm_index`` is out of range.
        """
        if not (0 <= arm_index < self.n_arms):
            raise IndexError(
                f"arm_index {arm_index} out of range "
                f"[0, {self.n_arms})"
            )
        x = self._validate_context(context)
        self._A[arm_index] += np.outer(x, x)
        self._b[arm_index] += float(reward) * x


# ---------------------------------------------------------------------
# Policy manager
# ---------------------------------------------------------------------


class PolicyManager:
    """Manages the three independent adaptive-threshold bandits.

    Instantiates one ``LinUCBBandit`` per memory-control decision and
    exposes a uniform ``select_threshold`` / ``update`` API keyed by
    bandit name. All state is in-memory for the manager's lifetime.

    Bandit names (use these exact strings):
        - ``"novelty_threshold"``
        - ``"similarity_threshold"``
        - ``"redundancy_threshold"``
    """

    # Discretized action spaces (threshold buckets). All are on the
    # cosine-similarity scale exposed by the retriever (higher == more
    # similar). Rationale per bandit:
    #
    # novelty_threshold: a candidate is admitted only if its *max
    #   similarity* to existing memories is BELOW this value (i.e. it is
    #   novel enough). Buckets span 0.5–0.95: below 0.5 almost nothing is
    #   novel enough to reject, above 0.95 only near-duplicates are
    #   rejected. 6 buckets.
    #
    # similarity_threshold: a retrieved memory is injected only if its
    #   similarity to the query is ABOVE this value. Buckets span
    #   0.2–0.7: this is the practical relevance band for the injection
    #   pipeline (cf. the default relevance_threshold of 0.5 in config).
    #   6 buckets.
    #
    # redundancy_threshold: two retrieved memories are redundant if their
    #   pairwise similarity is ABOVE this value. Buckets span 0.7–0.95:
    #   only fairly-to-very similar pairs should be collapsed. 6 buckets.
    ACTION_SPACES: Dict[str, List[float]] = {
        "novelty_threshold": [0.50, 0.59, 0.68, 0.77, 0.86, 0.95],
        "similarity_threshold": [0.20, 0.30, 0.40, 0.50, 0.60, 0.70],
        "redundancy_threshold": [0.70, 0.75, 0.80, 0.85, 0.90, 0.95],
    }

    def __init__(self, alpha: float = 1.0):
        """Initialize the manager and its three bandits.

        Args:
            alpha: Exploration parameter shared by all three bandits.
                Defaults to 1.0.
        """
        self.alpha = float(alpha)
        self.context_dim = CONTEXT_DIM
        self._bandits: Dict[str, LinUCBBandit] = {
            name: LinUCBBandit(
                actions=actions,
                context_dim=CONTEXT_DIM,
                alpha=self.alpha,
            )
            for name, actions in self.ACTION_SPACES.items()
        }
        logger.info(
            "PolicyManager initialized: bandits=%s, context_dim=%d, "
            "alpha=%.3f",
            list(self._bandits.keys()),
            self.context_dim,
            self.alpha,
        )

    @property
    def bandit_names(self) -> List[str]:
        """The names of the managed bandits."""
        return list(self._bandits.keys())

    def _get_bandit(self, bandit_name: str) -> LinUCBBandit:
        """Return the named bandit or raise a clear error."""
        try:
            return self._bandits[bandit_name]
        except KeyError:
            raise KeyError(
                f"unknown bandit '{bandit_name}'; valid names: "
                f"{list(self._bandits.keys())}"
            )

    def select_threshold(
        self,
        bandit_name: str,
        llm_core: str,
        task_type: str,
    ) -> Tuple[float, int, np.ndarray]:
        """Select a threshold for the named decision under a context.

        Args:
            bandit_name: One of ``bandit_names``.
            llm_core: The agent's LLM model string.
            task_type: The task type.

        Returns:
            Tuple ``(threshold_value, arm_index, context_vector)``. The
            caller keeps ``arm_index`` and ``context_vector`` so it can
            later attribute a reward to this exact decision via
            ``update``.
        """
        bandit = self._get_bandit(bandit_name)
        context = build_context_vector(llm_core, task_type)
        threshold_value, arm_index = bandit.select_arm(context)
        logger.debug(
            "select_threshold[%s]: llm=%s task=%s -> "
            "value=%.3f arm=%d",
            bandit_name,
            llm_core,
            task_type,
            threshold_value,
            arm_index,
        )
        return threshold_value, arm_index, context

    def update(
        self,
        bandit_name: str,
        arm_index: int,
        context_vector: np.ndarray,
        reward_value: float,
    ) -> None:
        """Apply a reward to a previously-selected decision.

        This is the reward path that a future ``report_reward`` handler
        will call. It is *not* wired into the kernel in this subtask.

        Args:
            bandit_name: One of ``bandit_names``.
            arm_index: The arm returned by ``select_threshold``.
            context_vector: The context returned by ``select_threshold``.
            reward_value: Observed scalar reward.
        """
        bandit = self._get_bandit(bandit_name)
        bandit.update(arm_index, context_vector, reward_value)
        logger.debug(
            "update[%s]: arm=%d reward=%.4f",
            bandit_name,
            arm_index,
            reward_value,
        )

    def arm_scores(
        self,
        bandit_name: str,
        llm_core: str,
        task_type: str,
    ) -> np.ndarray:
        """Return per-arm LinUCB scores for a context (inspection/test).

        Args:
            bandit_name: One of ``bandit_names``.
            llm_core: The agent's LLM model string.
            task_type: The task type.

        Returns:
            ``np.ndarray`` of per-arm scores.
        """
        bandit = self._get_bandit(bandit_name)
        context = build_context_vector(llm_core, task_type)
        return bandit.arm_scores(context)

    def arm_mean_estimates(
        self,
        bandit_name: str,
        llm_core: str,
        task_type: str,
    ) -> np.ndarray:
        """Return per-arm learned mean estimates (inspection/test).

        The exploitation term alone (no UCB bonus), for verifying that
        reward moves an arm's estimate.

        Args:
            bandit_name: One of ``bandit_names``.
            llm_core: The agent's LLM model string.
            task_type: The task type.

        Returns:
            ``np.ndarray`` of per-arm mean estimates.
        """
        bandit = self._get_bandit(bandit_name)
        context = build_context_vector(llm_core, task_type)
        return bandit.arm_mean_estimates(context)
