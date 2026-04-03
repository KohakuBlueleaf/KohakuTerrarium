"""
Phase 1 Unit Tests - Core Foundation

Tests for:
- Logging system
- TriggerEvent
- Message types
- Conversation class

These tests run offline without API keys.
"""

import json
from datetime import datetime

import pytest

from kohakuterrarium.core.conversation import Conversation, ConversationConfig
from kohakuterrarium.core.events import (
    EventType,
    TriggerEvent,
    create_error_event,
    create_tool_complete_event,
    create_user_input_event,
)
from kohakuterrarium.llm.message import (
    AssistantMessage,
    Message,
    SystemMessage,
    UserMessage,
    create_message,
    dicts_to_messages,
    messages_to_dicts,
)
from kohakuterrarium.utils.logging import get_logger


class TestLogging:
    """Tests for the logging system."""

    def test_get_logger(self):
        """Test that get_logger returns a logger."""
        logger = get_logger(__name__)
        assert logger is not None
        assert logger.name == __name__

    def test_logger_levels(self):
        """Test that all log levels work without error."""
        logger = get_logger("test.levels")
        # Should not raise
        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")
        logger.error("error message")

    def test_logger_with_extra_fields(self):
        """Test logger with extra fields."""
        logger = get_logger("test.extra")
        # Should not raise
        logger.info("message with extras", field1="value1", field2=123)


class TestTriggerEvent:
    """Tests for TriggerEvent."""

    def test_basic_event(self):
        """Test basic event creation."""
        event = TriggerEvent(type="user_input", content="Hello!")
        assert event.type == "user_input"
        assert event.content == "Hello!"
        assert event.stackable is True
        assert event.job_id is None
        assert isinstance(event.timestamp, datetime)

    def test_event_with_all_fields(self):
        """Test event with all fields populated."""
        event = TriggerEvent(
            type="tool_complete",
            content="output",
            context={"exit_code": 0},
            job_id="job_123",
            prompt_override="Custom prompt",
            stackable=False,
        )
        assert event.type == "tool_complete"
        assert event.context["exit_code"] == 0
        assert event.job_id == "job_123"
        assert event.prompt_override == "Custom prompt"
        assert event.stackable is False

    def test_event_validation(self):
        """Test that empty type raises error."""
        with pytest.raises(ValueError, match="type cannot be empty"):
            TriggerEvent(type="")

    def test_with_context(self):
        """Test with_context creates new event."""
        event = TriggerEvent(type="test", context={"a": 1})
        event2 = event.with_context(b=2)

        # Original unchanged
        assert "b" not in event.context
        # New event has both
        assert event2.context["a"] == 1
        assert event2.context["b"] == 2

    def test_event_type_constants(self):
        """Test EventType constants."""
        assert EventType.USER_INPUT == "user_input"
        assert EventType.TOOL_COMPLETE == "tool_complete"
        assert EventType.ERROR == "error"

    def test_factory_functions(self):
        """Test event factory functions."""
        # User input
        event = create_user_input_event("Hello", source="cli")
        assert event.type == EventType.USER_INPUT
        assert event.content == "Hello"
        assert event.context["source"] == "cli"

        # Tool complete
        event2 = create_tool_complete_event("job_1", "output", exit_code=0)
        assert event2.type == EventType.TOOL_COMPLETE
        assert event2.job_id == "job_1"
        assert event2.context["exit_code"] == 0

        # Error
        event3 = create_error_event("api_error", "Connection failed")
        assert event3.type == EventType.ERROR
        assert event3.stackable is False


