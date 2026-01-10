"""
Input module protocol and base class.

Input modules receive external input and produce TriggerEvents.
"""

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from kohakuterrarium.core.events import TriggerEvent


@runtime_checkable
class InputModule(Protocol):
    """
    Protocol for input modules.

    Input modules receive external input (CLI, API, ASR, etc.)
    and convert it to TriggerEvents for the controller.
    """

    async def start(self) -> None:
        """Start the input module."""
        ...

    async def stop(self) -> None:
        """Stop the input module."""
        ...

    async def get_input(self) -> TriggerEvent | None:
        """
        Wait for and return the next input event.

        Returns:
            TriggerEvent with type="user_input", or None if no input
        """
        ...


class BaseInputModule(ABC):
    """
    Base class for input modules.

    Provides common functionality for input handling.
    """

    def __init__(self):
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if module is running."""
        return self._running

    async def start(self) -> None:
        """Start the input module."""
        self._running = True
        await self._on_start()

    async def stop(self) -> None:
        """Stop the input module."""
        self._running = False
        await self._on_stop()

    async def _on_start(self) -> None:
        """Called when module starts. Override in subclass."""
        pass

    async def _on_stop(self) -> None:
        """Called when module stops. Override in subclass."""
        pass

    @abstractmethod
    async def get_input(self) -> TriggerEvent | None:
        """Get next input event. Must be implemented by subclass."""
        ...
