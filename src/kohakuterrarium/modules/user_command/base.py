"""
User command system — slash commands typed by the human user.

Two execution layers:
  INPUT: intercepted at input module, before LLM (e.g. /exit, /help)
  AGENT: handled by agent with full state access (e.g. /model, /compact)
"""

from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol, runtime_checkable


class CommandLayer(Enum):
    """Where the command executes."""

    INPUT = "input"  # Pre-LLM, fast, no agent state
    AGENT = "agent"  # Has full agent state access


@dataclass
class UserCommandResult:
    """Result of executing a user command.

    For CLI/TUI: ``output`` is printed as text.
    For web frontend: ``data`` carries structured payload that the
    frontend can render as a modal, selector, table, etc.

    ``data`` convention::

        {"type": "text"}                          — plain text (default)
        {"type": "select", "options": [...],      — show picker
         "endpoint": "/api/agents/{id}/model"}
        {"type": "table", "columns": [...],       — render table
         "rows": [...]}
    """

    output: str = ""  # Plain text (CLI/TUI display)
    consumed: bool = True  # If True, don't pass text to LLM
    error: str | None = None
    data: dict[str, Any] | None = None  # Structured payload for rich UI

    @property
    def success(self) -> bool:
        return self.error is None


@dataclass
class UserCommandContext:
    """Context passed to command execute()."""

    agent: Any | None = None  # Agent instance (None for INPUT layer)
    session: Any | None = None  # Session
    input_module: Any | None = None
    output_fn: Callable[[str], None] | None = None  # Write to user
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class UserCommand(Protocol):
    """Protocol for user commands."""

    @property
    def name(self) -> str:
        """Command name without slash (e.g. "model")."""
        ...

    @property
    def aliases(self) -> list[str]:
        """Alternative names (e.g. ["quit"] for exit command)."""
        ...

    @property
    def description(self) -> str:
        """One-line description for /help."""
        ...

    @property
    def layer(self) -> CommandLayer:
        """Where this command executes."""
        ...

    async def execute(
        self, args: str, context: UserCommandContext
    ) -> UserCommandResult:
        """Execute the command."""
        ...


class BaseUserCommand:
    """Base class with error handling."""

    aliases: list[str] = []

    async def execute(
        self, args: str, context: UserCommandContext
    ) -> UserCommandResult:
        try:
            return await self._execute(args, context)
        except Exception as e:
            return UserCommandResult(error=str(e))

    @abstractmethod
    async def _execute(
        self, args: str, context: UserCommandContext
    ) -> UserCommandResult: ...


def parse_slash_command(text: str) -> tuple[str, str]:
    """Parse "/model claude-opus-4.6" → ("model", "claude-opus-4.6")."""
    text = text.lstrip("/")
    parts = text.split(None, 1)
    name = parts[0].lower() if parts else ""
    args = parts[1] if len(parts) > 1 else ""
    return name, args
