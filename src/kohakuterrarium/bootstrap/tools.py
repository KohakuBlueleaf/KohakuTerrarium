"""
Tool initialization factory.

Registers tools from agent config into the module registry.
"""

from typing import Any

from kohakuterrarium.builtins.tool_catalog import get_builtin_tool
from kohakuterrarium.core.config import AgentConfig
from kohakuterrarium.core.loader import ModuleLoadError, ModuleLoader
from kohakuterrarium.core.registry import Registry
from kohakuterrarium.modules.tool.base import BaseTool
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


def create_tool(
    tool_config: Any,
    loader: ModuleLoader | None,
) -> BaseTool | None:
    """Create a single tool instance from a tool config entry.

    Handles builtin, custom, and package tool types. Returns None
    if the tool could not be created.
    """
    match tool_config.type:
        case "builtin":
            tool = get_builtin_tool(tool_config.name)
            if tool is None:
                logger.warning("Unknown built-in tool", tool_name=tool_config.name)
            return tool

        case "custom" | "package":
            if not tool_config.module or not tool_config.class_name:
                logger.warning(
                    "Custom tool missing module or class",
                    tool_name=tool_config.name,
                )
                return None
            if loader is None:
                logger.warning(
                    "No module loader available for custom tool",
                    tool_name=tool_config.name,
                )
                return None
            try:
                return loader.load_instance(
                    module_path=tool_config.module,
                    class_name=tool_config.class_name,
                    module_type=tool_config.type,
                    options=tool_config.options,
                )
            except ModuleLoadError as e:
                logger.error("Failed to load custom tool", error=str(e))
                return None

        case _:
            logger.warning("Unknown tool type", tool_type=tool_config.type)
            return None


def init_tools(
    config: AgentConfig,
    registry: Registry,
    loader: ModuleLoader | None,
) -> None:
    """Register all tools from agent config into the registry.

    Iterates over config.tools and creates each tool via create_tool(),
    registering successful results in the registry.
    """
    for tool_config in config.tools:
        tool = create_tool(tool_config, loader)
        if tool:
            registry.register_tool(tool)
