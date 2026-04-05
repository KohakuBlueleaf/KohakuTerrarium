"""
TUI session: full-screen Textual app for agent interaction.

Standalone mode: single chat area.
Terrarium mode: tabbed chat (root + creatures + channels) + terrarium panel.
"""

import asyncio
import threading
import time
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header, Markdown, Static, TabbedContent, TabPane

from kohakuterrarium.builtins.tui.widgets import (
    ChatInput,
    CompactSummaryBlock,
    LoadOlderButton,
    QueuedMessage,
    RunningPanel,
    ScratchpadPanel,
    SessionInfoPanel,
    StreamingText,
    SubAgentBlock,
    SystemNotice,
    TerrariumPanel,
    ToolBlock,
    TriggerMessage,
    UserMessage,
)
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)

# Default widget limits (configurable via TUISession)
DEFAULT_MAX_CHAT_WIDGETS = 80  # Cull when exceeding this
DEFAULT_CULL_KEEP = 50  # Keep this many after cull
DEFAULT_LOAD_BATCH = 30  # Load this many when "Load older" clicked
CULL_KEEP = DEFAULT_CULL_KEEP  # Module-level for import by output.py

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
    #input-box { dock: bottom; }
    #queued-area { height: auto; max-height: 6; padding: 0 1; }
    #right-status-panel { height: 1fr; overflow-y: auto; padding: 1; }

    .chat-tab-scroll { height: 1fr; padding: 0 1; }
    .cull-header { height: 1; color: $text-muted; text-align: center; padding: 0 1; }
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
        self.tui_session: Any = None  # Set by TUISession.start()
        # Terrarium tabs: ["root", "swe", "reviewer", "#tasks", "#review"]
        self._terrarium_tabs = terrarium_tabs
        self._input_queue: asyncio.Queue[str] = asyncio.Queue()
        self._stop_event = asyncio.Event()
        self._queued_widgets: list[QueuedMessage] = []
        self._is_processing = False
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
                yield Vertical(id="queued-area")
                yield ChatInput(id="input-box")
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

    def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        # Slash commands: don't show in chat — command system handles display
        if text.startswith("/"):
            self._input_queue.put_nowait(text)
            return
        if self._is_processing:
            # Agent is busy: show in queued area (above input, not in chat)
            qw = QueuedMessage(text)
            self._queued_widgets.append(qw)
            try:
                self.query_one("#queued-area", Vertical).mount(qw)
            except Exception:
                pass
        else:
            chat = self._get_active_chat()
            if chat:
                chat.mount(UserMessage(text))
                chat.scroll_end(animate=False)
        self._input_queue.put_nowait(text)

    def on_chat_input_command_hint(self, event: ChatInput.CommandHint) -> None:
        """Show command completion hints in the quick-status line."""
        try:
            status = self.query_one("#quick-status", Static)
            if event.hint:
                status.update(event.hint)
            elif not self._is_processing:
                status.update(IDLE_STATUS)
        except Exception:
            pass

    def on_chat_input_edit_queued(self, event: ChatInput.EditQueued) -> None:
        """Pull the last queued message back into the input box for editing."""
        if not self._queued_widgets:
            return
        qw = self._queued_widgets.pop()
        text = qw.message_text
        # Remove from chat and queue
        qw.remove()
        # Drain this message from the asyncio queue
        try:
            # Queue is FIFO; the message we want is the last one.
            # Rebuild queue without the last item.
            items = []
            while not self._input_queue.empty():
                items.append(self._input_queue.get_nowait())
            if items:
                items.pop()  # remove the last (most recent queued message)
            for item in items:
                self._input_queue.put_nowait(item)
        except Exception:
            pass
        # Put text back in input box
        try:
            inp = self.query_one("#input-box", ChatInput)
            inp.clear()
            inp.insert(text)
            inp.focus()
        except Exception:
            pass

    def on_load_older_button_clicked(self, event: LoadOlderButton.Clicked) -> None:
        """Handle 'Load older' button click."""
        if self.tui_session:
            target = self.get_active_tab_name() if self._terrarium_tabs else ""
            self.tui_session.load_older_batch(target)

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
        self._stop_event.set()
        self._input_queue.put_nowait("")  # empty string signals exit
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

    def __init__(
        self,
        agent_name: str = "agent",
        max_chat_widgets: int = DEFAULT_MAX_CHAT_WIDGETS,
        cull_keep: int = DEFAULT_CULL_KEEP,
        load_batch: int = DEFAULT_LOAD_BATCH,
    ):
        self.agent_name = agent_name
        self.running = False
        self._app: AgentTUI | None = None
        self._stop_event = asyncio.Event()
        self._streaming_widgets: dict[str, StreamingText] = {}  # target -> widget
        self._current_subagents: dict[str, SubAgentBlock] = {}  # target -> block
        # Terrarium mode
        self._terrarium_tabs: list[str] | None = None
        self._active_target: str = ""  # which tab output is currently targeting
        # Widget culling config
        self._max_chat_widgets = max_chat_widgets
        self._cull_keep = cull_keep
        self._load_batch = load_batch
        # "Load older" system: stores widgets that were culled or not mounted
        # on resume. Keyed by target. Each is a list of widgets (oldest first).
        self._older_widgets: dict[str, list] = {}  # target -> [widget, ...]
        self._culled_count: dict[str, int] = {}  # target -> count of culled widgets

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
                self._cull_chat_widgets(chat)
            except Exception:
                pass

        self._safe_call(_do)

    def _cull_chat_widgets(self, chat: VerticalScroll) -> None:
        """Remove old widgets when chat has too many, keeping recent ones."""
        children = list(chat.children)
        if len(children) <= self._max_chat_widgets:
            return

        remove_count = len(children) - self._cull_keep
        to_remove = children[:remove_count]

        target = self._active_target or "_default"
        self._culled_count[target] = self._culled_count.get(target, 0) + remove_count

        for w in to_remove:
            w.remove()

        # Update or add LoadOlderButton at top
        self._update_load_older_button(chat, target)

    def _update_load_older_button(self, chat: VerticalScroll, target: str) -> None:
        """Add/update the 'Load older' button at the top of chat."""
        # How many widgets can we load from the stored older_widgets?
        available = len(self._older_widgets.get(target, []))
        culled = self._culled_count.get(target, 0)
        total_hidden = available + culled

        if total_hidden <= 0:
            return

        # Remove existing button
        for child in list(chat.children):
            if isinstance(child, LoadOlderButton):
                child.remove()
                break

        # Only show button if there are stored widgets to load
        if available > 0:
            btn = LoadOlderButton(available)
            first = list(chat.children)
            if first:
                chat.mount(btn, before=first[0])
            else:
                chat.mount(btn)
        elif culled > 0:
            # Culled live messages (no stored data to reload)
            header = Static(
                f"[{culled} earlier messages not available]",
                classes="cull-header",
            )
            first = list(chat.children)
            if first:
                chat.mount(header, before=first[0])

    def store_older_widgets(self, target: str, widgets: list) -> None:
        """Store widgets for 'Load older' (from resume truncation)."""
        self._older_widgets[target] = widgets

    def load_older_batch(self, target: str = "") -> None:
        """Load a batch of older widgets into the chat."""
        target = target or self._active_target or "_default"
        stored = self._older_widgets.get(target, [])
        if not stored:
            return

        scroll_id = self._get_chat_scroll_id(target)
        batch_size = self._load_batch
        # Take from the end of stored (most recent of the older messages)
        batch = stored[-batch_size:]
        self._older_widgets[target] = (
            stored[:-batch_size] if batch_size < len(stored) else []
        )

        def _do():
            try:
                chat = self._app.query_one(f"#{scroll_id}", VerticalScroll)
                # Remove the LoadOlderButton
                for child in list(chat.children):
                    if isinstance(child, LoadOlderButton):
                        child.remove()
                        break
                # Prepend the batch
                first = list(chat.children)
                if first:
                    for w in reversed(batch):
                        chat.mount(w, before=first[0])
                else:
                    for w in batch:
                        chat.mount(w)
                # Add new button if more available
                self._update_load_older_button(chat, target)
            except Exception:
                pass

        self._safe_call(_do)

    # ── Chat area ───────────────────────────────────────────────

    def add_user_message(self, text: str, target: str = "") -> None:
        self._safe_mount(UserMessage(text), target=target)

    def add_system_notice(
        self, text: str, command: str = "", error: bool = False, target: str = ""
    ) -> None:
        """Add a non-collapsible system notice (for command results)."""
        self._safe_mount(
            SystemNotice(text, command=command, error=error), target=target
        )

    def add_trigger_message(
        self, label: str, content: str = "", target: str = ""
    ) -> None:
        self._safe_mount(TriggerMessage(label, content), target=target)

    def add_compact_summary(
        self, round_num: int, summary: str, target: str = ""
    ) -> None:
        """Add a compact summary accordion to the chat (shows immediately)."""
        block = CompactSummaryBlock(summary)
        self._last_compact_block = block
        self._safe_mount(block, target=target)

    def update_compact_summary(
        self, round_num: int, summary: str, target: str = ""
    ) -> None:
        """Update the current compact block with final summary (amber -> aquamarine)."""
        block = getattr(self, "_last_compact_block", None)
        if block:

            def _do():
                try:
                    block.mark_done(summary)
                except Exception:
                    pass

            self._safe_call(_do)
        else:
            self.add_compact_summary(round_num, summary, target=target)

    def update_token_usage(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total: int = 0,
        cached_tokens: int = 0,
    ) -> None:
        """Update session info with per-call token usage (accumulated)."""
        if not self._app or not self._app.is_running:
            return

        def _do():
            try:
                panel = self._app.query_one("#session-panel", SessionInfoPanel)
                panel.add_usage(prompt_tokens, completion_tokens, total, cached_tokens)
            except Exception:
                pass

        self._safe_call(_do)

    def restore_token_usage(
        self, total_in: int, total_out: int, last_prompt: int, total_cached: int = 0
    ) -> None:
        """Restore cumulative token totals from session history (on resume)."""
        if not self._app or not self._app.is_running:
            return

        def _do():
            try:
                panel = self._app.query_one("#session-panel", SessionInfoPanel)
                panel.restore_usage(total_in, total_out, last_prompt, total_cached)
            except Exception:
                pass

        self._safe_call(_do)

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
        scroll_id = self._get_chat_scroll_id(target)

        def _do():
            try:
                text = widget.get_text().strip()
                if not text:
                    return
                chat = self._app.query_one(f"#{scroll_id}", VerticalScroll)
                # Check if user is at bottom before replacing
                at_bottom = (
                    chat.max_scroll_y == 0 or chat.scroll_y >= chat.max_scroll_y - 2
                )
                # Replace StreamingText with Textual Markdown (selectable)
                md = Markdown(text)
                chat.mount(md, after=widget)
                widget.remove()
                # Keep scroll at bottom if user was there
                if at_bottom:
                    chat.scroll_end(animate=False)
                # Cull old widgets if too many
                self._cull_chat_widgets(chat)
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
        self, session_id: str = "", model: str = "", agent_name: str = ""
    ) -> None:
        # Buffer for deferred apply (session_info fires before TUI app mounts)
        self._pending_session_info = (session_id, model, agent_name)
        if not self._app or not self._app.is_running:
            return

        def _do():
            try:
                self._app.query_one("#session-panel", SessionInfoPanel).set_info(
                    session_id, model, agent_name
                )
            except Exception:
                pass

        self._safe_call(_do)

    def set_compact_threshold(self, threshold_tokens: int) -> None:
        # Buffer for deferred apply
        self._pending_compact_threshold = threshold_tokens
        if not self._app or not self._app.is_running:
            return

        def _do():
            try:
                panel = self._app.query_one("#session-panel", SessionInfoPanel)
                panel.set_compact_threshold(threshold_tokens)
            except Exception:
                pass

        self._safe_call(_do)

    def apply_pending_session_info(self) -> None:
        """Apply buffered session info after TUI app is ready."""
        info = getattr(self, "_pending_session_info", None)
        if info:
            self.update_session_info(*info)
        threshold = getattr(self, "_pending_compact_threshold", None)
        if threshold:
            self.set_compact_threshold(threshold)

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
            self._app._is_processing = True
            # Move queued messages from queue area into chat (promoted to UserMessage style)
            if self._app._queued_widgets:
                chat = self._app._get_active_chat()
                for qw in self._app._queued_widgets:
                    try:
                        # Remove from queue area, mount as UserMessage in chat
                        text = qw.message_text
                        qw.remove()
                        if chat:
                            chat.mount(UserMessage(text))
                    except Exception:
                        pass
                if chat:
                    chat.scroll_end(animate=False)
                self._app._queued_widgets.clear()
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
            self._app._is_processing = False
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
            # Apply any session info buffered before the app was ready
            self.apply_pending_session_info()
            return True
        except asyncio.TimeoutError:
            return False

    async def start(self, prompt: str = "You: ") -> None:
        self._app = AgentTUI(
            agent_name=self.agent_name,
            terrarium_tabs=self._terrarium_tabs,
        )
        self._app.tui_session = self
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
            self._app._input_queue.put_nowait("")  # unblock get_input

    async def get_input(self, prompt: str = "You: ") -> str:
        if not self._app:
            return ""
        return await self._app._input_queue.get()

    async def show_selection_modal(
        self, title: str, options: list[dict], current: str = ""
    ) -> str | None:
        """Show a selection modal and return chosen value or None.

        Safe to call from any async context. Uses ``call_later`` to
        delegate ``push_screen`` to the app's message loop where
        ``active_app`` ContextVar is set.
        """
        from kohakuterrarium.builtins.tui.widgets import SelectionModal

        if not self._app or not self._app.is_running:
            return None

        result_future: asyncio.Future[str | None] = asyncio.Future()
        modal = SelectionModal(title=title, options=options, current=current)

        def _on_dismiss(value: str | None) -> None:
            if not result_future.done():
                result_future.set_result(value)

        # call_later posts to the app's message queue — the callback
        # executes inside the app's _context() where active_app is set.
        self._app.call_later(lambda: self._app.push_screen(modal, callback=_on_dismiss))
        return await result_future

    async def show_confirm_modal(self, message: str) -> bool:
        """Show a confirm modal and return True/False."""
        from kohakuterrarium.builtins.tui.widgets import ConfirmModal

        if not self._app or not self._app.is_running:
            return False

        result_future: asyncio.Future[bool] = asyncio.Future()
        modal = ConfirmModal(message)

        def _on_dismiss(value: bool) -> None:
            if not result_future.done():
                result_future.set_result(value)

        self._app.call_later(lambda: self._app.push_screen(modal, callback=_on_dismiss))
        return await result_future

    def stop(self) -> None:
        self.running = False
        self._stop_event.set()
        if self._app:
            self._app._input_queue.put_nowait("")  # unblock get_input
            if self._app.is_running:
                self._app.exit()

    async def wait_for_stop(self) -> None:
        await self._stop_event.wait()
