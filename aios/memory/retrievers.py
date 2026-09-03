from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import chromadb
from chromadb.config import Settings
from nltk.tokenize import word_tokenize
import os
from qdrant_client import QdrantClient, models as qmodels
from aios.config.config_manager import config as global_config
import uuid

def simple_tokenize(text):
    return word_tokenize(text)

class SimpleEmbeddingRetriever:
    """Simple retriever using sentence embeddings"""
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        self.model = SentenceTransformer(model_name)
        self.documents = []
        self.embeddings = None

    def add_document(self, document: str):
        """Add a document to the retriever.

        Args:
            document: Text content to add
        """
        self.documents.append(document)
        # Update embeddings
        if len(self.documents) == 1:
            self.embeddings = self.model.encode([document])
        else:
            new_embedding = self.model.encode([document])
            self.embeddings = np.vstack([self.embeddings, new_embedding])

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search for similar documents.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of dictionaries containing document content and similarity score
        """
        if not self.documents:
            return []

        # Get query embedding
        query_embedding = self.model.encode([query])

        # Calculate cosine similarities
        similarities = cosine_similarity(query_embedding, self.embeddings)[0]

        # Get top k results
        top_indices = np.argsort(similarities)[-top_k:][::-1]

        results = []
        for idx in top_indices:
            results.append({
                'content': self.documents[idx],
                'score': float(similarities[idx])
            })

        return results

def distance_to_similarity(distance: float, space: str = "l2") -> float:
    """Convert a raw vector-DB distance to a bounded similarity.

    The conversion is metric-aware so the resulting similarity is
    monotonically decreasing in distance (ranking-preserving) and
    stays in sane bounds for the configured space:

    - ``cosine``: Chroma cosine distance in [0, 2]; similarity =
      ``1 - distance`` in [-1, 1].
    - ``ip`` (inner product): Chroma returns a negated inner product;
      similarity = ``-distance``.
    - ``l2`` (squared euclidean, Chroma's default): distance in
      [0, inf); similarity = ``1 / (1 + distance)`` in (0, 1].

    Args:
        distance: Raw distance from the vector DB.
        space: The collection's distance metric ("l2", "cosine", "ip").

    Returns:
        A float similarity. Higher means more similar.
    """
    d = float(distance)
    space = (space or "l2").lower()
    if space == "cosine":
        return 1.0 - d
    if space == "ip":
        return -d
    # Default / "l2": monotonic decreasing, bounded (0, 1].
    return 1.0 / (1.0 + d)


class ChromaRetriever:
    """Vector database retrieval using ChromaDB"""
    def __init__(self, collection_name: str = "memories"):
        """Initialize ChromaDB retriever.

        Args:
            collection_name: Name of the ChromaDB collection
        """
        self.client = chromadb.Client(Settings(allow_reset=True))
        self.collection = self.client.get_or_create_collection(name=collection_name)

    @property
    def space(self) -> str:
        """The collection's configured distance metric.

        Chroma defaults to ``l2`` when no ``hnsw:space`` is set. Read
        defensively across Chroma versions; falls back to ``l2``.
        """
        try:
            cfg = self.collection._model.configuration_json
            return cfg.get("hnsw", {}).get("space", "l2")
        except Exception:
            meta = getattr(self.collection, "metadata", None) or {}
            return meta.get("hnsw:space", "l2")

    def add_document(self, document: str, metadata: Dict, doc_id: str):
        """Add a document to ChromaDB.

        Args:
            document: Text content to add
            metadata: Dictionary of metadata
            doc_id: Unique identifier for the document
        """
        # Convert lists to strings in metadata to comply with ChromaDB requirements
        processed_metadata = {}
        for key, value in metadata.items():
            if isinstance(value, list):
                processed_metadata[key] = ", ".join(value)
            else:
                processed_metadata[key] = value

        self.collection.add(
            documents=[document],
            metadatas=[processed_metadata],
            ids=[doc_id]
        )

    def delete_document(self, doc_id: str):
        """Delete a document from ChromaDB.

        Args:
            doc_id: ID of document to delete
        """
        self.collection.delete(ids=[doc_id])

    def search(self, query: str, k: int = 5):
        """Search for similar documents.

        Args:
            query: Query text
            k: Number of results to return

        Returns:
            Chroma query result dict. Includes ``ids``, ``metadatas``,
            ``documents`` and ``distances``. ``distances`` are the raw
            distances from the collection's configured metric (cosine
            by default); callers convert to a similarity as
            ``similarity = 1 - distance``. ``distances`` is requested
            explicitly so it is always present regardless of Chroma
            version defaults.
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=k,
            include=["metadatas", "documents", "distances"],
        )

        # Convert string metadata back to lists where appropriate
        if 'metadatas' in results and results['metadatas']:
            for metadata in results['metadatas']:
                for key in ['keywords', 'tags']:
                    if key in metadata and isinstance(metadata[key], str):
                        metadata[key] = [item.strip() for item in metadata[key].split(',')]

        return results


