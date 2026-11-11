"""
GraphitiProvider: Zep's open-source temporal knowledge graph
(graphiti-core) on Neo4j, behind the provider contract.

NeurIPS Subtask 16; the design is docs/GRAPHITI_BACKEND.md. In short:

- One episode per write, in the user's group (``group_id``). A user's
  statement is a ``user:`` chat message, so Graphiti extracts facts
  about the user; a JSON object is a ``json`` episode.
- Graphiti takes no metadata, so ours is a sidecar on the episode node
  (``aios_metadata``), with per-fact changes beside it
  (``aios_row_metadata``: supersession marks, updates).
- A row is one fact as one write claims it: ``<fact uuid>:<episode
  uuid>``. Graphiti merges a restated fact onto the existing one and
  appends the episode, so a fact can have several rows, each with its
  write's metadata.
- ``search`` is Graphiti's documented ``search()`` (BM25 and cosine,
  reciprocal-rank fusion), unscored: ``scored_search`` is false. It runs
  through ``search_`` on a copy of the same recipe, because ``search()``
  writes its limit into the recipe object ingestion also reads.
- Graphiti's LLM (the pinned ``memory.backend_llm``) and embedder (the
  pinned ``memory.embedding``) come from ``cerebrum.utils.graphiti``, and
  every call runs under the caller's usage tag.
"""
import asyncio
import json
import logging
import uuid as uuid_lib
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from .base import Candidate, MemoryProvider, ProviderError, note_metadata

if TYPE_CHECKING:
    from aios.memory.note import MemoryNote

logger = logging.getLogger(__name__)

DEFAULT_SCOPE = "default"

_ROW_FIELDS = """
       r.uuid AS edge, r.fact AS fact, r.valid_at AS valid_at,
       r.invalid_at AS invalid_at, r.expired_at AS expired_at,
       size(r.episodes) AS claims, ep.uuid AS episode,
       ep.aios_metadata AS metadata, ep.aios_row_metadata AS row_metadata
"""

LIST_ROWS = """
MATCH (ep:Episodic {group_id: $group})
WHERE ep.aios_metadata IS NOT NULL
MATCH (:Entity)-[r:RELATES_TO {group_id: $group}]->(:Entity)
WHERE ep.uuid IN r.episodes
RETURN """ + _ROW_FIELDS + """
ORDER BY ep.created_at, ep.uuid, r.created_at, r.uuid
LIMIT $limit
"""

ROWS_OF_EDGES = """
MATCH (:Entity)-[r:RELATES_TO {group_id: $group}]->(:Entity)
WHERE r.uuid IN $edges
MATCH (ep:Episodic {group_id: $group})
WHERE ep.aios_metadata IS NOT NULL AND ep.uuid IN r.episodes
RETURN """ + _ROW_FIELDS + """
ORDER BY ep.created_at, ep.uuid
"""

ONE_ROW = """
MATCH (ep:Episodic {uuid: $episode, group_id: $group})
WHERE ep.aios_metadata IS NOT NULL
MATCH (:Entity)-[r:RELATES_TO {uuid: $edge, group_id: $group}]->(:Entity)
WHERE ep.uuid IN r.episodes
RETURN """ + _ROW_FIELDS


def _iso(value: Any) -> Optional[str]:
    """A Neo4j or Python datetime as an ISO string; None stays None."""
    if value is None:
        return None
    native = getattr(value, "to_native", None)
    if callable(native):
        value = native()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def split_id(memory_id: str) -> Optional[Tuple[str, str]]:
    """``(fact uuid, episode uuid)`` from a row id, or None."""
    parts = str(memory_id or "").split(":")
    if len(parts) != 2 or not all(parts):
        return None
    return parts[0], parts[1]


