"""
Discord Input/Output Module - Re-exports from split modules.

This file maintains backward compatibility by re-exporting all classes
from the split modules:
- discord_client.py - Shared Discord client
- discord_input.py - Input module
- discord_output.py - Output module
"""

from discord_client import (
    DiscordClient,
    DiscordMessage,
    RecentMessage,
    get_client,
    register_client,
    short_id,
)
from discord_input import DiscordInputModule
from discord_output import DiscordOutputModule, create_discord_io

__all__ = [
    "DiscordClient",
    "DiscordMessage",
    "RecentMessage",
    "DiscordInputModule",
    "DiscordOutputModule",
    "create_discord_io",
    "get_client",
    "register_client",
    "short_id",
]
