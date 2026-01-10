"""
Pattern definitions for stream parsing.

Supports XML-style tool calls: <tool_name attr="value">content</tool_name>
"""

import re
from dataclasses import dataclass, field


@dataclass
class ParserConfig:
    """
    Configuration for the stream parser.

    Attributes:
        emit_block_events: Whether to emit BlockStart/BlockEnd events
        buffer_text: Whether to buffer text between blocks
        text_buffer_size: Minimum chars to buffer before emitting
    """

    # Whether to emit BlockStartEvent and BlockEndEvent
    emit_block_events: bool = False

    # Buffer text chunks before emitting (reduces event count)
    buffer_text: bool = True

    # Minimum chars to buffer before emitting text
    text_buffer_size: int = 1


# Regex for parsing XML-style opening tags with attributes
# Matches: <tag_name attr1="value1" attr2="value2">
# Or self-closing: <tag_name attr="value"/>
OPENING_TAG_PATTERN = re.compile(
    r"<([a-zA-Z_][a-zA-Z0-9_]*)"  # Tag name
    r"((?:\s+[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*\"[^\"]*\")*)"  # Attributes
    r"\s*(/?)>"  # Optional self-closing /
)

# Regex for extracting individual attributes
ATTR_PATTERN = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*"([^"]*)"')

# Regex for closing tag
CLOSING_TAG_PATTERN = re.compile(r"</([a-zA-Z_][a-zA-Z0-9_]*)>")


def parse_attributes(attr_string: str) -> dict[str, str]:
    """
    Parse attributes from an opening tag.

    Args:
        attr_string: String like ' path="src/main.py" limit="50"'

    Returns:
        Dict of attribute name -> value
    """
    attrs = {}
    for match in ATTR_PATTERN.finditer(attr_string):
        name, value = match.groups()
        attrs[name] = value
    return attrs


def parse_opening_tag(tag_text: str) -> tuple[str, dict[str, str], bool] | None:
    """
    Parse an opening XML tag.

    Args:
        tag_text: Full tag like '<bash>' or '<edit path="file.py">' or '<read/>'

    Returns:
        (tag_name, attributes, is_self_closing) or None if invalid
    """
    match = OPENING_TAG_PATTERN.match(tag_text)
    if not match:
        return None

    tag_name = match.group(1)
    attr_string = match.group(2)
    is_self_closing = match.group(3) == "/"

    attrs = parse_attributes(attr_string) if attr_string else {}

    return tag_name, attrs, is_self_closing


def parse_closing_tag(tag_text: str) -> str | None:
    """
    Parse a closing XML tag.

    Args:
        tag_text: Tag like '</bash>'

    Returns:
        Tag name or None if invalid
    """
    match = CLOSING_TAG_PATTERN.match(tag_text)
    if match:
        return match.group(1)
    return None


def build_tool_args(
    tag_name: str,
    attributes: dict[str, str],
    content: str,
) -> dict[str, str]:
    """
    Build tool arguments from tag attributes and content.

    For tools like bash/python, content is the main argument.
    For tools like edit, content is the diff and path is an attribute.

    Args:
        tag_name: The tool name
        attributes: Parsed attributes from the tag
        content: Content between opening and closing tags

    Returns:
        Complete args dict for the tool
    """
    args = dict(attributes)  # Copy attributes

    # Map content to the appropriate argument based on tool type
    content = content.strip()
    if content:
        # Determine what to call the content arg based on tool
        content_arg_map = {
            "bash": "command",
            "python": "code",
            "edit": "diff",
            "write": "content",
            "read": "path",  # For <read>path</read> style
            "glob": "pattern",
            "grep": "pattern",
            # Commands
            "info": "tool_name",
            "read_job": "job_id",
        }

        content_arg = content_arg_map.get(tag_name, "content")

        # Don't override if already set via attribute
        if content_arg not in args:
            args[content_arg] = content

    return args


# Known tool names for validation
KNOWN_TOOLS = {"bash", "python", "read", "write", "edit", "glob", "grep"}

# Known sub-agent names
KNOWN_SUBAGENTS = {"agent"}  # Generic agent tag, type specified via attribute

# Known command names
KNOWN_COMMANDS = {"info", "read_job"}


def is_tool_tag(tag_name: str) -> bool:
    """Check if tag name is a known tool."""
    return tag_name in KNOWN_TOOLS


def is_subagent_tag(tag_name: str) -> bool:
    """Check if tag name is a sub-agent call."""
    return tag_name in KNOWN_SUBAGENTS


def is_command_tag(tag_name: str) -> bool:
    """Check if tag name is a known command."""
    return tag_name in KNOWN_COMMANDS
