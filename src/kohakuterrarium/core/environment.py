"""
Environment - isolated execution context for multi-session support.

Environment = shared state per user request (inter-creature channels, config)
Session = private state per creature (scratchpad, sub-agent channels)
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from kohakuterrarium.core.channel import ChannelRegistry
from kohakuterrarium.core.session import Session
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Environment:
    """Isolated execution context. One per terrarium or user request.

    Holds shared resources (inter-creature channels) and manages
    per-creature Sessions. Modules can register additional shared
    state via the register/get pattern.
    """

    env_id: str = field(default_factory=lambda: f"env_{uuid4().hex[:8]}")
    shared_channels: ChannelRegistry = field(default_factory=ChannelRegistry)
    _sessions: dict[str, Session] = field(default_factory=dict)
    _context: dict[str, Any] = field(default_factory=dict)

    def get_session(self, key: str) -> Session:
        """Get or create a creature-private session."""
        if key not in self._sessions:
            self._sessions[key] = Session(key=key)
            logger.debug(
                "Session created in environment",
                env_id=self.env_id,
                session_key=key,
            )
        return self._sessions[key]

    def list_sessions(self) -> list[str]:
        """List all session keys in this environment."""
        return list(self._sessions.keys())

    def register(self, key: str, value: Any) -> None:
        """Register env-level shared state. Modules use this for extensibility."""
        self._context[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get env-level shared state."""
        return self._context.get(key, default)
