"""Info tool - load full documentation for a tool or sub-agent on demand."""

from pathlib import Path
from typing import Any

from kohakuterrarium.builtin_skills import (
    get_builtin_subagent_doc,
    get_builtin_tool_doc,
)
from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.modules.tool.base import (
    BaseTool,
    ExecutionMode,
    ToolContext,
    ToolResult,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@register_builtin("info")
class InfoTool(BaseTool):
    """Load full documentation for a tool or sub-agent."""

    needs_context = True

    @property
    def tool_name(self) -> str:
        return "info"

    @property
    def description(self) -> str:
        return "Get full documentation for a tool or sub-agent by name"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(
        self, args: dict[str, Any], context: ToolContext | None = None
    ) -> ToolResult:
        """Load documentation for the named tool or sub-agent."""
        name = args.get("name", args.get("content", "")).strip()

        if not name:
            return ToolResult(error="Provide the name of a tool or sub-agent.")

        # 1. Try builtin tool docs
        doc = get_builtin_tool_doc(name)
        if doc:
            logger.debug("Loaded tool doc", tool_name=name)
            return ToolResult(output=doc, exit_code=0)

        # 2. Try builtin sub-agent docs
        doc = get_builtin_subagent_doc(name)
        if doc:
            logger.debug("Loaded subagent doc", subagent_name=name)
            return ToolResult(output=doc, exit_code=0)

        # 3. Try agent-local docs
        if context and hasattr(context, "working_dir"):
            for subdir in ["prompts/tools", "prompts/subagents"]:
                doc_path = Path(context.working_dir) / subdir / f"{name}.md"
                if doc_path.exists():
                    return ToolResult(
                        output=doc_path.read_text(encoding="utf-8"),
                        exit_code=0,
                    )

        # 4. Try tool's own get_full_documentation
        if context and context.session:
            # Access registry through the agent if possible
            pass

        return ToolResult(
            error=f"No documentation found for '{name}'. "
            "Check the tool/sub-agent name and try again."
        )

    def get_full_documentation(self, tool_format: str = "native") -> str:
        return """# info

Get full documentation for any tool or sub-agent.

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| name | string | Name of the tool or sub-agent to look up |

## Behavior

- Checks builtin tool docs first, then builtin sub-agent docs.
- Falls back to agent-local docs in prompts/tools/ or prompts/subagents/.
- Returns an error if no documentation is found for the given name.

## Notes

Use this when you need to understand a tool's full parameter set
or learn about edge cases. The tool list in your system prompt shows
one-line descriptions; this gives you the complete reference.
"""
