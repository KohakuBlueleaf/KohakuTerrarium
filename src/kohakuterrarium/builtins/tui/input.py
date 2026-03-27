"""TUI input module - reads input via shared TUI session."""

import asyncio
from typing import Any

from kohakuterrarium.builtins.tui.session import TUISession
from kohakuterrarium.core.events import TriggerEvent, create_user_input_event
from kohakuterrarium.core.session import get_session
from kohakuterrarium.modules.input.base import BaseInputModule
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class TUIInput(BaseInputModule):
    """
    Input module that reads from a shared TUI session.

    Config:
        input:
          type: tui
          session_key: my_agent  # optional
          prompt: "You: "        # optional
    """

    def __init__(
        self,
        session_key: str | None = None,
        prompt: str = "> ",
        **options: Any,
    ):
        super().__init__()
        self._session_key = session_key
        self._prompt = prompt
        self._tui: TUISession | None = None
        self._exit_requested = False

    @property
    def exit_requested(self) -> bool:
        """Check if exit was requested."""
        return self._exit_requested

    async def _on_start(self) -> None:
        """Initialize TUI input by attaching to shared session."""
        session = get_session(self._session_key)
        if session.tui is None:
            session.tui = TUISession()
        self._tui = session.tui
        self._tui.running = True
        logger.debug("TUI input started", session_key=self._session_key)

    async def _on_stop(self) -> None:
        """Cleanup TUI input."""
        if self._tui:
            self._tui.stop()
        logger.debug("TUI input stopped")

    async def get_input(self) -> TriggerEvent | None:
        """
        Get input from the TUI session.

        Returns:
            TriggerEvent with user input, or None if exit requested / no input
        """
        if not self._running or not self._tui:
            return None

        try:
            text = await self._tui.get_input(self._prompt)

            if not text:
                return None

            if text.lower() in ("exit", "quit", "/exit", "/quit"):
                self._exit_requested = True
                logger.debug("Exit command received")
                return None

            return create_user_input_event(text, source="tui")

        except (EOFError, asyncio.CancelledError):
            self._exit_requested = True
            return None
        except Exception as e:
            logger.error("Error reading TUI input", error=str(e))
            return None
