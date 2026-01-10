"""
Builtin tool registry.

Provides registration and lookup for built-in tools.
Uses a global registry populated at import time via decorators.
"""

from typing import TYPE_CHECKING, Callable, TypeVar

from kohakuterrarium.utils.logging import get_logger

if TYPE_CHECKING:
    from kohakuterrarium.modules.tool.base import BaseTool

logger = get_logger(__name__)

# Global registry of built-in tool classes
_BUILTIN_TOOLS: dict[str, type["BaseTool"]] = {}

T = TypeVar("T", bound="BaseTool")


def register_builtin(name: str) -> Callable[[type[T]], type[T]]:
    """
    Decorator to register a built-in tool.

    Usage:
        @register_builtin("bash")
        class BashTool(BaseTool):
            ...

    Args:
        name: Tool name for registration

    Returns:
        Decorator function
    """

    def decorator(cls: type[T]) -> type[T]:
        _BUILTIN_TOOLS[name] = cls
        logger.debug("Registered builtin tool", tool_name=name)
        return cls

    return decorator


def get_builtin_tool(name: str) -> "BaseTool | None":
    """
    Get an instance of a built-in tool by name.

    Args:
        name: Tool name

    Returns:
        Tool instance or None if not found
    """
    tool_cls = _BUILTIN_TOOLS.get(name)
    if tool_cls:
        return tool_cls()
    return None


def list_builtin_tools() -> list[str]:
    """
    List all registered built-in tool names.

    Returns:
        List of tool names
    """
    return list(_BUILTIN_TOOLS.keys())


def is_builtin_tool(name: str) -> bool:
    """
    Check if a tool name is a registered built-in.

    Args:
        name: Tool name to check

    Returns:
        True if registered
    """
    return name in _BUILTIN_TOOLS
