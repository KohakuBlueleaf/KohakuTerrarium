"""
Custom Textual widgets for the KohakuTerrarium TUI.

Gemstone color palette:
  iolite:     #5A4FCF  (primary, tools)
  taaffeite:  #A57EAE  (sub-agents)
  aquamarine: #4C9989  (success, done)
  amber:      #D4920A  (running, warning)
  sapphire:   #0F52BA  (info)
  coral:      #E74C3C  (error)
"""

import time

from textual.containers import Vertical

from textual.widgets import Collapsible, Static


# ── Tool Call Block ─────────────────────────────────────────────


class ToolBlock(Collapsible):
    """A single tool call displayed as a collapsible accordion.

    Collapsed title shows: icon + name + args + (summary)
    Expanded body shows: full tool output sent to LLM
    """

    DEFAULT_CSS = """
    ToolBlock {
        height: auto;
        margin: 0;
        padding: 0;
    }
    ToolBlock > Contents {
        height: auto;
        max-height: 8;
        overflow-y: auto;
        padding: 0 1;
    }
    ToolBlock > CollapsibleTitle {
        background: transparent;
    }
    ToolBlock > CollapsibleTitle:hover {
        background: #5A4FCF 15%;
    }
    ToolBlock > CollapsibleTitle:focus {
        background: #5A4FCF 15%;
    }
    ToolBlock.-running > CollapsibleTitle {
        color: #D4920A;
    }
    ToolBlock.-done > CollapsibleTitle {
        color: #4C9989;
    }
    ToolBlock.-error > CollapsibleTitle {
        color: #E74C3C;
    }
    .tool-output {
        height: auto;
        color: $text-muted;
    }
    """

    BUTTON_OPEN = "[-]"
    BUTTON_CLOSED = "[+]"

    def __init__(
        self,
        tool_name: str,
        args_preview: str = "",
        tool_id: str = "",
        **kwargs,
    ):
        self.tool_name = tool_name
        self.tool_id = tool_id
        self.args_preview = args_preview
        self.state = "running"
        self.result_summary = ""
        self.start_time = time.monotonic()
        self._output_widget = Static("", classes="tool-output")
        title = self._build_title()
        super().__init__(self._output_widget, title=title, collapsed=True, **kwargs)
        self.add_class("-running")

    def _build_title(self) -> str:
        if self.state == "running":
            elapsed = time.monotonic() - self.start_time
            parts = [f"\u25cb {self.tool_name}"]
            if self.args_preview:
                parts.append(f"  {self.args_preview[:50]}")
            if elapsed >= 0.5:
                parts.append(f"  ({elapsed:.1f}s)")
            return "".join(parts)
        elif self.state == "done":
            parts = [f"\u25cf {self.tool_name}"]
            if self.args_preview:
                parts.append(f"  {self.args_preview[:50]}")
            if self.result_summary:
                parts.append(f"  ({self.result_summary})")
            return "".join(parts)
        elif self.state == "error":
            parts = [f"\u2717 {self.tool_name}"]
            if self.result_summary:
                parts.append(f"  {self.result_summary[:60]}")
            return "".join(parts)
        return f"? {self.tool_name}"

    def mark_done(self, output: str = "", summary: str = "") -> None:
        self.state = "done"
        self.result_summary = summary or _summarize_output(output)
        if output:
            self._output_widget.update(output[:3000])
        self.remove_class("-running")
        self.add_class("-done")
        self.title = self._build_title()

    def mark_error(self, error: str = "") -> None:
        self.state = "error"
        self.result_summary = error[:80]
        if error:
            self._output_widget.update(error[:3000])
        self.remove_class("-running")
        self.add_class("-error")
        self.title = self._build_title()


