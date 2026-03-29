"""Creature handle - wrapper around an Agent with terrarium metadata."""

from dataclasses import dataclass, field

from kohakuterrarium.core.agent import Agent
from kohakuterrarium.terrarium.config import CreatureConfig


@dataclass
class CreatureHandle:
    """
    Wrapper around an Agent instance with terrarium metadata.

    Tracks which channels the creature listens to and can send on,
    along with the original config and the live Agent reference.
    """

    name: str
    agent: Agent
    config: CreatureConfig
    listen_channels: list[str] = field(default_factory=list)
    send_channels: list[str] = field(default_factory=list)

    @property
    def is_running(self) -> bool:
        """Check if the underlying agent is running."""
        return self.agent.is_running
