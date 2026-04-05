"""Help command — list available slash commands."""

from kohakuterrarium.builtins.user_commands import register_user_command
from kohakuterrarium.modules.user_command.base import (
    BaseUserCommand,
    CommandLayer,
    UserCommandContext,
    UserCommandResult,
)


@register_user_command("help")
class HelpCommand(BaseUserCommand):
    name = "help"
    aliases = ["h", "?"]
    description = "Show available commands"
    layer = CommandLayer.INPUT

    async def _execute(
        self, args: str, context: UserCommandContext
    ) -> UserCommandResult:
        registry = context.extra.get("command_registry")
        if not registry:
            return UserCommandResult(output="No commands available.")

        lines = ["Available commands:", ""]
        for cmd in registry.values():
            alias_str = ""
            if cmd.aliases:
                alias_str = f" (aliases: {', '.join('/' + a for a in cmd.aliases)})"
            lines.append(f"  /{cmd.name:<12} {cmd.description}{alias_str}")
        lines.append("")
        return UserCommandResult(output="\n".join(lines))
