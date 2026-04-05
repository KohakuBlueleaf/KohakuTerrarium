"""
User command system — slash commands typed by the human user.

Two execution layers:
  INPUT: intercepted at input module, before LLM (e.g. /exit, /help)
  AGENT: handled by agent with full state access (e.g. /model, /compact)

Rich UI payloads:
  Commands return a ``data`` field with typed UI hints. CLI/TUI renders
  them as text; web frontend renders them as modals, pickers, etc.
  Each payload is a dict with a ``type`` key. Typed constructors below.
"""

from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol, runtime_checkable


class CommandLayer(Enum):
    """Where the command executes."""

    INPUT = "input"  # Pre-LLM, fast, no agent state
    AGENT = "agent"  # Has full agent state access


# ── Rich UI payload constructors ────────────────────────────────────
#
# Each returns a plain dict (JSON-serializable for the API).
# Frontend switches on data["type"] to decide rendering.
#
# Supported now:  text, notify, select, info_panel, list, confirm
# Reserved:       table, form, progress  (implement when needed)


def ui_text(message: str) -> dict[str, Any]:
    """Plain text block."""
    return {"type": "text", "message": message}


def ui_notify(message: str, *, level: str = "info") -> dict[str, Any]:
    """Toast / banner notification.

    Args:
        level: "info", "success", "warning", "error"
    """
    return {"type": "notify", "message": message, "level": level}


def ui_confirm(
    message: str,
    *,
    action: str,
    action_args: str = "",
) -> dict[str, Any]:
    """Yes/No confirmation dialog.

    Frontend sends ``POST /command { command: action, args: action_args }``
    if the user confirms.
    """
    return {
        "type": "confirm",
        "message": message,
        "action": action,
        "action_args": action_args,
    }


def ui_select(
    title: str,
    options: list[dict[str, Any]],
    *,
    current: str = "",
    action: str = "",
) -> dict[str, Any]:
    """Picker / selector modal.

    Each option: ``{"value": str, "label": str, ...extra fields}``.
    Frontend sends ``POST /command { command: action, args: selected_value }``
    when the user picks one.
    """
    return {
        "type": "select",
        "title": title,
        "current": current,
        "options": options,
        "action": action,
    }


def ui_info_panel(
    title: str,
    fields: list[dict[str, str]],
) -> dict[str, Any]:
    """Key/value info card.

    Each field: ``{"key": "Model", "value": "gpt-5.4"}``.
    """
    return {"type": "info_panel", "title": title, "fields": fields}


def ui_list(
    title: str,
    items: list[dict[str, str]],
) -> dict[str, Any]:
    """Styled list of items.

    Each item: ``{"label": str, "description": str, ...extra}``.
    """
    return {"type": "list", "title": title, "items": items}


# Reserved constructors (implement when needed):
#
# def ui_table(title, columns, rows) -> dict:
#     """Data table with sortable columns."""
#
# def ui_form(title, fields, action) -> dict:
#     """Input form with typed fields."""
#
# def ui_progress(message, percent) -> dict:
#     """Progress indicator."""


# ── Command result ──────────────────────────────────────────────────


@dataclass
class UserCommandResult:
    """Result of executing a user command.

    ``output``: plain text for CLI/TUI.
    ``data``:   structured UI payload (built via ui_* constructors above).
                Web frontend renders based on ``data["type"]``.
                CLI/TUI ignores ``data`` and prints ``output``.
    """

    output: str = ""
    consumed: bool = True  # If True, don't pass text to LLM
    error: str | None = None
    data: dict[str, Any] | None = None

    @property
    def success(self) -> bool:
        return self.error is None


# ── Command context ─────────────────────────────────────────────────


@dataclass
class UserCommandContext:
    """Context passed to command execute()."""

    agent: Any | None = None  # Agent instance (None for INPUT layer)
    session: Any | None = None  # Session
    input_module: Any | None = None
    output_fn: Callable[[str], None] | None = None  # Write to user
    extra: dict[str, Any] = field(default_factory=dict)


# ── Protocol + base class ───────────────────────────────────────────


@runtime_checkable
class UserCommand(Protocol):
    """Protocol for user commands."""

    @property
    def name(self) -> str: ...

    @property
    def aliases(self) -> list[str]: ...

    @property
    def description(self) -> str: ...

    @property
    def layer(self) -> CommandLayer: ...

    async def execute(
        self, args: str, context: UserCommandContext
    ) -> UserCommandResult: ...


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


# ── Parsing ─────────────────────────────────────────────────────────


def parse_slash_command(text: str) -> tuple[str, str]:
    """Parse "/model claude-opus-4.6" → ("model", "claude-opus-4.6")."""
    text = text.lstrip("/")
    parts = text.split(None, 1)
    name = parts[0].lower() if parts else ""
    args = parts[1] if len(parts) > 1 else ""
    return name, args
