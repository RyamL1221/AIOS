# NeurIPS 2027 Development Status

Branch: `feature/NeurIPS-2027-changes` in both repos, based on `main`.
Baseline tag: `workshop-postrun` (AIOS `44529a4`, Cerebrum `e7898fa`).
`feature/self-improving-memory` is a separate project: its docs,
`.kiro/steering` text on gating, `scripts/e2e_smoke.py` and subtask tags
do not describe this branch.

## Rules

1. Every fix or feature includes a test that fails without it.
2. Update this file at the end of each subtask.
3. Tag subtasks `neurips-subtask-NN`. The `subtask-NN` names are taken by
   the self-improving project.
4. After any edit to `../Cerebrum`, run
   `.venv/bin/python -m pip install ../Cerebrum --no-deps --force-reinstall`.
   The venv is shared across branches, so reinstall after switching too.
5. Never run the Cerebrum suite while a kernel listens on port 8000.

## Subtasks

| # | Subtask | Status |
|---|---------|--------|
| 1 | Single kernel retrieval path | Done |

### Subtask 1

`MemoryManager.retrieve_for_agent` now serves injection and SDK search.
Details, behavior changes and the before/after result are in
`docs/RETRIEVAL_PATH.md`. Smoke: `scripts/retrieval_smoke.py` against a
running kernel.

## Test baselines

These fail on `workshop-postrun` too and are not caused by later work.

- AIOS: `tests/modules/memory/test_memory.py` fails at collection, and 14
  tests in `test_mem0_provider.py` / `test_zep_provider.py` error (their
  `manager` argument is collected as a missing fixture).
- Cerebrum `tests/agents`: 20 failures, 2 errors.

## Known issues

1. `relevance_threshold` is inert on Mem0: `get_all` returns no scores,
   and it also does not rank, so query text does not affect selection.
2. Workshop provenance: the 1,800 trials span several code states and
   recorded no commit, config or injected sets. See the `mem0_default`
   note: gpt-4o ran before Cerebrum `6255bee`, llama and qwen after.
3. `config.yaml` (0.3 / 10 / 2000) and `config.yaml.example`
   (0.5 / 5 / 1500) still differ.
4. `Mem0Provider.add_memory` still writes `/tmp/per_user_proof.txt`.
5. `ConversationExtractor` writes directly to the provider, outside the
   write barrier.
6. `update_memory` and `remove_memory` by id have no visibility check.
7. `get_memory` on Mem0 only reads the default user's collection: it
   receives an id and no user, so a memory in a per-user collection is
   "not found" even for its owner.
8. `get_memory` on Zep always answers "not found": Zep episodes carry no
   owner, so the visibility rule fails closed.

## Fixed

- `get_memory` visibility: an agent reads a memory by id only if it owns
  it or it is shared. Anything else gets the same "Memory not found" as
  a missing id.
