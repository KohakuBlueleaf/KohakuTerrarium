"""
Message types for LLM conversations.

Provides typed message structures compatible with OpenAI API format.
"""

from dataclasses import dataclass, field
from typing import Any, Literal


# Role type for type safety
Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class Message:
    """
    A single message in a conversation.

    Compatible with OpenAI API message format.

    Attributes:
        role: Message role (system, user, assistant, tool)
        content: Message content text
        name: Optional name for the message sender
        tool_call_id: For tool messages, the ID of the tool call this responds to
        metadata: Optional metadata (not sent to API, for internal use)
    """

    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to OpenAI API format dict."""
        result: dict[str, Any] = {
            "role": self.role,
            "content": self.content,
        }
        if self.name:
            result["name"] = self.name
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        """Create Message from dict (e.g., API response)."""
        return cls(
            role=data["role"],
            content=data.get("content", ""),
            name=data.get("name"),
            tool_call_id=data.get("tool_call_id"),
        )


@dataclass
class SystemMessage(Message):
    """System message that sets up the conversation context."""

    role: Role = field(default="system", init=False)

    def __init__(self, content: str, **kwargs: Any):
        super().__init__(role="system", content=content, **kwargs)


@dataclass
class UserMessage(Message):
    """User message in the conversation."""

    role: Role = field(default="user", init=False)

    def __init__(self, content: str, name: str | None = None, **kwargs: Any):
        super().__init__(role="user", content=content, name=name, **kwargs)


@dataclass
class AssistantMessage(Message):
    """Assistant message in the conversation."""

    role: Role = field(default="assistant", init=False)

    def __init__(self, content: str, name: str | None = None, **kwargs: Any):
        super().__init__(role="assistant", content=content, name=name, **kwargs)


@dataclass
class ToolMessage(Message):
    """Tool result message in the conversation."""

    role: Role = field(default="tool", init=False)

    def __init__(
        self,
        content: str,
        tool_call_id: str,
        name: str | None = None,
        **kwargs: Any,
    ):
        super().__init__(
            role="tool",
            content=content,
            tool_call_id=tool_call_id,
            name=name,
            **kwargs,
        )


# Type alias for a list of messages
MessageList = list[Message]


def messages_to_dicts(messages: MessageList) -> list[dict[str, Any]]:
    """Convert a list of Messages to OpenAI API format."""
    return [msg.to_dict() for msg in messages]


def dicts_to_messages(dicts: list[dict[str, Any]]) -> MessageList:
    """Convert OpenAI API format dicts to Messages."""
    return [Message.from_dict(d) for d in dicts]


def create_message(role: Role, content: str, **kwargs: Any) -> Message:
    """Factory function to create the appropriate Message subclass."""
    match role:
        case "system":
            return SystemMessage(content, **kwargs)
        case "user":
            return UserMessage(content, **kwargs)
        case "assistant":
            return AssistantMessage(content, **kwargs)
        case "tool":
            if "tool_call_id" not in kwargs:
                raise ValueError("ToolMessage requires tool_call_id")
            return ToolMessage(content, **kwargs)
        case _:
            return Message(role=role, content=content, **kwargs)
