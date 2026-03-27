"""
Session registry - unified keyed storage for session-scoped shared state.

A Session holds all shared objects for one agent (or group of cooperating agents):
channels, scratchpad, TUI state, and user-provided extras.

Usage:
    from kohakuterrarium.core.session import get_session, set_session

    # Get or create by key
    session = get_session("my_agent")
    session.scratchpad.set("key", "value")
    channel = session.channels.get_or_create("inbox")

    # Inject custom session (testing, programmatic use)
    set_session(my_custom_session, key="test")
"""

from dataclasses import dataclass, field
from typing import Any

from kohakuterrarium.core.channel import ChannelRegistry
from kohakuterrarium.core.scratchpad import Scratchpad
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_KEY = "__default__"


@dataclass
class Session:
    """
    All session-scoped shared state for one agent.

    Attributes:
        key: Session identifier
        channels: Channel registry for cross-component messaging
        scratchpad: Session-scoped key-value working memory
        tui: TUI session state (set when TUI mode active)
        extra: User-provided custom state (database connections, API clients, etc.)
    """

    key: str
    channels: ChannelRegistry = field(default_factory=ChannelRegistry)
    scratchpad: Scratchpad = field(default_factory=Scratchpad)
    tui: Any | None = None
    extra: dict[str, Any] = field(default_factory=dict)


_sessions: dict[str, Session] = {}


def get_session(key: str | None = None) -> Session:
    """
    Get or create a session by key.

    Args:
        key: Session key. None or omitted uses the default session.

    Returns:
        Session instance (created if not exists)
    """
    k = key or _DEFAULT_KEY
    if k not in _sessions:
        _sessions[k] = Session(key=k)
        logger.debug("Session created", session_key=k)
    return _sessions[k]


def set_session(session: Session, key: str | None = None) -> None:
    """
    Inject a custom session. For programmatic/testing use.

    Args:
        session: Session to inject
        key: Session key. None uses the default key.
    """
    k = key or _DEFAULT_KEY
    _sessions[k] = session
    logger.debug("Session injected", session_key=k)


def remove_session(key: str | None = None) -> None:
    """
    Remove a session. For cleanup/testing.

    Args:
        key: Session key to remove. None removes the default session.
    """
    k = key or _DEFAULT_KEY
    if _sessions.pop(k, None) is not None:
        logger.debug("Session removed", session_key=k)


def list_sessions() -> list[str]:
    """List all active session keys."""
    return list(_sessions.keys())
