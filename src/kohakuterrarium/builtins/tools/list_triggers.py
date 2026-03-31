"""List triggers tool - introspect active triggers on the agent."""

from typing import Any

from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.modules.tool.base import (
    BaseTool,
    ExecutionMode,
    ToolContext,
    ToolResult,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@register_builtin("list_triggers")
class ListTriggersTool(BaseTool):
    """List all active triggers on this agent."""

    needs_context = True

    @property
    def tool_name(self) -> str:
        return "list_triggers"

    @property
    def description(self) -> str:
        return "List all active triggers (channel watchers, timers, etc.)"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    def get_parameters_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    async def _execute(
        self, args: dict[str, Any], context: ToolContext | None = None
    ) -> ToolResult:
        if not context or not context.agent:
            return ToolResult(error="Agent context required")

        triggers = context.agent.trigger_manager.list()
        if not triggers:
            return ToolResult(output="No active triggers.", exit_code=0)

        lines = [f"Active triggers ({len(triggers)}):"]
        for info in triggers:
            ts = info.created_at.strftime("%H:%M:%S")
            status = "running" if info.running else "stopped"
            lines.append(
                f"  {info.trigger_id} ({info.trigger_type}) [{status}] since {ts}"
            )

        return ToolResult(output="\n".join(lines), exit_code=0)

    def get_full_documentation(self, tool_format: str = "native") -> str:
        return """# list_triggers

List all active triggers on this agent.

## Arguments

None.

## Output

Shows each trigger's ID, type, status, and creation time.

## Notes

Triggers are set up by tools like terrarium_observe, or by the
terrarium runtime for channel communication. Use this to see
what the agent is currently listening for.
"""
