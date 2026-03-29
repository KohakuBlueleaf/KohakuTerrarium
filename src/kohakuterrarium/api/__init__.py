"""Core service API for hosting and managing agents and terrariums.

All runtime operations go through KohakuManager. Event types are
transport-agnostic dataclasses usable by any interface layer.
"""

from kohakuterrarium.api.agent_session import AgentSession
from kohakuterrarium.api.events import ChannelEvent, OutputEvent
from kohakuterrarium.api.manager import KohakuManager

__all__ = [
    "AgentSession",
    "ChannelEvent",
    "KohakuManager",
    "OutputEvent",
]
