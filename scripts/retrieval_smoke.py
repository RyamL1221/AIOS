"""
Smoke checks for the kernel retrieval path, over real HTTP.

Needs a running kernel with the Mem0 provider and a local Ollama. Each
check writes to its own new user, so runs do not affect each other. With
``--kernel-log``, the kernel's log file, it also sends one GPT-4o chat on
Azure and checks that the Mem0 LLM synced to it.

    python scripts/retrieval_smoke.py [--kernel-log logs/kernel.log]

Most checks compare stored text exactly, so they need verbatim writes:
with ``memory.mem0.infer: true`` (``backend_extraction`` at
``/memory/config``) Mem0 rewrites every write into extracted facts and
those checks are skipped. Run once with ``infer: false`` for the full
set.
"""
import argparse
import sys
import time

import requests

BASE_URL = "http://localhost:8000"
MODEL = {"name": "qwen2.5:7b", "backend": "ollama"}
AZURE_MODEL = {"name": "gpt-4o", "backend": "azure"}
RUN = int(time.time())
KERNEL_LOG = None


def post(agent, query_type, query_data, user_id=None):
    """POST one /query request."""
    body = {
        "query_type": query_type,
        "agent_name": agent,
        "query_data": {"query_class": query_type, **query_data},
    }
    if user_id:
        body["user_id"] = user_id
    response = requests.post(f"{BASE_URL}/query", json=body, timeout=300)
    response.raise_for_status()
    return response.json()


def memory(agent, operation, **params):
    """Run one memory operation."""
    return post(agent, "memory", {
        "operation_type": operation, "params": params,
    })


def write(user, agent, content, policy="private", mtype="profile"):
    """Write a memory and return its id."""
    result = memory(agent, "add_memory", content=content, metadata={
        "user_id": user,
        "owner_agent": agent,
        "sharing_policy": policy,
        "memory_type": mtype,
    })
    return result["response"]["memory_id"]


def search(agent, user=None, k=5, content="q", **params):
    """Run an SDK-shaped search and return its result rows."""
    if user:
        params["user_id"] = user
    result = memory(
        agent, "retrieve_memory", content=content, k=k, **params
    )
    return result["response"]["search_results"]


def chat(user, model=MODEL):
    """Send a chat turn and return its injection diagnostics."""
    result = post("assistant_agent", "llm", {
        "llms": [model],
        "messages": [{"role": "user", "content": "hi"}],
        "action_type": "chat",
        "max_new_tokens": 8,
    }, user_id=user)
    return result["injection_diagnostics"]


def check_config():
    response = requests.get(f"{BASE_URL}/memory/config", timeout=10)
    response.raise_for_status()
    body = response.json()
    assert set(body) == {
        "relevance_threshold",
        "max_injected_memories",
        "max_memory_tokens",
        "provider",
        "capabilities",
        "embedding",
        "auto_inject",
        "auto_extract",
        "backend_llm",
        "backend_extraction",
        "pipeline",
        "pipeline_version",
    }, body
    assert set(body["pipeline"]) == {
        "relevance_threshold", "max_injected_memories",
        "max_memory_tokens", "write_barrier",
        "block_format", "block_recency",
    }, body
    assert set(body["embedding"]) == {
        "provider", "model", "dimension", "ollama_base_url",
    }, body


def check_privacy_gap():
    user = f"smoke_{RUN}_privacy"
    write(user, "profile_agent", "secret note")
    write(user, "profile_agent", "open note", policy="shared")
    write(user, "assistant_agent", "my note")
    contents = {r["content"] for r in search("assistant_agent", user)}
    assert contents == {"open note", "my note"}, contents
    diagnostics = chat(user)
    assert diagnostics["injected_count"] == 2, diagnostics


def check_scored_retrieval():
    user = f"smoke_{RUN}_scored"
    write(user, "profile_agent", "prefers Python and VS Code", "shared")
    write(user, "profile_agent", "lasagna needs ricotta", "shared")
    rows = search("assistant_agent", user, content="Python editor")
    assert rows[0]["content"] == "prefers Python and VS Code", rows
    assert all(isinstance(r["score"], float) for r in rows), rows
    assert rows[0]["score"] > rows[1]["score"], rows
    config = requests.get(f"{BASE_URL}/memory/config", timeout=10).json()
    diagnostics = chat(user)
    assert diagnostics["scores_present"] is True, diagnostics
    assert diagnostics["threshold_used"] == config[
        "relevance_threshold"
    ], diagnostics


def check_block_format():
    """The injected block uses the kernel's configured format
    (Subtask 9d: "compact" unless memory.block_format says "legacy")."""
    user = f"smoke_{RUN}_block"
    write(user, "profile_agent", "prefers Rust", "shared")
    pipeline = requests.get(
        f"{BASE_URL}/memory/config", timeout=10
    ).json()["pipeline"]
    assert pipeline["block_format"] in ("compact", "legacy"), pipeline
    diagnostics = chat(user)
    assert diagnostics["injected_count"] == 1, diagnostics
    assert diagnostics["block_format"] == pipeline["block_format"], (
        diagnostics, pipeline,
    )
    assert diagnostics["block_recency"] == pipeline["block_recency"]


def check_own_roundtrip_without_metadata():
    agent = f"smoke_agent_{RUN}"
    memory(agent, "add_memory", content="plain note", metadata={})
    contents = [r["content"] for r in search(agent)]
    assert contents == ["plain note"], contents


def check_get_memory_visibility():
    user = f"smoke_{RUN}_get"
    memory_id = write(user, "profile_agent", f"held {RUN}")
    allowed = memory(
        "profile_agent", "get_memory", memory_id=memory_id, user_id=user
    )
    assert allowed["response"]["content"] == f"held {RUN}", allowed
    denied = memory(
        "assistant_agent", "get_memory", memory_id=memory_id, user_id=user
    )
    assert not denied["response"]["success"], denied
    assert denied["response"]["content"] is None, denied


