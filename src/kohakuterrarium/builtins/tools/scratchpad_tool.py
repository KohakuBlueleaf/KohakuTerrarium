"""Scratchpad tool - read/write session working memory."""

from typing import Any

from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.core.scratchpad import get_scratchpad
from kohakuterrarium.modules.tool.base import (
    BaseTool,
    ExecutionMode,
    ToolContext,
    ToolResult,
)


@register_builtin("scratchpad")
class ScratchpadTool(BaseTool):
    """Read/write session-scoped key-value working memory."""

    needs_context = True

    @property
    def tool_name(self) -> str:
        return "scratchpad"

    @property
    def description(self) -> str:
        return "Read/write session working memory (key-value)"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(
        self, args: dict[str, Any], context: ToolContext | None = None
    ) -> ToolResult:
        """Execute scratchpad action."""
        action = args.get("action", "get")
        key = args.get("key", "")
        value = args.get("value", "")

        scratchpad = (
            context.session.scratchpad
            if context and context.session
            else get_scratchpad()
        )

        match action:
            case "set":
                if not key:
                    return ToolResult(error="Key is required for set action")
                scratchpad.set(key, value)
                return ToolResult(output=f"Set '{key}'", exit_code=0)

            case "get":
                if not key:
                    return ToolResult(error="Key is required for get action")
                result = scratchpad.get(key)
                if result is None:
                    return ToolResult(output=f"Key '{key}' not found", exit_code=0)
                return ToolResult(output=result, exit_code=0)

            case "delete":
                if not key:
                    return ToolResult(error="Key is required for delete action")
                if scratchpad.delete(key):
                    return ToolResult(output=f"Deleted '{key}'", exit_code=0)
                return ToolResult(output=f"Key '{key}' not found", exit_code=0)

            case "list":
                keys = scratchpad.list_keys()
                if not keys:
                    return ToolResult(output="(empty)", exit_code=0)
                output = "\n".join(f"- {k}" for k in keys)
                return ToolResult(output=output, exit_code=0)

            case "clear":
                scratchpad.clear()
                return ToolResult(output="Scratchpad cleared", exit_code=0)

            case _:
                return ToolResult(
                    error=f"Unknown action: {action}. Use: get, set, delete, list, clear"
                )

    def get_full_documentation(self, tool_format: str = "native") -> str:
        return """# scratchpad

Read/write session-scoped working memory. Data persists within the session
but is cleared on restart. Use for plans, tracking progress, notes.

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| action | string | get, set, delete, list, or clear |
| key | string | Key name (required for get/set/delete) |
| value | string | Value to store (required for set) |

## Actions

- **set**: Store a value under the given key. Overwrites if key exists.
- **get**: Retrieve the value for a key. Returns "not found" if missing.
- **delete**: Remove a key and its value.
- **list**: Show all stored keys.
- **clear**: Remove all keys and values.

## Output

Returns the value for get, confirmation for set/delete/clear, key list for list.
"""
