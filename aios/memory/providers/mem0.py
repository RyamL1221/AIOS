"""
Mem0Provider - Memory provider using Mem0 for AI-native memory management.

Kernel mode stores content verbatim (``infer=False``) in one Mem0 store
per user. ``search`` scores through Mem0's own vector store: Mem0's
``search()`` cannot be used for that, because its Chroma adapter returns
the raw L2 distance as ``score`` and ``score_and_rank`` treats it as a
similarity, so results come back least similar first, clamped at 1.0
(docs/PROVIDER_CONTRACT.md, "Mem0").
"""
import copy
import logging
import os
import re
import threading
import time
from typing import Dict, Any, List, Optional, TYPE_CHECKING

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

        # Shared ChromaDB PersistentClient (set during initialize).
        self._persistent_client = None
        self._chroma_path: Optional[str] = None

        # Base Mem0 config template (set during initialize).
        # Used to stamp out per-user Memory instances with only
        # the collection_name changed.
        self._base_mem0_config: Dict[str, Any] = {}
    
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
                
        except Exception as e:
            from . import ProviderInitializationError
            raise ProviderInitializationError(
                "mem0",
                f"Failed to initialize Mem0 client: {str(e)}"
            )
    
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

        sanitized_user_id = (
            sanitized_user_id[:max_user_len].strip("_-")
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

    # Mapping from AIOS kernel backend names to Mem0 LLM provider names.
    _BACKEND_TO_MEM0_PROVIDER: Dict[str, str] = {
        "openai": "openai",
        "azure": "azure_openai",
        "azure_openai": "azure_openai",
        "anthropic": "anthropic",
        "gemini": "gemini",
        "ollama": "ollama",
        "groq": "groq",
        "deepseek": "deepseek",
        "vllm": "vllm",
        "litellm": "litellm",
    }

    @staticmethod
    def _azure_kwargs(deployment: str) -> Dict[str, Any]:
        """Return Mem0's Azure client settings from the variables the
        kernel's LiteLLM calls use (``AZURE_API_KEY``,
        ``AZURE_API_BASE``, ``AZURE_API_VERSION``). The deployment is the
        model name, as in LiteLLM's ``azure/<deployment>``. Unset
        variables are left out, so Mem0 falls back to its own
        ``LLM_AZURE_*`` variables."""
        settings = {
            "api_key": os.environ.get("AZURE_API_KEY"),
            "azure_endpoint": os.environ.get("AZURE_API_BASE"),
            "api_version": os.environ.get("AZURE_API_VERSION"),
            "azure_deployment": deployment,
        }
        return {k: v for k, v in settings.items() if v}

    def sync_llm_from_query(
        self,
        llms: "list[dict] | None",
    ) -> None:
        """Synchronize the Mem0 client's LLM with the agent's
        runtime model selection.

        This allows the kernel to propagate the agent's chosen
        LLM (specified in ``LLMQuery.llms``) to the Mem0
        provider so that Mem0's internal fact extraction uses the
        same model as the assistant agent — without requiring a
        static ``mem0.llm`` entry in ``config.yaml``.

        The method is idempotent: if the requested model is
        already active, it short-circuits without reconstructing
        the LLM object.

        Args:
            llms: The ``LLMQuery.llms`` field — a list of dicts
                each containing at minimum ``name`` (model name)
                and optionally ``backend`` (AIOS backend
                identifier). ``None`` or empty list is a no-op.
        """
        if not llms or not self.client:
            return

        # Use the first entry in the list (primary model).
        primary = llms[0]
        model_name = primary.get("name")
        backend = primary.get("backend", "")

        if not model_name:
            return

        # Map AIOS backend → Mem0 provider name.
        mem0_provider = self._BACKEND_TO_MEM0_PROVIDER.get(
            backend, ""
        )
        if not mem0_provider:
            # Unknown backend — cannot map, leave Mem0 LLM as-is.
            logger.debug(
                "Cannot map AIOS backend '%s' to a Mem0 LLM "
                "provider; skipping sync.",
                backend,
            )
            return

        # Idempotency check: skip if already using this model.
        current_llm = getattr(self.client, "llm", None)
        if current_llm is not None:
            current_model = getattr(
                current_llm, "model", None
            ) or getattr(
                getattr(current_llm, "config", None),
                "model",
                None,
            )
            if current_model == model_name:
                return

        # Build new Mem0 LLM config and create the instance.
        try:
            from mem0.utils.factory import LlmFactory

            llm_config: Dict[str, Any] = {"model": model_name}

            if mem0_provider == "azure_openai":
                llm_config["azure_kwargs"] = self._azure_kwargs(
                    model_name
                )
            else:
                api_key = self._get_api_key(mem0_provider)
                if api_key:
                    llm_config["api_key"] = api_key

            # For Ollama, include the hostname from kernel config.
            if mem0_provider == "ollama":
                from aios.config.config_manager import (
                    config as global_config,
                )
                llms_cfg = global_config.get_llms_config() or {}
                for m in llms_cfg.get("models", []):
                    if (
                        m.get("backend") == "ollama"
                        and m.get("hostname")
                    ):
                        llm_config[
                            "ollama_base_url"
                        ] = m["hostname"]
                        break

            new_llm = LlmFactory.create(
                mem0_provider, llm_config
            )
            # Writes go through the per-user clients, so they take the
            # synced LLM too, and so does every client created later.
            with self._user_clients_lock:
                self._synced_llm = new_llm
                self.client.llm = new_llm
                for client in self._user_clients.values():
                    client.llm = new_llm
            logger.info(
                "Mem0 LLM synced to %s/%s",
                mem0_provider,
                model_name,
            )
        except Exception as e:
            logger.warning(
                "Failed to sync Mem0 LLM to %s/%s: %s",
                mem0_provider,
                model_name,
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
        metadata = note_metadata(memory_note)
        user_id = self._scope(metadata.get("user_id"))
        kwargs: Dict[str, Any] = {
            "user_id": user_id,
            "metadata": metadata,
            # Store the content verbatim. With infer=True Mem0's LLM
            # extracts facts and dedupes by hash, and in June 2026 that
            # stored nothing while add() reported success.
            "infer": False,
        }
        if self.default_agent_id:
            kwargs["agent_id"] = self.default_agent_id
        client = self._get_client_for_user(user_id)
        try:
            result = client.add(memory_note.content, **kwargs)
        except Exception as e:
            raise ProviderError(f"Mem0 add failed: {e}") from e
        memory_id = self._extract_memory_id(result)
        if not memory_id:
            raise ProviderError("Mem0 add returned no memory id")
        self._await_stored(client, memory_id)
        return memory_id

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
        client = self._get_client_for_user(self._scope(user_id))
        try:
            item = client.get(memory_id)
        except Exception:
            return None
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
