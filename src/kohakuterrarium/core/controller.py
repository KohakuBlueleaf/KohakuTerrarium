"""
Controller - Main LLM conversation loop with event queue.

The controller orchestrates agent operation:
- Receives TriggerEvents (input, tool completion, etc.)
- Maintains conversation context
- Runs LLM and parses output
- Dispatches tool calls and sub-agents

Supports multimodal content (text + images).
"""

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncIterator

if TYPE_CHECKING:
    from kohakuterrarium.llm.base import ToolSchema
    from kohakuterrarium.llm.message import ContentPart

from kohakuterrarium.parsing import (
    CommandEvent,
    CommandResultEvent,
    ParseEvent,
    ParserConfig,
    StreamParser,
    SubAgentCallEvent,
    TextEvent,
    ToolCallEvent,
)
from kohakuterrarium.commands.base import Command, CommandResult
from kohakuterrarium.commands.read import (
    InfoCommand,
    JobsCommand,
    ReadCommand,
    WaitCommand,
)
from kohakuterrarium.core.conversation import Conversation, ConversationConfig
from kohakuterrarium.core.events import TriggerEvent
from kohakuterrarium.core.executor import Executor
from kohakuterrarium.core.job import JobResult, JobStatus, JobStore
from kohakuterrarium.core.registry import Registry
from kohakuterrarium.llm.base import LLMProvider
from kohakuterrarium.utils.logging import get_logger
from kohakuterrarium.modules.tool.base import ToolInfo

logger = get_logger(__name__)


@dataclass
class ControllerConfig:
    """
    Configuration for the controller.

    Attributes:
        system_prompt: Base system prompt
        include_job_status: Include job status in context
        include_tools_list: Include tool list in system prompt
        batch_stackable_events: Batch stackable events together
        max_context_chars: Maximum context length
        max_messages: Maximum number of messages to keep
        ephemeral: If True, clear conversation after each interaction (keep system only)
        known_outputs: Set of known output target names (e.g., "discord")
        tool_format: Tool calling format — "bracket", "xml", "native", or None
    """

    system_prompt: str = "You are a helpful assistant."
    include_job_status: bool = True
    include_tools_list: bool = True
    batch_stackable_events: bool = True
    max_context_chars: int = 100000  # ~25k tokens, reasonable default
    max_messages: int = 50  # Keep last 50 messages
    ephemeral: bool = False  # Clear after each interaction (for group chat bots)
    known_outputs: set[str] = field(default_factory=set)  # Output targets for parser
    tool_format: str | None = None  # "bracket", "xml", "native", or None (auto)


@dataclass
class ControllerContext:
    """
    Context object passed to commands and handlers.

    Provides access to controller internals for commands like ##read##.
    """

    controller: "Controller"
    job_store: JobStore
    registry: Registry

    def get_job_status(self, job_id: str) -> JobStatus | None:
        """Get job status."""
        return self.job_store.get_status(job_id)

    def get_job_result(self, job_id: str) -> JobResult | None:
        """Get job result."""
        if self.controller.executor:
            return self.controller.executor.get_result(job_id)
        return self.job_store.get_result(job_id)

    def get_tool_info(self, tool_name: str) -> ToolInfo | None:
        """Get tool info."""
        return self.registry.get_tool_info(tool_name)

    def get_subagent_info(self, subagent_name: str) -> str | None:
        """Get sub-agent info (placeholder)."""
        return None


