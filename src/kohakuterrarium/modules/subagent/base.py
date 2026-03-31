"""
Sub-agent base class.

A sub-agent is a nested agent with its own controller, limited tool access,
and configurable output routing.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from kohakuterrarium.core.constants import TOOL_OUTPUT_PREVIEW_CHARS
from kohakuterrarium.core.conversation import Conversation
from kohakuterrarium.core.events import TriggerEvent
from kohakuterrarium.core.executor import Executor
from kohakuterrarium.core.job import JobResult, JobState, JobStatus, JobType
from kohakuterrarium.core.registry import Registry
from kohakuterrarium.llm.base import LLMProvider
from kohakuterrarium.modules.subagent.config import OutputTarget, SubAgentConfig
from kohakuterrarium.modules.tool.base import Tool
from kohakuterrarium.parsing import ParserConfig, StreamParser, TextEvent, ToolCallEvent
from kohakuterrarium.parsing.format import (
    BRACKET_FORMAT,
    XML_FORMAT,
    ToolCallFormat,
    format_tool_call_example,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


_SUBAGENT_CRITICAL_RULES = """
## CRITICAL: You MUST use tools to complete your task

- After calling a tool, STOP and wait for results
- Do NOT just describe what you would do - actually DO it
- Continue calling tools until task is complete
""".strip()


def build_subagent_framework_hints(
    tool_format: str | None,
    parser_format: "ToolCallFormat | None" = None,
) -> str:
    """Build format-aware framework hints for sub-agents.

    - Native mode: no format examples (API handles it)
    - Custom mode: generate examples from the actual ToolCallFormat
    """
    if tool_format == "native":
        return (
            "## Tool Calling\n\n"
            "Tools are called via the API's native function calling mechanism.\n"
            "You do not need to format tool calls manually.\n\n"
            + _SUBAGENT_CRITICAL_RULES
        )

    # Custom format: generate examples from ToolCallFormat
    if parser_format is None:
        parser_format = BRACKET_FORMAT

    lines = ["## Tool Calling Format", ""]

    # Show generic format
    generic = format_tool_call_example(
        parser_format, "tool_name", {"arg": "value"}, "content here"
    )
    lines.append(f"```\n{generic}\n```")
    lines.append("")

    # Show concrete examples
    lines.append("Examples:")
    lines.append("")

    glob_ex = format_tool_call_example(parser_format, "glob", {"pattern": "**/*.py"})
    lines.append(f"```\n{glob_ex}\n```")
    lines.append("")

    grep_ex = format_tool_call_example(
        parser_format, "grep", {"pattern": "class.*Config"}
    )
    lines.append(f"```\n{grep_ex}\n```")
    lines.append("")

    read_ex = format_tool_call_example(parser_format, "read", {"path": "src/main.py"})
    lines.append(f"```\n{read_ex}\n```")
    lines.append("")

    lines.append(_SUBAGENT_CRITICAL_RULES)
    return "\n".join(lines)


# Backward-compatible alias (bracket format)
SUBAGENT_FRAMEWORK_HINTS = build_subagent_framework_hints("bracket", BRACKET_FORMAT)


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
        tool_format: str | None = None,
    ):
        """
        Initialize sub-agent.

        Args:
            config: Sub-agent configuration
            parent_registry: Parent's registry for tool access
            llm: LLM provider (can be same as parent or different)
            agent_path: Path to agent folder for loading prompts
            tool_format: Tool format to use (None = bracket default).
                "native" means the LLM uses native tool calling.
                "bracket"/"xml"/custom are text-based formats.
        """
        self.config = config
        self.parent_registry = parent_registry
        self.llm = llm
        self.agent_path = agent_path
        self.tool_format = tool_format

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

        # Resolve tool call format for the parser
        self._is_native = tool_format == "native"
        parser_tool_format = self._resolve_parser_format(tool_format)

        # Stream parser with known tools from registry
        self._parser_config = ParserConfig(
            known_tools=set(self.registry.list_tools()),
            tool_format=parser_tool_format,
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
            tool_format=tool_format or "bracket",
        )

    @staticmethod
    def _resolve_parser_format(tool_format: str | None) -> ToolCallFormat:
        """Resolve a tool_format string to a ToolCallFormat instance.

        For native mode, we still return BRACKET_FORMAT as fallback
        (the parser won't be used much in native mode, but needs a valid format).
        """
        match tool_format:
            case "xml":
                return XML_FORMAT
            case "native" | None | "bracket":
                return BRACKET_FORMAT
            case _:
                return BRACKET_FORMAT

    def _create_limited_registry(self) -> Registry:
        """
        Create registry with only allowed tools.

        Tools not found in parent registry are tracked in self._missing_tools
        so the error can be surfaced to the LLM if the sub-agent tries to
        use them.
        """
        limited = Registry()
        self._missing_tools: list[str] = []

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
                self._missing_tools.append(tool_name)
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

        # Warn about missing tools so the LLM knows its limitations
        if self._missing_tools:
            missing_note = (
                "## Unavailable Tools\n\n"
                "The following tools were requested but are not available: "
                + ", ".join(f"`{t}`" for t in self._missing_tools)
                + "\nDo NOT attempt to call these tools. Work with what is available."
            )
            parts.append(missing_note)

        # Framework hints (format-aware)
        parser_fmt = self._resolve_parser_format(self.tool_format)
        parts.append(build_subagent_framework_hints(self.tool_format, parser_fmt))

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
                    # Use get_text_output() to handle both str and multimodal
                    text_output = result.get_text_output()
                    output = text_output if text_output else "(no output)"
                    results.append(f"[{tool_call.name}]\n{output}")
                    # Log success with output preview
                    output_preview = (text_output or "")[:100].replace("\n", " ")
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
