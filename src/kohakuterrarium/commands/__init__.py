"""
Commands module - framework commands for controller.

Commands are special actions like ##read##, ##info## that the
controller can use to interact with the framework.
"""

from kohakuterrarium.commands.base import (
    BaseCommand,
    Command,
    CommandResult,
    parse_command_args,
)
from kohakuterrarium.commands.read import InfoCommand, ReadCommand

__all__ = [
    # Protocol and base
    "Command",
    "BaseCommand",
    "CommandResult",
    "parse_command_args",
    # Implementations
    "ReadCommand",
    "InfoCommand",
]