class QdrantRetriever:
    """Vector database retrieval using Qdrant"""
    def __init__(self, collection_name: str = "memories", model_name: Optional[str] = None):
        """Initialize Qdrant retriever.

        Args:
            collection_name: Name of the Qdrant collection
            model_name: SentenceTransformer model for embeddings
        """
        storage_cfg = global_config.get_storage_config() or {}
        host = storage_cfg.get("qdrant_host", os.environ.get("QDRANT_HOST", "localhost"))
        port = int(storage_cfg.get("qdrant_port", os.environ.get("QDRANT_PORT", 6333)))
        api_key = storage_cfg.get("qdrant_api_key", os.environ.get("QDRANT_API_KEY"))

        self.client = QdrantClient(host=host, port=port, api_key=api_key or None)
        # Qdrant collections here are created with Distance.COSINE, and
        # ``search`` maps score->distance as ``1 - score``; report the
        # cosine space so ``distance_to_similarity`` inverts it back to
        # the original cosine similarity.
        self.space = "cosine"
        self.collection_name = collection_name or "memories"
        self.model_name = model_name or storage_cfg.get("qdrant_model_name") or os.environ.get("QDRANT_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

        if self.collection_name and not self.client.collection_exists(self.collection_name):
            vector_size = self.client.get_embedding_size(self.model_name)
            self.client.create_collection(
                self.collection_name,
                vectors_config=qmodels.VectorParams(
                    size=vector_size,
                    distance=qmodels.Distance.COSINE,
                ),
            )

    def add_document(self, document: str, metadata: Dict, doc_id: str):
        """Add a document to Qdrant.

        Args:
            document: Text content to add
            metadata: Dictionary of metadata
            doc_id: Unique identifier for the document
        """
        processed_metadata = {}
        for key, value in (metadata or {}).items():
            if isinstance(value, list):
                processed_metadata[key] = ", ".join(value)
            else:
                processed_metadata[key] = value

        qdrant_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(doc_id)))
        processed_metadata["original_id"] = str(doc_id)

        self.client.upload_collection(
            collection_name=self.collection_name,
            vectors=[qmodels.Document(text=document, model=self.model_name)],
            ids=[qdrant_id],
            payload=[processed_metadata],
        )

    def delete_document(self, doc_id: str):
        qdrant_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(doc_id)))
        """Delete a document from Qdrant."""
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=[qdrant_id],
        )

    def search(self, query: str, k: int = 5):
        """Search for similar documents.

        Returns a dict structurally similar to Chroma's response for compatibility
        with existing code paths in memory manager.
        """
        results = self.client.query_points(
            collection_name=self.collection_name,
            query=qmodels.Document(text=query, model=self.model_name),
            limit=k,
        ).points

        ids = [[(r.payload or {}).get("original_id", str(r.id)) for r in results]]
        metadatas = [[(r.payload or {}) for r in results]]
        documents = [[""] * len(results)]
        # Qdrant returns a cosine *similarity* in ``r.score`` (the
        # collection is created with Distance.COSINE). Expose it as a
        # ``distances`` list shaped like Chroma's so the shared
        # ``_build_similarity_map`` (similarity = 1 - distance) recovers
        # the original similarity. Additive: existing keys unchanged.
        distances = [[1.0 - float(r.score) for r in results]]

        return {
            "ids": ids,
            "metadatas": metadatas,
            "documents": documents,
            "distances": distances,
        }
