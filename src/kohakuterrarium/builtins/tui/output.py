"""TUI output module - writes to Textual app with visual turn separation."""

import re
from typing import Any

from rich.panel import Panel
from rich.text import Text

from kohakuterrarium.builtins.tui.session import TUISession
from kohakuterrarium.core.session import get_session
from kohakuterrarium.modules.output.base import BaseOutputModule
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class TUIOutput(BaseOutputModule):
    """
    Output module using Textual full-screen TUI.

    Each assistant turn is visually separated:
    - begin_assistant_turn() adds a header
    - streaming output appears incrementally
    - end_assistant_turn() adds a separator

    Config:
        output:
          type: tui
          session_key: my_agent  # optional
    """

    def __init__(self, session_key: str | None = None, **options: Any):
        super().__init__()
        self._session_key = session_key
        self._tui: TUISession | None = None
        self._stream_buffer: str = ""
        self._turn_started: bool = False

    async def _on_start(self) -> None:
        """Attach to shared TUI session."""
        session = get_session(self._session_key)
        if session.tui is None:
            session.tui = TUISession(
                agent_name=session.key if session.key != "__default__" else "agent",
            )
        self._tui = session.tui
        logger.debug("TUI output started", session_key=self._session_key)

    async def _on_stop(self) -> None:
        """Flush and cleanup."""
        await self.flush()
        logger.debug("TUI output stopped")

    def _ensure_turn_started(self) -> None:
        """Start a new assistant turn block if not already started."""
        if not self._turn_started and self._tui:
            self._tui.begin_assistant_turn()
            self._turn_started = True

    async def on_processing_start(self) -> None:
        """Show animated processing indicator when agent starts thinking."""
        if self._tui:
            self._tui.start_thinking()

    async def on_processing_end(self) -> None:
        """Stop animated processing indicator, show idle status."""
        if self._tui:
            self._tui.stop_thinking()
            self._tui.set_idle()

    async def write(self, content: str) -> None:
        """Write complete content to the output pane."""
        if self._tui and content:
            self._ensure_turn_started()
            self._tui.write_output(content)

    async def write_stream(self, chunk: str) -> None:
        """
        Buffer streaming chunks and flush on newlines.

        Each complete line is written to the output pane.
        """
        if not self._tui or not chunk:
            return

        self._ensure_turn_started()
        self._stream_buffer += chunk

        while "\n" in self._stream_buffer:
            line, self._stream_buffer = self._stream_buffer.split("\n", 1)
            if line:
                self._tui.write_output(line)

    async def flush(self) -> None:
        """Flush remaining buffered stream content."""
        if self._tui and self._stream_buffer:
            self._tui.write_output(self._stream_buffer)
            self._stream_buffer = ""

    def reset(self) -> None:
        """Reset between turns - end the current assistant block."""
        if self._turn_started and self._tui:
            self._tui.end_assistant_turn()
            self._turn_started = False
        self._stream_buffer = ""

    def on_activity(self, activity_type: str, detail: str) -> None:
        """Show tool/subagent activity inline in main output and in Status tab."""
        if not self._tui:
            return

        # Always log to Status tab for detailed history
        self._tui.update_status(f"[{activity_type}] {detail}")

        # Build inline Rich Text for main output
        inline = self._format_activity_inline(activity_type, detail)
        if inline:
            self._ensure_turn_started()
            self._tui.write_to_output(inline)

    async def on_resume(self, events: list[dict]) -> None:
        """Render session history in the TUI output pane."""
        if not self._tui or not events:
            return

        # Wait for Textual app to be mounted (writes are dropped before mount)
        await self._tui.wait_ready()

        # Group events into processing cycles
        cycles: list[dict] = []
        current: dict | None = None

        for evt in events:
            etype = evt.get("type", "")

            if etype in ("user_input", "trigger_fired"):
                if current:
                    cycles.append(current)
                if etype == "user_input":
                    label = evt.get("content", "")
                else:
                    ch = evt.get("channel", "")
                    sender = evt.get("sender", "")
                    label = f"[{ch}] from {sender}: {evt.get('content', '')}"
                current = {
                    "input_type": etype,
                    "input": label,
                    "text_parts": [],
                    "activities": [],
                }
            elif current is not None:
                if etype == "text":
                    current["text_parts"].append(evt.get("content", ""))
                elif etype == "tool_call":
                    name = evt.get("name", "tool")
                    current["activities"].append(("tool_start", name))
                elif etype == "tool_result":
                    name = evt.get("name", "tool")
                    error = evt.get("error")
                    if error:
                        current["activities"].append(("tool_error", name))
                    else:
                        current["activities"].append(("tool_done", name))
                elif etype == "subagent_call":
                    name = evt.get("name", "subagent")
                    current["activities"].append(("subagent_start", name))
                elif etype == "subagent_result":
                    name = evt.get("name", "subagent")
                    current["activities"].append(("subagent_done", name))

        if current:
            cycles.append(current)

        if not cycles:
            return

        # Write a "resumed" header
        header = Text()
        header.append(f"  Resumed session ({len(cycles)} turns)  ", style="bold dim")
        self._tui.write_to_output(header)
        self._tui.write_to_output("")

        # Render each cycle
        for cycle in cycles:
            # User input panel (same style as TUI's on_input_submitted)
            if cycle["input_type"] == "user_input":
                self._tui.write_to_output(
                    Panel(
                        cycle["input"],
                        title="You",
                        title_align="left",
                        border_style="cyan",
                    )
                )
            else:
                self._tui.write_to_output(
                    Panel(
                        cycle["input"],
                        title="Trigger",
                        title_align="left",
                        border_style="yellow",
                    )
                )

            # Assistant turn: activities + text
            self._tui.begin_assistant_turn()

            for activity_type, name in cycle["activities"]:
                inline = self._format_activity_inline(activity_type, f"[{name}]")
                if inline:
                    self._tui.write_to_output(inline)

            full_text = "".join(cycle["text_parts"]).strip()
            if full_text:
                self._tui.write_output(full_text)

            self._tui.end_assistant_turn()

        # Final separator
        sep = Text()
        sep.append("  End of history  ", style="bold dim")
        self._tui.write_to_output(sep)
        self._tui.write_to_output("")

    @staticmethod
    def _parse_detail_bracket(detail: str) -> tuple[str, str]:
        """
        Extract name and remainder from '[name] rest' format.

        Returns:
            (name, rest) or ("", detail) if no bracket found.
        """
        m = re.match(r"^\[([^\]]+)\]\s*(.*)", detail)
        if m:
            return m.group(1), m.group(2)
        return "", detail

    @staticmethod
    def _format_activity_inline(activity_type: str, detail: str) -> Text | None:
        """
        Build a Rich Text line for inline display in the main output.

        Returns None for activity types that shouldn't be shown inline.
        """
        name, rest = TUIOutput._parse_detail_bracket(detail)

        match activity_type:
            case "tool_start":
                text = Text()
                text.append("  \u2699 ", style="dim")
                text.append(name or "tool", style="bold cyan")
                if rest:
                    text.append(f": {rest}", style="dim")
                return text

            case "tool_done":
                text = Text()
                text.append("  \u2713 ", style="green")
                text.append(name or "tool", style="bold cyan")
                if rest:
                    text.append(f": {rest}", style="green")
                return text

            case "tool_error":
                text = Text()
                text.append("  \u2717 ", style="red")
                text.append(name or "tool", style="bold red")
                if rest:
                    text.append(f": {rest}", style="red")
                return text

            case "subagent_start":
                text = Text()
                text.append("  \u2699 ", style="dim")
                text.append("[sub] ", style="dim italic")
                text.append(name or "subagent", style="bold magenta")
                if rest:
                    text.append(f": {rest}", style="dim")
                return text

            case "subagent_done":
                text = Text()
                text.append("  \u2713 ", style="green")
                text.append("[sub] ", style="dim italic")
                text.append(name or "subagent", style="bold magenta")
                if rest:
                    text.append(f": {rest}", style="green")
                return text

            case "subagent_error":
                text = Text()
                text.append("  \u2717 ", style="red")
                text.append("[sub] ", style="dim italic")
                text.append(name or "subagent", style="bold red")
                if rest:
                    text.append(f": {rest}", style="red")
                return text

            case _:
                # command_done, command_error, etc. - status tab only
                return None
