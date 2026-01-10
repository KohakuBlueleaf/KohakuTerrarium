"""
LLM module - Language model providers and abstractions.

Exports:
- LLMProvider: Protocol for LLM providers
- OpenAIProvider: OpenAI/OpenRouter compatible provider
- Message types: Message, SystemMessage, UserMessage, AssistantMessage
"""

from kohakuterrarium.llm.base import (
    BaseLLMProvider,
    ChatChunk,
    ChatResponse,
    LLMConfig,
    LLMProvider,
)
from kohakuterrarium.llm.message import (
    AssistantMessage,
    Message,
    MessageList,
    SystemMessage,
    ToolMessage,
    UserMessage,
    create_message,
    dicts_to_messages,
    messages_to_dicts,
)
from kohakuterrarium.llm.openai import (
    OPENAI_BASE_URL,
    OPENROUTER_BASE_URL,
    OpenAIProvider,
)

__all__ = [
    # Provider protocol
    "LLMProvider",
    "BaseLLMProvider",
    "LLMConfig",
    "ChatChunk",
    "ChatResponse",
    # OpenAI provider
    "OpenAIProvider",
    "OPENAI_BASE_URL",
    "OPENROUTER_BASE_URL",
    # Message types
    "Message",
    "MessageList",
    "SystemMessage",
    "UserMessage",
    "AssistantMessage",
    "ToolMessage",
    "create_message",
    "messages_to_dicts",
    "dicts_to_messages",
]
