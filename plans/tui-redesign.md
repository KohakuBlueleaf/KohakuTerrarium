# TUI Redesign Plan

Goal: TUI = "TUI version of the web frontend, minus the topology graph."
Each instance = one TUI. TUI has no graph. Otherwise the design is nearly the same.

## Design Principles

1. One Collapsible per tool call (no separate start/done lines)
2. Sub-agents as nested Collapsible containing their tool Collapsibles
3. Text streams live into the chat view
4. Right panel shows live status, not a log dump
5. Terrarium mode adds chat tabs and terrarium overview
6. Escape key interrupts current processing (not Ctrl+C which kills the app)

## Layout: Standalone Agent

```
+--- KohakuTerrarium - swe_agent -----------------------------------+
| [Chat]                            | [Status] [Logs]               |
+-----------------------------------+                                |
|                                   | +--- Running ----------------+|
| +- You -----------------------+  | | o bash  npm test  (2.1s)   ||
| | Fix the auth bug            |  | | > explore  find auth (5s)  ||
| +-----------------------------+  | +----------------------------+|
|                                   |                                |
| I'll investigate the auth module. | +--- Scratchpad -------------+|
|                                   | | plan: step 1               ||
| > read src/auth/middleware.py     | | status: working             ||
|   142 lines                  [v]  | +----------------------------+|
|                                   |                                |
| > bash npm test                   | +--- Session ----------------+|
|   PASS (12 tests)            [v]  | | ID: cli_abc12345           ||
|                                   | | Runtime: 2m 31s            ||
| v explore find auth validation    | | Tokens: 12.4k             ||
|   +-- o glob **/*.py (12 files)   | | Model: gpt-5.4             ||
|   +-- o grep "validate_token"     | +----------------------------+|
|   +-- o read middleware.py        |                                |
|   Found validate_token() on 42   |                                |
|                                   |                                |
| The issue is on line 42...        |                                |
|                                   |                                |
| KohakUwU  o Idle                  |                                |
+-----------------------------------+                                |
| > _                               |                                |
+-----------------------------------+--------------------------------+
| Esc: interrupt  Ctrl+C: quit  Ctrl+L: clear            F1: help   |
+--------------------------------------------------------------------+
```

## Layout: Terrarium Mode

```
+--- KohakuTerrarium - swe_team ------------------------------------+
| [root] [swe] [reviewer] [#tasks] [#review] | [Status] [Terrarium] |
+---------------------------------------------+                      |
|                                             | +--- Running -------+|
| (same chat area as standalone,              | | o terrarium_send  ||
|  content switches per active tab)           | | > explore (5.2s)  ||
|                                             | +------------------+|
|                                             |                      |
|                                             | +--- Scratchpad ---+|
|                                             | | task: auth bug    ||
|                                             | +------------------+|
|                                             |                      |
|                                             | +--- Session ------+|
|                                             | | ID: terrarium_... ||
|                                             | | Creatures: 2      ||
|                                             | | Channels: 5       ||
|                                             | | Tokens: 24.1k     ||
|                                             | +------------------+|
|                                             |                      |
| KohakUwU  o Idle                            |                      |
+---------------------------------------------+                      |
| > _                                         |                      |
+---------------------------------------------+----------------------+
| Tab: switch chat  Esc: interrupt  Ctrl+C: quit           F1: help  |
+---------------------------------------------------------------------+
```

### Terrarium Tab (right panel)

```
+--- Terrarium ----------------------+
| Creatures:                         |
|   o swe       [tasks, feedback]    |
|               -> [review, chat]    |
|   o reviewer  [review, chat]       |
|               -> [feedback, results]|
|                                    |
| Channels:                          |
|   tasks      (queue)    2 msgs     |
|   review     (queue)    0 msgs     |
|   feedback   (queue)    1 msgs     |
|   results    (queue)    0 msgs     |
|   team_chat  (broadcast) 3 msgs   |
+------------------------------------+
```

## Chat Area Widget Tree

```
ChatView (VerticalScroll, auto-scroll to bottom)
  +-- UserMessage (Panel, cyan border)
  |     "Fix the auth bug"
  |
  +-- AssistantBlock (Container)
  |   +-- StreamingText (Static, live-updating during generation)
  |   |     "I'll investigate the auth module."
  |   |
  |   +-- ToolBlock (Collapsible, collapsed by default)
  |   |     title: "o read  src/auth/middleware.py  (142 lines)"
  |   |     body:  "path=src/auth/middleware.py\n---\n(output preview)"
  |   |
  |   +-- ToolBlock (Collapsible)
  |   |     title: "o bash  npm test  (12 tests passed)"
  |   |     body:  "command=npm test\n---\n> jest --runInBand\nPASS..."
  |   |
  |   +-- SubAgentBlock (Collapsible)
  |   |     title: "v explore  find auth validation  (3 tools, 2.1s)"
  |   |     body:
  |   |       +-- ToolBlock (nested, compact)
  |   |       |     "o glob **/*.py (12 files)"
  |   |       +-- ToolBlock
  |   |       |     "o grep validate_token (3 matches)"
  |   |       +-- ToolBlock
  |   |       |     "o read middleware.py (142 lines)"
  |   |       +-- ResultText (Static)
  |   |             "Found validate_token() on line 42..."
  |   |
  |   +-- StreamingText (Static)
  |         "The issue is on line 42..."
  |
  +-- TriggerMessage (Panel, yellow border)
  |     "[results] swe: Fixed the auth bug..."
  |
  +-- AssistantBlock (Container)
        ...
```

