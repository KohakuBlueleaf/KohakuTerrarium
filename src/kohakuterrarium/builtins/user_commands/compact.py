"""Compact command — trigger manual context compaction."""

from kohakuterrarium.builtins.user_commands import register_user_command
from kohakuterrarium.modules.user_command.base import (
    BaseUserCommand,
    CommandLayer,
    UserCommandContext,
    UserCommandResult,
)


@register_user_command("compact")
class CompactCommand(BaseUserCommand):
    name = "compact"
    aliases = []
    description = "Compact conversation context now"
    layer = CommandLayer.AGENT

    async def _execute(
        self, args: str, context: UserCommandContext
    ) -> UserCommandResult:
        if not context.agent:
            return UserCommandResult(error="No agent context.")
        mgr = context.agent.compact_manager
        if not mgr:
            return UserCommandResult(error="Compaction not configured.")
        if mgr.is_compacting:
            return UserCommandResult(output="Compaction already in progress.")
        mgr.trigger_compact()
        return UserCommandResult(output="Compaction triggered.")
