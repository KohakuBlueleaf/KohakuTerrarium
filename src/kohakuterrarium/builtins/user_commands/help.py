"""Help command — list available slash commands."""

from kohakuterrarium.builtins.user_commands import register_user_command
from kohakuterrarium.modules.user_command.base import (
    BaseUserCommand,
    CommandLayer,
    UserCommandContext,
    UserCommandResult,
    ui_list,
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
        registry = context.extra.get("command_registry", {})

        # Plain text
        lines = ["Available commands:", ""]
        items = []
        for cmd in registry.values():
            alias_str = ""
            if cmd.aliases:
                alias_str = f" (aliases: {', '.join('/' + a for a in cmd.aliases)})"
            lines.append(f"  /{cmd.name:<12} {cmd.description}{alias_str}")
            items.append(
                {
                    "label": f"/{cmd.name}",
                    "description": cmd.description,
                    "aliases": [f"/{a}" for a in cmd.aliases],
                    "layer": cmd.layer.value,
                }
            )
        lines.append("")

        return UserCommandResult(
            output="\n".join(lines),
            data=ui_list("Commands", items),
        )
