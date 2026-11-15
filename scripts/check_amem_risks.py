"""Live check of the A-MEM backend's open risks, on A-MEM's real LLM
(NeurIPS Subtask 17; docs/AMEM_BACKEND.md, "Open risks").

Opt-in: it calls Azure gpt-4o (memory.backend_llm) through LiteLLM and
needs the local Ollama. Each user's statements are written through the
A-MEM provider as the v2 writers write them, twice, in two fresh
namespaces (stores in the process), then:

1. every note ``search`` and ``list`` return carries its write's
   ``owner_agent``, ``user_id``, ``sharing_policy``, ``memory_type``,
   ``fact_key`` and ``provenance_event``, after evolution rewrote notes;
2. deleting a write's note removes it from ``search`` and ``list``;
3. a forget through the memory library deletes the slot's note and every
   carrier, those whose derived text carries the value included, and
   leaves no note text, derived text or Chroma copy naming it.

It also reports, per write, the notes A-MEM's evolution changed, the
LLM calls and tokens, and where the two runs differ (generated tags and
contexts, the search order). Writes a JSON report. Usage:
    .venv/bin/python scripts/check_amem_risks.py --out report.json
"""
import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# (owner, slot, event, utterance, value, aliases), as the v2 writers
# store a statement: the value in ``structured``, its aliases in
# ``value_aliases`` (the forget finds a fact's forms there).
USERS = {
    "chat": [
        ("profile_agent", "team_chat", "u0-e1",
         "My team's chat tool is Mattermost.", "Mattermost", []),
        ("task_agent", "project", "u0-e2",
         "I'm working on the Larkspur migration this quarter.",
         "Larkspur migration", ["Larkspur"]),
        ("calendar_agent", "retro", "u0-e3",
         "Retro notes go in the Mattermost channel #retro.", "#retro", []),
        ("profile_agent", "home_city", "u0-e4", "I live in Utrecht.",
         "Utrecht", []),
    ],
    "lawyer": [
        ("profile_agent", "lawyer", "u1-e1", "My lawyer is Greta Sandvik.",
         "Greta Sandvik", ["Sandvik"]),
        ("calendar_agent", "call", "u1-e2", "Call with Sandvik on Friday.",
         "Friday", []),
        ("task_agent", "editor", "u1-e3",
         "I edit code in VS Code with Python.", "VS Code", []),
    ],
}
FORGET = {"chat": ("team_chat", "Mattermost"),
          "lawyer": ("lawyer", "Sandvik")}
KEYS = ("owner_agent", "user_id", "sharing_policy", "memory_type",
        "fact_key", "provenance_event")


def load_env():
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


class Evolved:
    """The provider's ``A-MEM write ... evolved <n> note(s)`` lines."""

    def __init__(self):
        import logging

        self.counts = []
        handler = logging.Handler()
        handler.emit = lambda record: self.counts.append(
            int(record.getMessage().split(" evolved ")[1].split()[0]))
        logger = logging.getLogger("aios.memory.providers.amem")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)


def amem_texts(provider, user):
    """Every text A-MEM keeps for the user: each note's content and
    derived text, and its Chroma document and metadata."""
    if not provider.stores.has(user):
        return []
    store = provider.stores.store(user)
    texts = [" ".join([note.content, str(note.context),
                       json.dumps(note.keywords), json.dumps(note.tags)])
             for note in store.memories.values()]
    stored = store.retriever.collection.get(
        include=["documents", "metadatas"])
    texts += [(document or "") + " " + json.dumps(meta, default=str)
              for document, meta in zip(stored["documents"],
                                        stored["metadatas"])]
    return texts


