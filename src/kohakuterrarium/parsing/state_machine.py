"""
Streaming state machine parser for LLM output.

Parses XML-style tool calls and commands from streaming text.
Format: <tool_name attr="value">content</tool_name>

Handles partial chunks correctly (tags split across chunks).
"""

from enum import Enum, auto

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
    KNOWN_COMMANDS,
    KNOWN_SUBAGENTS,
    KNOWN_TOOLS,
    ParserConfig,
    build_tool_args,
    is_command_tag,
    is_subagent_tag,
    is_tool_tag,
    parse_closing_tag,
    parse_opening_tag,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class ParserState(Enum):
    """Parser state machine states."""

    NORMAL = auto()  # Normal text streaming
    IN_OPENING_TAG = auto()  # Inside < ... > (buffering tag)
    IN_CONTENT = auto()  # Inside tag content, waiting for </tag>
    IN_CLOSING_TAG = auto()  # Inside </ ... > (buffering closing tag)


class StreamParser:
    """
    Streaming parser for LLM output.

    Detects and parses XML-style:
    - Tool calls: <bash>command</bash>, <edit path="file">diff</edit>
    - Commands: <info>tool_name</info>, <read_job>job_id</read_job>
    - Self-closing: <read path="file.py"/>

    Usage:
        parser = StreamParser()
        for chunk in llm_stream:
            events = parser.feed(chunk)
            for event in events:
                handle_event(event)
        # Don't forget to flush at end
        final_events = parser.flush()
    """

    def __init__(self, config: ParserConfig | None = None):
        self.config = config or ParserConfig()
        self._reset()

    def _reset(self) -> None:
        """Reset parser state."""
        self.state = ParserState.NORMAL
        self.text_buffer = ""  # Buffered text to emit
        self.tag_buffer = ""  # Current tag being parsed
        self.content_buffer = ""  # Content inside current tag
        self.current_tag_name = ""  # Name of current open tag
        self.current_tag_attrs: dict[str, str] = {}  # Attributes of current tag
        self._last_progress_log = 0  # For progress logging

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

        # Handle incomplete states
        if self.state == ParserState.IN_OPENING_TAG:
            # Incomplete tag, emit as text
            self.text_buffer += "<" + self.tag_buffer
            self.tag_buffer = ""

        elif self.state == ParserState.IN_CONTENT:
            # Stream ended inside a tag
            logger.warning(
                "Stream ended with incomplete tag",
                tag_name=self.current_tag_name,
            )
            if self.config.emit_block_events:
                events.append(
                    BlockEndEvent(
                        block_type="tool",
                        success=False,
                        error="Stream ended before tag closed",
                    )
                )

        elif self.state == ParserState.IN_CLOSING_TAG:
            # Incomplete closing tag, treat content + partial close as text
            self.text_buffer += self.content_buffer + "</" + self.tag_buffer
            self.tag_buffer = ""
            self.content_buffer = ""

        # Emit any remaining text
        if self.text_buffer:
            events.append(TextEvent(self.text_buffer))
            self.text_buffer = ""

        self._reset()
        return events

    def _process_char(self, char: str) -> list[ParseEvent]:
        """Process a single character."""
        match self.state:
            case ParserState.NORMAL:
                return self._handle_normal(char)
            case ParserState.IN_OPENING_TAG:
                return self._handle_in_opening_tag(char)
            case ParserState.IN_CONTENT:
                return self._handle_in_content(char)
            case ParserState.IN_CLOSING_TAG:
                return self._handle_in_closing_tag(char)
        return []

    def _handle_normal(self, char: str) -> list[ParseEvent]:
        """Handle character in NORMAL state."""
        events: list[ParseEvent] = []

        if char == "<":
            # Might be starting a tag
            self.tag_buffer = ""
            self.state = ParserState.IN_OPENING_TAG
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

    def _handle_in_opening_tag(self, char: str) -> list[ParseEvent]:
        """Handle character while parsing an opening tag."""
        events: list[ParseEvent] = []

        if char == ">":
            # Tag complete, parse it
            full_tag = "<" + self.tag_buffer + ">"
            parsed = parse_opening_tag(full_tag)

            if parsed:
                tag_name, attrs, is_self_closing = parsed

                # Check if it's a known tool, sub-agent, or command
                if (
                    is_tool_tag(tag_name)
                    or is_subagent_tag(tag_name)
                    or is_command_tag(tag_name)
                ):
                    if is_self_closing:
                        # Self-closing tag, emit immediately
                        events.extend(self._emit_tag_event(tag_name, attrs, ""))
                        self.state = ParserState.NORMAL
                    else:
                        # Need to collect content until closing tag
                        self.current_tag_name = tag_name
                        self.current_tag_attrs = attrs
                        self.content_buffer = ""
                        self._last_progress_log = 0  # Reset progress counter
                        self.state = ParserState.IN_CONTENT
                        if self.config.emit_block_events:
                            events.append(BlockStartEvent(block_type="tool"))
                        logger.debug("Entered tag", tag_name=tag_name)
                else:
                    # Not a known tag, emit as text
                    self.text_buffer += full_tag
                    self.state = ParserState.NORMAL
            else:
                # Invalid tag format, emit as text
                self.text_buffer += full_tag
                self.state = ParserState.NORMAL

            self.tag_buffer = ""

        elif char == "<":
            # Another < before > - previous was not a tag
            self.text_buffer += "<" + self.tag_buffer
            self.tag_buffer = ""
            # Stay in IN_OPENING_TAG for this new <

        else:
            self.tag_buffer += char

            # Safety: if tag buffer gets too long, it's not a real tag
            if len(self.tag_buffer) > 200:
                self.text_buffer += "<" + self.tag_buffer
                self.tag_buffer = ""
                self.state = ParserState.NORMAL

        return events

    def _handle_in_content(self, char: str) -> list[ParseEvent]:
        """Handle character while inside tag content."""
        events: list[ParseEvent] = []
        self.content_buffer += char

        # Log progress periodically (every 500 chars)
        current_len = len(self.content_buffer)
        if current_len - self._last_progress_log >= 500:
            logger.debug(
                "Buffering tool content",
                tag_name=self.current_tag_name,
                chars=current_len,
            )
            self._last_progress_log = current_len

        # Check if we're starting a closing tag
        if self.content_buffer.endswith("</"):
            # Might be closing tag, switch to closing tag state
            # Remove </ from content buffer
            self.content_buffer = self.content_buffer[:-2]
            self.tag_buffer = ""
            self.state = ParserState.IN_CLOSING_TAG

        return events

    def _handle_in_closing_tag(self, char: str) -> list[ParseEvent]:
        """Handle character while parsing a closing tag."""
        events: list[ParseEvent] = []

        if char == ">":
            # Closing tag complete
            closing_name = self.tag_buffer

            if closing_name == self.current_tag_name:
                # Matching close, emit the tool/command
                events.extend(
                    self._emit_tag_event(
                        self.current_tag_name,
                        self.current_tag_attrs,
                        self.content_buffer,
                    )
                )
                if self.config.emit_block_events:
                    events.append(BlockEndEvent(block_type="tool", success=True))
                logger.debug("Closed tag", tag_name=self.current_tag_name)

                self.current_tag_name = ""
                self.current_tag_attrs = {}
                self.content_buffer = ""
                self.state = ParserState.NORMAL
            else:
                # Not matching, put back as content
                self.content_buffer += "</" + self.tag_buffer + ">"
                self.state = ParserState.IN_CONTENT

            self.tag_buffer = ""

        elif char == "<":
            # Another < inside closing tag - malformed, treat as content
            self.content_buffer += "</" + self.tag_buffer
            self.tag_buffer = ""
            self.state = ParserState.IN_OPENING_TAG

        else:
            self.tag_buffer += char

            # Safety: closing tag name shouldn't be too long
            if len(self.tag_buffer) > 50:
                self.content_buffer += "</" + self.tag_buffer
                self.tag_buffer = ""
                self.state = ParserState.IN_CONTENT

        return events

    def _emit_tag_event(
        self,
        tag_name: str,
        attrs: dict[str, str],
        content: str,
    ) -> list[ParseEvent]:
        """Create appropriate event for a completed tag."""
        events: list[ParseEvent] = []

        # Build args from attributes and content
        args = build_tool_args(tag_name, attrs, content)

        if is_tool_tag(tag_name):
            # Tool call
            raw = self._build_raw_tag(tag_name, attrs, content)
            events.append(ToolCallEvent(name=tag_name, args=args, raw=raw))
            logger.debug("Parsed tool call", tool_name=tag_name)

        elif is_subagent_tag(tag_name):
            # Sub-agent call: <agent type="explore">task</agent>
            subagent_type = attrs.get("type", "explore")
            subagent_args = {
                "task": content.strip(),
                **{k: v for k, v in attrs.items() if k != "type"},
            }
            raw = self._build_raw_tag(tag_name, attrs, content)
            events.append(
                SubAgentCallEvent(name=subagent_type, args=subagent_args, raw=raw)
            )
            logger.debug("Parsed sub-agent call", subagent_type=subagent_type)

        elif is_command_tag(tag_name):
            # Framework command
            if tag_name == "info":
                cmd_name = "info"
                cmd_args = args.get("tool_name", content.strip())
            elif tag_name == "read_job":
                cmd_name = "read"
                cmd_args = args.get("job_id", content.strip())
            else:
                cmd_name = tag_name
                cmd_args = content.strip()

            raw = self._build_raw_tag(tag_name, attrs, content)
            events.append(CommandEvent(command=cmd_name, args=cmd_args, raw=raw))
            logger.debug("Parsed command", command=cmd_name)

        return events

    def _build_raw_tag(
        self,
        tag_name: str,
        attrs: dict[str, str],
        content: str,
    ) -> str:
        """Reconstruct the raw tag string."""
        attr_str = "".join(f' {k}="{v}"' for k, v in attrs.items())
        if content:
            return f"<{tag_name}{attr_str}>{content}</{tag_name}>"
        else:
            return f"<{tag_name}{attr_str}/>"

    def get_state(self) -> ParserState:
        """Get current parser state."""
        return self.state

    def is_in_block(self) -> bool:
        """Check if parser is currently inside a block."""
        return self.state in (ParserState.IN_CONTENT, ParserState.IN_CLOSING_TAG)


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
