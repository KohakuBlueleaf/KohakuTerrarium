"""Model command — list or switch LLM models."""

from kohakuterrarium.builtins.user_commands import register_user_command
from kohakuterrarium.modules.user_command.base import (
    BaseUserCommand,
    CommandLayer,
    UserCommandContext,
    UserCommandResult,
)


@register_user_command("model")
class ModelCommand(BaseUserCommand):
    name = "model"
    aliases = ["llm"]
    description = "List models or switch: /model [name]"
    layer = CommandLayer.AGENT

    async def _execute(
        self, args: str, context: UserCommandContext
    ) -> UserCommandResult:
        if not args:
            return self._list_models(context)
        return self._switch_model(args.strip(), context)

    def _list_models(self, context: UserCommandContext) -> UserCommandResult:
        from kohakuterrarium.llm.profiles import list_all

        entries = list_all()
        current = ""
        if context.agent:
            current = getattr(context.agent.llm, "model", "")

        lines = [f"Current model: {current}", ""]
        available = [e for e in entries if e.get("available")]
        if available:
            lines.append("Available models:")
            for e in available:
                marker = " *" if e["model"] == current else ""
                lines.append(
                    f"  {e['name']:<25} {e['model']:<35} ({e['login_provider']}){marker}"
                )
        else:
            lines.append("No models with API keys configured.")
            lines.append("Run: kt login <provider>")
        lines.append("")
        lines.append("Switch: /model <name>")
        return UserCommandResult(output="\n".join(lines))

    def _switch_model(
        self, name: str, context: UserCommandContext
    ) -> UserCommandResult:
        if not context.agent:
            return UserCommandResult(error="No agent context for model switching.")
        try:
            model = context.agent.switch_model(name)
            return UserCommandResult(output=f"Switched to: {model}")
        except ValueError as e:
            return UserCommandResult(error=str(e))
