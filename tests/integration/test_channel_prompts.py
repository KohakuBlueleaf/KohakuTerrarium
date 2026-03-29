"""Integration tests for channel prompt awareness.

Tests that the prompt aggregator correctly generates channel communication
hints and that tools provide helpful errors for non-existent channels.
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kohakuterrarium.core.channel import (
    AgentChannel,
    ChannelMessage,
    ChannelRegistry,
    SubAgentChannel,
)
from kohakuterrarium.core.registry import Registry
from kohakuterrarium.prompt.aggregator import (
    _build_channel_hints,
    aggregate_system_prompt,
)


# =============================================================================
# Channel Description Tests
# =============================================================================


class TestChannelDescriptions:
    """Tests for channel description field."""

    def test_subagent_channel_description(self):
        """SubAgentChannel stores description."""
        ch = SubAgentChannel("tasks", description="Task dispatch queue")
        assert ch.description == "Task dispatch queue"

    def test_agent_channel_description(self):
        """AgentChannel stores description."""
        ch = AgentChannel("discussion", description="Team group chat")
        assert ch.description == "Team group chat"

    def test_registry_passes_description(self):
        """Registry passes description to created channels."""
        reg = ChannelRegistry()
        ch = reg.get_or_create(
            "results",
            channel_type="queue",
            description="Completed task results",
        )
        assert ch.description == "Completed task results"

    def test_registry_get_channel_info(self):
        """Registry returns channel info for prompt injection."""
        reg = ChannelRegistry()
        reg.get_or_create("tasks", description="Task queue")
        reg.get_or_create(
            "events", channel_type="broadcast", description="Team events"
        )

        info = reg.get_channel_info()
        assert len(info) == 2

        tasks_info = next(c for c in info if c["name"] == "tasks")
        assert tasks_info["type"] == "queue"
        assert tasks_info["description"] == "Task queue"

        events_info = next(c for c in info if c["name"] == "events")
        assert events_info["type"] == "broadcast"
        assert events_info["description"] == "Team events"


# =============================================================================
# Channel Prompt Hints Tests
# =============================================================================


class TestChannelPromptHints:
    """Tests for _build_channel_hints in aggregator."""

    def _registry_with_channel_tools(self) -> Registry:
        """Create registry with send_message and wait_channel tools."""
        registry = Registry()
        mock_send = MagicMock()
        mock_send.tool_name = "send_message"
        mock_send.description = "Send a message to a channel"
        mock_send.get_parameters_schema.return_value = {}
        registry.register_tool(mock_send)

        mock_wait = MagicMock()
        mock_wait.tool_name = "wait_channel"
        mock_wait.description = "Wait for a channel message"
        mock_wait.get_parameters_schema.return_value = {}
        registry.register_tool(mock_wait)
        return registry

    def test_no_hints_without_channel_tools(self):
        """No channel section when channel tools not registered."""
        registry = Registry()
        result = _build_channel_hints(registry, None)
        assert result == ""

    def test_hints_with_channel_tools(self):
        """Channel section generated when channel tools registered."""
        registry = self._registry_with_channel_tools()
        result = _build_channel_hints(registry, None)

        assert "Channel Communication" in result
        assert "send_message" in result
        assert "wait_channel" in result

    def test_hints_with_queue_channels(self):
        """Queue channels listed in prompt."""
        registry = self._registry_with_channel_tools()
        channels = [
            {"name": "tasks", "type": "queue", "description": "Task dispatch"},
            {"name": "results", "type": "queue", "description": "Task results"},
        ]
        result = _build_channel_hints(registry, {"channels": channels})

        assert "Queue channels" in result
        assert "`tasks`" in result
        assert "Task dispatch" in result
        assert "`results`" in result

    def test_hints_with_broadcast_channels(self):
        """Broadcast channels listed in prompt."""
        registry = self._registry_with_channel_tools()
        channels = [
            {
                "name": "team_chat",
                "type": "broadcast",
                "description": "Group discussion",
            },
        ]
        result = _build_channel_hints(registry, {"channels": channels})

        assert "Broadcast channels" in result
        assert "`team_chat`" in result
        assert "Group discussion" in result

    def test_hints_with_mixed_channels(self):
        """Both channel types listed correctly."""
        registry = self._registry_with_channel_tools()
        channels = [
            {"name": "tasks", "type": "queue", "description": "Work items"},
            {"name": "events", "type": "broadcast", "description": "Status updates"},
        ]
        result = _build_channel_hints(registry, {"channels": channels})

        assert "Queue channels" in result
        assert "Broadcast channels" in result

    def test_hints_no_channels_configured(self):
        """When no channels configured, explains on-the-fly creation."""
        registry = self._registry_with_channel_tools()
        result = _build_channel_hints(registry, None)

        assert "No channels are pre-configured" in result
        assert "on-the-fly" in result

    def test_aggregate_includes_channel_hints(self):
        """aggregate_system_prompt includes channel section."""
        registry = self._registry_with_channel_tools()
        channels = [
            {"name": "inbox", "type": "queue", "description": "Incoming tasks"},
        ]

        result = aggregate_system_prompt(
            "You are a test agent.",
            registry,
            channels=channels,
        )

        assert "Channel Communication" in result
        assert "`inbox`" in result
        assert "Incoming tasks" in result


# =============================================================================
# Error Hint Tests (send_message to non-existent broadcast)
# =============================================================================


class TestChannelErrorHints:
    """Tests for helpful error messages on non-existent channels."""

    async def test_send_to_nonexistent_broadcast_shows_available(self):
        """Sending to non-existent broadcast channel returns error with listing."""
        from kohakuterrarium.builtins.tools.send_message import SendMessageTool
        from kohakuterrarium.core.session import Session
        from kohakuterrarium.modules.tool.base import ToolContext

        tool = SendMessageTool()
        session = Session(key="test_error")
        session.channels.get_or_create(
            "tasks", description="Task queue",
        )
        session.channels.get_or_create(
            "events",
            channel_type="broadcast",
            description="Team events",
        )

        context = ToolContext(
            agent_name="test_agent",
            session=session,
            working_dir=Path.cwd(),
        )

        result = await tool._execute(
            {
                "channel": "nonexistent",
                "message": "hello",
                "channel_type": "broadcast",
            },
            context=context,
        )

        assert result.error is not None
        assert "does not exist" in result.error
        assert "tasks" in result.error
        assert "events" in result.error

    async def test_send_to_queue_creates_on_fly(self):
        """Sending to non-existent queue channel creates it (no error)."""
        from kohakuterrarium.builtins.tools.send_message import SendMessageTool
        from kohakuterrarium.core.session import Session
        from kohakuterrarium.modules.tool.base import ToolContext

        tool = SendMessageTool()
        session = Session(key="test_queue_create")

        context = ToolContext(
            agent_name="test_agent",
            session=session,
            working_dir=Path.cwd(),
        )

        result = await tool._execute(
            {"channel": "new_channel", "message": "hello"},
            context=context,
        )

        # Queue channels auto-create, no error
        assert result.error is None
        assert "Message sent" in result.output

        # Channel was created
        ch = session.channels.get("new_channel")
        assert ch is not None
        assert ch.channel_type == "queue"
