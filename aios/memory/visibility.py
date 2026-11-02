"""
The visibility rule for cross-agent memory retrieval.

Applied by the kernel only, in ``MemoryManager.retrieve_for_agent``;
providers never filter by visibility (docs/PROVIDER_CONTRACT.md).
"""


def apply_sharing_filter(
    candidates: list,
    agent_name: str,
    user_id: str | None,
    sharing_policy: str | None,
    get_metadata: callable,
) -> list:
    """Filter candidate memories by ownership and sharing rules.

    Implements the decision matrix for cross-agent memory retrieval.
    Each candidate is kept or dropped based on the combination of
    ``user_id`` and ``sharing_policy`` supplied by the caller, plus
    the metadata stored on the memory itself.

    Safe defaults:
    - Missing ``sharing_policy`` in metadata → treated as ``"private"``
    - Missing ``owner_agent`` in metadata → never matches any agent

    Privacy invariant: a memory whose ``owner_agent`` differs from
    *agent_name* is **never** returned unless its metadata
    ``sharing_policy`` is exactly ``"shared"``.

    Args:
        candidates: Raw results from the provider's search.
        agent_name: The requesting agent's name.
        user_id: Optional user_id filter from query.params.
        sharing_policy: Optional sharing_policy filter from
            query.params.
        get_metadata: Callable that extracts a metadata dict from
            a single candidate item.  Must return a dict with keys:
            ``owner_agent``, ``user_id``, ``sharing_policy``.

    Returns:
        Filtered list of candidates that pass the sharing rules.
    """
    result = []
    for candidate in candidates:
        meta = get_metadata(candidate)
        mem_owner = meta.get("owner_agent", "")
        mem_user = meta.get("user_id", "")
        mem_policy = meta.get("sharing_policy", "") or "private"

        is_own = mem_owner == agent_name

        # --- privacy invariant ---
        if not is_own and mem_policy != "shared":
            continue

        if user_id is None and sharing_policy is None:
            # Default: agent-scoped only
            if is_own:
                result.append(candidate)

        elif user_id is None and sharing_policy is not None:
            # Policy filter within agent scope
            if is_own and mem_policy == sharing_policy:
                result.append(candidate)

        elif user_id is not None and sharing_policy is None:
            # User-scoped with implicit privacy
            if mem_user == user_id and (
                is_own or mem_policy == "shared"
            ):
                result.append(candidate)

        elif (
            user_id is not None
            and sharing_policy == "shared"
        ):
            # Cross-agent shared
            if (
                mem_user == user_id
                and mem_policy == "shared"
            ):
                result.append(candidate)

        elif (
            user_id is not None
            and sharing_policy == "private"
        ):
            # Own private only
            if (
                is_own
                and mem_user == user_id
                and mem_policy == "private"
            ):
                result.append(candidate)

        else:
            # Any other sharing_policy value with user_id
            if (
                mem_user == user_id
                and mem_policy == sharing_policy
            ):
                if is_own or mem_policy == "shared":
                    result.append(candidate)

    return result
