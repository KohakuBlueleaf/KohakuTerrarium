"""
Input module protocol and base class.

Input modules receive external input and produce TriggerEvents.
Integrates with the user command system for slash commands.
"""

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from kohakuterrarium.core.events import TriggerEvent


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

    async def try_user_command(self, text: str) -> Any | None:
        """Try to execute a slash command, handling rich UI data.

        For commands that return structured ``data`` (confirm, select, etc.),
        this method handles the interactive flow in the terminal before
        returning the final result.

        Returns UserCommandResult or None if not a known command.
        """
        if not self._user_commands or not text.startswith("/"):
            return None

        from kohakuterrarium.modules.user_command.base import parse_slash_command

        name, args = parse_slash_command(text)
        canonical = self._command_alias_map.get(name, name)
        cmd = self._user_commands.get(canonical)
        if cmd is None:
            return None

        # Update context with latest refs
        ctx = self._user_command_context
        ctx.extra["command_registry"] = self._user_commands
        result = await cmd.execute(args, ctx)

        # Handle interactive data payloads (confirm, select)
        if result.data and not result.error:
            followup = await self._handle_ui_data(result)
            if followup is not None:
                return followup

        return result

    async def _handle_ui_data(self, result: Any) -> Any | None:
        """Handle rich UI payloads interactively in the terminal.

        For ``confirm``: prompts [y/N], re-executes with action_args if yes.
        For ``select``: shows numbered list, re-executes with chosen value.
        Returns a new UserCommandResult if interaction happened, None otherwise.
        """
        import asyncio

        from kohakuterrarium.modules.user_command.base import UserCommandResult

        data = result.data
        data_type = data.get("type", "")

        if data_type == "confirm":
            print(data.get("message", "Confirm?"))
            loop = asyncio.get_event_loop()
            answer = await loop.run_in_executor(None, lambda: input("[y/N]: ").strip())
            if answer.lower() in ("y", "yes"):
                action = data.get("action", "")
                action_args = data.get("action_args", "")
                if action:
                    canonical = self._command_alias_map.get(action, action)
                    cmd = self._user_commands.get(canonical)
                    if cmd:
                        ctx = self._user_command_context
                        return await cmd.execute(action_args, ctx)
            return UserCommandResult(output="Cancelled.", consumed=True)

        if data_type == "select":
            options = data.get("options", [])
            if not options:
                return None
            print(data.get("title", "Select:"))
            for i, opt in enumerate(options, 1):
                marker = " *" if opt.get("selected") else ""
                label = opt.get("label", opt.get("value", ""))
                extra = opt.get("provider", "")
                extra_str = f"  ({extra})" if extra else ""
                print(f"  {i:>3}. {label}{extra_str}{marker}")
            print(f"  Enter number (1-{len(options)}) or name, empty to cancel:")
            loop = asyncio.get_event_loop()
            choice = await loop.run_in_executor(None, lambda: input("> ").strip())
            if not choice:
                return UserCommandResult(output="Cancelled.", consumed=True)
            # Resolve choice: number or name
            selected = None
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    selected = options[idx]["value"]
            else:
                selected = choice
            if selected:
                action = data.get("action", "")
                if action:
                    canonical = self._command_alias_map.get(action, action)
                    cmd = self._user_commands.get(canonical)
                    if cmd:
                        ctx = self._user_command_context
                        return await cmd.execute(selected, ctx)
            return UserCommandResult(output="Cancelled.", consumed=True)

        # Other types (notify, info_panel, list, text): no interaction needed
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
