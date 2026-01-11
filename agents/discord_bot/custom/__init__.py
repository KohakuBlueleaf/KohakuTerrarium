"""
Custom Discord modules for the group chat bot.

This package provides:
- DiscordInputModule: Receives messages from Discord
- DiscordOutputModule: Sends messages to Discord
- DiscordPingTrigger: Fires when bot is mentioned
- DiscordIdleTrigger: Fires after chat inactivity

The input module registers a Discord client to a shared registry,
which allows the output module and triggers to access the same
connection without needing to be explicitly linked.
"""

from .discord_io import (
    DiscordClient,
    DiscordInputModule,
    DiscordMessage,
    DiscordOutputModule,
    create_discord_io,
)
from .discord_trigger import (
    DiscordActivityMonitor,
    DiscordIdleTrigger,
    DiscordPingTrigger,
)

__all__ = [
    "DiscordClient",
    "DiscordInputModule",
    "DiscordOutputModule",
    "DiscordMessage",
    "DiscordPingTrigger",
    "DiscordIdleTrigger",
    "DiscordActivityMonitor",
    "create_discord_io",
]
