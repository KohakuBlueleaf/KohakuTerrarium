"""
Streaming state machine parser for LLM output.

Parses custom format tool calls and commands from streaming text.
Format:
    [/function]
    @@arg=value
    content here
    [function/]

Handles partial chunks correctly (markers split across chunks).
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
    ParserConfig,
    is_command_tag,
    is_subagent_tag,
    is_tool_tag,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class ParserState(Enum):
    """Parser state machine states."""

    NORMAL = auto()  # Normal text streaming
    MAYBE_OPEN = auto()  # Saw `[`, might be opening marker
    OPEN_SLASH = auto()  # Saw `[/`, expecting name
    IN_OPEN_NAME = auto()  # Reading function name after `[/`
    IN_BLOCK = auto()  # Inside block, reading args/content
    MAYBE_CLOSE = auto()  # Saw `[` inside block, might be closing
    IN_CLOSE_NAME = auto()  # Reading function name after `[`
    EXPECT_CLOSE_SLASH = auto()  # Expecting `/]` after close name


class StreamParser:
    """
    Streaming parser for LLM output.

    Detects and parses custom format:
    - Tool calls: [/bash]ls -la[bash/]
    - Commands: [/info]bash[info/]
    - With content:
        [/write]
        @@path=file.py
        content here
        [write/]

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
        self.name_buffer = ""  # Current function name being parsed
        self.block_buffer = ""  # Content inside current block
        self.current_name = ""  # Name of current open block
        self._last_progress_log = 0

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
        """
        events: list[ParseEvent] = []

        # Emit any buffered text
        if self.text_buffer:
            events.append(TextEvent(self.text_buffer))
            self.text_buffer = ""

        # Handle incomplete states
        if self.state == ParserState.MAYBE_OPEN:
            events.append(TextEvent("["))
        elif self.state == ParserState.OPEN_SLASH:
            events.append(TextEvent("[/"))
        elif self.state == ParserState.IN_OPEN_NAME:
            events.append(TextEvent("[/" + self.name_buffer))
        elif self.state == ParserState.IN_BLOCK:
            logger.warning(
                "Unclosed block at end of stream", block_name=self.current_name
            )
            raw = self._build_raw_open() + self.block_buffer
            events.append(TextEvent(raw))
        elif self.state == ParserState.MAYBE_CLOSE:
            self.block_buffer += "["
            raw = self._build_raw_open() + self.block_buffer
            events.append(TextEvent(raw))
        elif self.state == ParserState.IN_CLOSE_NAME:
            self.block_buffer += "[" + self.name_buffer
            raw = self._build_raw_open() + self.block_buffer
            events.append(TextEvent(raw))
        elif self.state == ParserState.EXPECT_CLOSE_SLASH:
            self.block_buffer += "[" + self.name_buffer
            raw = self._build_raw_open() + self.block_buffer
            events.append(TextEvent(raw))

        self._reset()
        return events

    def _process_char(self, char: str) -> list[ParseEvent]:
        """Process a single character."""
        events: list[ParseEvent] = []

        match self.state:
            case ParserState.NORMAL:
                events.extend(self._handle_normal(char))
            case ParserState.MAYBE_OPEN:
                events.extend(self._handle_maybe_open(char))
            case ParserState.OPEN_SLASH:
                events.extend(self._handle_open_slash(char))
            case ParserState.IN_OPEN_NAME:
                events.extend(self._handle_in_open_name(char))
            case ParserState.IN_BLOCK:
                events.extend(self._handle_in_block(char))
            case ParserState.MAYBE_CLOSE:
                events.extend(self._handle_maybe_close(char))
            case ParserState.IN_CLOSE_NAME:
                events.extend(self._handle_in_close_name(char))
            case ParserState.EXPECT_CLOSE_SLASH:
                events.extend(self._handle_expect_close_slash(char))

        return events

    def _handle_normal(self, char: str) -> list[ParseEvent]:
        """Handle character in NORMAL state."""
        events: list[ParseEvent] = []

        if char == "[":
            # Potential opening marker
            if self.text_buffer:
                events.append(TextEvent(self.text_buffer))
                self.text_buffer = ""
            self.state = ParserState.MAYBE_OPEN
        else:
            self.text_buffer += char

        return events

    def _handle_maybe_open(self, char: str) -> list[ParseEvent]:
        """Handle character after seeing `[`."""
        events: list[ParseEvent] = []

        if char == "/":
            # Got `[/` - start of opening tag
            self.state = ParserState.OPEN_SLASH
        else:
            # Not a valid opening - emit `[` as text
            self.text_buffer += "[" + char
            self.state = ParserState.NORMAL

        return events

    def _handle_open_slash(self, char: str) -> list[ParseEvent]:
        """Handle character after seeing `[/`."""
        events: list[ParseEvent] = []

        if char.isalnum() or char == "_":
            # Start of function name
            self.name_buffer = char
            self.state = ParserState.IN_OPEN_NAME
        else:
            # Not a valid tag - emit `[/` as text
            self.text_buffer += "[/" + char
            self.state = ParserState.NORMAL

        return events

    def _handle_in_open_name(self, char: str) -> list[ParseEvent]:
        """Handle character while reading opening function name."""
        events: list[ParseEvent] = []

        if char == "]":
            # End of opening marker - `[/name]`
            self.current_name = self.name_buffer
            self.name_buffer = ""
            self.block_buffer = ""
            self.state = ParserState.IN_BLOCK

            # Emit block start event
            events.append(BlockStartEvent(self.current_name))
            logger.debug("Block started", block_name=self.current_name)
        elif char.isalnum() or char == "_":
            # Continue reading name
            self.name_buffer += char
        else:
            # Invalid character - not a valid marker, emit as text
            self.text_buffer += "[/" + self.name_buffer + char
            self.name_buffer = ""
            self.state = ParserState.NORMAL

        return events

    def _handle_in_block(self, char: str) -> list[ParseEvent]:
        """Handle character inside block content."""
        events: list[ParseEvent] = []

        if char == "[":
            # Potential closing marker
            self.state = ParserState.MAYBE_CLOSE
        else:
            self.block_buffer += char

        return events

    def _handle_maybe_close(self, char: str) -> list[ParseEvent]:
        """Handle character after seeing `[` inside block."""
        events: list[ParseEvent] = []

        if char.isalnum() or char == "_":
            # Start of closing name - `[name`
            self.name_buffer = char
            self.state = ParserState.IN_CLOSE_NAME
        else:
            # Not a closing marker - add `[` and char to content
            self.block_buffer += "[" + char
            self.state = ParserState.IN_BLOCK

        return events

    def _handle_in_close_name(self, char: str) -> list[ParseEvent]:
        """Handle character while reading closing function name."""
        events: list[ParseEvent] = []

        if char == "/":
            # Got `[name/` - expecting `]` next
            self.state = ParserState.EXPECT_CLOSE_SLASH
        elif char.isalnum() or char == "_":
            # Continue reading close name
            self.name_buffer += char
        else:
            # Invalid char - not a close marker, add to content
            self.block_buffer += "[" + self.name_buffer + char
            self.name_buffer = ""
            self.state = ParserState.IN_BLOCK

        return events

    def _handle_expect_close_slash(self, char: str) -> list[ParseEvent]:
        """Handle character after seeing `[name/` - expecting `]`."""
        events: list[ParseEvent] = []

        if char == "]":
            # End of closing marker - `[name/]`
            if self.name_buffer == self.current_name:
                # Valid close - process the block
                events.extend(self._complete_block())
            else:
                # Mismatched close - treat as content
                logger.warning(
                    "Mismatched close marker",
                    expected=self.current_name,
                    got=self.name_buffer,
                )
                self.block_buffer += "[" + self.name_buffer + "/]"
                self.name_buffer = ""
                self.state = ParserState.IN_BLOCK
        else:
            # Invalid - not a proper close, add to content
            self.block_buffer += "[" + self.name_buffer + "/" + char
            self.name_buffer = ""
            self.state = ParserState.IN_BLOCK

        return events

    def _complete_block(self) -> list[ParseEvent]:
        """Process a completed block and return appropriate events."""
        events: list[ParseEvent] = []
        name = self.current_name
        content = self.block_buffer

        # Parse args and content from block
        args, body = self._parse_block_content(content)

        # Build raw representation
        raw = self._build_raw(name, args, body)

        # Determine block type and create event
        if is_tool_tag(name, self.config.known_tools):
            # Tool call
            tool_args = {**args}
            if body:
                # Map body to appropriate arg based on tool
                content_arg = self.config.content_arg_map.get(name, "content")
                tool_args[content_arg] = body
            events.append(ToolCallEvent(name=name, args=tool_args, raw=raw))
            logger.debug("Parsed tool call", tool_name=name)

        elif is_subagent_tag(name, self.config.known_subagents):
            # Sub-agent call
            subagent_args = {"task": body.strip(), **args}
            events.append(SubAgentCallEvent(name=name, args=subagent_args, raw=raw))
            logger.debug("Parsed sub-agent call", subagent_type=name)

        elif is_command_tag(name, self.config.known_commands):
            # Framework command
            cmd_args = body.strip()
            events.append(CommandEvent(command=name, args=cmd_args, raw=raw))
            logger.debug("Parsed command", command=name)

        else:
            # Unknown block type - emit as text
            logger.warning("Unknown block type", block_name=name)
            events.append(TextEvent(raw))

        # Emit block end event
        events.append(BlockEndEvent(name))

        # Reset state
        self.current_name = ""
        self.name_buffer = ""
        self.block_buffer = ""
        self.state = ParserState.NORMAL

        return events

    def _parse_block_content(self, content: str) -> tuple[dict[str, str], str]:
        """
        Parse block content into args and body.

        Args start with @@ on their own line.
        Everything else is body.

        Returns:
            (args_dict, body_string)
        """
        args: dict[str, str] = {}
        body_lines: list[str] = []
        in_args = True

        for line in content.split("\n"):
            # Skip empty lines while still in args section
            if in_args and line.strip() == "":
                continue
            if in_args and line.startswith("@@"):
                # Parse arg: @@key=value
                arg_content = line[2:]  # Remove @@
                if "=" in arg_content:
                    key, value = arg_content.split("=", 1)
                    args[key.strip()] = value.strip()
                else:
                    # Arg without value
                    args[arg_content.strip()] = ""
            else:
                # Once we hit a non-arg line, everything is body
                in_args = False
                body_lines.append(line)

        body = "\n".join(body_lines).strip()
        return args, body

    def _build_raw_open(self) -> str:
        """Build raw opening marker."""
        return f"[/{self.current_name}]\n"

    def _build_raw(self, name: str, args: dict[str, str], body: str) -> str:
        """Build raw representation of block."""
        parts = [f"[/{name}]"]
        for key, value in args.items():
            parts.append(f"@@{key}={value}")
        if body:
            parts.append(body)
        parts.append(f"[{name}/]")
        return "\n".join(parts)


# Convenience function for non-streaming parsing
def parse_full(text: str, config: ParserConfig | None = None) -> list[ParseEvent]:
    """
    Parse a complete text (non-streaming).

    Args:
        text: Full text to parse
        config: Parser configuration

    Returns:
        List of all ParseEvents
    """
    parser = StreamParser(config)
    events = parser.feed(text)
    events.extend(parser.flush())
    return events
