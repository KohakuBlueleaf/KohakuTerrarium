"""
Builtins module - all built-in components for the framework.

Contains:
- tools: Built-in tool implementations (bash, python, read, write, edit, glob, grep)
- skills: Skill documentation files (future)
- inputs: Input modules (future)
- outputs: Output modules (future)
- triggers: Trigger modules (future)
- subagents: Sub-agent definitions (future)
"""

from kohakuterrarium.builtins.tools import (
    BashTool,
    EditTool,
    GlobTool,
    GrepTool,
    PythonTool,
    ReadTool,
    WriteTool,
    get_builtin_tool,
    is_builtin_tool,
    list_builtin_tools,
    register_builtin,
)

__all__ = [
    # Tool registry
    "register_builtin",
    "get_builtin_tool",
    "list_builtin_tools",
    "is_builtin_tool",
    # Tool implementations
    "BashTool",
    "PythonTool",
    "ReadTool",
    "WriteTool",
    "EditTool",
    "GlobTool",
    "GrepTool",
]
