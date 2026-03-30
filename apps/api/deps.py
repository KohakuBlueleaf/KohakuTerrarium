"""FastAPI dependencies."""

from kohakuterrarium.serving import KohakuManager

_manager: KohakuManager | None = None


def get_manager() -> KohakuManager:
    """Return the singleton KohakuManager instance."""
    global _manager
    if _manager is None:
        _manager = KohakuManager()
    return _manager