def run(namespace, memory, evolved):
    from aios.memory.embedding import EmbeddingConfig
    from aios.memory.note import MemoryNote
    from aios.memory.pipeline import MemoryPipeline, PipelineSettings
    from aios.memory.providers.amem import AMemProvider
    from cerebrum.utils import usage

    provider = AMemProvider()
    provider.initialize({
        "embedding": EmbeddingConfig.from_memory_config(memory).as_dict(),
        "backend_llm": memory["backend_llm"], "namespace": namespace,
    })
    report = {"namespace": namespace, "users": {},
              "versions": provider.versions}
    for name, statements in USERS.items():
        user = f"risk_{name}@users.example"
        found = report["users"][name] = {"writes": []}
        with usage.tagged(user):
            for owner, slot, event, text, value, aliases in statements:
                note = MemoryNote(content=text)
                note.metadata = {
                    "owner_agent": owner, "user_id": user,
                    "memory_type": "profile", "sharing_policy": "shared",
                    "created_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                    "fact_key": slot, "provenance_event": event,
                    "event_type": "add", "session": 1,
                    "structured": json.dumps({
                        "event_type": "add", "fact_key": slot,
                        "value": value}, sort_keys=True),
                    "value_aliases": json.dumps(aliases),
                }
                started = time.time()
                note_id = provider.add(note)
                found["writes"].append({
                    "event": event, "note": note_id,
                    "notes_changed": evolved.counts[-1],
                    "seconds": round(time.time() - started, 1)})
            records = usage.ACCUMULATOR.take(user, wait=5.0)
        found["llm"] = usage.summarize(records, usage.BACKEND_EXTRACTION)
        found["embedding"] = usage.summarize(records, usage.EMBEDDING)
        rows = provider.list(user, 1000)
        searched = provider.search(statements[0][3], user, 20)
        found["notes"] = {r.metadata.get("provenance_event"): {
            "tags": r.metadata.get("amem_tags"),
            "context": r.metadata.get("amem_context")} for r in rows}
        found["search_order"] = [r.metadata.get("provenance_event")
                                 for r in searched]
        missing = [
            {"id": r.memory_id, "missing": [
                k for k in KEYS if r.metadata.get(k) in (None, "")]}
            for r in rows + searched
            if any(r.metadata.get(k) in (None, "") for k in KEYS)]
        wrong_user = [r.memory_id for r in rows + searched
                      if r.metadata.get("user_id") != user]
        found["risk1_metadata_on_every_note"] = {
            "rows": len(rows), "searched": len(searched),
            "missing_keys": missing, "wrong_user": wrong_user,
            "holds": not missing and not wrong_user
            and len(rows) == len(statements)}
        event = statements[-1][2]
        mine = [r.memory_id for r in rows
                if r.metadata.get("provenance_event") == event]
        for memory_id in mine:
            provider.delete(memory_id, user)
        after = provider.list(user, 1000)
        after_search = provider.search(statements[-1][3], user, 20)
        found["risk2_delete"] = {
            "event": event, "deleted": mine,
            "holds": bool(mine) and not any(
                r.memory_id in mine for r in after + after_search)}
        slot, value = FORGET[name]
        pipeline = MemoryPipeline(provider, PipelineSettings(),
                                  usage_tag=usage.tagged)
        with usage.tagged(user):
            forgot = pipeline.forget("assistant_agent", user, slot)
        word = value.split()[-1]
        left = [t for t in amem_texts(provider, user) if word in t]
        found["forget"] = {"deleted": forgot.get("deleted"),
                           "scrubbed": forgot.get("scrubbed"),
                           "texts_left_naming_the_value": left,
                           "holds": not left}
    report["holds"] = all(
        u[k]["holds"] for u in report["users"].values()
        for k in ("risk1_metadata_on_every_note", "risk2_delete",
                  "forget"))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    load_env()
    import yaml

    memory = yaml.safe_load(
        (ROOT / "aios/config/config.yaml.example").read_text())["memory"]
    evolved = Evolved()
    runs = [run(f"risk{uuid.uuid4().hex[:8]}", memory, evolved)
            for _ in range(2)]
    differs = {}
    for name in USERS:
        a, b = (r["users"][name] for r in runs)
        differs[name] = {
            "tags_or_context": sorted(
                e for e in a["notes"] if a["notes"][e] != b["notes"].get(e)),
            "search_order": a["search_order"] != b["search_order"]}
    report = {"runs": runs, "differs": differs,
              "holds": all(r["holds"] for r in runs)}
    Path(args.out).write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({"holds": report["holds"], "differs": differs,
                      "out": args.out}, indent=1))
    return 0 if report["holds"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
