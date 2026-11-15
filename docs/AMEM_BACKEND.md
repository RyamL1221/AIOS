# A-MEM backend (NeurIPS Subtask 17)

A-MEM (Xu et al., 2025, "A-MEM: Agentic Memory for LLM Agents",
arXiv:2502.12110) keeps each memory as a note that its own LLM annotates
(keywords, a context sentence, tags) and links to related notes, and it
"evolves" the notes a new one is close to: their tags and context are
rewritten as notes arrive. It is the fourth backend, and the only one
whose stored rows are rewritten after they are written. This document
fixes, before any provider code, how A-MEM plugs into the provider
contract (`PROVIDER_CONTRACT.md`) beneath the kernel and the replicated
agents, and what the forget and supersession can and cannot do on it.
The native condition is specified in `NATIVE_USAGE.md` ("native_amem").

Facts below about A-MEM come from its source at the pinned commit (cited
as `memory_system.py:line`, `retrievers.py:line`, `llm_controller.py:line`
in the package `agentic_memory`), from its README at that commit, and
from an exploration on 2026-11-12 against the pinned stack ("Exploration"
below).

## Which A-MEM

A-MEM is research code with three public repositories. Decided by the
user on 2026-11-12, after the exploration: **WujiangXu/A-mem-sys at
`f303dfc71e07bdc787f4bc135d4cea328ae30e99`** (2025-11-06), which the
paper's reproduction repository calls "our official implementation" for
building agents.

- **agiresearch/A-mem** (`ceffb860`, 2025-12-12), the repository the
  task named, is an older fork. At its HEAD `add_note` generates no
  keywords, context or tags (`analyze_content` exists, nothing calls
  it); evolution indexes the store's notes by their position in the
  neighbour search, so it rewrote the tags of the store's five oldest
  notes, not the neighbours' (8 writes, twice); the links it makes are
  those positions ("0", "1"), which never resolve, so `search_agentic`
  never adds a linked note; and Chroma embeds the content alone. There,
  retrieval is plain vector search over the verbatim text and evolution
  changes only tags no block shows.
- **WujiangXu/A-mem-sys** (`f303dfc`) generates the attributes on
  `add_note` when they are missing (`memory_system.py:244-265`), shows
  the LLM its neighbours by note id, so links resolve and evolution
  updates the neighbours it was shown (`:314-340`, `:721-743`), and
  embeds the content with its context, keywords and tags
  (`retrievers.py:30-74`).
