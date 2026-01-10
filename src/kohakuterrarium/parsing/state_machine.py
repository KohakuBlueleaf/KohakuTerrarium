"""
Streaming state machine parser for LLM output.

Parses tool calls, sub-agent calls, and commands from streaming text.
Handles partial chunks correctly (markers split across chunks).
"""

from enum import Enum, auto
from typing import Any

from kohakuterrarium.parsing.events import (
    BlockEndEvent,
    BlockStartEvent,
    CommandEvent,
    ParseEvent,
    SubAgentCallEvent,
    TextEvent,
    ToolCallEvent,
)
from kohakuterrarium.parsing.patterns import (
    ParserConfig,
    parse_command,
    parse_subagent_content,
    parse_tool_content,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class ParserState(Enum):
    """Parser state machine states."""

    NORMAL = auto()  # Normal text streaming
    MAYBE_MARKER = auto()  # Might be starting a marker
    IN_TOOL_BLOCK = auto()  # Inside ##tool## block
    IN_SUBAGENT_BLOCK = auto()  # Inside ##subagent:name## block
    IN_COMMAND = auto()  # Inside ##command## (single line)


class StreamParser:
    """
    Streaming parser for LLM output.

    Detects and parses:
    - Tool calls: ##tool##...##tool##
    - Sub-agent calls: ##subagent:name##...##subagent##
    - Commands: ##read job_id## (single line)

    Usage:
        parser = StreamParser()
        for chunk in llm_stream:
            events = parser.feed(chunk)
            for event in events:
                handle_event(event)
        # Don't forget to flush at end
        final_events = parser.flush()
    """

    # Marker that starts all special blocks
    MARKER_START = "##"
    MARKER_CHAR = "#"

    def __init__(self, config: ParserConfig | None = None):
        self.config = config or ParserConfig()
        self._reset()

    def _reset(self) -> None:
        """Reset parser state."""
        self.state = ParserState.NORMAL
        self.buffer = ""  # Current buffer
        self.text_buffer = ""  # Buffered text to emit
        self.block_content = ""  # Content inside current block
        self.block_name = ""  # Name for subagent blocks
        self.marker_buffer = ""  # Buffer for potential marker

    def feed(self, chunk: str) -> list[ParseEvent]:
        """
        Feed a chunk of text to the parser.

        Args:
            chunk: Text chunk from LLM stream

        Returns:
            List of ParseEvents detected in this chunk
        """
        events: list[ParseEvent] = []

        for char in chunk:
            new_events = self._process_char(char)
            events.extend(new_events)

        return events

    def flush(self) -> list[ParseEvent]:
        """
        Flush any remaining buffered content.

        Call this when the stream ends.

        Returns:
            List of any remaining ParseEvents
        """
        events: list[ParseEvent] = []

        # Emit any buffered marker as text (incomplete marker)
        if self.marker_buffer:
            self.text_buffer += self.marker_buffer
            self.marker_buffer = ""

        # Emit any remaining text
        if self.text_buffer:
            events.append(TextEvent(self.text_buffer))
            self.text_buffer = ""

        # Handle incomplete blocks
        if self.state in (ParserState.IN_TOOL_BLOCK, ParserState.IN_SUBAGENT_BLOCK):
            logger.warning("Stream ended with incomplete block", state=self.state.name)
            if self.config.emit_block_events:
                events.append(
                    BlockEndEvent(
                        block_type=(
                            "tool"
                            if self.state == ParserState.IN_TOOL_BLOCK
                            else "subagent"
                        ),
                        success=False,
                        error="Stream ended before block completed",
                    )
                )

        self._reset()
        return events

    def _process_char(self, char: str) -> list[ParseEvent]:
        """Process a single character."""
        events: list[ParseEvent] = []

        match self.state:
            case ParserState.NORMAL:
                events.extend(self._handle_normal(char))

            case ParserState.MAYBE_MARKER:
                events.extend(self._handle_maybe_marker(char))

            case ParserState.IN_TOOL_BLOCK:
                events.extend(self._handle_in_tool_block(char))

            case ParserState.IN_SUBAGENT_BLOCK:
                events.extend(self._handle_in_subagent_block(char))

            case ParserState.IN_COMMAND:
                events.extend(self._handle_in_command(char))

        return events

    def _handle_normal(self, char: str) -> list[ParseEvent]:
        """Handle character in NORMAL state."""
        events: list[ParseEvent] = []

        if char == self.MARKER_CHAR:
            # Might be starting a marker
            self.marker_buffer = char
            self.state = ParserState.MAYBE_MARKER
        else:
            self.text_buffer += char
            # Emit text if buffer reaches threshold
            if (
                not self.config.buffer_text
                or len(self.text_buffer) >= self.config.text_buffer_size
            ):
                events.append(TextEvent(self.text_buffer))
                self.text_buffer = ""

        return events

    def _handle_maybe_marker(self, char: str) -> list[ParseEvent]:
        """Handle character when we might be in a marker."""
        events: list[ParseEvent] = []
        self.marker_buffer += char

        # Check if we have enough to determine marker type
        if len(self.marker_buffer) >= 2:
            if self.marker_buffer == "##":
                # Confirmed marker start, now determine type
                # Keep reading until we can identify the block type
                pass
            elif not self.marker_buffer.startswith("#"):
                # False alarm, emit as text
                self.text_buffer += self.marker_buffer
                self.marker_buffer = ""
                self.state = ParserState.NORMAL

        # Check for complete markers
        if self.marker_buffer.endswith("##") and len(self.marker_buffer) > 2:
            # We have a complete marker, determine type
            events.extend(self._process_complete_marker())

        return events

    def _process_complete_marker(self) -> list[ParseEvent]:
        """Process a complete marker (##...##)."""
        events: list[ParseEvent] = []
        marker = self.marker_buffer

        # Check if it's the tool block start
        if marker == self.config.tool_pattern.start:
            self.state = ParserState.IN_TOOL_BLOCK
            self.block_content = ""
            self.marker_buffer = ""
            if self.config.emit_block_events:
                events.append(BlockStartEvent(block_type="tool"))
            logger.debug("Entered tool block")

        # Check if it's a subagent block start (##subagent:name##)
        elif marker.startswith("##subagent:") and marker.endswith("##"):
            name = marker[11:-2]  # Extract name from ##subagent:name##
            self.state = ParserState.IN_SUBAGENT_BLOCK
            self.block_content = ""
            self.block_name = name
            self.marker_buffer = ""
            if self.config.emit_block_events:
                events.append(BlockStartEvent(block_type="subagent", name=name))
            logger.debug("Entered subagent block", subagent_name=name)

        # Check if it's a simple command (##command args##)
        elif marker.startswith("##") and marker.endswith("##"):
            # Single-line command like ##read job_123##
            content = marker[2:-2]
            # Check if it looks like a command (no newlines, starts with word)
            if (
                content
                and not content.startswith("tool")
                and not content.startswith("subagent")
            ):
                command, args = parse_command(marker)
                events.append(CommandEvent(command=command, args=args, raw=marker))
                self.marker_buffer = ""
                self.state = ParserState.NORMAL
                logger.debug("Parsed command", command=command)
            else:
                # Not a recognized pattern, emit as text
                self.text_buffer += marker
                self.marker_buffer = ""
                self.state = ParserState.NORMAL
        else:
            # Not a recognized marker, continue buffering
            pass

        return events

    def _handle_in_tool_block(self, char: str) -> list[ParseEvent]:
        """Handle character inside a tool block."""
        events: list[ParseEvent] = []
        self.block_content += char

        # Check for end marker
        if self.block_content.endswith(self.config.tool_pattern.end):
            # Remove end marker from content
            content = self.block_content[: -len(self.config.tool_pattern.end)]
            # Parse tool call
            name, args = parse_tool_content(content)
            events.append(
                ToolCallEvent(
                    name=name,
                    args=args,
                    raw=self.config.tool_pattern.start
                    + content
                    + self.config.tool_pattern.end,
                )
            )
            if self.config.emit_block_events:
                events.append(BlockEndEvent(block_type="tool", success=True))
            logger.debug("Parsed tool call", tool_name=name)
            self.block_content = ""
            self.state = ParserState.NORMAL

        return events

    def _handle_in_subagent_block(self, char: str) -> list[ParseEvent]:
        """Handle character inside a subagent block."""
        events: list[ParseEvent] = []
        self.block_content += char

        # Check for end marker
        if self.block_content.endswith(self.config.subagent_pattern.end):
            # Remove end marker from content
            content = self.block_content[: -len(self.config.subagent_pattern.end)]
            # Parse subagent call
            args = parse_subagent_content(content)
            events.append(
                SubAgentCallEvent(
                    name=self.block_name,
                    args=args,
                    raw=f"##subagent:{self.block_name}##"
                    + content
                    + self.config.subagent_pattern.end,
                )
            )
            if self.config.emit_block_events:
                events.append(BlockEndEvent(block_type="subagent", success=True))
            logger.debug("Parsed subagent call", subagent_name=self.block_name)
            self.block_content = ""
            self.block_name = ""
            self.state = ParserState.NORMAL

        return events

    def _handle_in_command(self, char: str) -> list[ParseEvent]:
        """Handle character inside a command (not used in current impl)."""
        # Commands are single-line, handled in MAYBE_MARKER
        return []

    def get_state(self) -> ParserState:
        """Get current parser state."""
        return self.state

    def is_in_block(self) -> bool:
        """Check if parser is currently inside a block."""
        return self.state in (
            ParserState.IN_TOOL_BLOCK,
            ParserState.IN_SUBAGENT_BLOCK,
            ParserState.IN_COMMAND,
        )


def parse_complete(text: str, config: ParserConfig | None = None) -> list[ParseEvent]:
    """
    Parse complete text (non-streaming convenience function).

    Args:
        text: Complete text to parse
        config: Optional parser configuration

    Returns:
        List of all ParseEvents
    """
    parser = StreamParser(config)
    events = parser.feed(text)
    events.extend(parser.flush())
    return events


def extract_tool_calls(events: list[ParseEvent]) -> list[ToolCallEvent]:
    """Extract only tool call events from event list."""
    return [e for e in events if isinstance(e, ToolCallEvent)]


def extract_subagent_calls(events: list[ParseEvent]) -> list[SubAgentCallEvent]:
    """Extract only sub-agent call events from event list."""
    return [e for e in events if isinstance(e, SubAgentCallEvent)]


def extract_text(events: list[ParseEvent]) -> str:
    """Extract and join all text from events."""
    return "".join(e.text for e in events if isinstance(e, TextEvent))
