"""
Pattern definitions for stream parsing.

Configurable patterns for detecting tool calls, sub-agent calls, and commands.
"""

from dataclasses import dataclass, field


@dataclass
class BlockPattern:
    """
    Pattern definition for a block type.

    Attributes:
        start: Start marker (e.g., "##tool##")
        end: End marker (e.g., "##tool##")
        name_in_start: Whether name is embedded in start marker
            If True: "##subagent:name##" extracts "name"
            If False: name is parsed from content
    """

    start: str
    end: str
    name_in_start: bool = False
    name_prefix: str = ""  # e.g., "subagent:" for "##subagent:name##"

    def matches_start(self, text: str) -> bool:
        """Check if text matches start pattern."""
        if self.name_in_start:
            # For patterns like ##subagent:name##
            prefix = self.start.rstrip("#") + self.name_prefix
            return text.startswith(prefix)
        return text == self.start

    def extract_name_from_start(self, text: str) -> str | None:
        """Extract name from start marker if name_in_start is True."""
        if not self.name_in_start:
            return None
        # e.g., "##subagent:explore##" -> "explore"
        prefix = self.start.rstrip("#") + self.name_prefix
        suffix = "##"
        if text.startswith(prefix) and text.endswith(suffix):
            return text[len(prefix) : -len(suffix)]
        return None


@dataclass
class ParserConfig:
    """
    Configuration for the stream parser.

    Attributes:
        tool_pattern: Pattern for tool call blocks
        subagent_pattern: Pattern for sub-agent call blocks
        command_pattern: Pattern for framework commands
        emit_block_events: Whether to emit BlockStart/BlockEnd events
        buffer_text: Whether to buffer text between blocks
    """

    tool_pattern: BlockPattern = field(
        default_factory=lambda: BlockPattern(
            start="##tool##",
            end="##tool##",
            name_in_start=False,
        )
    )

    subagent_pattern: BlockPattern = field(
        default_factory=lambda: BlockPattern(
            start="##subagent:",
            end="##subagent##",
            name_in_start=True,
            name_prefix="",  # name comes right after "##subagent:"
        )
    )

    command_pattern: BlockPattern = field(
        default_factory=lambda: BlockPattern(
            start="##",
            end="##",
            name_in_start=True,
            name_prefix="",
        )
    )

    # Whether to emit BlockStartEvent and BlockEndEvent
    emit_block_events: bool = False

    # Buffer text chunks before emitting (reduces event count)
    buffer_text: bool = True

    # Minimum chars to buffer before emitting text
    text_buffer_size: int = 1


@dataclass
class ParsedBlock:
    """
    Represents a parsed block with its components.

    Used internally by the parser.
    """

    block_type: str  # "tool", "subagent", "command"
    name: str
    content: str
    raw: str


def parse_yaml_like(content: str) -> dict[str, str]:
    """
    Parse simple YAML-like content (key: value pairs).

    Handles:
    - Simple key: value
    - Multi-line values with indentation
    - Nested keys (args: ...)

    Returns flat dict - nested structures as strings.
    """
    result: dict[str, str] = {}
    lines = content.strip().split("\n")

    current_key: str | None = None
    current_value_lines: list[str] = []
    base_indent = 0

    for line in lines:
        # Skip empty lines
        if not line.strip():
            if current_key:
                current_value_lines.append("")
            continue

        # Count leading spaces
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        # Check if this is a new key
        if ":" in stripped and not stripped.startswith("-"):
            # Might be a new key
            colon_pos = stripped.find(":")
            potential_key = stripped[:colon_pos].strip()
            rest = stripped[colon_pos + 1 :].strip()

            # Is it a top-level key? (minimal indent or first key)
            if current_key is None or indent <= base_indent:
                # Save previous key if exists
                if current_key:
                    result[current_key] = "\n".join(current_value_lines).strip()

                current_key = potential_key
                base_indent = indent

                if rest:
                    # Value on same line
                    current_value_lines = [rest]
                else:
                    # Value on next lines
                    current_value_lines = []
            else:
                # It's part of the current value (nested)
                if current_key:
                    current_value_lines.append(line)
        else:
            # Continuation of current value
            if current_key:
                current_value_lines.append(line)

    # Save last key
    if current_key:
        result[current_key] = "\n".join(current_value_lines).strip()

    return result


def parse_tool_content(content: str) -> tuple[str, dict[str, str]]:
    """
    Parse tool block content to extract name and args.

    Expected format:
        name: tool_name
        args:
          arg1: value1
          arg2: value2

    Or simple:
        name: tool_name
        command: ls -la

    Returns:
        (tool_name, args_dict)
    """
    parsed = parse_yaml_like(content)
    name = parsed.pop("name", "")

    # If there's an "args" key with nested content, parse it
    if "args" in parsed:
        args_content = parsed.pop("args")
        # Parse nested args
        nested = parse_yaml_like(args_content)
        parsed.update(nested)

    return name, parsed


def parse_subagent_content(content: str) -> dict[str, str]:
    """
    Parse sub-agent block content (name already extracted from start marker).

    Returns args dict.
    """
    return parse_yaml_like(content)


def parse_command(raw: str) -> tuple[str, str]:
    """
    Parse a command like "##read job_123 --lines 50##".

    Returns:
        (command_name, args_string)
    """
    # Remove ## delimiters
    content = raw.strip()
    if content.startswith("##"):
        content = content[2:]
    if content.endswith("##"):
        content = content[:-2]

    content = content.strip()

    # Split into command and args
    parts = content.split(None, 1)
    command = parts[0] if parts else ""
    args = parts[1] if len(parts) > 1 else ""

    return command, args
