"""
Built-in tool implementations.

All tools use the @register_builtin decorator for automatic registration.
"""

from kohakuterrarium.builtins.tools.registry import (
    get_builtin_tool,
    is_builtin_tool,
    list_builtin_tools,
    register_builtin,
)

# Import tools to trigger registration
from kohakuterrarium.builtins.tools.bash import BashTool, PythonTool
from kohakuterrarium.builtins.tools.edit import EditTool
from kohakuterrarium.builtins.tools.glob import GlobTool
from kohakuterrarium.builtins.tools.grep import GrepTool
from kohakuterrarium.builtins.tools.read import ReadTool
from kohakuterrarium.builtins.tools.write import WriteTool

__all__ = [
    # Registry
    "register_builtin",
    "get_builtin_tool",
    "list_builtin_tools",
    "is_builtin_tool",
    # Tools
    "BashTool",
    "PythonTool",
    "ReadTool",
    "WriteTool",
    "EditTool",
    "GlobTool",
    "GrepTool",
]
