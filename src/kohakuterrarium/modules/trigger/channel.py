"""Channel trigger - fires when a message arrives on a named channel."""

import asyncio
from typing import Any

from kohakuterrarium.core.channel import (
    AgentChannel,
    ChannelRegistry,
    ChannelSubscription,
    get_channel_registry,
)
from kohakuterrarium.core.events import EventType, TriggerEvent
from kohakuterrarium.modules.trigger.base import BaseTrigger
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class ChannelTrigger(BaseTrigger):
    """
    Trigger that fires when a message arrives on a named channel.

    Supports both queue (SubAgentChannel) and broadcast (AgentChannel) channels.
    For broadcast channels, a subscriber_id is used to create a subscription.

    Usage:
        trigger = ChannelTrigger(
            channel_name="inbox",
            prompt="Handle incoming message: {content}",
        )
        await trigger.start()
        event = await trigger.wait_for_trigger()
    """

    def __init__(
        self,
        channel_name: str,
        subscriber_id: str | None = None,
        prompt: str | None = None,
        filter_sender: str | None = None,
        registry: ChannelRegistry | None = None,
        session: Any | None = None,
        **options: Any,
    ):
        """
        Initialize channel trigger.

        Args:
            channel_name: Name of the channel to listen on
            subscriber_id: Subscriber ID for broadcast channels (auto-generated if None)
            prompt: Prompt template to include in event (supports {content} substitution)
            filter_sender: Only fire for messages from this sender
            registry: Optional channel registry (defaults to global singleton)
            session: Optional session whose channel registry to use
            **options: Additional options
        """
        super().__init__(prompt=prompt, **options)
        self.channel_name = channel_name
        self.subscriber_id = subscriber_id
        self.filter_sender = filter_sender
        self._registry = registry
        self._session = session
        self._subscription: ChannelSubscription | None = None

    async def _on_start(self) -> None:
        """Resolve registry on start."""
        if self._registry is None:
            if self._session is not None:
                self._registry = self._session.channels
            else:
                self._registry = get_channel_registry()
        logger.debug("Channel trigger started", channel=self.channel_name)

    async def _on_stop(self) -> None:
        """Clean up subscription and log stop."""
        if self._subscription is not None:
            self._subscription.unsubscribe()
            self._subscription = None
        logger.debug("Channel trigger stopped", channel=self.channel_name)

    async def wait_for_trigger(self) -> TriggerEvent | None:
        """Wait for a message on the channel."""
        if not self._running:
            return None

        channel = self._registry.get_or_create(self.channel_name)

        while self._running:
            try:
                # Use a timeout so we periodically check if still running
                if isinstance(channel, AgentChannel):
                    if self._subscription is None:
                        sub_id = self.subscriber_id or f"trigger_{self.channel_name}"
                        self._subscription = channel.subscribe(sub_id)
                    msg = await self._subscription.receive(timeout=1.0)
                else:
                    msg = await channel.receive(timeout=1.0)
            except asyncio.TimeoutError:
                continue

            # Filter by sender if configured
            if self.filter_sender and msg.sender != self.filter_sender:
                continue

            # Build content string
            content = msg.content if isinstance(msg.content, str) else str(msg.content)

            # Build prompt with content substitution
            event_prompt = self.prompt
            if event_prompt and "{content}" in event_prompt:
                event_prompt = event_prompt.replace("{content}", content)

            return self._create_event(
                EventType.CHANNEL_MESSAGE,
                content=event_prompt or content,
                context={
                    "sender": msg.sender,
                    "channel": self.channel_name,
                    "message_id": msg.message_id,
                    "raw_content": msg.content,
                    **msg.metadata,
                },
            )

        return None
