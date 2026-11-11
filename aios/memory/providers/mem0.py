"""
Mem0Provider - Memory provider using Mem0 for AI-native memory management.

Kernel mode stores in one Mem0 store per user. With ``memory.mem0.infer``
(Subtask 9) Mem0's own LLM, pinned to ``memory.backend_llm``, extracts
facts from each write as it does for the native agents; without it the
content is stored verbatim (``infer=False``). ``search`` scores through
Mem0's own vector store. Mem0's ``search()`` cannot be used for that:
its Chroma adapter returns the squared L2 distance as ``score``, and
``score_and_rank`` treats it as a similarity, clamps it at 1.0 and keeps
the top k. With no BM25 or entity boost (Chroma has no keyword search;
spaCy is not installed), every row at cosine 0.5 or below ties at 1.0
in Chroma's nearest-first order; the rows above 0.5, the relevant ones,
follow from the least similar up, so the top-k cut drops them whenever
k rows lie at 0.5 or below (docs/PROVIDER_CONTRACT.md, "Mem0").
"""
import copy
import hashlib
import logging
import os
import re
import threading
import time
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from cerebrum.utils.usage import count_embeddings, seed_mem0_llm

from .base import (
    Candidate,
    MemoryProvider,
    ProviderError,
    note_metadata,
    similarity_from_distance,
)

if TYPE_CHECKING:
    from aios.memory.note import MemoryNote

logger = logging.getLogger(__name__)


