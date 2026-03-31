"""Integration tests for TerrariumAPI and ChannelObserver."""

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from kohakuterrarium.core.channel import AgentChannel, ChannelMessage, SubAgentChannel
from kohakuterrarium.core.session import Session, remove_session
from kohakuterrarium.terrarium.api import TerrariumAPI
from kohakuterrarium.terrarium.config import (
    ChannelConfig,
    CreatureConfig,
    TerrariumConfig,
)
from kohakuterrarium.terrarium.observer import ChannelObserver, ObservedMessage
from kohakuterrarium.terrarium.runtime import TerrariumRuntime

SWE_AGENT_DIR = (
    Path(__file__).resolve().parents[2] / "examples" / "agent-apps" / "swe_agent"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def terrarium_config() -> TerrariumConfig:
    """Minimal terrarium config with two creatures and mixed channels."""
    swe_path = str(SWE_AGENT_DIR.resolve())
    return TerrariumConfig(
        name="api_test",
        creatures=[
            CreatureConfig(
                name="alpha",
                config_data={"base_config": swe_path},
                base_dir=Path("."),
                listen_channels=["inbox_alpha"],
                send_channels=["outbox_alpha", "team_chat"],
            ),
            CreatureConfig(
                name="beta",
                config_data={"base_config": swe_path},
                base_dir=Path("."),
                listen_channels=["inbox_beta"],
                send_channels=["outbox_beta", "team_chat"],
            ),
        ],
        channels=[
            ChannelConfig(
                name="inbox_alpha", channel_type="queue", description="Alpha inbox"
            ),
            ChannelConfig(
                name="outbox_alpha", channel_type="queue", description="Alpha outbox"
            ),
            ChannelConfig(
                name="inbox_beta", channel_type="queue", description="Beta inbox"
            ),
            ChannelConfig(
                name="outbox_beta", channel_type="queue", description="Beta outbox"
            ),
            ChannelConfig(
                name="team_chat",
                channel_type="broadcast",
                description="Shared broadcast",
            ),
        ],
    )


@pytest.fixture(autouse=True)
def cleanup_sessions(terrarium_config: TerrariumConfig):
    """Remove session created by runtime after each test."""
    yield
    remove_session(f"terrarium_{terrarium_config.name}")


@pytest.fixture()
async def started_runtime(terrarium_config: TerrariumConfig):
    """A TerrariumRuntime that has been started (but not running creatures)."""
    runtime = TerrariumRuntime(terrarium_config)
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "fake-key-for-test"}):
        await runtime.start()
    yield runtime
    await runtime.stop()


# ---------------------------------------------------------------------------
# TerrariumAPI — channel operations
# ---------------------------------------------------------------------------


