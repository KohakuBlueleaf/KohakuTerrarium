"""
Input module protocol and base class.

Input modules receive external input and produce TriggerEvents.
Integrates with the user command system for slash commands.
"""

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from kohakuterrarium.core.events import TriggerEvent
from kohakuterrarium.modules.user_command.base import (
    UserCommandResult,
    parse_slash_command,
)


@runtime_checkable
class InputModule(Protocol):
    """
    Protocol for input modules.

    Input modules receive external input (CLI, API, ASR, etc.)
    and convert it to TriggerEvents for the controller.
    """

    async def start(self) -> None:
        """Start the input module."""
        ...

    async def stop(self) -> None:
        """Stop the input module."""
        ...

    async def get_input(self) -> TriggerEvent | None:
        """
        Wait for and return the next input event.

        Returns:
            TriggerEvent with type="user_input", or None if no input
        """
        ...


class BaseInputModule(ABC):
    """
    Base class for input modules.

    Provides common functionality for input handling and
    user command dispatch (slash commands).

    Subclasses must override ``render_command_data()`` to handle
    interactive data payloads (select, confirm, etc.) natively
    in their UI framework.
    """

    def __init__(self):
        self._running = False
        # User command system (set by agent after construction)
        self._user_commands: dict[str, Any] = {}  # name → UserCommand
        self._user_command_context: Any = None
        self._command_alias_map: dict[str, str] = {}  # alias → canonical

    def set_user_commands(self, commands: dict[str, Any], context: Any) -> None:
        """Register user commands and context for slash command dispatch.

        Called by Agent during initialization.
        """
        self._user_commands = commands
        self._user_command_context = context
        # Build alias map
        self._command_alias_map = {}
        for name, cmd in commands.items():
            for alias in getattr(cmd, "aliases", []):
                self._command_alias_map[alias] = name

    async def try_user_command(self, text: str) -> UserCommandResult | None:
        """Execute a slash command. Returns result or None if not a command.

        After executing the command, calls ``render_command_data()`` if
        the result has a ``data`` payload. The subclass renders interactive
        UI (select, confirm, etc.) and may return a follow-up result.
        """
        if not self._user_commands or not text.startswith("/"):
            return None

        name, args = parse_slash_command(text)
        canonical = self._command_alias_map.get(name, name)
        cmd = self._user_commands.get(canonical)
        if cmd is None:
            return None

        ctx = self._user_command_context
        ctx.extra["command_registry"] = self._user_commands
        result = await cmd.execute(args, ctx)

        # Let the subclass handle interactive data payloads
        if result.data and not result.error:
            followup = await self.render_command_data(result, canonical)
            if followup is not None:
                return followup

        return result

    async def render_command_data(
        self, result: UserCommandResult, command_name: str
    ) -> UserCommandResult | None:
        """Render a command's interactive data payload.

        Subclasses override this to handle ``result.data`` natively:
        - CLI: print numbered list, prompt with input()
        - TUI: show selection widget in Textual
        - Web: return data as-is (frontend renders modal)

        If the user makes a selection, execute the follow-up command
        and return the new result. Return None to use the original result.
        """
        return None

    async def _execute_followup(
        self, action: str, args: str
    ) -> UserCommandResult | None:
        """Helper: execute a follow-up command by name (for render_command_data)."""
        canonical = self._command_alias_map.get(action, action)
        cmd = self._user_commands.get(canonical)
        if cmd:
            ctx = self._user_command_context
            return await cmd.execute(args, ctx)
        return None

    @property
    def is_running(self) -> bool:
        """Check if module is running."""
        return self._running

    async def start(self) -> None:
        """Start the input module."""
        self._running = True
        await self._on_start()

    async def stop(self) -> None:
        """Stop the input module."""
        self._running = False
        await self._on_stop()

    async def _on_start(self) -> None:
        """Called when module starts. Override in subclass."""
        pass

    async def _on_stop(self) -> None:
        """Called when module stops. Override in subclass."""
        pass

    @abstractmethod
    async def get_input(self) -> TriggerEvent | None:
        """Get next input event. Must be implemented by subclass."""
        ...
