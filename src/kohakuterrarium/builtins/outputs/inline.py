"""
Inline output module. Claude Code-style terminal output.

Design principles:
- Text streams live (character by character, no buffering)
- Each tool call is ONE visual line that transitions states
- Sub-agents render as indented nested blocks
- Blank line separates user input from assistant output
- Works over SSH/tmux/any terminal (no alternate screen buffer)
"""

import sys
import time

from rich.console import Console
from rich.markdown import Markdown as RichMarkdown
from rich.panel import Panel
from rich.text import Text

from kohakuterrarium.modules.output.base import BaseOutputModule
from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class InlineOutput(BaseOutputModule):
    """Inline terminal output using Rich. No alternate screen buffer.

    Config:
        output:
          type: inline
    """

    def __init__(self, **options):
        super().__init__()
        self._console = Console(highlight=False)
        self._in_turn = False
        self._has_text = False
        # Tool call tracking for in-place replacement
        self._pending_tool: dict | None = None  # {name, args_preview, start_time}
        self._can_replace = False  # True if nothing printed since tool_start
        # Sub-agent nesting
        self._in_subagent = False
        self._subagent_name = ""

    async def _on_start(self) -> None:
        logger.debug("Inline output started")

    async def _on_stop(self) -> None:
        if self._in_turn:
            self._end_turn()
        logger.debug("Inline output stopped")

    # ── User input ──────────────────────────────────────────────

    async def on_user_input(self, text: str) -> None:
        """Render user input as a panel (overwrites the raw prompt line)."""
        if not text:
            return
        # Move cursor up to overwrite the prompt line that prompt_toolkit wrote
        sys.stdout.write("\033[A\033[2K")
        sys.stdout.flush()
        self._console.print(
            Panel(
                text,
                title="[bold cyan]You[/]",
                title_align="left",
                border_style="cyan",
                padding=(0, 1),
            )
        )
        self._console.print()  # blank line after input

    # ── Processing lifecycle ────────────────────────────────────

    async def on_processing_start(self) -> None:
        self._has_text = False
        self._pending_tool = None
        self._can_replace = False

    async def on_processing_end(self) -> None:
        if self._in_turn:
            self._end_turn()

    # ── Text streaming (live, no buffering) ─────────────────────

    async def write(self, content: str) -> None:
        if not content:
            return
        self._ensure_turn()
        self._can_replace = False
        sys.stdout.write(content)
        sys.stdout.flush()
        self._has_text = True

    async def write_stream(self, chunk: str) -> None:
        if not chunk:
            return
        self._ensure_turn()
        self._can_replace = False
        sys.stdout.write(chunk)
        sys.stdout.flush()
        self._has_text = True

    async def flush(self) -> None:
        sys.stdout.flush()

    def reset(self) -> None:
        pass

    def _ensure_turn(self) -> None:
        if not self._in_turn:
            self._in_turn = True

    def _end_turn(self) -> None:
        # End any trailing text with newline
        if self._has_text:
            sys.stdout.write("\n")
        self._console.print()  # blank separator between turns
        sys.stdout.flush()
        self._in_turn = False
        self._has_text = False
        self._pending_tool = None
        self._in_subagent = False

    # ── Activity rendering ──────────────────────────────────────

    def on_activity(self, activity_type: str, detail: str) -> None:
        name, rest = _parse_detail(detail)
        self._handle_activity(activity_type, name, rest, {})

    def on_activity_with_metadata(
        self, activity_type: str, detail: str, metadata: dict
    ) -> None:
        name, rest = _parse_detail(detail)
        self._handle_activity(activity_type, name, rest, metadata)

    def _handle_activity(
        self, activity_type: str, name: str, rest: str, metadata: dict
    ) -> None:
        self._ensure_turn()

        # Newline after streaming text before tool lines
        if self._has_text:
            sys.stdout.write("\n\n")
            sys.stdout.flush()
            self._has_text = False

        match activity_type:
            # ── Tool calls (single-line with in-place replacement) ──

            case "tool_start":
                args_preview = _format_args_preview(name, metadata.get("args", {}))
                if not args_preview and rest:
                    args_preview = rest[:80]

                indent = "    " if self._in_subagent else "  "
                prefix = "\u251c\u2500 " if self._in_subagent else ""

                t = Text(f"{indent}{prefix}\u25cb ", style="dim cyan")
                t.append(name, style="bold cyan")
                if args_preview:
                    t.append(f"  {args_preview}", style="dim")
                self._console.print(t)

                self._pending_tool = {
                    "name": name,
                    "args_preview": args_preview,
                    "start_time": time.monotonic(),
                    "indent": indent,
                    "prefix": prefix,
                }
                self._can_replace = True

            case "tool_done":
                elapsed = ""
                if self._pending_tool and self._pending_tool["name"] == name:
                    dt = time.monotonic() - self._pending_tool["start_time"]
                    if dt >= 0.1:
                        elapsed = f"{dt:.1f}s"
                    args_preview = self._pending_tool["args_preview"]
                    indent = self._pending_tool["indent"]
                    prefix = self._pending_tool["prefix"]
                else:
                    args_preview = ""
                    indent = "    " if self._in_subagent else "  "
                    prefix = "\u251c\u2500 " if self._in_subagent else ""

                # Build the done line
                result_info = _format_result_preview(rest)

                t = Text(f"{indent}{prefix}\u25cf ", style="green")
                t.append(name, style="bold cyan")
                if args_preview:
                    t.append(f"  {args_preview}", style="dim")
                parts = [p for p in (result_info, elapsed) if p]
                if parts:
                    t.append(f"  ({', '.join(parts)})", style="dim")

                if self._can_replace and self._pending_tool:
                    # Replace the tool_start line in-place
                    sys.stdout.write("\033[A\033[2K")
                    sys.stdout.flush()

                self._console.print(t)
                self._pending_tool = None
                self._can_replace = False

            case "tool_error":
                if self._can_replace and self._pending_tool:
                    sys.stdout.write("\033[A\033[2K")
                    sys.stdout.flush()

                indent = "    " if self._in_subagent else "  "
                prefix = "\u251c\u2500 " if self._in_subagent else ""
                t = Text(f"{indent}{prefix}\u2717 ", style="red")
                t.append(name, style="bold red")
                if rest:
                    t.append(f"  {rest[:100]}", style="red")
                self._console.print(t)
                self._pending_tool = None
                self._can_replace = False

            # ── Sub-agent calls (nested block) ──────────────────

            case "subagent_start":
                self._console.print()
                task = metadata.get("task", rest)
                t = Text("  \u25b7 ", style="dim magenta")
                t.append(name, style="bold magenta")
                if task:
                    t.append(f"  {task[:80]}", style="dim")
                self._console.print(t)
                self._in_subagent = True
                self._subagent_name = name
                self._can_replace = False

            case "subagent_done":
                self._in_subagent = False
                tools_used = metadata.get("tools_used", [])
                turns = metadata.get("turns", 0)
                elapsed = metadata.get("duration", 0)

                t = Text("  \u25b6 ", style="green")
                t.append(name, style="bold magenta")
                parts = []
                if tools_used:
                    parts.append(", ".join(tools_used))
                if turns:
                    parts.append(f"{turns} turns")
                if elapsed and elapsed >= 0.1:
                    parts.append(f"{elapsed:.1f}s")
                if parts:
                    t.append(f"  ({'; '.join(parts)})", style="dim")
                self._console.print(t)
                self._console.print()
                self._can_replace = False

            case "subagent_error":
                self._in_subagent = False
                t = Text("  \u2717 ", style="red")
                t.append(name, style="bold red")
                if rest:
                    t.append(f"  {rest[:100]}", style="red")
                self._console.print(t)
                self._console.print()
                self._can_replace = False

            # ── Sub-agent internal tools (deeply nested) ────────

            case s if s.startswith("subagent_tool_"):
                tool_name = metadata.get("tool", "")
                sub_detail = metadata.get("detail", rest)
                sub_activity = s.replace("subagent_", "")

                if sub_activity == "tool_start":
                    t = Text("    \u251c\u2500 \u25cb ", style="dim")
                    t.append(tool_name, style="cyan")
                    args_str = _format_args_preview(
                        tool_name, metadata.get("args", {})
                    )
                    if args_str:
                        t.append(f"  {args_str}", style="dim")
                    elif sub_detail:
                        t.append(f"  {sub_detail[:60]}", style="dim")
                    self._console.print(t)
                    self._pending_tool = {
                        "name": tool_name,
                        "args_preview": args_str or sub_detail[:60],
                        "start_time": time.monotonic(),
                        "indent": "    ",
                        "prefix": "\u251c\u2500 ",
                    }
                    self._can_replace = True

                elif sub_activity == "tool_done":
                    result_info = _format_result_preview(sub_detail)
                    t = Text("    \u251c\u2500 \u25cf ", style="dim green")
                    t.append(tool_name, style="cyan")
                    if self._pending_tool and self._pending_tool["name"] == tool_name:
                        args_str = self._pending_tool["args_preview"]
                        if args_str:
                            t.append(f"  {args_str}", style="dim")
                    if result_info:
                        t.append(f"  ({result_info})", style="dim")

                    if self._can_replace and self._pending_tool:
                        sys.stdout.write("\033[A\033[2K")
                        sys.stdout.flush()
                    self._console.print(t)
                    self._pending_tool = None
                    self._can_replace = False

                elif sub_activity == "tool_error":
                    if self._can_replace and self._pending_tool:
                        sys.stdout.write("\033[A\033[2K")
                        sys.stdout.flush()
                    t = Text("    \u251c\u2500 \u2717 ", style="red")
                    t.append(tool_name, style="bold red")
                    self._console.print(t)
                    self._pending_tool = None
                    self._can_replace = False

            case _:
                self._can_replace = False

    # ── Resume history rendering ────────────────────────────────

    async def on_resume(self, events: list[dict]) -> None:
        """Render session history with full detail and markdown."""
        if not events:
            return

        turns = _group_into_turns(events)
        if not turns:
            return

        self._console.print()
        header = Text()
        header.append(" Resumed session ", style="bold reverse")
        header.append(f"  {len(turns)} turns", style="dim")
        self._console.print(header)
        self._console.print()

        for turn in turns:
            _render_turn(self._console, turn)

        sep = Text("\u2500" * 50, style="dim")
        self._console.print(sep)
        self._console.print()


