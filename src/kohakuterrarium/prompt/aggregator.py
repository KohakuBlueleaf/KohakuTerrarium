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


# Framework hints template - {named_outputs_section} is replaced dynamically
FRAMEWORK_HINTS_OUTPUT_MODEL = """
## Output Format

Plain text = internal thinking (not sent anywhere)
To send output externally, you MUST wrap in output block:

[/output_<name>]your content here[output_<name>/]
{named_outputs_section}
"""

NAMED_OUTPUTS_SECTION_TEMPLATE = """
Available: {outputs_list}

---output example---
[/output_{first_output}]Hello![output_{first_output}/]
---end example---

If you want to send to {first_output}, wrap your message exactly like above.
Without the wrapper, nothing gets sent.
"""

# Framework hints base - examples are generated dynamically from registry
_DYNAMIC_HINTS_HEADER = """## Calling Functions

All functions (tools and sub-agents) use this format:

```
[/function_name]
@@arg=value
content here
[function_name/]
```
"""

_DYNAMIC_HINTS_FOOTER = """
## Execution Model

- **Direct tools**: Results return after you finish your response
- **Sub-agents**: Run in background - you MUST use `wait` to get results
- **Commands** (info, jobs, wait): Execute during your response

IMPORTANT: When calling a function, output ONLY the function call block. Do not output any extra text, markers, or filler characters (like dashes, dots, etc.) before or after the function call. If you need results before continuing, end with the function call and nothing else.
IMPORTANT: You may ONLY call functions listed in the "Available Functions" section above. Do NOT call functions that are not listed.

## Commands

- `[/info]tool_name[info/]` - read docs for a tool
- `[/jobs][jobs/]` - list running background jobs
- `[/wait]job_id[wait/]` - block until job completes (default 60s timeout)
- `[/wait timeout="10"]job_id[wait/]` - wait with custom timeout (seconds)

### Wait Command Usage

Sub-agents run in background. To get their results, you MUST call wait:

1. Call a sub-agent (you get a job_id)
2. Call `[/wait]job_id[wait/]` to block until it completes

Without calling wait, sub-agent results are NOT delivered to you.
"""

_STATIC_HINTS_HEADER = _DYNAMIC_HINTS_HEADER

_STATIC_HINTS_FOOTER = """
## Execution Model

- **Direct tools**: Results return after you finish your response
- **Sub-agents**: Run in background, status reported back

IMPORTANT: When calling a function, output ONLY the function call block. Do not output any extra text, markers, or filler characters before or after. If you need results before continuing, end with the function call and nothing else.
IMPORTANT: You may ONLY call functions listed in the "Available Functions" section above. Do NOT call functions that are not listed.
"""


def _build_dynamic_hints(
    registry: Registry | None = None, tool_format: str = "bracket"
) -> str:
    """Build framework hints with examples from actual registered tools."""
    parts = [_DYNAMIC_HINTS_HEADER.strip()]

    examples = _build_tool_examples(registry, tool_format=tool_format)
    if examples:
        parts.append("Examples:\n" + examples)

    parts.append(_DYNAMIC_HINTS_FOOTER.strip())
    return "\n\n".join(parts)


def _build_static_hints(
    registry: Registry | None = None, tool_format: str = "bracket"
) -> str:
    """Build static framework hints with examples from actual registered tools."""
    parts = [_STATIC_HINTS_HEADER.strip()]

    examples = _build_tool_examples(registry, tool_format=tool_format)
    if examples:
        parts.append("Examples:\n" + examples)

    parts.append(_STATIC_HINTS_FOOTER.strip())
    return "\n\n".join(parts)


_NATIVE_HINTS = """## Tool Usage

Tools are called via the API's native function calling mechanism.
You do not need to format tool calls manually.

By default, tool results are returned immediately after your response.
You WILL receive the result before your next turn.

All tools accept an optional `run_in_background` parameter (boolean).
If set to true, the tool runs asynchronously and results are delivered
in a later turn instead of immediately. When you have background jobs
running, you can continue with other work - the results will be
delivered to you automatically when ready. You do NOT need to poll
or wait for them. Just finish your current response and the system
will notify you when background tasks complete.

You may ONLY call tools listed in the "Available Functions" section above.
"""


