"""
Phase 2 Unit Tests - Stream Parsing

Tests for:
- ParseEvent types
- XML-style tag parsing
- StreamParser state machine
- Tool, sub-agent, and command detection

These tests run offline without API keys.
"""

import pytest

from kohakuterrarium.parsing import (
    CommandEvent,
    ParserConfig,
    ParserState,
    StreamParser,
    SubAgentCallEvent,
    TextEvent,
    ToolCallEvent,
    extract_subagent_calls,
    extract_text,
    extract_tool_calls,
    is_action_event,
    is_text_event,
    parse_complete,
    parse_opening_tag,
    parse_closing_tag,
    parse_attributes,
    build_tool_args,
    is_tool_tag,
    is_command_tag,
    KNOWN_TOOLS,
    KNOWN_COMMANDS,
)


class TestParseEvents:
    """Tests for ParseEvent types."""

    def test_text_event(self):
        """Test TextEvent creation."""
        event = TextEvent("hello")
        assert event.text == "hello"
        assert bool(event) is True

        empty = TextEvent("")
        assert bool(empty) is False

    def test_tool_call_event(self):
        """Test ToolCallEvent creation."""
        event = ToolCallEvent(name="bash", args={"command": "ls"})
        assert event.name == "bash"
        assert event.args["command"] == "ls"

    def test_subagent_call_event(self):
        """Test SubAgentCallEvent creation."""
        event = SubAgentCallEvent(name="explore", args={"query": "test"})
        assert event.name == "explore"
        assert event.args["query"] == "test"

    def test_command_event(self):
        """Test CommandEvent creation."""
        event = CommandEvent(command="info", args="bash")
        assert event.command == "info"
        assert "bash" in event.args

    def test_is_action_event(self):
        """Test is_action_event helper."""
        assert is_action_event(ToolCallEvent("test", {}))
        assert is_action_event(SubAgentCallEvent("test", {}))
        assert is_action_event(CommandEvent("test"))
        assert not is_action_event(TextEvent("hello"))

    def test_is_text_event(self):
        """Test is_text_event helper."""
        assert is_text_event(TextEvent("hello"))
        assert not is_text_event(ToolCallEvent("test", {}))


class TestXMLParsing:
    """Tests for XML-style tag parsing."""

    def test_parse_opening_tag(self):
        """Test parsing opening tags."""
        tag, attrs, self_closing = parse_opening_tag("<bash>")
        assert tag == "bash"
        assert attrs == {}
        assert self_closing is False

    def test_parse_opening_tag_with_attrs(self):
        """Test parsing opening tags with attributes."""
        tag, attrs, self_closing = parse_opening_tag('<read path="test.py"/>')
        assert tag == "read"
        assert attrs["path"] == "test.py"
        assert self_closing is True

    def test_parse_opening_tag_multi_attrs(self):
        """Test parsing opening tags with multiple attributes."""
        tag, attrs, self_closing = parse_opening_tag(
            '<grep path="src/" glob="*.py">pattern</grep>'
        )
        assert tag == "grep"
        assert attrs["path"] == "src/"
        assert attrs["glob"] == "*.py"

    def test_parse_closing_tag(self):
        """Test parsing closing tags."""
        tag = parse_closing_tag("</bash>")
        assert tag == "bash"

        tag = parse_closing_tag("</read>")
        assert tag == "read"

    def test_parse_attributes(self):
        """Test attribute parsing."""
        attrs = parse_attributes('path="test.py" limit="10"')
        assert attrs["path"] == "test.py"
        assert attrs["limit"] == "10"

    def test_is_tool_tag(self):
        """Test tool tag detection."""
        assert is_tool_tag("bash")
        assert is_tool_tag("python")
        assert is_tool_tag("read")
        assert not is_tool_tag("unknown")

    def test_is_command_tag(self):
        """Test command tag detection."""
        assert is_command_tag("info")
        assert is_command_tag("read_job")
        assert not is_command_tag("bash")

    def test_build_tool_args_bash(self):
        """Test building args for bash tool."""
        args = build_tool_args("bash", {}, "ls -la")
        assert args["command"] == "ls -la"

    def test_build_tool_args_read(self):
        """Test building args for read tool."""
        args = build_tool_args("read", {"path": "test.py"}, "")
        assert args["path"] == "test.py"

    def test_build_tool_args_write(self):
        """Test building args for write tool."""
        args = build_tool_args("write", {"path": "test.py"}, "content here")
        assert args["path"] == "test.py"
        assert args["content"] == "content here"