# ── Helpers ─────────────────────────────────────────────────────


def _parse_detail(detail: str) -> tuple[str, str]:
    """Extract [name] prefix from detail string.

    Strips the [job_id] suffix: "info[9b4270]" -> "info".
    """
    if detail.startswith("["):
        try:
            end = detail.index("]", 1)
            raw_name = detail[1:end]
            rest = detail[end + 2 :]
            if "[" in raw_name:
                raw_name = raw_name[: raw_name.index("[")]
            return raw_name, rest
        except (ValueError, IndexError):
            pass
    return "unknown", detail


def _format_args_preview(tool_name: str, args: dict) -> str:
    """Format tool args as a concise preview string."""
    if not args:
        return ""
    match tool_name:
        case "bash":
            return args.get("command", "")[:80]
        case "read":
            path = args.get("path", "")
            offset = args.get("offset")
            limit = args.get("limit")
            suffix = ""
            if offset or limit:
                suffix = f" ({offset or 0}:{(offset or 0) + (limit or 0)})"
            return f"{path}{suffix}"
        case "write":
            return args.get("path", "")[:80]
        case "edit":
            return args.get("file_path", args.get("path", ""))[:80]
        case "glob":
            return args.get("pattern", "")[:80]
        case "grep":
            pattern = args.get("pattern", "")
            path = args.get("path", "")
            return f'"{pattern}" {path}'.strip()[:80]
        case "send_message":
            return f"-> {args.get('channel', '')}"
        case "wait_channel":
            return f"<- {args.get('channel', '')}"
        case "terrarium_send":
            return f"-> {args.get('channel', '')}"
        case "terrarium_observe":
            return f"<- {args.get('channel', '')}"
        case "think":
            thought = str(args.get("thought", args.get("content", "")))
            return thought[:60]
        case "info":
            return args.get("name", args.get("topic", ""))[:60]
        case _:
            for k, v in args.items():
                if k == "content" or k.startswith("_"):
                    continue
                return f"{k}={str(v)[:50]}"
            return ""