class GraphitiProvider(MemoryProvider):
    """Graphiti on Neo4j, one group per user (docs/GRAPHITI_BACKEND.md)."""

    # A write takes seconds; the write barrier orders a retrieval
    # accepted after it.
    synchronous_commit = False

    def __init__(self):
        self.runner = None
        self.graphiti = None
        self.default_user_id = DEFAULT_SCOPE
        self.namespace = ""
        # Graphiti extracts on every write; there is no verbatim mode.
        self.backend_extraction = True
        # Tests pass their own LLM and get a client of their own; the
        # kernel and the replicated agents share the process's client.
        self._shared = False
        # graphiti-core, the Neo4j driver and server, reported by
        # /memory/config for the run's provenance.
        self.versions: Optional[Dict[str, str]] = None

    # -- setup -------------------------------------------------------------

    def initialize(self, config: Dict[str, Any]) -> None:
        from . import ProviderInitializationError

        try:
            from cerebrum.utils import graphiti as clients

            self._clients = clients
            self.default_user_id = config.get("user_id") or DEFAULT_SCOPE
            self.namespace = str(config.get("namespace") or "")
            if self.namespace and not clients.GROUP_ID.match(
                    self.namespace):
                raise ValueError(
                    f"namespace {self.namespace!r}: letters, digits, "
                    "_ and - only")
            backend_llm = config.get("backend_llm") or {}
            embedding = config.get("embedding") or {}
            if config.get("llm_client") is None:
                self.runner, self.graphiti = clients.shared_graphiti(
                    backend_llm, embedding, config.get("neo4j"))
                self._shared = True
            else:
                self.runner = clients.GraphitiRunner()
                self.graphiti = clients.build_graphiti(
                    self.runner, backend_llm, embedding,
                    neo4j=config.get("neo4j"), llm=config["llm_client"])
            self.versions = clients.versions(self.runner, self.graphiti)
        except Exception as e:
            if self.runner is not None and not self._shared:
                self.runner.close()
            raise ProviderInitializationError(
                "graphiti", f"{type(e).__name__}: {e}") from e

    def capabilities(self) -> Dict[str, bool]:
        return {
            "scored_search": False,
            "semantic_search": True,
            "internal_llm": True,
            "native_sdk": True,
        }

    def close(self) -> None:
        if self._shared:  # the process's client outlives its users
            self.graphiti = None
            self.runner = None
            return
        if self.graphiti is not None and self.runner is not None:
            try:
                self.runner.run(self.graphiti.close)
            except Exception as e:  # closing never fails the caller
                logger.warning("Graphiti close failed: %s", e)
        if self.runner is not None:
            self.runner.close()
        self.graphiti = None
        self.runner = None

    # -- helpers -----------------------------------------------------------

    def _group(self, user_id: Optional[str]) -> str:
        """The user's group: Graphiti's form of the user id, after the
        store's namespace when it has one."""
        group = self._clients.group_id(user_id or self.default_user_id)
        return f"{self.namespace}__{group}" if self.namespace else group

    def _lock(self, group: str) -> asyncio.Lock:
        # Only ever called on the runner's loop.
        return self.runner.lock(group)

    def _run(self, fn, *args, **kwargs):
        if self.graphiti is None:
            raise ProviderError("Graphiti provider is not initialized")
        return self.runner.run(fn, *args, **kwargs)

    async def _query(self, cypher: str, **params) -> List[Any]:
        records, _, _ = await self.graphiti.driver.execute_query(
            cypher, params=params)
        return list(records)

    @staticmethod
    def _candidate(record: Any) -> Candidate:
        metadata = json.loads(record["metadata"] or "{}")
        changes = json.loads(record["row_metadata"] or "{}")
        metadata.update(changes.get(record["edge"]) or {})
        metadata.update({
            "graphiti_edge_uuid": record["edge"],
            "graphiti_episode_uuid": record["episode"],
            "graphiti_valid_at": _iso(record["valid_at"]),
            "graphiti_invalid_at": _iso(record["invalid_at"]),
            "graphiti_expired_at": _iso(record["expired_at"]),
            "graphiti_episode_count": record["claims"],
        })
        return Candidate(
            memory_id=f"{record['edge']}:{record['episode']}",
            content=record["fact"] or "",
            metadata=metadata,
        )

    async def _row(self, memory_id: str, group: str) -> Optional[Any]:
        ids = split_id(memory_id)
        if ids is None:
            return None
        rows = await self._query(
            ONE_ROW, edge=ids[0], episode=ids[1], group=group)
        return rows[0] if rows else None

    # -- add ---------------------------------------------------------------

    def add(self, memory_note: "MemoryNote") -> str:
        """One episode; returns the id of the write's first row, or
        ``""`` when Graphiti extracted no fact from it."""
        metadata = note_metadata(memory_note)
        scope = metadata.get("user_id") or self.default_user_id
        try:
            return self._run(self._add, memory_note, metadata, scope)
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(
                f"Graphiti add failed: {type(e).__name__}: {e}") from e

    async def _add(self, memory_note, metadata, scope) -> str:
        from graphiti_core.nodes import EpisodeType

        group = self._group(scope)
        owner = metadata.get("owner_agent", "")
        memory_type = metadata.get("memory_type", "")
        body, source = self._clients.episode_body(
            memory_note.content, memory_type)
        async with self._lock(group):
            result = await self.graphiti.add_episode(
                name=f"{owner}:{memory_type}:{memory_note.id}",
                episode_body=body,
                source_description=f"{owner} {memory_type}".strip(),
                reference_time=self._clients.utc_time(
                    metadata.get("created_at")),
                source=EpisodeType(source),
                group_id=group,
            )
            episode = result.episode.uuid
            await self._query(
                "MATCH (ep:Episodic {uuid: $episode}) "
                "SET ep.aios_metadata = $metadata, "
                "ep.aios_row_metadata = '{}'",
                episode=episode, metadata=json.dumps(metadata, default=str),
            )
        own = [e for e in result.edges if episode in (e.episodes or [])]
        invalidated = [e for e in result.edges
                       if episode not in (e.episodes or []) and e.expired_at]
        if invalidated:
            logger.info(
                "Graphiti invalidated %d fact(s) of group %s at episode %s",
                len(invalidated), group, episode)
        if not own:
            logger.info("Graphiti extracted no fact from episode %s of %s",
                        episode, group)
            return ""
        return f"{own[0].uuid}:{episode}"

    # -- reads -------------------------------------------------------------

    def search(
        self, query_text: str, user_id: Optional[str], top_k: int
    ) -> List[Candidate]:
        """Graphiti's ``search()`` for the user's group, its facts as
        rows in Graphiti's order, cut at ``top_k`` rows; unscored."""
        if top_k <= 0 or not (query_text or "").strip():
            return []
        try:
            return self._run(self._search, query_text, user_id, int(top_k))
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(
                f"Graphiti search failed: {type(e).__name__}: {e}") from e

    async def _search(self, query_text, user_id, top_k) -> List[Candidate]:
        from graphiti_core.search.search_config_recipes import (
            EDGE_HYBRID_SEARCH_RRF,
        )
        from graphiti_core.search.search_filters import SearchFilters

        group = self._group(user_id)
        # The recipe search() runs, copied: search() writes its limit
        # into the shared recipe, which ingestion reads too.
        config = EDGE_HYBRID_SEARCH_RRF.model_copy(deep=True)
        config.limit = top_k
        results = await self.graphiti.search_(
            query_text, config=config, group_ids=[group],
            search_filter=SearchFilters(),
        )
        order = [edge.uuid for edge in results.edges]
        if not order:
            return []
        rows: Dict[str, List[Candidate]] = {}
        for record in await self._query(
                ROWS_OF_EDGES, edges=order, group=group):
            rows.setdefault(record["edge"], []).append(
                self._candidate(record))
        found = [row for edge in order for row in rows.get(edge, [])]
        return found[:top_k]

    def list(self, user_id: Optional[str], top_k: int) -> List[Candidate]:
        """The user's rows in write order, unscored."""
        if top_k <= 0:
            return []
        try:
            records = self._run(self._query, LIST_ROWS,
                                group=self._group(user_id), limit=int(top_k))
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(
                f"Graphiti list failed: {type(e).__name__}: {e}") from e
        return [self._candidate(r) for r in records]

    def get(
        self, memory_id: str, user_id: Optional[str]
    ) -> Optional[Candidate]:
        try:
            record = self._run(self._row, memory_id, self._group(user_id))
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(
                f"Graphiti get failed: {type(e).__name__}: {e}") from e
        return self._candidate(record) if record is not None else None

    # -- writes to rows ----------------------------------------------------

    def update(
        self,
        memory_id: str,
        user_id: Optional[str],
        content: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> bool:
        """New content replaces the row's fact sentence verbatim and is
        re-embedded, with no LLM call; a fact other writes also claim is
        split first, so theirs keep the old sentence (on a copy, under
        new ids). Metadata merges into the row's own changes."""
        try:
            return self._run(
                self._update, memory_id, self._group(user_id), content,
                metadata)
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(
                f"Graphiti update failed: {type(e).__name__}: {e}") from e

    def update_metadata(
        self,
        memory_id: str,
        user_id: Optional[str],
        metadata: Dict[str, Any],
    ) -> bool:
        """The row's own metadata changes only; no embedding call."""
        return self.update(memory_id, user_id, None, metadata)

    async def _update(self, memory_id, group, content, metadata) -> bool:
        async with self._lock(group):
            record = await self._row(memory_id, group)
            if record is None:
                return False
            edge, episode = record["edge"], record["episode"]
            if content is not None:
                await self._replace_fact(edge, episode, group, content)
            if metadata:
                await self._merge_row_metadata(
                    episode, edge, metadata, group)
            return True

    async def _merge_row_metadata(self, episode, edge, metadata, group):
        rows = await self._query(
            "MATCH (ep:Episodic {uuid: $episode, group_id: $group}) "
            "RETURN ep.aios_row_metadata AS row_metadata",
            episode=episode, group=group)
        changes = json.loads((rows[0]["row_metadata"] if rows else None)
                             or "{}")
        # The kernel strips owner_agent, user_id and created_at from an
        # update; required keys are never removed (merge, not replace).
        changes[edge] = {**changes.get(edge, {}), **metadata}
        await self._query(
            "MATCH (ep:Episodic {uuid: $episode, group_id: $group}) "
            "SET ep.aios_row_metadata = $changes",
            episode=episode, group=group,
            changes=json.dumps(changes, default=str))

    async def _replace_fact(self, edge, episode, group, content):
        vector = await self.graphiti.embedder.create(content)
        records = await self._query(
            "MATCH ()-[r:RELATES_TO {uuid: $edge, group_id: $group}]->() "
            "RETURN r.episodes AS episodes", edge=edge, group=group)
        others = [e for e in (records[0]["episodes"] if records else [])
                  if e != episode]
        if others:
            copy = str(uuid_lib.uuid4())
            await self._query(
                "MATCH (a:Entity)-[r:RELATES_TO {uuid: $edge, group_id: "
                "$group}]->(b:Entity) "
                "CREATE (a)-[c:RELATES_TO]->(b) "
                "SET c = properties(r), c.uuid = $copy, c.episodes = $others",
                edge=edge, group=group, copy=copy, others=others)
            # The other writes' own changes move to the copy.
            for other in others:
                rows = await self._query(
                    "MATCH (ep:Episodic {uuid: $episode, group_id: $group}) "
                    "RETURN ep.aios_row_metadata AS row_metadata",
                    episode=other, group=group)
                changes = json.loads(
                    (rows[0]["row_metadata"] if rows else None) or "{}")
                if edge in changes:
                    changes[copy] = changes.pop(edge)
                    await self._query(
                        "MATCH (ep:Episodic {uuid: $episode, group_id: "
                        "$group}) SET ep.aios_row_metadata = $changes",
                        episode=other, group=group,
                        changes=json.dumps(changes, default=str))
        await self._query(
            "MATCH ()-[r:RELATES_TO {uuid: $edge, group_id: $group}]->() "
            "SET r.episodes = [$episode], r.fact = $fact "
            "WITH r CALL db.create.setRelationshipVectorProperty("
            "r, 'fact_embedding', $vector)",
            edge=edge, group=group, episode=episode, fact=content,
            vector=vector)

    def delete(self, memory_id: str, user_id: Optional[str]) -> bool:
        """Removes the write's claim on the fact: the fact is deleted
        when no write claims it, and an episode left with no fact is
        deleted. No LLM call."""
        try:
            return self._run(self._delete, memory_id, self._group(user_id))
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(
                f"Graphiti delete failed: {type(e).__name__}: {e}") from e

    async def _delete(self, memory_id, group) -> bool:
        async with self._lock(group):
            record = await self._row(memory_id, group)
            if record is None:
                return False
            edge, episode = record["edge"], record["episode"]
            await self._query(
                "MATCH ()-[r:RELATES_TO {uuid: $edge, group_id: $group}]->() "
                "SET r.episodes = [x IN r.episodes WHERE x <> $episode]",
                edge=edge, group=group, episode=episode)
            await self._query(
                "MATCH ()-[r:RELATES_TO {uuid: $edge, group_id: $group}]->() "
                "WHERE size(r.episodes) = 0 DELETE r",
                edge=edge, group=group)
            await self._delete_if_factless(episode, group)
            return True

    async def _delete_if_factless(self, episode, group, *,
                                  only_blank: bool = False) -> int:
        condition = " AND coalesce(ep.content, '') = ''" if only_blank else ""
        records = await self._query(
            "MATCH (ep:Episodic {uuid: $episode, group_id: $group}) "
            "WHERE NOT EXISTS { MATCH ()-[r:RELATES_TO {group_id: $group}]"
            "->() WHERE ep.uuid IN r.episodes }" + condition + " "
            "DETACH DELETE ep RETURN count(*) AS n",
            episode=episode, group=group)
        return int(records[0]["n"]) if records else 0

    # -- the forget's scrub --------------------------------------------------

    def scrub_history(
        self,
        user_id: Optional[str],
        forms: List[str],
        deleted_ids: List[str] = (),
        kept_ids: List[str] = (),
    ) -> Dict[str, int]:
        """Remove forgotten forms from what Graphiti keeps besides its
        facts (docs/GRAPHITI_BACKEND.md, "The forget on Graphiti"), with
        no LLM call:

        - ``messages``: the content of the user's episodes that carry a
          form, and of the deleted rows' episodes whatever it holds, is
          blanked (later writes read the user's latest episodes as
          context); an episode left with no fact and no content is
          deleted. Counted once per episode, a deleted row's episode
          that the delete already removed (its last fact) included.
        - ``history``: the user's entities whose name carries a form are
          deleted, with any fact still attached; the summaries that
          carry one are blanked. Counted once per entity.

        ``kept_ids`` are not needed: every episode and entity of the
        user is checked."""
        try:
            return self._run(
                self._scrub, self._group(user_id), list(forms or ()),
                list(deleted_ids or ()))
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(
                f"Graphiti scrub failed: {type(e).__name__}: {e}") from e

    async def _scrub(self, group, forms, deleted_ids) -> Dict[str, int]:
        from aios.memory.pipeline.matching import match_forms

        def carries(text: Optional[str]) -> bool:
            return bool(forms) and bool(text) and bool(
                match_forms(text, forms))

        deleted_episodes = {ids[1] for ids in map(split_id, deleted_ids)
                            if ids is not None}
        async with self._lock(group):
            episodes = await self._query(
                "MATCH (ep:Episodic {group_id: $group}) "
                "RETURN ep.uuid AS uuid, ep.content AS content",
                group=group)
            present = {record["uuid"] for record in episodes}
            # A deleted row's episode the delete already removed.
            gone = deleted_episodes - present
            blank = sorted(
                record["uuid"] for record in episodes
                if record["uuid"] in deleted_episodes
                or carries(record["content"]))
            if blank:
                await self._query(
                    "MATCH (ep:Episodic {group_id: $group}) "
                    "WHERE ep.uuid IN $uuids SET ep.content = ''",
                    group=group, uuids=blank)
            for episode in blank:
                await self._delete_if_factless(
                    episode, group, only_blank=True)
            entities = await self._query(
                "MATCH (n:Entity {group_id: $group}) "
                "RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary",
                group=group)
            named = sorted(r["uuid"] for r in entities if carries(r["name"]))
            summarized = sorted(
                r["uuid"] for r in entities
                if r["uuid"] not in named and carries(r["summary"]))
            if named:
                await self._query(
                    "MATCH (n:Entity {group_id: $group}) "
                    "WHERE n.uuid IN $uuids DETACH DELETE n",
                    group=group, uuids=named)
            if summarized:
                await self._query(
                    "MATCH (n:Entity {group_id: $group}) "
                    "WHERE n.uuid IN $uuids SET n.summary = ''",
                    group=group, uuids=summarized)
        if blank or gone or named or summarized:
            logger.info(
                "Graphiti scrub of %s: %d episode(s) blanked, %d gone "
                "with their last fact, %d entity name(s), %d "
                "summary(ies)", group, len(blank), len(gone), len(named),
                len(summarized))
        return {"messages": len(blank) + len(gone),
                "history": len(named) + len(summarized)}
