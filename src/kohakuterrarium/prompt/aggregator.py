"""
Prompt aggregation - build system prompts from components.

Supports two modes:
1. Legacy: Combines base prompt, tool list, and framework hints
2. Plugin-based: Uses modular plugins for flexible composition

Full tool documentation is loaded on-demand via ##info## command.
"""

from pathlib import Path

from kohakuterrarium.core.registry import Registry
from kohakuterrarium.prompt.plugins import (
    BasePlugin,
    PluginContext,
    get_default_plugins,
)
from kohakuterrarium.prompt.template import render_template_safe
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


# Default framework hints included in system prompt
DEFAULT_FRAMEWORK_HINTS = """
## Tool Call Syntax

Use XML-style tags to call tools. The tag name is the tool name.

### Single-argument tools (content is the argument):
```
<bash>ls -la</bash>
<python>print("Hello")</python>
```

### Multi-argument tools (use attributes + content):
```
<read path="src/main.py"/>
<write path="new_file.py">file content here</write>
<edit path="src/main.py">
@@ -1,1 +1,2 @@
 import os
+import sys
</edit>
```

## Framework Commands

- `<info>tool_name</info>` - Get full documentation for a tool
- `<read_job>job_id</read_job>` - Read output from a background job

## Sub-Agent Syntax (if available)

Dispatch tasks to specialized sub-agents:
```
<agent type="explore">Find files related to authentication</agent>
<agent type="plan">Design the implementation for user login</agent>
```
""".strip()


def aggregate_system_prompt(
    base_prompt: str,
    registry: Registry | None = None,
    *,
    include_tools: bool = True,
    include_hints: bool = True,
    extra_context: dict | None = None,
) -> str:
    """
    Build complete system prompt from components.

    Includes only tool names + one-line descriptions.
    Full documentation is available via ##info tool_name## command.

    Args:
        base_prompt: Base system prompt (can contain Jinja2 templates)
        registry: Registry with registered tools
        include_tools: Include tool list in prompt
        include_hints: Include framework command hints
        extra_context: Extra variables for template rendering

    Returns:
        Complete system prompt
    """
    parts = []

    # Render base prompt with any template variables
    context = extra_context or {}
    if registry and include_tools:
        context["tools"] = [
            {
                "name": name,
                "description": (
                    registry.get_tool_info(name).description
                    if registry.get_tool_info(name)
                    else ""
                ),
            }
            for name in registry.list_tools()
        ]

    rendered_base = render_template_safe(base_prompt, **context)
    parts.append(rendered_base)

    # Add tool list (name + one-line description only)
    if registry and include_tools and "{{ tools }}" not in base_prompt:
        tools_list = _build_tools_list(registry)
        if tools_list:
            parts.append(tools_list)

    # Add framework hints
    if include_hints:
        parts.append(DEFAULT_FRAMEWORK_HINTS)

    result = "\n\n".join(parts)
    logger.debug("Aggregated system prompt", length=len(result))
    return result


def _build_tools_list(registry: Registry) -> str:
    """Build a concise tool list with names and one-line descriptions."""
    tool_names = registry.list_tools()
    if not tool_names:
        return ""

    lines = ["## Available Tools", ""]
    for name in tool_names:
        info = registry.get_tool_info(name)
        description = info.description if info else "No description"
        lines.append(f"- `{name}`: {description}")

    lines.append("")
    lines.append("Use `<info>tool_name</info>` for full documentation.")

    return "\n".join(lines)


def build_context_message(
    events_content: str,
    job_status: str | None = None,
) -> str:
    """
    Build a context message for the controller.

    Args:
        events_content: Formatted event content
        job_status: Optional job status section

    Returns:
        Formatted context message
    """
    parts = []

    if job_status:
        parts.append(f"## Running Jobs\n{job_status}")

    parts.append(events_content)

    return "\n\n".join(parts)


def aggregate_with_plugins(
    base_prompt: str,
    plugins: list[BasePlugin] | None = None,
    *,
    registry: Registry | None = None,
    working_dir: Path | None = None,
    agent_path: Path | None = None,
    extra_context: dict | None = None,
) -> str:
    """
    Build system prompt using plugin architecture.

    Plugins are sorted by priority and their content is appended
    after the base prompt.

    Args:
        base_prompt: Base system prompt (agent personality/guidelines)
        plugins: List of plugins to use (default: tool_list + framework_hints)
        registry: Registry with registered tools
        working_dir: Working directory for context
        agent_path: Agent folder path
        extra_context: Extra variables for template rendering

    Returns:
        Complete system prompt
    """
    # Use default plugins if none provided
    if plugins is None:
        plugins = get_default_plugins()

    # Create context for plugins
    context = PluginContext(
        registry=registry,
        working_dir=working_dir or Path.cwd(),
        agent_path=agent_path,
        extra=extra_context or {},
    )

    # Start with rendered base prompt
    template_vars = extra_context or {}
    rendered_base = render_template_safe(base_prompt, **template_vars)
    parts = [rendered_base]

    # Sort plugins by priority and collect content
    sorted_plugins = sorted(plugins, key=lambda p: p.priority)
    for plugin in sorted_plugins:
        try:
            content = plugin.get_content(context)
            if content:
                parts.append(content)
                logger.debug(
                    "Plugin contributed content",
                    plugin=plugin.name,
                    length=len(content),
                )
        except Exception as e:
            logger.warning("Plugin failed", plugin=plugin.name, error=str(e))

    result = "\n\n".join(parts)
    logger.debug(
        "Aggregated system prompt with plugins",
        length=len(result),
        plugin_count=len(plugins),
    )
    return result
