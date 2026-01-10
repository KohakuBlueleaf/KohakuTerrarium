"""
Output module protocol and base class.

Output modules handle the final delivery of agent output.
"""

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable


@runtime_checkable
class OutputModule(Protocol):
    """
    Protocol for output modules.

    Output modules receive content from the controller/router
    and deliver it to the appropriate destination.
    """

    async def start(self) -> None:
        """Start the output module."""
        ...

    async def stop(self) -> None:
        """Stop the output module."""
        ...

    async def write(self, content: str) -> None:
        """
        Write complete content.

        Args:
            content: Full content to output
        """
        ...

    async def write_stream(self, chunk: str) -> None:
        """
        Write a streaming chunk.

        Args:
            chunk: Partial content chunk
        """
        ...

    async def flush(self) -> None:
        """Flush any buffered content."""
        ...


class BaseOutputModule(ABC):
    """
    Base class for output modules.

    Provides common functionality for output handling.
    """

    def __init__(self):
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if module is running."""
        return self._running

    async def start(self) -> None:
        """Start the output module."""
        self._running = True
        await self._on_start()

    async def stop(self) -> None:
        """Stop the output module."""
        await self.flush()
        self._running = False
        await self._on_stop()

    async def _on_start(self) -> None:
        """Called when module starts. Override in subclass."""
        pass

    async def _on_stop(self) -> None:
        """Called when module stops. Override in subclass."""
        pass

    @abstractmethod
    async def write(self, content: str) -> None:
        """Write complete content. Must be implemented by subclass."""
        ...

    async def write_stream(self, chunk: str) -> None:
        """Write streaming chunk. Default calls write()."""
        await self.write(chunk)

    async def flush(self) -> None:
        """Flush buffered content. Default is no-op."""
        pass
