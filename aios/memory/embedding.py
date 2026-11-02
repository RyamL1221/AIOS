"""
The pinned embedding model for memory providers.

``memory.embedding`` names one model; the Mem0 provider's embedder and
the Chroma in-house provider both read it here, so every backend embeds
with the same model and the same call. See docs/PROVIDER_CONTRACT.md.
"""
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

DEFAULTS = {
    "provider": "ollama",
    "model": "nomic-embed-text",
    "dimension": 768,
    "ollama_base_url": "http://localhost:11434",
}


@dataclass(frozen=True)
class EmbeddingConfig:
    """The ``memory.embedding`` block."""

    provider: str
    model: str
    dimension: int
    ollama_base_url: str

    @classmethod
    def from_memory_config(
        cls, memory_config: Dict[str, Any]
    ) -> "EmbeddingConfig":
        """Read ``memory.embedding``, filling unset keys with defaults."""
        block = {**DEFAULTS, **(memory_config.get("embedding") or {})}
        unknown = set(block) - set(DEFAULTS)
        if unknown:
            raise ValueError(
                f"memory.embedding: unknown keys {sorted(unknown)}"
            )
        if block["provider"] != "ollama":
            raise ValueError(
                "memory.embedding.provider: only 'ollama' is supported, "
                f"got {block['provider']!r}"
            )
        dimension = block["dimension"]
        if not isinstance(dimension, int) or dimension <= 0:
            raise ValueError(
                "memory.embedding.dimension must be a positive integer"
            )
        return cls(**block)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def mem0_embedder(self) -> Dict[str, Any]:
        """The same model as Mem0's ``embedder`` config."""
        return {
            "provider": self.provider,
            "config": {
                "model": self.model,
                "ollama_base_url": self.ollama_base_url,
                "embedding_dims": self.dimension,
            },
        }


class Embedder:
    """Embeds text with the pinned model, the way Mem0's Ollama
    embedder does (``Client.embed``), so both backends get the same
    vectors."""

    def __init__(self, config: EmbeddingConfig):
        from ollama import Client

        self.config = config
        self._client = Client(host=config.ollama_base_url)

    def embed(self, text: str) -> List[float]:
        """Return one vector; raises if its length is not the pinned
        dimension, which catches a model mismatch at the first write."""
        response = self._client.embed(model=self.config.model, input=text)
        embeddings = response.get("embeddings") or []
        if not embeddings:
            raise ValueError(
                f"embedding model {self.config.model!r} returned nothing"
            )
        vector = list(embeddings[0])
        if len(vector) != self.config.dimension:
            raise ValueError(
                f"embedding model {self.config.model!r} returned "
                f"{len(vector)} dimensions, memory.embedding.dimension "
                f"is {self.config.dimension}"
            )
        return vector
