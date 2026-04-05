"""TUI input module - reads input from Textual app."""

import asyncio
from typing import Any

from kohakuterrarium.builtins.tui.session import TUISession
from kohakuterrarium.core.events import TriggerEvent, create_user_input_event
from kohakuterrarium.core.session import get_session
from kohakuterrarium.modules.input.base import BaseInputModule
from kohakuterrarium.utils.logging import (
    get_logger,
    restore_logging,
    suppress_logging,
)

logger = get_logger(__name__)


class TUIInput(BaseInputModule):
    """
    Input module using Textual full-screen TUI.

    Creates or attaches to a shared TUISession. On start,
    launches the Textual app as a background task.

    Config:
        input:
          type: tui
          session_key: my_agent  # optional
          prompt: "You: "        # optional
    """

    def __init__(
        self,
        session_key: str | None = None,
        prompt: str = "You: ",
        **options: Any,
    ):
        super().__init__()
        self._session_key = session_key
        self._prompt = prompt
        self._tui: TUISession | None = None
        self._app_task: asyncio.Task | None = None
        self._exit_requested = False

    @property
    def exit_requested(self) -> bool:
        """Check if exit was requested."""
        return self._exit_requested

    async def _on_start(self) -> None:
        """Initialize TUI and launch the Textual app."""
        session = get_session(self._session_key)
        if session.tui is None:
            session.tui = TUISession(
                agent_name=session.key if session.key != "__default__" else "agent",
            )
        self._tui = session.tui

        # Configure terrarium tabs if available
        terrarium_tabs = session.extra.get("terrarium_tui_tabs")
        if terrarium_tabs:
            self._tui.set_terrarium_tabs(terrarium_tabs)

        # Suppress framework logs (captured by SessionOutput to session DB)
        suppress_logging()

        # Build and launch the Textual app
        await self._tui.start(self._prompt)
        self._app_task = asyncio.create_task(self._tui.run_app())
        await self._tui.wait_ready()
        logger.debug("TUI input started", session_key=self._session_key)

    async def _on_stop(self) -> None:
        """Stop the Textual app and restore stderr logging."""
        if self._tui:
            self._tui.stop()
        if self._app_task and not self._app_task.done():
            self._app_task.cancel()
            try:
                await self._app_task
            except (asyncio.CancelledError, Exception):
                pass

        restore_logging()
        logger.debug("TUI input stopped")

    async def get_input(self) -> TriggerEvent | None:
        """
        Wait for user input from the Textual app.

        Returns:
            TriggerEvent with user input, or None on exit/error
        """
        if not self._running or not self._tui:
            return None

        try:
            text = await self._tui.get_input(self._prompt)

            if not text:
                self._exit_requested = True
                return None

            # Legacy exit fallback (if command system not wired)
            if not self._user_commands and text.lower() in (
                "exit",
                "quit",
                "/exit",
                "/quit",
            ):
                self._exit_requested = True
                return None

            # Try slash command
            if text.startswith("/"):
                result = await self.try_user_command(text)
                if result is not None:
                    if result.output:
                        self._tui.add_system_notice(result.output)
                    if result.error:
                        self._tui.add_system_notice(result.error, error=True)
                    if self._exit_requested:
                        return None
                    if result.consumed:
                        return await self.get_input()

            return create_user_input_event(text, source="tui")

        except (EOFError, asyncio.CancelledError):
            self._exit_requested = True
            return None
        except Exception as e:
            logger.error("Error reading TUI input", error=str(e))
            return None