class TestStreamParser:
    """Tests for StreamParser."""

    def test_empty_input(self):
        """Test parser with empty input."""
        parser = StreamParser()
        events = parser.feed("")
        events.extend(parser.flush())
        assert len(events) == 0

    def test_text_only(self):
        """Test parser with text only (no blocks)."""
        parser = StreamParser()
        events = parser.feed("Hello world!")
        events.extend(parser.flush())

        text = extract_text(events)
        assert "Hello world!" in text

    def test_single_tool_call(self):
        """Test parsing a single tool call."""
        text = """Some text before.

<bash>ls -la</bash>

Some text after."""

        events = parse_complete(text)
        tools = extract_tool_calls(events)

        assert len(tools) == 1
        assert tools[0].name == "bash"
        assert tools[0].args.get("command") == "ls -la"

    def test_tool_with_attributes(self):
        """Test parsing tool call with attributes."""
        text = '<read path="src/main.py"/>'

        events = parse_complete(text)
        tools = extract_tool_calls(events)

        assert len(tools) == 1
        assert tools[0].name == "read"
        assert tools[0].args.get("path") == "src/main.py"

    def test_tool_with_attrs_and_content(self):
        """Test parsing tool with both attributes and content."""
        text = """<write path="test.py">
def hello():
    print("Hello")
</write>"""

        events = parse_complete(text)
        tools = extract_tool_calls(events)

        assert len(tools) == 1
        assert tools[0].name == "write"
        assert tools[0].args.get("path") == "test.py"
        assert "def hello" in tools[0].args.get("content", "")

    def test_multiple_tool_calls(self):
        """Test parsing multiple tool calls."""
        text = """<bash>ls</bash>

<bash>pwd</bash>"""

        events = parse_complete(text)
        tools = extract_tool_calls(events)

        assert len(tools) == 2
        assert tools[0].args.get("command") == "ls"
        assert tools[1].args.get("command") == "pwd"

    def test_command(self):
        """Test parsing framework command."""
        text = "Check this: <info>bash</info>"

        events = parse_complete(text)
        commands = [e for e in events if isinstance(e, CommandEvent)]

        assert len(commands) == 1
        assert commands[0].command == "info"
        assert "bash" in commands[0].args

    def test_streaming_chunks(self):
        """Test that streaming works correctly."""
        parser = StreamParser()

        # Feed in small chunks
        chunks = ["<ba", "sh>l", "s -la</bash>"]

        all_events = []
        for chunk in chunks:
            events = parser.feed(chunk)
            all_events.extend(events)
        all_events.extend(parser.flush())

        tools = extract_tool_calls(all_events)
        assert len(tools) == 1
        assert tools[0].args.get("command") == "ls -la"

    def test_character_by_character(self):
        """Test feeding character by character."""
        text = "<bash>test</bash>"
        parser = StreamParser()

        all_events = []
        for char in text:
            events = parser.feed(char)
            all_events.extend(events)
        all_events.extend(parser.flush())

        tools = extract_tool_calls(all_events)
        assert len(tools) == 1

    def test_parser_state(self):
        """Test parser state tracking."""
        parser = StreamParser()

        assert parser.get_state() == ParserState.NORMAL
        assert not parser.is_in_block()

        parser.feed("<bash>")
        assert parser.is_in_block()

        parser.feed("test</bash>")
        parser.flush()
        assert parser.get_state() == ParserState.NORMAL

    def test_incomplete_block(self):
        """Test handling of incomplete block at stream end."""
        parser = StreamParser()

        events = parser.feed("<bash>test")
        # No tool event yet (block not closed)
        tools = extract_tool_calls(events)
        assert len(tools) == 0

        # Flush should handle incomplete block
        final_events = parser.flush()
        # Still no tool event (incomplete)
        tools = extract_tool_calls(final_events)
        assert len(tools) == 0

    def test_false_marker(self):
        """Test that false markers are handled as text."""
        text = "Use < for less than and > for greater than"

        events = parse_complete(text)
        text_content = extract_text(events)

        assert "<" in text_content or ">" in text_content

    def test_mixed_content(self):
        """Test response with various content types."""
        text = """Text before

<bash>ls</bash>

<info>bash</info>

Text after"""

        events = parse_complete(text)

        tools = extract_tool_calls(events)
        commands = [e for e in events if isinstance(e, CommandEvent)]

        assert len(tools) == 1
        assert len(commands) == 1


class TestParserConfig:
    """Tests for ParserConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = ParserConfig()
        assert config.emit_block_events is False

    def test_custom_config(self):
        """Test custom configuration."""
        config = ParserConfig(
            emit_block_events=True,
            buffer_text=False,
        )
        assert config.emit_block_events is True
        assert config.buffer_text is False


class TestExtractFunctions:
    """Tests for extraction helper functions."""

    def test_extract_tool_calls(self):
        """Test extract_tool_calls function."""
        events = [
            TextEvent("hello"),
            ToolCallEvent("tool1", {}),
            TextEvent("world"),
            ToolCallEvent("tool2", {}),
        ]

        tools = extract_tool_calls(events)
        assert len(tools) == 2
        assert tools[0].name == "tool1"
        assert tools[1].name == "tool2"

    def test_extract_subagent_calls(self):
        """Test extract_subagent_calls function."""
        events = [
            TextEvent("hello"),
            SubAgentCallEvent("agent1", {}),
        ]

        subagents = extract_subagent_calls(events)
        assert len(subagents) == 1
        assert subagents[0].name == "agent1"

    def test_extract_text(self):
        """Test extract_text function."""
        events = [
            TextEvent("Hello "),
            ToolCallEvent("tool", {}),
            TextEvent("World"),
        ]

        text = extract_text(events)
        assert text == "Hello World"


class TestKnownTags:
    """Tests for known tool and command tags."""

    def test_known_tools(self):
        """Test that all expected tools are in KNOWN_TOOLS."""
        expected = {"bash", "python", "read", "write", "edit", "glob", "grep"}
        assert expected.issubset(KNOWN_TOOLS)

    def test_known_commands(self):
        """Test that all expected commands are in KNOWN_COMMANDS."""
        expected = {"info", "read_job"}
        assert expected.issubset(KNOWN_COMMANDS)
