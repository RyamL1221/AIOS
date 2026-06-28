"""
Mem0Provider - Memory provider using Mem0 for AI-native memory management.

This provider integrates with the Mem0 library to provide AI-native memory
management capabilities including automatic memory extraction, semantic search,
and intelligent memory organization.
"""
import logging
import os
import time
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from cerebrum.memory.apis import MemoryQuery, MemoryResponse

from .base import (
    MemoryProvider,
    _apply_sharing_filter,
    _enrich_metadata,
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

                    # Inject a PersistentClient to bypass Mem0's
                    # deprecated chromadb.Client(Settings(...)) which
                    # is always in-memory in ChromaDB >= 0.4
                    if not vs_cfg.get("client"):
                        import chromadb
                        from chromadb.config import (
                            Settings as ChromaSettings,
                        )
                        vs_cfg["client"] = (
                            chromadb.PersistentClient(
                                path=vs_cfg["path"],
                                settings=ChromaSettings(
                                    anonymized_telemetry=False,
                                ),
                            )
                        )
                        logger.info(
                            "Injected PersistentClient for "
                            "ChromaDB at %s",
                            vs_cfg["path"],
                        )

            # Resolve API keys for cloud LLM/embedder providers
            self._resolve_provider_api_keys(mem0_config)
            
            # Initialize Mem0 client
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
    # Dynamic LLM synchronization
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_filter_metadata(item: dict) -> dict:
        """Build a unified metadata dict for _apply_sharing_filter.

        Mem0's ``_search_vector_store`` promotes certain payload keys
        (``user_id``, ``agent_id``, ``run_id``, ``actor_id``, ``role``)
        to top-level fields in the returned dict, EXCLUDING them from
        the nested ``item["metadata"]`` dict.  The sharing filter needs
        ``user_id`` alongside ``owner_agent`` and ``sharing_policy`` in
        a single dict.

        This helper merges top-level promoted keys back into the nested
        metadata so ``_apply_sharing_filter`` can read all cross-agent
        fields from one place.
        """
        meta = dict(item.get("metadata") or {})
        # Merge promoted keys that _apply_sharing_filter needs.
        for key in ("user_id", "agent_id"):
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

            # Resolve API key for the target provider.
            api_key = self._get_api_key(
                # Mem0 provider names mostly align with
                # ConfigManager key names. For azure_openai,
                # fall back to "openai" since AIOS stores the
                # key under that name.
                "openai" if mem0_provider.startswith("azure")
                else mem0_provider
            )
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
            self.client.llm = new_llm
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

    def _await_searchable(
        self,
        memory_id: str,
        user_id: str,
        max_wait: float = 10.0,
        interval: float = 0.5,
    ) -> bool:
        """Poll Mem0 until a newly written memory is visible
        through get_all().

        Returns True if the memory becomes visible before timeout.
        Returns False if the timeout is reached.
        """
        waited = 0.0

        while waited < max_wait:
            try:
                all_memories = self.client.get_all(
                    filters={"user_id": user_id}
                )
            except Exception:
                logger.exception(
                    "add_memory: failed while checking "
                    "searchability for memory %s user_id=%s",
                    memory_id,
                    user_id,
                )
                time.sleep(interval)
                waited += interval
                continue

            memories = self._normalize_get_all_result(
                all_memories
            )

            found = any(
                memory.get("id") == memory_id
                or memory.get("memory_id") == memory_id
                for memory in memories
                if isinstance(memory, dict)
            )

            if found:
                return True

            time.sleep(interval)
            waited += interval

        logger.warning(
            "add_memory: memory %s not searchable after "
            "%.1fs user_id=%s",
            memory_id,
            max_wait,
            user_id,
        )

        return False

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def add_memory(self, memory_note: 'MemoryNote') -> MemoryResponse:
        """Add a memory note to Mem0 storage.
        
        Maps MemoryNote fields to Mem0's memory format and stores the memory
        with associated metadata. Extracts user_id and agent_id from the
        memory_note metadata, falling back to config defaults.
        
        Args:
            memory_note: The memory note to store
        
        Returns:
            MemoryResponse with success=True and memory_id on success,
            or success=False with error message on failure.
        """
        from aios.memory.note import MemoryNote
        
        if not isinstance(memory_note, MemoryNote):
            return MemoryResponse(
                success=False,
                error=f"Expected MemoryNote, got {type(memory_note).__name__}"
            )
        
        try:
            # Extract user_id and agent_id from metadata or use defaults
            user_id = self.default_user_id
            agent_id = self.default_agent_id
            
            # Check if memory_note has metadata attribute with provider-specific params
            if hasattr(memory_note, 'metadata') and memory_note.metadata:
                user_id = memory_note.metadata.get("user_id", user_id)
                agent_id = memory_note.metadata.get("agent_id", agent_id)
            
            # Build metadata for Mem0
            metadata = {
                "keywords": memory_note.keywords,
                "tags": memory_note.tags,
                "category": memory_note.category,
                "context": memory_note.context,
                "timestamp": memory_note.timestamp,
                "memory_note_id": memory_note.id
            }

            # Preserve cross-agent metadata fields so
            # that _apply_sharing_filter can read them
            # on retrieval.
            if hasattr(memory_note, 'metadata') and memory_note.metadata:
                for key in (
                    "owner_agent",
                    "sharing_policy",
                    "memory_type",
                    "user_id",
                ):
                    val = memory_note.metadata.get(key)
                    if val is not None:
                        metadata[key] = val
            
            # Build add parameters
            add_kwargs = {
                "user_id": user_id,
                "metadata": metadata
            }
            
            if agent_id:
                add_kwargs["agent_id"] = agent_id
            
            # Add memory to Mem0
            result = self.client.add(memory_note.content, **add_kwargs)
            
            # Extract memory ID from result
            memory_id = self._extract_memory_id(result)

            # Fall back to original memory_note ID if Mem0
            # doesn't return one
            memory_id = memory_id or memory_note.id

            # --- Diagnostic: verify memory was stored ---
            try:
                all_for_user = self.client.get_all(
                    filters={"user_id": user_id},
                    top_k=100,
                )
                stored_count = len(
                    self._normalize_get_all_result(
                        all_for_user
                    )
                )
            except Exception as diag_err:
                stored_count = f"<error: {diag_err}>"
            logger.info(
                "[MEM0_DEBUG] add: user_id=%s, "
                "content='%s', memory_id=%s, "
                "add_result_type=%s, "
                "total_stored_for_user=%s",
                user_id,
                (memory_note.content or "")[:80],
                memory_id,
                type(result).__name__,
                stored_count,
            )
            # Also print to ensure capture in kernel.log
            print(
                f"[MEM0_DEBUG] add: user_id={user_id}, "
                f"content='{(memory_note.content or '')[:80]}', "
                f"memory_id={memory_id}, "
                f"add_result_type={type(result).__name__}, "
                f"total_stored_for_user={stored_count}",
                flush=True,
            )

            # Wait until the memory is visible through get_all()
            # so downstream retrievals (and the write barrier)
            # observe the committed state.
            if memory_id:
                self._await_searchable(memory_id, user_id)
            else:
                logger.warning(
                    "add_memory: Mem0 write succeeded but no "
                    "memory_id was returned user_id=%s",
                    user_id,
                )
            
            return MemoryResponse(success=True, memory_id=memory_id)
            
        except Exception as e:
            return MemoryResponse(
                success=False,
                error=f"Mem0 add_memory failed: {str(e)}"
            )
    
    def remove_memory(self, memory_id: str) -> MemoryResponse:
        """Remove a memory from Mem0 by ID.
        
        Args:
            memory_id: Unique identifier of the memory to remove
        
        Returns:
            MemoryResponse with success=True on successful removal,
            or success=False with error message on failure.
        """
        try:
            self.client.delete(memory_id)
            return MemoryResponse(success=True, memory_id=memory_id)
        except Exception as e:
            return MemoryResponse(
                success=False,
                error=f"Mem0 remove_memory failed: {str(e)}"
            )
    
    def update_memory(self, memory_note: 'MemoryNote') -> MemoryResponse:
        """Update an existing memory in Mem0.
        
        Args:
            memory_note: The memory note with updated content/metadata
        
        Returns:
            MemoryResponse with success=True and memory_id on success,
            or success=False with error message on failure.
        """
        from aios.memory.note import MemoryNote
        
        if not isinstance(memory_note, MemoryNote):
            return MemoryResponse(
                success=False,
                error=f"Expected MemoryNote, got {type(memory_note).__name__}"
            )
        
        try:
            # Mem0 update takes memory_id and new data
            self.client.update(memory_note.id, memory_note.content)
            return MemoryResponse(success=True, memory_id=memory_note.id)
        except Exception as e:
            return MemoryResponse(
                success=False,
                error=f"Mem0 update_memory failed: {str(e)}"
            )
    
    def get_memory(self, memory_id: str) -> MemoryResponse:
        """Retrieve a memory from Mem0 by ID.
        
        Args:
            memory_id: Unique identifier of the memory to retrieve
        
        Returns:
            MemoryResponse with success=True, content, and metadata on success,
            or success=False with error message if memory not found.
        """
        if not isinstance(memory_id, str):
            return MemoryResponse(
                success=False,
                error="Memory id must be a string"
            )
        
        try:
            result = self.client.get(memory_id)
            
            if result is None:
                return MemoryResponse(success=False, error="Memory not found")
            
            # Extract content and metadata from Mem0 result
            content = result.get("memory", "") if isinstance(result, dict) else str(result)
            metadata = result.get("metadata", {}) if isinstance(result, dict) else {}
            
            return MemoryResponse(
                success=True,
                content=content,
                metadata={
                    "keywords": metadata.get("keywords", []),
                    "tags": metadata.get("tags", []),
                    "category": metadata.get("category", "Uncategorized"),
                    "timestamp": metadata.get("timestamp", "")
                }
            )
        except Exception as e:
            return MemoryResponse(
                success=False,
                error=f"Mem0 get_memory failed: {str(e)}"
            )
    
    def retrieve_memory(self, query: MemoryQuery) -> MemoryResponse:
        """Search for memories in Mem0 matching the query.
        
        Performs semantic search using Mem0's search functionality to
        find memories similar to the query content.  Results are
        filtered by cross-agent sharing rules when ``agent_name``,
        ``user_id``, or ``sharing_policy`` are present in
        ``query.params``.
        
        Args:
            query: MemoryQuery containing:
                  - params["content"]: The search query text
                  - params["k"]: Maximum number of results to return
                  - params["agent_name"]: (optional) requesting agent
                  - params["user_id"]: (optional) user-scope filter
                  - params["sharing_policy"]: (optional) policy filter
                  - params["agent_id"]: Optional agent ID for search
        
        Returns:
            MemoryResponse with success=True and search_results on
            success.
        """
        try:
            content = query.params.get("content", "")
            k = query.params.get("k", 5)
            agent_name = query.params.get("agent_name")
            sharing_policy = query.params.get(
                "sharing_policy"
            )

            # Use user_id from params when provided;
            # fall back to agent_name (which scopes to the
            # memories stored by ConversationExtractor for
            # this agent), then to the configured default.
            user_id = query.params.get("user_id")
            search_user_id = (
                user_id
                if user_id is not None
                else (agent_name or self.default_user_id)
            )

            agent_id = query.params.get(
                "agent_id", self.default_agent_id
            )
            
            # Build search parameters.
            # Mem0 >= 0.1.29 requires entity IDs inside
            # a ``filters`` dict rather than as top-level
            # keyword arguments.
            search_filters: dict = {
                "user_id": search_user_id,
            }
            search_kwargs: dict = {
                "filters": search_filters,
                "top_k": k,
                # Disable mem0's internal scoring threshold.
                # The user_id pre-filter already scopes results
                # to the correct user; AIOS's own
                # relevance_threshold handles quality filtering
                # at the ContextInjector level. Without this,
                # mem0's score_and_rank() discards valid results
                # as the ChromaDB collection grows (scores drop
                # below 0.1 with more diverse embeddings).
                "threshold": 0.0,
            }
            
            if agent_id:
                search_filters["agent_id"] = agent_id
            
            # Search Mem0
            results = self.client.search(
                content, **search_kwargs
            )
            
            # Normalise Mem0 results into a flat list of
            # dicts regardless of the response format.
            items: list = []
            if isinstance(results, list):
                items = results
            elif (
                isinstance(results, dict)
                and "results" in results
            ):
                items = results["results"]

            # --- Diagnostic: log search outcome ---
            logger.info(
                "[MEM0_DEBUG] search: user_id=%s, "
                "query='%s', top_k=%d, threshold=%s, "
                "raw_result_count=%d",
                search_user_id,
                (content or "")[:80],
                k,
                search_kwargs.get("threshold"),
                len(items),
            )
            # Also print to ensure capture in kernel.log
            print(
                f"[MEM0_DEBUG] search: user_id={search_user_id}, "
                f"query='{(content or '')[:80]}', "
                f"top_k={k}, threshold={search_kwargs.get('threshold')}, "
                f"raw_result_count={len(items)}",
                flush=True,
            )
            if not items:
                # Check if memories exist at all for this user
                try:
                    all_for_user = self.client.get_all(
                        filters={"user_id": search_user_id},
                        top_k=100,
                    )
                    stored = self._normalize_get_all_result(
                        all_for_user
                    )
                    stored_count = len(stored)
                except Exception as diag_err:
                    stored_count = -1
                    logger.warning(
                        "[MEM0_DEBUG] get_all probe failed: "
                        "%s",
                        diag_err,
                    )
                if stored_count > 0:
                    logger.warning(
                        "[MEM0_DEBUG] search returned 0 but "
                        "get_all(user_id=%s) found %d "
                        "memories. Likely a scoring/threshold "
                        "issue inside mem0.",
                        search_user_id,
                        stored_count,
                    )
                    print(
                        f"[MEM0_DEBUG] search returned 0 but "
                        f"get_all(user_id={search_user_id}) "
                        f"found {stored_count} memories. "
                        f"Likely a scoring/threshold issue.",
                        flush=True,
                    )
                elif stored_count == 0:
                    logger.warning(
                        "[MEM0_DEBUG] search returned 0 and "
                        "get_all(user_id=%s) also found 0. "
                        "No memories stored for this user_id.",
                        search_user_id,
                    )
                    print(
                        f"[MEM0_DEBUG] search returned 0 and "
                        f"get_all(user_id={search_user_id}) "
                        f"also found 0. No memories stored.",
                        flush=True,
                    )
            # --- End diagnostic ---

            # Apply cross-agent sharing filter when
            # agent_name is available (injected by
            # MemoryManager).
            if agent_name is not None:
                pre_filter_count = len(items)
                items = _apply_sharing_filter(
                    items,
                    agent_name,
                    user_id,
                    sharing_policy,
                    self._extract_filter_metadata,
                )
                logger.debug(
                    "retrieve_memory sharing filter: "
                    "retained %d/%d for agent=%s "
                    "user_id=%s policy=%s",
                    len(items),
                    pre_filter_count,
                    agent_name,
                    user_id,
                    sharing_policy,
                )

            # Map filtered items to standard format,
            # respecting k on the filtered set.
            search_results = []
            for item in items[:k]:
                if not isinstance(item, dict):
                    continue
                metadata = _enrich_metadata(
                    self._extract_filter_metadata(item)
                )
                search_results.append({
                    "content": item.get("memory", ""),
                    "keywords": metadata.get(
                        "keywords", []
                    ),
                    "tags": metadata.get("tags", []),
                    "category": metadata.get(
                        "category", "Uncategorized"
                    ),
                    "timestamp": metadata.get(
                        "timestamp", ""
                    ),
                    "score": item.get("score"),
                    "metadata": metadata,
                })
            
            return MemoryResponse(
                success=True,
                search_results=search_results,
            )
            
        except Exception as e:
            return MemoryResponse(
                success=False,
                error=(
                    f"Mem0 retrieve_memory failed: "
                    f"{str(e)}"
                ),
            )
    
    def retrieve_memory_raw(self, query: MemoryQuery) -> List['MemoryNote']:
        """Retrieve raw memory objects from Mem0 for internal processing.
        
        Similar to retrieve_memory but returns raw MemoryNote objects
        instead of a formatted MemoryResponse.  Results are filtered
        by cross-agent sharing rules when ``agent_name``,
        ``user_id``, or ``sharing_policy`` are present in
        ``query.params``.
        
        Args:
            query: MemoryQuery containing:
                  - params["content"]: The search query text
                  - params["k"]: Maximum number of results (default: 5)
                  - params["agent_name"]: (optional) requesting agent
                  - params["user_id"]: (optional) user-scope filter
                  - params["sharing_policy"]: (optional) policy filter
                  - params["agent_id"]: Optional agent ID for search
        
        Returns:
            List of MemoryNote objects matching the query.
        """
        from aios.memory.note import MemoryNote
        
        content = query.params.get("content", "")
        k = query.params.get("k", 5)
        agent_name = query.params.get("agent_name")
        sharing_policy = query.params.get("sharing_policy")

        # Use user_id from params when provided;
        # fall back to agent_name (which scopes to the
        # memories stored by ConversationExtractor for
        # this agent), then to the configured default.
        user_id = query.params.get("user_id")
        search_user_id = (
            user_id
            if user_id is not None
            else (agent_name or self.default_user_id)
        )

        agent_id = query.params.get(
            "agent_id", self.default_agent_id
        )
        
        # Build search parameters.
        # Mem0 >= 0.1.29 requires entity IDs inside
        # a ``filters`` dict.
        search_filters: dict = {
            "user_id": search_user_id,
        }
        search_kwargs: dict = {
            "filters": search_filters,
            "top_k": k,
            # Disable mem0's internal scoring threshold.
            # See retrieve_memory() for rationale.
            "threshold": 0.0,
        }
        
        if agent_id:
            search_filters["agent_id"] = agent_id
        
        try:
            results = self.client.search(
                content, **search_kwargs
            )
        except Exception:
            return []
        
        # Normalise Mem0 results into a flat list of
        # dicts regardless of the response format.
        items: list = []
        if isinstance(results, list):
            items = results
        elif (
            isinstance(results, dict)
            and "results" in results
        ):
            items = results["results"]

        # --- Diagnostic: log search outcome ---
        logger.info(
            "[MEM0_DEBUG] search_raw: user_id=%s, "
            "query='%s', top_k=%d, threshold=%s, "
            "raw_result_count=%d",
            search_user_id,
            (content or "")[:80],
            k,
            search_kwargs.get("threshold"),
            len(items),
        )
        # Also print to ensure capture in kernel.log
        print(
            f"[MEM0_DEBUG] search_raw: user_id={search_user_id}, "
            f"query='{(content or '')[:80]}', "
            f"top_k={k}, threshold={search_kwargs.get('threshold')}, "
            f"raw_result_count={len(items)}",
            flush=True,
        )
        if not items:
            try:
                all_for_user = self.client.get_all(
                    filters={"user_id": search_user_id},
                    top_k=100,
                )
                stored = self._normalize_get_all_result(
                    all_for_user
                )
                stored_count = len(stored)
            except Exception as diag_err:
                stored_count = -1
                logger.warning(
                    "[MEM0_DEBUG] get_all probe failed "
                    "(raw): %s",
                    diag_err,
                )
            if stored_count > 0:
                logger.warning(
                    "[MEM0_DEBUG] search_raw returned 0 but "
                    "get_all(user_id=%s) found %d memories. "
                    "Likely a scoring/threshold issue.",
                    search_user_id,
                    stored_count,
                )
            elif stored_count == 0:
                logger.warning(
                    "[MEM0_DEBUG] search_raw returned 0 and "
                    "get_all(user_id=%s) also found 0. "
                    "No memories stored for this user_id.",
                    search_user_id,
                )
        # --- End diagnostic ---

        # Apply cross-agent sharing filter when
        # agent_name is available (injected by
        # MemoryManager).
        if agent_name is not None:
            pre_filter_count = len(items)
            items = _apply_sharing_filter(
                items,
                agent_name,
                user_id,
                sharing_policy,
                self._extract_filter_metadata,
            )
            logger.debug(
                "retrieve_memory_raw sharing filter: "
                "retained %d/%d for agent=%s "
                "user_id=%s policy=%s",
                len(items),
                pre_filter_count,
                agent_name,
                user_id,
                sharing_policy,
            )

        # Convert filtered items to MemoryNote objects,
        # respecting k on the filtered set.
        memory_notes = []
        for item in items[:k]:
            if not isinstance(item, dict):
                continue
            metadata = _enrich_metadata(
                self._extract_filter_metadata(item)
            )
            memory_note = MemoryNote(
                content=item.get("memory", ""),
                id=(
                    item.get("id")
                    or metadata.get("memory_note_id")
                ),
                keywords=metadata.get("keywords", []),
                tags=metadata.get("tags", []),
                category=metadata.get(
                    "category", "Uncategorized"
                ),
                context=metadata.get("context", "General"),
                timestamp=metadata.get("timestamp"),
                metadata=metadata,
            )
            memory_notes.append(memory_note)
        
        return memory_notes
    
    def close(self) -> None:
        """Clean up Mem0 resources.
        
        Properly disconnects from Mem0 services and releases resources.
        """
        # Mem0 client doesn't require explicit cleanup
        # but we reset the client reference
        self.client = None
