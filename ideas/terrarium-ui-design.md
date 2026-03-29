# Terrarium UI/UX Design

The interface layer for observing, controlling, and interacting with terrariums.

## Design Principle

The terrarium interface serves three contexts with one unified API:
1. **Programmatic** - Python code importing the library
2. **CLI** - Terminal commands for quick operations
3. **Web UI** - Rich visual interface for monitoring and interaction
4. **HTTP API** - The bridge between backend and any frontend

All four share the same core operations. The Web UI is the primary experience. CLI and programmatic are power-user shortcuts. HTTP API is the transport.

## Core API Shape

### Current State (What Exists)

```python
class TerrariumAPI:
    # Channel ops
    list_channels() -> list[dict]
    channel_info(name) -> dict
    send_to_channel(name, content, sender, metadata) -> str

    # Creature ops
    list_creatures() -> list[dict]
    get_creature_status(name) -> dict
    stop_creature(name) -> bool
    start_creature(name) -> bool

    # Terrarium ops
    get_status() -> dict
    is_running -> bool
```

### What's Missing

The current API is read-heavy but interaction-light. For a real UI, we need:

**Configuration CRUD** (before running):
- Create/edit/delete terrarium configs
- Create/edit/delete creature configs
- Manage channel topology (add/remove channels, change types)
- Validate configs before running

**Runtime Control**:
- Hot-add/remove channels while running
- Hot-add/remove creatures while running
- Pause/resume individual creatures
- Inject messages into any channel (already exists)
- Read channel message history (not just live observation)

**Observation**:
- Real-time channel message stream (WebSocket)
- Creature output log stream (WebSocket)
- Channel traffic metrics (messages/sec, queue depth)
- Creature activity timeline (when did each creature process events)

**Session Management**:
- Multiple terrariums running simultaneously
- Save/load terrarium state
- Export terrarium as distributable zip

## HTTP API Design

### REST Endpoints

```
# Terrarium lifecycle
POST   /api/terrariums                    Create + start a terrarium from config
GET    /api/terrariums                    List running terrariums
GET    /api/terrariums/{id}               Get terrarium status
DELETE /api/terrariums/{id}               Stop + cleanup terrarium
POST   /api/terrariums/{id}/pause         Pause all creatures
POST   /api/terrariums/{id}/resume        Resume all creatures

# Creatures
GET    /api/terrariums/{id}/creatures              List creatures
GET    /api/terrariums/{id}/creatures/{name}        Creature status + recent log
POST   /api/terrariums/{id}/creatures/{name}/stop   Stop one creature
POST   /api/terrariums/{id}/creatures/{name}/start  Restart one creature

# Channels
GET    /api/terrariums/{id}/channels               List channels
GET    /api/terrariums/{id}/channels/{name}         Channel info + recent messages
POST   /api/terrariums/{id}/channels/{name}/send    Inject message

# Configuration (CRUD, no running terrarium needed)
GET    /api/configs                       List saved configs
POST   /api/configs                       Create new config
GET    /api/configs/{id}                  Get config details
PUT    /api/configs/{id}                  Update config
DELETE /api/configs/{id}                  Delete config
POST   /api/configs/{id}/validate         Validate config
POST   /api/configs/{id}/export           Export as zip

# Single agent (run standalone creature with chat interface)
POST   /api/agents                        Create + start agent from config
GET    /api/agents/{id}                   Agent status
POST   /api/agents/{id}/chat              Send message (chat interface)
DELETE /api/agents/{id}                   Stop agent
```

### WebSocket Streams

```
WS /ws/terrariums/{id}/channels          All channel messages (real-time)
WS /ws/terrariums/{id}/channels/{name}   Single channel stream
WS /ws/terrariums/{id}/creatures/{name}  Creature output log stream
WS /ws/terrariums/{id}/events            All terrarium events (lifecycle, errors)
WS /ws/agents/{id}/chat                  Agent chat stream (streaming LLM output)
```

## CLI Design

The CLI mirrors the HTTP API but for terminal use:

