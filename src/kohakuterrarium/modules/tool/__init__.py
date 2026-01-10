"""
Tool module - executable tools for the controller.

Exports:
- Tool: Protocol for tools
- BaseTool: Base class for tools
- BashTool: Shell command execution
- PythonTool: Python code execution
- ReadTool: File reading
- WriteTool: File writing
- EditTool: File editing (string replacement)
- GlobTool: File pattern matching
- GrepTool: Content search
"""

from kohakuterrarium.modules.tool.base import (
    BaseTool,
    ExecutionMode,
    Tool,
    ToolConfig,
    ToolInfo,
    ToolResult,
)
from kohakuterrarium.modules.tool.bash import BashTool, PythonTool
from kohakuterrarium.modules.tool.file_tools import (
    EditTool,
    GlobTool,
    GrepTool,
    ReadTool,
    WriteTool,
)

__all__ = [
    # Protocol and base
    "Tool",
    "BaseTool",
    "ToolConfig",
    "ToolResult",
    "ToolInfo",
    "ExecutionMode",
    # Implementations
    "BashTool",
    "PythonTool",
    "ReadTool",
    "WriteTool",
    "EditTool",
    "GlobTool",
    "GrepTool",
]
