"""
Test that retrieve_memory exposes a per-result similarity score.

Subtask 3 threads the vector-DB similarity through into every
``search_results`` entry so the future similarity-threshold policy can
read it. This is a payload-only change: ranking, ordering, top-k, and
the set of returned keys (other than the additive ``similarity``) must
be unchanged.

The test exercises the real ``InHouseProvider`` + ``ChromaRetriever``
against an in-memory ChromaDB collection (no external services). It
asserts:

1. Every returned entry carries a numeric ``similarity``.
2. Similarity values are in sane bounds for cosine (roughly [-1, 1],
   practically [0, 1] for these embeddings).
3. The most on-topic query returns its matching memory first with the
   highest similarity (ordering is consistent with ranking).
4. All pre-existing keys are still present (additive, not a rename).

Run standalone:

    python tests/modules/memory/test_similarity_score_exposed.py
"""
from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cerebrum.memory.apis import MemoryQuery

from aios.memory.note import MemoryNote
from aios.memory.providers.in_house import InHouseProvider

# Keys every search_results entry carried before this change. The test
# asserts they all survive (the change is purely additive).
_PRE_EXISTING_KEYS = {
    "content",
    "keywords",
    "tags",
    "category",
    "timestamp",
    "metadata",
}


class SimilarityScoreExposedTest(unittest.TestCase):
    """retrieve_memory search_results entries carry a similarity."""

    def setUp(self) -> None:
        self.provider = InHouseProvider()
        # Force the Chroma backend (default) regardless of env.
        self.provider.initialize({"vector_db_backend": "chroma"})

        # Populate a small, semantically distinct collection.
        self.docs = {
            "m_python": "The user prefers writing code in Python.",
            "m_coffee": "The user drinks black coffee every morning.",
            "m_travel": "The user is planning a trip to Japan next spring.",
        }
        for doc_id, content in self.docs.items():
            note = MemoryNote(content=content)
            note.id = doc_id
            resp = self.provider.add_memory(note)
            self.assertTrue(resp.success, resp.error)

    def _retrieve(self, content: str, k: int = 3):
        query = MemoryQuery(
            operation_type="retrieve_memory",
            params={"content": content, "k": k},
        )
        resp = self.provider.retrieve_memory(query)
        self.assertTrue(resp.success, resp.error)
        return resp.search_results

    def test_every_result_has_numeric_similarity(self) -> None:
        results = self._retrieve("What programming language do I like?")
        self.assertGreater(len(results), 0)

        for entry in results:
            self.assertIn("similarity", entry)
            sim = entry["similarity"]
            self.assertIsInstance(sim, float)
            # Default Chroma space is L2 -> similarity = 1/(1+d) in
            # (0, 1]. Cosine would be [-1, 1]. Accept the union so the
            # test is metric-agnostic; the key guarantee is a sane,
            # bounded value (no >1 blowups, no negative L2 artifacts).
            self.assertGreater(sim, -1.0001)
            self.assertLessEqual(sim, 1.0001)

    def test_existing_keys_preserved(self) -> None:
        results = self._retrieve("coffee", k=3)
        for entry in results:
            self.assertTrue(
                _PRE_EXISTING_KEYS.issubset(entry.keys()),
                f"missing pre-existing keys: "
                f"{_PRE_EXISTING_KEYS - set(entry.keys())}",
            )

    def test_ordering_consistent_with_ranking(self) -> None:
        # The Python query should rank the python memory first, and its
        # similarity should be the max in the returned set.
        results = self._retrieve(
            "Which coding language does the user prefer?", k=3
        )
        self.assertEqual(results[0]["content"], self.docs["m_python"])

        sims = [e["similarity"] for e in results]
        # Similarity is monotonically non-increasing with rank
        # (retrieval order == descending similarity for cosine).
        self.assertEqual(sims, sorted(sims, reverse=True))
        self.assertEqual(sims[0], max(sims))

    def test_count_matches_k(self) -> None:
        results = self._retrieve("anything", k=2)
        self.assertEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
