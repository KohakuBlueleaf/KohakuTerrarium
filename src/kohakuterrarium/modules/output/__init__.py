"""
Output module - route and deliver agent output.

Exports:
- OutputModule: Protocol for output modules
- BaseOutputModule: Base class for output modules
- StdoutOutput: Terminal output implementation
- OutputRouter: Routes parse events to outputs
"""

from kohakuterrarium.modules.output.base import BaseOutputModule, OutputModule
from kohakuterrarium.modules.output.router import (
    MultiOutputRouter,
    OutputRouter,
    OutputState,
)
from kohakuterrarium.modules.output.stdout import PrefixedStdoutOutput, StdoutOutput

__all__ = [
    # Protocol and base
    "OutputModule",
    "BaseOutputModule",
    # Router
    "OutputRouter",
    "MultiOutputRouter",
    "OutputState",
    # Implementations
    "StdoutOutput",
    "PrefixedStdoutOutput",
]
