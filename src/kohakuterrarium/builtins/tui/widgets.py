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
from textual.events import Key
from textual.message import Message

from textual.widgets import Collapsible, Static, TextArea

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
        color: #5A4FCF;
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
            try:
                self._output_widget.update(output[:3000])
            except Exception:
                # Escape markup-like content that Textual can't parse
                from textual.content import Content

                self._output_widget.update(Content(output[:3000]))
        self.remove_class("-running")
        self.add_class("-done")
        self.title = self._build_title()

    def mark_error(self, error: str = "") -> None:
        self.state = "error"
        self.result_summary = error[:80]
        if error:
            try:
                self._output_widget.update(error[:3000])
            except Exception:
                from textual.content import Content

                self._output_widget.update(Content(error[:3000]))
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
        color: #A57EAE;
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
        color: #5A4FCF;
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


class QueuedMessage(Static):
    """User message queued while agent is processing. Visually distinct (dashed border)."""

    DEFAULT_CSS = """
    QueuedMessage {
        height: auto;
        margin: 1 0 0 0;
        padding: 0 1;
        border: dashed #D4920A 50%;
        border-title-color: #D4920A;
        border-title-align: left;
        color: $text-muted;
    }
    """

    def __init__(self, text: str, **kwargs):
        super().__init__(text, **kwargs)
        self.border_title = "Queued"
        self.message_text = text

    def promote(self) -> None:
        """Convert to a normal UserMessage (when agent picks it up)."""
        self.border_title = "You"
        self.remove_class("-queued")
        self.styles.border = ("round", "#5A4FCF")
        self.styles.border_title_color = "#5A4FCF"
        self.styles.color = None


class SystemNotice(Static):
    """Non-collapsible system notice for command results.

    Visually distinct from chat messages — dimmed, centered text,
    clearly not part of the LLM conversation context.
    """

    DEFAULT_CSS = """
    SystemNotice {
        height: auto;
        margin: 0;
        padding: 0 2;
        color: $text-muted;
        text-align: center;
        text-style: italic;
    }
    SystemNotice.--error {
        color: #E74C3C;
    }
    """

    def __init__(self, text: str, error: bool = False, **kwargs):
        super().__init__(f"— {text} —", **kwargs)
        if error:
            self.add_class("--error")


