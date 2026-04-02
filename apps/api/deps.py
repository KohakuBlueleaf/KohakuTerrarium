"""FastAPI dependencies."""

import os
from pathlib import Path

from kohakuterrarium.serving import KohakuManager

_manager: KohakuManager | None = None

_DEFAULT_SESSION_DIR = str(Path.home() / ".kohakuterrarium" / "sessions")


def get_manager() -> KohakuManager:
    """Return the singleton KohakuManager instance."""
    global _manager
    if _manager is None:
        session_dir = os.environ.get("KT_SESSION_DIR", _DEFAULT_SESSION_DIR)
        _manager = KohakuManager(session_dir=session_dir)
    return _manager