class TestAPIChannelOps:
    """Tests for channel listing, info, and send."""

    async def test_list_channels(self, started_runtime: TerrariumRuntime):
        api = started_runtime.api
        channels = await api.list_channels()
        names = {ch["name"] for ch in channels}
        assert "inbox_alpha" in names
        assert "team_chat" in names
        assert len(channels) == 5

    async def test_list_channels_before_start(self, terrarium_config: TerrariumConfig):
        runtime = TerrariumRuntime(terrarium_config)
        api = runtime.api
        assert await api.list_channels() == []

    async def test_channel_info_queue(self, started_runtime: TerrariumRuntime):
        api = started_runtime.api
        info = await api.channel_info("inbox_alpha")
        assert info is not None
        assert info["type"] == "queue"
        assert info["name"] == "inbox_alpha"
        assert "qsize" in info

    async def test_channel_info_broadcast(self, started_runtime: TerrariumRuntime):
        api = started_runtime.api
        info = await api.channel_info("team_chat")
        assert info is not None
        assert info["type"] == "broadcast"
        assert "subscriber_count" in info

    async def test_channel_info_nonexistent(self, started_runtime: TerrariumRuntime):
        api = started_runtime.api
        assert await api.channel_info("no_such_channel") is None

    async def test_send_to_queue_channel(self, started_runtime: TerrariumRuntime):
        api = started_runtime.api
        msg_id = await api.send_to_channel("inbox_alpha", "hello alpha")
        assert msg_id.startswith("msg_")

        # Verify message arrived on the queue
        ch = started_runtime._session.channels.get("inbox_alpha")
        assert isinstance(ch, SubAgentChannel)
        msg = await ch.receive(timeout=1.0)
        assert msg.content == "hello alpha"
        assert msg.sender == "human"

    async def test_send_to_broadcast_channel(self, started_runtime: TerrariumRuntime):
        api = started_runtime.api

        # Subscribe to receive the broadcast
        ch = started_runtime._session.channels.get("team_chat")
        assert isinstance(ch, AgentChannel)
        sub = ch.subscribe("test_listener")

        msg_id = await api.send_to_channel("team_chat", "broadcast msg", sender="admin")
        assert msg_id.startswith("msg_")

        received = await sub.receive(timeout=1.0)
        assert received.content == "broadcast msg"
        assert received.sender == "admin"
        sub.unsubscribe()

    async def test_send_with_metadata(self, started_runtime: TerrariumRuntime):
        api = started_runtime.api
        await api.send_to_channel(
            "inbox_alpha", "priority task", metadata={"priority": "high"}
        )
        ch = started_runtime._session.channels.get("inbox_alpha")
        msg = await ch.receive(timeout=1.0)
        assert msg.metadata["priority"] == "high"

    async def test_send_to_nonexistent_raises(self, started_runtime: TerrariumRuntime):
        api = started_runtime.api
        with pytest.raises(ValueError, match="not found"):
            await api.send_to_channel("ghost_channel", "nope")

    async def test_send_before_start_raises(self, terrarium_config: TerrariumConfig):
        runtime = TerrariumRuntime(terrarium_config)
        api = runtime.api
        with pytest.raises(ValueError, match="not running"):
            await api.send_to_channel("inbox_alpha", "fail")


# ---------------------------------------------------------------------------
# TerrariumAPI — creature operations
# ---------------------------------------------------------------------------


class TestAPICreatureOps:
    """Tests for creature listing and status."""

    async def test_list_creatures(self, started_runtime: TerrariumRuntime):
        api = started_runtime.api
        creatures = await api.list_creatures()
        names = {c["name"] for c in creatures}
        assert names == {"alpha", "beta"}
        for c in creatures:
            assert "running" in c
            assert "listen_channels" in c
            assert "send_channels" in c

    async def test_get_creature_status(self, started_runtime: TerrariumRuntime):
        api = started_runtime.api
        status = await api.get_creature_status("alpha")
        assert status is not None
        assert status["name"] == "alpha"
        assert status["listen_channels"] == ["inbox_alpha"]

    async def test_get_creature_status_nonexistent(
        self, started_runtime: TerrariumRuntime
    ):
        api = started_runtime.api
        assert await api.get_creature_status("no_creature") is None


# ---------------------------------------------------------------------------
# TerrariumAPI — terrarium operations
# ---------------------------------------------------------------------------


class TestAPITerrariumOps:
    """Tests for terrarium-level status."""

    async def test_get_status(self, started_runtime: TerrariumRuntime):
        api = started_runtime.api
        status = api.get_status()
        assert status["name"] == "api_test"
        assert status["running"] is True
        assert "alpha" in status["creatures"]
        assert "beta" in status["creatures"]
        assert len(status["channels"]) == 5

    async def test_is_running(self, started_runtime: TerrariumRuntime):
        api = started_runtime.api
        assert api.is_running is True

    async def test_is_running_before_start(self, terrarium_config: TerrariumConfig):
        runtime = TerrariumRuntime(terrarium_config)
        assert runtime.api.is_running is False


# ---------------------------------------------------------------------------
# ChannelObserver
# ---------------------------------------------------------------------------


