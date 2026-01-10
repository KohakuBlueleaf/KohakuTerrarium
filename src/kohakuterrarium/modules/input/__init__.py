"""
Input module - receive external input and produce TriggerEvents.

Exports:
- InputModule: Protocol for input modules
- BaseInputModule: Base class for input modules
- CLIInput: Terminal input implementation
"""

from kohakuterrarium.modules.input.base import BaseInputModule, InputModule
from kohakuterrarium.modules.input.cli import CLIInput, NonBlockingCLIInput

__all__ = [
    # Protocol and base
    "InputModule",
    "BaseInputModule",
    # Implementations
    "CLIInput",
    "NonBlockingCLIInput",
]
