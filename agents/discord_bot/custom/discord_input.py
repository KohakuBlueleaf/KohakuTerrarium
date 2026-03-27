"""
Discord Input Module - Receives messages from Discord.

Wraps DiscordClient to produce TriggerEvents for the controller.
Uses string.format() templates for flexible context formatting.
Supports multimodal input (images from attachments, stickers, emojis).
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Literal

import discord

from kohakuterrarium.core.events import TriggerEvent
from kohakuterrarium.llm.message import ContentPart, ImagePart, TextPart
from kohakuterrarium.modules.input import BaseInputModule
from kohakuterrarium.utils.logging import get_logger

from discord_client import (
    CustomEmoji,
    DiscordClient,
    DiscordMessage,
    MediaAttachment,
    MediaSticker,
    register_client,
    short_id,
)
from image_utils import ProcessedImage, process_multiple_images

logger = get_logger("kohakuterrarium.custom.discord_input")


class DiscordInputModule(BaseInputModule):
    """
    Input module that receives messages from Discord.

    Wraps DiscordClient to produce TriggerEvents for the controller.
    Registers client to shared registry for output module to use.
    Uses string.format() template for context formatting.
    Supports multimodal input (images from attachments, stickers, emojis).
    """

    def __init__(
        self,
        token: str | None = None,
        token_env: str = "DISCORD_BOT_TOKEN",
        channel_ids: list[int] | None = None,
        readonly_channel_ids: list[int] | None = None,
        history_limit: int = 50,
        recent_limit: int = 10,
        client_name: str = "default",
        shared_client: DiscordClient | None = None,
        instant_memory_file: str | None = None,
        context_format_file: str | None = None,
        context_files: dict[str, str] | None = None,
        # Timezone option
        timezone: str | None = None,
        # Multimodal options
        include_images: bool = False,
        include_attachments: bool = True,
        include_stickers: bool = True,
        include_emojis: bool = True,
        image_detail: Literal["auto", "low", "high"] = "low",
        max_images_per_message: int = 4,
        max_total_images: int = 10,
        gif_sample_frames: list[str] | None = None,
    ):
        """
        Initialize Discord input.

        Args:
            token: Bot token (or use token_env)
            token_env: Environment variable name for token
            channel_ids: Channel IDs to listen and respond to
            readonly_channel_ids: Channel IDs to observe but not respond in
            history_limit: Background context messages (older, for reference)
            recent_limit: Recent messages to show (newer, to respond to)
            client_name: Name for shared client registry
            shared_client: Share client with output module
            instant_memory_file: Path to memory file to auto-inject
            context_format_file: Template file for context formatting (uses str.format())
            context_files: Dict mapping template vars to file paths
                           e.g., {"character": "./memory/character.md"}
            timezone: Timezone for message timestamps (e.g., "Asia/Tokyo", "America/New_York").
                     If None, uses system local timezone.

            Multimodal options:
            include_images: Enable multimodal image input (master switch)
            include_attachments: Include image attachments
            include_stickers: Include sticker images
            include_emojis: Include custom emoji images
            image_detail: Vision model detail level ("low", "high", "auto")
            max_images_per_message: Max images to include from single message
            max_total_images: Max total images across all messages
            gif_sample_frames: Which frames to sample from GIFs
                              Default: ["first", "middle", "last"]
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
        self.recent_limit = recent_limit
        self.client_name = client_name
        self.instant_memory_file = instant_memory_file
        self.context_format_file = context_format_file
        self.context_files = context_files or {}

        # Multimodal settings
        self.include_images = include_images
        self.include_attachments = include_attachments
        self.include_stickers = include_stickers
        self.include_emojis = include_emojis
        self.image_detail: Literal["auto", "low", "high"] = image_detail
        self.max_images_per_message = max_images_per_message
        self.max_total_images = max_total_images
        self.gif_sample_frames = gif_sample_frames or ["first", "middle", "last"]

        # Load context format template (uses str.format() with {var} placeholders)
        self._context_template: str | None = None
        if context_format_file:
            self._load_context_template(context_format_file)

        # Debug output directory
        self._debug_output_dir = self._resolve_path("./debug_context")

        logger.info(
            "Initializing Discord input module",
            extra={
                "channel_ids": channel_ids,
                "readonly_channel_ids": readonly_channel_ids,
                "history_limit": history_limit,
                "recent_limit": recent_limit,
                "context_format_file": context_format_file,
                "context_files": list(context_files.keys()) if context_files else [],
                "timezone": timezone or "local",
                "multimodal": include_images,
                "image_detail": image_detail if include_images else None,
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
                timezone=timezone,
            )
            self._owns_client = True

        register_client(client_name, self.client)
        self._client_task: asyncio.Task | None = None

    def _resolve_path(self, file_path: str) -> Path:
        """Resolve path relative to this module's directory (agent folder)."""
        path = Path(file_path)
        if path.is_absolute():
            return path
        # Resolve relative to this module's directory (custom/ folder's parent = agent folder)
        module_dir = Path(__file__).parent.parent
        return module_dir / file_path

    def _load_context_template(self, template_path: str) -> None:
        """Load template from file (uses str.format() with {var} placeholders)."""
        try:
            path = self._resolve_path(template_path)
            if path.exists():
                self._context_template = path.read_text(encoding="utf-8")
                logger.debug("Loaded context template", extra={"path": str(path)})
            else:
                logger.warning(
                    "Context template file not found", extra={"path": str(path)}
                )
        except Exception as e:
            logger.error(
                "Failed to load context template",
                extra={"path": template_path, "error": str(e)},
            )

    def _load_context_file(self, file_path: str) -> str:
        """Load content from a context file."""
        try:
            path = self._resolve_path(file_path)
            if path.exists():
                return path.read_text(encoding="utf-8").strip()
            else:
                logger.warning("Context file not found", extra={"path": str(path)})
        except Exception as e:
            logger.warning(
                "Failed to load context file",
                extra={"path": file_path, "error": str(e)},
            )
        return ""

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
        """Read instant memory file content (raw, no wrapper)."""
        if not self.instant_memory_file:
            return ""
        return self._load_context_file(self.instant_memory_file)

    def _build_history_text(self, history_msgs: list[str]) -> str:
        """Format history messages with numbering."""
        if not history_msgs:
            return ""
        numbered = [f"#{i} {msg}" for i, msg in enumerate(history_msgs, 1)]
        return "\n".join(numbered)

    def _build_recent_text(self, recent_msgs: list[str], start_num: int) -> str:
        """Format recent messages with numbering and LATEST marker."""
        if not recent_msgs:
            return ""
        numbered = []
        for i, msg in enumerate(recent_msgs):
            num = start_num + i
            if i == len(recent_msgs) - 1:
                numbered.append(f"#{num} [LATEST] {msg}")
            else:
                numbered.append(f"#{num} {msg}")
        return "\n".join(numbered)

    def _build_media_markers(self, msg: DiscordMessage) -> str:
        """Build media markers for a message (attachments, stickers, emojis)."""
        markers = []

        # Image attachments
        for att in msg.attachments:
            if att.is_image:
                anim_tag = " (animated GIF)" if att.is_animated else ""
                markers.append(f"[attachment:{att.filename}{anim_tag}]")

        # Stickers
        for sticker in msg.stickers:
            anim_tag = " (animated)" if sticker.is_animated else ""
            markers.append(f"[sticker:{sticker.name}{anim_tag}]")

        # Custom emojis (only note them, don't list URLs in text)
        if msg.custom_emojis:
            emoji_names = [f":{e.name}:" for e in msg.custom_emojis]
            animated_count = sum(1 for e in msg.custom_emojis if e.animated)
            if animated_count > 0:
                markers.append(
                    f"[emojis: {', '.join(emoji_names)} ({animated_count} animated)]"
                )
            else:
                markers.append(f"[emojis: {', '.join(emoji_names)}]")

        return " ".join(markers)

    def _build_new_messages_text(
        self, messages: list[DiscordMessage], is_readonly: bool
    ) -> str:
        """Format new messages that just arrived."""
        formatted_lines = []
        for i, msg in enumerate(messages, 1):
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

            # Build media markers
            media_markers = self._build_media_markers(msg)
            media_suffix = f" {media_markers}" if media_markers else ""

            msg_header = f"[{msg.timestamp}] {readonly_marker}{ping_marker}{bot_marker}{reply_marker}[{author_info}]"
            formatted_lines.append(f"NEW#{i} {msg_header}: {msg.content}{media_suffix}")

        return "\n".join(formatted_lines)

    def _build_location(self, last_msg: DiscordMessage) -> str:
        """Build location info: bot identity, server, channel."""
        bot_identity = self.client.get_bot_identity()

        guild_part = ""
        if last_msg.guild_name and last_msg.guild_id:
            guild_short = short_id(last_msg.guild_id)
            guild_part = f"[Server:{last_msg.guild_name}({guild_short})]"

        channel_short = short_id(last_msg.channel_id)
        channel_part = f"[#{last_msg.channel_name}({channel_short})]"

        identity_header = f"[You:{bot_identity}]"
        return f"{identity_header} {guild_part} {channel_part}".strip()

    def _render_with_template(self, template_vars: dict) -> str:
        """Render context using str.format() with {var} placeholders."""
        if self._context_template:
            try:
                result = self._context_template.format(**template_vars)
                # self._save_debug_output(result)
                return result
            except KeyError as e:
                logger.error("Template missing variable", extra={"missing": str(e)})
            except Exception as e:
                logger.error("Template render failed", extra={"error": str(e)})

        # Fallback: simple concatenation if no template
        fallback = self._render_fallback(template_vars)
        # self._save_debug_output(fallback)
        return fallback

    def _save_debug_output(self, content: str) -> None:
        """Save rendered context to debug file with timestamp."""
        try:
            self._debug_output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_file = self._debug_output_dir / f"context_{timestamp}.md"
            debug_file.write_text(content, encoding="utf-8")
            logger.debug("Saved debug context", extra={"path": str(debug_file)})
        except Exception as e:
            logger.warning("Failed to save debug output", extra={"error": str(e)})

    def _render_fallback(self, vars: dict) -> str:
        """Fallback rendering when no template is configured."""
        sections = [
            ("Instant Memory", "instant_memory"),
            ("Tool History", "tool_history"),
            ("History", "history"),
            ("Recent", "recent"),
            ("Rules", "rules"),
            ("Character", "character"),
            ("Location", "location"),
        ]

        parts = []
        for header, key in sections:
            if vars.get(key):
                parts.append(f"### {header}\n\n{vars[key]}")

        parts.append(f"### New Messages\n\n{vars.get('new_messages', '')}")

        return "\n\n".join(parts)

    def _collect_image_items(
        self, messages: list[DiscordMessage]
    ) -> list[tuple[str, str, str, bool]]:
        """
        Collect image items from messages for processing.

        Returns list of (url, source_type, source_name, is_animated) tuples.
        """
        items: list[tuple[str, str, str, bool]] = []
        images_collected = 0

        for msg in messages:
            msg_images = 0

            # Attachments
            if self.include_attachments:
                for att in msg.attachments:
                    if att.is_image and msg_images < self.max_images_per_message:
                        items.append(
                            (att.url, "attachment", att.filename, att.is_animated)
                        )
                        msg_images += 1
                        images_collected += 1

            # Stickers
            if self.include_stickers:
                for sticker in msg.stickers:
                    if msg_images < self.max_images_per_message:
                        # Skip lottie stickers (vector format, not image)
                        if sticker.format_type == "lottie":
                            continue
                        items.append(
                            (
                                sticker.url,
                                "sticker",
                                sticker.name,
                                sticker.is_animated,
                            )
                        )
                        msg_images += 1
                        images_collected += 1

            # Custom emojis
            if self.include_emojis:
                for emoji in msg.custom_emojis:
                    if msg_images < self.max_images_per_message:
                        items.append((emoji.url, "emoji", emoji.name, emoji.animated))
                        msg_images += 1
                        images_collected += 1

            if images_collected >= self.max_total_images:
                break

        return items[: self.max_total_images]

    async def _process_images(self, messages: list[DiscordMessage]) -> list[ImagePart]:
        """
        Process images from messages into ImagePart objects.

        Downloads images, extracts GIF frames, converts to base64.
        """
        items = self._collect_image_items(messages)
        if not items:
            return []

        logger.debug(
            "Processing images",
            extra={"count": len(items), "types": [t for _, t, _, _ in items]},
        )

        processed = await process_multiple_images(
            items,
            max_images=self.max_total_images,
            gif_sample_positions=self.gif_sample_frames,
        )

        # Convert ProcessedImage to ImagePart
        image_parts: list[ImagePart] = []
        for img in processed:
            # Build description for source
            if img.frame_info:
                source_name = f"{img.source_name} ({img.frame_info})"
            else:
                source_name = img.source_name

            image_parts.append(
                ImagePart(
                    url=img.data_url,
                    detail=self.image_detail,
                    source_type=img.source_type,
                    source_name=source_name,
                )
            )

        logger.debug("Processed images", extra={"result_count": len(image_parts)})
        return image_parts

    def _build_multimodal_content(
        self, text: str, images: list[ImagePart]
    ) -> str | list[ContentPart]:
        """
        Build content, using multimodal format only if images present.

        Images are prepended to content with descriptions.
        """
        if not images:
            return text

        # Build content parts
        parts: list[ContentPart] = []

        # Add image descriptions as text header
        image_desc_lines = []
        for i, img in enumerate(images, 1):
            desc = img.get_description()
            image_desc_lines.append(f"Image {i}: {desc}")

        image_header = (
            "## Attached Images\n\n"
            + "\n".join(image_desc_lines)
            + "\n\n(Images shown below as visual content)\n\n"
        )

        # Add header text
        parts.append(TextPart(text=image_header))

        # Add images
        parts.extend(images)

        # Add main text content
        parts.append(TextPart(text=text))

        return parts

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

            # Fetch history from Discord
            channel = self.client.get_channel(last_msg.channel_id)
            if not channel:
                try:
                    channel = await self.client.fetch_channel(last_msg.channel_id)
                except discord.DiscordException:
                    channel = None

            # Split into history (older) and recent (newer)
            history_text = ""
            recent_text = ""
            recent_media_messages: list[DiscordMessage] = []
            if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
                all_history = await self.client.fetch_channel_history(channel)
                if all_history:
                    total = len(all_history)
                    if total > self.recent_limit:
                        history_msgs = all_history[: total - self.recent_limit]
                        recent_msgs = all_history[total - self.recent_limit :]
                    else:
                        history_msgs = []
                        recent_msgs = all_history

                    history_text = self._build_history_text(history_msgs)
                    recent_text = self._build_recent_text(
                        recent_msgs, len(history_msgs) + 1
                    )

                # Fetch recent messages with media info for image processing
                if self.include_images:
                    recent_media_messages = (
                        await self.client.fetch_channel_history_with_media(
                            channel, limit=self.recent_limit
                        )
                    )

            # Build template variables with raw content (no formatting)
            template_vars = {
                "instant_memory": self._read_instant_memory(),
                "history": history_text,
                "recent": recent_text,
                "new_messages": self._build_new_messages_text(messages, is_readonly),
                "location": self._build_location(last_msg),
                "tool_history": "",  # TODO: implement tool history tracking
            }

            # Load context files (character, rules, etc.) - raw content
            for var_name, file_path in self.context_files.items():
                template_vars[var_name] = self._load_context_file(file_path)

            # Render using template or fallback
            formatted_text = self._render_with_template(template_vars)

            # Process images if multimodal is enabled
            image_parts: list[ImagePart] = []
            if self.include_images:
                # Combine new messages with recent media messages for image processing
                # Recent media messages are from history, new messages are just arrived
                all_media_messages = recent_media_messages.copy()

                # Filter out new messages that are already in recent history (by message_id)
                recent_ids = {m.message_id for m in recent_media_messages}
                for msg in messages:
                    if msg.message_id not in recent_ids and msg.has_media():
                        all_media_messages.append(msg)

                # Check if any messages have media
                if all_media_messages:
                    image_parts = await self._process_images(all_media_messages)
                    logger.info(
                        "Processed multimodal content",
                        extra={
                            "image_count": len(image_parts),
                            "from_recent": len(recent_media_messages),
                            "from_new": len(all_media_messages)
                            - len(recent_media_messages),
                            "sources": [
                                f"{img.source_type}:{img.source_name}"
                                for img in image_parts[:5]  # Log first 5
                            ],
                        },
                    )

            # Build final content (text or multimodal)
            final_content = self._build_multimodal_content(formatted_text, image_parts)

            # Count media for context
            total_attachments = sum(len(m.attachments) for m in messages)
            total_stickers = sum(len(m.stickers) for m in messages)
            total_emojis = sum(len(m.custom_emojis) for m in messages)

            return TriggerEvent(
                type="user_input",
                content=final_content,
                context={
                    **last_msg.to_context(),
                    "is_readonly": is_readonly,
                    "bot_identity": self.client.get_bot_identity(),
                    "is_mention": any_mention,
                    "message_count": len(messages),
                    "multimodal": len(image_parts) > 0,
                    "image_count": len(image_parts),
                    "total_attachments": total_attachments,
                    "total_stickers": total_stickers,
                    "total_emojis": total_emojis,
                },
                stackable=True,
            )
        except asyncio.TimeoutError:
            return None

    def get_client(self) -> DiscordClient:
        """Get the Discord client for sharing with output module."""
        return self.client
