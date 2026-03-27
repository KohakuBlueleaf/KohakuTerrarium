"""
TUI (Terminal UI) module - shared input/output with rich display.

Provides TUIInput and TUIOutput that share a TUISession via the
Session registry. Both modules access session.tui for shared state.
"""

from kohakuterrarium.builtins.tui.session import TUISession

__all__ = ["TUISession"]
