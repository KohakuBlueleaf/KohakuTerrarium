"""
TUI session: full-screen Textual app for agent interaction.

Standalone mode: single chat area.
Terrarium mode: tabbed chat (root + creatures + channels) + terrarium panel.
"""

import asyncio
import threading
import time
from typing import Any

from rich.markdown import Markdown as RichMarkdown
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header, Input, Static, TabbedContent, TabPane

from kohakuterrarium.builtins.tui.widgets import (
    RunningPanel,
    ScratchpadPanel,
    SessionInfoPanel,
    StreamingText,
    SubAgentBlock,
    TerrariumPanel,
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
    #chat-tabs { height: 1fr; }
    #quick-status { height: 1; color: $kohaku-amber; padding: 0 1; }
    #input-box { dock: bottom; height: 3; }
    #right-status-panel { height: 1fr; overflow-y: auto; padding: 1; }

    .chat-tab-scroll { height: 1fr; padding: 0 1; }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear_output", "Clear", show=True),
        Binding("escape", "interrupt", "Interrupt", show=True),
    ]

    def __init__(
        self,
        agent_name: str = "agent",
        terrarium_tabs: list[str] | None = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.agent_name = agent_name
        # Terrarium tabs: ["root", "swe", "reviewer", "#tasks", "#review"]
        self._terrarium_tabs = terrarium_tabs
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
                if self._terrarium_tabs:
                    with TabbedContent(id="chat-tabs"):
                        for tab_name in self._terrarium_tabs:
                            label = (
                                tab_name if not tab_name.startswith("#") else tab_name
                            )
                            with TabPane(label, id=f"tab-{_safe_id(tab_name)}"):
                                yield VerticalScroll(
                                    id=f"chat-{_safe_id(tab_name)}",
                                    classes="chat-tab-scroll",
                                )
                else:
                    yield VerticalScroll(id="chat-scroll")
                yield Static("", id="quick-status")
                yield Input(placeholder="Type a message...", id="input-box")
            with Vertical(id="right-panel"):
                with VerticalScroll(id="right-status-panel"):
                    yield RunningPanel(id="running-panel")
                    yield ScratchpadPanel(id="scratchpad-panel")
                    yield SessionInfoPanel(id="session-panel")
                    if self._terrarium_tabs:
                        yield TerrariumPanel(id="terrarium-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"KohakuTerrarium - {self.agent_name}"
        self._set_status_text(IDLE_STATUS)
        self._mounted_event.set()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        chat = self._get_active_chat()
        if chat:
            chat.mount(UserMessage(text))
            chat.scroll_end(animate=False)
        event.input.clear()
        self._input_value = text
        self._input_ready.set()

    def _get_active_chat(self) -> VerticalScroll | None:
        """Get the currently visible chat scroll widget."""
        try:
            if self._terrarium_tabs:
                tabs = self.query_one("#chat-tabs", TabbedContent)
                active = tabs.active
                # active is like "tab-root", extract the id suffix
                if active:
                    scroll_id = active.replace("tab-", "chat-")
                    return self.query_one(f"#{scroll_id}", VerticalScroll)
            return self.query_one("#chat-scroll", VerticalScroll)
        except Exception:
            return None

    def get_active_tab_name(self) -> str:
        """Get the active tab name (e.g. 'root', 'swe', '#tasks')."""
        if not self._terrarium_tabs:
            return ""
        try:
            tabs = self.query_one("#chat-tabs", TabbedContent)
            active_id = tabs.active  # "tab-root"
            if active_id:
                return _id_to_name(active_id.replace("tab-", ""))
        except Exception:
            pass
        return self._terrarium_tabs[0] if self._terrarium_tabs else ""

    def action_interrupt(self) -> None:
        if self.on_interrupt:
            self.on_interrupt()

    def action_clear_output(self) -> None:
        chat = self._get_active_chat()
        if chat:
            chat.remove_children()

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


# ── Helpers ─────────────────────────────────────────────────────


def _safe_id(name: str) -> str:
    """Convert tab name to CSS-safe ID. '#tasks' -> 'ch_tasks'."""
    if name.startswith("#"):
        return "ch_" + name[1:].replace("-", "_")
    return name.replace("-", "_")


def _id_to_name(safe: str) -> str:
    """Reverse of _safe_id. 'ch_tasks' -> '#tasks'."""
    if safe.startswith("ch_"):
        return "#" + safe[3:]
    return safe


# ────────────────────────────────────────────────────────────────
# TUISession
# ────────────────────────────────────────────────────────────────


class TUISession:
    """Shared TUI state between input and output modules.

    In terrarium mode, each tab (root, creature, channel) has its own
    chat scroll. Widgets are routed to the correct tab via `target`.
    """

    def __init__(self, agent_name: str = "agent"):
        self.agent_name = agent_name
        self.running = False
        self._app: AgentTUI | None = None
        self._stop_event = asyncio.Event()
        self._streaming_widgets: dict[str, StreamingText] = {}  # target -> widget
        self._current_subagents: dict[str, SubAgentBlock] = {}  # target -> block
        # Terrarium mode
        self._terrarium_tabs: list[str] | None = None
        self._active_target: str = ""  # which tab output is currently targeting

    def set_terrarium_tabs(self, tabs: list[str]) -> None:
        """Configure terrarium mode before start()."""
        self._terrarium_tabs = tabs
        if tabs:
            self._active_target = tabs[0]

    def set_active_target(self, target: str) -> None:
        """Set which tab receives new output widgets."""
        self._active_target = target

    def get_active_tab(self) -> str:
        """Get the user's currently visible tab."""
        if self._app:
            return self._app.get_active_tab_name()
        return self._active_target

    # ── Safe widget operations ──────────────────────────────────

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

    def _get_chat_scroll_id(self, target: str = "") -> str:
        """Get the chat scroll widget ID for a target."""
        if not self._terrarium_tabs:
            return "chat-scroll"
        t = target or self._active_target
        return f"chat-{_safe_id(t)}" if t else "chat-scroll"

    def _safe_mount(self, widget: Any, scroll: bool = True, target: str = "") -> None:
        if not self._app or not self._app.is_running:
            return
        scroll_id = self._get_chat_scroll_id(target)

        def _do():
            try:
                chat = self._app.query_one(f"#{scroll_id}", VerticalScroll)
                chat.mount(widget)
                if scroll:
                    chat.scroll_end(animate=False)
            except Exception:
                pass

        self._safe_call(_do)

    # ── Chat area ───────────────────────────────────────────────

    def add_user_message(self, text: str, target: str = "") -> None:
        self._safe_mount(UserMessage(text), target=target)

    def add_trigger_message(
        self, label: str, content: str = "", target: str = ""
    ) -> None:
        self._safe_mount(TriggerMessage(label, content), target=target)

    def add_tool_block(
        self,
        tool_name: str,
        args_preview: str = "",
        tool_id: str = "",
        target: str = "",
    ) -> ToolBlock | None:
        sa = self._current_subagents.get(target or "_default")
        if sa:

            def _do():
                try:
                    sa.add_tool_line(tool_name, args_preview)
                except Exception:
                    pass

            self._safe_call(_do)
            return None
        block = ToolBlock(tool_name, args_preview, tool_id)
        self._safe_mount(block, target=target)
        return block

    def update_tool_block(
        self,
        tool_name: str,
        output: str = "",
        error: str | None = None,
        tool_id: str = "",
        target: str = "",
    ) -> None:
        if not self._app or not self._app.is_running:
            return
        scroll_id = self._get_chat_scroll_id(target)
        sa = self._current_subagents.get(target or "_default")

        def _do():
            try:
                if sa:
                    sa.update_tool_line(tool_name, done=not error, error=bool(error))
                    return
                chat = self._app.query_one(f"#{scroll_id}", VerticalScroll)
                for child in reversed(list(chat.children)):
                    if not isinstance(child, ToolBlock) or child.state != "running":
                        continue
                    if (
                        tool_id and child.tool_id == tool_id
                    ) or child.tool_name == tool_name:
                        if error:
                            child.mark_error(error)
                        else:
                            child.mark_done(output)
                        return
            except Exception:
                pass

        self._safe_call(_do)

    def add_subagent_block(
        self,
        agent_name: str,
        task: str = "",
        agent_id: str = "",
        target: str = "",
    ) -> SubAgentBlock:
        block = SubAgentBlock(agent_name, sa_task=task, agent_id=agent_id)
        self._current_subagents[target or "_default"] = block
        self._safe_mount(block, target=target)
        return block

    def end_subagent_block(
        self,
        output: str = "",
        tools_used: list[str] | None = None,
        turns: int = 0,
        duration: float = 0,
        error: str | None = None,
        target: str = "",
    ) -> None:
        key = target or "_default"
        sa = self._current_subagents.get(key)
        if not sa:
            return
        if error:
            sa.mark_error(error)
        else:
            sa.mark_done(output, tools_used, turns, duration)
        self._current_subagents.pop(key, None)

    def interrupt_subagent(self, target: str = "") -> None:
        key = target or "_default"
        sa = self._current_subagents.get(key)
        if sa:
            sa.mark_interrupted()
            self._current_subagents.pop(key, None)

    # ── Streaming text ──────────────────────────────────────────

    def begin_streaming(self, target: str = "") -> None:
        key = target or "_default"
        widget = StreamingText()
        self._streaming_widgets[key] = widget
        self._safe_mount(widget, target=target)

    def append_stream(self, chunk: str, target: str = "") -> None:
        key = target or "_default"
        if key not in self._streaming_widgets:
            self.begin_streaming(target=target)
        widget = self._streaming_widgets.get(key)
        scroll_id = self._get_chat_scroll_id(target)

        def _do():
            try:
                if widget:
                    widget.append(chunk)
                    chat = self._app.query_one(f"#{scroll_id}", VerticalScroll)
                    chat.scroll_end(animate=False)
            except Exception:
                pass

        self._safe_call(_do)

    def end_streaming(self, target: str = "") -> None:
        key = target or "_default"
        widget = self._streaming_widgets.pop(key, None)
        if not widget:
            return

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
                self._app.query_one("#scratchpad-panel", ScratchpadPanel).update_data(
                    data
                )
            except Exception:
                pass

        self._safe_call(_do)

    def update_session_info(
        self, session_id: str = "", model: str = "", tokens: int = 0
    ) -> None:
        if not self._app or not self._app.is_running:
            return

        def _do():
            try:
                self._app.query_one("#session-panel", SessionInfoPanel).set_info(
                    session_id, model, tokens
                )
            except Exception:
                pass

        self._safe_call(_do)

    def add_tokens(self, count: int) -> None:
        if not self._app or not self._app.is_running:
            return

        def _do():
            try:
                self._app.query_one("#session-panel", SessionInfoPanel).add_tokens(
                    count
                )
            except Exception:
                pass

        self._safe_call(_do)

    def update_terrarium(self, creatures: list[dict], channels: list[dict]) -> None:
        """Update the terrarium overview panel."""
        if not self._app or not self._app.is_running:
            return

        def _do():
            try:
                panel = self._app.query_one("#terrarium-panel", TerrariumPanel)
                panel.set_topology(creatures, channels)
            except Exception:
                pass

        self._safe_call(_do)

    def write_log(self, text: str) -> None:
        pass  # Logs go to session DB

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
        self._app = AgentTUI(
            agent_name=self.agent_name,
            terrarium_tabs=self._terrarium_tabs,
        )
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
