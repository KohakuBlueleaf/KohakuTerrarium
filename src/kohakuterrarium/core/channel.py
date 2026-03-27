"""
Named async channel system for cross-component communication.

Provides a simple pub/sub-like mechanism where components can send and receive
messages through named channels, enabling decoupled communication between
agents, tools, and other framework components.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ChannelMessage:
    """A message sent through a channel."""

    sender: str
    content: str | dict
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class Channel:
    """Named async channel for cross-component communication."""

    def __init__(self, name: str, maxsize: int = 0):
        self.name = name
        self._queue: asyncio.Queue[ChannelMessage] = asyncio.Queue(maxsize=maxsize)

    async def send(self, message: ChannelMessage) -> None:
        """Send a message to the channel."""
        await self._queue.put(message)
        logger.debug(
            "Message sent on channel '%s' from '%s'",
            self.name,
            message.sender,
        )

    async def receive(self, timeout: float | None = None) -> ChannelMessage:
        """Receive a message from the channel. Blocks until available.

        Args:
            timeout: Maximum seconds to wait. None means wait indefinitely.

        Returns:
            The next ChannelMessage from the channel.

        Raises:
            asyncio.TimeoutError: If timeout is exceeded before a message arrives.
        """
        if timeout is not None:
            message = await asyncio.wait_for(self._queue.get(), timeout=timeout)
        else:
            message = await self._queue.get()
        logger.debug(
            "Message received on channel '%s' from '%s'",
            self.name,
            message.sender,
        )
        return message

    def try_receive(self) -> ChannelMessage | None:
        """Non-blocking receive. Returns None if the channel is empty."""
        try:
            message = self._queue.get_nowait()
            logger.debug(
                "Message received (non-blocking) on channel '%s' from '%s'",
                self.name,
                message.sender,
            )
            return message
        except asyncio.QueueEmpty:
            return None

    @property
    def empty(self) -> bool:
        """Whether the channel has no pending messages."""
        return self._queue.empty()

    @property
    def qsize(self) -> int:
        """Approximate number of messages in the channel."""
        return self._queue.qsize()


class ChannelRegistry:
    """Registry of named channels."""

    def __init__(self) -> None:
        self._channels: dict[str, Channel] = {}

    def get_or_create(self, name: str, maxsize: int = 0) -> Channel:
        """Get an existing channel or create a new one.

        Args:
            name: The channel name.
            maxsize: Maximum queue size for a newly created channel.
                     Ignored if the channel already exists.

        Returns:
            The existing or newly created Channel.
        """
        if name not in self._channels:
            self._channels[name] = Channel(name, maxsize=maxsize)
            logger.debug("Created channel '%s'", name)
        return self._channels[name]

    def get(self, name: str) -> Channel | None:
        """Get a channel by name, or None if it does not exist."""
        return self._channels.get(name)

    def list_channels(self) -> list[str]:
        """List all registered channel names."""
        return list(self._channels.keys())

    def remove(self, name: str) -> bool:
        """Remove a channel from the registry.

        Args:
            name: The channel name to remove.

        Returns:
            True if the channel existed and was removed, False otherwise.
        """
        if name in self._channels:
            del self._channels[name]
            logger.debug("Removed channel '%s'", name)
            return True
        return False


_default_registry: ChannelRegistry | None = None


def get_channel_registry() -> ChannelRegistry:
    """Get or create the default channel registry singleton."""
    global _default_registry
    if _default_registry is None:
        _default_registry = ChannelRegistry()
    return _default_registry
