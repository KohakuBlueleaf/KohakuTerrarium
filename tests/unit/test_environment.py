"""Tests for Environment-Session two-level isolation system.

Covers:
- Environment creation and identity
- Session lifecycle (get_or_create, isolation, listing)
- Shared state registration (register/get)
- Channel isolation (private vs shared, cross-session visibility)
"""

import pytest

from kohakuterrarium.core.channel import ChannelRegistry
from kohakuterrarium.core.environment import Environment
from kohakuterrarium.core.session import Session


class TestEnvironment:
    """Core Environment behavior."""

    def test_create_environment(self):
        """Environment has env_id, shared_channels, empty sessions."""
        env = Environment()
        assert env.env_id.startswith("env_")
        assert isinstance(env.shared_channels, ChannelRegistry)
        assert env.list_sessions() == []

    def test_custom_env_id(self):
        """Environment accepts a custom env_id."""
        env = Environment(env_id="custom_123")
        assert env.env_id == "custom_123"

    def test_get_session_creates_new(self):
        """get_session creates a new Session if not exists."""
        env = Environment()
        session = env.get_session("agent_a")
        assert isinstance(session, Session)
        assert session.key == "agent_a"

    def test_get_session_returns_same(self):
        """get_session with same key returns same Session."""
        env = Environment()
        s1 = env.get_session("agent_a")
        s2 = env.get_session("agent_a")
        assert s1 is s2

    def test_sessions_are_isolated(self):
        """Different session keys get different Sessions with separate scratchpads."""
        env = Environment()
        sa = env.get_session("agent_a")
        sb = env.get_session("agent_b")

        assert sa is not sb
        assert sa.key != sb.key

        # Scratchpads are independent
        sa.scratchpad.set("x", "1")
        assert sb.scratchpad.get("x") is None

    def test_shared_channels_separate_from_sessions(self):
        """Environment shared_channels is not the same as any session's channels."""
        env = Environment()
        session = env.get_session("agent_a")
        assert env.shared_channels is not session.channels

    def test_register_and_get(self):
        """Modules can register and retrieve shared state."""
        env = Environment()
        env.register("db_conn", {"host": "localhost"})
        assert env.get("db_conn") == {"host": "localhost"}

    def test_get_missing_returns_default(self):
        """get() returns default when key not registered."""
        env = Environment()
        assert env.get("missing") is None
        assert env.get("missing", 42) == 42

    def test_list_sessions(self):
        """list_sessions returns all created session keys."""
        env = Environment()
        env.get_session("alpha")
        env.get_session("beta")
        env.get_session("gamma")
        keys = env.list_sessions()
        assert sorted(keys) == ["alpha", "beta", "gamma"]


class TestEnvironmentChannelIsolation:
    """Channel isolation between sessions and shared_channels."""

    def test_private_channels_not_visible_to_other_sessions(self):
        """Channel created in session A is not visible in session B."""
        env = Environment()
        sa = env.get_session("agent_a")
        sb = env.get_session("agent_b")

        sa.channels.get_or_create("inbox_a", "queue")
        assert sb.channels.get("inbox_a") is None

    def test_shared_channel_visible_from_environment(self):
        """Channel in shared_channels is accessible from environment."""
        env = Environment()
        ch = env.shared_channels.get_or_create("broadcast_all", "broadcast")
        assert env.shared_channels.get("broadcast_all") is ch

    def test_shared_channel_not_in_session(self):
        """Shared channel is not automatically visible in session channels."""
        env = Environment()
        env.shared_channels.get_or_create("shared_ch", "queue")
        session = env.get_session("agent_a")
        assert session.channels.get("shared_ch") is None

    def test_same_name_private_and_shared_are_different(self):
        """Private channel 'foo' and shared channel 'foo' are distinct objects."""
        env = Environment()
        session = env.get_session("agent_a")

        shared_foo = env.shared_channels.get_or_create("foo", "queue")
        private_foo = session.channels.get_or_create("foo", "queue")

        assert shared_foo is not private_foo

    def test_two_sessions_same_channel_name_are_different(self):
        """Two sessions creating same-named channel get distinct objects."""
        env = Environment()
        sa = env.get_session("agent_a")
        sb = env.get_session("agent_b")

        ch_a = sa.channels.get_or_create("work", "queue")
        ch_b = sb.channels.get_or_create("work", "queue")

        assert ch_a is not ch_b

    def test_session_scratchpad_isolation(self):
        """Scratchpads across sessions are fully independent."""
        env = Environment()
        sa = env.get_session("agent_a")
        sb = env.get_session("agent_b")

        sa.scratchpad.set("plan", "step 1")
        sb.scratchpad.set("plan", "step 99")

        assert sa.scratchpad.get("plan") == "step 1"
        assert sb.scratchpad.get("plan") == "step 99"


class TestMultiEnvironmentIsolation:
    """Multiple environments don't interfere with each other."""

    def test_two_envs_separate_channels(self):
        """Two environments have completely separate shared_channels."""
        env1 = Environment(env_id="user_1")
        env2 = Environment(env_id="user_2")

        env1.shared_channels.get_or_create("tasks")
        env2.shared_channels.get_or_create("tasks")

        assert env1.shared_channels.get("tasks") is not env2.shared_channels.get(
            "tasks"
        )

    def test_two_envs_separate_sessions(self):
        """Sessions in different environments are independent."""
        env1 = Environment(env_id="user_1")
        env2 = Environment(env_id="user_2")

        s1 = env1.get_session("agent")
        s2 = env2.get_session("agent")

        s1.scratchpad.set("key", "val_1")
        s2.scratchpad.set("key", "val_2")

        assert s1.scratchpad.get("key") == "val_1"
        assert s2.scratchpad.get("key") == "val_2"

    def test_two_envs_separate_context(self):
        """Registered context in different environments is independent."""
        env1 = Environment(env_id="user_1")
        env2 = Environment(env_id="user_2")

        env1.register("model", "gpt-4")
        env2.register("model", "gemini")

        assert env1.get("model") == "gpt-4"
        assert env2.get("model") == "gemini"


class TestAsyncChannelIsolation:
    """Async tests for message-level isolation."""

    async def test_private_message_not_on_shared(self):
        """Message sent on private channel doesn't appear on shared channel of same name."""
        from kohakuterrarium.core.channel import ChannelMessage

        env = Environment()
        session = env.get_session("creature_a")

        shared = env.shared_channels.get_or_create("results")
        private = session.channels.get_or_create("results")

        await private.send(ChannelMessage(sender="sub", content="private"))

        assert shared.empty
        assert not private.empty

    async def test_shared_message_not_on_private(self):
        """Message sent on shared channel doesn't appear on private channel of same name."""
        from kohakuterrarium.core.channel import ChannelMessage

        env = Environment()
        session = env.get_session("creature_a")

        shared = env.shared_channels.get_or_create("data")
        private = session.channels.get_or_create("data")

        await shared.send(ChannelMessage(sender="other", content="shared"))

        assert not shared.empty
        assert private.empty
