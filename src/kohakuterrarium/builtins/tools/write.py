"""
Write tool - write content to files.
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


@register_builtin("write")
class WriteTool(BaseTool):
    """
    Tool for writing/creating files.

    Creates parent directories if needed.
    """

    @property
    def tool_name(self) -> str:
        return "write"

    @property
    def description(self) -> str:
        return "Write content to a file"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any]) -> ToolResult:
        """Write content to file."""
        path = args.get("path", "")
        content = args.get("content", "")

        if not path:
            return ToolResult(error="No path provided")

        # Resolve path
        file_path = Path(path).expanduser().resolve()

        try:
            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Check if file exists for logging
            exists = file_path.exists()

            # Write content
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(content)

            action = "Updated" if exists else "Created"
            lines = content.count("\n") + 1 if content else 0

            logger.debug(
                "File written",
                file_path=str(file_path),
                action=action.lower(),
                lines=lines,
            )

            return ToolResult(
                output=f"{action} {file_path} ({lines} lines, {len(content)} bytes)",
                exit_code=0,
            )

        except PermissionError:
            return ToolResult(error=f"Permission denied: {path}")
        except Exception as e:
            logger.error("Write failed", error=str(e))
            return ToolResult(error=str(e))

    def get_full_documentation(self) -> str:
        return """# write

Write content to a file. Creates the file if it doesn't exist.
Creates parent directories automatically.

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| path | attribute | Path to file (required) |
| content | body | Content to write |

## Examples

Create a new file:
```xml
<write path="src/hello.py">
def hello():
    print("Hello, World!")

if __name__ == "__main__":
    hello()
</write>
```

## Notes

- Overwrites existing files
- Creates parent directories if they don't exist
- Content is written exactly as provided
"""
