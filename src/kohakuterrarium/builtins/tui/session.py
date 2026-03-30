"""
TUI session - full-screen Textual app for agent interaction.

Layout:
  ┌─ KohakuTerrarium ──────────────────────────────────────┐
  │                             │ [Status] [Logs]          │
  │  ┌─ You ──────────────┐    │                          │
  │  │ Fix the auth bug    │    │  (detailed status log)   │
  │  └────────────────────┘    │                          │
  │                             │                          │
  │  ── Assistant ──────────    │                          │
  │  I'll check the module...   │                          │
  │                             │                          │
  │    ⚙ bash: command=ls src/  │                          │
  │    ✓ bash: OK               │                          │
  │    ⚙ read: file=auth.py     │                          │
  │    ✓ read: OK               │                          │
  │                             │                          │
  │  Found the issue in ...     │                          │
  │  ──────────────────────    │                          │
  │                             │                          │
  │ KohakUwUing...              │                          │
  ├─────────────────────────────┤                          │
  │ You: _                      │                          │
  └────────────────────────── Ctrl+C quit ─────────────────┘
"""

import asyncio
import threading
import time
from typing import Any

from rich.markdown import Markdown as RichMarkdown
from rich.panel import Panel
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Footer,
    Header,
    Input,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)

from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


THINKING_FRAMES = [
    "◐ KohakUwUing",
    "◓ KohakUwUing.",
    "◑ KohakUwUing..",
    "◒ KohakUwUing...",
]


class AgentTUI(App):
    """Textual app for KohakuTerrarium agent interaction."""

    TITLE = "KohakuTerrarium"
    CSS = """
    #main-container {
        height: 1fr;
    }

    #left-panel {
        width: 2fr;
    }

    #right-panel {
        width: 1fr;
        min-width: 30;
    }

    #output-log {
        height: 1fr;
        border: solid $primary-background;
    }

    #quick-status {
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }

    #input-box {
        dock: bottom;
        height: 3;
    }

    #jobs-log, #logs-log {
        height: 1fr;
    }

    TabbedContent {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear_output", "Clear", show=True),
    ]

    def __init__(self, agent_name: str = "agent", **kwargs: Any):
        super().__init__(**kwargs)
        self.agent_name = agent_name
        self._input_ready = asyncio.Event()
        self._input_value: str = ""
        self._stop_event = asyncio.Event()
        self._thinking_active = False
        self._thinking_thread: threading.Thread | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            with Vertical(id="left-panel"):
                yield RichLog(id="output-log", highlight=True, markup=False, wrap=True)
                yield Static("", id="quick-status")
                yield Input(placeholder="Type a message...", id="input-box")
            with Vertical(id="right-panel"):
                with TabbedContent():
                    with TabPane("Status", id="tab-status"):
                        yield RichLog(
                            id="jobs-log", highlight=True, markup=False, wrap=True
                        )
                    with TabPane("Logs", id="tab-logs"):
                        yield RichLog(
                            id="logs-log", highlight=False, markup=False, wrap=True
                        )
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"KohakuTerrarium - {self.agent_name}"
        output = self.query_one("#output-log", RichLog)
        output.write(
            Panel(
                f"Agent: {self.agent_name}\n" "Type a message below. Ctrl+C to quit.",
                title="Welcome",
                border_style="dim",
            )
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in input box."""
        text = event.value.strip()
        if not text:
            return

        output = self.query_one("#output-log", RichLog)
        output.write(Panel(text, title="You", title_align="left", border_style="cyan"))

        event.input.clear()
        self._input_value = text
        self._input_ready.set()

    def start_thinking_animation(self) -> None:
        """Start KohakUwUing animation in a background thread."""
        self._thinking_active = True
        self._thinking_thread = threading.Thread(
            target=self._thinking_loop, daemon=True
        )
        self._thinking_thread.start()

    def stop_thinking_animation(self) -> None:
        """Stop animation and clear status line."""
        self._thinking_active = False
        try:
            self.call_from_thread(self._clear_status)
        except Exception:
            pass

    def _thinking_loop(self) -> None:
        """Background thread that cycles animation frames."""
        idx = 0
        while self._thinking_active:
            frame = THINKING_FRAMES[idx % len(THINKING_FRAMES)]
            try:
                self.call_from_thread(self._set_status_text, frame)
            except Exception:
                break
            idx += 1
            time.sleep(0.3)

    def _set_status_text(self, text: str) -> None:
        """Update status widget (must be called on Textual thread)."""
        try:
            self.query_one("#quick-status", Static).update(text)
        except Exception:
            pass

    def _clear_status(self) -> None:
        """Clear status widget (must be called on Textual thread)."""
        try:
            self.query_one("#quick-status", Static).update("")
        except Exception:
            pass

    def action_clear_output(self) -> None:
        """Clear the output log."""
        self.query_one("#output-log", RichLog).clear()

    def action_quit(self) -> None:
        """Quit the app."""
        self._input_value = ""
        self._stop_event.set()
        self._input_ready.set()
        self.exit()


