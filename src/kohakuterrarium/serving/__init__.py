"""Core service API for hosting and managing agents and terrariums.

All runtime operations go through KohakuManager. Event types are
transport-agnostic dataclasses usable by any interface layer.
"""

from kohakuterrarium.serving.agent_session import AgentSession
from kohakuterrarium.serving.events import ChannelEvent, OutputEvent
from kohakuterrarium.serving.manager import KohakuManager

__all__ = [
    "AgentSession",
    "ChannelEvent",
    "KohakuManager",
    "OutputEvent",
]
