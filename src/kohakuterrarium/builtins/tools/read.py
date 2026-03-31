"""
Read tool - read file contents.
"""

from pathlib import Path
from typing import Any

import aiofiles

from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.modules.tool.base import (
    BaseTool,
    ExecutionMode,
    ToolResult,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@register_builtin("read")
class ReadTool(BaseTool):
    """
    Tool for reading file contents.

    Supports reading entire files or specific line ranges.
    """

    @property
    def tool_name(self) -> str:
        return "read"

    @property
    def description(self) -> str:
        return "Read file contents"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any]) -> ToolResult:
        """Read file contents."""
        path = args.get("path", "")
        if not path:
            return ToolResult(error="No path provided")

        # Resolve path
        file_path = Path(path).expanduser().resolve()

        if not file_path.exists():
            return ToolResult(error=f"File not found: {path}")

        if not file_path.is_file():
            return ToolResult(error=f"Not a file: {path}")

        # Get optional parameters
        offset = int(args.get("offset", 0))
        limit = int(args.get("limit", 0))

        try:
            async with aiofiles.open(
                file_path, encoding="utf-8", errors="replace"
            ) as f:
                content = await f.read()
            lines = content.splitlines(keepends=True)

            total_lines = len(lines)

            # Apply offset and limit
            if offset > 0:
                lines = lines[offset:]
            if limit > 0:
                lines = lines[:limit]

            # Format with line numbers
            output_lines = []
            start_line = offset + 1
            for i, line in enumerate(lines):
                line_num = start_line + i
                # Remove trailing newline for cleaner output
                line_content = line.rstrip("\n\r")
                output_lines.append(f"{line_num:6}→{line_content}")

            output = "\n".join(output_lines)

            # Add truncation notice if applicable
            if limit > 0 and offset + limit < total_lines:
                output += f"\n\n... (showing lines {offset + 1}-{offset + len(lines)} of {total_lines})"

            logger.debug(
                "File read",
                file_path=str(file_path),
                lines_read=len(lines),
            )

            return ToolResult(output=output, exit_code=0)

        except PermissionError:
            return ToolResult(error=f"Permission denied: {path}")
        except Exception as e:
            logger.error("Read failed", error=str(e))
            return ToolResult(error=str(e))

    def get_full_documentation(self, tool_format: str = "native") -> str:
        return """# read

Read file contents with optional line range.

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| path | string | Path to file (required) |
| offset | integer | Line to start from (0-based, default: 0) |
| limit | integer | Max lines to read (default: all) |

## Behavior

- Returns file contents with line numbers in the format `     1→content`.
- If offset and limit are specified, only that range is returned.
- Shows a truncation notice when the range does not cover the full file.

## Output

Line-numbered file contents. Line numbers are 1-indexed in the output.
"""
