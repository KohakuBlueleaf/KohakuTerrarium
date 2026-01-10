"""
Standard output module.

Outputs to terminal/stdout with streaming support.
"""

import sys

from kohakuterrarium.modules.output.base import BaseOutputModule
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class StdoutOutput(BaseOutputModule):
    """
    Standard output module.

    Writes content to stdout with streaming support.
    """

    def __init__(
        self,
        *,
        prefix: str = "",
        suffix: str = "\n",
        stream_suffix: str = "",
        flush_on_stream: bool = True,
    ):
        """
        Initialize stdout output.

        Args:
            prefix: Prefix to add before output (e.g., "Assistant: ")
            suffix: Suffix to add after complete output (e.g., newline)
            stream_suffix: Suffix for streaming chunks (usually empty)
            flush_on_stream: Whether to flush after each stream chunk
        """
        super().__init__()
        self.prefix = prefix
        self.suffix = suffix
        self.stream_suffix = stream_suffix
        self.flush_on_stream = flush_on_stream
        self._streaming = False
        self._has_output = False

    async def _on_start(self) -> None:
        """Initialize stdout output."""
        logger.debug("Stdout output started")

    async def _on_stop(self) -> None:
        """Cleanup stdout output."""
        logger.debug("Stdout output stopped")

    async def write(self, content: str) -> None:
        """
        Write complete content to stdout.

        Args:
            content: Content to write
        """
        if not content:
            return

        # Add prefix if this is start of output
        output = ""
        if not self._has_output and self.prefix:
            output += self.prefix

        output += content + self.suffix

        sys.stdout.write(output)
        sys.stdout.flush()

        self._has_output = True
        self._streaming = False

    async def write_stream(self, chunk: str) -> None:
        """
        Write a streaming chunk to stdout.

        Args:
            chunk: Chunk to write
        """
        if not chunk:
            return

        # Add prefix if this is start of output
        if not self._streaming and not self._has_output and self.prefix:
            sys.stdout.write(self.prefix)

        sys.stdout.write(chunk + self.stream_suffix)

        if self.flush_on_stream:
            sys.stdout.flush()

        self._streaming = True
        self._has_output = True

    async def flush(self) -> None:
        """Flush stdout and add suffix if streaming."""
        if self._streaming:
            sys.stdout.write(self.suffix)
        sys.stdout.flush()
        self._streaming = False

    def reset(self) -> None:
        """Reset output state for new conversation turn."""
        self._has_output = False
        self._streaming = False


class PrefixedStdoutOutput(StdoutOutput):
    """
    Stdout output with configurable prefix per message.

    Useful for distinguishing different speakers in conversation.
    """

    def __init__(
        self,
        prefix: str = "Assistant: ",
        **kwargs,
    ):
        super().__init__(prefix=prefix, **kwargs)

    async def write_with_prefix(self, content: str, prefix: str | None = None) -> None:
        """
        Write content with optional custom prefix.

        Args:
            content: Content to write
            prefix: Custom prefix (uses default if None)
        """
        old_prefix = self.prefix
        if prefix is not None:
            self.prefix = prefix

        await self.write(content)

        self.prefix = old_prefix
