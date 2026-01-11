"""
Parsing module - Stream parsing for LLM output.

Provides state machine parser for detecting custom format tool calls
and framework commands from streaming LLM output.

Format:
    [/function_name]
    @@arg=value
    content
    [function_name/]

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
    DEFAULT_COMMANDS,
    DEFAULT_CONTENT_ARG_MAP,
    DEFAULT_SUBAGENT_TAGS,
    ParserConfig,
    is_command_tag,
    is_subagent_tag,
    is_tool_tag,
)
from kohakuterrarium.parsing.state_machine import (
    ParserState,
    StreamParser,
    parse_full,
)

__all__ = [
    # Parser
    "StreamParser",
    "ParserState",
    "parse_full",
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
    # Pattern defaults (for extending)
    "DEFAULT_COMMANDS",
    "DEFAULT_CONTENT_ARG_MAP",
    "DEFAULT_SUBAGENT_TAGS",
    "is_tool_tag",
    "is_subagent_tag",
    "is_command_tag",
]
