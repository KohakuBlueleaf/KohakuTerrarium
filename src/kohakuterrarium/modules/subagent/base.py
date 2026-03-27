"""
Sub-agent base class.

A sub-agent is a nested agent with its own controller, limited tool access,
and configurable output routing.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from kohakuterrarium.core.constants import (
    SUBAGENT_TOOL_OUTPUT_MAX_CHARS,
    TOOL_OUTPUT_PREVIEW_CHARS,
)
from kohakuterrarium.core.conversation import Conversation
from kohakuterrarium.core.events import TriggerEvent
from kohakuterrarium.core.executor import Executor
from kohakuterrarium.core.job import JobResult, JobState, JobStatus, JobType
from kohakuterrarium.core.registry import Registry
from kohakuterrarium.llm.base import LLMProvider
from kohakuterrarium.modules.subagent.config import OutputTarget, SubAgentConfig
from kohakuterrarium.modules.tool.base import Tool
from kohakuterrarium.parsing import ParserConfig, StreamParser, TextEvent, ToolCallEvent
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


# Framework hints for sub-agents (simplified version)
SUBAGENT_FRAMEWORK_HINTS = """
## Tool Calling Format

Format: `[/name]` opens, `[name/]` closes

```
[/tool_name]
@@arg=value
content here
[tool_name/]
```

Examples:

```
[/glob]@@pattern=**/*.py[glob/]
```

```
[/grep]@@pattern=class.*Config[grep/]
```

```
[/read]@@path=src/main.py[read/]
```

## CRITICAL: You MUST use tools to complete your task