class Controller:
    """
    Main controller for agent operation.

    Manages:
    - Event queue for incoming triggers
    - Conversation history
    - LLM interaction with streaming
    - Tool/sub-agent dispatch
    - Command execution

    Usage:
        controller = Controller(llm_provider, config)

        # Push events
        await controller.push_event(trigger_event)

        # Run controller loop
        async for parse_event in controller.run_once():
            if isinstance(parse_event, TextEvent):
                print(parse_event.text, end="")
            elif isinstance(parse_event, ToolCallEvent):
                handle_tool_call(parse_event)
    """

    def __init__(
        self,
        llm: LLMProvider,
        config: ControllerConfig | None = None,
        executor: Executor | None = None,
        registry: Registry | None = None,
    ):
        """
        Initialize controller.

        Args:
            llm: LLM provider for chat
            config: Controller configuration
            executor: Tool executor (creates one if None)
            registry: Module registry (creates one if None)
        """
        self.llm = llm
        self.config = config or ControllerConfig()
        self.executor = executor
        self.registry = registry or Registry()

        # Conversation history (with limits from config)
        conv_config = ConversationConfig(
            max_messages=self.config.max_messages,
            max_context_chars=self.config.max_context_chars,
            keep_system=True,
        )
        self.conversation = Conversation(conv_config)

        # Event queue
        self._event_queue: asyncio.Queue[TriggerEvent] = asyncio.Queue()
        self._pending_events: list[TriggerEvent] = []

        # Stream parser (config built lazily from registry)
        self._parser_config: ParserConfig | None = None
        self._parser: StreamParser | None = None

        # Job store (shared with executor if provided)
        if executor:
            self.job_store = executor.job_store
        else:
            self.job_store = JobStore()

        # Commands
        self._commands: dict[str, Command] = {
            "read": ReadCommand(),
            "info": InfoCommand(),
            "jobs": JobsCommand(),
            "wait": WaitCommand(),
        }

        # Context for commands
        self._context = ControllerContext(
            controller=self,
            job_store=self.job_store,
            registry=self.registry,
        )

        # Setup system prompt
        self._setup_system_prompt()

    def _get_parser(self) -> StreamParser:
        """Get parser with current registry tools, sub-agents, and outputs."""
        from kohakuterrarium.parsing.format import BRACKET_FORMAT, XML_FORMAT

        # Build config from current registry state
        known_tools = set(self.registry.list_tools())
        known_subagents = set(self.registry.list_subagents())

        # Resolve tool format for parser
        fmt = self.config.tool_format
        tool_format = BRACKET_FORMAT  # default
        if fmt == "xml":
            tool_format = XML_FORMAT

        self._parser_config = ParserConfig(
            known_tools=known_tools,
            known_subagents=known_subagents,
            known_outputs=self.config.known_outputs,
            tool_format=tool_format,
        )
        return StreamParser(self._parser_config)

    @property
    def _is_native_mode(self) -> bool:
        """Check if using native API tool calling."""
        return self.config.tool_format == "native"

    def _get_native_tool_schemas(self) -> "list[ToolSchema]":
        """Build native tool schemas from registry."""
        from kohakuterrarium.llm.tools import build_tool_schemas

        return build_tool_schemas(self.registry)

    def _setup_system_prompt(self) -> None:
        """Setup initial system prompt."""
        prompt_parts = [self.config.system_prompt]

        # Add tool list
        if self.config.include_tools_list:
            tools_prompt = self.registry.get_tools_prompt()
            if tools_prompt:
                prompt_parts.append(tools_prompt)

        # Join and add to conversation
        full_prompt = "\n\n".join(prompt_parts)
        self.conversation.append("system", full_prompt)

    async def push_event(self, event: TriggerEvent) -> None:
        """
        Push an event to the controller queue.

        Args:
            event: Trigger event to process
        """
        await self._event_queue.put(event)
        logger.debug("Event pushed", event_type=event.type)

    def push_event_sync(self, event: TriggerEvent) -> None:
        """Push event synchronously (for callbacks)."""
        self._event_queue.put_nowait(event)

    async def _collect_events(self) -> list[TriggerEvent]:
        """Collect and batch pending events."""
        events: list[TriggerEvent] = []

        # First, use any pending events from previous run
        if self._pending_events:
            events.extend(self._pending_events)
            self._pending_events.clear()

        # Get first event from queue if we don't have any yet
        if not events:
            if self._event_queue.empty():
                # No events at all, will block until one arrives
                first = await self._event_queue.get()
                events.append(first)
            else:
                # Get first event non-blocking
                events.append(self._event_queue.get_nowait())

        # Collect additional stackable events (non-blocking)
        if self.config.batch_stackable_events:
            while not self._event_queue.empty():
                try:
                    event = self._event_queue.get_nowait()
                    if event.stackable and events and events[-1].stackable:
                        events.append(event)
                    else:
                        # Non-stackable, save for next run
                        self._pending_events.append(event)
                        break
                except asyncio.QueueEmpty:
                    break

        return events

    def _format_events_for_context(
        self, events: list[TriggerEvent]
    ) -> "str | list[ContentPart]":
        """
        Format events as user message content.

        Returns multimodal content if any event has images.
        """
        from kohakuterrarium.llm.message import ContentPart, ImagePart, TextPart

        text_parts: list[str] = []
        image_parts: list[ImagePart] = []
        has_multimodal = False

        for event in events:
            if event.type == "user_input":
                if isinstance(event.content, list):
                    has_multimodal = True
                    # Extract text and images from multimodal content
                    for part in event.content:
                        if isinstance(part, TextPart):
                            text_parts.append(part.text)
                        elif isinstance(part, ImagePart):
                            image_parts.append(part)
                elif isinstance(event.content, str):
                    text_parts.append(event.content)
            elif event.type == "tool_complete":
                content_text = event.get_text_content()
                text_parts.append(
                    f"[Tool {event.job_id} completed]\n{content_text[:500]}"
                )
            elif event.type == "subagent_output":
                content_text = event.get_text_content()
                text_parts.append(
                    f"[Sub-agent {event.job_id} output]\n{content_text[:500]}"
                )
            else:
                content_text = event.get_text_content()
                text_parts.append(f"[{event.type}] {content_text}")

        # Combine text
        combined_text = "\n\n".join(text_parts)

        # Return multimodal if we have images
        if has_multimodal and image_parts:
            result: list[ContentPart] = [TextPart(text=combined_text)]
            result.extend(image_parts)
            return result

        return combined_text

    async def run_once(self) -> AsyncIterator[ParseEvent]:
        """
        Run one controller turn.

        Collects pending events, runs LLM, and yields parse events.

        Yields:
            ParseEvents as they are detected in the LLM output
        """
        # Collect events
        events = await self._collect_events()
        if not events:
            return

        logger.debug("Processing events", count=len(events))

        # Build context with job status
        from kohakuterrarium.llm.message import ContentPart, ImagePart, TextPart

        text_context_parts: list[str] = []
        image_context_parts: list[ImagePart] = []

        if self.config.include_job_status:
            job_context = self.job_store.format_context()
            if job_context:
                text_context_parts.append(job_context)

        # Add event content (may be multimodal)
        event_content = self._format_events_for_context(events)

        if isinstance(event_content, str):
            text_context_parts.append(event_content)
        else:
            # Multimodal content - extract text and images
            for part in event_content:
                if isinstance(part, TextPart):
                    text_context_parts.append(part.text)
                elif isinstance(part, ImagePart):
                    image_context_parts.append(part)

        # Build final user content
        combined_text = "\n\n".join(text_context_parts)

        if image_context_parts:
            # Multimodal: text + images
            user_content: str | list[ContentPart] = [TextPart(text=combined_text)]
            user_content.extend(image_context_parts)
        else:
            user_content = combined_text

        # In native mode, empty tool_complete events just trigger next turn
        # (tool results already added as role="tool" messages)
        if not combined_text.strip() and self._is_native_mode:
            pass  # Skip empty user message
        else:
            self.conversation.append("user", user_content)

        # Run LLM
        messages = self.conversation.to_messages()
        logger.info("Generating response...")

        assistant_content = ""

        if self._is_native_mode:
            # Native mode: pass tool schemas to API, get structured tool_calls
            tool_schemas = self._get_native_tool_schemas()
            async for chunk in self.llm.chat(
                messages, stream=True, tools=tool_schemas or None
            ):
                assistant_content += chunk
                if chunk:
                    yield TextEvent(text=chunk)

            # Extract native tool calls and build proper assistant message
            native_calls = (
                self.llm.last_tool_calls if hasattr(self.llm, "last_tool_calls") else []
            )

            if native_calls:
                # Build assistant message WITH tool_calls metadata
                tool_calls_data = []
                known_subagents = set(self.registry.list_subagents())
                for tc in native_calls:
                    tool_calls_data.append(
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": tc.arguments,
                            },
                        }
                    )
                    logger.info(
                        "Native tool call",
                        tool_name=tc.name,
                        tool_args=tc.arguments[:100],
                    )
                    if tc.name in known_subagents:
                        yield SubAgentCallEvent(
                            name=tc.name,
                            args=tc.parsed_arguments(),
                            raw=tc.arguments,
                        )
                    else:
                        # Include tool_call_id so results can be linked
                        yield ToolCallEvent(
                            name=tc.name,
                            args={
                                **tc.parsed_arguments(),
                                "_tool_call_id": tc.id,
                            },
                            raw=tc.arguments,
                        )

                # Add assistant message with tool_calls
                self.conversation.append(
                    "assistant",
                    assistant_content or None,
                    tool_calls=tool_calls_data,
                )
            else:
                # No tool calls - normal assistant message
                self.conversation.append("assistant", assistant_content)
        else:
            # Custom format mode: parse text stream for tool calls
            self._parser = self._get_parser()

            async for chunk in self.llm.chat(messages, stream=True):
                assistant_content += chunk

                # Parse chunk
                parse_events = self._parser.feed(chunk)

                for event in parse_events:
                    # Commands execute inline; yield result as CommandResultEvent
                    if isinstance(event, CommandEvent):
                        result = await self._handle_command(event)
                        if result.content:
                            assistant_content += f"\n{result.content}\n"
                            yield CommandResultEvent(
                                command=event.command, content=result.content
                            )
                        elif result.error:
                            assistant_content += f"\n[Command Error: {result.error}]\n"
                            yield CommandResultEvent(
                                command=event.command, error=result.error
                            )
                    else:
                        yield event

            # Flush parser
            for event in self._parser.flush():
                if isinstance(event, CommandEvent):
                    result = await self._handle_command(event)
                    if result.content:
                        assistant_content += f"\n{result.content}\n"
                        yield CommandResultEvent(
                            command=event.command, content=result.content
                        )
                    elif result.error:
                        assistant_content += f"\n[Command Error: {result.error}]\n"
                        yield CommandResultEvent(
                            command=event.command, error=result.error
                        )
                else:
                    yield event

        # Add assistant message to conversation (custom format only;
        # native mode already appended above with tool_calls metadata)
        if not self._is_native_mode:
            self.conversation.append("assistant", assistant_content)

    async def _handle_command(self, event: CommandEvent) -> CommandResult:
        """Handle a framework command."""
        command = self._commands.get(event.command)
        if command is None:
            logger.warning("Unknown command", command=event.command)
            return CommandResult(error=f"Unknown command: {event.command}")

        logger.info("Executing command: %s", event.command)
        result = await command.execute(event.args, self._context)
        logger.debug(
            "Command result", command=event.command, has_content=bool(result.content)
        )
        return result

    def register_job(self, status: JobStatus) -> None:
        """Register a job status (for external tracking)."""
        self.job_store.register(status)

    def get_job_status(self, job_id: str) -> JobStatus | None:
        """Get job status."""
        return self.job_store.get_status(job_id)

    def has_pending_events(self) -> bool:
        """Check if there are pending events."""
        return not self._event_queue.empty() or len(self._pending_events) > 0

    def flush(self) -> None:
        """
        Clear conversation history (keep system prompt only).

        Used in ephemeral mode after completing an interaction.
        """
        self.conversation.clear(keep_system=True)
        logger.debug("Controller flushed (ephemeral mode)")

    @property
    def is_ephemeral(self) -> bool:
        """Check if controller is in ephemeral mode."""
        return self.config.ephemeral

    async def run_loop(
        self,
        on_text: Any | None = None,
        on_tool: Any | None = None,
        on_subagent: Any | None = None,
    ) -> None:
        """
        Run continuous controller loop.

        Args:
            on_text: Callback for text events
            on_tool: Callback for tool call events
            on_subagent: Callback for sub-agent call events
        """
        while True:
            async for event in self.run_once():
                if isinstance(event, TextEvent) and on_text:
                    on_text(event.text)
                elif isinstance(event, ToolCallEvent) and on_tool:
                    await on_tool(event)
                elif isinstance(event, SubAgentCallEvent) and on_subagent:
                    await on_subagent(event)
