"""Clear command — clear conversation history."""

from kohakuterrarium.builtins.user_commands import register_user_command
from kohakuterrarium.modules.user_command.base import (
    BaseUserCommand,
    CommandLayer,
    UserCommandContext,
    UserCommandResult,
)


@register_user_command("clear")
class ClearCommand(BaseUserCommand):
    name = "clear"
    aliases = []
    description = "Clear conversation history"
    layer = CommandLayer.AGENT

    async def _execute(
        self, args: str, context: UserCommandContext
    ) -> UserCommandResult:
        if not context.agent:
            return UserCommandResult(error="No agent context.")
        context.agent.controller.conversation.clear()
        return UserCommandResult(output="Conversation cleared.")