- Call tools using the [/tool]...[tool/] format above
- After calling a tool, STOP and wait for results
- Do NOT just describe what you would do - actually DO it
- Continue calling tools until task is complete
""".strip()


@dataclass
class SubAgentResult:
    """
    Result from sub-agent execution.

    Attributes:
        output: Main output content
        success: Whether execution was successful
        error: Error message if failed
        turns: Number of conversation turns used
        duration: Execution time in seconds
        metadata: Additional result data
    """

    output: str = ""
    success: bool = True
    error: str | None = None
    turns: int = 0
    duration: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def truncated(self, max_chars: int = 2000) -> str:
        """Get truncated output with note if truncated."""
        if len(self.output) <= max_chars:
            return self.output
        return f"{self.output[:max_chars]}\n... ({len(self.output) - max_chars} more chars)"


class SubAgent:
    """
    Nested agent with limited capabilities.

    A sub-agent runs with its own controller and tool access, but returns
    results to the parent controller (unless output_to=external).

    Usage:
        config = SubAgentConfig(name="explore", tools=["glob", "grep", "read"])
        subagent = SubAgent(config, parent_registry, llm_provider)
        result = await subagent.run("Find all Python files with 'async def'")
    """

    def __init__(
        self,
        config: SubAgentConfig,
        parent_registry: Registry,
        llm: LLMProvider,
        agent_path: Any = None,
    ):
        """
        Initialize sub-agent.

        Args:
            config: Sub-agent configuration
            parent_registry: Parent's registry for tool access
            llm: LLM provider (can be same as parent or different)
            agent_path: Path to agent folder for loading prompts
        """
        self.config = config
        self.parent_registry = parent_registry
        self.llm = llm
        self.agent_path = agent_path

        # Create limited registry with only allowed tools
        self.registry = self._create_limited_registry()

        # Create executor for this sub-agent
        self.executor = Executor()
        for tool_name in self.registry.list_tools():
            tool = self.registry.get_tool(tool_name)
            if tool:
                self.executor.register_tool(tool)

        # Conversation for this sub-agent
        self.conversation = Conversation()

        # Stream parser with known tools from registry
        self._parser_config = ParserConfig(
            known_tools=set(self.registry.list_tools()),
        )
        self._parser = StreamParser(self._parser_config)

        # State
        self._running = False
        self._start_time: datetime | None = None
        self._turns = 0

        logger.debug(
            "SubAgent created",
            subagent_name=config.name,
            tools=config.tools,
        )

    def _create_limited_registry(self) -> Registry:
        """Create registry with only allowed tools."""
        limited = Registry()

        for tool_name in self.config.tools:
            tool = self.parent_registry.get_tool(tool_name)
            if tool:
                # Check if tool is allowed based on can_modify
                if not self.config.can_modify and self._is_modifying_tool(tool_name):
                    logger.warning(
                        "Skipping modifying tool for read-only sub-agent",
                        tool_name=tool_name,
                        subagent=self.config.name,
                    )
                    continue
                limited.register_tool(tool)
            else:
                logger.warning(
                    "Tool not found in parent registry",
                    tool_name=tool_name,
                    subagent=self.config.name,
                )

        return limited

    # Default set of tools considered modifying (used when config.modifying_tools is None)
    DEFAULT_MODIFYING_TOOLS: set[str] = {"write", "edit", "bash", "python"}

    def _is_modifying_tool(self, tool_name: str) -> bool:
        """Check if tool can modify files."""
        modifying_tools = (
            self.config.modifying_tools
            if self.config.modifying_tools is not None
            else self.DEFAULT_MODIFYING_TOOLS
        )
        return tool_name in modifying_tools

    def _build_system_prompt(self) -> str:
        """Build complete system prompt with framework hints and tool list."""
        parts = []

        # Base prompt from config
        base_prompt = self.config.load_prompt(self.agent_path)
        parts.append(base_prompt)

        # Tool list
        tool_names = self.registry.list_tools()
        if tool_names:
            tool_lines = ["## Available Tools", ""]
            for name in tool_names:
                info = self.registry.get_tool_info(name)
                desc = info.description if info else "Tool"
                tool_lines.append(f"- `{name}`: {desc}")
            parts.append("\n".join(tool_lines))

        # Framework hints
        parts.append(SUBAGENT_FRAMEWORK_HINTS)

        result = "\n\n".join(parts)
        logger.info(
            "Sub-agent system prompt built",
            subagent_name=self.config.name,
            tool_count=len(tool_names),
            prompt_length=len(result),
        )
        return result

    async def run(self, task: str) -> SubAgentResult:
        """
        Execute the sub-agent with a task.

        Args:
            task: Task description for the sub-agent

        Returns:
            SubAgentResult with output and status
        """
        self._running = True
        self._start_time = datetime.now()
        self._turns = 0

        try:
            return await asyncio.wait_for(
                self._run_internal(task),
                timeout=self.config.timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Sub-agent timed out",
                subagent_name=self.config.name,
                timeout=self.config.timeout,
            )
            return SubAgentResult(
                success=False,
                error=f"Timed out after {self.config.timeout}s",
                turns=self._turns,
                duration=self._calculate_duration(),
            )
        except Exception as e:
            logger.error(
                "Sub-agent error",
                subagent_name=self.config.name,
                error=str(e),
            )
            return SubAgentResult(
                success=False,
                error=str(e),
                turns=self._turns,
                duration=self._calculate_duration(),
            )
        finally:
            self._running = False

    async def _run_internal(self, task: str) -> SubAgentResult:
        """Internal run logic."""
        # Setup conversation
        self.conversation = Conversation()
        system_prompt = self._build_system_prompt()
        self.conversation.append("system", system_prompt)
        self.conversation.append("user", task)

        output_parts: list[str] = []

        # Run conversation loop
        while self._turns < self.config.max_turns:
            self._turns += 1
            logger.debug(
                "Sub-agent turn started",
                subagent_name=self.config.name,
                turn=self._turns,
            )

            # Get response from LLM
            messages = self.conversation.to_messages()
            assistant_content = ""
            self._parser = StreamParser(self._parser_config)

            # Track tools to execute
            tool_calls: list[ToolCallEvent] = []

            async for chunk in self.llm.chat(messages, stream=True):
                assistant_content += chunk

                # Parse for tool calls
                for event in self._parser.feed(chunk):
                    if isinstance(event, ToolCallEvent):
                        tool_calls.append(event)
                    elif isinstance(event, TextEvent):
                        output_parts.append(event.text)

            # Flush parser
            for event in self._parser.flush():
                if isinstance(event, ToolCallEvent):
                    tool_calls.append(event)
                elif isinstance(event, TextEvent):
                    output_parts.append(event.text)

            # Add assistant message to conversation
            self.conversation.append("assistant", assistant_content)

            # Log LLM output preview
            preview = assistant_content[:200].replace("\n", " ")
            logger.debug(
                "Sub-agent LLM response",
                subagent_name=self.config.name,
                turn=self._turns,
                preview=preview + ("..." if len(assistant_content) > 200 else ""),
            )

            # If no tool calls, we're done
            if not tool_calls:
                logger.info(
                    "Sub-agent no tools called - finishing",
                    subagent_name=self.config.name,
                    response_preview=assistant_content[:300].replace("\n", "\\n"),
                )
                logger.debug(
                    "Sub-agent completed (no more tool calls)",
                    subagent_name=self.config.name,
                    total_turns=self._turns,
                )
                break

            # Execute tools
            logger.info(
                "Sub-agent executing tools",
                subagent_name=self.config.name,
                tool_count=len(tool_calls),
                tools=[tc.name for tc in tool_calls],
            )
            tool_results = await self._execute_tools(tool_calls)

            # Add tool results as user message
            if tool_results:
                self.conversation.append("user", tool_results)

        # Build final output
        final_output = "".join(output_parts).strip()

        return SubAgentResult(
            output=final_output,
            success=True,
            turns=self._turns,
            duration=self._calculate_duration(),
        )

    async def _execute_tools(self, tool_calls: list[ToolCallEvent]) -> str:
        """Execute tool calls and return formatted results."""
        results: list[str] = []

        for tool_call in tool_calls:
            tool = self.registry.get_tool(tool_call.name)
            if tool is None:
                logger.warning(
                    "Sub-agent tool not available",
                    subagent_name=self.config.name,
                    tool_name=tool_call.name,
                )
                results.append(f"[{tool_call.name}] Error: Tool not available")
                continue

            # Log tool execution start
            args_preview = str(tool_call.args)[:100]
            logger.debug(
                "Sub-agent tool start",
                subagent_name=self.config.name,
                tool_name=tool_call.name,
                tool_args=args_preview,
            )

            try:
                result = await tool.execute(tool_call.args)
                if result.success:
                    output = (
                        result.output[:SUBAGENT_TOOL_OUTPUT_MAX_CHARS]
                        if result.output
                        else "(no output)"
                    )
                    results.append(f"[{tool_call.name}]\n{output}")
                    # Log success with output preview
                    output_preview = (result.output or "")[:100].replace("\n", " ")
                    logger.debug(
                        "Sub-agent tool success",
                        subagent_name=self.config.name,
                        tool_name=tool_call.name,
                        output_preview=output_preview,
                    )
                else:
                    error = result.error or "Unknown error"
                    results.append(f"[{tool_call.name}] Error: {error}")
                    logger.warning(
                        "Sub-agent tool failed",
                        subagent_name=self.config.name,
                        tool_name=tool_call.name,
                        error=error,
                    )
            except Exception as e:
                results.append(f"[{tool_call.name}] Error: {str(e)}")
                logger.error(
                    "Sub-agent tool exception",
                    subagent_name=self.config.name,
                    tool_name=tool_call.name,
                    error=str(e),
                )

        return "\n\n".join(results)

    def _calculate_duration(self) -> float:
        """Calculate elapsed time."""
        if self._start_time:
            return (datetime.now() - self._start_time).total_seconds()
        return 0.0

    @property
    def is_running(self) -> bool:
        """Check if sub-agent is currently running."""
        return self._running


class SubAgentJob:
    """
    Wrapper for running a sub-agent as a background job.

    Integrates with the executor's job tracking system.
    """

    def __init__(
        self,
        subagent: SubAgent,
        job_id: str,
    ):
        self.subagent = subagent
        self.job_id = job_id
        self._task: asyncio.Task | None = None
        self._result: SubAgentResult | None = None

    async def run(self, task: str) -> SubAgentResult:
        """Run the sub-agent and return result."""
        self._result = await self.subagent.run(task)
        return self._result

    def to_job_status(self) -> JobStatus:
        """Create job status for this sub-agent run."""
        # Check error first, then running, then done
        if self._result and not self._result.success:
            state = JobState.ERROR
        elif self.subagent.is_running:
            state = JobState.RUNNING
        else:
            state = JobState.DONE

        return JobStatus(
            job_id=self.job_id,
            job_type=JobType.SUBAGENT,
            type_name=self.subagent.config.name,
            state=state,
            output_lines=self._result.output.count("\n") + 1 if self._result else 0,
            output_bytes=len(self._result.output) if self._result else 0,
            preview=(
                self._result.output[:TOOL_OUTPUT_PREVIEW_CHARS] if self._result else ""
            ),
            error=self._result.error if self._result else None,
        )

    def to_job_result(self) -> JobResult | None:
        """Convert to JobResult for compatibility."""
        if not self._result:
            return None

        return JobResult(
            job_id=self.job_id,
            output=self._result.output,
            exit_code=0 if self._result.success else 1,
            error=self._result.error,
            metadata={
                "turns": self._result.turns,
                "duration": self._result.duration,
            },
        )
