"""
Prompt aggregation - build system prompts from components.

Supports two skill modes:
1. Dynamic: Model uses [/info] to read tool docs on demand (less tokens)
2. Static: All tool docs included in system prompt (more context upfront)

Configurable via agent config: skill_mode: "dynamic" | "static"
"""

from pathlib import Path

from kohakuterrarium.builtin_skills import get_all_subagent_docs, get_all_tool_docs
from kohakuterrarium.core.registry import Registry
from kohakuterrarium.prompt.plugins import (
    BasePlugin,
    PluginContext,
    get_default_plugins,
)
from kohakuterrarium.prompt.template import render_template_safe
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


# Framework hints for dynamic skill mode (use [/info] to read docs)
DYNAMIC_FRAMEWORK_HINTS = """
## Calling Functions

All functions (tools and sub-agents) use this format:

```
[/function_name]
@@arg=value
content here
[function_name/]
```

Examples:

```
[/read]@@path=file.py[read/]
```

```
[/bash]ls -la[bash/]
```

```
[/write]
@@path=out.txt
content here
[write/]
```

```
[/explore]find auth code[explore/]
```

## Execution Model

- **Direct tools** (bash, read, write, etc.): Results return after you finish your response
- **Sub-agents** (explore, plan): Run in background, status reported back
- **Commands** (info, jobs): Results return after you finish your response

If you need results before continuing, END your response. Don't keep writing.
Call the function, then STOP and wait for results.

## Commands

- `[/info]tool_name[info/]` - read docs (stop and wait for result)
- `[/jobs][jobs/]` - list running jobs
- `[/wait]job_id[wait/]` - wait for background job
""".strip()

# Framework hints for static skill mode (all docs in prompt)
STATIC_FRAMEWORK_HINTS = """
## Calling Functions

All functions (tools and sub-agents) use this format:

```
[/function_name]
@@arg=value
content here
[function_name/]
```

Examples:

```
[/read]@@path=file.py[read/]
```

```
[/bash]ls -la[bash/]
```

```
[/explore]find auth code[explore/]
```

## Execution Model

- **Direct tools**: Results return after you finish your response
- **Sub-agents**: Run in background, status reported back

If you need results before continuing, END your response and wait.
""".strip()

# Backward compatibility
DEFAULT_FRAMEWORK_HINTS = DYNAMIC_FRAMEWORK_HINTS


def aggregate_system_prompt(
    base_prompt: str,
    registry: Registry | None = None,
    *,
    include_tools: bool = True,
    include_hints: bool = True,
    skill_mode: str = "dynamic",
    extra_context: dict | None = None,
) -> str:
    """
    Build complete system prompt from components.

    Args:
        base_prompt: Base system prompt (can contain Jinja2 templates)
        registry: Registry with registered tools
        include_tools: Include tool list in prompt
        include_hints: Include framework command hints
        skill_mode: "dynamic" (use [/info]) or "static" (full docs in prompt)
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

    # Add tool documentation based on skill_mode
    if registry and include_tools and "{{ tools }}" not in base_prompt:
        if skill_mode == "static":
            # Static mode: include full documentation
            full_docs = _build_full_tool_docs(registry)
            if full_docs:
                parts.append(full_docs)
        else:
            # Dynamic mode: only names + descriptions
            tools_list = _build_tools_list(registry)
            if tools_list:
                parts.append(tools_list)

    # Add framework hints (different for each mode)
    if include_hints:
        hints = (
            STATIC_FRAMEWORK_HINTS
            if skill_mode == "static"
            else DYNAMIC_FRAMEWORK_HINTS
        )
        parts.append(hints)

    result = "\n\n".join(parts)
    logger.debug("Aggregated system prompt", length=len(result), skill_mode=skill_mode)
    return result


def _build_tools_list(registry: Registry) -> str:
    """Build a concise tool list with names and one-line descriptions."""
    tool_names = registry.list_tools()
    subagent_names = registry.list_subagents()

    if not tool_names and not subagent_names:
        return ""

    lines = ["## Available Functions", ""]

    # Tools
    if tool_names:
        lines.append("**Tools:**")
        for name in tool_names:
            info = registry.get_tool_info(name)
            description = info.description if info else "No description"
            lines.append(f"- `{name}`: {description}")
        lines.append("")

    # Sub-agents
    if subagent_names:
        lines.append("**Sub-agents:**")
        for name in subagent_names:
            subagent = registry.get_subagent(name)
            desc = (
                getattr(subagent, "description", "Sub-agent")
                if subagent
                else "Sub-agent"
            )
            lines.append(f"- `{name}`: {desc}")
        lines.append("")

    lines.append("Use `[/info]name[info/]` for full documentation.")

    return "\n".join(lines)


def _build_full_tool_docs(registry: Registry) -> str:
    """Build full documentation for all tools and sub-agents (static mode)."""
    tool_names = registry.list_tools()
    subagent_names = registry.list_subagents()

    if not tool_names and not subagent_names:
        return ""

    parts = ["## Function Documentation", ""]

    # Get tool docs
    tool_docs = get_all_tool_docs(tool_names)
    for name in tool_names:
        doc = tool_docs.get(name)
        if doc:
            parts.append(doc)
            parts.append("")
        else:
            # Fallback to basic info
            info = registry.get_tool_info(name)
            if info:
                parts.append(f"### {name}\n{info.description}")
                parts.append("")

    # Get sub-agent docs
    subagent_docs = get_all_subagent_docs(subagent_names)
    for name in subagent_names:
        doc = subagent_docs.get(name)
        if doc:
            parts.append(doc)
            parts.append("")
        else:
            subagent = registry.get_subagent(name)
            desc = (
                getattr(subagent, "description", "Sub-agent")
                if subagent
                else "Sub-agent"
            )
            parts.append(f"### {name}\n{desc}")
            parts.append("")

    return "\n".join(parts)


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
