"""
Discord Input Module - Receives messages from Discord.

Wraps DiscordClient to produce TriggerEvents for the controller.
"""

import asyncio

import discord

from kohakuterrarium.core.events import TriggerEvent
from kohakuterrarium.modules.input import BaseInputModule
from kohakuterrarium.utils.logging import get_logger

from discord_client import (
    DiscordClient,
    DiscordMessage,
    register_client,
    short_id,
)

logger = get_logger("kohakuterrarium.custom.discord_input")


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
        instant_memory_file: str | None = None,
    ):
        """
        Initialize Discord input.

        Args:
            token: Bot token (or use token_env)
            token_env: Environment variable name for token
            channel_ids: Channel IDs to listen and respond to
            readonly_channel_ids: Channel IDs to observe but not respond in
            history_limit: Number of messages to fetch as history
            client_name: Name for shared client registry
            shared_client: Share client with output module
            instant_memory_file: Path to memory file to auto-inject
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
        self.instant_memory_file = instant_memory_file

        logger.info(
            "Initializing Discord input module",
            extra={
                "channel_ids": channel_ids,
                "readonly_channel_ids": readonly_channel_ids,
                "history_limit": history_limit,
            },
        )

        if shared_client:
            self.client = shared_client
            self._owns_client = False
        else:
            self.client = DiscordClient(
                channel_ids=channel_ids,
                readonly_channel_ids=readonly_channel_ids,
                history_limit=history_limit,
            )
            self._owns_client = True

        register_client(client_name, self.client)
        self._client_task: asyncio.Task | None = None

    async def _on_start(self) -> None:
        """Start the Discord client."""
        if self._owns_client:
            logger.info("Starting Discord client...")
            await self.client.login(self.token)
            self._client_task = asyncio.create_task(self.client.connect())
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

    def _read_instant_memory(self) -> str:
        """Read instant memory file content."""
        if not self.instant_memory_file:
            return ""

        try:
            from pathlib import Path

            path = Path(self.instant_memory_file)
            if not path.exists():
                return ""

            content = path.read_text(encoding="utf-8").strip()
            if not content:
                return ""

            return (
                "--- Instant Memory (auto-updated context) ---\n"
                f"{content}\n"
                "--- End Instant Memory ---\n\n"
            )
        except Exception as e:
            logger.warning(
                "Failed to read instant memory",
                extra={"path": self.instant_memory_file, "error": str(e)},
            )
            return ""

    async def get_input(self) -> TriggerEvent | None:
        """Get next Discord message(s) as TriggerEvent."""
        if not self._running:
            return None

        try:
            first_msg = await asyncio.wait_for(
                self.client.get_message(),
                timeout=1.0,
            )

            await asyncio.sleep(0.5)

            messages: list[DiscordMessage] = [first_msg]

            while True:
                try:
                    extra_msg = self.client._message_queue.get_nowait()
                    messages.append(extra_msg)
                except asyncio.QueueEmpty:
                    break

            logger.info(
                "Messages consumed from queue",
                extra={
                    "consumed_count": len(messages),
                    "authors": [m.author_display_name for m in messages],
                },
            )

            last_msg = messages[-1]
            self.client.set_output_context(channel_id=last_msg.channel_id)

            is_readonly = self.client.is_readonly_channel(last_msg.channel_id)
            any_mention = any(m.is_mention for m in messages)

            # Fetch history
            history_context = ""
            channel = self.client.get_channel(last_msg.channel_id)
            if not channel:
                try:
                    channel = await self.client.fetch_channel(last_msg.channel_id)
                except discord.DiscordException:
                    channel = None

            if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
                history = await self.client.fetch_channel_history(channel)
                if history:
                    history_context = (
                        "--- Recent History ---\n"
                        + "\n".join(history)
                        + "\n--- End History ---\n\n"
                    )

            # Build context header
            bot_identity = self.client.get_bot_identity()

            guild_part = ""
            if last_msg.guild_name and last_msg.guild_id:
                guild_short = short_id(last_msg.guild_id)
                guild_part = f"[Server:{last_msg.guild_name}({guild_short})]"

            channel_short = short_id(last_msg.channel_id)
            channel_part = f"[#{last_msg.channel_name}({channel_short})]"

            identity_header = f"[You:{bot_identity}]"
            context_header = f"{identity_header} {guild_part} {channel_part}".strip()

            # Format messages
            formatted_lines = []
            for msg in messages:
                readonly_marker = "[READONLY] " if is_readonly else ""
                ping_marker = "[PINGED] " if msg.is_mention else ""
                bot_marker = "[BOT] " if msg.is_bot else ""

                if msg.author_display_name != msg.author_name:
                    author_info = f"{msg.author_display_name}|{msg.author_name}({msg.short_author_id})"
                else:
                    author_info = f"{msg.author_name}({msg.short_author_id})"

                reply_marker = ""
                if msg.reply_to_author:
                    reply_bot = "[BOT]" if msg.reply_to_is_bot else ""
                    if msg.reply_to_content:
                        quote_preview = msg.reply_to_content[:60]
                        if len(msg.reply_to_content) > 60:
                            quote_preview += "..."
                        reply_marker = (
                            f'[→{reply_bot}{msg.reply_to_author}: "{quote_preview}"] '
                        )
                    else:
                        reply_marker = f"[→{reply_bot}{msg.reply_to_author}] "
                elif msg.reply_to_id:
                    reply_marker = f"[→msg:{short_id(msg.reply_to_id)}] "

                msg_header = f"[{msg.timestamp}] {readonly_marker}{ping_marker}{bot_marker}{reply_marker}[{author_info}]"
                formatted_lines.append(f"{msg_header}: {msg.content}")

            instant_memory = self._read_instant_memory()

            formatted_content = (
                f"{instant_memory}{history_context}{context_header}\n"
                + "\n".join(formatted_lines)
            )

            instruction_reminder = """
---
Process this message following your system prompt. You can:
- Think through the message (plain text goes to internal log only)
- Use tools/memory as needed (EVEN in read-only channels!)
- Use [/output_discord]message[output_discord/] ONLY if you want to respond
If you don't need to respond, just think or stay silent - no output_discord needed.
"""
            formatted_content += instruction_reminder

            return TriggerEvent(
                type="user_input",
                content=formatted_content,
                context={
                    **last_msg.to_context(),
                    "is_readonly": is_readonly,
                    "bot_identity": bot_identity,
                    "is_mention": any_mention,
                    "message_count": len(messages),
                },
                stackable=True,
            )
        except asyncio.TimeoutError:
            return None

    def get_client(self) -> DiscordClient:
        """Get the Discord client for sharing with output module."""
        return self.client
