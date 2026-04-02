"""
Builtin tool registry (backward-compatible re-exports).

All real logic now lives in ``builtins.tool_catalog``. This module
re-exports the public API so that existing tool modules importing
``from kohakuterrarium.builtins.tools.registry import register_builtin``
continue to work without changes.
"""

from kohakuterrarium.builtins.tool_catalog import (
    get_builtin_tool,
    is_builtin_tool,
    list_builtin_tools,
    register_builtin,
)

__all__ = [
    "register_builtin",
    "get_builtin_tool",
    "list_builtin_tools",
    "is_builtin_tool",
]
