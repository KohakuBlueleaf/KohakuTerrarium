"""TUI session - shared state between TUI input and output modules."""

import asyncio
import sys
from dataclasses import dataclass, field

from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TUISession:
    """
    Shared TUI state between input and output modules.

    Stored in Session.tui. Both TUIInput and TUIOutput reference the same
    TUISession instance for coordinated terminal access.
    """

    input_queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    output_lines: list[str] = field(default_factory=list)
    running: bool = False
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event)

    async def get_input(self, prompt: str = "> ") -> str:
        """Get input from the TUI. Blocks until available."""
        sys.stderr.write(prompt)
        sys.stderr.flush()
        loop = asyncio.get_event_loop()
        line = await loop.run_in_executor(None, sys.stdin.readline)
        return line.strip()

    def write_output(self, text: str) -> None:
        """Write output text to the TUI."""
        self.output_lines.append(text)
        sys.stdout.write(text)
        sys.stdout.flush()

    def write_line(self, text: str) -> None:
        """Write a line to the TUI."""
        self.write_output(text + "\n")

    async def wait_for_stop(self) -> None:
        """Block until stop is signaled."""
        await self._stop_event.wait()

    def stop(self) -> None:
        """Signal stop."""
        self.running = False
        self._stop_event.set()