class SubAgentBlock(Collapsible):
    """A sub-agent collapsible. Nested tools are plain text lines, not accordions."""

    DEFAULT_CSS = """
    SubAgentBlock {
        height: auto;
        margin: 0;
        padding: 0;
        background: $boost;
    }
    SubAgentBlock > Contents {
        height: auto;
        max-height: 10;
        overflow-y: auto;
        padding: 0 0 0 2;
    }
    SubAgentBlock > CollapsibleTitle {
        background: transparent;
    }
    SubAgentBlock > CollapsibleTitle:hover {
        background: #A57EAE 15%;
    }
    SubAgentBlock > CollapsibleTitle:focus {
        background: #A57EAE 15%;
    }
    SubAgentBlock.-running > CollapsibleTitle {
        color: #A57EAE;
    }
    SubAgentBlock.-done > CollapsibleTitle {
        color: #4C9989;
    }
    SubAgentBlock.-error > CollapsibleTitle {
        color: #E74C3C;
    }
    SubAgentBlock.-interrupted > CollapsibleTitle {
        color: #D4920A;
    }
    .sa-tools {
        height: auto;
    }
    .sa-tool-line {
        height: 1;
        margin: 0 0 0 2;
        color: #0F52BA;
    }
    .sa-tool-line.-done {
        color: #4C9989;
    }
    .sa-tool-line.-error {
        color: #E74C3C;
    }
    .sa-result {
        height: auto;
        max-height: 6;
        overflow-y: auto;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BUTTON_OPEN = "[-]"
    BUTTON_CLOSED = "[+]"

    def __init__(
        self,
        agent_name: str,
        sa_task: str = "",
        agent_id: str = "",
        **kwargs,
    ):
        self.agent_name = agent_name
        self.sa_task = sa_task
        self.agent_id = agent_id
        self.state = "running"
        self.result_summary = ""
        self.start_time = time.monotonic()
        self._tools_container = Vertical(classes="sa-tools")
        self._result_widget = Static("", classes="sa-result")
        # Track tool lines by unique key for updating
        self._tool_lines: dict[str, Static] = {}
        self._tool_counter: int = 0
        # Map: tool_name -> list of keys (for matching done events by name)
        self._tool_name_keys: dict[str, list[str]] = {}
        super().__init__(
            self._tools_container,
            self._result_widget,
            title=self._build_title(),
            collapsed=False,
            **kwargs,
        )
        self.add_class("-running")

    def _build_title(self) -> str:
        if self.state == "running":
            elapsed = time.monotonic() - self.start_time
            parts = [f"\u25cb {self.agent_name}"]
            if self.sa_task:
                parts.append(f"  {self.sa_task[:40]}")
            if elapsed >= 0.5:
                parts.append(f"  ({elapsed:.1f}s)")
            return "".join(parts)
        elif self.state == "done":
            parts = [f"\u25cf {self.agent_name}"]
            if self.result_summary:
                parts.append(f"  ({self.result_summary})")
            return "".join(parts)
        elif self.state == "interrupted":
            return f"\u25cb {self.agent_name}  (interrupted)"
        else:
            parts = [f"\u2717 {self.agent_name}"]
            if self.result_summary:
                parts.append(f"  {self.result_summary[:50]}")
            return "".join(parts)

    def add_tool_line(self, tool_name: str, args_preview: str = "") -> str:
        """Add a single-line tool entry. Returns unique key for update."""
        key = f"{tool_name}_{self._tool_counter}"
        self._tool_counter += 1
        text = f"\u25cb {tool_name}"
        if args_preview:
            text += f"  {args_preview[:50]}"
        line = Static(text, classes="sa-tool-line")
        line._raw_text = text
        self._tool_lines[key] = line
        self._tool_name_keys.setdefault(tool_name, []).append(key)
        try:
            self._tools_container.mount(line)
        except Exception:
            if not hasattr(self, "_pending_tool_lines"):
                self._pending_tool_lines = []
            self._pending_tool_lines.append(line)
        return key

    def on_mount(self) -> None:
        """Mount pending tool lines and apply deferred CSS classes."""
        if hasattr(self, "_pending_tool_lines"):
            for line in self._pending_tool_lines:
                self._tools_container.mount(line)
                # Apply CSS class that was set before mount
                if hasattr(line, "_deferred_class"):
                    line.add_class(line._deferred_class)
            del self._pending_tool_lines

    def update_tool_line(
        self, tool_name: str, done: bool = True, error: bool = False
    ) -> None:
        """Update the first unfinished tool line matching tool_name."""
        # Find first key for this tool_name that's still running (○)
        keys = self._tool_name_keys.get(tool_name, [])
        line = None
        for key in keys:
            candidate = self._tool_lines.get(key)
            if candidate and getattr(candidate, "_raw_text", "").startswith("\u25cb "):
                line = candidate
                break
        if not line:
            return
        old_text = getattr(line, "_raw_text", "")
        new_text = old_text.replace("\u25cb ", "\u25cf " if done else "\u2717 ", 1)
        line._raw_text = new_text
        line.update(new_text)
        # Store desired class for deferred application after mount
        cls = "-error" if error else "-done"
        line._deferred_class = cls
        # Try to apply now (works if already mounted, harmless if not)
        line.add_class(cls)

    def mark_done(
        self,
        output: str = "",
        tools_used: list[str] | None = None,
        turns: int = 0,
        duration: float = 0,
    ) -> None:
        self.state = "done"
        parts = []
        if tools_used:
            parts.append(", ".join(tools_used))
        if turns:
            parts.append(f"{turns} turns")
        if duration >= 0.1:
            parts.append(f"{duration:.1f}s")
        self.result_summary = "; ".join(parts) if parts else ""
        if output:
            self._result_widget.update(output[:2000])
        self.remove_class("-running")
        self.add_class("-done")
        self.title = self._build_title()

    def mark_error(self, error: str = "") -> None:
        self.state = "error"
        self.result_summary = error[:60]
        self.remove_class("-running")
        self.add_class("-error")
        self.title = self._build_title()

    def mark_interrupted(self) -> None:
        self.state = "interrupted"
        self.remove_class("-running")
        self.add_class("-interrupted")
        self.title = self._build_title()


# ── Message Widgets ─────────────────────────────────────────────


class UserMessage(Static):
    DEFAULT_CSS = """
    UserMessage {
        height: auto;
        margin: 1 0 0 0;
        padding: 0 1;
        border: round #5A4FCF;
        border-title-color: #5A4FCF;
        border-title-align: left;
    }
    """

    def __init__(self, text: str, **kwargs):
        super().__init__(text, **kwargs)
        self.border_title = "You"


class TriggerMessage(Static):
    DEFAULT_CSS = """
    TriggerMessage {
        height: auto;
        margin: 1 0 0 0;
        padding: 0 1;
        border: round #D4920A;
        border-title-color: #D4920A;
        border-title-align: left;
    }
    """

    def __init__(self, label: str, content: str = "", **kwargs):
        display = f"{label}\n{content}" if content else label
        super().__init__(display, **kwargs)
        self.border_title = "Trigger"


class StreamingText(Static):
    DEFAULT_CSS = """
    StreamingText {
        height: auto;
        margin: 0;
        padding: 0;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._chunks: list[str] = []

    def append(self, chunk: str) -> None:
        self._chunks.append(chunk)
        self.update("".join(self._chunks))

    def get_text(self) -> str:
        return "".join(self._chunks)


# ── Status Panels ───────────────────────────────────────────────


class RunningPanel(Static):
    """Live list of running tools/sub-agents. Timer refreshes every second."""

    DEFAULT_CSS = """
    RunningPanel {
        height: auto;
        max-height: 12;
        padding: 0 1;
        border: round #D4920A;
        border-title-color: #D4920A;
        border-title-align: left;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("(idle)", **kwargs)
        self.border_title = "Running"
        self._items: dict[str, tuple[str, float]] = {}

    def on_mount(self) -> None:
        self.set_interval(1.0, self._tick)

    def _tick(self) -> None:
        if self._items:
            self._refresh_display()

    def add_item(self, item_id: str, label: str) -> None:
        self._items[item_id] = (label, time.monotonic())
        self._refresh_display()

    def remove_item(self, item_id: str) -> None:
        self._items.pop(item_id, None)
        self._refresh_display()

    def clear(self) -> None:
        self._items.clear()
        self._refresh_display()

    def _refresh_display(self) -> None:
        if not self._items:
            self.update("(idle)")
            return
        lines = []
        for _, (label, start) in self._items.items():
            elapsed = time.monotonic() - start
            lines.append(f"\u25cb {label}  ({elapsed:.0f}s)")
        self.update("\n".join(lines))


class ScratchpadPanel(Static):
    DEFAULT_CSS = """
    ScratchpadPanel {
        height: auto;
        max-height: 10;
        padding: 0 1;
        border: round #0F52BA;
        border-title-color: #0F52BA;
        border-title-align: left;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("(empty)", **kwargs)
        self.border_title = "Scratchpad"

    def update_data(self, data: dict) -> None:
        if not data:
            self.update("(empty)")
            return
        lines = [f"{k}: {str(v)[:60]}" for k, v in data.items()]
        self.update("\n".join(lines))


class SessionInfoPanel(Static):
    DEFAULT_CSS = """
    SessionInfoPanel {
        height: auto;
        max-height: 8;
        padding: 0 1;
        border: round #4C9989;
        border-title-color: #4C9989;
        border-title-align: left;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self.border_title = "Session"
        self._start_time = time.monotonic()
        self._tokens = 0
        self._model = ""
        self._session_id = ""

    def set_info(self, session_id: str = "", model: str = "", tokens: int = 0) -> None:
        self._session_id = session_id
        self._model = model
        self._tokens = tokens
        self._refresh()

    def add_tokens(self, count: int) -> None:
        self._tokens += count
        self._refresh()

    def _refresh(self) -> None:
        elapsed = time.monotonic() - self._start_time
        mins, secs = int(elapsed // 60), int(elapsed % 60)
        lines = []
        if self._session_id:
            lines.append(f"ID: {self._session_id[:20]}")
        if self._model:
            lines.append(f"Model: {self._model}")
        lines.append(f"Runtime: {mins}m {secs}s")
        if self._tokens >= 1000:
            lines.append(f"Tokens: {self._tokens / 1000:.1f}k")
        elif self._tokens > 0:
            lines.append(f"Tokens: {self._tokens}")
        self.update("\n".join(lines))


# ── Helpers ─────────────────────────────────────────────────────


class TerrariumPanel(Static):
    """Creature and channel overview for terrarium mode."""

    DEFAULT_CSS = """
    TerrariumPanel {
        height: auto;
        max-height: 16;
        padding: 0 1;
        border: round #A57EAE;
        border-title-color: #A57EAE;
        border-title-align: left;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self.border_title = "Terrarium"
        self._creatures: list[dict] = []
        self._channels: list[dict] = []

    def set_topology(self, creatures: list[dict], channels: list[dict]) -> None:
        """Update creature/channel display.

        creatures: [{"name": "swe", "running": True, "listen": [...], "send": [...]}]
        channels: [{"name": "tasks", "type": "queue", "description": "..."}]
        """
        self._creatures = creatures
        self._channels = channels
        self._refresh()

    def _refresh(self) -> None:
        lines = []
        if self._creatures:
            lines.append("Creatures:")
            for c in self._creatures:
                icon = "\u25cf" if c.get("running") else "\u25cb"
                listen = ", ".join(c.get("listen", []))
                send = ", ".join(c.get("send", []))
                lines.append(f"  {icon} {c['name']}")
                if listen:
                    lines.append(f"    listen: {listen}")
                if send:
                    lines.append(f"    send: {send}")
        if self._channels:
            if lines:
                lines.append("")
            lines.append("Channels:")
            for ch in self._channels:
                ctype = ch.get("type", "queue")
                lines.append(f"  {ch['name']}  ({ctype})")
        self.update("\n".join(lines) if lines else "(no topology)")


# ── Helpers ─────────────────────────────────────────────────────


def _summarize_output(output: str) -> str:
    if not output:
        return ""
    lines = output.strip().split("\n")
    if len(lines) <= 1 and len(output) <= 60:
        return output.strip()
    return f"{len(lines)} lines"
