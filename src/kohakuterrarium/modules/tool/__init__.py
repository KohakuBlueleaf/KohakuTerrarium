"""
Tool module - executable tools for the controller.

Exports:
- Tool: Protocol for tools
- BaseTool: Base class for tools
- ToolConfig, ToolResult, ToolInfo: Tool data classes
- ExecutionMode: Tool execution modes

Note: Built-in tool implementations are in kohakuterrarium.builtins.tools
Import from there for tool registry functions and tool classes.
"""

from kohakuterrarium.modules.tool.base import (
    BaseTool,
    ExecutionMode,
    Tool,
    ToolConfig,
    ToolInfo,
    ToolResult,
)

__all__ = [
    # Protocol and base
    "Tool",
    "BaseTool",
    "ToolConfig",
    "ToolResult",
    "ToolInfo",
    "ExecutionMode",
]