def check_update_delete_owner_only():
    user = f"smoke_{RUN}_owner"
    for policy in ("private", "shared"):
        memory_id = write(user, "profile_agent", f"{policy} v1", policy)
        for operation, extra in (
            ("update_memory", {"content": "stolen"}),
            ("remove_memory", {}),
        ):
            refused = memory(
                "assistant_agent",
                operation,
                memory_id=memory_id,
                user_id=user,
                **extra,
            )
            assert refused["response"]["error"] == "Memory not found", refused
        contents = {r["content"] for r in search("profile_agent", user)}
        assert f"{policy} v1" in contents, contents
        assert "stolen" not in contents, contents
        updated = memory(
            "profile_agent",
            "update_memory",
            memory_id=memory_id,
            content=f"{policy} v2",
            user_id=user,
        )
        assert updated["response"]["success"], updated
        contents = {r["content"] for r in search("profile_agent", user)}
        assert f"{policy} v2" in contents, contents
        removed = memory(
            "profile_agent", "remove_memory", memory_id=memory_id, user_id=user
        )
        assert removed["response"]["success"], removed
        contents = {r["content"] for r in search("profile_agent", user)}
        assert f"{policy} v2" not in contents, contents


def check_conversation_write_visible_immediately():
    user = f"smoke_{RUN}_conversation"
    chat(user)
    rows = search("assistant_agent", user)
    kinds = [r["metadata"]["memory_type"] for r in rows]
    assert kinds == ["conversation"], rows
    assert rows[0]["metadata"]["sharing_policy"] == "private", rows
    assert search("profile_agent", user) == [], "conversation leaked"


def check_memory_id_and_update():
    user = f"smoke_{RUN}_upsert"
    memory_id = write(user, "profile_agent", "old value", policy="shared")
    rows = search("profile_agent", user)
    assert rows[0]["memory_id"] == memory_id, rows
    result = memory(
        "profile_agent",
        "update_memory",
        memory_id=memory_id,
        content="new value",
        metadata={"user_id": user},
    )
    assert result["response"]["success"], result
    rows = search("profile_agent", user)
    assert [r["content"] for r in rows] == ["new value"], rows
    meta = rows[0]["metadata"]
    assert meta["sharing_policy"] == "shared", meta
    assert meta["owner_agent"] == "profile_agent", meta


def check_cap_and_top_k():
    user = f"smoke_{RUN}_cap"
    for index in range(25):
        write(user, "profile_agent", f"fact {index}", policy="shared")
    limit = requests.get(
        f"{BASE_URL}/memory/config", timeout=10
    ).json()["max_injected_memories"]
    diagnostics = chat(user)
    assert diagnostics["shared_fetched"] > 20, diagnostics
    assert diagnostics["after_dedupe"] > limit, diagnostics
    assert diagnostics["after_cap"] == limit, diagnostics
    assert diagnostics["injected_count"] <= limit, diagnostics


def check_azure_mem0_llm_sync():
    if KERNEL_LOG is None:
        raise RuntimeError("needs --kernel-log")
    with open(KERNEL_LOG) as handle:
        handle.seek(0, 2)
        chat(f"smoke_{RUN}_azure", AZURE_MODEL)
        time.sleep(1)
        new = handle.read()
    assert "Failed to sync Mem0 LLM" not in new, new[-2000:]
    assert "Mem0 LLM synced to litellm/azure/gpt-4o" in new, new[-2000:]


CHECKS = [
    check_block_format,
    check_config,
    check_privacy_gap,
    check_scored_retrieval,
    check_own_roundtrip_without_metadata,
    check_get_memory_visibility,
    check_update_delete_owner_only,
    check_conversation_write_visible_immediately,
    check_memory_id_and_update,
    check_cap_and_top_k,
    check_azure_mem0_llm_sync,
]


# Checks that need the kernel to store writes verbatim (see the module
# docstring); the Mem0 LLM sync check also needs the synced, not the
# pinned, backend LLM.
NEEDS_VERBATIM = {
    "check_privacy_gap", "check_scored_retrieval",
    "check_own_roundtrip_without_metadata", "check_get_memory_visibility",
    "check_update_delete_owner_only",
    "check_conversation_write_visible_immediately",
    "check_memory_id_and_update", "check_azure_mem0_llm_sync",
}


def main() -> int:
    """Run every check and report each result."""
    global KERNEL_LOG
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel-log")
    KERNEL_LOG = parser.parse_args().kernel_log
    failed = 0
    config = requests.get(f"{BASE_URL}/memory/config", timeout=10).json()
    internal_llm = config["capabilities"]["internal_llm"]
    extracting = bool(config.get("backend_extraction"))
    for check in CHECKS:
        if extracting and check.__name__ in NEEDS_VERBATIM:
            print(f"SKIP {check.__name__}: the backend extracts facts "
                  "(memory.mem0.infer); needs verbatim writes")
            continue
        if check is check_azure_mem0_llm_sync and KERNEL_LOG is None:
            print(f"SKIP {check.__name__}: no --kernel-log")
            continue
        if check is check_azure_mem0_llm_sync and not internal_llm:
            print(f"SKIP {check.__name__}: provider has no internal LLM")
            continue
        try:
            check()
            print(f"PASS {check.__name__}")
        except Exception as error:
            failed += 1
            print(f"FAIL {check.__name__}: {error!r}"[:600])
    print("SMOKE PASS" if not failed else f"SMOKE FAIL ({failed})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
