"""
Glob tool - find files matching patterns.
"""

import asyncio
from pathlib import Path
from typing import Any

from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.modules.tool.base import (
    BaseTool,
    ExecutionMode,
    ToolResult,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@register_builtin("glob")
class GlobTool(BaseTool):
    """
    Tool for finding files by pattern.

    Supports glob patterns like **/*.py
    """

    @property
    def tool_name(self) -> str:
        return "glob"

    @property
    def description(self) -> str:
        return "Find files matching a pattern"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any]) -> ToolResult:
        """Find files matching pattern."""
        pattern = args.get("pattern", "")
        if not pattern:
            return ToolResult(error="No pattern provided")

        # Get base path
        base_path = args.get("path", ".")
        base = Path(base_path).expanduser().resolve()

        if not base.exists():
            return ToolResult(error=f"Path not found: {base_path}")

        # Get limit
        limit = int(args.get("limit", 100))

        try:
            # Run blocking glob/stat in thread pool
            result = await asyncio.to_thread(self._find_files, base, pattern, limit)
            return result

        except Exception as e:
            logger.error("Glob failed", error=str(e))
            return ToolResult(error=str(e))

    def _find_files(self, base: Path, pattern: str, limit: int) -> ToolResult:
        """Synchronous file finding (runs in thread pool)."""
        # Use glob to find files
        matches = list(base.glob(pattern))

        # Sort by modification time (newest first)
        matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        # Apply limit
        total = len(matches)
        if limit > 0 and len(matches) > limit:
            matches = matches[:limit]

        # Format output
        output_lines = []
        for match in matches:
            try:
                rel_path = match.relative_to(base)
            except ValueError:
                rel_path = match
            output_lines.append(str(rel_path))

        output = "\n".join(output_lines)

        if total > len(matches):
            output += f"\n\n... ({total} total, showing {len(matches)})"

        logger.debug(
            "Glob search",
            pattern=pattern,
            matches=len(matches),
        )

        return ToolResult(output=output or "(no matches)", exit_code=0)

    def get_full_documentation(self) -> str:
        return """# glob

Find files matching a glob pattern.

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| pattern | body | Glob pattern (required) |
| path | attribute | Base directory (default: cwd) |
| limit | attribute | Max results (default: 100) |

## Examples

Find all Python files:
```xml
<glob>**/*.py</glob>
```

Find files in specific directory:
```xml
<glob path="src/components">*.ts</glob>
```

With limit:
```xml
<glob path="." limit="50">**/*.md</glob>
```

## Patterns

- `*` - matches any characters except /
- `**` - matches any characters including /
- `?` - matches single character
- `[abc]` - matches a, b, or c

## Output

Returns list of matching file paths, sorted by modification time (newest first).
"""
