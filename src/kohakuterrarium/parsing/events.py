"""
Parse events emitted by the stream parser.

These events represent parsed segments from LLM output:
- TextEvent: Regular text content
- ToolCallEvent: Tool call block
- SubAgentCallEvent: Sub-agent call block
- CommandEvent: Framework command (##read##, ##info##)
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextEvent:
    """
    Regular text content from LLM output.

    Emitted for text outside of any special blocks.
    """

    text: str

    def __bool__(self) -> bool:
        return bool(self.text)


@dataclass
class ToolCallEvent:
    """
    Tool call detected in LLM output.

    Attributes:
        name: Tool name
        args: Parsed arguments (dict)
        raw: Raw content of the tool block
    """

    name: str
    args: dict[str, Any] = field(default_factory=dict)
    raw: str = ""

    def __repr__(self) -> str:
        return f"ToolCallEvent(name={self.name!r}, args={self.args})"


@dataclass
class SubAgentCallEvent:
    """
    Sub-agent call detected in LLM output.

    Attributes:
        name: Sub-agent name
        args: Parsed arguments (dict)
        raw: Raw content of the sub-agent block
    """

    name: str
    args: dict[str, Any] = field(default_factory=dict)
    raw: str = ""

    def __repr__(self) -> str:
        return f"SubAgentCallEvent(name={self.name!r}, args={self.args})"


@dataclass
class CommandEvent:
    """
    Framework command detected in LLM output.

    Commands like ##read job_id## or ##info tool_name##.

    Attributes:
        command: Command name (read, info, etc.)
        args: Command arguments as string
        raw: Raw content of the command
    """

    command: str
    args: str = ""
    raw: str = ""

    def __repr__(self) -> str:
        return f"CommandEvent(command={self.command!r}, args={self.args!r})"


@dataclass
class BlockStartEvent:
    """
    Signals the start of a block (tool, subagent, etc.).

    Used for early resource allocation before block completes.
    """

    block_type: str  # "tool", "subagent", "command"
    name: str | None = None


@dataclass
class BlockEndEvent:
    """
    Signals the end of a block.

    Used to finalize block processing.
    """

    block_type: str
    success: bool = True
    error: str | None = None


# Union type for all parse events
ParseEvent = (
    TextEvent
    | ToolCallEvent
    | SubAgentCallEvent
    | CommandEvent
    | BlockStartEvent
    | BlockEndEvent
)


def is_action_event(event: ParseEvent) -> bool:
    """Check if event requires action (tool/subagent/command)."""
    return isinstance(event, (ToolCallEvent, SubAgentCallEvent, CommandEvent))


def is_text_event(event: ParseEvent) -> bool:
    """Check if event is text content."""
    return isinstance(event, TextEvent)
