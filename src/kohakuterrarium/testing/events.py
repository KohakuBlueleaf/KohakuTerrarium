"""Event recording for testing event flow and ordering."""

import time
from dataclasses import dataclass, field


@dataclass
class RecordedEvent:
    """A recorded event with timing and source information."""

    timestamp: float
    event_type: str
    content: str
    source: str  # "controller", "trigger", "tool", "channel", "output"
    metadata: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        content_preview = (
            self.content[:50] + "..." if len(self.content) > 50 else self.content
        )
        return f"RecordedEvent({self.source}/{self.event_type}: {content_preview!r})"


class EventRecorder:
    """
    Records events flowing through the system for ordering assertions.

    Usage:
        recorder = EventRecorder()
        recorder.record("tool_complete", "bash result", source="tool")
        recorder.record("channel_message", "hello", source="channel")

        assert recorder.count == 2
        assert recorder.events[0].source == "tool"
        assert recorder.of_type("channel_message")[0].content == "hello"
    """

    def __init__(self):
        self.events: list[RecordedEvent] = []

    def record(
        self,
        event_type: str,
        content: str = "",
        source: str = "unknown",
        **metadata: object,
    ) -> None:
        """Record an event."""
        self.events.append(
            RecordedEvent(
                timestamp=time.monotonic(),
                event_type=event_type,
                content=content,
                source=source,
                metadata=metadata,
            )
        )

    def clear(self) -> None:
        """Clear all recorded events."""
        self.events.clear()

    @property
    def count(self) -> int:
        return len(self.events)

    def of_type(self, event_type: str) -> list[RecordedEvent]:
        """Filter events by type."""
        return [e for e in self.events if e.event_type == event_type]

    def of_source(self, source: str) -> list[RecordedEvent]:
        """Filter events by source."""
        return [e for e in self.events if e.source == source]

    def types_in_order(self) -> list[str]:
        """Get event types in chronological order."""
        return [e.event_type for e in self.events]

    def sources_in_order(self) -> list[str]:
        """Get event sources in chronological order."""
        return [e.source for e in self.events]

    def assert_order(self, *expected_types: str) -> None:
        """Assert events occurred in the given order (may have other events between)."""
        actual = self.types_in_order()
        idx = 0
        for expected in expected_types:
            found = False
            while idx < len(actual):
                if actual[idx] == expected:
                    found = True
                    idx += 1
                    break
                idx += 1
            assert found, (
                f"Expected event '{expected}' not found in remaining events "
                f"after index {idx}. Full order: {actual}"
            )

    def assert_before(self, first: str, second: str) -> None:
        """Assert first event type occurred before second."""
        first_idx = next(
            (i for i, e in enumerate(self.events) if e.event_type == first), None
        )
        second_idx = next(
            (i for i, e in enumerate(self.events) if e.event_type == second), None
        )
        assert first_idx is not None, f"Event '{first}' not found"
        assert second_idx is not None, f"Event '{second}' not found"
        assert (
            first_idx < second_idx
        ), f"Expected '{first}' (idx={first_idx}) before '{second}' (idx={second_idx})"
