"""
Think tool - explicit reasoning step (no-op tool).
"""

from typing import Any

from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.modules.tool.base import BaseTool, ExecutionMode, ToolResult


@register_builtin("think")
class ThinkTool(BaseTool):
    """
    No-op tool for explicit reasoning.

    Forces the model to externalize reasoning into a tool call that's
    preserved in context. The tool does nothing - its value is that
    the thought is recorded as a tool_complete event.
    """

    @property
    def tool_name(self) -> str:
        return "think"

    @property
    def description(self) -> str:
        return "Record a reasoning step (preserved in context)"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(self, args: dict[str, Any]) -> ToolResult:
        """Think is a no-op - just acknowledge the thought."""
        return ToolResult(output="Noted.", exit_code=0)

    def get_full_documentation(self, tool_format: str = "native") -> str:
        return """# think

Explicit reasoning/thinking step. The tool itself does nothing -
its value is that the thought is preserved in conversation context
and won't be lost to context compaction.

Use this to externalize multi-step reasoning, plan before acting,
or record decisions that should survive context compaction.

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| thought | string | Your reasoning (required) |

## Output

Returns "Noted." (fixed response).
"""
