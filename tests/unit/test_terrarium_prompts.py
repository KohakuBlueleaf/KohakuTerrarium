"""Tests for terrarium prompt aggregation (auto-listening, channel info)."""

import pytest

from kohakuterrarium.terrarium.config import (
    ChannelConfig,
    CreatureConfig,
    TerrariumConfig,
    build_channel_topology_prompt,
)
from kohakuterrarium.terrarium.factory import build_root_awareness_prompt


def _make_config(
    creatures: list[dict] | None = None,
    channels: list[dict] | None = None,
) -> TerrariumConfig:
    """Build a minimal TerrariumConfig for testing."""
    from pathlib import Path

    cc = []
    for c in creatures or []:
        cc.append(
            CreatureConfig(
                name=c["name"],
                config_data={},
                base_dir=Path("/fake"),
                listen_channels=c.get("listen", []),
                send_channels=c.get("send", []),
            )
        )
    chs = []
    for ch in channels or []:
        chs.append(
            ChannelConfig(
                name=ch["name"],
                channel_type=ch.get("type", "queue"),
                description=ch.get("description", ""),
            )
        )
    return TerrariumConfig(name="test_terrarium", creatures=cc, channels=chs)


class TestCreatureTopologyPrompt:
    """Test build_channel_topology_prompt for creatures."""

    def test_includes_auto_listening_section(self):
        config = _make_config(
            creatures=[
                {"name": "swe", "listen": ["tasks"], "send": ["results"]},
            ],
            channels=[
                {"name": "tasks", "type": "queue"},
                {"name": "results", "type": "queue"},
            ],
        )
        prompt = build_channel_topology_prompt(config, config.creatures[0])
        assert "Auto-Listening" in prompt

    def test_includes_trigger_format(self):
        config = _make_config(
            creatures=[
                {"name": "swe", "listen": ["tasks"], "send": ["results"]},
            ],
            channels=[{"name": "tasks"}, {"name": "results"}],
        )
        prompt = build_channel_topology_prompt(config, config.creatures[0])
        assert "[Channel 'channel_name' from sender_name]" in prompt

    def test_includes_broadcast_format(self):
        config = _make_config(
            creatures=[
                {"name": "swe", "listen": ["chat"], "send": ["chat"]},
            ],
            channels=[{"name": "chat", "type": "broadcast"}],
        )
        prompt = build_channel_topology_prompt(config, config.creatures[0])
        assert "(broadcast)" in prompt

    def test_hearing_not_must_respond(self):
        config = _make_config(
            creatures=[
                {"name": "swe", "listen": ["tasks"], "send": ["results"]},
            ],
            channels=[{"name": "tasks"}, {"name": "results"}],
        )
        prompt = build_channel_topology_prompt(config, config.creatures[0])
        assert "does NOT mean you must respond" in prompt

    def test_lists_listen_channels(self):
        config = _make_config(
            creatures=[
                {"name": "swe", "listen": ["tasks", "feedback"], "send": ["results"]},
            ],
            channels=[
                {"name": "tasks"},
                {"name": "feedback"},
                {"name": "results"},
            ],
        )
        prompt = build_channel_topology_prompt(config, config.creatures[0])
        assert "`tasks`" in prompt
        assert "`feedback`" in prompt
        assert "(listen" in prompt

    def test_lists_send_channels(self):
        config = _make_config(
            creatures=[
                {"name": "swe", "listen": ["tasks"], "send": ["results", "review"]},
            ],
            channels=[
                {"name": "tasks"},
                {"name": "results"},
                {"name": "review"},
            ],
        )
        prompt = build_channel_topology_prompt(config, config.creatures[0])
        assert "`results`" in prompt
        assert "(send" in prompt or "send" in prompt.lower()

    def test_includes_direct_channel(self):
        config = _make_config(
            creatures=[{"name": "swe", "listen": ["tasks"], "send": []}],
            channels=[{"name": "tasks"}],
        )
        prompt = build_channel_topology_prompt(config, config.creatures[0])
        assert "`swe`" in prompt
        assert "direct channel" in prompt

    def test_includes_team_members(self):
        config = _make_config(
            creatures=[
                {"name": "swe", "listen": ["tasks"], "send": ["results"]},
                {"name": "reviewer", "listen": ["review"], "send": ["feedback"]},
            ],
            channels=[
                {"name": "tasks"},
                {"name": "results"},
                {"name": "review"},
                {"name": "feedback"},
            ],
        )
        prompt = build_channel_topology_prompt(config, config.creatures[0])
        assert "reviewer" in prompt

    def test_empty_channels_returns_empty(self):
        config = _make_config(
            creatures=[{"name": "swe", "listen": [], "send": []}],
            channels=[],
        )
        prompt = build_channel_topology_prompt(config, config.creatures[0])
        # No channels configured = no topology prompt needed
        # (direct channel only shows when there are other relevant channels)
        assert prompt == "" or "swe" in prompt


class TestRootAwarenessPrompt:
    """Test build_root_awareness_prompt for the root agent."""

    def test_includes_auto_listening(self):
        config = _make_config(
            creatures=[{"name": "swe", "listen": ["tasks"], "send": ["results"]}],
            channels=[{"name": "tasks"}, {"name": "results"}],
        )
        prompt = build_root_awareness_prompt(config)
        assert "Auto-Listening" in prompt
        assert "ALL channels" in prompt

    def test_includes_trigger_format(self):
        config = _make_config(
            creatures=[{"name": "swe"}],
            channels=[{"name": "tasks"}],
        )
        prompt = build_root_awareness_prompt(config)
        assert "[Channel 'channel_name' from sender_name]" in prompt

    def test_hearing_not_must_respond(self):
        config = _make_config(
            creatures=[{"name": "swe"}],
            channels=[{"name": "tasks"}],
        )
        prompt = build_root_awareness_prompt(config)
        assert "does NOT mean you must respond" in prompt

    def test_lists_creatures(self):
        config = _make_config(
            creatures=[
                {"name": "swe"},
                {"name": "reviewer"},
            ],
            channels=[],
        )
        prompt = build_root_awareness_prompt(config)
        assert "swe" in prompt
        assert "reviewer" in prompt

    def test_lists_channels(self):
        config = _make_config(
            creatures=[{"name": "swe"}],
            channels=[
                {"name": "tasks", "type": "queue", "description": "Work items"},
                {"name": "chat", "type": "broadcast"},
            ],
        )
        prompt = build_root_awareness_prompt(config)
        assert "`tasks`" in prompt
        assert "`chat`" in prompt
        assert "broadcast" in prompt

    def test_lists_direct_channels(self):
        config = _make_config(
            creatures=[{"name": "swe"}, {"name": "reviewer"}],
            channels=[],
        )
        prompt = build_root_awareness_prompt(config)
        assert "direct channel" in prompt.lower() or "Direct" in prompt

    def test_terrarium_id(self):
        config = _make_config(creatures=[{"name": "swe"}], channels=[])
        prompt = build_root_awareness_prompt(config)
        assert "test_terrarium" in prompt