- **WujiangXu/AgenticMemory** is the paper's reproduction code, not a
  library ("This repository is specifically designed to reproduce the
  results presented in our paper", its README).

## Versions and setup

- `agentic-memory` 0.0.1 installed from
  `git+https://github.com/WujiangXu/A-mem-sys@f303dfc71e07bdc787f4bc135d4cea328ae30e99`
  in both venvs, without its own dependency resolution (`--no-deps`). Its
  modules import `sentence_transformers`, `transformers`, `nltk`,
  `rank_bm25`, `sklearn`, `chromadb` and `litellm` when loaded
  (`memory_system.py:1-20`, `retrievers.py:1-13`), so those a venv
  lacked are installed beside it, pip choosing versions that change
  nothing installed: in the AIOS venv `rank_bm25`; in Cerebrum's also
  `sentence-transformers`, `transformers`, `torch` and `nltk`, with
  their own new dependencies. A-MEM's sentence-transformers model is
  never loaded (the provider gives the system the pinned embedder,
  "Store, partition and isolation"), so the two venvs' different
  versions of it reach no row. The commit is pinned in AIOS
  `requirements.txt` and in Cerebrum `requirements-amem.txt` (with the
  packages Cerebrum's venv lacked, at the versions installed; installed
  with `--no-deps`), not in Cerebrum's `requirements.txt`, the SDK
  package's dependency list, which cannot carry a git reference. Tests
  check both pins and the installed commit in each venv (AIOS
  `tests/environment/test_amem_pin.py`, Cerebrum
  `tests/agents/test_amem_pin.py`), as for `graphiti-core`.
- No server: A-MEM is a library. Its notes live in the process
  (`AgenticMemorySystem.memories`, a dict), and its vectors in a Chroma
  collection (`retrievers.py:18-28`).
- Chroma telemetry is off (`anonymized_telemetry=False`), as for Mem0.

The pinned commit goes into every run's `PROVENANCE.md`, and
`/memory/config` reports it in `backend_versions`.

## What A-MEM stores

- A **note** (`MemoryNote`, `memory_system.py:24-81`): `content`, `id`
  (a UUID), `keywords`, `links` (note ids), `context` (one sentence,
  "General" by default), `category` ("Uncategorized" by default), `tags`,
  `timestamp` and `last_accessed` (`YYYYMMDDHHMM`), `retrieval_count` and
  `evolution_history`. Nothing writes the last two. There is no free
  metadata mapping: `add_note(content, **kwargs)` passes its keywords to
  `MemoryNote`, so an unknown key is a `TypeError`.
- Its **Chroma document** (`retrievers.py:30-74`): the content with
  " context: ...", " keywords: ..." and " tags: ..." appended when set,
  embedded; the note's fields as metadata (lists as JSON), and that
  document as `enhanced_content`.
- Nothing else: no message history, no log of changes.

The two copies drift. Evolution rewrites a neighbour's `tags` and
`context` in the process's note (`:732-743`) but not its Chroma document
or metadata, which keep what they had when the note was written or last
updated (A-MEM's `update` re-adds the document from the process's note;
a supersession mark rewrites the Chroma `category`, below). Search
ranks by the Chroma document, `search_agentic` returns a hit's Chroma
metadata (`:544-585`), and evolution shows the LLM each neighbour's
Chroma copy (`find_related_memories`, `:314-340`): each evolution starts
from the neighbour as first written, so a later one rewrites, and can
drop, what an earlier one added.

## One note per write

A write is one `add_note(content, category=<our metadata>, time=<the
write's time, YYYYMMDDHHMM>)`:
1. `MemoryNote` is built; its keywords, context and tags are missing, so
   A-MEM's LLM generates them (`analyze_content`, `:163-235`; one call).
2. If the store holds a note, evolution (`process_memory`, `:625-753`):
   the five notes nearest the new content in Chroma are shown to the LLM
   with their ids (one call), which decides whether to evolve and how:
   `strengthen` links the new note to some of them and sets its tags;
   `update_neighbor` rewrites the shown notes' tags and context.
3. The note goes into the dict and into Chroma.

So a write is about two LLM calls; the first write of a store is one.
The content is stored verbatim: the row a write gives is the note, and
its text is what the writer wrote (a statement; in v1 a JSON payload; a
conversation turn as its "User:" and "Assistant:" lines). A write that
returns has stored its note. A-MEM catches its LLM's errors in both
steps (`:233-235`, `:746-753`): a failed analysis leaves the defaults, a
failed evolution keeps what it applied before the error (a
`strengthen`'s links and tags), each with a printed or logged line, and
the note is still stored.

Every locus writes through one helper (Cerebrum `cerebrum/utils/amem.py`,
`add_note`), which logs, for each write, `A-MEM evolved <n> note(s) at
note <id>`: the existing notes whose tags, context or links its
evolution changed. The kernel's provider logs a line of its own for the
same write (`A-MEM write <id> of <user> evolved <n> note(s)`), which is
not counted. "Notes changed per write" is counted from the helper's
lines in each cell's logs; the results files do not record it.

## Metadata: in `category`

A-MEM's notes carry no metadata mapping, and evolution rewrites `tags`
and `context`. `category` is a free string that `add_note` accepts and
nothing in A-MEM writes after (evolution touches `links`, `tags` and
`context` only, `:717-743`). `search()` returns a hit's id, content,
context, keywords, tags and distance, not its `category`, so the
provider and the native agents read each hit's note from the store's
dict, `category` included. So our metadata (the required keys and the
v2 statement
fields, `PROVIDER_CONTRACT.md`, "Required metadata") is the note's
`category`, as JSON, in every locus: the kernel's provider and the
replicated agents' (the same provider), and the native agents (their
own keys). In the exploration every note's `category` was intact after
14 evolution decisions (two runs of eight writes).

- A **row** is a note: `memory_id` is the note id, `content` its
  content, `metadata` its `category` parsed, plus A-MEM's note id and
  links (`amem_note_id`, `amem_links`). A row does not carry A-MEM's
  keywords, context or tags: evolution writes them from the user's other
  notes, another agent's private ones included, and the kernel's
  visibility rule keeps or drops whole rows, so a row's derived text
  would carry a private value past it (found on review).
- A supersession mark changes the note's `category` in the dict and in
  Chroma's metadata (`collection.update`, no re-embedding), not through
  A-MEM's `update`, which deletes and re-adds the document
  (`:387-426`).

## Search: `search`, in every locus

The native condition uses A-MEM's `search(query, k)`, the README's first
search example ("Enhanced Retrieval with Metadata"), decided by the user
on 2026-11-12. (An earlier decision that day chose `search_agentic`,
asked with the agiresearch/A-mem README in view, whose only search
example it is; the README at the pinned commit lists it under
"Alternative search methods".) The kernel's and the replicated agents'
provider uses `search` too, for three reasons: it is the native
condition's call, so the loci differ in what they do with A-MEM's notes
and not in how they ask for them; every row it returns has a score, so
the provider can say `scored_search` true and be ranked as in-house and
Mem0 are; and it reads each note as it is now (`search_agentic` returns
a hit's Chroma metadata, written with the note).

- `search` (`:462-481`) queries Chroma for `k` notes and returns them in
  Chroma's order (nearest first), each from the process's notes, with
  its distance as `score`.
- **The check.** `search_agentic` (`:544-623`) returns the same notes in
  the same order: it adds the notes Chroma's hits link to after the
  hits and then cuts the list at `k`, and Chroma returns `min(k, notes
  in the store)` hits, so with `k` notes or more in the store the hits
  fill the list and the cut drops every linked note, and with fewer every
  note is already a hit. In the exploration both gave the same hits in
  the same order, and a test checks it with stores larger and smaller
  than `k` (`test_search_agentic_returns_searchs_notes`).
- Chroma's collection has no distance space, so the distance is squared
  L2. The pinned embedder's vectors are unit vectors (Mem0's evidence,
  `NATIVE_USAGE.md`), so a note's cosine is `1 - d/2`, the provider's
  similarity; `scored_search` is true. With `relevance_threshold` 0.0 the
  kernel drops a note only at a negative cosine; every note of the
  exploration was between 0.34 and 0.69.
- `k` is the kernel's own fetch (own k, shared 4k; v2 k = 30 since
  Amendment 6, v1 k = 10); the native consumer's k is 10, and it uses
  A-MEM's order and A-MEM's distance as the score, filtering on none.
  Only a V4 consumer at H = 2 (`HETEROGENEITY.md`) sets a threshold
  (0.5), and it applies it to that score as returned, as native Mem0's
  V4 consumer does to Mem0's: it keeps the notes at distance 0.5 or more
  (cosine 0.75 or less) and drops nearer ones.