class Mem0Provider(MemoryProvider):
    """Provider using Mem0 for memory management.
    
    Mem0 provides AI-native memory management with features like:
    - Automatic memory extraction from conversations
    - Semantic search across memories
    - User and agent-scoped memory organization
    
    Attributes:
        client: Mem0 Memory client instance
        default_user_id: Default user ID for memory operations
        default_agent_id: Default agent ID for memory operations
    """
    
    def __init__(self):
        """Initialize the Mem0Provider with empty state.
        
        The actual Mem0 client is created during initialize() based on config.
        """
        self.client = None
        self.default_user_id = "default"
        self.default_agent_id = None

        # Per-user client cache: user_id -> Memory instance.
        # Each user gets a dedicated ChromaDB collection within
        # the shared PersistentClient directory, eliminating the
        # interleaving problem that caused dropped memories.
        self._user_clients: Dict[str, Any] = {}
        self._user_clients_lock = threading.RLock()
        # The LLM set by sync_llm_from_query, applied to every client.
        self._synced_llm = None
        self._default_collection_prefix = "mem0_memories"
        # Mem0 extracts facts from each write with its pinned LLM.
        self.backend_extraction = False

        # Shared ChromaDB PersistentClient (set during initialize).
        self._persistent_client = None
        self._chroma_path: Optional[str] = None

        # Base Mem0 config template (set during initialize).
        # Used to stamp out per-user Memory instances with only
        # the collection_name changed.
        self._base_mem0_config: Dict[str, Any] = {}
        # The store's own Mem0 history file (messages and history
        # records), set during initialize.
        self.history_db_path: Optional[str] = None
    
    def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize the provider with Mem0 configuration.
        
        Creates and configures the Mem0 Memory client with the provided
        settings for LLM, embedder, and vector store. Resolves API keys
        for cloud providers (OpenAI, Anthropic) from ConfigManager or
        environment variables.
        
        Args:
            config: Configuration dictionary containing:
                   - user_id: Default user ID (default: "default")
                   - agent_id: Default agent ID (optional)
                   - llm: LLM configuration dict
                   - embedder: Embedder configuration dict
                   - vector_store: Vector store configuration dict
                   - api_key: Mem0 cloud API key (optional, for cloud mode)
        
        Raises:
            ProviderInitializationError: If Mem0 client initialization fails.
        """
        try:
            from mem0 import Memory
        except ImportError as e:
            raise ImportError(
                "Mem0 library not installed. "
                "Install with: pip install mem0ai"
            ) from e
        
        try:
            # Extract default IDs from config
            self.default_user_id = config.get("user_id", "default")
            self.default_agent_id = config.get("agent_id")
            self.backend_extraction = bool(config.get("infer", False))
            # memory.backend_llm.seed, set on every client built here.
            self._llm_seed = config.get("llm_seed")
            
            # Build Mem0 configuration
            mem0_config = {}
            
            if config.get("llm"):
                mem0_config["llm"] = config["llm"]
            
            if config.get("embedder"):
                mem0_config["embedder"] = config["embedder"]
            
            if config.get("vector_store"):
                mem0_config["vector_store"] = config["vector_store"]

                # Inject default ChromaDB persistence path if missing
                # and ensure any relative path is resolved to absolute
                vs = mem0_config["vector_store"]
                if vs.get("provider") == "chroma":
                    vs_cfg = vs.setdefault("config", {})
                    if not vs_cfg.get("path"):
                        path = os.path.join(
                            os.getcwd(), ".mem0", "chroma"
                        )
                        vs_cfg["path"] = path
                    else:
                        path = vs_cfg["path"]
                    # Always resolve to absolute path
                    vs_cfg["path"] = os.path.abspath(path)
                    os.makedirs(vs_cfg["path"], exist_ok=True)
                    logger.info(
                        "ChromaDB persistence path: %s",
                        vs_cfg["path"],
                    )

                    # Create a shared PersistentClient to bypass
                    # Mem0's deprecated chromadb.Client(Settings(...))
                    # which is always in-memory in ChromaDB >= 0.4.
                    # This single client is reused across all per-user
                    # Memory instances (each gets its own collection
                    # within this persistent directory).
                    if not vs_cfg.get("client"):
                        import chromadb
                        from chromadb.config import (
                            Settings as ChromaSettings,
                        )
                        self._persistent_client = (
                            chromadb.PersistentClient(
                                path=vs_cfg["path"],
                                settings=ChromaSettings(
                                    anonymized_telemetry=False,
                                ),
                            )
                        )
                        vs_cfg["client"] = (
                            self._persistent_client
                        )
                        logger.info(
                            "Injected shared PersistentClient "
                            "for ChromaDB at %s",
                            vs_cfg["path"],
                        )
                    else:
                        # Config already provided a client;
                        # reuse it as the shared instance.
                        self._persistent_client = (
                            vs_cfg["client"]
                        )

                    # Store the chroma path for reference.
                    self._chroma_path = vs_cfg["path"]

                    # Extract collection prefix from config
                    # (falls back to default).
                    configured_name = vs_cfg.get(
                        "collection_name",
                        self._default_collection_prefix,
                    )
                    self._default_collection_prefix = (
                        configured_name
                    )

            # Each store keeps Mem0's messages and history records in a
            # file of its own, next to its vectors, not in the
            # ~/.mem0/history.db every run shared (known issue 46;
            # docs/DELETION_AND_SUPERSESSION.md, Decision 3). Every
            # per-user client is a copy of this config, so all get it.
            history_path = config.get("history_db_path")
            if not history_path and self._chroma_path:
                history_path = os.path.join(
                    os.path.dirname(self._chroma_path), "history.db"
                )
            if history_path:
                history_path = os.path.abspath(history_path)
                os.makedirs(os.path.dirname(history_path), exist_ok=True)
                mem0_config["history_db_path"] = history_path
                logger.info("Mem0 history path: %s", history_path)
            self.history_db_path = history_path

            # Resolve API keys for cloud LLM/embedder providers
            self._resolve_provider_api_keys(mem0_config)

            # Save base config as template for per-user clients.
            self._base_mem0_config = mem0_config

            # Initialize default Mem0 client (backward compat).
            if mem0_config:
                self.client = Memory.from_config(mem0_config)
            else:
                # Use default configuration
                self.client = Memory()
            self._count_embeddings(self.client)
            seed_mem0_llm(self.client, self._llm_seed)
                
        except Exception as e:
            from . import ProviderInitializationError
            raise ProviderInitializationError(
                "mem0",
                f"Failed to initialize Mem0 client: {str(e)}"
            )
    
    @staticmethod
    def _count_embeddings(client) -> None:
        """Count the tokens of the client's Ollama embedding calls per
        trial (``cerebrum.utils.usage``)."""
        embedder = getattr(client, "embedding_model", None)
        ollama = getattr(embedder, "client", None)
        if ollama is not None and hasattr(ollama, "embed"):
            count_embeddings(ollama, embedder.config.model)

    def _resolve_provider_api_keys(
        self, mem0_config: Dict[str, Any]
    ) -> None:
        """Resolve API keys for cloud providers and inject into config.
        
        For LLM providers "openai" and "anthropic", and embedder provider
        "openai", resolves the API key from ConfigManager or the
        corresponding environment variable and injects it into the
        Mem0 config dict.
        
        Args:
            mem0_config: The Mem0 configuration dict to modify in-place.
        """
        # Provider name -> (config key name, env var name)
        _KEY_MAP = {
            "openai": ("openai_api_key", "OPENAI_API_KEY"),
            "anthropic": ("anthropic_api_key", "ANTHROPIC_API_KEY"),
        }
        
        # Resolve LLM provider API key
        llm_cfg = mem0_config.get("llm", {})
        llm_provider = llm_cfg.get("provider", "")
        if llm_provider in _KEY_MAP:
            key = self._get_api_key(llm_provider)
            if key:
                cfg_key, env_var = _KEY_MAP[llm_provider]
                llm_cfg.setdefault("config", {})[cfg_key] = key
                logger.info(
                    "Resolved API key for LLM provider '%s'",
                    llm_provider,
                )
        
        # Resolve embedder provider API key
        embedder_cfg = mem0_config.get("embedder", {})
        embedder_provider = embedder_cfg.get("provider", "")
        if embedder_provider in _KEY_MAP:
            key = self._get_api_key(embedder_provider)
            if key:
                cfg_key, _ = _KEY_MAP[embedder_provider]
                embedder_cfg.setdefault("config", {})[cfg_key] = key
                logger.info(
                    "Resolved API key for embedder provider '%s'",
                    embedder_provider,
                )
    
    @staticmethod
    def _get_api_key(provider: str) -> str | None:
        """Retrieve API key from ConfigManager or environment variable.
        
        Args:
            provider: Provider name (e.g. "openai", "anthropic").
            
        Returns:
            The API key string, or None if not found.
        """
        try:
            from aios.config.config_manager import config as global_config
            key = global_config.get_api_key(provider)
            if key:
                return key
        except Exception:
            pass
        
        # Fallback: check environment variable directly
        env_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
        }
        env_var = env_map.get(provider)
        if env_var:
            return os.environ.get(env_var)
        return None

    # ------------------------------------------------------------------
    # Per-user collection helpers
    # ------------------------------------------------------------------

    def _resolve_op_user_id(
        self,
        params: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Resolve the target user_id for a memory operation.

        Priority:
        1. Explicit ``params["user_id"]``
        2. ``metadata["user_id"]``
        3. ``self.default_user_id`` (from config)
        4. Literal ``"default"``

        Returns:
            A non-empty string suitable for routing to a
            per-user collection.
        """
        params = params or {}
        metadata = metadata or {}

        user_id = (
            params.get("user_id")
            or metadata.get("user_id")
            or self.default_user_id
            or "default"
        )

        return str(user_id)

    def _sanitize_collection_component(
        self, value: str
    ) -> str:
        """Sanitize a string for use in a ChromaDB collection name.

        ChromaDB collection name rules:
        - 3–63 characters
        - Starts and ends with alphanumeric
        - Contains only alphanumeric, underscores, or hyphens
        - No consecutive periods (moot — we never produce them)
        """
        value = str(value or "default")

        # Replace invalid characters with underscore.
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", value)
        # Collapse consecutive underscores.
        sanitized = re.sub(r"_+", "_", sanitized)
        # Strip leading/trailing non-alphanumeric.
        sanitized = sanitized.strip("_-")

        if not sanitized:
            sanitized = "default"

        # Ensure starts with alphanumeric.
        if not sanitized[0].isalnum():
            sanitized = f"u{sanitized}"

        # Ensure ends with alphanumeric.
        if not sanitized[-1].isalnum():
            sanitized = f"{sanitized}u"

        return sanitized

    def _collection_name_for_user(self, user_id: str) -> str:
        """Build a valid per-user ChromaDB collection name.

        Format: ``{prefix}_{sanitized_user_id}``

        The result always satisfies ChromaDB naming constraints
        (3–63 chars, alphanumeric start/end, safe characters).
        """
        sanitized_user_id = (
            self._sanitize_collection_component(user_id)
        )
        prefix = self._sanitize_collection_component(
            self._default_collection_prefix
        )

        # Reserve room for the underscore separator.
        max_user_len = 63 - len(prefix) - 1
        if max_user_len < 3:
            prefix = "mem0"
            max_user_len = 63 - len(prefix) - 1

        if len(sanitized_user_id) > max_user_len:
            # Too long: keep a prefix and a hash of the full id, so two
            # ids sharing a long prefix never share a collection (known
            # issue 31). Ids that fit keep their name unchanged.
            digest = hashlib.sha256(
                str(user_id).encode("utf-8")
            ).hexdigest()[:10]
            keep = max_user_len - len(digest) - 1
            head = sanitized_user_id[:keep].strip("_-") if keep > 0 else ""
            sanitized_user_id = (
                f"{head}_{digest}" if head else digest[:max_user_len]
            )

        if not sanitized_user_id:
            sanitized_user_id = "default"

        # Ensure truncated value still ends with alnum.
        if not sanitized_user_id[-1].isalnum():
            sanitized_user_id = f"{sanitized_user_id}u"

        collection_name = f"{prefix}_{sanitized_user_id}"

        if len(collection_name) < 3:
            collection_name = "mem0_default"

        # Final safety: truncate and strip trailing non-alnum.
        collection_name = collection_name[:63].rstrip("_-")
        if not collection_name[-1].isalnum():
            collection_name = f"{collection_name}u"

        return collection_name

    def _get_client_for_user(self, user_id: str):
        """Return a cached per-user Mem0 Memory client, creating
        one lazily if needed.

        Each user_id maps to a dedicated ChromaDB collection
        (named via ``_collection_name_for_user``). All collections
        share the same underlying ``PersistentClient`` directory.

        Thread-safe: uses ``_user_clients_lock`` to guard the
        cache dict.

        Args:
            user_id: The resolved user identity. Blank/None is
                normalized to the configured default.

        Returns:
            A ``mem0.Memory`` instance scoped to the user's
            collection.
        """
        from mem0 import Memory

        # Normalize blank to default.
        user_id = self._resolve_op_user_id(
            params={"user_id": user_id}
        )

        with self._user_clients_lock:
            # Fast path: return cached client.
            cached = self._user_clients.get(user_id)
            if cached is not None:
                return cached

            # Lazy-initialize if needed.
            if (
                self._persistent_client is None
                or not self._base_mem0_config
            ):
                self.initialize()

            # Defensive: if initialize() still didn't set up
            # the shared state, we cannot proceed.
            if (
                self._persistent_client is None
                or not self._base_mem0_config
            ):
                raise RuntimeError(
                    "Mem0Provider could not initialize "
                    "per-user client state"
                )

            # Build per-user config from template.
            collection_name = (
                self._collection_name_for_user(user_id)
            )

            # Remove the unpicklable PersistentClient from the base
            # config before deepcopy, then restore it. deepcopy uses
            # pickle internally and ChromaDB's native Bindings objects
            # cannot be serialized.
            base_vs_config = (
                self._base_mem0_config
                .get("vector_store", {})
                .get("config", {})
            )
            saved_client = base_vs_config.pop("client", None)
            try:
                user_config = copy.deepcopy(
                    self._base_mem0_config
                )
            finally:
                # Always restore the client reference on the base config.
                if saved_client is not None:
                    base_vs_config["client"] = saved_client

            vector_store = user_config.setdefault(
                "vector_store", {}
            )
            vector_store_config = vector_store.setdefault(
                "config", {}
            )
            vector_store_config["collection_name"] = (
                collection_name
            )
            vector_store_config["client"] = (
                self._persistent_client
            )

            # Create the per-user Memory instance.
            client = Memory.from_config(user_config)
            self._count_embeddings(client)
            seed_mem0_llm(client, getattr(self, "_llm_seed", None))
            if self._synced_llm is not None:
                client.llm = self._synced_llm

            # Cache it.
            self._user_clients[user_id] = client

            print(
                f"[PER_USER] Created client for "
                f"user_id={user_id}, "
                f"collection={collection_name}",
                flush=True,
            )
            logger.info(
                "Created Mem0 client for user_id=%s "
                "collection=%s",
                user_id,
                collection_name,
            )

            return client

    # ------------------------------------------------------------------
    # Dynamic LLM synchronization
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_filter_metadata(item: dict) -> dict:
        """Build one metadata dict from a Mem0 result item.

        Mem0 promotes some payload keys (``user_id``, ``agent_id``, ...)
        and ``created_at`` to the item's top level and leaves them out of
        ``item["metadata"]``; the kernel reads them from the metadata, so
        they are merged back in.
        """
        meta = dict(item.get("metadata") or {})
        for key in ("user_id", "agent_id", "created_at"):
            if key not in meta and key in item:
                meta[key] = item[key]
        return meta

    # Kernel backends LiteLLM serves under the same ``<backend>/<model>``
    # name the kernel's own adapter uses.
    _LITELLM_BACKENDS = frozenset({
        "openai", "azure", "anthropic", "gemini", "ollama", "groq",
        "deepseek",
    })

    def sync_llm_from_query(
        self,
        llms: "list[dict] | None",
    ) -> None:
        """Synchronize the Mem0 client's LLM with the agent's
        runtime model selection.

        Mem0's LLM is its ``litellm`` provider with the model the kernel
        itself calls (``<backend>/<model>``), so its calls reach LiteLLM's
        callbacks and their tokens are counted per trial
        (``cerebrum.utils.usage``). LiteLLM reads the provider's
        credentials (``AZURE_API_*`` and so on) from the environment, as
        it does for the kernel's calls. With ``memory.mem0.infer`` on
        (the benchmarks' setting) the LLM is pinned to
        ``memory.backend_llm`` and this returns at once; with it off,
        Mem0 stores the content verbatim and never calls this LLM.

        Idempotent: if the requested model is already active, it returns
        without rebuilding the LLM.

        Args:
            llms: The ``LLMQuery.llms`` field — a list of dicts
                each containing at minimum ``name`` (model name)
                and optionally ``backend`` (AIOS backend
                identifier). ``None`` or empty list is a no-op.
        """
        if not llms or not self.client:
            return
        if self.backend_extraction:
            return  # the LLM is pinned to memory.backend_llm

        # Use the first entry in the list (primary model).
        primary = llms[0]
        model_name = primary.get("name")
        backend = primary.get("backend", "")

        if not model_name:
            return
        if backend not in self._LITELLM_BACKENDS:
            logger.debug(
                "No LiteLLM route for AIOS backend '%s'; skipping "
                "Mem0 LLM sync.",
                backend,
            )
            return
        litellm_model = f"{backend}/{model_name}"

        # Idempotency check: skip if already using this model.
        current_llm = getattr(self.client, "llm", None)
        current_model = getattr(
            getattr(current_llm, "config", None), "model", None
        )
        if current_model == litellm_model:
            return

        try:
            from mem0.utils.factory import LlmFactory

            new_llm = LlmFactory.create(
                "litellm", {"model": litellm_model}
            )
            # Writes go through the per-user clients, so they take the
            # synced LLM too, and so does every client created later.
            with self._user_clients_lock:
                self._synced_llm = new_llm
                self.client.llm = new_llm
                for client in self._user_clients.values():
                    client.llm = new_llm
            logger.info("Mem0 LLM synced to litellm/%s", litellm_model)
        except Exception as e:
            logger.warning(
                "Failed to sync Mem0 LLM to litellm/%s: %s",
                litellm_model,
                e,
            )
    
    # ------------------------------------------------------------------
    # Searchability polling helpers
    # ------------------------------------------------------------------

    def _normalize_get_all_result(self, result: object) -> list:
        """Normalize Mem0 get_all() responses into a list of memory dicts.

        Mem0 may return either:
        - a plain list
        - a dict with a results/memories/data field
        """
        if isinstance(result, list):
            return result

        if isinstance(result, dict):
            for key in ("results", "memories", "data"):
                value = result.get(key)
                if isinstance(value, list):
                    return value

        return []

    def _extract_memory_ids(self, result: object) -> List[str]:
        """Every memory id in a Mem0 ``add()`` response, in order (one
        per stored fact with extraction); the single-id shapes of
        ``_extract_memory_id`` otherwise."""
        items = result.get("results") if isinstance(result, dict) else None
        if isinstance(items, list):
            ids = [
                str(item.get("id") or item.get("memory_id"))
                for item in items
                if isinstance(item, dict)
                and (item.get("id") or item.get("memory_id"))
            ]
            return ids
        single = self._extract_memory_id(result)
        return [single] if single else []

    def _extract_memory_id(
        self, result: object
    ) -> Optional[str]:
        """Extract a memory ID from Mem0 add() responses.

        Mem0 response shapes can vary by version/configuration.
        Supported shapes:
        - {"id": "abc123"}
        - {"memory_id": "abc123"}
        - {"results": [{"id": "abc123"}]}
        - {"results": [{"memory_id": "abc123"}]}
        - [{"id": "abc123"}]
        - [{"memory_id": "abc123"}]
        """
        if isinstance(result, dict):
            for key in ("id", "memory_id"):
                value = result.get(key)
                if value:
                    return str(value)

            for list_key in ("results", "memories", "data"):
                value = result.get(list_key)
                if isinstance(value, list):
                    extracted = self._extract_memory_id(value)
                    if extracted:
                        return extracted

        if isinstance(result, list):
            for item in result:
                extracted = self._extract_memory_id(item)
                if extracted:
                    return extracted

        return None

    # ------------------------------------------------------------------
    # The provider contract
    # ------------------------------------------------------------------

    # Payload keys that are Mem0's own bookkeeping, not memory metadata.
    _PAYLOAD_INTERNAL = {"data", "hash", "text_lemmatized", "updated_at"}

    def capabilities(self) -> Dict[str, bool]:
        return {
            "scored_search": True,
            "semantic_search": True,
            "internal_llm": True,
            "native_sdk": True,
        }

    def _scope(self, user_id: Optional[str]) -> str:
        return self._resolve_op_user_id(params={"user_id": user_id})

    def _candidate(self, item: dict) -> Candidate:
        """A Candidate from a Mem0 result item (``get`` / ``get_all``)."""
        return Candidate(
            memory_id=str(item.get("id")),
            content=item.get("memory", "") or "",
            metadata=self._extract_filter_metadata(item),
        )

    def _await_stored(self, client, memory_id: str,
                      max_wait: float = 10.0,
                      interval: float = 0.1) -> None:
        """Wait until a new memory can be read back by id, so a
        retrieval released by the write barrier sees it."""
        waited = 0.0
        while waited < max_wait:
            if client.vector_store.get(vector_id=memory_id) is not None:
                return
            time.sleep(interval)
            waited += interval
        logger.warning(
            "add: memory %s not readable after %.1fs", memory_id, max_wait
        )

    def add(self, memory_note: "MemoryNote") -> str:
        """Store one note and return a memory id. With extraction, Mem0
        may store several facts (each with the full metadata) or none;
        the first fact's id is returned, ``""`` for none."""
        metadata = note_metadata(memory_note)
        user_id = self._scope(metadata.get("user_id"))
        kwargs: Dict[str, Any] = {
            "user_id": user_id,
            "metadata": metadata,
            "infer": self.backend_extraction,
        }
        content: Any = memory_note.content
        if self.backend_extraction:
            # As the native agents call it: the writer as the agent, and
            # a conversation turn as role-tagged messages.
            kwargs["agent_id"] = metadata.get("owner_agent")
            content = self._messages(content, metadata)
        elif self.default_agent_id:
            kwargs["agent_id"] = self.default_agent_id
        client = self._get_client_for_user(user_id)
        try:
            result = client.add(content, **kwargs)
        except Exception as e:
            raise ProviderError(f"Mem0 add failed: {e}") from e
        memory_ids = self._extract_memory_ids(result)
        if not memory_ids:
            if self.backend_extraction:
                logger.info("add: Mem0 extracted no facts for %s", user_id)
                return ""
            raise ProviderError("Mem0 add returned no memory id")
        for memory_id in memory_ids:
            self._await_stored(client, memory_id)
        return memory_ids[0]

    _TURN = re.compile(
        r"\AUser: (?P<user>.*?)\nAssistant: (?P<assistant>.*)\Z",
        re.DOTALL,
    )

    @classmethod
    def _messages(cls, content: str, metadata: Dict[str, Any]) -> Any:
        """A conversation memory's ``User: ...\\nAssistant: ...`` text as
        the two messages Mem0's extraction expects; other content as
        is (Mem0 makes it one user message)."""
        if metadata.get("memory_type") == "conversation":
            match = cls._TURN.match(content or "")
            if match:
                return [
                    {"role": "user", "content": match["user"]},
                    {"role": "assistant", "content": match["assistant"]},
                ]
        return content

    def search(
        self, query_text: str, user_id: Optional[str], top_k: int
    ) -> List[Candidate]:
        """Nearest memories by the pinned embedding, scored with the
        similarity from the raw Chroma distance (not Mem0's ``search()``
        score; see the module docstring)."""
        user_id = self._scope(user_id)
        client = self._get_client_for_user(user_id)
        store = client.vector_store
        count = store.collection.count()
        if count == 0 or top_k <= 0:
            return []
        space = (store.collection.metadata or {}).get("hnsw:space", "l2")
        vector = client.embedding_model.embed(query_text, "search")
        hits = store.search(
            query=query_text,
            vectors=vector,
            top_k=min(top_k, count),
            filters={"user_id": user_id},
        )
        rows = []
        for hit in hits:
            payload = dict(hit.payload or {})
            content = payload.get("data", "")
            metadata = {
                key: value for key, value in payload.items()
                if key not in self._PAYLOAD_INTERNAL
            }
            rows.append(Candidate(
                memory_id=str(hit.id),
                content=content,
                metadata=metadata,
                score=similarity_from_distance(hit.score, space),
            ))
        return rows

    def list(self, user_id: Optional[str], top_k: int) -> List[Candidate]:
        user_id = self._scope(user_id)
        if top_k <= 0:
            return []
        result = self._get_client_for_user(user_id).get_all(
            filters={"user_id": user_id}, top_k=top_k
        )
        return [
            self._candidate(item)
            for item in self._normalize_get_all_result(result)
            if isinstance(item, dict)
        ]

    def get(
        self, memory_id: str, user_id: Optional[str]
    ) -> Optional[Candidate]:
        """The row, or None when the scope holds no row with this id.
        Mem0's Chroma adapter signals a missing id with IndexError; any
        other error is a failed read and raises ``ProviderError``, so a
        delete or an update never takes a read error for a missing row
        (a forget would file it under ``not_found`` and succeed)."""
        client = self._get_client_for_user(self._scope(user_id))
        try:
            item = client.get(memory_id)
        except IndexError:
            return None
        except Exception as e:
            raise ProviderError(f"Mem0 get failed: {e}") from e
        return self._candidate(item) if isinstance(item, dict) else None

    def update(
        self,
        memory_id: str,
        user_id: Optional[str],
        content: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> bool:
        current = self.get(memory_id, user_id)
        if current is None:
            return False
        merged = {**current.metadata, **(metadata or {})}
        merged.pop("created_at", None)  # Mem0 keeps the original
        client = self._get_client_for_user(self._scope(user_id))
        try:
            client.update(
                memory_id,
                current.content if content is None else content,
                metadata=merged,
            )
        except Exception as e:
            raise ProviderError(f"Mem0 update failed: {e}") from e
        return True

    def update_metadata(
        self,
        memory_id: str,
        user_id: Optional[str],
        metadata: Dict[str, Any],
    ) -> bool:
        """Write ``metadata`` into the row's stored payload alone: the
        text, its hash and its embedding stay, and Mem0's ``update``
        (which re-embeds the text and records a history UPDATE) is not
        called. The full payload is written back, so the result is the
        same whether Chroma merges or replaces a record's metadata."""
        store = self._get_client_for_user(self._scope(user_id)).vector_store
        try:
            found = store.get(vector_id=memory_id)
        except IndexError:
            return False  # Mem0's Chroma adapter: no row with this id
        except Exception as e:
            raise ProviderError(f"Mem0 metadata read failed: {e}") from e
        if found is None:
            return False
        payload = {**(found.payload or {}), **(metadata or {})}
        try:
            store.update(vector_id=memory_id, vector=None, payload=payload)
        except Exception as e:
            raise ProviderError(f"Mem0 metadata update failed: {e}") from e
        return True

    # Rows per SQLite ``IN (...)`` list, under SQLite's variable limit.
    _SCRUB_CHUNK = 500

    @staticmethod
    def _scope_is_user(session_scope: Optional[str], user_id: str) -> bool:
        """Whether a Mem0 message scope belongs to ``user_id``. Mem0
        builds it from the sorted ``agent_id``, ``run_id`` and
        ``user_id`` entries joined by ``&``, so ``user_id`` comes last.
        Compared exactly, never with SQL ``LIKE``: v2 ids contain
        ``_``, which ``LIKE`` reads as a wildcard."""
        scope = session_scope or ""
        entry = f"user_id={user_id}"
        return scope == entry or scope.endswith("&" + entry)

    def scrub_history(
        self,
        user_id: Optional[str],
        forms: List[str],
        deleted_ids: List[str] = (),
        kept_ids: List[str] = (),
    ) -> Dict[str, int]:
        """Remove forgotten forms from the store's Mem0 history file
        (docs/DELETION_AND_SUPERSESSION.md, Decision 3).

        - ``messages``: every message in one of the user's scopes, of
          any agent, whose content carries a form is deleted whole.
          Mem0 reads a scope's last 10 messages into each extraction,
          verbatim, and a redaction cannot be mapped back through the
          matcher's normalization.
        - ``history``: the text (``old_memory``, ``new_memory``) of
          every record of a deleted row is cleared, and of any record of
          the user's other rows (``kept_ids``) where it carries a form.
          The records themselves stay.

        Run after the deletes: Mem0's ``delete`` records the deleted
        text. Returns how many messages were deleted and how many
        history records were cleared.
        """
        from aios.memory.pipeline.matching import match_forms

        counts = {"messages": 0, "history": 0}
        # The store's own file; without one (a vector store other than
        # Chroma and no history_db_path) the file Mem0's clients use.
        path = self.history_db_path or getattr(
            getattr(self.client, "db", None), "db_path", None
        )
        forms = [form for form in forms if form]
        if not path or not os.path.exists(path):
            return counts
        import sqlite3

        scope_user = self._scope(user_id)
        deleted = {str(i) for i in deleted_ids}
        ids = sorted(deleted | {str(i) for i in kept_ids})
        connection = sqlite3.connect(path, timeout=30)
        try:
            with connection:
                messages = connection.execute(
                    "SELECT id, session_scope, content FROM messages"
                ).fetchall()
                doomed = [
                    (message_id,)
                    for message_id, scope, content in messages
                    if forms and self._scope_is_user(scope, scope_user)
                    and match_forms(content, forms)
                ]
                connection.executemany(
                    "DELETE FROM messages WHERE id = ?", doomed
                )
                counts["messages"] = len(doomed)
                for start in range(0, len(ids), self._SCRUB_CHUNK):
                    chunk = ids[start:start + self._SCRUB_CHUNK]
                    records = connection.execute(
                        "SELECT id, memory_id, old_memory, new_memory "
                        "FROM history WHERE memory_id IN ("
                        + ",".join("?" * len(chunk)) + ")",
                        chunk,
                    ).fetchall()
                    for record_id, memory_id, old, new in records:
                        gone = memory_id in deleted
                        clear_old = old is not None and (
                            gone or bool(match_forms(old, forms))
                        )
                        clear_new = new is not None and (
                            gone or bool(match_forms(new, forms))
                        )
                        if not (clear_old or clear_new):
                            continue
                        connection.execute(
                            "UPDATE history SET "
                            "old_memory = CASE WHEN ? THEN NULL "
                            "ELSE old_memory END, "
                            "new_memory = CASE WHEN ? THEN NULL "
                            "ELSE new_memory END WHERE id = ?",
                            (int(clear_old), int(clear_new), record_id),
                        )
                        counts["history"] += 1
        finally:
            connection.close()
        return counts

    def delete(self, memory_id: str, user_id: Optional[str]) -> bool:
        if self.get(memory_id, user_id) is None:
            return False
        try:
            self._get_client_for_user(self._scope(user_id)).delete(memory_id)
        except Exception as e:
            raise ProviderError(f"Mem0 delete failed: {e}") from e
        return True

    def close(self) -> None:
        self.client = None
