# TUI Redesign Plan

Goal: TUI = "TUI version of the web frontend, minus the topology graph"

## Layout

```
┌─ KohakuTerrarium ──────────────────────────────────────────────────┐
│ [root] [swe] [reviewer] [#tasks] [#review]  │ [Status] [Terrarium]│
├─────────────────────────────────────────────┤                      │
│                                              │ ┌─ Running ────────┐│
│ ╭─ You ──────────────────────────────╮      │ │ ○ bash (2.1s)    ││
│ │ Fix the auth bug                    │      │ │ ▷ explore (5.2s) ││
│ ╰────────────────────────────────────╯      │ └──────────────────┘│
│                                              │ ┌─ Scratchpad ─────┐│
│ I'll investigate the auth module.            │ │ plan: step 1     ││
│                                              │ │ status: working  ││
│ ▶ read src/auth/middleware.py ────────       │ └──────────────────┘│
│   path=src/auth/middleware.py          [v]  │ ┌─ Session ────────┐│
│   142 lines read                             │ │ ID: cli_abc123   ││
│                                              │ │ Runtime: 2m 31s  ││
│ ▶ bash npm test ─────────────────────       │ │ Tokens: 12.4k    ││
│   command=npm test                     [v]  │ │ Model: gpt-5.4   ││
│   PASS (12 tests)                            │ └──────────────────┘│
│                                              │                      │
│ ▼ explore find auth validation ──────       │                      │
│   ├─ ● glob **/*.py (12 files)              │                      │
│   ├─ ● grep "validate_token" (3 matches)    │                      │
│   └─ ● read middleware.py (142 lines)       │                      │
│   Result: Found validate_token() ...        │                      │
│                                              │                      │
│ The issue is on line 42...                   │                      │
│                                              │                      │
│ ◐ KohakUwUing...                             │                      │
├──────────────────────────────────────────────┤                      │
│ > _                                          │                      │
└──────────────────────────────────────────────┴──────────────────────┘
```

## Files to Change

### `builtins/tui/session.py` (rewrite AgentTUI)

**New Textual widgets needed:**
- `ToolBlock(Collapsible)`: single tool call with header (name + args) and body (output)
- `SubAgentBlock(Collapsible)`: sub-agent with nested ToolBlocks
- `ChatView(VerticalScroll)`: scrollable chat with messages, ToolBlocks, text
- `RunningPanel(Static)`: live-updating list of running tools
- `ScratchpadPanel(Static)`: live-updating scratchpad key-value display
- `SessionInfoPanel(Static)`: session metadata display
- `TerrariumOverview(Container)`: creature/channel status list

**New layout:**
```python
def compose(self) -> ComposeResult:
    yield Header()
    with Horizontal(id="main-container"):
        with Vertical(id="left-panel"):
            # Chat tabs (for terrarium: root + creatures + channels)
            with TabbedContent(id="chat-tabs"):
                with TabPane("Chat", id="tab-chat"):
                    yield ChatView(id="chat-view")
            yield Static("", id="quick-status")
            yield Input(placeholder="Type a message...", id="input-box")
        with Vertical(id="right-panel"):
            with TabbedContent(id="info-tabs"):
                with TabPane("Status", id="tab-status"):
                    yield RunningPanel(id="running-panel")
                    yield ScratchpadPanel(id="scratchpad-panel")
                    yield SessionInfoPanel(id="session-panel")
                with TabPane("Logs", id="tab-logs"):
                    yield RichLog(id="logs-log")
    yield Footer()
```

**Terrarium mode adds:**
- Extra chat tabs: one per creature + one per channel
- "Terrarium" tab in right panel with creature/channel overview

### `builtins/tui/output.py` (rewrite TUIOutput)

**Tool call flow (single Collapsible, updated in-place):**
1. `on_activity("tool_start")`: create ToolBlock(collapsed), add to ChatView
2. `on_activity("tool_done")`: update ToolBlock header with result summary
3. No separate start/done lines

**Sub-agent flow:**
1. `on_activity("subagent_start")`: create SubAgentBlock(collapsed)
2. `on_activity("subagent_tool_start")`: add ToolBlock inside SubAgentBlock
3. `on_activity("subagent_done")`: update SubAgentBlock header

**Text streaming:**
Text chunks go to a running Markdown widget at bottom of ChatView.
On processing_end, the widget is finalized.

**Running panel updates:**
Tool start: add entry to RunningPanel
Tool done: remove from RunningPanel

### `builtins/tui/widgets.py` (new file)

Custom Textual widgets:
- `ToolBlock`: Collapsible with tool name/args header, output body
- `SubAgentBlock`: Collapsible with nested ToolBlocks
- `RunningPanel`: live list of running jobs
- `ScratchpadPanel`: formatted key-value display
- `SessionInfoPanel`: session metadata display
- `TerrariumOverview`: creature status + channel list

## Implementation Priority

1. Right panel redesign (3 sections)
2. ToolBlock Collapsible widget
3. In-place tool state updates (no separate start/done)
4. SubAgentBlock with nested tools
5. Chat tabs for terrarium
6. Terrarium overview tab
7. Running panel live updates
8. Scratchpad viewer
9. Session info panel

## Key Textual Widgets to Use

- `Collapsible`: native accordion, title + collapsible body
- `VerticalScroll`: scrollable container (replaces RichLog for chat)
- `Static`: updatable text widget (for panels)
- `TabbedContent` / `TabPane`: tabs
- `RichLog`: still useful for logs tab
- `DataTable`: could use for scratchpad/session info
