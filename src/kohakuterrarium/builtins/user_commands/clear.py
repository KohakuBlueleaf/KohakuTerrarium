"""Clear command — clear conversation history."""

from kohakuterrarium.builtins.user_commands import register_user_command
from kohakuterrarium.modules.user_command.base import (
    BaseUserCommand,
    CommandLayer,
    UserCommandContext,
    UserCommandResult,
    ui_confirm,
    ui_notify,
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

        # --force skips confirmation (used by frontend after confirm dialog)
        if args.strip() == "--force":
            context.agent.controller.conversation.clear()
            return UserCommandResult(
                output="Conversation cleared.",
                data=ui_notify("Conversation cleared", level="success"),
            )

        msgs = len(context.agent.controller.conversation.get_messages())

        # CLI/TUI: clear immediately (no confirmation)
        if context.input_module:
            context.agent.controller.conversation.clear()
            return UserCommandResult(output=f"Cleared {msgs} messages.")

        # Web frontend: return confirm dialog
        return UserCommandResult(
            output=f"Clear {msgs} messages?",
            data=ui_confirm(
                f"Clear {msgs} messages from conversation history?",
                action="clear",
                action_args="--force",
            ),
        )
