"""A scripted LLM for A-MEM's two prompts (docs/AMEM_BACKEND.md, "One
note per write"), so the provider's tests run A-MEM's own code on the
local Chroma and Ollama embedder with no LLM call.

- Analysis (``analyze_content``): keywords are the note's capitalized
  words, the context is "About: <content>", the tags ``["note"]``: the
  note's derived text carries its values.
- Evolution (``process_memory``): with ``evolve`` on, the new note is
  linked to the first neighbour shown, tagged ``["linked"]``, and every
  neighbour's context gets " Related: <new content>": evolution copies
  the new note's values into the neighbours, as A-MEM's LLM can. With
  ``evolve="tags"`` the neighbours' contexts are left as they are and
  their tags become the new note's last word: a value reaches another
  note through its tags alone.
"""
import json
import re

ANALYSIS = "Generate a structured analysis"
EVOLUTION = "memory evolution agent"
NEIGHBOR = re.compile(r"memory_id:(\S+)\t.*?memory context: (.*?)\t")


class ScriptedLLM:
    def __init__(self, evolve: bool = True):
        self.evolve = evolve
        self.calls = []

    def get_completion(self, prompt, response_format=None,
                       temperature=None, **_):
        if ANALYSIS in prompt:
            content = prompt.split("Content for analysis:", 1)[1].strip()
            self.calls.append("analysis")
            return json.dumps({
                "keywords": re.findall(r"\b[A-Z][a-zA-Z0-9-]+", content),
                "context": f"About: {content}", "tags": ["note"]})
        if EVOLUTION in prompt:
            self.calls.append("evolution")
            content = re.search(r"content: (.*)", prompt).group(1).strip()
            neighbors = NEIGHBOR.findall(prompt)
            if not self.evolve or not neighbors:
                return json.dumps({
                    "should_evolve": False, "actions": [],
                    "suggested_connections": [], "tags_to_update": [],
                    "new_context_neighborhood": [],
                    "new_tags_neighborhood": []})
            if self.evolve == "tags":
                word = content.rstrip(" .").split()[-1]
                return json.dumps({
                    "should_evolve": True, "actions": ["update_neighbor"],
                    "suggested_connections": [], "tags_to_update": [],
                    "new_context_neighborhood": [
                        context for _, context in neighbors],
                    "new_tags_neighborhood": [[word] for _ in neighbors]})
            return json.dumps({
                "should_evolve": True,
                "actions": ["strengthen", "update_neighbor"],
                "suggested_connections": [neighbors[0][0]],
                "tags_to_update": ["linked"],
                "new_context_neighborhood": [
                    f"{context} Related: {content}"
                    for _, context in neighbors],
                "new_tags_neighborhood": [["note", "evolved"]
                                          for _ in neighbors]})
        raise AssertionError(f"unexpected prompt: {prompt[:80]!r}")


def amem_ready() -> bool:
    try:
        import agentic_memory.memory_system  # noqa: F401
    except Exception:
        return False
    return True


needs_amem = __import__("pytest").mark.skipif(
    not amem_ready(), reason="needs agentic-memory (A-mem-sys) installed")


def amem_provider(evolve: bool = True, namespace: str = None):
    """The A-MEM provider with a scripted LLM, the pinned embedder and
    stores of its own (a namespace per call)."""
    import uuid

    from aios.memory.embedding import EmbeddingConfig
    from aios.memory.providers.amem import AMemProvider

    provider = AMemProvider()
    provider.initialize({
        "llm": ScriptedLLM(evolve=evolve),
        "embedding": EmbeddingConfig.from_memory_config({}).as_dict(),
        "namespace": namespace or uuid.uuid4().hex[:8],
    })
    return provider