```bash
# Terrarium
kohaku terrarium run <path> [--seed "..."] [--observe]
kohaku terrarium info <path>
kohaku terrarium stop <id>
kohaku terrarium list

# Channels (while terrarium running)
kohaku channel list <terrarium-id>
kohaku channel send <terrarium-id> <channel> "message"
kohaku channel read <terrarium-id> <channel> [--last 10]

# Agent (standalone)
kohaku agent run <path>
kohaku agent chat <path>          # interactive chat mode

# Config
kohaku config validate <path>
kohaku config export <path> -o terrarium.zip
```

## Web UI Design

### Tech Stack

- **Frontend**: Vite + Vue3 + UnoCSS + Pinia + Element Plus + auto-routing
- **Backend**: FastAPI + SQLite (for config storage, message history)
- **Real-time**: WebSocket for channel streams and creature logs
- **Bundling**: Ship as optional `kohakuterrarium[web]` extra

### Page Structure

```
/                           Dashboard (list terrariums + agents)
/terrarium/new              Config editor (create terrarium)
/terrarium/:id              Terrarium viewer (main experience)
/terrarium/:id/config       Edit running terrarium config
/agent/new                  Create standalone agent
/agent/:id                  Agent chat interface
/agent/:id/config           Edit agent config
/configs                    Config library (saved configs)
```

### Terrarium Viewer (Main Page) - `/terrarium/:id`

This is the most important page. It needs to show:

#### Layout

```
+----------------------------------------------------------+
| Terrarium: novel_writer                    [Pause] [Stop] |
+----------------------------------------------------------+
|                    |                                       |
|   Topology Graph   |          Channel Stream               |
|                    |                                       |
|  [brainstorm]      |  [ideas] brainstorm: Story concept... |
|      |             |  [outline] planner: Chapter 1 of 4..  |
|      v             |  [team_chat] writer: Ch1 complete      |
|  [planner]         |  [draft] writer: Chapter 1 summary     |
|      |             |                                       |
|      v             |  > Send to channel: [____] [Send]     |
|  [writer]          |                                       |
|                    |                                       |
+--------------------+---------------------------------------+
|                    Creature Details                         |
| [brainstorm: DONE] [planner: DONE] [writer: RUNNING 3/4]  |
| Output log: "正在撰寫第三章..."                              |
+----------------------------------------------------------+
```

#### Topology Graph (Left Panel)

Visual graph showing creatures as nodes and channels as edges.
- Node colors: green (running), gray (idle), blue (done), red (error)
- Edge labels: channel name + type (queue/broadcast)
- Edge animation: pulse when message flows through
- Click node: show creature details
- Click edge: filter channel stream to that channel

Could use a simple SVG/Canvas renderer or a library like vue-flow.

#### Channel Stream (Center Panel)

Real-time message feed, like a chat UI:
- Each message shows: timestamp, channel name (color-coded), sender, content preview
- Click message to expand full content
- Filter by channel (tabs or checkboxes)
- Human can type a message and send to any channel (dropdown selector)
- Messages from different channels have different background colors

#### Creature Details (Bottom Panel)

- Status cards for each creature (running/idle/done/error)
- Click to expand: output log, tool activity, turn count, elapsed time
- Stop/restart buttons per creature

### Agent Chat Interface - `/agent/:id`

Standard chat UI for standalone agents:
- Message bubbles (user / assistant)
- Streaming assistant responses
- Tool call indicators (collapsible: "Running bash: ls -la" with output)
- Sub-agent activity sidebar
- System prompt viewer (collapsible)

### Config Editor - `/terrarium/new`

Visual config builder:
- Creature list: add/remove creatures, pick config folders
- Channel list: add/remove channels, set type (queue/broadcast), description
- Topology wiring: drag channels to creatures (listen/send)
- Preview: show the topology graph
- Validate button: check config before running
- Save/Run buttons

## Backend Architecture

```
src/kohakuterrarium/web/
  __init__.py
  app.py              FastAPI app factory
  routes/
    terrariums.py     Terrarium CRUD + lifecycle
    creatures.py      Creature status + control
    channels.py       Channel ops + message injection
    agents.py         Standalone agent chat
    configs.py        Config CRUD + validation + export
    ws.py             WebSocket handlers
  models.py           SQLite models (peewee-async or aiosqlite)
  schemas.py          Pydantic request/response schemas
  manager.py          TerrariumManager (manages multiple running terrariums)
```

