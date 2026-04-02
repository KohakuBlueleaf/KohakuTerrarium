"""
Grep tool - search file contents.
"""

import re
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


@register_builtin("grep")
class GrepTool(BaseTool):
    """
    Tool for searching file contents.

    Supports regex patterns and file type filtering.
    """

    needs_context = True

    @property
    def tool_name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return "Search file contents for a pattern"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any], **kwargs: Any) -> ToolResult:
        """Search files for pattern."""
        context = kwargs.get("context")

        pattern = args.get("pattern", "")
        if not pattern:
            return ToolResult(error="No pattern provided")

        # Get base path
        base_path = args.get("path", ".")
        base = Path(base_path).expanduser().resolve()

        # Path boundary guard
        if context and context.path_guard:
            msg = context.path_guard.check(str(base))
            if msg:
                return ToolResult(error=msg)

        if not base.exists():
            return ToolResult(error=f"Path not found: {base_path}")

        # Get options
        file_pattern = args.get("glob", "**/*")
        limit = int(args.get("limit", 50))
        case_insensitive = args.get("ignore_case", False)

        # Compile regex
        try:
            flags = re.IGNORECASE if case_insensitive else 0
            regex = re.compile(pattern, flags)
        except re.error as e:
            return ToolResult(error=f"Invalid regex: {e}")

        try:
            matches = []
            total_matches = 0
            files_searched = 0

            # Find files to search
            if base.is_file():
                files = [base]
            else:
                files = list(base.glob(file_pattern))

            for file_path in files:
                if not file_path.is_file():
                    continue

                # Skip binary files
                if is_binary_file(file_path):
                    continue

                files_searched += 1

                try:
                    async with aiofiles.open(
                        file_path, encoding="utf-8", errors="replace"
                    ) as f:
                        line_num = 0
                        async for line in f:
                            line_num += 1
                            if regex.search(line):
                                total_matches += 1

                                if len(matches) < limit:
                                    content = line.rstrip()
                                    # Truncate long lines
                                    if len(content) > 2000:
                                        content = content[:2000] + " ... (truncated)"

                                    try:
                                        rel_path = file_path.relative_to(base)
                                    except ValueError:
                                        rel_path = file_path

                                    matches.append(
                                        {
                                            "file": str(rel_path),
                                            "line": line_num,
                                            "content": content,
                                        }
                                    )
                except Exception:
                    continue

            # Format output
            output_lines = []
            for match in matches:
                output_lines.append(
                    f"{match['file']}:{match['line']}: {match['content']}"
                )

            output = "\n".join(output_lines)

            if total_matches > limit:
                output += (
                    f"\n\nShowing first {limit} of {total_matches} matches. "
                    "Narrow your pattern or use glob first."
                )
            else:
                output += f"\n\n({total_matches} matches in {files_searched} files)"

            logger.debug(
                "Grep search",
                pattern=pattern,
                matches=total_matches,
                files=files_searched,
            )

            return ToolResult(output=output or "(no matches)", exit_code=0)

        except Exception as e:
            logger.error("Grep failed", error=str(e))
            return ToolResult(error=str(e))

    def get_full_documentation(self, tool_format: str = "native") -> str:
        return """# grep

Search file contents for a pattern (regex supported).

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| pattern | string | Search pattern - Python regex (required) |
| path | string | Directory or file to search (default: cwd) |
| glob | string | File pattern filter (default: "**/*") |
| limit | integer | Max matches (default: 50) |
| ignore_case | boolean | Case-insensitive search (default: false) |

## Behavior

- Skips binary files automatically.
- Searches recursively through directories matching the glob filter.
- Stops after reaching the match limit.

## Output

Returns matches in `file:line: content` format, one per line.
Shows total match count and files searched at the end.
"""