class TriggerMessage(Collapsible):
    """Channel/trigger message as a collapsible accordion.

    Title shows the label (channel + sender), body shows the full content.
    Amber color scheme to match trigger theme.
    """

    DEFAULT_CSS = """
    TriggerMessage {
        height: auto;
        margin: 1 0 0 0;
        padding: 0;
    }
    TriggerMessage > Contents {
        height: auto;
        max-height: 12;
        overflow-y: auto;
        padding: 0 1;
    }
    TriggerMessage > CollapsibleTitle {
        color: #D4920A;
        background: transparent;
    }
    TriggerMessage > CollapsibleTitle:hover {
        background: #D4920A 15%;
    }
    TriggerMessage > CollapsibleTitle:focus {
        background: #D4920A 15%;
    }
    .trigger-body {
        height: auto;
        color: $text-muted;
    }
    """

    BUTTON_OPEN = "[-]"
    BUTTON_CLOSED = "[+]"

    def __init__(self, label: str, content: str = "", **kwargs):
        preview = content[:80].replace("\n", " ") if content else ""
        title = f"\u25cf {label}"
        if preview:
            title += f"  {preview}"
        self._body = Static(content, classes="trigger-body")
        super().__init__(
            self._body,
            title=title,
            collapsed=bool(content),
            **kwargs,
        )


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
        self._input_tokens = 0
        self._output_tokens = 0
        self._cached_tokens = 0
        self._last_prompt_tokens = 0
        self._compact_threshold = 0
        self._model = ""
        self._session_id = ""
        self._agent_name = ""

    def set_info(
        self, session_id: str = "", model: str = "", agent_name: str = ""
    ) -> None:
        self._session_id = session_id
        self._model = model
        self._agent_name = agent_name
        self._refresh()

    def add_usage(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total: int = 0,
        cached_tokens: int = 0,
    ) -> None:
        self._input_tokens += prompt_tokens
        self._output_tokens += completion_tokens
        self._cached_tokens += cached_tokens
        self._last_prompt_tokens = prompt_tokens
        self._refresh()

    def restore_usage(
        self, total_in: int, total_out: int, last_prompt: int, total_cached: int = 0
    ) -> None:
        """Set cumulative totals from session history (on resume)."""
        self._input_tokens = total_in
        self._output_tokens = total_out
        self._cached_tokens = total_cached
        self._last_prompt_tokens = last_prompt
        self._refresh()

    def add_tokens(self, count: int) -> None:
        """Backward compat: treat as total input tokens."""
        self._input_tokens += count
        self._refresh()

    def set_compact_threshold(self, threshold_tokens: int) -> None:
        self._compact_threshold = threshold_tokens
        self._refresh()

    def _refresh(self) -> None:
        elapsed = time.monotonic() - self._start_time
        mins, secs = int(elapsed // 60), int(elapsed % 60)
        lines = []
        if self._agent_name:
            lines.append(f"Agent: {self._agent_name}")
        if self._session_id:
            lines.append(f"ID: {self._session_id[:20]}")
        if self._model:
            lines.append(f"Model: {self._model}")
        lines.append(f"Runtime: {mins}m {secs}s")
        total = self._input_tokens + self._output_tokens
        if total > 0:
            in_part = f"In: {_fmt_tokens(self._input_tokens)}"
            if self._cached_tokens > 0:
                in_part += f" (cache {_fmt_tokens(self._cached_tokens)})"
            lines.append(f"{in_part}  Out: {_fmt_tokens(self._output_tokens)}")
        if self._compact_threshold > 0:
            if self._last_prompt_tokens > 0:
                pct = int(self._last_prompt_tokens / self._compact_threshold * 100)
                lines.append(
                    f"Context: {_fmt_tokens(self._last_prompt_tokens)}"
                    f"/{_fmt_tokens(self._compact_threshold)} ({pct}%)"
                )
            else:
                lines.append(f"Compact: {_fmt_tokens(self._compact_threshold)}")
        self.update("\n".join(lines))


# ── Helpers ─────────────────────────────────────────────────────


class CompactSummaryBlock(Collapsible):
    """Compact summary displayed as a collapsible accordion.

    Amber while compacting, aquamarine when done.
    """

    DEFAULT_CSS = """
    CompactSummaryBlock {
        height: auto;
        margin: 1 0;
        padding: 0;
    }
    CompactSummaryBlock > Contents {
        height: auto;
        max-height: 12;
        overflow-y: auto;
        padding: 0 1;
    }
    CompactSummaryBlock > CollapsibleTitle {
        background: transparent;
    }
    CompactSummaryBlock > CollapsibleTitle:hover {
        background: #0F52BA 15%;
    }
    CompactSummaryBlock > CollapsibleTitle:focus {
        background: #0F52BA 15%;
    }
    CompactSummaryBlock.-running > CollapsibleTitle {
        color: #D4920A;
    }
    CompactSummaryBlock.-done > CollapsibleTitle {
        color: #0F52BA;
    }
    .compact-body {
        height: auto;
        color: $text-muted;
    }
    """

    BUTTON_OPEN = "[-]"
    BUTTON_CLOSED = "[+]"

    def __init__(self, summary: str, done: bool = False, **kwargs):
        self._body = Static(summary, classes="compact-body")
        if done:
            title = "\u25cf Context auto-compact"
        else:
            title = "\u25cb Context auto-compact"
        super().__init__(self._body, title=title, collapsed=True, **kwargs)
        self.add_class("-done" if done else "-running")

    def mark_done(self, summary: str) -> None:
        """Transition from running (amber) to done (sapphire)."""
        self._body.update(summary)
        self.title = "\u25cf Context auto-compact"
        self.remove_class("-running")
        self.add_class("-done")


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


# ── Load Older Button ──────────────────────────────────────────


class LoadOlderButton(Static):
    """Clickable button to load earlier messages that were culled."""

    DEFAULT_CSS = """
    LoadOlderButton {
        height: 1;
        text-align: center;
        color: #0F52BA;
        padding: 0 1;
    }
    LoadOlderButton:hover {
        background: #0F52BA 15%;
        text-style: underline;
    }
    """

    def __init__(self, hidden_count: int, **kwargs):
        super().__init__(
            f"\u25b2 Load {min(hidden_count, 30)} older messages ({hidden_count} hidden)",
            **kwargs,
        )
        self.hidden_count = hidden_count

    class Clicked(Message):
        pass

    def on_click(self) -> None:
        self.post_message(self.Clicked())


# ── Chat Input ─────────────────────────────────────────────────


class ChatInput(TextArea):
    """Multi-line input. Enter sends, Shift+Enter or Ctrl+J inserts newline.

    Ctrl+J works universally (including SSH) since it is the literal
    newline character and does not depend on terminal modifier support.
    """

    DEFAULT_CSS = """
    ChatInput {
        height: auto;
        min-height: 3;
        max-height: 8;
        border: solid #5A4FCF 30%;
    }
    ChatInput:focus {
        border: solid #5A4FCF;
    }
    """

    class Submitted(Message):
        """Posted when the user presses Enter to send."""

        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    class EditQueued(Message):
        """Posted when user presses Up on empty input to edit last queued message."""

        pass

    def _on_key(self, event: Key) -> None:
        # Shift+Enter, Ctrl+Enter, Ctrl+J: insert newline
        if event.key in ("shift+enter", "ctrl+enter", "ctrl+j"):
            event.prevent_default()
            event.stop()
            self.insert("\n")
            return
        # Plain Enter: send message
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            text = self.text.strip()
            if text:
                self.post_message(self.Submitted(text))
                self.clear()
            return
        # Up arrow on empty input: edit last queued message
        if event.key == "up" and not self.text.strip():
            event.prevent_default()
            event.stop()
            self.post_message(self.EditQueued())
            return
        super()._on_key(event)


# ── Helpers ─────────────────────────────────────────────────────


def _fmt_tokens(n: int) -> str:
    """Format token count as human-readable string."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _summarize_output(output: str) -> str:
    if not output:
        return ""
    lines = output.strip().split("\n")
    if len(lines) <= 1 and len(output) <= 60:
        return output.strip()
    return f"{len(lines)} lines"
