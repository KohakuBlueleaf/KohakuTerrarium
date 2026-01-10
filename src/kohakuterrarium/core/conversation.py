"""
Conversation management for KohakuTerrarium.

Handles message history, context length tracking, and serialization.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from kohakuterrarium.llm.message import (
    Message,
    MessageList,
    Role,
    create_message,
    messages_to_dicts,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ConversationConfig:
    """
    Configuration for conversation management.

    Attributes:
        max_messages: Maximum number of messages to keep (0 = unlimited)
        max_context_chars: Maximum context length in characters (0 = unlimited)
        keep_system: Always keep system message(s) even when truncating
    """

    max_messages: int = 0
    max_context_chars: int = 0
    keep_system: bool = True


@dataclass
class ConversationMetadata:
    """Metadata about a conversation."""

    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    message_count: int = 0
    total_chars: int = 0


class Conversation:
    """
    Manages a conversation with message history and context tracking.

    Supports:
    - Adding messages (system, user, assistant, tool)
    - Context length tracking
    - Serialization to/from JSON
    - Message truncation when context grows too large

    Usage:
        conv = Conversation()
        conv.append("system", "You are a helpful assistant.")
        conv.append("user", "Hello!")
        conv.append("assistant", "Hi! How can I help?")

        # Get messages for API call
        messages = conv.to_messages()

        # Check context length
        print(f"Context: {conv.get_context_length()} chars")
    """

    def __init__(self, config: ConversationConfig | None = None):
        """
        Initialize a conversation.

        Args:
            config: Optional configuration for context management
        """
        self.config = config or ConversationConfig()
        self._messages: MessageList = []
        self._metadata = ConversationMetadata()

    def append(
        self,
        role: Role | str,
        content: str,
        **kwargs: Any,
    ) -> Message:
        """
        Append a message to the conversation.

        Args:
            role: Message role (system, user, assistant, tool)
            content: Message content
            **kwargs: Additional message parameters (name, tool_call_id, etc.)

        Returns:
            The created Message object
        """
        msg = create_message(role, content, **kwargs)  # type: ignore
        self._messages.append(msg)

        # Update metadata
        self._metadata.message_count += 1
        self._metadata.total_chars += len(content)
        self._metadata.updated_at = datetime.now()

        logger.debug(
            "Message appended",
            role=role,
            content_length=len(content),
            total_messages=len(self._messages),
        )

        # Check if truncation needed
        self._maybe_truncate()

        return msg

    def append_message(self, message: Message) -> None:
        """Append an existing Message object."""
        self._messages.append(message)
        self._metadata.message_count += 1
        self._metadata.total_chars += len(message.content)
        self._metadata.updated_at = datetime.now()
        self._maybe_truncate()

    def _maybe_truncate(self) -> None:
        """Truncate messages if limits exceeded."""
        if self.config.max_messages <= 0 and self.config.max_context_chars <= 0:
            return

        # Keep system messages if configured
        system_messages: list[Message] = []
        other_messages: list[Message] = []

        if self.config.keep_system:
            for msg in self._messages:
                if msg.role == "system":
                    system_messages.append(msg)
                else:
                    other_messages.append(msg)
        else:
            other_messages = list(self._messages)

        # Truncate by message count
        if self.config.max_messages > 0:
            max_other = self.config.max_messages - len(system_messages)
            if len(other_messages) > max_other:
                other_messages = other_messages[-max_other:]
                logger.debug("Truncated by message count", kept=len(other_messages))

        # Truncate by context chars
        if self.config.max_context_chars > 0:
            total = sum(len(m.content) for m in system_messages)
            kept = []
            for msg in reversed(other_messages):
                msg_len = len(msg.content)
                if total + msg_len <= self.config.max_context_chars:
                    kept.insert(0, msg)
                    total += msg_len
                else:
                    break
            if len(kept) < len(other_messages):
                logger.debug(
                    "Truncated by context chars",
                    kept=len(kept),
                    dropped=len(other_messages) - len(kept),
                )
            other_messages = kept

        # Rebuild messages list
        self._messages = system_messages + other_messages
        self._metadata.total_chars = sum(len(m.content) for m in self._messages)

    def to_messages(self) -> list[dict[str, Any]]:
        """
        Convert conversation to OpenAI API message format.

        Returns:
            List of message dicts suitable for API calls
        """
        return messages_to_dicts(self._messages)

    def get_messages(self) -> MessageList:
        """Get the raw Message objects."""
        return list(self._messages)

    def get_context_length(self) -> int:
        """
        Get current context length in characters.

        Note: This is characters, not tokens. For token estimation,
        divide by ~4 for English text.
        """
        return sum(len(msg.content) for msg in self._messages)

    def get_last_message(self) -> Message | None:
        """Get the last message in the conversation."""
        return self._messages[-1] if self._messages else None

    def get_last_assistant_message(self) -> Message | None:
        """Get the last assistant message."""
        for msg in reversed(self._messages):
            if msg.role == "assistant":
                return msg
        return None

    def clear(self, keep_system: bool = True) -> None:
        """
        Clear the conversation history.

        Args:
            keep_system: If True, keep system messages
        """
        if keep_system:
            self._messages = [m for m in self._messages if m.role == "system"]
        else:
            self._messages = []

        self._metadata.message_count = len(self._messages)
        self._metadata.total_chars = sum(len(m.content) for m in self._messages)
        logger.debug("Conversation cleared", kept_messages=len(self._messages))

    def __len__(self) -> int:
        """Return number of messages."""
        return len(self._messages)

    def __bool__(self) -> bool:
        """Return True if conversation has messages."""
        return len(self._messages) > 0

    # Serialization

    def to_json(self) -> str:
        """Serialize conversation to JSON string."""
        data = {
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "name": msg.name,
                    "tool_call_id": msg.tool_call_id,
                    "metadata": msg.metadata,
                }
                for msg in self._messages
            ],
            "metadata": {
                "created_at": self._metadata.created_at.isoformat(),
                "updated_at": self._metadata.updated_at.isoformat(),
                "message_count": self._metadata.message_count,
                "total_chars": self._metadata.total_chars,
            },
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "Conversation":
        """Deserialize conversation from JSON string."""
        data = json.loads(json_str)
        conv = cls()

        for msg_data in data.get("messages", []):
            msg = create_message(
                role=msg_data["role"],
                content=msg_data["content"],
                name=msg_data.get("name"),
                tool_call_id=msg_data.get("tool_call_id"),
            )
            msg.metadata = msg_data.get("metadata", {})
            conv._messages.append(msg)

        if "metadata" in data:
            meta = data["metadata"]
            conv._metadata = ConversationMetadata(
                created_at=datetime.fromisoformat(meta["created_at"]),
                updated_at=datetime.fromisoformat(meta["updated_at"]),
                message_count=meta["message_count"],
                total_chars=meta["total_chars"],
            )

        return conv

    def __repr__(self) -> str:
        return (
            f"Conversation(messages={len(self._messages)}, "
            f"context_chars={self.get_context_length()})"
        )
