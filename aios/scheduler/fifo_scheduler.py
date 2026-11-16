# A FIFO scheduler: one thread per module queue. Each thread blocks on
# its queue until a syscall arrives (the queue's condition variable), so
# no request waits for a polling interval (NeurIPS Subtask 18,
# docs/STRESS_DIMENSIONS.md; known issue 15).

from aios.hooks.types.llm import LLMRequestQueueGetMessage
from aios.hooks.types.memory import MemoryRequestQueueGetMessage
from aios.hooks.types.tool import ToolRequestQueueGetMessage
from aios.hooks.types.storage import StorageRequestQueueGetMessage
# from aios.hooks.types.llm import LLMRequestQueue
# from aios.hooks.types.memory import MemoryRequestQueue
# from aios.hooks.types.tool import ToolRequestQueue
# from aios.hooks.types.storage import StorageRequestQueue


from aios.memory.manager import MemoryManager
from aios.storage.storage import StorageManager
from aios.llm_core.adapter import LLMAdapter
from aios.tool.manager import ToolManager

from .base import BaseScheduler

from queue import Empty

import traceback
import time
import logging
from typing import Optional, Any, Dict, List

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FIFOScheduler(BaseScheduler):
    """
    A FIFO (First-In-First-Out) task scheduler implementation.

    This scheduler processes tasks in the order they arrive. The LLM
    thread waits for a request, takes every request already queued with
    it and runs them as one batch; requests that arrive while a batch
    runs form the next one. Other tasks (Memory, Storage, Tool) are
    processed individually as they arrive. No thread polls on an
    interval: each blocks on its queue until a syscall is put.
    
    Example:
        ```python
        scheduler = FIFOScheduler(
            llm=llm_adapter,
            memory_manager=memory_mgr,
            storage_manager=storage_mgr,
            tool_manager=tool_mgr,
            log_mode="console",
            get_llm_syscall=llm_queue.get,
            get_memory_syscall=memory_queue.get,
            get_storage_syscall=storage_queue.get,
            get_tool_syscall=tool_queue.get,
        )
        scheduler.start()
        ```
    """

    def __init__(
        self,
        llm: LLMAdapter,
        memory_manager: MemoryManager,
        storage_manager: StorageManager,
        tool_manager: ToolManager,
        log_mode: str,
        get_llm_syscall: LLMRequestQueueGetMessage,
        get_memory_syscall: MemoryRequestQueueGetMessage,
        get_storage_syscall: StorageRequestQueueGetMessage,
        get_tool_syscall: ToolRequestQueueGetMessage,
    ):
        """
        Initialize the FIFO Scheduler.

        Args:
            llm: LLM adapter instance
            memory_manager: Memory management instance
            storage_manager: Storage management instance
            tool_manager: Tool management instance
            log_mode: Logging mode configuration
            get_llm_syscall: Function to get LLM syscalls
            get_memory_syscall: Function to get Memory syscalls
            get_storage_syscall: Function to get Storage syscalls
            get_tool_syscall: Function to get Tool syscalls. Each getter
                waits a short time for a syscall and raises
                ``queue.Empty`` when none came; the LLM getter also
                takes ``timeout=0`` (take without waiting), which the
                LLM thread uses to collect a batch.
        """
        super().__init__(
            llm,
            memory_manager,
            storage_manager,
            tool_manager,
            log_mode,
            get_llm_syscall,
            get_memory_syscall,
            get_storage_syscall,
            get_tool_syscall,
        )
        
    def _execute_syscall(
        self, 
        syscall: Any,
        executor: Any,
        syscall_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a system call with proper status tracking and error handling.
        
        Args:
            syscall: The system call to execute
            executor: Function to execute the syscall
            syscall_type: Type of the syscall for logging
            
        Returns:
            Optional[Dict[str, Any]]: Response from the syscall execution
            
        Example:
            ```python
            response = scheduler._execute_syscall(
                llm_syscall,
                self.llm.execute_llm_syscall,
                "LLM"
            )
            ```
        """
        try:
            syscall.set_status("executing")
            self.logger.log(
                f"{syscall.agent_name} is executing {syscall_type} syscall.\n",
                "executing"
            )
            syscall.set_start_time(time.time())

            response = executor(syscall)
            syscall.set_response(response)

            syscall.event.set()
            syscall.set_status("done")
            syscall.set_end_time(time.time())

            self.logger.log(
                f"Completed {syscall_type} syscall for {syscall.agent_name}. "
                f"Thread ID: {syscall.get_pid()}\n",
                "done"
            )
            
            return response

        except Exception as e:
            logger.error(f"Error executing {syscall_type} syscall: {str(e)}")
            traceback.print_exc()
            return None


    def _execute_batch_syscalls(
        self,
        batch: List[Any],
        executor: Any,
        syscall_type: str
    ) -> None:
        """
        Execute a batch of system calls with proper status tracking and error handling.

        Args:
            batch: The list of system calls to execute
            executor: Function to execute the batch of syscalls
            syscall_type: Type of the syscalls for logging
        """
        if not batch:
            return

        start_time = time.time()
        for syscall in batch:
            try:
                syscall.set_status("executing")
                
                logger.info(f"{syscall.agent_name} preparing batched {syscall_type} syscall.")
                syscall.set_start_time(start_time)
            except Exception as e:
                logger.error(f"Error preparing syscall {getattr(syscall, 'agent_name', 'unknown')} for batch execution: {str(e)}")
                continue

        if not batch:
            logger.warning(f"Empty batch after preparation for {syscall_type}, skipping execution.")
            return

        # self.logger.log(
        #     f"Executing batch of {len(batch)} {syscall_type} syscalls.\n",
        #     "executing_batch"
        # )
        logger.info(f"Executing batch of {len(batch)} {syscall_type} syscalls.")

        try:
            responses = executor(batch)

            for i, syscall in enumerate(batch):
                logger.info(f"Completed batched {syscall_type} syscall for {syscall.agent_name}. "
                    f"Thread ID: {syscall.get_pid()}\n")


        except Exception as e:
            logger.error(f"Error executing {syscall_type} syscall batch: {str(e)}")
            traceback.print_exc()


    def _queued(self, get) -> List[Any]:
        """Every syscall already in the queue ``get`` reads, in arrival
        order, without waiting for more."""
        taken = []
        while True:
            try:
                taken.append(get(timeout=0))
            except Empty:
                return taken

    def process_llm_requests(self) -> None:
        """
        Process LLM requests as they arrive, in batches.

        The thread blocks on the queue until a request is put (its wait
        ends at once; the short timeout only lets it see ``stop``), then
        takes every request already queued and runs them as one batch,
        in arrival order. Requests that arrive while a batch runs wait
        for it and form the next batch. Until Subtask 18 the thread
        slept ``batch_interval`` (1 s) before each collection, so a
        request waited up to a second for nothing (known issue 15).

        Example:
            ```python
            # Two requests queued together run as one batch:
            # Batch = [
            #   {"messages": [{"role": "user", "content": "Hello"}]},
            #   {"messages": [{"role": "user", "content": "World"}]}
            # ]
            # Calls self.llm.execute_llm_syscalls(Batch)
            ```
        """
        while self.active:
            try:
                first = self.get_llm_syscall()
            except Empty:
                continue
            batch = [first] + self._queued(self.get_llm_syscall)
            self._execute_batch_syscalls(
                batch, self.llm.execute_llm_syscalls, "LLM"
            )

    def process_memory_requests(self) -> None:
        """
        Process Memory requests from the queue.
        
        Example:
            ```python
            scheduler.process_memory_requests()
            # Processes Memory requests like:
            # {
            #     "operation": "store",
            #     "data": {"key": "value"}
            # }
            ```
        """
        while self.active:
            try:
                memory_syscall = self.get_memory_syscall()
                self._execute_syscall(
                    memory_syscall,
                    self.memory_manager.address_request,
                    "Memory"
                )
            except Empty:
                pass

    def process_storage_requests(self) -> None:
        """
        Process Storage requests from the queue.
        
        Example:
            ```python
            scheduler.process_storage_requests()
            # Processes Storage requests like:
            # {
            #     "operation": "write",
            #     "path": "/tmp/file.txt",
            #     "content": "Hello, World!"
            # }
            ```
        """
        while self.active:
            try:
                storage_syscall = self.get_storage_syscall()
                self._execute_syscall(
                    storage_syscall,
                    self.storage_manager.address_request,
                    "Storage"
                )
            except Empty:
                pass

    def process_tool_requests(self) -> None:
        """
        Process Tool requests from the queue.
        
        Example:
            ```python
            scheduler.process_tool_requests()
            # Processes Tool requests like:
            # {
            #     "name": "calculator",
            #     "arguments": {
            #         "operation": "add",
            #         "numbers": [1, 2]
            #     }
            # }
            ```
        """
        while self.active:
            try:
                tool_syscall = self.get_tool_syscall()
                self._execute_syscall(
                    tool_syscall,
                    self.tool_manager.address_request,
                    "Tool"
                )
            except Empty:
                pass

    def start(self) -> None:
        """
        Start all request processing threads.
        
        Example:
            ```python
            scheduler = FIFOScheduler(...)
            scheduler.start()
            # Starts processing all types of requests
            ```
        """
        self.active = True
        self.start_processing_threads([
            self.process_llm_requests,
            self.process_memory_requests,
            self.process_storage_requests,
            self.process_tool_requests
        ])

    def stop(self) -> None:
        """
        Stop all request processing threads.
        
        Example:
            ```python
            scheduler.stop()
            # Stops all processing threads gracefully
            ```
        """
        self.active = False
        self.stop_processing_threads()