def _build_native_hints(registry: Registry | None = None) -> str:
    """Build hints for native tool calling mode (no syntax examples)."""
    return _NATIVE_HINTS.strip()


def _build_tool_examples(
    registry: Registry | None, tool_format: str = "bracket"
) -> str:
    """Generate call examples from actual registered tools and sub-agents.

    Examples adapt to the tool_format:
    - bracket: [/tool]@@arg=val\\ncontent[tool/]
    - xml: <tool arg="val">content</tool>
    """
    if not registry:
        return ""

    examples: list[str] = []
    tool_names = set(registry.list_tools())
    subagent_names = set(registry.list_subagents())

    if tool_format == "xml":
        # XML format examples
        if "read" in tool_names:
            examples.append('```\n<read path="file.py"/>\n```')
        elif "glob" in tool_names:
            examples.append('```\n<glob pattern="**/*.py"/>\n```')

        if "bash" in tool_names:
            examples.append("```\n<bash>ls -la</bash>\n```")
        elif "think" in tool_names:
            examples.append(
                "```\n<think>Analyze the problem step by step...</think>\n```"
            )

        if "write" in tool_names:
            examples.append('```\n<write path="out.txt">content here</write>\n```')
        elif "send_message" in tool_names:
            examples.append(
                '```\n<send_message channel="inbox">Hello</send_message>\n```'
            )
    else:
        # Bracket format examples (default)
        if "read" in tool_names:
            examples.append("```\n[/read]@@path=file.py[read/]\n```")
        elif "json_read" in tool_names:
            examples.append("```\n[/json_read]@@path=data.json[json_read/]\n```")
        elif "glob" in tool_names:
            examples.append("```\n[/glob]@@pattern=**/*.py[glob/]\n```")

        if "think" in tool_names:
            examples.append(
                "```\n[/think]\nAnalyze the problem step by step...\n[think/]\n```"
            )
        elif "bash" in tool_names:
            examples.append("```\n[/bash]ls -la[bash/]\n```")

        if "write" in tool_names:
            examples.append(
                "```\n[/write]\n@@path=out.txt\ncontent here\n[write/]\n```"
            )
        elif "scratchpad" in tool_names:
            examples.append(
                "```\n[/scratchpad]\n@@action=set\n@@key=plan\nmy plan here\n[scratchpad/]\n```"
            )
        elif "send_message" in tool_names:
            examples.append(
                "```\n[/send_message]\n@@channel=inbox\nHello from agent\n[send_message/]\n```"
            )

    # Sub-agent example
    if subagent_names:
        first_sa = sorted(subagent_names)[0]
        if tool_format == "xml":
            examples.append(
                f"```\n<{first_sa}>describe the task here</{first_sa}>\n```"
            )
        else:
            examples.append(
                f"```\n[/{first_sa}]describe the task here[{first_sa}/]\n```"
            )

    return "\n\n".join(examples)


