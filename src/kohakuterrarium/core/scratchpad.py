"""
Session-scoped key-value working memory.

Different from memory (file-based, cross-session, agent-managed).
Scratchpad is session-scoped, framework-managed, structured, and cheap.
"""

from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class Scratchpad:
    """
    Session-scoped key-value working memory.

    Different from memory (file-based, cross-session, agent-managed).
    Scratchpad is:
    - Session-scoped (cleared on restart)
    - Framework-managed (auto-injected into context)
    - Structured (key-value, not free-form)
    - Cheap (no LLM needed to read/write)
    """

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        logger.debug("Scratchpad initialized")

    def set(self, key: str, value: str) -> None:
        """Set a key-value pair."""
        self._data[key] = value
        logger.debug("Scratchpad set", key=key)

    def get(self, key: str) -> str | None:
        """Get value by key. Returns None if not found."""
        return self._data.get(key)

    def delete(self, key: str) -> bool:
        """Delete a key. Returns True if existed."""
        if key in self._data:
            del self._data[key]
            logger.debug("Scratchpad deleted", key=key)
            return True
        return False

    def list_keys(self) -> list[str]:
        """List all keys."""
        return list(self._data.keys())

    def clear(self) -> None:
        """Clear all data."""
        self._data.clear()
        logger.debug("Scratchpad cleared")

    def to_dict(self) -> dict[str, str]:
        """Get all data as a dict copy."""
        return self._data.copy()

    def to_prompt_section(self) -> str:
        """
        Format scratchpad as a prompt section for injection into system prompt.

        Returns empty string if scratchpad is empty.
        Returns markdown with ## Working Memory header if has data.
        """
        if not self._data:
            return ""

        lines = ["## Working Memory\n"]
        for key, value in self._data.items():
            # For multi-line values, indent them
            if "\n" in value:
                lines.append(f"### {key}\n{value}\n")
            else:
                lines.append(f"- **{key}**: {value}")

        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __repr__(self) -> str:
        return f"Scratchpad(keys={list(self._data.keys())})"


def get_scratchpad() -> Scratchpad:
    """Get scratchpad from the default session. Prefer context.session.scratchpad."""
    # Import inside function to avoid circular import:
    # session.py imports Scratchpad from this module
    from kohakuterrarium.core.session import get_session

    return get_session().scratchpad
