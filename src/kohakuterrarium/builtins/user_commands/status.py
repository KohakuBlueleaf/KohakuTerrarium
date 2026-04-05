"""Status command — show agent/session info."""

from kohakuterrarium.builtins.user_commands import register_user_command
from kohakuterrarium.modules.user_command.base import (
    BaseUserCommand,
    CommandLayer,
    UserCommandContext,
    UserCommandResult,
)


@register_user_command("status")
class StatusCommand(BaseUserCommand):
    name = "status"
    aliases = ["info"]
    description = "Show agent/session status"
    layer = CommandLayer.AGENT

    async def _execute(
        self, args: str, context: UserCommandContext
    ) -> UserCommandResult:
        if not context.agent:
            return UserCommandResult(error="No agent context.")

        agent = context.agent
        model = getattr(agent.llm, "model", "unknown")
        msgs = len(agent.controller.conversation.get_messages())
        tools = len(agent.registry.list_tools())
        running_jobs = len(agent.executor.get_running_jobs())
        compacting = (
            agent.compact_manager.is_compacting if agent.compact_manager else False
        )

        lines = [
            f"Agent:     {agent.config.name}",
            f"Model:     {model}",
            f"Messages:  {msgs}",
            f"Tools:     {tools}",
            f"Jobs:      {running_jobs} running",
            f"Compacting: {'yes' if compacting else 'no'}",
        ]
        return UserCommandResult(output="\n".join(lines))
