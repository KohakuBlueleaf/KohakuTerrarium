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
        message = args.get("message", "") or args.get("content", "")
        channel_type = args.get("channel_type", "queue")
        reply_to = args.get("reply_to", None) or None

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

        # Resolve channel: private session first, shared environment second
        channel = None
        chan_registry = None

        # 1. Check creature's private channels (sub-agent channels)
        if context and context.session:
            chan_registry = context.session.channels
            channel = chan_registry.get(channel_name)

        # 2. Check environment's shared channels (inter-creature channels)
        if channel is None and context and context.environment:
            channel = context.environment.shared_channels.get(channel_name)
            if channel is not None:
                chan_registry = context.environment.shared_channels

        # 3. Fallback for no-context usage (standalone / testing)
        if channel is None and not context:
            fallback_registry = get_channel_registry()
            channel = fallback_registry.get(channel_name)
            if channel is None:
                channel = fallback_registry.get_or_create(
                    channel_name, channel_type=channel_type
                )
            chan_registry = fallback_registry

        # 4. For broadcast channels that don't exist yet, error with listing
        if channel is None and channel_type == "broadcast":
            available: list[dict[str, str]] = []
            if context and context.session:
                available.extend(context.session.channels.get_channel_info())
            if context and context.environment:
                available.extend(context.environment.shared_channels.get_channel_info())
            avail_str = (
                ", ".join(f"`{c['name']}` ({c['type']})" for c in available) or "none"
            )
            return ToolResult(
                error=(
                    f"Broadcast channel '{channel_name}' does not exist. "
                    f"Available channels: {avail_str}"
                )
            )

        # 5. Auto-create queue in private session (for sub-agent use)
        if channel is None and context and context.session:
            # Validate: warn if a shared channel has the same name
            if context.environment:
                conflict = context.environment.shared_channels.get(channel_name)
                if conflict is not None:
                    return ToolResult(
                        error=(
                            f"Channel '{channel_name}' exists in shared scope. "
                            f"Use a unique name for private channels."
                        )
                    )
            channel = context.session.channels.get_or_create(
                channel_name, channel_type=channel_type
            )
            chan_registry = context.session.channels

        # Send message
        msg = ChannelMessage(
            sender=sender,
            content=message,
            metadata=metadata,
            reply_to=reply_to,
        )
        await channel.send(msg)

        logger.debug("Message sent", channel=channel_name, sender=sender)
        content_preview = message[:60].replace("\n", " ")
        return ToolResult(
            output=(
                f"Delivered to '{channel_name}' (id: {msg.message_id}). "
                f"Content: \"{content_preview}{'...' if len(message) > 60 else ''}\". "
                f"Message delivered successfully, no further action needed for this send."
            ),
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
| channel_type | @@arg | Channel type: "queue" (default) or "broadcast" |
| reply_to | @@arg | Optional message ID to reply to (for threading) |

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

Reply to a previous message:
```
[/send_message]
@@channel=inbox_agent_b
@@reply_to=msg_abc123def456
Here are the results you requested.
[send_message/]
```

Broadcast channel:
```
[/send_message]
@@channel=status_updates
@@channel_type=broadcast
Build completed successfully.
[send_message/]
```

## Output

Confirmation that message was sent, including the generated message ID.
"""
