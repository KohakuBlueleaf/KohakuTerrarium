"""
Output router - routes parse events to appropriate output modules.

Uses a simple state machine to handle different output modes.
"""

from enum import Enum, auto
from typing import Any

from kohakuterrarium.modules.output.base import OutputModule
from kohakuterrarium.parsing import (
    BlockEndEvent,
    BlockStartEvent,
    CommandEvent,
    OutputEvent,
    ParseEvent,
    SubAgentCallEvent,
    TextEvent,
    ToolCallEvent,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class OutputState(Enum):
    """Output routing state."""

    NORMAL = auto()  # Regular text output (stdout)
    TOOL_BLOCK = auto()  # Inside tool call block (suppress output)
    SUBAGENT_BLOCK = auto()  # Inside sub-agent block (suppress output)
    COMMAND_BLOCK = auto()  # Inside command block
    OUTPUT_BLOCK = auto()  # Inside explicit output block


class OutputRouter:
    """
    Routes parse events to appropriate output modules.

    Handles:
    - Text events → default output module (stdout)
    - OutputEvent → named output module (e.g., discord, tts)
    - Tool/subagent events → suppress text, emit event for handling
    - Commands → process inline
    """

    def __init__(
        self,
        default_output: OutputModule,
        *,
        named_outputs: dict[str, OutputModule] | None = None,
        suppress_tool_blocks: bool = True,
        suppress_subagent_blocks: bool = True,
    ):
        """
        Initialize output router.

        Args:
            default_output: Default output module for text (stdout)
            named_outputs: Named output modules (e.g., {"discord": DiscordOutput})
            suppress_tool_blocks: Don't output text inside tool blocks
            suppress_subagent_blocks: Don't output text inside subagent blocks
        """
        self.default_output = default_output
        self.named_outputs = named_outputs or {}
        self.suppress_tool_blocks = suppress_tool_blocks
        self.suppress_subagent_blocks = suppress_subagent_blocks

        self._state = OutputState.NORMAL
        self._pending_tool_calls: list[ToolCallEvent] = []
        self._pending_subagent_calls: list[SubAgentCallEvent] = []
        self._pending_commands: list[CommandEvent] = []
        self._pending_outputs: list[OutputEvent] = []

    @property
    def state(self) -> OutputState:
        """Current output state."""
        return self._state

    @property
    def pending_tool_calls(self) -> list[ToolCallEvent]:
        """Get and clear pending tool calls."""
        calls = self._pending_tool_calls
        self._pending_tool_calls = []
        return calls

    @property
    def pending_subagent_calls(self) -> list[SubAgentCallEvent]:
        """Get and clear pending sub-agent calls."""
        calls = self._pending_subagent_calls
        self._pending_subagent_calls = []
        return calls

    @property
    def pending_commands(self) -> list[CommandEvent]:
        """Get and clear pending commands."""
        commands = self._pending_commands
        self._pending_commands = []
        return commands

    @property
    def pending_outputs(self) -> list[OutputEvent]:
        """Get and clear pending output events."""
        outputs = self._pending_outputs
        self._pending_outputs = []
        return outputs

    def get_output_targets(self) -> list[str]:
        """Get list of registered output target names."""
        return list(self.named_outputs.keys())

    async def start(self) -> None:
        """Start the router and output modules."""
        await self.default_output.start()
        for name, output in self.named_outputs.items():
            await output.start()
            logger.debug("Named output started", output_name=name)
        logger.debug("Output router started")

    async def stop(self) -> None:
        """Stop the router and output modules."""
        for name, output in self.named_outputs.items():
            await output.stop()
            logger.debug("Named output stopped", output_name=name)
        await self.default_output.stop()
        logger.debug("Output router stopped")

    async def route(self, event: ParseEvent) -> None:
        """
        Route a parse event to appropriate handler.

        Args:
            event: Parse event to route
        """
        match event:
            case TextEvent(text=text):
                await self._handle_text(text)

            case ToolCallEvent():
                self._pending_tool_calls.append(event)
                logger.debug("Tool call queued", tool_name=event.name)

            case SubAgentCallEvent():
                self._pending_subagent_calls.append(event)
                logger.debug("Sub-agent call queued", subagent_name=event.name)

            case CommandEvent():
                self._pending_commands.append(event)
                logger.debug("Command queued", command=event.command)

            case OutputEvent():
                # Route to named output immediately
                await self._handle_output(event)

            case BlockStartEvent(block_type=block_type):
                self._handle_block_start(block_type)

            case BlockEndEvent(block_type=block_type):
                self._handle_block_end(block_type)

    async def _handle_text(self, text: str) -> None:
        """Handle text event based on current state."""
        match self._state:
            case OutputState.NORMAL:
                # Default output (stdout) - for model "thinking"
                await self.default_output.write_stream(text)

            case OutputState.TOOL_BLOCK:
                if not self.suppress_tool_blocks:
                    await self.default_output.write_stream(text)

            case OutputState.SUBAGENT_BLOCK:
                if not self.suppress_subagent_blocks:
                    await self.default_output.write_stream(text)

            case OutputState.COMMAND_BLOCK:
                # Commands are typically suppressed
                pass

            case OutputState.OUTPUT_BLOCK:
                # Output blocks are handled via OutputEvent, suppress streaming
                pass

    async def _handle_output(self, event: OutputEvent) -> None:
        """
        Handle explicit output event.

        Routes to named output module if registered.
        """
        target = event.target
        content = event.content

        if target in self.named_outputs:
            output_module = self.named_outputs[target]
            await output_module.write(content)
            logger.debug(
                "Output sent to target", target=target, content_len=len(content)
            )
        else:
            # Unknown target - log warning, optionally send to default
            logger.warning(
                "Unknown output target, sending to default",
                target=target,
                available=list(self.named_outputs.keys()),
            )
            await self.default_output.write(f"[output_{target}] {content}")

    def _handle_block_start(self, block_type: str) -> None:
        """Handle block start event."""
        # Check for output block first (format: output_<target>)
        if block_type.startswith("output_"):
            self._state = OutputState.OUTPUT_BLOCK
            return

        match block_type:
            case "tool":
                self._state = OutputState.TOOL_BLOCK
            case "subagent":
                self._state = OutputState.SUBAGENT_BLOCK
            case "command":
                self._state = OutputState.COMMAND_BLOCK

    def _handle_block_end(self, block_type: str) -> None:
        """Handle block end event."""
        self._state = OutputState.NORMAL

    async def flush(self) -> None:
        """Flush output modules."""
        await self.default_output.flush()
        for output in self.named_outputs.values():
            await output.flush()

    async def on_processing_start(self) -> None:
        """Notify output modules that processing is starting."""
        # Call on named outputs (they might want to show typing indicators)
        for output in self.named_outputs.values():
            if hasattr(output, "on_processing_start"):
                await output.on_processing_start()

    async def on_processing_end(self) -> None:
        """Notify output modules that processing has ended."""
        for output in self.named_outputs.values():
            if hasattr(output, "on_processing_end"):
                await output.on_processing_end()

    def reset(self) -> None:
        """Reset router state for new turn."""
        self._state = OutputState.NORMAL
        self._pending_tool_calls.clear()
        self._pending_subagent_calls.clear()
        self._pending_commands.clear()
        self._pending_outputs.clear()


class MultiOutputRouter(OutputRouter):
    """
    Router that can route to multiple output modules.

    Different content types can go to different destinations.
    """

    def __init__(
        self,
        default_output: OutputModule,
        outputs: dict[str, OutputModule] | None = None,
        **kwargs: Any,
    ):
        """
        Initialize multi-output router.

        Args:
            default_output: Default output module
            outputs: Named output modules for specific content types
            **kwargs: Additional arguments for base router
        """
        super().__init__(default_output, **kwargs)
        self.outputs = outputs or {}

    async def start(self) -> None:
        """Start all output modules."""
        await super().start()
        for output in self.outputs.values():
            await output.start()

    async def stop(self) -> None:
        """Stop all output modules."""
        for output in self.outputs.values():
            await output.stop()
        await super().stop()

    async def write_to(self, name: str, content: str) -> None:
        """
        Write to a specific named output.

        Args:
            name: Output module name
            content: Content to write
        """
        if name in self.outputs:
            await self.outputs[name].write(content)
        else:
            logger.warning("Unknown output module", output_name=name)

    async def flush(self) -> None:
        """Flush all output modules."""
        await super().flush()
        for output in self.outputs.values():
            await output.flush()
