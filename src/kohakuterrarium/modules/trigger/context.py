"""
Context update trigger - fires when context changes.
"""

import asyncio
from typing import Any

from kohakuterrarium.core.events import EventType, TriggerEvent
from kohakuterrarium.modules.trigger.base import BaseTrigger
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class ContextUpdateTrigger(BaseTrigger):
    """
    Trigger that fires when context is updated.

    Used by conversational agents to trigger output when:
    - New ASR input arrives
    - Memory is updated
    - External state changes

    Usage:
        trigger = ContextUpdateTrigger(
            prompt="New context available",
            debounce_ms=100,
        )
        await trigger.start()

        # In another coroutine:
        trigger.set_context({"new_input": "hello"})

        # Wait for trigger:
        event = await trigger.wait_for_trigger()
    """

    def __init__(
        self,
        prompt: str | None = None,
        debounce_ms: int = 100,
        **options: Any,
    ):
        """
        Initialize context update trigger.

        Args:
            prompt: Prompt to include in event
            debounce_ms: Milliseconds to debounce rapid updates
            **options: Additional options
        """
        super().__init__(prompt=prompt, **options)
        self.debounce_ms = debounce_ms
        self._pending_event: asyncio.Event | None = None
        self._last_context: dict[str, Any] = {}
        self._stop_event: asyncio.Event | None = None

    def _ensure_events(self) -> None:
        """Lazily create asyncio primitives if not yet initialized."""
        if self._pending_event is None:
            self._pending_event = asyncio.Event()
        if self._stop_event is None:
            self._stop_event = asyncio.Event()

    async def _on_start(self) -> None:
        """Reset state on start."""
        self._ensure_events()
        self._pending_event.clear()
        self._stop_event.clear()
        self._last_context = {}
        logger.debug("Context update trigger started")

    async def _on_stop(self) -> None:
        """Signal stop."""
        self._ensure_events()
        self._stop_event.set()
        self._pending_event.set()  # Wake up any waiting
        logger.debug("Context update trigger stopped")

    def _on_context_update(self, context: dict[str, Any]) -> None:
        """Called when context is updated."""
        self._ensure_events()
        # Check if context actually changed
        if context != self._last_context:
            self._last_context = context.copy()
            self._pending_event.set()
            logger.debug("Context update detected")

    async def wait_for_trigger(self) -> TriggerEvent | None:
        """Wait for context change."""
        if not self._running:
            return None

        self._ensure_events()
        # Wait for context update or stop
        await self._pending_event.wait()

        if not self._running:
            return None

        # Debounce - wait a bit for more updates
        if self.debounce_ms > 0:
            await asyncio.sleep(self.debounce_ms / 1000)

        self._pending_event.clear()

        if not self._running:
            return None

        return self._create_event(
            EventType.CONTEXT_UPDATE,
            content=self.prompt or "Context updated",
            context=self._last_context.copy(),
        )

    def trigger_now(self, context: dict[str, Any] | None = None) -> None:
        """
        Manually trigger with optional context.

        Args:
            context: Optional context to set before triggering
        """
        self._ensure_events()
        if context:
            self._context.update(context)
            self._last_context = context.copy()
        self._pending_event.set()
