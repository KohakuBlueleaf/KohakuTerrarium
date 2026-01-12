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
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@register_builtin("grep")
class GrepTool(BaseTool):
    """
    Tool for searching file contents.

    Supports regex patterns and file type filtering.
    """

    @property
    def tool_name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return "Search file contents for a pattern"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any]) -> ToolResult:
        """Search files for pattern."""
        pattern = args.get("pattern", "")
        if not pattern:
            return ToolResult(error="No pattern provided")

        # Get base path
        base_path = args.get("path", ".")
        base = Path(base_path).expanduser().resolve()

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
            files_searched = 0

            # Find files to search
            if base.is_file():
                files = [base]
            else:
                files = list(base.glob(file_pattern))

            for file_path in files:
                if not file_path.is_file():
                    continue

                # Skip binary files (quick sync check is fine)
                try:
                    async with aiofiles.open(file_path, "rb") as f:
                        chunk = await f.read(1024)
                        if b"\x00" in chunk:
                            continue
                except Exception:
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
                                try:
                                    rel_path = file_path.relative_to(base)
                                except ValueError:
                                    rel_path = file_path

                                matches.append(
                                    {
                                        "file": str(rel_path),
                                        "line": line_num,
                                        "content": line.rstrip(),
                                    }
                                )

                                if len(matches) >= limit:
                                    break
                except Exception:
                    continue

                if len(matches) >= limit:
                    break

            # Format output
            output_lines = []
            for match in matches:
                output_lines.append(
                    f"{match['file']}:{match['line']}: {match['content']}"
                )

            output = "\n".join(output_lines)

            if len(matches) >= limit:
                output += (
                    f"\n\n... (limit {limit} reached, {files_searched} files searched)"
                )
            else:
                output += f"\n\n({len(matches)} matches in {files_searched} files)"

            logger.debug(
                "Grep search",
                pattern=pattern,
                matches=len(matches),
                files=files_searched,
            )

            return ToolResult(output=output or "(no matches)", exit_code=0)

        except Exception as e:
            logger.error("Grep failed", error=str(e))
            return ToolResult(error=str(e))

    def get_full_documentation(self) -> str:
        return """# grep

Search file contents for a pattern (regex supported).

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| pattern | body | Search pattern - regex (required) |
| path | attribute | Directory or file to search (default: cwd) |
| glob | attribute | File pattern filter (default: "**/*") |
| limit | attribute | Max matches (default: 50) |
| ignore_case | attribute | Case-insensitive (default: false) |

## Examples

Search for function definitions:
```xml
<grep glob="**/*.py">def \\w+\\(</grep>
```

Case-insensitive search:
```xml
<grep ignore_case="true">todo|fixme</grep>
```

Search in specific file:
```xml
<grep path="src/main.py">import</grep>
```

Search in directory:
```xml
<grep path="src/" glob="*.py">class \\w+:</grep>
```

## Output

Returns matches in format:
```
file.py:10: matching line content
file.py:25: another match
```
"""