The `TerrariumManager` holds references to running `TerrariumRuntime` instances:

```python
class TerrariumManager:
    _terrariums: dict[str, TerrariumRuntime]

    async def create(self, config: TerrariumConfig) -> str: ...
    async def stop(self, terrarium_id: str) -> None: ...
    def get(self, terrarium_id: str) -> TerrariumRuntime | None: ...
    def list_all(self) -> list[dict]: ...
```

### Database (SQLite)

Stores persistent data:
- Saved configs (terrarium + creature configs as JSON)
- Message history (channel messages for replay/search)
- Session logs (creature output logs)
- Run history (when was each terrarium started/stopped)

### WebSocket Protocol

```json
// Client subscribes to channels
{"type": "subscribe", "channels": ["ideas", "outline", "team_chat"]}

// Server pushes messages
{"type": "channel_message", "channel": "ideas", "sender": "brainstorm", "content": "...", "timestamp": "..."}

// Server pushes creature events
{"type": "creature_event", "creature": "writer", "event": "tool_start", "detail": "[write] chapter_1.md"}

// Client sends message
{"type": "send_message", "channel": "seed", "content": "Write a story about..."}
```

## Export Format

A terrarium zip contains everything needed to run:

```
my_terrarium.zip
  terrarium.yaml
  creatures/
    brainstorm/
      config.yaml
      prompts/system.md
    planner/
      config.yaml
      prompts/system.md
    writer/
      config.yaml
      prompts/system.md
  README.md           (auto-generated: what this terrarium does, how to run)
```

Import: extract zip, run `kohaku terrarium run ./my_terrarium/`

## Topology Graph: Channels as First-Class Nodes

Drawing individual edges between agents doesn't scale. With 12 agents on one broadcast channel, you'd get 66 edges. Unusable.

**Solution**: Channels are visual nodes, not edges.

```
Instead of (N*N edges):     Use (N+1 nodes):

  A ----> B                   A --\
  A ----> C                        +-->[tasks queue]--+--> B
  A ----> D                   E --/                   +--> C
  E ----> B                                           +--> D
  E ----> C
  E ----> D
  (6 edges)                   (4 creature-to-channel edges)
```

The graph has TWO node types:
- **Creature nodes** (circles/rounded rects) - agent instances
- **Channel nodes** (smaller rects, color-coded) - queue or broadcast

Connections are always creature-to-channel or channel-to-creature. This naturally handles all topologies:

| Pattern | Visual |
|---------|--------|
| 1:1 queue | `A --> [ch] --> B` |
| N:1 fan-in | `A,B,C --> [ch] --> D` |
| 1:N broadcast | `A --> [ch] --> B,C,D` |
| N:N group chat | `A,B,C <--> [ch] <--> A,B,C` (bidirectional) |

UI interactions:
- Click creature node: show status, output log, controls (stop/restart)
- Click channel node: filter the channel stream to that channel
- Hover edge: highlight the flow direction (send vs listen)
- Animate edges when messages flow through (pulse effect)
- For config editor: drag to connect creatures to channels

Library options: vue-flow (most flexible), D3 (powerful but manual), plain SVG (simplest, may be enough)

## Implementation Phases

### Phase A: Hot-Plug API (Python, no HTTP)

Enable adding/removing creatures and channels at runtime. Required for the root agent and for runtime management via any interface.

**New methods on Agent:**
- `add_trigger(trigger)` - add and start a trigger on a running agent
- `remove_trigger(trigger)` - stop and remove a trigger

**New methods on TerrariumRuntime:**
- `add_creature(config)` - create, wire, and start a new creature
- `remove_creature(name)` - stop, cleanup, and remove a creature
- `add_channel(name, type, desc)` - create a channel at runtime
- `wire_channel(creature, channel, direction)` - connect creature to channel

**Other:**
- Support in-memory AgentConfig (no disk path required)
- System prompt update at runtime (replace topology section)