class TestChannelObserver:
    """Tests for the non-destructive channel observer."""

    async def test_observe_broadcast_receives_messages(
        self, started_runtime: TerrariumRuntime
    ):
        """Observer on a broadcast channel receives sent messages."""
        observer = started_runtime.observer
        await observer.observe("team_chat")

        # Give the observe loop a moment to start
        await asyncio.sleep(0.05)

        # Send a message through the channel directly
        ch = started_runtime._session.channels.get("team_chat")
        await ch.send(ChannelMessage(sender="agent_a", content="hello team"))

        # Wait a bit for the observer loop to pick it up
        await asyncio.sleep(0.2)

        messages = observer.get_messages(channel="team_chat")
        assert len(messages) >= 1
        assert messages[-1].content == "hello team"
        assert messages[-1].sender == "agent_a"
        assert messages[-1].channel == "team_chat"

        await observer.stop()

    async def test_observe_broadcast_multiple_messages(
        self, started_runtime: TerrariumRuntime
    ):
        """Observer collects multiple broadcast messages."""
        observer = started_runtime.observer
        await observer.observe("team_chat")
        await asyncio.sleep(0.05)

        ch = started_runtime._session.channels.get("team_chat")
        for i in range(5):
            await ch.send(ChannelMessage(sender="bot", content=f"msg_{i}"))

        await asyncio.sleep(0.3)

        messages = observer.get_messages(channel="team_chat")
        assert len(messages) == 5
        contents = [m.content for m in messages]
        assert contents == [f"msg_{i}" for i in range(5)]

        await observer.stop()

    async def test_record_queue_messages(self, started_runtime: TerrariumRuntime):
        """Record method stores queue messages via the API path."""
        observer = started_runtime.observer
        msg = ChannelMessage(sender="human", content="recorded msg")
        observer.record("inbox_alpha", msg)

        messages = observer.get_messages(channel="inbox_alpha")
        assert len(messages) == 1
        assert messages[0].content == "recorded msg"

    async def test_get_messages_filter_by_channel(
        self, started_runtime: TerrariumRuntime
    ):
        """get_messages filters correctly by channel name."""
        observer = started_runtime.observer

        msg_a = ChannelMessage(sender="x", content="a")
        msg_b = ChannelMessage(sender="x", content="b")
        observer.record("inbox_alpha", msg_a)
        observer.record("inbox_beta", msg_b)

        alpha_msgs = observer.get_messages(channel="inbox_alpha")
        assert len(alpha_msgs) == 1
        assert alpha_msgs[0].content == "a"

        beta_msgs = observer.get_messages(channel="inbox_beta")
        assert len(beta_msgs) == 1
        assert beta_msgs[0].content == "b"

    async def test_get_messages_last_n(self, started_runtime: TerrariumRuntime):
        """get_messages respects last_n limit."""
        observer = started_runtime.observer
        for i in range(10):
            observer.record("inbox_alpha", ChannelMessage(sender="x", content=f"m{i}"))

        recent = observer.get_messages(channel="inbox_alpha", last_n=3)
        assert len(recent) == 3
        assert recent[0].content == "m7"
        assert recent[2].content == "m9"

    async def test_on_message_callback(self, started_runtime: TerrariumRuntime):
        """Registered callbacks fire for each observed message."""
        observer = started_runtime.observer
        collected: list[ObservedMessage] = []
        observer.on_message(lambda msg: collected.append(msg))

        observer.record("inbox_alpha", ChannelMessage(sender="x", content="cb_test"))
        assert len(collected) == 1
        assert collected[0].content == "cb_test"

    async def test_observer_stop_cleans_subscriptions(
        self, started_runtime: TerrariumRuntime
    ):
        """After stop(), broadcast subscriptions are cleaned up."""
        observer = started_runtime.observer
        await observer.observe("team_chat")
        await asyncio.sleep(0.05)

        await observer.stop()

        ch = started_runtime._session.channels.get("team_chat")
        assert isinstance(ch, AgentChannel)
        # The observer subscription should be removed
        assert "_observer_team_chat" not in ch._subscribers

    async def test_observe_nonexistent_channel(self, started_runtime: TerrariumRuntime):
        """Observing a non-existent channel does not crash."""
        observer = started_runtime.observer
        await observer.observe("does_not_exist")
        # No tasks created for nonexistent channel
        assert len(observer._observe_tasks) == 0
        await observer.stop()

    async def test_send_to_channel_records_in_observer(
        self, started_runtime: TerrariumRuntime
    ):
        """API send_to_channel records message in observer when active."""
        # Access observer to ensure it's created
        observer = started_runtime.observer

        await started_runtime.api.send_to_channel(
            "inbox_alpha", "via api", sender="tester"
        )

        messages = observer.get_messages(channel="inbox_alpha")
        assert len(messages) == 1
        assert messages[0].sender == "tester"
        assert messages[0].content == "via api"

        await observer.stop()
