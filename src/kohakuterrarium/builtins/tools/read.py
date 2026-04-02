"""
Read tool - read file contents.
"""

import os
import time
from pathlib import Path
from typing import Any

import aiofiles

from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.modules.tool.base import (
    BaseTool,
    ExecutionMode,
    ToolResult,
)
from kohakuterrarium.utils.file_guard import is_binary_file
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@register_builtin("read")
class ReadTool(BaseTool):
    """
    Tool for reading file contents.

    Supports reading entire files or specific line ranges.
    """

    needs_context = True

    @property
    def tool_name(self) -> str:
        return "read"

    @property
    def description(self) -> str:
        return "Read file contents (required before write/edit)"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any], **kwargs: Any) -> ToolResult:
        """Read file contents."""
        context = kwargs.get("context")

        path = args.get("path", "")
        if not path:
            return ToolResult(error="No path provided")

        # Resolve path
        file_path = Path(path).expanduser().resolve()

        # Binary file guard
        if is_binary_file(file_path):
            return ToolResult(
                error=f"Binary file detected ({file_path.suffix}). "
                "Use bash with xxd, file, or other tools to inspect binary files."
            )

        # Path boundary guard
        if context and context.path_guard:
            msg = context.path_guard.check(str(file_path))
            if msg:
                return ToolResult(error=msg)

        if not file_path.exists():
            return ToolResult(error=f"File not found: {path}")

        if not file_path.is_file():
            return ToolResult(error=f"Not a file: {path}")

        # Get optional parameters
        offset = int(args.get("offset", 0))
        limit = int(args.get("limit", 0))

        # Configurable output truncation
        max_output_bytes = int(self.config.extra.get("max_output_bytes", 200000))

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
                # Truncate individual long lines
                if len(line_content) > 2000:
                    total_chars = len(line_content)
                    line_content = (
                        line_content[:2000]
                        + f" ... (line truncated, {total_chars} chars)"
                    )
                output_lines.append(f"{line_num:6}→{line_content}")

            output = "\n".join(output_lines)

            # Add truncation notice if applicable
            if limit > 0 and offset + limit < total_lines:
                output += f"\n\n... (showing lines {offset + 1}-{offset + len(lines)} of {total_lines})"

            # Truncate total output if it exceeds max bytes
            if max_output_bytes > 0 and len(output.encode("utf-8")) > max_output_bytes:
                output = output.encode("utf-8")[:max_output_bytes].decode(
                    "utf-8", errors="ignore"
                )
                output += f"\n\n[Output truncated at {max_output_bytes} bytes. Use offset/limit to read specific sections.]"

            logger.debug(
                "File read",
                file_path=str(file_path),
                lines_read=len(lines),
            )

            # Record read to file_read_state
            if context and context.file_read_state:
                mtime_ns = os.stat(file_path).st_mtime_ns
                partial = bool(args.get("offset") or args.get("limit"))
                context.file_read_state.record_read(
                    str(file_path), mtime_ns, partial, time.time()
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

## SAFETY

- You MUST read files before writing or editing them. The write and edit tools
  will error if you haven't read the file first.
- Binary files (images, PDFs, compiled files) are detected and rejected with
  a helpful message.
- Lines longer than 2000 characters are truncated.
- Total output is capped at 200KB. Use offset/limit for large files.

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

## TIPS

- Use `glob` first to find files by pattern, then `read` to examine them.
- Use `grep` to locate relevant lines, then `read` with offset/limit to
  examine context.
- For large files, read in chunks with offset/limit.
"""
