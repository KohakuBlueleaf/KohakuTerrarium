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
from kohakuterrarium.core.executor import Executor
from kohakuterrarium.core.job import JobResult, JobState, JobStatus, JobType
from kohakuterrarium.core.registry import Registry
from kohakuterrarium.llm.base import LLMProvider
from kohakuterrarium.llm.tools import build_tool_schemas
from kohakuterrarium.modules.subagent.config import SubAgentConfig
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
    parser_format: ToolCallFormat | None = None,
) -> str:
    """Build format-aware framework hints for sub-agents.

    Native mode: no format examples (API handles it).
    Custom mode: generate examples from the actual ToolCallFormat.
    """
    if tool_format == "native":
        return (
            "## Tool Calling\n\n"
            "Tools are called via the API's native function calling mechanism.\n"
            "You do not need to format tool calls manually.\n\n"
            + _SUBAGENT_CRITICAL_RULES
        )

    if parser_format is None:
        parser_format = BRACKET_FORMAT

    lines = ["## Tool Calling Format", ""]
    generic = format_tool_call_example(
        parser_format, "tool_name", {"arg": "value"}, "content here"
    )
    lines.append(f"```\n{generic}\n```")
    lines.append("")
    lines.append("Examples:")
    lines.append("")

    for name, args in [
        ("glob", {"pattern": "**/*.py"}),
        ("grep", {"pattern": "class.*Config"}),
        ("read", {"path": "src/main.py"}),
    ]:
        ex = format_tool_call_example(parser_format, name, args)
        lines.append(f"```\n{ex}\n```")
        lines.append("")

    lines.append(_SUBAGENT_CRITICAL_RULES)
    return "\n".join(lines)


# Backward-compatible alias (bracket format)
SUBAGENT_FRAMEWORK_HINTS = build_subagent_framework_hints("bracket", BRACKET_FORMAT)


