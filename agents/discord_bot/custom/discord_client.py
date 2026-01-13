"""
Discord Client - Shared Discord client for input/output modules.

This module contains the core Discord client that bridges discord.py
with the KohakuTerrarium framework.
"""

import asyncio
import re
from collections import deque
from dataclasses import dataclass
from typing import Any

import discord

from kohakuterrarium.utils.logging import get_logger

logger = get_logger("kohakuterrarium.custom.discord_client")


# Module-level registry for sharing Discord client between input/output
_shared_clients: dict[str, "DiscordClient"] = {}


def register_client(name: str, client: "DiscordClient") -> None:
    """Register a Discord client for sharing."""
    _shared_clients[name] = client


def get_client(name: str) -> "DiscordClient | None":
    """Get a registered Discord client."""
    return _shared_clients.get(name)


def short_id(full_id: int) -> str:
    """Convert full ID to short form (first 4 + last 4 digits)."""
    s = str(full_id)
    if len(s) <= 8:
        return s
    return f"{s[:4]}..{s[-4:]}"


# Pattern to match Discord mentions: <@123456> or <@!123456> (nickname mention)
DISCORD_MENTION_PATTERN = re.compile(r"<@!?(\d+)>")


@dataclass
class DiscordMessage:
    """Represents a Discord message with metadata."""

    content: str
    author_id: int
    author_name: str
    author_display_name: str
    channel_id: int
    channel_name: str
    guild_id: int | None
    guild_name: str | None
    message_id: int
    is_mention: bool
    mentioned_users: list[int]
    reply_to_id: int | None
    reply_to_author: str | None = None
    reply_to_content: str | None = None
    reply_to_is_bot: bool = False
    is_bot: bool = False
    timestamp: str = ""
    short_msg_id: str = ""
    short_author_id: str = ""

    def __post_init__(self):
        self.short_msg_id = short_id(self.message_id)
        self.short_author_id = short_id(self.author_id)

    def to_context(self) -> dict[str, Any]:
        """Convert to context dict for TriggerEvent."""
        return {
            "source": "discord",
            "author_id": self.author_id,
            "author_name": self.author_name,
            "author_display_name": self.author_display_name,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "guild_id": self.guild_id,
            "guild_name": self.guild_name,
            "message_id": self.message_id,
            "short_msg_id": self.short_msg_id,
            "is_mention": self.is_mention,
            "mentioned_users": self.mentioned_users,
            "reply_to_id": self.reply_to_id,
        }


@dataclass
class RecentMessage:
    """Lightweight record of recent message for reference."""

    message_id: int
    short_id: str
    author_name: str
    author_id: int
    content_preview: str
    is_bot: bool = False


