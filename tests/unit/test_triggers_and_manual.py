"""Tests for trigger system improvements and require_manual_read."""

import asyncio

import pytest

from kohakuterrarium.modules.trigger.base import BaseTrigger
from kohakuterrarium.modules.trigger.channel import ChannelTrigger
from kohakuterrarium.modules.trigger.scheduler import SchedulerTrigger
from kohakuterrarium.modules.trigger.timer import TimerTrigger
from kohakuterrarium.modules.tool.base import BaseTool


class TestTriggerProperties:
    """Test resumable and universal flags on trigger types."""

    def test_base_trigger_defaults(self):
        assert BaseTrigger.resumable is False
        assert BaseTrigger.universal is False

    def test_channel_trigger_flags(self):
        assert ChannelTrigger.resumable is True
        assert ChannelTrigger.universal is True

    def test_timer_trigger_flags(self):
        assert TimerTrigger.resumable is True
        assert TimerTrigger.universal is True

    def test_scheduler_trigger_flags(self):
        assert SchedulerTrigger.resumable is True
        assert SchedulerTrigger.universal is True


class TestTimerTriggerResume:
    def test_to_resume_dict(self):
        t = TimerTrigger(interval=120, prompt="check status")
        d = t.to_resume_dict()
        assert d["interval"] == 120
        assert d["prompt"] == "check status"
        assert d["immediate"] is False  # Never immediate on resume

    def test_from_resume_dict(self):
        t = TimerTrigger.from_resume_dict({"interval": 300, "prompt": "five min check"})
        assert t.interval == 300
        assert t.prompt == "five min check"
        assert t.immediate is False

    def test_roundtrip(self):
        original = TimerTrigger(interval=60, prompt="test", immediate=True)
        d = original.to_resume_dict()
        restored = TimerTrigger.from_resume_dict(d)
        assert restored.interval == original.interval
        assert restored.prompt == original.prompt
        # immediate is forced False on resume
        assert restored.immediate is False


class TestChannelTriggerResume:
    def test_to_resume_dict(self):
        t = ChannelTrigger(
            channel_name="results",
            subscriber_id="root_results",
            ignore_sender="root",
            prompt="Result: {content}",
        )
        d = t.to_resume_dict()
        assert d["channel_name"] == "results"
        assert d["subscriber_id"] == "root_results"
        assert d["ignore_sender"] == "root"
        assert d["prompt"] == "Result: {content}"

    def test_from_resume_dict(self):
        t = ChannelTrigger.from_resume_dict(
            {
                "channel_name": "tasks",
                "subscriber_id": "watcher",
                "filter_sender": "boss",
            }
        )
        assert t.channel_name == "tasks"
        assert t.subscriber_id == "watcher"
        assert t.filter_sender == "boss"
        assert t.ignore_sender is None
        assert t._registry is None  # Caller must set

    def test_roundtrip(self):
        original = ChannelTrigger(
            channel_name="review",
            ignore_sender="reviewer",
            prompt="Review needed",
        )
        restored = ChannelTrigger.from_resume_dict(original.to_resume_dict())
        assert restored.channel_name == original.channel_name
        assert restored.ignore_sender == original.ignore_sender
        assert restored.prompt == original.prompt


class TestSchedulerTrigger:
    def test_to_resume_dict(self):
        t = SchedulerTrigger(every_minutes=30, prompt="half hour")
        d = t.to_resume_dict()
        assert d["every_minutes"] == 30
        assert d["prompt"] == "half hour"
        assert d["daily_at"] is None
        assert d["hourly_at"] is None

    def test_from_resume_dict_every_minutes(self):
        t = SchedulerTrigger.from_resume_dict({"every_minutes": 15, "prompt": "15m"})
        assert t.every_minutes == 15
        assert t.prompt == "15m"

    def test_from_resume_dict_daily(self):
        t = SchedulerTrigger.from_resume_dict({"daily_at": "09:30"})
        assert t.daily_at == "09:30"
        assert t.every_minutes is None

    def test_from_resume_dict_hourly(self):
        t = SchedulerTrigger.from_resume_dict({"hourly_at": 45})
        assert t.hourly_at == 45

    def test_seconds_until_next_every_minutes(self):
        t = SchedulerTrigger(every_minutes=60)
        secs = t._seconds_until_next()
        assert 0 < secs <= 3600

    def test_seconds_until_next_daily(self):
        t = SchedulerTrigger(daily_at="00:00")
        secs = t._seconds_until_next()
        assert 0 < secs <= 86400

    def test_seconds_until_next_hourly(self):
        t = SchedulerTrigger(hourly_at=0)
        secs = t._seconds_until_next()
        assert 0 < secs <= 3600


class TestRequireManualRead:
    """Test the require_manual_read tool property."""

    def test_default_false(self):
        class MyTool(BaseTool):
            @property
            def tool_name(self):
                return "my_tool"

            @property
            def description(self):
                return "test"

            async def _execute(self, args, context=None):
                pass

        t = MyTool()
        assert t.require_manual_read is False
        assert t._manual_read is False

    def test_can_set_true(self):
        class LockedTool(BaseTool):
            require_manual_read = True

            @property
            def tool_name(self):
                return "locked"

            @property
            def description(self):
                return "test"

            async def _execute(self, args, context=None):
                pass

        t = LockedTool()
        assert t.require_manual_read is True
        assert t._manual_read is False

    def test_manual_read_unlocks(self):
        class LockedTool(BaseTool):
            require_manual_read = True

            @property
            def tool_name(self):
                return "locked"

            @property
            def description(self):
                return "test"

            async def _execute(self, args, context=None):
                pass

        t = LockedTool()
        assert not t._manual_read
        t._manual_read = True
        assert t._manual_read


class TestCreateTriggerTool:
    def test_import(self):
        from kohakuterrarium.builtins.tools.create_trigger import CreateTriggerTool

        t = CreateTriggerTool()
        assert t.tool_name == "create_trigger"
        assert t.require_manual_read is True
        assert t.needs_context is True

    def test_trigger_registry(self):
        from kohakuterrarium.builtins.tools.create_trigger import (
            _ensure_registry,
            _TRIGGER_TYPES,
        )

        _ensure_registry()
        assert "TimerTrigger" in _TRIGGER_TYPES
        assert "ChannelTrigger" in _TRIGGER_TYPES
        assert "SchedulerTrigger" in _TRIGGER_TYPES

    def test_has_documentation(self):
        from kohakuterrarium.builtins.tools.create_trigger import CreateTriggerTool

        t = CreateTriggerTool()
        doc = t.get_full_documentation()
        assert "TimerTrigger" in doc
        assert "SchedulerTrigger" in doc
        assert "ChannelTrigger" in doc
        assert "interval" in doc
        assert "every_minutes" in doc
        assert "daily_at" in doc