class TUISession:
    """
    Shared TUI state between input and output modules.

    Wraps the Textual AgentTUI app. Both TUIInput and TUIOutput
    reference the same TUISession via the Session registry (session.tui).
    """

    def __init__(self, agent_name: str = "agent"):
        self.agent_name = agent_name
        self.running = False
        self._app: AgentTUI | None = None
        self._stop_event = asyncio.Event()
        self._assistant_buffer: list[str] = []

    def _safe_write(self, widget_id: str, content: Any) -> None:
        """Safely write to a RichLog widget via Textual's thread-safe call."""
        if not self._app or not self._app.is_running:
            return
        try:
            self._app.call_from_thread(self._do_write, widget_id, content)
        except Exception:
            # Fallback: try direct write (works if already on Textual thread)
            try:
                widget = self._app.query_one(f"#{widget_id}", RichLog)
                widget.write(content)
            except Exception:
                pass

    @staticmethod
    def _do_write_static(app: Any, widget_id: str, content: Any) -> None:
        """Write content to widget (runs on Textual thread)."""
        try:
            widget = app.query_one(f"#{widget_id}", RichLog)
            widget.write(content)
        except Exception:
            pass

    def _do_write(self, widget_id: str, content: Any) -> None:
        """Instance method for call_from_thread."""
        if self._app:
            self._do_write_static(self._app, widget_id, content)

    def write_to_output(self, content: Any) -> None:
        """
        Write directly to the main output RichLog (unbuffered).

        Unlike write_output() which buffers text for markdown rendering,
        this writes Rich Text objects immediately - used for inline tool
        activity display.
        """
        self._safe_write("output-log", content)

    async def start(self, prompt: str = "You: ") -> None:
        """Create the Textual app."""
        self._app = AgentTUI(agent_name=self.agent_name)
        self.running = True
        self._stop_event.clear()
        logger.debug("TUI session created", agent_name=self.agent_name)

    async def run_app(self) -> None:
        """Run the Textual app event loop. Call from a background task."""
        if not self._app:
            return
        try:
            await self._app.run_async()
        except Exception as e:
            # Can't write to TUI if app crashed, just log
            logger.error("TUI app error", error=str(e))
        finally:
            self.running = False
            self._stop_event.set()
            self._app._input_ready.set()

    async def get_input(self, prompt: str = "You: ") -> str:
        """Wait for user input. Returns empty string on stop."""
        if not self._app:
            return ""

        self._flush_assistant_block()

        self._app._input_ready.clear()
        self._app._input_value = ""
        await self._app._input_ready.wait()
        return self._app._input_value

    def write_output(self, text: str) -> None:
        """Buffer assistant output. Rendered as markdown on turn end."""
        if not text:
            return
        self._assistant_buffer.append(text)

    def write_line(self, text: str) -> None:
        """Buffer a line of assistant output."""
        self.write_output(text)

    def _flush_assistant_block(self) -> None:
        """Render buffered assistant output as markdown."""
        if not self._assistant_buffer:
            return
        full_text = "\n".join(self._assistant_buffer)
        if full_text.strip():
            try:
                self._safe_write("output-log", RichMarkdown(full_text))
            except Exception:
                self._safe_write("output-log", Text(full_text))
        self._assistant_buffer.clear()

    def begin_assistant_turn(self) -> None:
        """Mark the start of an assistant turn (just a blank line separator)."""
        self._assistant_buffer.clear()

    def end_assistant_turn(self) -> None:
        """Render the assistant turn (flush buffer, add blank line)."""
        self._flush_assistant_block()
        self._safe_write("output-log", "")

    def write_log(self, text: str) -> None:
        """Write to the Logs tab."""
        self._safe_write("logs-log", text)

    def update_status(self, text: str) -> None:
        """Append to the Status tab."""
        self._safe_write("jobs-log", text)

    def set_status(self, text: str) -> None:
        """Alias for update_status."""
        self.update_status(text)

    def start_thinking(self) -> None:
        """Start the KohakUwUing processing animation."""
        if not self._app or not self._app.is_running:
            return
        try:
            self._app.start_thinking_animation()
        except Exception:
            pass

    def stop_thinking(self) -> None:
        """Stop the KohakUwUing processing animation."""
        if not self._app or not self._app.is_running:
            return
        try:
            self._app.stop_thinking_animation()
        except Exception:
            pass

    def set_subtitle(self, text: str) -> None:
        """Update the quick status line above input box."""
        if not self._app or not self._app.is_running:
            return
        try:
            status = self._app.query_one("#quick-status", Static)
            status.update(text)
        except Exception:
            pass

    def stop(self) -> None:
        """Stop the TUI."""
        self.running = False
        self._stop_event.set()
        if self._app:
            self._app._input_ready.set()
            if self._app.is_running:
                self._app.exit()

    async def wait_for_stop(self) -> None:
        """Block until stop is signaled."""
        await self._stop_event.wait()
