"""
LLM Provider protocol and base types.

Defines the interface that all LLM providers must implement.
The interface is OpenAI API-oriented for consistency.
"""

from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from kohakuterrarium.llm.message import Message


@dataclass
class LLMConfig:
    """
    Configuration for an LLM provider.

    Attributes:
        model: Model identifier (e.g., "gpt-4o-mini", "claude-3-opus")
        temperature: Sampling temperature (0.0 to 2.0)
        max_tokens: Maximum tokens to generate
        top_p: Nucleus sampling parameter
        stop: Stop sequences
        extra: Provider-specific extra parameters
    """

    model: str
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    stop: list[str] | None = None
    extra: dict[str, Any] | None = None


@dataclass
class ChatChunk:
    """
    A chunk from a streaming chat response.

    Attributes:
        content: The text content of this chunk
        finish_reason: If this is the final chunk, the reason for finishing
        usage: Token usage info (usually only in final chunk)
    """

    content: str = ""
    finish_reason: str | None = None
    usage: dict[str, int] | None = None


@dataclass
class ChatResponse:
    """
    Complete chat response (for non-streaming).

    Attributes:
        content: The full response text
        finish_reason: Reason for stopping generation
        usage: Token usage statistics
        model: Model that generated the response
    """

    content: str
    finish_reason: str
    usage: dict[str, int]
    model: str


@runtime_checkable
class LLMProvider(Protocol):
    """
    Protocol for LLM providers.

    All LLM implementations must follow this interface.
    The interface is OpenAI API-oriented but can wrap other providers.
    """

    async def chat(
        self,
        messages: list[Message] | list[dict[str, Any]],
        *,
        stream: bool = True,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """
        Send a chat request to the LLM.

        Args:
            messages: List of conversation messages (Message objects or dicts)
            stream: Whether to stream the response
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Yields:
            Text chunks as they arrive (if streaming)

        Returns:
            Full response text (if not streaming, via single yield)

        Usage:
            # Streaming
            async for chunk in provider.chat(messages, stream=True):
                print(chunk, end="")

            # Non-streaming
            async for response in provider.chat(messages, stream=False):
                full_text = response
        """
        ...

    async def chat_complete(
        self,
        messages: list[Message] | list[dict[str, Any]],
        **kwargs: Any,
    ) -> ChatResponse:
        """
        Send a chat request and get complete response.

        Non-streaming convenience method.

        Args:
            messages: List of conversation messages
            **kwargs: Additional parameters

        Returns:
            Complete ChatResponse with content and metadata
        """
        ...


class BaseLLMProvider:
    """
    Base class for LLM providers with common utilities.

    Provides default implementations and helper methods.
    Subclasses should implement _stream_chat and _complete_chat.
    """

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig(model="gpt-4o-mini")

    def _normalize_messages(
        self,
        messages: list[Message] | list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Convert messages to API format."""
        if not messages:
            return []

        # Check if already dicts
        if isinstance(messages[0], dict):
            return messages  # type: ignore

        # Convert Message objects to dicts
        return [msg.to_dict() for msg in messages]  # type: ignore

    async def chat(
        self,
        messages: list[Message] | list[dict[str, Any]],
        *,
        stream: bool = True,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Default chat implementation that delegates to subclass methods."""
        normalized = self._normalize_messages(messages)

        if stream:
            async for chunk in self._stream_chat(normalized, **kwargs):
                yield chunk
        else:
            response = await self._complete_chat(normalized, **kwargs)
            yield response.content

    async def chat_complete(
        self,
        messages: list[Message] | list[dict[str, Any]],
        **kwargs: Any,
    ) -> ChatResponse:
        """Default complete implementation."""
        normalized = self._normalize_messages(messages)
        return await self._complete_chat(normalized, **kwargs)

    async def _stream_chat(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """
        Stream chat implementation. Must be overridden by subclass.
        """
        raise NotImplementedError("Subclass must implement _stream_chat")
        yield  # Make this a generator

    async def _complete_chat(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> ChatResponse:
        """
        Complete chat implementation. Must be overridden by subclass.
        """
        raise NotImplementedError("Subclass must implement _complete_chat")
