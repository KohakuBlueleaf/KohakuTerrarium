# Frontend Improvements Plan

Current state: Vue 3 web frontend with basic chat, topology graph, sessions page.
Goal: feature parity with the planned TUI (minus terminal constraints, plus graph).

## 1. Running Tasks Panel

**What:** A sidebar panel showing all currently running background tools and sub-agents
with the ability to stop them individually.

**Where:** Right side of the instance view, alongside or below the inspector panel.

**Design:**
```
+--- Running Tasks ----------------+
| o bash  npm test           [x]   |
|   started 2.1s ago               |
|                                   |
| > explore  find auth code  [x]   |
|   started 5.2s ago               |
|   +-- o glob **/*.py             |
|   +-- o grep "auth"              |
|                                   |
| o terrarium_observe        [x]   |
|   watching: results              |
+-----------------------------------+
```

**Implementation:**
- New component: `RunningTasksPanel.vue`
- Data source: WebSocket events (`tool_start` / `subagent_start` add entries,
  `tool_done` / `tool_error` / `subagent_done` remove them)
- Stop button calls: `POST /api/agents/{id}/interrupt` or uses `stop_task`
  via the chat (send a stop_task tool call command)
- Refresh: also poll agent status endpoint for job list

**API needed:**
- `GET /api/agents/{id}/jobs` or `GET /api/terrariums/{id}/creatures/{name}/jobs`
  to list running jobs (not yet implemented)
- Or derive from WebSocket events (track in Pinia store)

**Priority:** High. Users need visibility into what's running and ability to stop it.

## 2. Improved Tool Call Accordion

**Current:** ToolCallBlock.vue with basic expand/collapse, shows args and result.

**Improvements:**
- Show tool state badge: running (amber pulse), done (green check), error (red x),
  interrupted (amber circle)
- Show elapsed time
- Show input args in a formatted code block (not raw key=value)
- Tool-specific formatting:
  - `bash`: show command in monospace, output as terminal-styled block
  - `read`: show file path, line range, content with syntax highlighting
  - `edit`: show diff view (red/green)
  - `grep`: show pattern, matches with line numbers
  - `glob`: show pattern, file list
- Sub-agent accordion: show nested tool list AND result markdown
- Collapsible by default, expanded on click
- "Copy output" button on expanded view

**Implementation:**
- Refactor `ToolCallBlock.vue` into a more detailed component
- Add tool-specific render functions (bash output, diff view, etc.)
- Use existing `MarkdownRenderer.vue` for sub-agent results
- Add elapsed time tracking (store start timestamp in tool part object)

**Priority:** Medium. Current accordion works but lacks detail.

## 3. Sub-agent Nesting in Chat

**Current:** Sub-agent tools now nest inside parent accordion (fixed in this session).

**Improvements:**
- Show sub-agent's internal tool calls as a compact list with icons
- Show sub-agent result as rendered markdown
- Show interrupted sub-agents with amber indicator
- Allow expanding individual nested tool calls

**Current state:** Mostly working after the `subagent_tool` nesting fix.
Needs visual polish: nested tools should have lighter background, indented more clearly.

**Priority:** Low. Functionally working, needs polish.

## 4. Session Management Page

**Current:** Sessions page lists saved sessions with resume button.

**Improvements:**
- Show session preview: last few messages, token usage, duration
- Delete session button
- Search/filter sessions
- Show session size (file size)
- Sort by: last active, created, name, type
- Auto-refresh when new sessions appear

**API needed:**
- `DELETE /api/sessions/{name}` to delete a session file
- Session preview data already available from metadata

**Priority:** Low. Current page is functional.

## 5. Interrupt UX

**Current:** Red stop button replaces send button during processing.

**Improvements:**
- Keyboard shortcut: Escape key to interrupt (like Claude Code)
- Show "Interrupted" status message in chat after interrupt
- Stop button should also appear during background tool execution
  (not just during main processing)
- Add interrupt buttons per creature in terrarium topology view

**Implementation:**
- Add `@keydown.escape` handler on the chat panel
- Track "any background activity" state (not just `processing` flag)
- Add interrupt buttons to creature nodes in topology graph

**Priority:** Medium. Stop button works but needs keyboard shortcut.

## 6. Token Usage Display

**Current:** Token count shown in tab bar header.

**Improvements:**
- Per-creature token breakdown in terrarium mode
- Cost estimate (if model pricing is known)
- Token usage chart over time (sparkline)
- Show in session info panel

**Priority:** Low. Current display is adequate.

## 7. Channel Message Feed

**Current:** Channel messages appear as trigger panels in chat.

**Improvements:**
- Dedicated channel tab with message feed (already has tabs)
- Channel message formatting: sender badge, timestamp, content
- Ability to send messages to channels from the UI
- Real-time channel message count in tab badge

**Priority:** Low. Channels are visible through trigger events.

## 8. Creature Status in Topology

**Current:** Topology graph shows creature nodes with status dots.

**Improvements:**
- Animate status dot when creature is processing
- Show current activity tooltip (what tool/sub-agent is running)
- Click creature node to open its chat tab
- Show channel message flow as animated edges
- Interrupt button on creature node context menu

**Priority:** Low. Graph is informational, not interactive.

## Implementation Order

1. **Running Tasks Panel** (high value, enables task management)
2. **Escape key interrupt** (quick win, important UX)
3. **Improved Tool Accordion** (visual quality)
4. **Sub-agent nesting polish** (visual quality)
5. **Session management improvements** (convenience)
6. **Everything else** (low priority)

## API Additions Needed

| Endpoint | Purpose | Priority |
|----------|---------|----------|
| `GET /api/agents/{id}/jobs` | List running jobs | High |
| `GET /api/terrariums/{id}/creatures/{name}/jobs` | List creature jobs | High |
| `DELETE /api/sessions/{name}` | Delete session file | Medium |
| `POST /api/agents/{id}/tasks/{job_id}/stop` | Stop specific task | Medium |