def aggregate_system_prompt(
    base_prompt: str,
    registry: Registry | None = None,
    *,
    include_tools: bool = True,
    include_hints: bool = True,
    skill_mode: str = "dynamic",
    tool_format: str = "bracket",
    known_outputs: set[str] | None = None,
    channels: list[dict[str, str]] | None = None,
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
        tool_format: Tool calling format — "bracket", "xml", or "native".
                     Native mode skips calling syntax examples (API handles it).
        known_outputs: Set of available named output targets (e.g., {"discord"})
        channels: Channel info for prompt injection (list of dicts with
                  name, type, description). Auto-detected from session if None.
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

    # Add channel communication hints (when channel tools are registered)
    if registry and include_hints:
        hint_ctx = dict(extra_context or {})
        if channels is not None:
            hint_ctx["channels"] = channels
        channel_hints = _build_channel_hints(registry, hint_ctx)
        if channel_hints:
            parts.append(channel_hints)

    # Add framework hints (different for each mode)
    if include_hints:
        # Build output model section with available outputs
        # (skip for native mode — outputs are also API-driven)
        if tool_format != "native":
            output_hints = _build_output_hints(known_outputs)
            if output_hints:
                parts.append(output_hints)

        # Add function calling hints
        # Native mode: skip syntax examples entirely (API handles formatting)
        # Bracket/XML/custom: show format-appropriate examples
        if tool_format == "native":
            hints = _build_native_hints(registry)
        elif skill_mode == "static":
            hints = _build_static_hints(registry, tool_format=tool_format)
        else:
            hints = _build_dynamic_hints(registry, tool_format=tool_format)
        parts.append(hints)

    result = "\n\n".join(parts)
    logger.debug("Aggregated system prompt", length=len(result), skill_mode=skill_mode)
    return result


def _build_output_hints(known_outputs: set[str] | None) -> str:
    """Build output model hints with available named outputs."""
    logger.debug("Building output hints", known_outputs=known_outputs)
    if not known_outputs:
        # No named outputs - just basic output model
        logger.debug("No known outputs, using basic output model")
        return FRAMEWORK_HINTS_OUTPUT_MODEL.format(named_outputs_section="").strip()

    # Build named outputs section
    outputs_list = ", ".join(f"`{name}`" for name in sorted(known_outputs))
    first_output = sorted(known_outputs)[0]

    named_section = NAMED_OUTPUTS_SECTION_TEMPLATE.format(
        outputs_list=outputs_list,
        first_output=first_output,
    )

    return FRAMEWORK_HINTS_OUTPUT_MODEL.format(
        named_outputs_section=named_section
    ).strip()


def _build_channel_hints(
    registry: Registry,
    extra_context: dict | None = None,
) -> str:
    """Build channel communication hints when channel tools are registered.

    Two paths:
    - SubAgentChannel (queue): pre-defined, listed statically in prompt
    - AgentChannel (broadcast): dynamic, seed prompt with current listing

    Channel info can be provided via extra_context["channels"] (list of dicts
    with name, type, description) or auto-detected from the session.
    """
    tool_names = set(registry.list_tools())
    has_send = "send_message" in tool_names
    has_wait = "wait_channel" in tool_names

    if not has_send and not has_wait:
        return ""

    # Get channel info from extra_context or empty
    channels: list[dict[str, str]] = []
    if extra_context and "channels" in extra_context:
        channels = extra_context["channels"]

    lines = ["## Channel Communication", ""]
    lines.append(
        "You can communicate with other agents and sub-agents through named channels."
    )
    lines.append("")

    # Split channels by type
    queue_channels = [c for c in channels if c.get("type") == "queue"]
    broadcast_channels = [c for c in channels if c.get("type") == "broadcast"]

    if queue_channels:
        lines.append("**Queue channels** (point-to-point, one consumer per message):")
        for ch in queue_channels:
            desc = f" — {ch['description']}" if ch.get("description") else ""
            lines.append(f"- `{ch['name']}`{desc}")
        lines.append("")

    if broadcast_channels:
        lines.append("**Broadcast channels** (all subscribers receive every message):")
        for ch in broadcast_channels:
            desc = f" — {ch['description']}" if ch.get("description") else ""
            lines.append(f"- `{ch['name']}`{desc}")
        lines.append("")

    if not channels:
        lines.append(
            "No channels are pre-configured. You can create queue channels "
            "on-the-fly by sending to any channel name."
        )
        lines.append("")

    # Usage guidance
    lines.append("**Usage:**")
    if has_send:
        lines.append(
            "- Send: `[/send_message]@@channel=name\\nYour message[send_message/]`"
        )
    if has_wait:
        lines.append("- Receive: `[/wait_channel]@@channel=name[wait_channel/]`")
    lines.append(
        "- Queue channels can be created on-the-fly. "
        "Broadcast channels must already exist."
    )

    return "\n".join(lines)


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
