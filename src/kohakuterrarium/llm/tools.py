"""
Utilities for building native tool schemas from the registry.

Converts registered Tool instances into ToolSchema objects suitable
for OpenAI-compatible native function calling.
"""

from kohakuterrarium.core.registry import Registry
from kohakuterrarium.llm.base import ToolSchema
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


def build_tool_schemas(registry: Registry) -> list[ToolSchema]:
    """
    Build native tool schemas from registered tools.

    Inspects each tool for a `get_parameters_schema()` method. If not
    available, falls back to a generic schema with a single "content"
    string parameter.

    Args:
        registry: Registry containing registered tools

    Returns:
        List of ToolSchema ready for the OpenAI tools API
    """
    schemas: list[ToolSchema] = []

    for name in registry.list_tools():
        info = registry.get_tool_info(name)
        if not info:
            continue

        # Try to get a proper parameters schema from the tool
        tool = registry.get_tool(name)
        params: dict = {}

        if tool and hasattr(tool, "get_parameters_schema"):
            try:
                params = tool.get_parameters_schema() or {}  # type: ignore
            except Exception as e:
                logger.warning(
                    "Failed to get parameters schema from tool",
                    tool_name=name,
                    error=str(e),
                )

        # Fall back to a generic content-based schema
        if not params:
            params = {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Input content for the tool",
                    }
                },
            }

        schemas.append(
            ToolSchema(
                name=name,
                description=info.description,
                parameters=params,
            )
        )

    logger.debug(
        "Built tool schemas",
        count=len(schemas),
        tools=[s.name for s in schemas],
    )
    return schemas