@dataclass
class SubAgentResult:
    """Result from sub-agent execution."""

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
    """Nested agent with limited capabilities.

    A sub-agent runs with its own controller and tool access, but returns
    results to the parent controller (unless output_to=external).
    """

    def __init__(
        self,
        config: SubAgentConfig,
        parent_registry: Registry,
        llm: LLMProvider,
        agent_path: Any = None,
        tool_format: str | None = None,
    ):
        self.config = config
        self.parent_registry = parent_registry
        self.llm = llm
        self.agent_path = agent_path
        self.tool_format = tool_format

        # Optional callback for reporting tool activity to parent
        self.on_tool_activity: Any = None

        # Parent's tool context builder (inherited environment, working_dir, etc.)
        self._build_tool_context: Any = None

        # Optional session store for persisting sub-agent conversations
        self._session_store: Any = None
        self._parent_name: str = ""
        self._run_index: int = 0

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
        """Resolve a tool_format string to a ToolCallFormat instance."""
        match tool_format:
            case "xml":
                return XML_FORMAT
            case "native" | None | "bracket":
                return BRACKET_FORMAT
            case _:
                return BRACKET_FORMAT

    def _create_limited_registry(self) -> Registry:
        """Create registry with only allowed tools."""
        limited = Registry()
        self._missing_tools: list[str] = []

        for tool_name in self.config.tools:
            tool = self.parent_registry.get_tool(tool_name)
            if tool:
                limited.register_tool(tool)
            else:
                self._missing_tools.append(tool_name)
                logger.warning(
                    "Tool not found in parent registry",
                    tool_name=tool_name,
                    subagent=self.config.name,
                )

        return limited

    def _build_system_prompt(self) -> str:
        """Build complete system prompt with framework hints and tool list."""
        parts = []

        base_prompt = self.config.load_prompt(self.agent_path)
        parts.append(base_prompt)

        tool_names = self.registry.list_tools()
        if tool_names:
            tool_lines = ["## Available Tools", ""]
            for name in tool_names:
                info = self.registry.get_tool_info(name)
                desc = info.description if info else "Tool"
                tool_lines.append(f"- `{name}`: {desc}")
            parts.append("\n".join(tool_lines))

        if self._missing_tools:
            missing_note = (
                "## Unavailable Tools\n\n"
                "The following tools were requested but are not available: "
                + ", ".join(f"`{t}`" for t in self._missing_tools)
                + "\nDo NOT attempt to call these tools. Work with what is available."
            )
            parts.append(missing_note)

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
        """Execute the sub-agent with a task."""
        self._running = True
        self._start_time = datetime.now()
        self._turns = 0

        try:
            if self.config.timeout > 0:
                return await asyncio.wait_for(
                    self._run_internal(task),
                    timeout=self.config.timeout,
                )
            else:
                return await self._run_internal(task)
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

    # ------------------------------------------------------------------
    # Internal run logic (split into focused helpers)
    # ------------------------------------------------------------------

    async def _run_internal(self, task: str) -> SubAgentResult:
        """Internal run logic. Runs conversation loop with tool execution."""
        self._setup_conversation(task)

        native_tool_schemas = None
        if self._is_native:
            native_tool_schemas = build_tool_schemas(self.registry)

        output_parts: list[str] = []
        tools_used: list[str] = []

        while self.config.max_turns == 0 or self._turns < self.config.max_turns:
            self._turns += 1
            logger.debug(
                "Sub-agent turn started",
                subagent_name=self.config.name,
                turn=self._turns,
            )

            tool_calls, turn_output = await self._run_single_turn(native_tool_schemas)
            output_parts.extend(turn_output)

            if not tool_calls:
                logger.info(
                    "Sub-agent no tools called, finishing",
                    subagent_name=self.config.name,
                )
                break

            tools_used.extend(tc.name for tc in tool_calls)
            tool_results = await self._execute_and_report_tools(tool_calls)
            self._append_tool_results(tool_calls, tool_results)

        return self._build_result(output_parts, tools_used)

    def _setup_conversation(self, task: str) -> None:
        """Initialize conversation with system prompt and task."""
        self.conversation = Conversation()
        system_prompt = self._build_system_prompt()
        self.conversation.append("system", system_prompt)
        self.conversation.append("user", task)

    async def _run_single_turn(
        self, native_tool_schemas: Any
    ) -> tuple[list[ToolCallEvent], list[str]]:
        """Run one LLM turn. Returns (tool_calls, output_text_parts)."""
        messages = self.conversation.to_messages()
        if self._is_native and native_tool_schemas:
            return await self._run_native_turn(messages, native_tool_schemas)
        return await self._run_text_turn(messages)

    async def _run_native_turn(
        self, messages: list[dict], tool_schemas: Any
    ) -> tuple[list[ToolCallEvent], list[str]]:
        """Run one native-mode LLM turn."""
        assistant_content = ""
        output_parts: list[str] = []
        tool_calls: list[ToolCallEvent] = []

        async for chunk in self.llm.chat(
            messages, stream=True, tools=tool_schemas or None
        ):
            assistant_content += chunk
            if chunk:
                output_parts.append(chunk)

        native_calls = (
            self.llm.last_tool_calls if hasattr(self.llm, "last_tool_calls") else []
        )

        if native_calls:
            tool_calls_data = []
            for tc in native_calls:
                tool_calls_data.append(
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                )
                tool_calls.append(
                    ToolCallEvent(
                        name=tc.name,
                        args={**tc.parsed_arguments(), "_tool_call_id": tc.id},
                        raw=tc.arguments,
                    )
                )
                logger.info(
                    "Sub-agent native tool call",
                    subagent_name=self.config.name,
                    tool_name=tc.name,
                )
            self.conversation.append(
                "assistant",
                assistant_content or "",
                tool_calls=tool_calls_data,
            )
        else:
            self.conversation.append("assistant", assistant_content)

        self._log_turn_preview(assistant_content)
        return tool_calls, output_parts

    async def _run_text_turn(
        self, messages: list[dict]
    ) -> tuple[list[ToolCallEvent], list[str]]:
        """Run one custom-format LLM turn with stream parsing."""
        self._parser = StreamParser(self._parser_config)
        assistant_content = ""
        output_parts: list[str] = []
        tool_calls: list[ToolCallEvent] = []

        async for chunk in self.llm.chat(messages, stream=True):
            assistant_content += chunk
            for event in self._parser.feed(chunk):
                if isinstance(event, ToolCallEvent):
                    tool_calls.append(event)
                elif isinstance(event, TextEvent):
                    output_parts.append(event.text)

        for event in self._parser.flush():
            if isinstance(event, ToolCallEvent):
                tool_calls.append(event)
            elif isinstance(event, TextEvent):
                output_parts.append(event.text)

        self.conversation.append("assistant", assistant_content)
        self._log_turn_preview(assistant_content)
        return tool_calls, output_parts

    def _log_turn_preview(self, assistant_content: str) -> None:
        """Log a preview of the LLM response for debugging."""
        preview = assistant_content[:200].replace("\n", " ")
        logger.debug(
            "Sub-agent LLM response",
            subagent_name=self.config.name,
            turn=self._turns,
            preview=preview + ("..." if len(assistant_content) > 200 else ""),
        )

    async def _execute_and_report_tools(self, tool_calls: list[ToolCallEvent]) -> str:
        """Execute tools, notifying parent of start/done via callback."""
        logger.info(
            "Sub-agent executing tools",
            subagent_name=self.config.name,
            tool_count=len(tool_calls),
            tools=[tc.name for tc in tool_calls],
        )

        if self.on_tool_activity:
            for tc in tool_calls:
                tc_args = {k: v for k, v in tc.args.items() if not k.startswith("_")}
                args_preview = ""
                if tc_args:
                    parts = [f"{k}={str(v)[:80]}" for k, v in tc_args.items()]
                    args_preview = " ".join(parts)[:120]
                self.on_tool_activity("tool_start", tc.name, args_preview)

        tool_results = await self._execute_tools(tool_calls)

        if self.on_tool_activity:
            for tc in tool_calls:
                self.on_tool_activity("tool_done", tc.name, "")

        return tool_results

    def _append_tool_results(
        self, tool_calls: list[ToolCallEvent], tool_results: str
    ) -> None:
        """Add tool results to conversation in the appropriate format."""
        if self._is_native:
            for tc in tool_calls:
                tool_call_id = tc.args.get("_tool_call_id", "")
                result_text = ""
                for r in tool_results.split("\n\n") if tool_results else []:
                    if r.startswith(f"[{tc.name}]"):
                        result_text = r
                        break
                if not result_text:
                    result_text = tool_results or "(no output)"
                if tool_call_id:
                    self.conversation.append(
                        "tool",
                        result_text,
                        tool_call_id=tool_call_id,
                        name=tc.name,
                    )
        else:
            if tool_results:
                self.conversation.append("user", tool_results)

    def _build_result(
        self, output_parts: list[str], tools_used: list[str]
    ) -> SubAgentResult:
        """Build the final SubAgentResult, saving conversation if possible."""
        final_output = "".join(output_parts).strip()

        if self._session_store:
            try:
                self._session_store.save_subagent(
                    parent=self._parent_name,
                    name=self.config.name,
                    run=self._run_index,
                    meta={
                        "task": (
                            self.conversation.to_messages()[1].get("content", "")
                            if len(self.conversation.to_messages()) > 1
                            else ""
                        ),
                        "turns": self._turns,
                        "tools_used": tools_used,
                        "success": True,
                        "duration": self._calculate_duration(),
                        "output_preview": final_output[:500],
                    },
                    conv_json=self.conversation.to_json(),
                )
            except Exception as e:
                logger.debug(
                    "Failed to save sub-agent conversation",
                    subagent=self.config.name,
                    error=str(e),
                )

        return SubAgentResult(
            output=final_output,
            success=True,
            turns=self._turns,
            duration=self._calculate_duration(),
            metadata={"tools_used": tools_used},
        )

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

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

            args_preview = str(tool_call.args)[:100]
            logger.debug(
                "Sub-agent tool start",
                subagent_name=self.config.name,
                tool_name=tool_call.name,
                tool_args=args_preview,
            )

            try:
                context = (
                    self._build_tool_context() if self._build_tool_context else None
                )
                result = await tool.execute(tool_call.args, context=context)
                # Guard against tools that return str instead of ToolResult
                if isinstance(result, str):
                    results.append(f"[{tool_call.name}]\n{result}")
                    continue
                if result.success:
                    text_output = result.get_text_output()
                    output = text_output if text_output else "(no output)"
                    results.append(f"[{tool_call.name}]\n{output}")
                    logger.debug(
                        "Sub-agent tool success",
                        subagent_name=self.config.name,
                        tool_name=tool_call.name,
                        output_preview=(text_output or "")[:100].replace("\n", " "),
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
    """Wrapper for running a sub-agent as a background job.

    Integrates with the executor's job tracking system.
    """

    def __init__(self, subagent: SubAgent, job_id: str):
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
