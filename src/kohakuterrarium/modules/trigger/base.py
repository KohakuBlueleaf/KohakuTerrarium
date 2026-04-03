"""
Trigger module protocol and base class.

Triggers produce TriggerEvents without user input - enabling autonomous agents.
"""

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from kohakuterrarium.core.events import TriggerEvent


@runtime_checkable
class TriggerModule(Protocol):
    """
    Protocol for trigger modules.

    Triggers produce TriggerEvents based on various conditions:
    - Timer: Fire at intervals
    - Condition: Fire when state matches
    - Context: Fire when context changes
    - Idle: Fire after inactivity period
    """

    async def start(self) -> None:
        """Start the trigger."""
        ...

    async def stop(self) -> None:
        """Stop the trigger."""
        ...

    async def wait_for_trigger(self) -> TriggerEvent | None:
        """
        Wait for and return the next trigger event.

        Returns:
            TriggerEvent when trigger fires, or None if stopped
        """
        ...

    def set_context(self, context: dict[str, Any]) -> None:
        """
        Update trigger context.

        Used by context-based triggers to receive state updates.

        Args:
            context: Current context dict
        """
        ...


class BaseTrigger(ABC):
    """
    Base class for trigger modules.

    Provides common functionality for trigger handling.
    """

    # Override in subclass to enable resume persistence
    resumable: bool = False
    # Override in subclass to allow creation via create_trigger tool
    universal: bool = False

    def __init__(
        self,
        prompt: str | None = None,
        **options: Any,
    ):
        """
        Initialize trigger.

        Args:
            prompt: Default prompt to include in trigger events
            **options: Additional trigger options
        """
        self.prompt = prompt
        self.options = options
        self._running = False
        self._context: dict[str, Any] = {}

    def to_resume_dict(self) -> dict[str, Any]:
        """Serialize trigger config for session persistence.

        Override in subclass to save constructor args needed for re-creation.
        Only called if resumable=True.
        """
        return {"prompt": self.prompt, **self.options}

    @classmethod
    def from_resume_dict(cls, data: dict[str, Any]) -> "BaseTrigger":
        """Re-create trigger from saved config.

        Override in subclass if constructor signature differs from data keys.
        """
        return cls(**data)

    @property
    def is_running(self) -> bool:
        """Check if trigger is running."""
        return self._running

    async def start(self) -> None:
        """Start the trigger."""
        self._running = True
        await self._on_start()

    async def stop(self) -> None:
        """Stop the trigger."""
        self._running = False
        await self._on_stop()

    async def _on_start(self) -> None:
        """Called when trigger starts. Override in subclass."""
        pass

    async def _on_stop(self) -> None:
        """Called when trigger stops. Override in subclass."""
        pass

    def set_context(self, context: dict[str, Any]) -> None:
        """Update trigger context."""
        self._context.update(context)
        self._on_context_update(context)

    def _on_context_update(self, context: dict[str, Any]) -> None:
        """Called when context is updated. Override in subclass."""
        pass

    @abstractmethod
    async def wait_for_trigger(self) -> TriggerEvent | None:
        """Wait for trigger event. Must be implemented by subclass."""
        ...

    def _create_event(
        self,
        event_type: str,
        content: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> TriggerEvent:
        """Create a trigger event with default values."""
        return TriggerEvent(
            type=event_type,
            content=content or self.prompt or "",
            context=context or self._context.copy(),
            prompt_override=self.prompt,
        )
