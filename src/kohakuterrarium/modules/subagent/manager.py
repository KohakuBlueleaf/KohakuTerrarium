"""
Sub-agent manager.

Handles sub-agent lifecycle, spawning, and status tracking.
Supports both regular (stateless) and interactive (long-lived) sub-agents.
"""

import asyncio
from pathlib import Path
from typing import Any, Callable

from kohakuterrarium.core.job import (
    JobResult,
    JobState,
    JobStatus,
    JobStore,
    JobType,
    generate_job_id,
)
from kohakuterrarium.core.registry import Registry
from kohakuterrarium.llm.base import LLMProvider
from kohakuterrarium.modules.subagent.base import SubAgent, SubAgentJob, SubAgentResult
from kohakuterrarium.modules.subagent.config import SubAgentConfig, SubAgentInfo
from kohakuterrarium.modules.subagent.interactive import (
    InteractiveOutput,
    InteractiveSubAgent,
)
from kohakuterrarium.parsing.events import SubAgentCallEvent
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class SubAgentManager:
    """
    Manages sub-agent lifecycle and execution.

    Responsibilities:
    - Register sub-agent configurations
    - Spawn sub-agents on demand
    - Track running sub-agents
    - Handle results and cleanup

    Usage:
        manager = SubAgentManager(registry, llm, job_store)
        manager.register(SubAgentConfig(name="explore", ...))

        # Spawn and run
        job_id = await manager.spawn("explore", "Find auth code")
        result = await manager.wait_for(job_id)

        # Or spawn from event
        job_id = await manager.spawn_from_event(subagent_call_event)
    """

    def __init__(
        self,
        parent_registry: Registry,
        llm: LLMProvider,
        job_store: JobStore | None = None,
        agent_path: Path | None = None,
        current_depth: int = 0,
        max_depth: int = 3,
    ):
        """
        Initialize sub-agent manager.

        Args:
            parent_registry: Parent's registry for tool access
            llm: LLM provider for sub-agents
            job_store: Store for job status tracking
            agent_path: Path to agent folder for prompt loading
            current_depth: Current nesting depth of this agent
            max_depth: Maximum allowed sub-agent depth (0 = unlimited)
        """
        self.parent_registry = parent_registry
        self.llm = llm
        self.job_store = job_store or JobStore()
        self.agent_path = agent_path
        self._current_depth: int = current_depth
        self._max_depth: int = max_depth

        # Registered sub-agent configs
        self._configs: dict[str, SubAgentConfig] = {}

        # Running sub-agent jobs (for stateless sub-agents)
        self._jobs: dict[str, SubAgentJob] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._results: dict[str, SubAgentResult] = {}

        # Interactive sub-agents (long-lived)
        self._interactive: dict[str, InteractiveSubAgent] = {}
        self._output_callbacks: dict[str, Callable[[InteractiveOutput], None]] = {}

    def register(self, config: SubAgentConfig) -> None:
        """
        Register a sub-agent configuration.

        Args:
            config: Sub-agent configuration
        """
        self._configs[config.name] = config
        logger.debug(
            "Registered sub-agent",
            subagent_name=config.name,
            tools=config.tools,
        )

    def get_config(self, name: str) -> SubAgentConfig | None:
        """Get sub-agent config by name."""
        return self._configs.get(name)

    def list_subagents(self) -> list[str]:
        """List registered sub-agent names."""
        return list(self._configs.keys())

    def get_subagent_info(self, name: str) -> SubAgentInfo | None:
        """Get sub-agent info for system prompt."""
        config = self._configs.get(name)
        if config:
            return SubAgentInfo.from_config(config)
        return None

    def get_subagents_prompt(self) -> str:
        """Generate sub-agents section for system prompt."""
        if not self._configs:
            return ""

        lines = ["## Available Sub-Agents", ""]
        for name, config in self._configs.items():
            info = SubAgentInfo.from_config(config)
            lines.append(info.to_prompt_line())

        lines.append("")
        lines.append(
            "Use: `[/name]task description[name/]` (e.g., `[/explore]find auth code[explore/]`)"
        )

        return "\n".join(lines)

    async def spawn(
        self,
        name: str,
        task: str,
        job_id: str | None = None,
    ) -> str:
        """
        Spawn a sub-agent to execute a task.

        Args:
            name: Sub-agent name
            task: Task description
            job_id: Optional job ID (generated if not provided)

        Returns:
            Job ID

        Raises:
            ValueError: If sub-agent not registered
        """
        config = self._configs.get(name)
        if config is None:
            raise ValueError(f"Sub-agent not registered: {name}")

        # Check depth limit before spawning
        if self._max_depth > 0 and self._current_depth >= self._max_depth:
            error_msg = (
                f"Sub-agent depth limit reached ({self._current_depth}/{self._max_depth}). "
                f"Cannot spawn '{name}'. Simplify your approach or use tools directly."
            )
            logger.warning(
                "Sub-agent depth limit reached",
                subagent_name=name,
                current_depth=self._current_depth,
                max_depth=self._max_depth,
            )
            # Generate job ID and store error result
            if job_id is None:
                job_id = generate_job_id(f"agent_{name}")

            error_result = SubAgentResult(success=False, error=error_msg)
            self._results[job_id] = error_result

            status = JobStatus(
                job_id=job_id,
                job_type=JobType.SUBAGENT,
                type_name=name,
                state=JobState.ERROR,
                error=error_msg,
            )
            self.job_store.register(status)

            return job_id

        # Generate job ID
        if job_id is None:
            job_id = generate_job_id(f"agent_{name}")

        # Create sub-agent
        subagent = SubAgent(
            config=config,
            parent_registry=self.parent_registry,
            llm=self.llm,
            agent_path=self.agent_path,
        )

        # Create job wrapper
        job = SubAgentJob(subagent, job_id)
        self._jobs[job_id] = job

        # Register job status
        status = JobStatus(
            job_id=job_id,
            job_type=JobType.SUBAGENT,
            type_name=name,
            state=JobState.RUNNING,
        )
        self.job_store.register(status)

        # Start background task
        task_obj = asyncio.create_task(self._run_subagent(job_id, job, task))
        self._tasks[job_id] = task_obj

        logger.info(
            "Spawned sub-agent",
            subagent_name=name,
            job_id=job_id,
        )

        return job_id

    async def spawn_from_event(self, event: SubAgentCallEvent) -> str:
        """
        Spawn sub-agent from a parsed event.

        Args:
            event: Parsed sub-agent call event

        Returns:
            Job ID
        """
        task = event.args.get("task", event.args.get("content", ""))
        return await self.spawn(event.name, task)

    async def _run_subagent(
        self,
        job_id: str,
        job: SubAgentJob,
        task: str,
    ) -> SubAgentResult:
        """Run sub-agent and update status."""
        try:
            result = await job.run(task)
            self._results[job_id] = result

            # Update status
            state = JobState.DONE if result.success else JobState.ERROR
            self.job_store.update_status(
                job_id,
                state=state,
                output_lines=result.output.count("\n") + 1 if result.output else 0,
                output_bytes=len(result.output),
                preview=result.output[:200] if result.output else "",
                error=result.error,
            )

            # Store result
            job_result = job.to_job_result()
            if job_result:
                self.job_store.store_result(job_result)

            logger.info(
                "Sub-agent completed",
                job_id=job_id,
                success=result.success,
                turns=result.turns,
            )

            return result

        except Exception as e:
            logger.error(
                "Sub-agent failed",
                job_id=job_id,
                error=str(e),
            )

            result = SubAgentResult(success=False, error=str(e))
            self._results[job_id] = result

            self.job_store.update_status(
                job_id,
                state=JobState.ERROR,
                error=str(e),
            )

            return result

    async def wait_for(
        self,
        job_id: str,
        timeout: float | None = None,
    ) -> SubAgentResult | None:
        """
        Wait for a sub-agent to complete.

        Args:
            job_id: Job ID to wait for
            timeout: Maximum wait time

        Returns:
            SubAgentResult if completed, None if timeout
        """
        task = self._tasks.get(job_id)
        if task is None:
            return self._results.get(job_id)

        try:
            return await asyncio.wait_for(task, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Wait timed out", job_id=job_id)
            return None

    async def wait_all(
        self,
        timeout: float | None = None,
    ) -> dict[str, SubAgentResult]:
        """
        Wait for all running sub-agents.

        Args:
            timeout: Maximum total wait time

        Returns:
            Dict of job_id -> SubAgentResult
        """
        if not self._tasks:
            return {}

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*self._tasks.values(), return_exceptions=True),
                timeout=timeout,
            )

            return {
                job_id: (
                    result
                    if isinstance(result, SubAgentResult)
                    else SubAgentResult(error=str(result))
                )
                for job_id, result in zip(self._tasks.keys(), results)
            }
        except asyncio.TimeoutError:
            return {
                job_id: self._results.get(job_id, SubAgentResult(error="Timeout"))
                for job_id in self._tasks.keys()
            }

    async def cancel(self, job_id: str) -> bool:
        """
        Cancel a running sub-agent.

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
        logger.debug("Cancelled sub-agent", job_id=job_id)
        return True

    def get_status(self, job_id: str) -> JobStatus | None:
        """Get sub-agent job status."""
        return self.job_store.get_status(job_id)

    def get_result(self, job_id: str) -> SubAgentResult | None:
        """Get sub-agent result (if completed)."""
        return self._results.get(job_id)

    def get_running_jobs(self) -> list[JobStatus]:
        """Get all running sub-agent jobs."""
        return [
            status
            for status in self.job_store.get_running_jobs()
            if status.job_type == JobType.SUBAGENT
        ]

    def cleanup(self, job_id: str) -> None:
        """
        Cleanup a completed sub-agent job.

        Args:
            job_id: Job to cleanup
        """
        self._jobs.pop(job_id, None)
        self._tasks.pop(job_id, None)
        # Keep result for potential later access
        logger.debug("Cleaned up sub-agent", job_id=job_id)

    def cleanup_all_completed(self) -> int:
        """
        Cleanup all completed sub-agent jobs.

        Returns:
            Number of jobs cleaned up
        """
        completed = [job_id for job_id, task in self._tasks.items() if task.done()]

        for job_id in completed:
            self.cleanup(job_id)

        return len(completed)

    # =========================================================================
    # Interactive Sub-Agent Management
    # =========================================================================

    async def start_interactive(
        self,
        name: str,
        on_output: Callable[[InteractiveOutput], None] | None = None,
    ) -> InteractiveSubAgent:
        """
        Start an interactive sub-agent.

        Interactive sub-agents stay alive and receive context updates.

        Args:
            name: Sub-agent name (must be registered with interactive=True)
            on_output: Callback for output chunks

        Returns:
            InteractiveSubAgent instance

        Raises:
            ValueError: If sub-agent not registered or not interactive
        """
        config = self._configs.get(name)
        if config is None:
            raise ValueError(f"Sub-agent not registered: {name}")

        if not config.interactive:
            raise ValueError(f"Sub-agent is not interactive: {name}")

        # Check if already running
        if name in self._interactive:
            logger.warning(
                "Interactive sub-agent already running",
                subagent_name=name,
            )
            return self._interactive[name]

        # Create interactive sub-agent
        agent = InteractiveSubAgent(
            config=config,
            parent_registry=self.parent_registry,
            llm=self.llm,
            agent_path=self.agent_path,
        )

        # Set output callback
        if on_output:
            agent.on_output = on_output
            self._output_callbacks[name] = on_output

        # Start the agent
        await agent.start()
        self._interactive[name] = agent

        logger.info(
            "Started interactive sub-agent",
            subagent_name=name,
            context_mode=config.context_mode.value,
        )

        return agent

    async def stop_interactive(self, name: str) -> None:
        """
        Stop an interactive sub-agent.

        Args:
            name: Sub-agent name
        """
        agent = self._interactive.get(name)
        if agent:
            await agent.stop()
            del self._interactive[name]
            self._output_callbacks.pop(name, None)

            logger.info("Stopped interactive sub-agent", subagent_name=name)

    async def stop_all_interactive(self) -> None:
        """Stop all running interactive sub-agents."""
        names = list(self._interactive.keys())
        for name in names:
            await self.stop_interactive(name)

    async def push_context(
        self,
        name: str,
        context: dict[str, Any],
    ) -> None:
        """
        Push context update to an interactive sub-agent.

        Args:
            name: Sub-agent name
            context: Context data to push

        Raises:
            ValueError: If sub-agent not running
        """
        agent = self._interactive.get(name)
        if agent is None:
            raise ValueError(f"Interactive sub-agent not running: {name}")

        await agent.push_context(context)

    async def push_context_all(self, context: dict[str, Any]) -> None:
        """
        Push context update to all running interactive sub-agents.

        Args:
            context: Context data to push
        """
        for agent in self._interactive.values():
            await agent.push_context(context)

    def get_interactive(self, name: str) -> InteractiveSubAgent | None:
        """
        Get a running interactive sub-agent.

        Args:
            name: Sub-agent name

        Returns:
            InteractiveSubAgent if running, None otherwise
        """
        return self._interactive.get(name)

    def list_interactive(self) -> list[str]:
        """
        List running interactive sub-agents.

        Returns:
            List of sub-agent names
        """
        return list(self._interactive.keys())

    def get_interactive_output(self, name: str) -> str:
        """
        Get and clear buffered output from interactive sub-agent.

        Used for return_as_context functionality.

        Args:
            name: Sub-agent name

        Returns:
            Buffered output text (empty if not found)
        """
        agent = self._interactive.get(name)
        if agent:
            return agent.get_buffered_output()
        return ""

    def set_output_callback(
        self,
        name: str,
        callback: Callable[[InteractiveOutput], None],
    ) -> None:
        """
        Set output callback for an interactive sub-agent.

        Args:
            name: Sub-agent name
            callback: Callback function for output chunks
        """
        agent = self._interactive.get(name)
        if agent:
            agent.on_output = callback
            self._output_callbacks[name] = callback