Estimated: ~300 lines of new code across Agent + TerrariumRuntime. No architectural changes.

### Phase B: HTTP API (FastAPI, no frontend)

Backend that wraps the Python API. Testable with curl/httpie/any HTTP client. This is also what Claude Code or other agent CLIs would use.

**Deliverables:**
```
src/kohakuterrarium/web/
  app.py              FastAPI app factory
  routes/
    terrariums.py     CRUD + lifecycle
    creatures.py      Status + control
    channels.py       List + send + history
    agents.py         Standalone agent chat
    configs.py        Config CRUD + validate + export
  ws.py               WebSocket handlers (channel stream, agent chat)
  manager.py          TerrariumManager (multiple concurrent terrariums)
  models.py           SQLite models (config storage, message history)
  schemas.py          Pydantic schemas
```

**Key decisions:**
- SQLite for persistence (configs, message history, run logs)
- WebSocket for real-time (channel messages, creature events, chat streaming)
- Pydantic for request/response validation
- CORS enabled for dev (frontend on different port)

**Testable milestone:** Run a terrarium via HTTP:
```bash
curl -X POST localhost:8000/api/terrariums -d '{"config_path": "agents/novel_terrarium/"}'
curl localhost:8000/api/terrariums/1/channels
wscat -c ws://localhost:8000/ws/terrariums/1/channels  # live stream
curl -X POST localhost:8000/api/terrariums/1/channels/seed/send -d '{"content": "Write a story"}'
```

### Phase C: Frontend Skeleton (Vue3, basic pages)

Minimal viable frontend. Four pages, functional but not polished.

**Deliverables:**
```
web/frontend/
  src/
    pages/
      index.vue             Dashboard (list terrariums + agents)
      terrarium/[id].vue    Terrarium viewer
      agent/[id].vue        Agent chat
      config/new.vue        Config editor (basic)
    components/
      TopologyGraph.vue     Channel-as-node graph
      ChannelStream.vue     Real-time message feed
      CreatureStatus.vue    Status cards
      ChatMessage.vue       Chat bubble
    stores/
      terrarium.ts          Pinia store for terrarium state
      websocket.ts          WebSocket connection manager
    api/
      client.ts             HTTP API client
```

**Terrarium viewer layout:**
```
+-------------------+---------------------------+
| TopologyGraph     | ChannelStream             |
| (vue-flow or SVG) | (scrolling message feed)  |
|                   |                           |
|  [creature]       | [ideas] brainstorm: ...   |
|     |             | [outline] planner: ...    |
|  [channel]        |                           |
|     |             | > Send: [channel] [msg]   |
|  [creature]       |                           |
+-------------------+---------------------------+
| CreatureStatus bar                             |
| [brainstorm:DONE] [planner:RUN] [writer:2/4]  |
+------------------------------------------------+
```

**Agent chat layout:**
```
+------------------------------------------------+
| Agent: swe_agent                    [Stop]     |
+------------------------------------------------+
| System prompt (collapsible)                    |
+------------------------------------------------+
|                                                |
| User: Fix the auth bug                        |
|                                                |
| Agent: I'll investigate the auth module...     |
|   [tool: bash] ls src/auth/                    |
|   [tool: read] src/auth/middleware.py          |
|   Found the issue in line 42...                |
|                                                |
| > [Type a message...]                [Send]   |
+------------------------------------------------+
```

### Phase D: UI Polish + Advanced Features

- Config editor with visual topology wiring (drag to connect)
- Export/import terrarium as zip
- Real-time edge animation on topology graph
- Creature output log viewer (expandable)
- Message search across channels
- Run history (past terrarium runs)
- Dark mode / theme support

## Summary

| Phase | What | Depends On | Effort |
|-------|------|-----------|--------|
| A | Hot-plug Python API | - | Small (~300 lines) |
| B | HTTP API + WebSocket | A | Medium (~800 lines) |
| C | Vue3 frontend skeleton | B | Medium-Large |
| D | Polish + advanced features | C | Ongoing |

Phase A unblocks everything. Phase B makes it usable by any client (Claude Code, curl, frontend). Phase C gives us the visual experience. Phase D is iterative polish.
