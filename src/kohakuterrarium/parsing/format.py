"""Configurable tool call format for the stream parser."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolCallFormat:
    """
    Defines the delimiters and style for tool call syntax.

    Two key format families:
    - Bracket: [/tool]@@arg=val\\ncontent[tool/]  (slash_means_open=True)
    - XML:     <tool arg="val">content</tool>     (slash_means_open=False)

    The state machine uses these to detect opening/closing tags:
    - See start_char -> might be a tag
    - See slash after start_char:
      - slash_means_open=True  -> it's an OPENING tag (bracket: [/name])
      - slash_means_open=False -> it's a CLOSING tag (XML: </name>)
    - See letter after start_char:
      - slash_means_open=True  -> it's a CLOSING tag (bracket: [name/])
      - slash_means_open=False -> it's an OPENING tag (XML: <name>)
    """

    start_char: str = "["
    end_char: str = "]"
    slash_means_open: bool = True
    arg_style: str = "line"  # "line" = @@key=val per line, "inline" = key="val" in tag
    arg_prefix: str = "@@"
    arg_kv_sep: str = "="


# Presets
BRACKET_FORMAT = ToolCallFormat()
XML_FORMAT = ToolCallFormat(
    start_char="<",
    end_char=">",
    slash_means_open=False,
    arg_style="inline",
    arg_prefix="",
)
