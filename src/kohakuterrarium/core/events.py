"""
Unified Event Model for KohakuTerrarium.

TriggerEvent is the universal event type that flows through the entire system:
- Input completion -> TriggerEvent
- Timer/condition triggers -> TriggerEvent
- Tool completion -> TriggerEvent
- Sub-agent output -> TriggerEvent

Stackable events can be batched when occurring simultaneously.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class TriggerEvent:
    """
    Universal event type that flows through the entire system.

    All components communicate through this single event type - inputs, triggers,
    tool completions, and sub-agent outputs all produce TriggerEvents.

    Attributes:
        type: Event type identifier. Common types:
            - "user_input": User provided input
            - "idle": Idle timeout trigger
            - "timer": Timer-based trigger
            - "tool_complete": Tool finished execution
            - "subagent_output": Sub-agent produced output
            - "monitor": Monitoring condition triggered
            - "error": Error occurred

        content: Main content/message of the event

        context: Additional context data (flexible dict for type-specific info)
            For tool_complete: may include exit_code, error, etc.
            For user_input: may include source, metadata, etc.

        timestamp: When the event was created

        job_id: For tool/subagent completion events, the job ID that completed

        prompt_override: Optional prompt injection for this event
            Triggers can include built-in prompts that tell agent what to do

        stackable: Whether this event can be batched with simultaneous events
            When multiple triggers fire at once, stackable events are combined
    """

    type: str
    content: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    job_id: str | None = None
    prompt_override: str | None = None
    stackable: bool = True

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        if not self.type:
            raise ValueError("TriggerEvent type cannot be empty")

    def with_context(self, **kwargs: Any) -> "TriggerEvent":
        """
        Create a new event with additional context.

        Returns a new TriggerEvent with merged context (doesn't mutate self).
        """
        new_context = {**self.context, **kwargs}
        return TriggerEvent(
            type=self.type,
            content=self.content,
            context=new_context,
            timestamp=self.timestamp,
            job_id=self.job_id,
            prompt_override=self.prompt_override,
            stackable=self.stackable,
        )

    def __repr__(self) -> str:
        parts = [f"TriggerEvent(type={self.type!r}"]
        if self.content:
            content_preview = (
                self.content[:50] + "..." if len(self.content) > 50 else self.content
            )
            parts.append(f"content={content_preview!r}")
        if self.job_id:
            parts.append(f"job_id={self.job_id!r}")
        if self.context:
            parts.append(f"context_keys={list(self.context.keys())}")
        parts.append(f"stackable={self.stackable}")
        return ", ".join(parts) + ")"


# Common event type constants for type safety
class EventType:
    """Common event type constants."""

    USER_INPUT = "user_input"
    IDLE = "idle"
    TIMER = "timer"
    TOOL_COMPLETE = "tool_complete"
    SUBAGENT_OUTPUT = "subagent_output"
    MONITOR = "monitor"
    ERROR = "error"
    STARTUP = "startup"
    SHUTDOWN = "shutdown"


def create_user_input_event(
    content: str,
    source: str = "cli",
    **extra_context: Any,
) -> TriggerEvent:
    """Create a user input event with standard context."""
    return TriggerEvent(
        type=EventType.USER_INPUT,
        content=content,
        context={"source": source, **extra_context},
        stackable=True,
    )


def create_tool_complete_event(
    job_id: str,
    content: str,
    exit_code: int | None = None,
    error: str | None = None,
    **extra_context: Any,
) -> TriggerEvent:
    """Create a tool completion event with standard context."""
    context: dict[str, Any] = extra_context
    if exit_code is not None:
        context["exit_code"] = exit_code
    if error is not None:
        context["error"] = error
    return TriggerEvent(
        type=EventType.TOOL_COMPLETE,
        content=content,
        context=context,
        job_id=job_id,
        stackable=True,
    )


def create_error_event(
    error_type: str,
    message: str,
    job_id: str | None = None,
    **extra_context: Any,
) -> TriggerEvent:
    """Create an error event with standard context."""
    return TriggerEvent(
        type=EventType.ERROR,
        content=message,
        context={"error_type": error_type, **extra_context},
        job_id=job_id,
        stackable=False,  # Errors typically need immediate attention
    )
