"""TUI output module - writes output via shared TUI session."""

from typing import Any

from kohakuterrarium.builtins.tui.session import TUISession
from kohakuterrarium.core.session import get_session
from kohakuterrarium.modules.output.base import BaseOutputModule
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class TUIOutput(BaseOutputModule):
    """
    Output module that writes to a shared TUI session.

    Config:
        output:
          type: tui
          session_key: my_agent  # optional
    """

    def __init__(self, session_key: str | None = None, **options: Any):
        super().__init__()
        self._session_key = session_key
        self._tui: TUISession | None = None

    async def _on_start(self) -> None:
        """Initialize TUI output by attaching to shared session."""
        session = get_session(self._session_key)
        if session.tui is None:
            session.tui = TUISession()
        self._tui = session.tui
        logger.debug("TUI output started", session_key=self._session_key)

    async def _on_stop(self) -> None:
        """Cleanup TUI output."""
        logger.debug("TUI output stopped")

    async def write(self, content: str) -> None:
        """
        Write complete content to the TUI.

        Args:
            content: Content to write
        """
        if self._tui:
            self._tui.write_output(content)

    async def write_stream(self, chunk: str) -> None:
        """
        Write a streaming chunk to the TUI.

        Args:
            chunk: Partial content chunk
        """
        if self._tui:
            self._tui.write_output(chunk)

    async def flush(self) -> None:
        """Flush TUI output. Currently a no-op."""
        pass
