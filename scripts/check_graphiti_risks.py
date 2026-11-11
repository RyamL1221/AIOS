"""Live check of the Graphiti backend's two open risks, on real
extraction (NeurIPS Subtask 16; docs/GRAPHITI_BACKEND.md, "Open risks").

Opt-in: it calls Azure gpt-4o (memory.backend_llm) through LiteLLM and
needs the local Neo4j and Ollama. Each user's statements are written
through the Graphiti provider as the v2 writers write them, then:

1. every fact ``search`` and ``list`` return carries its write's
   ``owner_agent``, ``user_id``, ``sharing_policy``, ``memory_type``,
   ``fact_key`` and ``provenance_event``, and every write that stored a
   fact can find a row of its own;
2. deleting a write's rows removes them from ``search`` and ``list``;
3. a forget through the memory library deletes the slot's rows and every
   carrier, and leaves no episode, entity name, summary or fact of the
   user naming the value.

Everything runs in its own namespace, dropped at the end. Writes a JSON
report. Usage:
    .venv/bin/python scripts/check_graphiti_risks.py --out report.json
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    load_env()
    import yaml

    from aios.memory.embedding import EmbeddingConfig
    from aios.memory.note import MemoryNote
    from aios.memory.pipeline import MemoryPipeline, PipelineSettings
    from aios.memory.providers.graphiti import GraphitiProvider
    from cerebrum.utils import usage

    memory = yaml.safe_load(
        (ROOT / "aios/config/config.yaml.example").read_text())["memory"]
    namespace = f"risk{uuid.uuid4().hex[:8]}"
    provider = GraphitiProvider()
    provider.initialize({
        "embedding": EmbeddingConfig.from_memory_config(memory).as_dict(),
        "backend_llm": memory["backend_llm"], "namespace": namespace,
    })
    report = {"namespace": namespace, "users": {}, "versions": None}
    try:
        report["versions"] = provider.versions
        for name, statements in USERS.items():
            user = f"risk_{name}@users.example"
            found = report["users"][name] = {"writes": []}
            ids_by_event = {}
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
                    first = provider.add(note)
                    found["writes"].append({
                        "event": event, "text": text, "first_row": first,
                        "seconds": round(time.time() - started, 1)})
                    ids_by_event[event] = first
                records = usage.ACCUMULATOR.take(user, wait=5.0)
            found["llm"] = usage.summarize(records, usage.BACKEND_EXTRACTION)
            found["embedding"] = usage.summarize(records, usage.EMBEDDING)
            rows = provider.list(user, 1000)
            searched = provider.search(statements[0][3], user, 20)
            events = {s[2] for s in statements}
            found["rows"] = [{"id": r.memory_id, "fact": r.content,
                              "event": r.metadata.get("provenance_event"),
                              "claims": r.metadata.get(
                                  "graphiti_episode_count"),
                              "invalid_at": r.metadata.get(
                                  "graphiti_invalid_at")} for r in rows]
            missing = [
                {"id": r.memory_id, "missing": [
                    k for k in KEYS if r.metadata.get(k) in (None, "")]}
                for r in rows + searched
                if any(r.metadata.get(k) in (None, "") for k in KEYS)]
            wrong_user = [r.memory_id for r in rows + searched
                          if r.metadata.get("user_id") != user]
            found["risk1_metadata_on_every_fact"] = {
                "rows": len(rows), "searched": len(searched),
                "missing_keys": missing, "wrong_user": wrong_user,
                "writes_with_no_fact": sorted(
                    e for e, first in ids_by_event.items() if not first),
                "writes_with_a_row": sorted(
                    {r.metadata.get("provenance_event") for r in rows}
                    & events),
                "holds": not missing and not wrong_user,
            }
            # Risk 2: delete one write's rows.
            event = statements[-1][2]
            mine = [r.memory_id for r in rows
                    if r.metadata.get("provenance_event") == event]
            for memory_id in mine:
                provider.delete(memory_id, user)
            after = provider.list(user, 1000)
            after_search = provider.search(statements[-1][3], user, 20)
            found["risk2_delete"] = {
                "event": event, "deleted": mine,
                "left_in_list": [r.memory_id for r in after
                                 if r.memory_id in mine],
                "left_in_search": [r.memory_id for r in after_search
                                   if r.memory_id in mine],
                "holds": bool(mine) and not any(
                    r.memory_id in mine for r in after + after_search),
            }
            # The forget, through the library.
            slot, value = FORGET[name]
            pipeline = MemoryPipeline(provider, PipelineSettings(),
                                      usage_tag=usage.tagged)
            with usage.tagged(user):
                forgot = pipeline.forget("assistant_agent", user, slot)
            texts = graphiti_texts(provider, user)
            word = value.split()[-1]
            found["forget"] = {
                "deleted": forgot.get("deleted"),
                "scrubbed": forgot.get("scrubbed"),
                "texts_left_naming_the_value": [t for t in texts
                                                if word in t],
                "holds": not [t for t in texts if word in t],
            }
        report["holds"] = all(
            u[k]["holds"] for u in report["users"].values()
            for k in ("risk1_metadata_on_every_fact", "risk2_delete",
                      "forget"))
    finally:
        drop(provider)
    Path(args.out).write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({"holds": report.get("holds"),
                      "out": args.out}, indent=1))
    return 0 if report.get("holds") else 1


def graphiti_texts(provider, user):
    async def texts():
        records, _, _ = await provider.graphiti.driver.execute_query(
            "MATCH (n {group_id: $group}) RETURN coalesce(n.content, '') "
            "AS a, coalesce(n.name, '') AS b, coalesce(n.summary, '') AS c "
            "UNION ALL MATCH ()-[r:RELATES_TO {group_id: $group}]->() "
            "RETURN r.fact AS a, '' AS b, '' AS c",
            params={"group": provider._group(user)})
        return [t for r in records for t in (r["a"], r["b"], r["c"]) if t]
    return provider.runner.run(texts)


def drop(provider):
    prefix = f"{provider.namespace}__"

    async def clear():
        await provider.graphiti.driver.execute_query(
            "MATCH (n) WHERE n.group_id STARTS WITH $prefix "
            "DETACH DELETE n", params={"prefix": prefix})
    provider.runner.run(clear)


if __name__ == "__main__":
    sys.exit(main())