class DiscordClient(discord.Client):
    """
    Custom Discord client that bridges discord.py with KohakuTerrarium.

    Handles message receiving and sending while maintaining Discord state.
    """

    def __init__(
        self,
        channel_ids: list[int] | None = None,
        readonly_channel_ids: list[int] | None = None,
        history_limit: int = 20,
        **kwargs: Any,
    ):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        super().__init__(intents=intents, **kwargs)

        self.channel_ids = set(channel_ids) if channel_ids else None
        self.readonly_channel_ids = (
            set(readonly_channel_ids) if readonly_channel_ids else set()
        )
        self.history_limit = history_limit
        self._message_queue: asyncio.Queue[DiscordMessage] = asyncio.Queue()

        # Track current channel for output
        self._current_channel_id: int | None = None

        # Recent messages buffer per channel
        self._recent_messages: dict[int, deque[RecentMessage]] = {}
        self._max_recent = max(50, history_limit)

        # User lookup cache (name -> id)
        self._user_cache: dict[str, int] = {}

        # Track which channels have been initialized with history
        self._history_fetched: set[int] = set()

    async def on_ready(self) -> None:
        """Called when bot is connected and ready."""
        logger.info(
            "Discord client ready",
            extra={"bot_user": str(self.user), "guilds": len(self.guilds)},
        )

    def get_bot_identity(self) -> str:
        """Get bot's identity string for prompts."""
        if self.user:
            return f"{self.user.display_name}({short_id(self.user.id)})"
        return "Bot(unknown)"

    async def fetch_channel_history(
        self,
        channel: discord.TextChannel | discord.Thread,
        force: bool = False,
    ) -> list[str]:
        """Fetch recent message history from a channel."""
        if self.history_limit <= 0:
            return []

        channel_id = channel.id
        self._history_fetched.add(channel_id)

        try:
            messages = []
            async for msg in channel.history(limit=self.history_limit):
                if msg.author == self.user:
                    continue

                self._user_cache[msg.author.display_name.lower()] = msg.author.id
                self._user_cache[msg.author.name.lower()] = msg.author.id

                if channel_id not in self._recent_messages:
                    self._recent_messages[channel_id] = deque(maxlen=self._max_recent)

                self._recent_messages[channel_id].appendleft(
                    RecentMessage(
                        message_id=msg.id,
                        short_id=short_id(msg.id),
                        author_name=msg.author.display_name,
                        author_id=msg.author.id,
                        content_preview=msg.content[:100] if msg.content else "",
                        is_bot=msg.author.bot,
                    )
                )

                msg_time = msg.created_at.strftime("%Y-%m-%d %H:%M")
                parsed_content = self.parse_mentions(msg.content, msg.guild)
                bot_marker = "[BOT] " if msg.author.bot else ""
                formatted = f"[{msg_time}] {bot_marker}[{msg.author.display_name}({short_id(msg.id)})]: {parsed_content}"
                messages.append(formatted)

            messages.reverse()

            logger.info(
                "Fetched channel history",
                extra={"channel_id": channel_id, "message_count": len(messages)},
            )
            return messages

        except discord.DiscordException as e:
            logger.warning(
                "Failed to fetch history",
                extra={"channel_id": channel_id, "error": str(e)},
            )
            return []

    async def on_message(self, message: discord.Message) -> None:
        """Handle incoming messages."""
        if message.author == self.user:
            return

        all_channels = set()
        if self.channel_ids:
            all_channels.update(self.channel_ids)
        all_channels.update(self.readonly_channel_ids)

        if all_channels and message.channel.id not in all_channels:
            return

        self._user_cache[message.author.display_name.lower()] = message.author.id
        self._user_cache[message.author.name.lower()] = message.author.id

        channel_id = message.channel.id
        if channel_id not in self._recent_messages:
            self._recent_messages[channel_id] = deque(maxlen=self._max_recent)

        self._recent_messages[channel_id].append(
            RecentMessage(
                message_id=message.id,
                short_id=short_id(message.id),
                author_name=message.author.display_name,
                author_id=message.author.id,
                content_preview=message.content[:100] if message.content else "",
                is_bot=message.author.bot,
            )
        )

        is_mention = self.user in message.mentions if self.user else False
        mentioned_users = [u.id for u in message.mentions]

        # Get reply reference
        reply_to_id = None
        reply_to_author = None
        reply_to_content = None
        reply_to_is_bot = False
        if message.reference and message.reference.message_id:
            reply_to_id = message.reference.message_id
            if message.reference.cached_message:
                ref_msg = message.reference.cached_message
                reply_to_author = ref_msg.author.display_name
                reply_to_content = self.parse_mentions(ref_msg.content, message.guild)
                reply_to_is_bot = ref_msg.author.bot
            else:
                if channel_id in self._recent_messages:
                    for recent in self._recent_messages[channel_id]:
                        if recent.message_id == reply_to_id:
                            reply_to_author = recent.author_name
                            reply_to_content = recent.content_preview
                            reply_to_is_bot = recent.is_bot
                            break
                if reply_to_content is None:
                    try:
                        ref_msg = await message.channel.fetch_message(reply_to_id)
                        reply_to_author = ref_msg.author.display_name
                        reply_to_content = self.parse_mentions(
                            ref_msg.content[:100] if ref_msg.content else "",
                            message.guild,
                        )
                        reply_to_is_bot = ref_msg.author.bot
                    except discord.DiscordException:
                        pass

        parsed_content = self.parse_mentions(message.content, message.guild)
        msg_time = message.created_at.strftime("%Y-%m-%d %H:%M")

        discord_msg = DiscordMessage(
            content=parsed_content,
            author_id=message.author.id,
            author_name=message.author.name,
            author_display_name=message.author.display_name,
            channel_id=message.channel.id,
            channel_name=getattr(message.channel, "name", "DM"),
            guild_id=message.guild.id if message.guild else None,
            guild_name=message.guild.name if message.guild else None,
            message_id=message.id,
            is_mention=is_mention,
            mentioned_users=mentioned_users,
            reply_to_id=reply_to_id,
            reply_to_author=reply_to_author,
            reply_to_content=reply_to_content,
            reply_to_is_bot=reply_to_is_bot,
            is_bot=message.author.bot,
            timestamp=msg_time,
        )

        await self._message_queue.put(discord_msg)
        logger.info(
            "Message queued",
            extra={
                "author": message.author.display_name,
                "channel": getattr(message.channel, "name", "DM"),
                "queue_size": self._message_queue.qsize(),
                "is_mention": is_mention,
            },
        )

    async def get_message(self) -> DiscordMessage:
        """Get next message from queue."""
        return await self._message_queue.get()

    def set_output_context(self, channel_id: int) -> None:
        """Set the target channel for output."""
        self._current_channel_id = channel_id

    def is_readonly_channel(self, channel_id: int) -> bool:
        """Check if channel is read-only."""
        return channel_id in self.readonly_channel_ids

    def find_message_id(self, reference: str, channel_id: int) -> int | None:
        """Find message ID from reference string."""
        if channel_id not in self._recent_messages:
            return None

        recent = self._recent_messages[channel_id]

        if reference.startswith("#") and reference[1:].isdigit():
            n = int(reference[1:])
            if 1 <= n <= len(recent):
                return list(recent)[-(n)].message_id
            return None

        if ".." in reference:
            for msg in recent:
                if msg.short_id == reference:
                    return msg.message_id
            return None

        ref_lower = reference.lower()
        for msg in reversed(list(recent)):
            if msg.author_name.lower() == ref_lower:
                return msg.message_id

        return None

    def find_user_id(self, name: str) -> int | None:
        """Find user ID from name."""
        return self._user_cache.get(name.lower())

    def parse_mentions(self, content: str, guild: discord.Guild | None) -> str:
        """Convert Discord mention format to readable @Username."""
        if not content:
            return content

        def replace_mention(match: re.Match) -> str:
            user_id = int(match.group(1))

            if self.user and user_id == self.user.id:
                return f"@{self.user.display_name}"

            if guild:
                member = guild.get_member(user_id)
                if member:
                    self._user_cache[member.display_name.lower()] = user_id
                    self._user_cache[member.name.lower()] = user_id
                    return f"@{member.display_name}"

            for name, uid in self._user_cache.items():
                if uid == user_id:
                    return f"@{name}"

            return f"@User({short_id(user_id)})"

        return DISCORD_MENTION_PATTERN.sub(replace_mention, content)

    async def send_message(
        self,
        content: str,
        channel_id: int | None = None,
        reply_to_id: int | None = None,
        mentions: list[int] | None = None,
    ) -> discord.Message | None:
        """Send a message to Discord."""
        target_channel_id = channel_id or self._current_channel_id

        if not target_channel_id:
            logger.warning("No target channel for send_message")
            return None

        if self.is_readonly_channel(target_channel_id):
            logger.debug(
                "Skipping send to read-only channel",
                extra={"channel_id": target_channel_id},
            )
            return None

        channel = self.get_channel(target_channel_id)
        if not channel:
            try:
                channel = await self.fetch_channel(target_channel_id)
            except discord.DiscordException as e:
                logger.warning(
                    "Failed to fetch channel",
                    extra={"channel_id": target_channel_id, "error": str(e)},
                )
                return None

        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            logger.warning(
                "Channel not messageable",
                extra={
                    "channel_id": target_channel_id,
                    "channel_type": type(channel).__name__,
                },
            )
            return None

        try:
            reference = None
            if reply_to_id:
                reference = discord.MessageReference(
                    message_id=reply_to_id,
                    channel_id=target_channel_id,
                )

            final_content = content
            if mentions:
                mention_strs = [f"<@{uid}>" for uid in mentions]
                final_content = " ".join(mention_strs) + " " + content

            logger.debug(
                "Sending Discord message",
                extra={
                    "channel_id": target_channel_id,
                    "reply_to": reply_to_id,
                    "content_preview": final_content[:50] if final_content else "",
                },
            )
            return await channel.send(final_content, reference=reference)
        except discord.DiscordException as e:
            logger.error("Failed to send Discord message", extra={"error": str(e)})
            return None

    def get_bot_user_id(self) -> int | None:
        """Get the bot's user ID."""
        return self.user.id if self.user else None

    def has_pending_messages(self) -> bool:
        """Check if there are messages waiting in the queue."""
        return not self._message_queue.empty()

    def pending_message_count(self) -> int:
        """Get the number of pending messages in queue."""
        return self._message_queue.qsize()
