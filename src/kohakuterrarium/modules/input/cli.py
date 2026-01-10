"""
CLI input module.

Provides terminal-based input for agents.
"""

import asyncio
import sys

from kohakuterrarium.core.events import TriggerEvent, create_user_input_event
from kohakuterrarium.modules.input.base import BaseInputModule
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class CLIInput(BaseInputModule):
    """
    Command-line interface input module.

    Reads user input from terminal with async support.
    """

    def __init__(
        self,
        prompt: str = "> ",
        *,
        exit_commands: list[str] | None = None,
    ):
        """
        Initialize CLI input.

        Args:
            prompt: Input prompt to display
            exit_commands: Commands that signal exit (default: /exit, /quit, exit, quit)
        """
        super().__init__()
        self.prompt = prompt
        self.exit_commands = exit_commands or ["/exit", "/quit", "exit", "quit"]
        self._exit_requested = False

    @property
    def exit_requested(self) -> bool:
        """Check if exit was requested."""
        return self._exit_requested

    async def _on_start(self) -> None:
        """Initialize CLI input."""
        logger.debug("CLI input started", prompt=self.prompt)

    async def _on_stop(self) -> None:
        """Cleanup CLI input."""
        logger.debug("CLI input stopped")

    async def get_input(self) -> TriggerEvent | None:
        """
        Get input from terminal.

        Returns:
            TriggerEvent with user input, or None if exit requested
        """
        if not self._running or self._exit_requested:
            return None

        try:
            # Run blocking input in thread pool
            loop = asyncio.get_event_loop()
            line = await loop.run_in_executor(None, self._read_line)

            if line is None:
                # EOF (Ctrl+D)
                self._exit_requested = True
                return None

            line = line.strip()

            # Check for exit commands
            if line.lower() in self.exit_commands:
                self._exit_requested = True
                logger.debug("Exit command received")
                return None

            # Return as trigger event
            return create_user_input_event(line)

        except (KeyboardInterrupt, EOFError):
            self._exit_requested = True
            return None
        except Exception as e:
            logger.error("Error reading input", error=str(e))
            return None

    def _read_line(self) -> str | None:
        """Read a line from stdin (blocking)."""
        try:
            # Print prompt
            sys.stdout.write(self.prompt)
            sys.stdout.flush()

            # Read line
            line = sys.stdin.readline()
            if not line:
                return None
            return line
        except (KeyboardInterrupt, EOFError):
            return None


class NonBlockingCLIInput(BaseInputModule):
    """
    Non-blocking CLI input using select/poll.

    Useful when you need to check for input without blocking.
    """

    def __init__(
        self,
        prompt: str = "> ",
        timeout: float = 0.1,
    ):
        """
        Initialize non-blocking CLI input.

        Args:
            prompt: Input prompt
            timeout: Poll timeout in seconds
        """
        super().__init__()
        self.prompt = prompt
        self.timeout = timeout
        self._buffer = ""
        self._prompt_shown = False

    async def get_input(self) -> TriggerEvent | None:
        """
        Check for input without blocking.

        Returns:
            TriggerEvent if complete line available, None otherwise
        """
        if not self._running:
            return None

        # Show prompt if needed
        if not self._prompt_shown:
            sys.stdout.write(self.prompt)
            sys.stdout.flush()
            self._prompt_shown = True

        # Check for available input
        loop = asyncio.get_event_loop()
        try:
            line = await asyncio.wait_for(
                loop.run_in_executor(None, self._try_read),
                timeout=self.timeout,
            )
            if line is not None:
                self._prompt_shown = False
                return create_user_input_event(line.strip())
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.error("Error in non-blocking read", error=str(e))

        return None

    def _try_read(self) -> str | None:
        """Try to read a line (may block briefly)."""
        import select

        # Check if input available (Unix only)
        if sys.platform != "win32":
            ready, _, _ = select.select([sys.stdin], [], [], self.timeout)
            if not ready:
                return None

        try:
            line = sys.stdin.readline()
            return line if line else None
        except Exception:
            return None