## Store, partition and isolation

- One `AgenticMemorySystem` per user: the user's store, as Mem0 has a
  collection per user and Graphiti a group. Its notes are its own; its
  Chroma collection is the user's (`amem_<readable part>_<12 hex of
  SHA-256>`, Chroma's name rules; the native agents' stores add a
  namespace, `amem_native_<readable part>_<12 hex>`), in a Chroma client
  of the stores' own, not the process's default in-memory one: a
  `PersistentClient` on a temporary directory removed when the process
  exits, one per set of stores (the native agents' set is apart from the
  provider's).
- A-MEM's constructor makes a retriever on the process's default
  in-memory Chroma client, `reset()`s it (`:117-118`) and loads a
  sentence-transformers model by name; all instances share one
  collection, `memories`. The provider builds the system without that
  retriever and gives it the user's, so building one user's store
  deletes nothing of another's. `consolidate_memories`, which A-MEM
  runs every 100 evolutions (`:286-289`), would rebuild into the shared
  default collection; the provider's system rebuilds into the user's
  own. No benchmark store reaches it (v2: about 18 writes a user on
  average, at most 22; v1: three).
- No persistence: a new process starts with no store. The kernel and
  each harness process keep theirs for the run.
- A per-user lock: one write or read of a store at a time (A-MEM's dict
  and evolution are not thread-safe).

## list, get, update, delete

- `list`: the user's notes, in the order written (the dict's order).
- `get`: one note (`read`, `:376-385`), the user's only.
- `update`: A-MEM's `update(note_id, content=...)` (`:387-426`): the
  content changes and the document is re-added with the note's old
  keywords, context and tags; A-MEM does not analyse it again.
- `delete`: A-MEM's `delete(note_id)` (`:428-443`): the note leaves the
  dict and Chroma.

## What deleting a note leaves

- **Evolved text in other notes.** Evolution writes a neighbour's
  context and tags from the new note's content, so another note's
  context or tags can carry a deleted note's value; in the exploration,
  a note about the user's name got the tag "staging server" from a later
  note about the staging server.
- **Stale Chroma copies.** Another note's Chroma document and metadata
  are what they were when it was written or last updated (evolution
  never rewrites them; A-MEM's `update` re-adds the document from the
  process's note, and a supersession mark rewrites the Chroma
  `category`), so they can carry a value its process note no longer
  does, and the reverse.
- **Dangling links.** Other notes keep the deleted note's id in `links`;
  `search_agentic` skips a link to no note (`:605-606`). An id is not a
  value.

## The forget on A-MEM

The library's forget (`DELETION_AND_SUPERSESSION.md`) deletes every row
of the slot and every row whose text carries a form of the fact (the
scorer's matcher, aliases included). On A-MEM a row's text is the note's
content. A-MEM's other text is the analogue of Graphiti's entity names
and summaries, and it is handled like them, in `scrub_history`, with no
LLM call:
- a note whose generated text (in the process: `context`, `keywords`,
  `tags`; in Chroma: its document and metadata) carries a form is a
  carrier, and is deleted (Subtask 15, Decision 1: carriers are
  deleted), whoever owns it;
- such notes are reported as `detached` rows, which the library reports
  as deleted with the reason `derived` (a backend's derived text carried
  a form; Graphiti's are `entity`), or as swept after a write;
- `messages` is 0 (A-MEM keeps no messages), and `history` counts the
  notes so deleted.

A deleted note can therefore take another fact with it, as a Mem0 fold
does; the forget reading counts these deletions in its `derived` column,
and in `other_agents` when another agent wrote the note (`same_writer`
counts value and alias deletions only). The scrub deletes every note
whose derived text, in the store or in Chroma, carries a form, so after
a forget no note A-MEM keeps carries one. The runs' audit reads rows'
content only, so this is checked by the unit tests (a value in a
neighbour's context, in its tags alone, in its stale Chroma copy) and by
the live risk check, not measured in the runs.

## Supersession

A-MEM has no supersession of its own: evolution never marks a note out
of date. The kernel's (`memory.supersession: exclude`) marks a slot's
earlier notes in their `category` and the selector excludes them.
Nothing is recorded apart, as Graphiti's invalidations are.

## LLM, embedder and cost

- **LLM.** A-MEM's controllers call OpenAI's client, Ollama, SGLang or
  OpenRouter (`llm_controller.py:45-237`), at temperature 1.0 by
  default, and the memory system calls `get_completion(prompt,
  response_format=...)` without one. The provider gives the system a
  controller that calls the synchronous `litellm.completion` with the
  pinned `memory.backend_llm` (Azure gpt-4o, temperature 0, seed
  20261105), with A-MEM's own messages and `response_format`
  (`json_schema`), and strips code fences, as Graphiti's client does.
  The call is synchronous in the caller's thread, so the trial's usage
  tag applies: each is a `backend_extraction` record of the trial.
- **Embedder.** The pinned `memory.embedding` (Ollama
  `nomic-embed-text`, 768) as the collection's embedding function,
  through the same `ollama.Client.embed` call as the other backends,
  counted by `count_embeddings`; not A-MEM's sentence-transformers model.
- **Cost** (exploration): 30 calls for 16 writes, 16,799 prompt and
  2,840 completion tokens, about 1,050 prompt tokens a write, against
  Graphiti's 6,656 and Mem0's one extraction call.
- The kernel, the replicated agents and the native agents build their
  systems with the same function (Cerebrum `cerebrum/utils/amem.py`), as
  `cerebrum/utils/graphiti.py` serves Graphiti.

## Capabilities

`scored_search` true (above), `semantic_search` true, `internal_llm`
true, `native_sdk` true; `synchronous_commit` false, so the write
barrier waits for a write as for Mem0 and Graphiti (a write takes about
two LLM calls).

## Exploration (2026-11-12)

Eight writes of one user (profile, task and calendar statements, a chat
app stated and then changed), twice on fresh stores, with the pinned
LLM and embedder, metadata in `category`; then `search_agentic` and
`search`, and the delete of the first chat-app note. Both repositories
(agiresearch/A-mem `ceffb86`, WujiangXu/A-mem-sys `f303dfc`); the latter:
- **Calls**: one on the first write, two on every other.
- **Evolution**: every write after the first evolved and changed 1 to
  4 existing notes (24 changes over the 14 later writes), all among the
  five shown, in their tags (every change) and context (6 changes); the
  new note was linked to a shown note in 5 and 4 of the 7 later writes.
- **Metadata**: every note's `category` intact in both runs.
- **Search**: `search_agentic` and `search` gave the same five hits, in
  the same order (no linked note can survive the cut, "Search" above).
- **Repeatability**: the two runs differed in every generated attribute
  set, in which neighbours evolution changed, and in the search from its
  third hit on (the second run ranked the staging-server note third, and
  the rest moved down), at temperature 0 with a seed: the generated text
  enters the embedding.
- **Delete**: the deleted note's id stayed in other notes' `links` (2
  notes in the first run, 1 in the second); in neither run did another
  note's text carry "Slack".

**Live risk check** (`scripts/check_amem_risks.py`, 2026-11-12,
through the provider as the v2 writers write, two users, seven
statements, run twice in fresh stores): every row `list` and `search`
returned carried its write's metadata; a deleted note left `list` and
`search`; the forget deleted the slot's note and each carrier (one by a
value, one by an alias), the scrub found no note whose derived text
carried a form, and no note text, derived text or Chroma copy of the
user named the value after it. Writes took 3 to 5 s (two calls; the
first write of a store, one call, about 2 s), about 470 prompt tokens a
call; evolution changed 0 to 2 notes a write. The two runs differed in
the tags or context of 6 of the 7 notes and gave the same search order.

## Tests

- The contract tests run the provider with a scripted LLM (analysis and
  evolution replies) and the pinned Ollama embedder.
- Risk 1: after evolution rewrites neighbours, every note `search` and
  `list` return carries the metadata it was written with.
- Risk 2: `delete` removes the note from the dict and from Chroma; a
  forget deletes a note whose evolved context, whose tags alone (ASCII
  or not), or whose Chroma copy carries a form, and reports it
  (`derived`).
- A row carries no derived text; a failed write leaves no note (both
  found on review).
- The isolation: building a second user's store leaves the first's
  notes and vectors.
- The pin test, as for `graphiti-core`.
- `scripts/check_amem_risks.py`: the risks on Azure gpt-4o, live.

## Open risks, before code

1. **Metadata through evolution.** It rests on `category`, which A-MEM
   never writes after `add_note`; a later A-MEM that did would lose it.
   Tested on every search.
2. **Deletion completeness.** A value can live in other notes' evolved
   text and in stale Chroma copies; the forget deletes those notes,
   which can delete other facts with them. Measured by the forget
   reading.
3. **Nondeterminism.** Analysis and evolution are LLM output that varies
   between runs at temperature 0 with a seed, and it enters the
   embedding, so which notes a search returns varies too. The kernel and
   replicated loci write the same inputs into different stores; their
   paired outcomes can differ (as Mem0's and Graphiti's).
4. **Swallowed errors.** A-MEM catches its LLM's errors in analysis and
   evolution: a failed call leaves a note without generated attributes,
   or an evolution stopped part-way, and A-MEM says so only on stdout
   ("Error analyzing content", a print) or in an ERROR record ("Error in
   memory evolution", "Error in process_memory"). The extraction guard
   (a trial whose backend made no LLM call fails) catches only an LLM
   that never answered, so the runs count those lines in their logs and
   report them. `search`
   (`:462-481`) catches nothing, so a failed search raises in every
   locus and the kernel reports it (`retrieval_error`);
   `search_agentic`, which returns `[]` on any error, is not used.
5. **Chroma drift.** Evolution's changes to a neighbour never reach its
   Chroma document, so search ranks by the note as first written.
