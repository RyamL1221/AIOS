"""Helpers for tests of the Graphiti provider (NeurIPS Subtask 16).

``ScriptedLLM`` answers Graphiti's prompts offline and deterministically
(docs/GRAPHITI_BACKEND.md, "Tests"): the user and one entity per fact;
each fact worded as the write's text (``split=False``, the contract
tests' verbatim case) or one fact per sentence (``split=True``); no
duplicate entities, no contradictions, no dates. Graphiti itself still
runs every step on the real Neo4j and the pinned embedder: entity
resolution, the verbatim merge of a restated fact, storage, search.

``graphiti_provider`` builds a provider on its own namespace (a group
prefix) and ``drop`` deletes everything in it, so tests never meet
another test's data in the shared database.
"""
import hashlib
import json
import os
import re
import socket
import uuid
from pathlib import Path

import pytest

AIOS_ROOT = Path(__file__).resolve().parents[3]
# The prompt templates put the message between the tags on lines of
# its own; capture it exactly, trailing spaces included.
CURRENT = re.compile(
    r"<CURRENT[ _]MESSAGE>\n(.*?)\n</CURRENT[ _]MESSAGE>", re.DOTALL)
ROLE = re.compile(r"^(?:\[[^\]]*\]\s*)?(?:user|assistant): ",
                  re.IGNORECASE)
COUNT = re.compile(r"contains (\d+) entities")
ENTITIES = re.compile(r"<ENTITIES>\s*(.*?)\s*</ENTITIES>", re.DOTALL)


def load_env() -> None:
    """NEO4J_* from AIOS/.env, without overriding the environment."""
    path = AIOS_ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def neo4j_ready() -> bool:
    load_env()
    if not os.environ.get("NEO4J_PASSWORD"):
        return False
    try:
        with socket.create_connection(("127.0.0.1", 7687), timeout=1):
            return True
    except OSError:
        return False


needs_neo4j = pytest.mark.skipif(
    not neo4j_ready(), reason="needs the local Neo4j (docs/GRAPHITI_BACKEND.md)")


def topic(fact: str) -> str:
    return "topic " + hashlib.sha256(fact.encode()).hexdigest()[:8]


def _llm_class():
    from graphiti_core.llm_client.client import LLMClient
    from graphiti_core.llm_client.config import LLMConfig

    class ScriptedLLM(LLMClient):
        def __init__(self, split: bool = False):
            super().__init__(LLMConfig(model="scripted",
                                       small_model="scripted"))
            self.split = split
            self.calls = []

        def facts(self, prompt: str):
            match = CURRENT.search(prompt)
            text = match.group(1) if match else ""
            lines = [ROLE.sub("", line, count=1) for line in text.split("\n")]
            text = "\n".join(line for line in lines if line.strip())
            if not self.split:
                return [text] if text.strip() else []
            return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text)
                    if s.strip()]

        async def _generate_response(self, messages, response_model=None,
                                     max_tokens=None, model_size=None, *,
                                     model=None):
            prompt = "\n".join(m.content for m in messages)
            name = response_model.__name__ if response_model else ""
            self.calls.append(name)
            if name == "ExtractedEntities":
                return {"extracted_entities": [
                    {"name": "user", "entity_type_id": 0}] + [
                    {"name": topic(f), "entity_type_id": 0}
                    for f in self.facts(prompt)]}
            if name == "ExtractedEdges":
                return {"edges": [
                    {"source_entity_name": "user",
                     "target_entity_name": topic(f),
                     "relation_type": "STATES", "fact": f,
                     "valid_at": None, "invalid_at": None}
                    for f in self.facts(prompt)]}
            if name == "NodeResolutions":
                count = COUNT.search(prompt)
                n = int(count.group(1)) if count else 0
                names = [""] * n
                block = ENTITIES.search(prompt)
                try:
                    for item in json.loads(block.group(1)) if block else []:
                        if 0 <= int(item.get("id", -1)) < n:
                            names[int(item["id"])] = item.get("name", "")
                except (ValueError, TypeError, AttributeError):
                    pass
                return {"entity_resolutions": [
                    {"id": i, "name": names[i], "duplicate_candidate_id": -1}
                    for i in range(n)]}
            if name == "EdgeDuplicate":
                return {"duplicate_facts": [], "contradicted_facts": []}
            if name == "EdgeTimestamps":
                return {"valid_at": None, "invalid_at": None}
            if name == "BatchEdgeTimestamps":
                return {"timestamps": []}
            if name == "SummarizedEntities":
                return {"summaries": []}
            return {}

    return ScriptedLLM


def scripted_llm(split: bool = False):
    return _llm_class()(split=split)


def graphiti_provider(llm=None, namespace=None):
    """A GraphitiProvider on the local Neo4j and the pinned embedder,
    with the scripted LLM, in a fresh namespace."""
    from aios.memory.embedding import EmbeddingConfig
    from aios.memory.providers.graphiti import GraphitiProvider

    load_env()
    provider = GraphitiProvider()
    provider.initialize({
        "embedding": EmbeddingConfig.from_memory_config({}).as_dict(),
        "backend_llm": {},
        "llm_client": llm if llm is not None else scripted_llm(),
        "namespace": namespace or f"t{uuid.uuid4().hex[:10]}",
    })
    return provider


def drop(provider) -> None:
    """Delete every node of the provider's namespace, then close it."""
    prefix = f"{provider.namespace}__"

    async def clear():
        await provider.graphiti.driver.execute_query(
            "MATCH (n) WHERE n.group_id STARTS WITH $prefix "
            "DETACH DELETE n", params={"prefix": prefix})

    try:
        provider.runner.run(clear)
    finally:
        provider.close()
