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

## Summary

The current API is a foundation. For a full Web UI, we need:
1. HTTP REST API wrapping `TerrariumAPI` + config CRUD
2. WebSocket streams for real-time channel/creature observation
3. `TerrariumManager` for multiple concurrent terrariums
4. SQLite for persistent config storage and message history
5. Vue3 frontend with topology graph, channel stream, and creature details
6. Agent chat interface for standalone creatures
