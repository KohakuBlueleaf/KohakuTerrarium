"""
Send message tool - send to a named channel.
"""

import json
from typing import Any

from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.core.channel import ChannelMessage, get_channel_registry
from kohakuterrarium.modules.tool.base import (
    BaseTool,
    ExecutionMode,
    ToolContext,
    ToolResult,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@register_builtin("send_message")
class SendMessageTool(BaseTool):
    """Send a message to a named channel for agent-to-agent communication."""

    needs_context = True

    @property
    def tool_name(self) -> str:
        return "send_message"

    @property
    def description(self) -> str:
        return "Send a message to a named channel"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.DIRECT

    async def _execute(
        self, args: dict[str, Any], context: ToolContext | None = None
    ) -> ToolResult:
        """Send message to channel."""
        channel_name = args.get("channel", "")
        message = args.get("message", "")

        if not channel_name:
            return ToolResult(error="Channel name is required")
        if not message:
            return ToolResult(error="Message content is required")

        # Determine sender from context or default
        sender = "unknown"
        if context:
            sender = context.agent_name

        # Parse metadata if provided
        metadata: dict[str, Any] = {}
        raw_metadata = args.get("metadata", "")
        if raw_metadata:
            try:
                metadata = (
                    json.loads(raw_metadata)
                    if isinstance(raw_metadata, str)
                    else raw_metadata
                )
            except json.JSONDecodeError:
                pass

        # Get or create channel from context or global registry
        registry = (
            context.session.channels
            if context and context.session
            else get_channel_registry()
        )
        channel = registry.get_or_create(channel_name)

        # Send message
        msg = ChannelMessage(
            sender=sender,
            content=message,
            metadata=metadata,
        )
        await channel.send(msg)

        logger.debug("Message sent", channel=channel_name, sender=sender)
        return ToolResult(
            output=f"Message sent to channel '{channel_name}'",
            exit_code=0,
        )

    def get_full_documentation(self) -> str:
        return """# send_message

Send a message to a named channel. Used for agent-to-agent communication.

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| channel | @@arg | Channel name (required) |
| message | content | Message content (required) |
| metadata | @@arg | Optional JSON metadata |

## Examples

```
[/send_message]
@@channel=inbox_agent_b
Please research the authentication module.
[send_message/]
```

With metadata:
```
[/send_message]
@@channel=results
@@metadata={"priority": "high"}
Analysis complete. Found 3 issues.
[send_message/]
```

## Output

Confirmation that message was sent.
"""
