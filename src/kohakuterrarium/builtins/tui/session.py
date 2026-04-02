"""
TUI session: full-screen Textual app for agent interaction.

Layout:
  +--- KohakuTerrarium -----------------------------------------------+
  | [Chat]                            | Running / Scratchpad / Session |
  +-----------------------------------+-------------------------------+
  |                                   | +-- Running ----------------+ |
  | +- You ----------------------+   | | (idle)                    | |
  | | Fix the auth bug           |   | +---------------------------+ |
  | +----------------------------+   |                               |
  |                                   | +-- Scratchpad -------------+ |
  | I'll investigate the module.      | | (empty)                   | |
  |                                   | +---------------------------+ |
  | [+] read src/auth/middleware.py   |                               |
  |                                   | +-- Session ----------------+ |
  | The issue is on line 42...        | | Runtime: 2m 31s           | |
  |                                   | +---------------------------+ |
  | KohakUwU  o Idle                  |                               |
  +-----------------------------------+                               |
  | > _                               |                               |
  +-----------------------------------+-------------------------------+
  | Esc: interrupt  Ctrl+C: quit  Ctrl+L: clear             F1: help |
  +-------------------------------------------------------------------+
"""

import asyncio
import threading
import time
from typing import Any

from rich.markdown import Markdown as RichMarkdown
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header, Input, Static

from kohakuterrarium.builtins.tui.widgets import (
    RunningPanel,
    ScratchpadPanel,
    SessionInfoPanel,
    StreamingText,
    SubAgentBlock,
    ToolBlock,
    TriggerMessage,
    UserMessage,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)

IDLE_STATUS = "\u25cf KohakUwU"

THINKING_FRAMES = [
    "\u25d0 KohakUwUing",
    "\u25d3 KohakUwUing.",
    "\u25d1 KohakUwUing..",
    "\u25d2 KohakUwUing...",
]


