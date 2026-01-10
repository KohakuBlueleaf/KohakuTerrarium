"""
Prompt aggregation - build system prompts from components.

Combines base prompt, tool documentation, and framework hints.
"""

from kohakuterrarium.core.registry import Registry
from kohakuterrarium.prompt.template import render_template_safe
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


# Default framework hints included in system prompt
DEFAULT_FRAMEWORK_HINTS = """
## Framework Commands

To read job output:
```
##read job_id [--lines N] [--offset M]##
```

To get tool documentation:
```
##info tool_name##
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

    # Add tool list if registry provided and not already in template
    if registry and include_tools and "{{ tools }}" not in base_prompt:
        tools_section = registry.get_tools_prompt()
        if tools_section:
            parts.append(tools_section)

    # Add framework hints
    if include_hints:
        parts.append(DEFAULT_FRAMEWORK_HINTS)

    result = "\n\n".join(parts)
    logger.debug("Aggregated system prompt", length=len(result))
    return result


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
