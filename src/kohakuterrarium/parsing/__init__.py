"""
Parsing module - Stream parsing for LLM output.

Provides state machine parser for detecting tool calls, sub-agent calls,
and framework commands from streaming LLM output.

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
    BlockPattern,
    ParserConfig,
    parse_command,
    parse_tool_content,
    parse_yaml_like,
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
    "BlockPattern",
    # Utilities
    "parse_yaml_like",
    "parse_tool_content",
    "parse_command",
    "extract_tool_calls",
    "extract_subagent_calls",
    "extract_text",
]