## Tool Call State Machine

Each ToolBlock transitions through states. The header updates in-place.

```
PENDING:    o bash  npm test              (dim, no expand arrow)
RUNNING:    o bash  npm test  (1.2s)      (animated, dim timer)
DONE:       o bash  npm test  (12 tests)  (green dot, expandable)
ERROR:      x bash  npm test  (error)     (red x, expandable)
```

In the Running panel (right side), only PENDING/RUNNING tools appear.
When a tool transitions to DONE/ERROR, it's removed from Running.

## Key Bindings

| Key | Action |
|-----|--------|
| Escape | Interrupt current processing (cancel LLM + direct tools) |
| Ctrl+C | Quit the TUI |
| Ctrl+L | Clear chat view |
| Tab / Shift+Tab | Switch chat tabs (terrarium mode) |
| Enter | Send message |
| Shift+Enter | Newline in input |
| F1 | Show help overlay |

## Files to Create/Modify

### New: `builtins/tui/widgets.py`

Custom Textual widgets:

```python
class ToolBlock(Collapsible):
    """Single tool call. Header updates in-place for state transitions."""
    # title: "o tool_name  args_preview  (result_summary)"
    # body: "Args:\n  key=value\n---\nOutput:\n  ..."
    # States: pending, running, done, error

class SubAgentBlock(Collapsible):
    """Sub-agent with nested ToolBlocks."""
    # title: "v agent_name  task  (N tools, Xs)"
    # body: ToolBlock children + result text

class UserMessage(Static):
    """User input rendered as a panel."""

class TriggerMessage(Static):
    """Channel trigger rendered as a panel."""

class StreamingText(Static):
    """Live-updating text during LLM generation."""

class RunningPanel(Static):
    """Live list of running tools/sub-agents. Auto-updates."""

class ScratchpadPanel(Static):
    """Key-value scratchpad viewer. Auto-updates."""

class SessionInfoPanel(Static):
    """Session metadata: ID, runtime, tokens, model."""

class TerrariumOverview(Static):
    """Creature/channel status for terrarium mode."""
```

### Rewrite: `builtins/tui/session.py`

- Replace `RichLog` chat area with `VerticalScroll` containing widget tree
- Add `TabbedContent` for chat tabs (terrarium mode)
- Replace right panel (2 tabs) with 3-section status + terrarium tab
- Add key binding for Escape (interrupt)
- Expose methods for TUIOutput to call: `add_user_message()`,
  `add_tool_block()`, `update_tool_block()`, `add_subagent_block()`,
  `add_trigger_message()`, `update_streaming_text()`, `update_running()`,
  `update_scratchpad()`, `update_session_info()`

### Rewrite: `builtins/tui/output.py`

- `on_activity("tool_start")`: create ToolBlock(collapsed), add to chat
- `on_activity("tool_done")`: update ToolBlock title with result summary
- `on_activity("subagent_start")`: create SubAgentBlock
- `on_activity("subagent_tool_*")`: add/update nested ToolBlock
- `on_activity("subagent_done")`: update SubAgentBlock title
- `write_stream()`: update StreamingText widget
- `on_processing_start()`: create new AssistantBlock + StreamingText
- `on_processing_end()`: finalize StreamingText
- `on_user_input()`: add UserMessage widget
- Live-update RunningPanel on tool start/done

## Implementation Phases

### Phase 1: Chat area with Collapsible tools
- Replace RichLog with VerticalScroll
- ToolBlock widget with state transitions
- UserMessage and TriggerMessage widgets
- StreamingText for live output
- Basic Escape key interrupt

### Phase 2: Right panel redesign
- Running panel (live tool/sub-agent list)
- Scratchpad viewer
- Session info panel
- Replace Status/Logs tabs with 3-section layout + Logs tab

### Phase 3: Sub-agent nesting
- SubAgentBlock with nested ToolBlocks
- Result text inside sub-agent accordion

### Phase 4: Terrarium mode
- Chat tabs (root + creatures + channels)
- Tab switching with keyboard
- Per-tab message history
- Terrarium overview tab in right panel

### Phase 5: Resume history in TUI
- on_resume renders historical events as proper widgets
  (UserMessage, ToolBlock(done), SubAgentBlock, TriggerMessage)
- Same visual as live session

## Textual Widgets Reference

| Widget | Use |
|--------|-----|
| `Collapsible` | Accordion for tools and sub-agents |
| `VerticalScroll` | Scrollable chat container |
| `Static` | Updatable text (streaming, panels) |
| `TabbedContent` / `TabPane` | Chat tabs, right panel tabs |
| `Input` | Message input |
| `Header` / `Footer` | App chrome |
| `RichLog` | Logs tab only |
