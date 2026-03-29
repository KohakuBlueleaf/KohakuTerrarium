"""Wait channel tool - wait for a message on a named channel."""

import asyncio
import json
from typing import Any

from kohakuterrarium.builtins.tools.registry import register_builtin
from kohakuterrarium.core.channel import AgentChannel, SubAgentChannel, get_channel_registry
from kohakuterrarium.modules.tool.base import (
    BaseTool,
    ExecutionMode,
    ToolContext,
    ToolResult,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@register_builtin("wait_channel")
class WaitChannelTool(BaseTool):
    """Wait for a message on a named channel."""

    needs_context = True

    @property
    def tool_name(self) -> str:
        return "wait_channel"

    @property
    def description(self) -> str:
        return "Wait for a message on a named channel"

    @property
    def execution_mode(self) -> ExecutionMode:
        return ExecutionMode.BACKGROUND

    async def _execute(
        self, args: dict[str, Any], context: ToolContext | None = None
    ) -> ToolResult:
        """Wait for channel message."""
        channel_name = args.get("channel", "")
        timeout = float(args.get("timeout", 30))

        if not channel_name:
            return ToolResult(error="Channel name is required")

        registry = (
            context.session.channels
            if context and context.session
            else get_channel_registry()
        )
        channel = registry.get_or_create(channel_name)

        subscription = None
        try:
            if isinstance(channel, AgentChannel):
                # For broadcast channels, subscribe using agent name
                subscriber_id = "unknown"
                if context:
                    subscriber_id = context.agent_name
                subscription = channel.subscribe(subscriber_id)
                msg = await subscription.receive(timeout=timeout)
            elif isinstance(channel, SubAgentChannel):
                msg = await channel.receive(timeout=timeout)
            else:
                msg = await channel.receive(timeout=timeout)

            # Format response
            content = msg.content
            if isinstance(content, dict):
                content = json.dumps(content, indent=2)

            output_parts = [
                f"From: {msg.sender}",
                f"Message-ID: {msg.message_id}",
                f"Content: {content}",
            ]
            if msg.reply_to:
                output_parts.append(f"Reply-To: {msg.reply_to}")
            if msg.metadata:
                output_parts.append(f"Metadata: {json.dumps(msg.metadata)}")

            logger.debug("Message received", channel=channel_name, sender=msg.sender)
            return ToolResult(output="\n".join(output_parts), exit_code=0)

        except asyncio.TimeoutError:
            return ToolResult(
                output=f"Timeout waiting for message on '{channel_name}' after {timeout}s",
                exit_code=1,
            )
        finally:
            if subscription is not None:
                subscription.unsubscribe()

    def get_full_documentation(self) -> str:
        return """# wait_channel

Wait for a message to arrive on a named channel. For request-response
patterns: send a message, then wait for reply on another channel.

Supports both queue channels (SubAgentChannel) and broadcast channels
(AgentChannel). For broadcast channels, automatically subscribes using
the agent name and unsubscribes after receiving.

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| channel | @@arg | Channel name to listen on (required) |
| timeout | @@arg | Seconds to wait (default: 30) |

## Examples

```
[/wait_channel]
@@channel=results_inbox
@@timeout=60
[wait_channel/]
```

## Output

Returns sender, message ID, content, and metadata of the received message.
On timeout, returns timeout notification with exit code 1.

## Mode

BACKGROUND - runs asynchronously, does not block other tools.
"""