class TestMessage:
    """Tests for Message types."""

    def test_basic_message(self):
        """Test basic Message creation."""
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_message_to_dict(self):
        """Test Message.to_dict()."""
        msg = Message(role="user", content="Hello", name="alice")
        d = msg.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "Hello"
        assert d["name"] == "alice"

    def test_message_from_dict(self):
        """Test Message.from_dict()."""
        d = {"role": "assistant", "content": "Hi there!"}
        msg = Message.from_dict(d)
        assert msg.role == "assistant"
        assert msg.content == "Hi there!"

    def test_specialized_messages(self):
        """Test specialized message classes."""
        sys_msg = SystemMessage(content="You are helpful")
        assert sys_msg.role == "system"

        user_msg = UserMessage(content="Hello")
        assert user_msg.role == "user"

        asst_msg = AssistantMessage(content="Hi!")
        assert asst_msg.role == "assistant"

    def test_create_message_factory(self):
        """Test create_message factory function."""
        msg = create_message("user", "Hello")
        assert isinstance(msg, UserMessage)

        msg2 = create_message("system", "Be helpful")
        assert isinstance(msg2, SystemMessage)

    def test_messages_conversion(self):
        """Test messages_to_dicts and dicts_to_messages."""
        messages = [
            SystemMessage("Be helpful"),
            UserMessage("Hello"),
            AssistantMessage("Hi!"),
        ]

        dicts = messages_to_dicts(messages)
        assert len(dicts) == 3
        assert all(isinstance(d, dict) for d in dicts)

        restored = dicts_to_messages(dicts)
        assert len(restored) == 3
        assert restored[0].role == "system"


class TestConversation:
    """Tests for Conversation class."""

    def test_empty_conversation(self):
        """Test empty conversation."""
        conv = Conversation()
        assert len(conv) == 0
        assert not conv
        assert conv.get_context_length() == 0

    def test_append_messages(self):
        """Test appending messages."""
        conv = Conversation()
        conv.append("system", "You are helpful")
        conv.append("user", "Hello")
        conv.append("assistant", "Hi!")

        assert len(conv) == 3
        assert conv

    def test_to_messages(self):
        """Test conversion to message dicts."""
        conv = Conversation()
        conv.append("user", "Hello")
        conv.append("assistant", "Hi!")

        messages = conv.to_messages()
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    def test_get_context_length(self):
        """Test context length calculation."""
        conv = Conversation()
        conv.append("user", "12345")  # 5 chars
        conv.append("assistant", "67890")  # 5 chars

        assert conv.get_context_length() == 10

    def test_get_last_message(self):
        """Test getting last message."""
        conv = Conversation()
        assert conv.get_last_message() is None

        conv.append("user", "Hello")
        last = conv.get_last_message()
        assert last is not None
        assert last.content == "Hello"

    def test_get_last_assistant_message(self):
        """Test getting last assistant message."""
        conv = Conversation()
        conv.append("user", "Hello")
        conv.append("assistant", "Hi!")
        conv.append("user", "How are you?")

        last_asst = conv.get_last_assistant_message()
        assert last_asst is not None
        assert last_asst.content == "Hi!"

    def test_clear_conversation(self):
        """Test clearing conversation."""
        conv = Conversation()
        conv.append("system", "System prompt")
        conv.append("user", "Hello")
        conv.append("assistant", "Hi!")

        conv.clear(keep_system=True)
        assert len(conv) == 1
        assert conv.get_messages()[0].role == "system"

        conv.clear(keep_system=False)
        assert len(conv) == 0

    def test_serialization(self):
        """Test JSON serialization."""
        conv = Conversation()
        conv.append("system", "Be helpful")
        conv.append("user", "Hello")
        conv.append("assistant", "Hi!")

        json_str = conv.to_json()
        assert isinstance(json_str, str)

        # Parse to verify valid JSON
        data = json.loads(json_str)
        assert "messages" in data
        assert len(data["messages"]) == 3

    def test_deserialization(self):
        """Test JSON deserialization."""
        conv = Conversation()
        conv.append("system", "Be helpful")
        conv.append("user", "Hello")

        json_str = conv.to_json()
        restored = Conversation.from_json(json_str)

        assert len(restored) == len(conv)
        assert restored.get_messages()[0].role == "system"
        assert restored.get_messages()[1].content == "Hello"

    def test_truncation_by_message_count(self):
        """Test truncation by message count."""
        config = ConversationConfig(max_messages=3, keep_system=True)
        conv = Conversation(config)

        conv.append("system", "System")  # kept
        conv.append("user", "Hello1")
        conv.append("assistant", "Hi1")
        conv.append("user", "Hello2")
        conv.append("assistant", "Hi2")

        # Should keep system + last 2 messages
        assert len(conv) == 3
        messages = conv.get_messages()
        assert messages[0].role == "system"


class TestConversationConfig:
    """Tests for ConversationConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = ConversationConfig()
        assert config.max_messages == 0  # unlimited
        assert config.keep_system is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = ConversationConfig(
            max_messages=100,
            keep_system=False,
        )
        assert config.max_messages == 100
        assert config.keep_system is False
