"""
LLM module - Language model providers and abstractions.

Exports:
- LLMProvider: Protocol for LLM providers
- OpenAIProvider: OpenAI/OpenRouter compatible provider
- Message types: Message, SystemMessage, UserMessage, AssistantMessage
- Native tool calling: ToolSchema, NativeToolCall, build_tool_schemas
"""

from kohakuterrarium.llm.base import (
    BaseLLMProvider,
    ChatChunk,
    ChatResponse,
    LLMConfig,
    LLMProvider,
    NativeToolCall,
    ToolSchema,
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
from kohakuterrarium.llm.tools import build_tool_schemas

__all__ = [
    # Provider protocol
    "LLMProvider",
    "BaseLLMProvider",
    "LLMConfig",
    "ChatChunk",
    "ChatResponse",
    # Native tool calling
    "ToolSchema",
    "NativeToolCall",
    "build_tool_schemas",
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
