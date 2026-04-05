"""Exit command — graceful shutdown."""

from kohakuterrarium.builtins.user_commands import register_user_command
from kohakuterrarium.modules.user_command.base import (
    BaseUserCommand,
    CommandLayer,
    UserCommandContext,
    UserCommandResult,
)


@register_user_command("exit")
class ExitCommand(BaseUserCommand):
    name = "exit"
    aliases = ["quit", "q"]
    description = "Exit the session"
    layer = CommandLayer.INPUT

    async def _execute(
        self, args: str, context: UserCommandContext
    ) -> UserCommandResult:
        # Signal exit via the input module
        if context.input_module and hasattr(context.input_module, "_exit_requested"):
            context.input_module._exit_requested = True
        return UserCommandResult(output="", consumed=True)
