"""
Background executor for tools and sub-agents.

Manages async execution of tools without blocking the controller.
"""

import asyncio
from typing import Any, Callable

from kohakuterrarium.core.events import TriggerEvent, create_tool_complete_event
from kohakuterrarium.core.job import (
    JobResult,
    JobState,
    JobStatus,
    JobStore,
    JobType,
    generate_job_id,
)
from kohakuterrarium.modules.tool.base import Tool, ToolResult
from kohakuterrarium.parsing.events import ToolCallEvent
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class Executor:
    """
    Background executor for tools.

    Manages tool execution in background tasks and tracks job status.

    Usage:
        executor = Executor()
        executor.register_tool(BashTool())

        # Submit from parse event
        job_id = await executor.submit_from_event(tool_call_event)

        # Or submit directly
        job_id = await executor.submit("bash", {"command": "ls"})

        # Wait for result
        result = await executor.wait_for(job_id)

        # Or get events when jobs complete
        async for event in executor.events():
            handle_completion(event)
    """

    def __init__(
        self,
        job_store: JobStore | None = None,
        on_complete: Callable[[TriggerEvent], Any] | None = None,
    ):
        """
        Initialize executor.

        Args:
            job_store: Store for job statuses (creates new if None)
            on_complete: Callback when jobs complete
        """
        self.job_store = job_store or JobStore()
        self._tools: dict[str, Tool] = {}
        self._tasks: dict[str, asyncio.Task[JobResult]] = {}
        self._results: dict[str, JobResult] = {}
        self._on_complete = on_complete
        self._event_queue: asyncio.Queue[TriggerEvent] = asyncio.Queue()

    def register_tool(self, tool: Tool) -> None:
        """Register a tool for execution."""
        self._tools[tool.tool_name] = tool
        logger.debug("Registered tool", tool_name=tool.tool_name)

    def get_tool(self, tool_name: str) -> Tool | None:
        """Get a registered tool by name."""
        return self._tools.get(tool_name)

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    async def submit(
        self,
        tool_name: str,
        args: dict[str, Any],
        job_id: str | None = None,
    ) -> str:
        """
        Submit a tool for background execution.

        Args:
            tool_name: Name of the tool to execute
            args: Arguments for the tool
            job_id: Optional job ID (generated if not provided)

        Returns:
            Job ID

        Raises:
            ValueError: If tool not registered
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ValueError(f"Tool not registered: {tool_name}")

        # Generate job ID
        if job_id is None:
            job_id = generate_job_id(tool_name)

        # Create job status
        status = JobStatus(
            job_id=job_id,
            job_type=JobType.TOOL,
            type_name=tool_name,
            state=JobState.RUNNING,
        )
        self.job_store.register(status)

        # Start background task
        task = asyncio.create_task(self._run_tool(job_id, tool, args))
        self._tasks[job_id] = task

        logger.debug("Submitted tool", job_id=job_id, tool_name=tool_name)
        return job_id

    async def submit_from_event(self, event: ToolCallEvent) -> str:
        """
        Submit a tool from a ToolCallEvent.

        Args:
            event: Parsed tool call event

        Returns:
            Job ID
        """
        return await self.submit(event.name, event.args)

    async def _run_tool(
        self,
        job_id: str,
        tool: Tool,
        args: dict[str, Any],
    ) -> JobResult:
        """Run a tool and update status."""
        try:
            # Execute tool
            result = await tool.execute(args)

            # Create job result
            job_result = JobResult(
                job_id=job_id,
                output=result.output,
                exit_code=result.exit_code,
                error=result.error,
                metadata=result.metadata,
            )

            # Update status
            self.job_store.update_status(
                job_id,
                state=JobState.DONE if result.success else JobState.ERROR,
                output_lines=result.output.count("\n") + 1 if result.output else 0,
                output_bytes=len(result.output.encode("utf-8")),
                preview=result.output[:200] if result.output else "",
                error=result.error,
            )
            self.job_store.store_result(job_result)
            self._results[job_id] = job_result

            logger.debug(
                "Tool completed",
                job_id=job_id,
                success=result.success,
            )

            # Create completion event
            event = create_tool_complete_event(
                job_id=job_id,
                content=result.output[:1000] if result.output else "",
                exit_code=result.exit_code,
                error=result.error,
            )

            # Notify via callback or queue
            if self._on_complete:
                self._on_complete(event)
            await self._event_queue.put(event)

            return job_result

        except Exception as e:
            logger.error("Tool execution failed", job_id=job_id, error=str(e))

            # Update status with error
            self.job_store.update_status(
                job_id,
                state=JobState.ERROR,
                error=str(e),
            )

            job_result = JobResult(job_id=job_id, error=str(e))
            self._results[job_id] = job_result

            # Create error event
            event = create_tool_complete_event(
                job_id=job_id,
                content="",
                error=str(e),
            )
            if self._on_complete:
                self._on_complete(event)
            await self._event_queue.put(event)

            return job_result

    async def wait_for(
        self,
        job_id: str,
        timeout: float | None = None,
    ) -> JobResult | None:
        """
        Wait for a job to complete.

        Args:
            job_id: Job ID to wait for
            timeout: Maximum wait time in seconds

        Returns:
            JobResult if completed, None if timeout or not found
        """
        task = self._tasks.get(job_id)
        if task is None:
            # Check if already completed
            return self._results.get(job_id)

        try:
            return await asyncio.wait_for(task, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Wait timed out", job_id=job_id)
            return None

    async def wait_all(
        self,
        timeout: float | None = None,
    ) -> dict[str, JobResult]:
        """
        Wait for all pending jobs to complete.

        Args:
            timeout: Maximum total wait time

        Returns:
            Dict of job_id -> JobResult
        """
        if not self._tasks:
            return {}

        tasks = list(self._tasks.values())
        job_ids = list(self._tasks.keys())

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout,
            )

            return {
                job_id: result
                for job_id, result in zip(job_ids, results)
                if isinstance(result, JobResult)
            }
        except asyncio.TimeoutError:
            logger.warning("Wait all timed out")
            return {
                job_id: self._results[job_id]
                for job_id in job_ids
                if job_id in self._results
            }

    async def cancel(self, job_id: str) -> bool:
        """
        Cancel a running job.

        Args:
            job_id: Job to cancel

        Returns:
            True if cancelled, False if not found or already done
        """
        task = self._tasks.get(job_id)
        if task is None or task.done():
            return False

        task.cancel()
        self.job_store.update_status(job_id, state=JobState.CANCELLED)
        logger.debug("Cancelled job", job_id=job_id)
        return True

    def get_status(self, job_id: str) -> JobStatus | None:
        """Get job status."""
        return self.job_store.get_status(job_id)

    def get_result(self, job_id: str) -> JobResult | None:
        """Get job result (if completed)."""
        return self._results.get(job_id) or self.job_store.get_result(job_id)

    def get_running_jobs(self) -> list[JobStatus]:
        """Get all running jobs."""
        return self.job_store.get_running_jobs()

    async def events(self) -> TriggerEvent:
        """
        Async generator for completion events.

        Yields TriggerEvents when jobs complete.
        """
        while True:
            event = await self._event_queue.get()
            yield event

    def get_next_event_nowait(self) -> TriggerEvent | None:
        """Get next completion event without waiting."""
        try:
            return self._event_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def get_next_event(self, timeout: float | None = None) -> TriggerEvent | None:
        """Get next completion event with optional timeout."""
        try:
            if timeout:
                return await asyncio.wait_for(self._event_queue.get(), timeout)
            return await self._event_queue.get()
        except asyncio.TimeoutError:
            return None
