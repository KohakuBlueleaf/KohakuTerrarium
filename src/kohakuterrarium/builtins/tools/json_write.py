"""JSON write tool - modify JSON files."""

import json
from pathlib import Path
from typing import Any

import aiofiles

from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.modules.tool.base import BaseTool, ExecutionMode, ToolResult
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


def _split_path(path: str) -> list[str | int]:
    """Split a dot-path into components, handling array indices."""
    parts: list[str | int] = []
    for segment in path.split("."):
        if not segment:
            continue
        if "[" in segment:
            key, rest = segment.split("[", 1)
            if key:
                parts.append(key)
            idx = rest.rstrip("]")
            parts.append(int(idx))
        else:
            parts.append(segment)
    return parts


def _set_path(data: Any, query: str, value: Any) -> Any:
    """Set a value at a dot-path in JSON data. Returns modified data."""
    if not query or query == ".":
        return value

    path = query.lstrip(".")
    parts = _split_path(path)

    # Navigate to parent, creating intermediate dicts as needed
    current = data
    for part in parts[:-1]:
        if isinstance(part, int):
            current = current[part]
        else:
            if part not in current:
                current[part] = {}
            current = current[part]

    # Set value at final key
    last = parts[-1]
    if isinstance(last, int):
        current[last] = value
    else:
        current[last] = value

    return data


@register_builtin("json_write")
class JsonWriteTool(BaseTool):
    """Modify JSON files with path expressions."""

    @property
    def tool_name(self) -> str:
        return "json_write"

    @property
    def description(self) -> str:
        return "Modify JSON files at specific paths"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any], **kwargs: Any) -> ToolResult:
        """Write/modify a JSON file."""
        path = args.get("path", "")
        query = args.get("query", ".")
        value_str = args.get("value", "")

        if not path:
            return ToolResult(error="Path is required")
        if not value_str:
            return ToolResult(error="Value is required")

        # Parse the value as JSON, fall back to plain string
        try:
            value = json.loads(value_str)
        except json.JSONDecodeError:
            value = value_str

        file_path = Path(path).expanduser().resolve()

        # Read existing file or start with empty dict
        if file_path.exists():
            try:
                async with aiofiles.open(file_path, encoding="utf-8") as f:
                    content = await f.read()
                data = json.loads(content)
            except json.JSONDecodeError as e:
                return ToolResult(error=f"Invalid existing JSON: {e}")
            except PermissionError:
                return ToolResult(error=f"Permission denied: {path}")
            except Exception as e:
                logger.error("JSON read failed", error=str(e))
                return ToolResult(error=str(e))
        else:
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            data = {}

        # Apply modification
        try:
            data = _set_path(data, query, value)
        except (KeyError, IndexError, TypeError) as e:
            return ToolResult(error=f"Failed to set path: {e}")

        # Write back
        try:
            output_str = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            async with aiofiles.open(file_path, mode="w", encoding="utf-8") as f:
                await f.write(output_str)
        except PermissionError:
            return ToolResult(error=f"Permission denied: {path}")
        except Exception as e:
            logger.error("JSON write failed", error=str(e))
            return ToolResult(error=f"Failed to write: {e}")

        logger.debug("JSON file written", file_path=str(file_path), query=query)
        return ToolResult(
            output=f"Updated {path} at '{query}'",
            exit_code=0,
        )

    def get_full_documentation(self, tool_format: str = "native") -> str:
        return """# json_write

Modify JSON files at specific paths.

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| path | string | Path to JSON file (required) |
| query | string | Dot-path to modify (default: "." for entire file) |
| value | string | JSON value to set (required) |

## Behavior

- If the file does not exist, creates it with an empty object as the base.
- Creates intermediate parent directories if needed.
- The value is parsed as JSON first; if invalid JSON, treated as a plain string.
- Use query "." to replace the entire file contents.
- Intermediate keys are auto-created as objects when setting nested paths.

## Output

Confirmation that the file was updated at the specified path.
"""
