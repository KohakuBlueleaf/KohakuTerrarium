"""
Parsing module - Stream parsing for LLM output.

Provides state machine parser for detecting XML-style tool calls
and framework commands from streaming LLM output.

Format: <tool_name attr="value">content</tool_name>

Exports:
- StreamParser: Main streaming parser
- ParseEvent types: TextEvent, ToolCallEvent, SubAgentCallEvent, CommandEvent
- ParserConfig: Parser configuration
"""

from kohakuterrarium.parsing.events import (
    BlockEndEvent,
    BlockStartEvent,
    CommandEvent,
    ParseEvent,
    SubAgentCallEvent,
    TextEvent,
    ToolCallEvent,
    is_action_event,
    is_text_event,
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
    parse_attributes,
    parse_closing_tag,
    parse_opening_tag,
)
from kohakuterrarium.parsing.state_machine import (
    ParserState,
    StreamParser,
    extract_subagent_calls,
    extract_text,
    extract_tool_calls,
    parse_complete,
)

__all__ = [
    # Parser
    "StreamParser",
    "ParserState",
    "parse_complete",
    # Events
    "ParseEvent",
    "TextEvent",
    "ToolCallEvent",
    "SubAgentCallEvent",
    "CommandEvent",
    "BlockStartEvent",
    "BlockEndEvent",
    "is_action_event",
    "is_text_event",
    # Config
    "ParserConfig",
    # Pattern utilities
    "KNOWN_TOOLS",
    "KNOWN_SUBAGENTS",
    "KNOWN_COMMANDS",
    "is_tool_tag",
    "is_subagent_tag",
    "is_command_tag",
    "parse_opening_tag",
    "parse_closing_tag",
    "parse_attributes",
    "build_tool_args",
    # Extract utilities
    "extract_tool_calls",
    "extract_subagent_calls",
    "extract_text",
]