def _format_result_preview(output: str) -> str:
    """Format tool result as a compact preview."""
    if not output:
        return ""
    lines = output.strip().split("\n")
    if len(lines) == 1 and len(lines[0]) <= 60:
        return lines[0]
    return f"{len(lines)} lines"


# ── Resume rendering ────────────────────────────────────────────


def _render_turn(console: Console, turn: dict) -> None:
    """Render one conversation turn with full detail."""
    # User input / trigger
    if turn["input_type"] == "user_input":
        console.print(
            Panel(
                turn["input"],
                title="[bold cyan]You[/]",
                title_align="left",
                border_style="cyan",
                padding=(0, 1),
            )
        )
    else:
        console.print(
            Panel(
                turn["input"][:300],
                title="[bold yellow]Trigger[/]",
                title_align="left",
                border_style="yellow",
                padding=(0, 1),
            )
        )
    console.print()

    # Events (tools and sub-agents)
    in_subagent = False
    for evt in turn["events"]:
        etype = evt.get("type", "")

        if etype == "tool_call":
            name = evt.get("name", "tool")
            args = evt.get("args", {})
            indent = "    " if in_subagent else "  "
            prefix = "\u251c\u2500 " if in_subagent else ""
            # In resume, we show the final state directly (● not ○)
            t = Text(f"{indent}{prefix}\u25cf ", style="green")
            t.append(name, style="bold cyan")
            args_preview = _format_args_preview(name, args)
            if args_preview:
                t.append(f"  {args_preview}", style="dim")
            console.print(t)

        elif etype == "tool_result":
            pass  # Merged into tool_call line above for resume

        elif etype == "subagent_call":
            in_subagent = True
            name = evt.get("name", "subagent")
            task = evt.get("task", "")
            console.print()
            t = Text("  \u25b7 ", style="dim magenta")
            t.append(name, style="bold magenta")
            if task:
                t.append(f"  {task[:80]}", style="dim")
            console.print(t)

        elif etype == "subagent_result":
            name = evt.get("name", "subagent")
            tools = evt.get("tools_used", [])
            turns_count = evt.get("turns", 0)
            duration = evt.get("duration", 0)
            t = Text("  \u25b6 ", style="green")
            t.append(name, style="bold magenta")
            parts = []
            if tools:
                parts.append(", ".join(tools))
            if turns_count:
                parts.append(f"{turns_count} turns")
            if duration and duration >= 0.1:
                parts.append(f"{duration:.1f}s")
            if parts:
                t.append(f"  ({'; '.join(parts)})", style="dim")
            console.print(t)
            console.print()
            in_subagent = False

        elif etype == "subagent_tool":
            tool_name = evt.get("tool_name", "")
            t = Text("    \u251c\u2500 \u25cf ", style="dim green")
            t.append(tool_name, style="cyan")
            console.print(t)

    # Assistant text (rendered as markdown for resume)
    text = "".join(turn["text_parts"]).strip()
    if text:
        console.print()
        try:
            console.print(RichMarkdown(text))
        except Exception:
            console.print(text)

    console.print()


def _group_into_turns(events: list[dict]) -> list[dict]:
    """Group session events into turns for resume display."""
    turns: list[dict] = []
    current: dict | None = None

    for evt in events:
        etype = evt.get("type", "")
        if etype == "user_input":
            if current:
                turns.append(current)
            current = {
                "input_type": "user_input",
                "input": evt.get("content", ""),
                "text_parts": [],
                "events": [],
            }
        elif etype == "trigger_fired":
            if current:
                turns.append(current)
            ch = evt.get("channel", "")
            sender = evt.get("sender", "")
            content = evt.get("content", "")
            current = {
                "input_type": "trigger",
                "input": f"[{ch}] {sender}: {content}",
                "text_parts": [],
                "events": [],
            }
        elif current is not None:
            if etype == "text":
                current["text_parts"].append(evt.get("content", ""))
            elif etype in (
                "tool_call",
                "tool_result",
                "subagent_call",
                "subagent_result",
                "subagent_tool",
            ):
                current["events"].append(evt)

    if current:
        turns.append(current)
    return turns
