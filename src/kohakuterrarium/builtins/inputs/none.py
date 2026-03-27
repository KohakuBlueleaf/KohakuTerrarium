"""
None input module.

For trigger-only agents that have no user input.
"""

import asyncio
from typing import Any

from kohakuterrarium.core.events import TriggerEvent
from kohakuterrarium.modules.input.base import BaseInputModule
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class NoneInput(BaseInputModule):
    """
    Input module that never produces input.

    For trigger-only agents (e.g., monitor_agent) that are driven
    entirely by timers, channels, or other triggers.

    Config:
        input:
          type: none
    """

    def __init__(self, **_options: Any):
        super().__init__()
        self._stop_event: asyncio.Event | None = None
        self._exit_requested = False

    @property
    def exit_requested(self) -> bool:
        """Check if exit was requested."""
        return self._exit_requested

    async def _on_start(self) -> None:
        """Initialize stop event."""
        self._stop_event = asyncio.Event()
        logger.debug("NoneInput started (trigger-only mode)")

    async def _on_stop(self) -> None:
        """Signal the stop event to unblock get_input."""
        if self._stop_event:
            self._stop_event.set()
        logger.debug("NoneInput stopped")

    async def get_input(self) -> TriggerEvent | None:
        """Block until stop() is called. Never produces input."""
        if not self._running:
            return None

        if self._stop_event:
            await self._stop_event.wait()

        self._exit_requested = True
        return None