class AgentTUI(App):
    """Textual app for KohakuTerrarium agent interaction."""

    TITLE = "KohakuTerrarium"
    CSS = """
    $kohaku-iolite: #5A4FCF;
    $kohaku-amber: #D4920A;

    Header { background: $kohaku-iolite; color: white; }
    Footer { background: $kohaku-iolite 15%; }

    #main-container { height: 1fr; }
    #left-panel { width: 2fr; }
    #right-panel { width: 1fr; min-width: 30; }
    #chat-scroll { height: 1fr; border: solid $primary-background; padding: 0 1; }
    #quick-status { height: 1; color: $kohaku-amber; padding: 0 1; }
    #input-box { dock: bottom; height: 3; }
    #right-status-panel { height: 1fr; overflow-y: auto; padding: 1; }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear_output", "Clear", show=True),
        Binding("escape", "interrupt", "Interrupt", show=True),
    ]

    def __init__(self, agent_name: str = "agent", **kwargs: Any):
        super().__init__(**kwargs)
        self.agent_name = agent_name
        self._input_ready = asyncio.Event()
        self._input_value: str = ""
        self._stop_event = asyncio.Event()
        self._mounted_event = asyncio.Event()
        self._thinking_active = False
        self._thinking_thread: threading.Thread | None = None
        self.on_interrupt: Any = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            with Vertical(id="left-panel"):
                yield VerticalScroll(id="chat-scroll")
                yield Static("", id="quick-status")
                yield Input(placeholder="Type a message...", id="input-box")
            with Vertical(id="right-panel"):
                with VerticalScroll(id="right-status-panel"):
                    yield RunningPanel(id="running-panel")
                    yield ScratchpadPanel(id="scratchpad-panel")
                    yield SessionInfoPanel(id="session-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"KohakuTerrarium - {self.agent_name}"
        self._set_status_text(IDLE_STATUS)
        self._mounted_event.set()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        chat = self.query_one("#chat-scroll", VerticalScroll)
        chat.mount(UserMessage(text))
        chat.scroll_end(animate=False)
        event.input.clear()
        self._input_value = text
        self._input_ready.set()

    def action_interrupt(self) -> None:
        if self.on_interrupt:
            self.on_interrupt()

    def action_clear_output(self) -> None:
        self.query_one("#chat-scroll", VerticalScroll).remove_children()

    def action_quit(self) -> None:
        self._input_value = ""
        self._stop_event.set()
        self._input_ready.set()
        self.exit()

    # ── Thinking animation ──────────────────────────────────────

    def start_thinking_animation(self) -> None:
        self._thinking_active = True
        self._thinking_thread = threading.Thread(
            target=self._thinking_loop, daemon=True
        )
        self._thinking_thread.start()

    def stop_thinking_animation(self) -> None:
        self._thinking_active = False
        try:
            self.call_from_thread(self._clear_status)
        except Exception:
            pass

    def _thinking_loop(self) -> None:
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
        try:
            self.query_one("#quick-status", Static).update(text)
        except Exception:
            pass

    def _clear_status(self) -> None:
        try:
            self.query_one("#quick-status", Static).update("")
        except Exception:
            pass


# ────────────────────────────────────────────────────────────────
# TUISession
# ────────────────────────────────────────────────────────────────


class TUISession:
    """Shared TUI state between input and output modules."""

    def __init__(self, agent_name: str = "agent"):
        self.agent_name = agent_name
        self.running = False
        self._app: AgentTUI | None = None
        self._stop_event = asyncio.Event()
        self._streaming_widget: StreamingText | None = None
        self._current_subagent: SubAgentBlock | None = None

    def _safe_call(self, fn: Any, *args: Any) -> None:
        if not self._app or not self._app.is_running:
            return
        try:
            self._app.call_later(fn, *args)
        except Exception:
            try:
                self._app.call_from_thread(fn, *args)
            except Exception:
                pass

    def _safe_mount(self, widget: Any, scroll: bool = True) -> None:
        if not self._app or not self._app.is_running:
            return

        def _do():
            try:
                chat = self._app.query_one("#chat-scroll", VerticalScroll)
                chat.mount(widget)
                if scroll:
                    chat.scroll_end(animate=False)
            except Exception:
                pass

        self._safe_call(_do)

    # ── Chat area ───────────────────────────────────────────────

    def add_user_message(self, text: str) -> None:
        self._safe_mount(UserMessage(text))

    def add_trigger_message(self, label: str, content: str = "") -> None:
        self._safe_mount(TriggerMessage(label, content))

    def add_tool_block(
        self, tool_name: str, args_preview: str = "", tool_id: str = ""
    ) -> ToolBlock | None:
        if self._current_subagent:
            def _do():
                try:
                    self._current_subagent.add_tool_line(tool_name, args_preview)
                except Exception:
                    pass
            self._safe_call(_do)
            return None
        block = ToolBlock(tool_name, args_preview, tool_id)
        self._safe_mount(block)
        return block

    def update_tool_block(
        self, tool_name: str, output: str = "", error: str | None = None,
        tool_id: str = "",
    ) -> None:
        if not self._app or not self._app.is_running:
            return

        def _do():
            try:
                if self._current_subagent:
                    self._current_subagent.update_tool_line(
                        tool_name, done=not error, error=bool(error)
                    )
                    return
                chat = self._app.query_one("#chat-scroll", VerticalScroll)
                for child in reversed(list(chat.children)):
                    if not isinstance(child, ToolBlock) or child.state != "running":
                        continue
                    if (tool_id and child.tool_id == tool_id) or child.tool_name == tool_name:
                        if error:
                            child.mark_error(error)
                        else:
                            child.mark_done(output)
                        return
            except Exception:
                pass

        self._safe_call(_do)

    def add_subagent_block(
        self, agent_name: str, task: str = "", agent_id: str = ""
    ) -> SubAgentBlock:
        block = SubAgentBlock(agent_name, sa_task=task, agent_id=agent_id)
        self._current_subagent = block
        self._safe_mount(block)
        return block

    def end_subagent_block(
        self, output: str = "", tools_used: list[str] | None = None,
        turns: int = 0, duration: float = 0, error: str | None = None,
    ) -> None:
        if not self._current_subagent:
            return
        if error:
            self._current_subagent.mark_error(error)
        else:
            self._current_subagent.mark_done(output, tools_used, turns, duration)
        self._current_subagent = None

    def interrupt_subagent(self) -> None:
        if self._current_subagent:
            self._current_subagent.mark_interrupted()
            self._current_subagent = None

    # ── Streaming text ──────────────────────────────────────────

    def begin_streaming(self) -> None:
        self._streaming_widget = StreamingText()
        self._safe_mount(self._streaming_widget)

    def append_stream(self, chunk: str) -> None:
        if not self._streaming_widget:
            self.begin_streaming()

        def _do():
            try:
                if self._streaming_widget:
                    self._streaming_widget.append(chunk)
                    chat = self._app.query_one("#chat-scroll", VerticalScroll)
                    chat.scroll_end(animate=False)
            except Exception:
                pass

        self._safe_call(_do)

    def end_streaming(self) -> None:
        if not self._streaming_widget:
            return
        widget = self._streaming_widget
        self._streaming_widget = None

        def _do():
            try:
                text = widget.get_text().strip()
                if text:
                    widget.update(RichMarkdown(text))
            except Exception:
                pass

        self._safe_call(_do)

    # ── Right panel ─────────────────────────────────────────────

    def update_running(self, item_id: str, label: str, remove: bool = False) -> None:
        if not self._app or not self._app.is_running:
            return

        def _do():
            try:
                panel = self._app.query_one("#running-panel", RunningPanel)
                if remove:
                    panel.remove_item(item_id)
                else:
                    panel.add_item(item_id, label)
            except Exception:
                pass

        self._safe_call(_do)

    def clear_running(self) -> None:
        if not self._app or not self._app.is_running:
            return

        def _do():
            try:
                self._app.query_one("#running-panel", RunningPanel).clear()
            except Exception:
                pass

        self._safe_call(_do)

    def update_scratchpad(self, data: dict) -> None:
        if not self._app or not self._app.is_running:
            return

        def _do():
            try:
                self._app.query_one("#scratchpad-panel", ScratchpadPanel).update_data(data)
            except Exception:
                pass

        self._safe_call(_do)

    def update_session_info(self, session_id: str = "", model: str = "", tokens: int = 0) -> None:
        if not self._app or not self._app.is_running:
            return

        def _do():
            try:
                self._app.query_one("#session-panel", SessionInfoPanel).set_info(session_id, model, tokens)
            except Exception:
                pass

        self._safe_call(_do)

    def add_tokens(self, count: int) -> None:
        if not self._app or not self._app.is_running:
            return

        def _do():
            try:
                self._app.query_one("#session-panel", SessionInfoPanel).add_tokens(count)
            except Exception:
                pass

        self._safe_call(_do)

    def write_log(self, text: str) -> None:
        pass  # Logs go to session DB now

    # ── Processing animation ────────────────────────────────────

    def start_thinking(self) -> None:
        if self._app and self._app.is_running:
            try:
                self._app.start_thinking_animation()
            except Exception:
                pass

    def stop_thinking(self) -> None:
        if self._app and self._app.is_running:
            try:
                self._app.stop_thinking_animation()
            except Exception:
                pass

    def set_idle(self) -> None:
        if self._app and self._app.is_running:
            try:
                self._app.query_one("#quick-status", Static).update(IDLE_STATUS)
            except Exception:
                pass

    # ── Lifecycle ───────────────────────────────────────────────

    async def wait_ready(self, timeout: float = 5.0) -> bool:
        if not self._app:
            return False
        try:
            await asyncio.wait_for(self._app._mounted_event.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def start(self, prompt: str = "You: ") -> None:
        self._app = AgentTUI(agent_name=self.agent_name)
        self.running = True
        self._stop_event.clear()

    async def run_app(self) -> None:
        if not self._app:
            return
        try:
            await self._app.run_async()
        except Exception as e:
            logger.error("TUI app error", error=str(e))
        finally:
            self.running = False
            self._stop_event.set()
            self._app._input_ready.set()

    async def get_input(self, prompt: str = "You: ") -> str:
        if not self._app:
            return ""
        self._app._input_ready.clear()
        self._app._input_value = ""
        await self._app._input_ready.wait()
        return self._app._input_value

    def stop(self) -> None:
        self.running = False
        self._stop_event.set()
        if self._app:
            self._app._input_ready.set()
            if self._app.is_running:
                self._app.exit()

    async def wait_for_stop(self) -> None:
        await self._stop_event.wait()
