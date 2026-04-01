"""FastAPI dependencies."""

import os

from kohakuterrarium.serving import KohakuManager

_manager: KohakuManager | None = None


def get_manager() -> KohakuManager:
    """Return the singleton KohakuManager instance."""
    global _manager
    if _manager is None:
        session_dir = os.environ.get("KT_SESSION_DIR", ".kohaku/sessions")
        _manager = KohakuManager(session_dir=session_dir)
    return _manager
