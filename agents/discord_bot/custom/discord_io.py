"""
Discord Input/Output Module.

Combined input and output handling for Discord bot using discord.py.
This module wraps discord.py to work with the KohakuTerrarium framework.

The input and output modules share a single Discord client through a
module-level registry. This allows them to be loaded separately by
the framework while still using the same connection.
"""

import asyncio
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import discord

from kohakuterrarium.core.events import TriggerEvent
from kohakuterrarium.modules.input import BaseInputModule
from kohakuterrarium.modules.output import BaseOutputModule
from kohakuterrarium.utils.logging import get_logger

# Use kohakuterrarium namespace so logs appear with framework logger
logger = get_logger("kohakuterrarium.custom.discord_io")


# Module-level registry for sharing Discord client between input/output
# This allows separately-loaded modules to share the same connection
_shared_clients: dict[str, "DiscordClient"] = {}


def _register_client(name: str, client: "DiscordClient") -> None:
    """Register a Discord client for sharing."""
    _shared_clients[name] = client


def _get_client(name: str) -> "DiscordClient | None":
    """Get a registered Discord client."""
    return _shared_clients.get(name)


def _short_id(full_id: int) -> str:
    """Convert full ID to short form (first 4 + last 4 digits)."""
    s = str(full_id)
    if len(s) <= 8:
        return s
    return f"{s[:4]}..{s[-4:]}"


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
    timestamp: str = ""  # HH:MM format
    # Short identifiers for bot to reference
    short_msg_id: str = ""
    short_author_id: str = ""

    def __post_init__(self):
        self.short_msg_id = _short_id(self.message_id)
        self.short_author_id = _short_id(self.author_id)

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
    content_preview: str  # First 50 chars


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
        """
        Initialize Discord client.

        Args:
            channel_ids: List of channel IDs to listen to. None = all channels.
            readonly_channel_ids: Channels to observe but not respond in.
            history_limit: Number of history messages to fetch on first message.
            **kwargs: Additional discord.Client options.
        """
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

        # Track current channel for output (no auto-reply)
        self._current_channel_id: int | None = None

        # Recent messages buffer per channel (for reply references)
        self._recent_messages: dict[int, deque[RecentMessage]] = {}
        self._max_recent = max(50, history_limit)  # Keep enough for history

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
            return f"{self.user.display_name}({_short_id(self.user.id)})"
        return "Bot(unknown)"

    async def fetch_channel_history(
        self, channel: discord.TextChannel | discord.Thread
    ) -> list[str]:
        """
        Fetch recent message history from a channel.

        Returns formatted history strings for context.
        """
        if self.history_limit <= 0:
            return []

        channel_id = channel.id
        if channel_id in self._history_fetched:
            return []

        self._history_fetched.add(channel_id)

        try:
            messages = []
            async for msg in channel.history(limit=self.history_limit):
                # Skip bot's own messages
                if msg.author == self.user:
                    continue

                # Cache user
                self._user_cache[msg.author.display_name.lower()] = msg.author.id
                self._user_cache[msg.author.name.lower()] = msg.author.id

                # Track in recent messages
                if channel_id not in self._recent_messages:
                    self._recent_messages[channel_id] = deque(maxlen=self._max_recent)

                self._recent_messages[channel_id].appendleft(
                    RecentMessage(
                        message_id=msg.id,
                        short_id=_short_id(msg.id),
                        author_name=msg.author.display_name,
                        author_id=msg.author.id,
                        content_preview=msg.content[:50] if msg.content else "",
                    )
                )

                # Format for context (with timestamp)
                short_msg_id = _short_id(msg.id)
                # Format time as HH:MM (local time)
                msg_time = msg.created_at.strftime("%H:%M")
                formatted = f"[{msg_time}] [{msg.author.display_name}({short_msg_id})]: {msg.content}"
                messages.append(formatted)

            # Reverse to chronological order
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
        # Ignore messages from self
        if message.author == self.user:
            return

        # Filter by channel if configured
        all_channels = set()
        if self.channel_ids:
            all_channels.update(self.channel_ids)
        all_channels.update(self.readonly_channel_ids)

        if all_channels and message.channel.id not in all_channels:
            return

        # Cache user for mentions
        self._user_cache[message.author.display_name.lower()] = message.author.id
        self._user_cache[message.author.name.lower()] = message.author.id

        # Track recent message
        channel_id = message.channel.id
        if channel_id not in self._recent_messages:
            self._recent_messages[channel_id] = deque(maxlen=self._max_recent)

        self._recent_messages[channel_id].append(
            RecentMessage(
                message_id=message.id,
                short_id=_short_id(message.id),
                author_name=message.author.display_name,
                author_id=message.author.id,
                content_preview=message.content[:50] if message.content else "",
            )
        )

        logger.debug(
            "Discord message received",
            extra={
                "author": message.author.display_name,
                "channel": getattr(message.channel, "name", "DM"),
                "guild": message.guild.name if message.guild else "DM",
                "content_preview": message.content[:50] if message.content else "",
            },
        )

        # Check if bot is mentioned
        is_mention = self.user in message.mentions if self.user else False

        # Get mentioned user IDs
        mentioned_users = [u.id for u in message.mentions]

        # Get reply reference if exists
        reply_to_id = None
        if message.reference and message.reference.message_id:
            reply_to_id = message.reference.message_id

        # Build message object
        msg_time = message.created_at.strftime("%H:%M")
        discord_msg = DiscordMessage(
            content=message.content,
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
            timestamp=msg_time,
        )

        await self._message_queue.put(discord_msg)

    async def get_message(self) -> DiscordMessage:
        """Get next message from queue."""
        return await self._message_queue.get()

    def set_output_context(self, channel_id: int) -> None:
        """Set the target channel for output (no auto-reply)."""
        self._current_channel_id = channel_id

    def is_readonly_channel(self, channel_id: int) -> bool:
        """Check if channel is read-only."""
        return channel_id in self.readonly_channel_ids

    def find_message_id(self, reference: str, channel_id: int) -> int | None:
        """
        Find message ID from reference string.

        Reference can be:
        - Short ID like "1234..5678"
        - "#N" for Nth recent message (1-indexed, 1 = most recent)
        - Username to find their last message
        """
        if channel_id not in self._recent_messages:
            return None

        recent = self._recent_messages[channel_id]

        # #N format (1-indexed from most recent)
        if reference.startswith("#") and reference[1:].isdigit():
            n = int(reference[1:])
            if 1 <= n <= len(recent):
                return list(recent)[-(n)].message_id
            return None

        # Short ID format
        if ".." in reference:
            for msg in recent:
                if msg.short_id == reference:
                    return msg.message_id
            return None

        # Username - find their last message
        ref_lower = reference.lower()
        for msg in reversed(list(recent)):
            if msg.author_name.lower() == ref_lower:
                return msg.message_id

        return None

    def find_user_id(self, name: str) -> int | None:
        """Find user ID from name."""
        return self._user_cache.get(name.lower())

    async def send_message(
        self,
        content: str,
        channel_id: int | None = None,
        reply_to_id: int | None = None,
        mentions: list[int] | None = None,
    ) -> discord.Message | None:
        """
        Send a message to Discord.

        Args:
            content: Message content
            channel_id: Target channel (uses current if None)
            reply_to_id: Message ID to reply to (optional)
            mentions: User IDs to mention (converts to <@id>)

        Returns:
            Sent message object or None if failed
        """
        target_channel_id = channel_id or self._current_channel_id

        if not target_channel_id:
            logger.warning("No target channel for send_message")
            return None

        # Check if channel is read-only
        if self.is_readonly_channel(target_channel_id):
            logger.debug(
                "Skipping send to read-only channel",
                extra={"channel_id": target_channel_id},
            )
            return None

        # Try cache first, then fetch (threads often not in cache)
        channel = self.get_channel(target_channel_id)
        if not channel:
            try:
                channel = await self.fetch_channel(target_channel_id)
                logger.debug(
                    "Fetched channel (not in cache)",
                    extra={
                        "channel_id": target_channel_id,
                        "channel_type": type(channel).__name__,
                    },
                )
            except discord.DiscordException as e:
                logger.warning(
                    "Failed to fetch channel",
                    extra={"channel_id": target_channel_id, "error": str(e)},
                )
                return None

        # Accept TextChannel, Thread, or any messageable channel
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
            # Build reference for reply
            reference = None
            if reply_to_id:
                reference = discord.MessageReference(
                    message_id=reply_to_id,
                    channel_id=target_channel_id,
                )

            # Add mentions to content
            final_content = content
            if mentions:
                mention_strs = [f"<@{uid}>" for uid in mentions]
                final_content = " ".join(mention_strs) + " " + content

            logger.debug(
                "Sending Discord message",
                extra={
                    "channel_id": target_channel_id,
                    "reply_to": reply_to_id,
                    "mentions": mentions,
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


class DiscordInputModule(BaseInputModule):
    """
    Input module that receives messages from Discord.

    Wraps DiscordClient to produce TriggerEvents for the controller.
    Registers client to shared registry for output module to use.
    """

    def __init__(
        self,
        token: str | None = None,
        token_env: str = "DISCORD_BOT_TOKEN",
        channel_ids: list[int] | None = None,
        readonly_channel_ids: list[int] | None = None,
        history_limit: int = 20,
        client_name: str = "default",
        shared_client: DiscordClient | None = None,
    ):
        """
        Initialize Discord input.

        Args:
            token: Bot token (or use token_env)
            token_env: Environment variable name for token
            channel_ids: Channel IDs to listen and respond to
            readonly_channel_ids: Channel IDs to observe but not respond in
            history_limit: Number of messages to fetch as history on first message
            client_name: Name for shared client registry
            shared_client: Share client with output module
        """
        import os

        super().__init__()

        self.token = token or os.environ.get(token_env, "")
        if not self.token:
            raise ValueError(
                f"Discord token not provided. Set {token_env} or pass token."
            )

        self.channel_ids = channel_ids
        self.readonly_channel_ids = readonly_channel_ids
        self.history_limit = history_limit
        self.client_name = client_name

        logger.info(
            "Initializing Discord input module",
            extra={
                "token_env": token_env,
                "channel_ids": channel_ids,
                "readonly_channel_ids": readonly_channel_ids,
                "history_limit": history_limit,
            },
        )

        # Use shared client or create new one
        if shared_client:
            self.client = shared_client
            self._owns_client = False
            logger.debug("Using shared Discord client")
        else:
            self.client = DiscordClient(
                channel_ids=channel_ids,
                readonly_channel_ids=readonly_channel_ids,
                history_limit=history_limit,
            )
            self._owns_client = True
            logger.debug("Created new Discord client")

        # Register client for output module to find
        _register_client(client_name, self.client)
        logger.debug("Registered Discord client", extra={"client_name": client_name})

        self._client_task: asyncio.Task | None = None

    async def _on_start(self) -> None:
        """Start the Discord client."""
        if self._owns_client:
            logger.info("Starting Discord client...")
            # Login first (required before wait_until_ready works)
            await self.client.login(self.token)
            logger.debug("Discord client logged in")

            # Start websocket connection in background task
            self._client_task = asyncio.create_task(self.client.connect())
            logger.debug("Discord client connecting...")

            # Wait for ready using discord.py's built-in method
            await self.client.wait_until_ready()
            logger.info("Discord client is ready")

    async def _on_stop(self) -> None:
        """Stop the Discord client."""
        if self._owns_client and self._client_task:
            await self.client.close()
            self._client_task.cancel()
            try:
                await self._client_task
            except asyncio.CancelledError:
                pass

    async def get_input(self) -> TriggerEvent | None:
        """Get next Discord message as TriggerEvent."""
        if not self._running:
            return None

        try:
            # Wait for message with timeout to allow checking running state
            msg = await asyncio.wait_for(
                self.client.get_message(),
                timeout=1.0,
            )

            # Set output context (channel only, no auto-reply)
            self.client.set_output_context(channel_id=msg.channel_id)

            # Check if read-only channel
            is_readonly = self.client.is_readonly_channel(msg.channel_id)

            # Fetch history if this is first message in channel
            history_context = ""
            if msg.channel_id not in self.client._history_fetched:
                # Get channel object to fetch history
                channel = self.client.get_channel(msg.channel_id)
                if not channel:
                    try:
                        channel = await self.client.fetch_channel(msg.channel_id)
                    except discord.DiscordException:
                        channel = None

                if channel and isinstance(
                    channel, (discord.TextChannel, discord.Thread)
                ):
                    history = await self.client.fetch_channel_history(channel)
                    if history:
                        history_context = (
                            "--- Recent History ---\n"
                            + "\n".join(history)
                            + "\n--- End History ---\n\n"
                        )

            # Build context header
            # Format: [Bot:name(id)] [Server:name(1234..5678)] [#channel(1234..5678)]
            bot_identity = self.client.get_bot_identity()

            guild_part = ""
            if msg.guild_name and msg.guild_id:
                guild_short = _short_id(msg.guild_id)
                guild_part = f"[Server:{msg.guild_name}({guild_short})]"

            channel_short = _short_id(msg.channel_id)
            channel_part = f"[#{msg.channel_name}({channel_short})]"

            readonly_marker = "[READONLY] " if is_readonly else ""
            ping_marker = "[PINGED] " if msg.is_mention else ""

            # Format: [You:BotName(id)] [Server:...] [#channel:...]
            # [HH:MM] [READONLY]? [PINGED]? [Author(msgid)]: content
            identity_header = f"[You:{bot_identity}]"
            context_header = f"{identity_header} {guild_part} {channel_part}".strip()
            msg_header = f"[{msg.timestamp}] {readonly_marker}{ping_marker}[{msg.author_display_name}({msg.short_msg_id})]"

            formatted_content = (
                f"{history_context}{context_header}\n{msg_header}: {msg.content}"
            )

            return TriggerEvent(
                type="user_input",
                content=formatted_content,
                context={
                    **msg.to_context(),
                    "is_readonly": is_readonly,
                    "bot_identity": bot_identity,
                },
                stackable=True,
            )
        except asyncio.TimeoutError:
            return None

    def get_client(self) -> DiscordClient:
        """Get the Discord client for sharing with output module."""
        return self.client


class DiscordOutputModule(BaseOutputModule):
    """
    Output module that sends messages to Discord.

    Uses the shared DiscordClient from the input module to send messages.
    Looks up client from module-level registry by name.

    Supports special markers in output:
    - [reply:Username] or [reply:#N] - reply to a message
    - [@Username] - mention a user

    Supports keyword filtering to replace sensitive words with [filtered].
    """

    # Patterns for parsing output markers
    REPLY_PATTERN = re.compile(r"\[reply:([^\]]+)\]", re.IGNORECASE)
    MENTION_PATTERN = re.compile(r"\[@([^\]]+)\]")

    def __init__(
        self,
        client: DiscordClient | None = None,
        client_name: str = "default",
        filtered_keywords: list[str] | None = None,
        keywords_file: str | None = None,
    ):
        """
        Initialize Discord output.

        Args:
            client: Shared Discord client (optional, will look up from registry)
            client_name: Name to look up in shared client registry
            filtered_keywords: List of keywords to filter (replace with [filtered])
            keywords_file: Path to file containing keywords (one per line)
        """
        super().__init__()
        self.client = client
        self.client_name = client_name
        self._buffer: list[str] = []

        # Load filtered keywords
        self._filtered_keywords: set[str] = set()
        if filtered_keywords:
            self._filtered_keywords.update(kw.lower() for kw in filtered_keywords)

        if keywords_file:
            self._load_keywords_file(keywords_file)

        if self._filtered_keywords:
            logger.info(
                "Keyword filter enabled",
                extra={"keyword_count": len(self._filtered_keywords)},
            )

        logger.info(
            "Initializing Discord output module",
            extra={"client_name": client_name},
        )

    def _load_keywords_file(self, filepath: str) -> None:
        """Load keywords from file (one per line, # for comments)."""
        import os

        if not os.path.exists(filepath):
            logger.warning("Keywords file not found", extra={"path": filepath})
            return

        try:
            with open(filepath, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        self._filtered_keywords.add(line.lower())
        except OSError as e:
            logger.warning("Failed to load keywords file", extra={"error": str(e)})

    def _filter_keywords(self, content: str) -> str:
        """Replace filtered keywords with [filtered]."""
        if not self._filtered_keywords:
            return content

        result = content
        for keyword in self._filtered_keywords:
            # Case-insensitive replacement
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            result = pattern.sub("[filtered]", result)

        if result != content:
            logger.debug("Content filtered", extra={"original_len": len(content)})

        return result

    def set_client(self, client: DiscordClient) -> None:
        """Set the Discord client (for delayed initialization)."""
        self.client = client

    def _ensure_client(self) -> DiscordClient | None:
        """Get client, looking up from registry if needed."""
        if self.client is None:
            self.client = _get_client(self.client_name)
            if self.client:
                logger.debug("Retrieved Discord client from registry")
            else:
                logger.warning("Discord client not found in registry")
        return self.client

    def _parse_markers(
        self, content: str, channel_id: int
    ) -> tuple[str, int | None, list[int]]:
        """
        Parse and remove markers from content.

        Returns:
            (cleaned_content, reply_to_id, mention_ids)
        """
        client = self._ensure_client()
        if not client:
            return content, None, []

        reply_to_id = None
        mention_ids = []

        # Parse reply marker
        reply_match = self.REPLY_PATTERN.search(content)
        if reply_match:
            ref = reply_match.group(1).strip()
            reply_to_id = client.find_message_id(ref, channel_id)
            content = self.REPLY_PATTERN.sub("", content)
            if reply_to_id:
                logger.debug(
                    "Found reply reference",
                    extra={"ref": ref, "message_id": reply_to_id},
                )

        # Parse mention markers
        for match in self.MENTION_PATTERN.finditer(content):
            name = match.group(1).strip()
            user_id = client.find_user_id(name)
            if user_id:
                mention_ids.append(user_id)
                logger.debug("Found mention", extra={"name": name, "user_id": user_id})

        # Remove mention markers from content
        content = self.MENTION_PATTERN.sub("", content)

        return content.strip(), reply_to_id, mention_ids

    async def write(self, content: str) -> None:
        """Write complete message to Discord."""
        client = self._ensure_client()
        if not client:
            logger.warning("Cannot write - no Discord client available")
            return

        # Clean content (remove any formatting artifacts)
        clean_content = content.strip()
        if not clean_content:
            return

        # Filter out [SKIP] responses (bot chose not to respond)
        # [SKIP] can appear alone, at start, at end, or with other content
        if "[SKIP]" in clean_content:
            logger.debug("Skipping response (bot chose not to reply)")
            return

        # Filter out garbage/repetitive content (model hallucination)
        stripped = clean_content.replace(" ", "").replace("\n", "")

        # Filter very short non-meaningful content (just punctuation/dashes)
        if len(stripped) <= 3:
            # Allow short actual words, filter punctuation-only
            if not any(c.isalnum() for c in stripped):
                logger.debug(
                    "Filtering garbage output (short punctuation)",
                    extra={"content": clean_content},
                )
                return

        # Filter repetitive characters (any length)
        unique_chars = set(stripped)
        if len(unique_chars) <= 2 and len(stripped) > 1:
            logger.debug(
                "Filtering garbage output (repetitive chars)",
                extra={"content": clean_content[:50]},
            )
            return

        # Get current channel
        channel_id = client._current_channel_id
        if not channel_id:
            logger.warning("No current channel for output")
            return

        # Parse markers
        final_content, reply_to_id, mention_ids = self._parse_markers(
            clean_content, channel_id
        )

        if not final_content:
            return

        # Apply keyword filter
        final_content = self._filter_keywords(final_content)

        await client.send_message(
            final_content,
            reply_to_id=reply_to_id,
            mentions=mention_ids,
        )

    async def write_stream(self, chunk: str) -> None:
        """Buffer streaming chunks."""
        self._buffer.append(chunk)

    async def flush(self) -> None:
        """Send buffered content."""
        if self._buffer:
            content = "".join(self._buffer)
            self._buffer.clear()
            await self.write(content)


# Factory function to create paired input/output
def create_discord_io(
    token: str | None = None,
    token_env: str = "DISCORD_BOT_TOKEN",
    channel_ids: list[int] | None = None,
    readonly_channel_ids: list[int] | None = None,
    history_limit: int = 20,
    filtered_keywords: list[str] | None = None,
    keywords_file: str | None = None,
) -> tuple[DiscordInputModule, DiscordOutputModule]:
    """
    Create paired Discord input and output modules with shared client.

    Args:
        token: Bot token
        token_env: Environment variable for token
        channel_ids: Channels to listen and respond to
        readonly_channel_ids: Channels to observe only
        history_limit: Number of history messages to fetch on startup
        filtered_keywords: List of keywords to filter in output
        keywords_file: Path to file containing keywords to filter

    Returns:
        Tuple of (input_module, output_module)
    """
    input_module = DiscordInputModule(
        token=token,
        token_env=token_env,
        channel_ids=channel_ids,
        readonly_channel_ids=readonly_channel_ids,
        history_limit=history_limit,
    )

    output_module = DiscordOutputModule(
        client=input_module.get_client(),
        filtered_keywords=filtered_keywords,
        keywords_file=keywords_file,
    )

    return input_module, output_module
