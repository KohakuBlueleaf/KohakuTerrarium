# KohakuTerrarium Web GUI Design

## Overview

All-in-one web interface for creating, configuring, managing, and running KohakuTerrarium agents.

Tech stack: FastAPI + SQLite (backend), Vite + Vue3 + UnoCSS + Element Plus + Pinia + JavaScript/JSDoc (frontend)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (Vite + Vue3)                                      │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Dashboard │  │  Builder │  │   Chat   │  │  Export  │   │
│  │  (list)   │  │ (config) │  │  (run)   │  │  (.zip)  │   │
│  └─────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│        └──────────────┴─────────────┴──────────────┘         │
│                         │                                     │
│                    Pinia Store                                │
│              (agents, sessions, ws)                           │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP + WebSocket
┌─────────────────────────┴───────────────────────────────────┐
│  Backend (FastAPI)                                            │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Agent    │  │ Session  │  │ Chat     │  │ Export   │   │
│  │ CRUD API │  │ Manager  │  │ WS API   │  │ API      │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       └──────────────┴─────────────┴──────────────┘         │
│                         │                                     │
│              KohakuTerrarium Core                             │
│       (Agent, Session, Executor, Controller)                 │
│                         │                                     │
│                    SQLite DB                                  │
│          (agents, sessions, chat_history)                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Database Schema (SQLite)

```sql
-- Agent configurations (the "saved" agents)
CREATE TABLE agents (
    id TEXT PRIMARY KEY,           -- uuid
    name TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    config_json TEXT NOT NULL,     -- full AgentConfig as JSON
    system_prompt TEXT DEFAULT '', -- system.md content
    extra_prompts_json TEXT DEFAULT '{}', -- {subagent_name: prompt_text}
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Running sessions (one agent can have multiple sessions)
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,           -- uuid
    agent_id TEXT NOT NULL REFERENCES agents(id),
    session_key TEXT NOT NULL,     -- maps to Session registry key
    status TEXT DEFAULT 'stopped', -- stopped, running, error
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_active DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Chat history (per session)
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,            -- user, assistant, system, activity
    content TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}', -- tool calls, job IDs, etc.
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## Backend API (FastAPI)

### Agent CRUD

```
GET    /api/agents                    List all agents
POST   /api/agents                    Create agent (name, config, prompt)
GET    /api/agents/{id}               Get agent details
PUT    /api/agents/{id}               Update agent config/prompt
DELETE /api/agents/{id}               Delete agent
POST   /api/agents/{id}/duplicate     Clone agent with new name
```

### Session Management

```
GET    /api/agents/{id}/sessions      List sessions for agent
POST   /api/agents/{id}/sessions      Create new session
DELETE /api/sessions/{id}             Delete session (stops if running)
POST   /api/sessions/{id}/start       Start agent in session
POST   /api/sessions/{id}/stop        Stop running agent
GET    /api/sessions/{id}/state       Get session state (jobs, scratchpad)
GET    /api/sessions/{id}/messages    Get chat history
```

### Chat (WebSocket)

```
WS /api/sessions/{id}/chat

// Client → Server
{ "type": "input", "content": "Fix the auth bug" }
{ "type": "stop" }

// Server → Client (streaming)
{ "type": "assistant_start" }
{ "type": "text", "content": "Let me " }
{ "type": "text", "content": "analyze..." }
{ "type": "assistant_end" }
{ "type": "activity", "activity_type": "tool_start", "detail": "[bash] running ls" }
{ "type": "activity", "activity_type": "tool_done", "detail": "[bash] OK" }
{ "type": "activity", "activity_type": "subagent_start", "detail": "[explore] searching" }
{ "type": "activity", "activity_type": "subagent_done", "detail": "[explore] done (3 turns)" }
{ "type": "status", "data": { "jobs": [...], "scratchpad": {...} } }
{ "type": "error", "content": "Connection to LLM failed" }
```

### Export/Import

```
GET    /api/agents/{id}/export        Download agent as .zip
POST   /api/agents/import             Upload .zip to create agent
```

### Builtins Reference

```
GET    /api/builtins/tools            List available builtin tools
GET    /api/builtins/subagents        List available builtin sub-agents
GET    /api/builtins/inputs           List available input types
GET    /api/builtins/outputs          List available output types
```

---

## Backend Implementation

### WebSocket Chat Handler

```python
# api/chat.py

from fastapi import WebSocket
from kohakuterrarium.core.agent import Agent
from kohakuterrarium.core.session import get_session

class WebSocketOutput(BaseOutputModule):
    """Output module that streams to WebSocket."""

    def __init__(self, ws: WebSocket):
        super().__init__()
        self._ws = ws

    async def write(self, content: str) -> None:
        await self._ws.send_json({"type": "text", "content": content})

    async def write_stream(self, chunk: str) -> None:
        await self._ws.send_json({"type": "text", "content": chunk})

    async def on_processing_start(self) -> None:
        await self._ws.send_json({"type": "assistant_start"})

    async def on_processing_end(self) -> None:
        await self._ws.send_json({"type": "assistant_end"})

    def on_activity(self, activity_type: str, detail: str) -> None:
        # Fire-and-forget since on_activity is sync
        asyncio.create_task(self._ws.send_json({
            "type": "activity",
            "activity_type": activity_type,
            "detail": detail,
        }))


class WebSocketInput:
    """Input module that reads from WebSocket."""

    def __init__(self, ws: WebSocket):
        self._ws = ws
        self._queue: asyncio.Queue = asyncio.Queue()
        self.exit_requested = False

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        self.exit_requested = True

    async def get_input(self) -> TriggerEvent | None:
        data = await self._queue.get()
        if data is None:
            self.exit_requested = True
            return None
        return create_user_input_event(data, source="web")

    async def feed(self, text: str) -> None:
        """Called by WS handler when client sends input."""
        await self._queue.put(text)


@app.websocket("/api/sessions/{session_id}/chat")
async def chat_ws(websocket: WebSocket, session_id: str):
    await websocket.accept()

    # Load agent config from DB
    session_row = db.get_session(session_id)
    agent_row = db.get_agent(session_row.agent_id)
    config = AgentConfig.from_dict(json.loads(agent_row.config_json))

    # Create I/O modules bound to this websocket
    ws_input = WebSocketInput(websocket)
    ws_output = WebSocketOutput(websocket)

    # Create and run agent
    agent = Agent(config, input_module=ws_input, output_module=ws_output)

    try:
        # Start agent and listen for WS messages
        await agent.start()

        async def ws_listener():
            try:
                while True:
                    data = await websocket.receive_json()
                    if data["type"] == "input":
                        await ws_input.feed(data["content"])
                    elif data["type"] == "stop":
                        await agent.stop()
                        break
            except WebSocketDisconnect:
                await agent.stop()

        # Run agent + listener concurrently
        await asyncio.gather(
            agent.run(),
            ws_listener(),
        )
    finally:
        await agent.stop()
        await websocket.close()
```

### Agent Config Builder

The key insight: the frontend builds a config dict (same shape as YAML),
the backend validates it and creates the Agent. No YAML files on disk.

```python
# api/agents.py

@app.post("/api/agents")
async def create_agent(body: AgentCreateRequest):
    """Create agent from config dict."""
    agent_id = str(uuid4())

    # Validate config by trying to build AgentConfig
    try:
        config = build_agent_config(body.config, body.system_prompt)
    except Exception as e:
        raise HTTPException(400, f"Invalid config: {e}")

    db.insert_agent(
        id=agent_id,
        name=body.name,
        config_json=json.dumps(body.config),
        system_prompt=body.system_prompt,
    )
    return {"id": agent_id, "name": body.name}


def build_agent_config(config_dict: dict, system_prompt: str) -> AgentConfig:
    """Build AgentConfig from web GUI config dict."""
    config_dict["system_prompt"] = system_prompt
    # No agent_path needed - prompts are inline
    return AgentConfig(
        name=config_dict.get("name", "web_agent"),
        model=config_dict.get("model", "google/gemini-3-flash-preview"),
        api_key_env=config_dict.get("api_key_env", "OPENROUTER_API_KEY"),
        base_url=config_dict.get("base_url", "https://openrouter.ai/api/v1"),
        system_prompt=system_prompt,
        tools=[ToolConfigItem(**t) for t in config_dict.get("tools", [])],
        subagents=[SubAgentConfigItem(**s) for s in config_dict.get("subagents", [])],
        termination=config_dict.get("termination"),
        # ... other fields
    )
```

### Export Format

```
agent_export.zip
├── config.yaml           # Agent config
├── prompts/
│   ├── system.md         # System prompt
│   └── plan_extra.md     # Extra prompts (if any)
└── metadata.json         # name, version, description, created_at
```

```python
@app.get("/api/agents/{agent_id}/export")
async def export_agent(agent_id: str):
    agent = db.get_agent(agent_id)
    config = json.loads(agent.config_json)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("config.yaml", yaml.dump(config))
        zf.writestr("prompts/system.md", agent.system_prompt)
        zf.writestr("metadata.json", json.dumps({
            "name": agent.name,
            "description": agent.description,
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
        }))

    return StreamingResponse(
        io.BytesIO(buf.getvalue()),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={agent.name}.zip"},
    )
```

---

## Frontend Pages

### 1. Dashboard (`/`)

Agent list with cards. Each card shows:
- Agent name + description
- Model name
- Tool count, sub-agent count
- Status indicator (stopped/running/error)
- Actions: Edit, Run, Duplicate, Export, Delete

```
┌─────────────────────────────────────────────────┐
│  KohakuTerrarium                    [+ New Agent]│
├─────────────────────────────────────────────────┤
│                                                  │
│  ┌─────────────┐  ┌─────────────┐              │
│  │ swe_agent   │  │ planner     │              │
│  │ gemini-3    │  │ gemini-3    │              │
│  │ 10 tools    │  │ 8 tools     │              │
│  │ 5 subagents │  │ 4 subagents │              │
│  │ ● Running   │  │ ○ Stopped   │              │
│  │ [Edit][Run] │  │ [Edit][Run] │              │
│  └─────────────┘  └─────────────┘              │
│                                                  │
└─────────────────────────────────────────────────┘
```

### 2. Agent Builder (`/agents/{id}/edit`)

Tabbed config editor:

```
┌─────────────────────────────────────────────────┐
│  ← Back    swe_agent    [Save] [Run] [Export]   │
├─────────────────────────────────────────────────┤
│ [General] [Tools] [Sub-Agents] [Prompt] [Adv.]  │
├─────────────────────────────────────────────────┤
│                                                  │
│  General tab:                                    │
│  ┌─────────────────────────────────────────┐    │
│  │ Name:    [swe_agent          ]          │    │
│  │ Model:   [google/gemini-3-flash ▼]      │    │
│  │ Temp:    [0.7    ]                      │    │
│  │ API Key: [OPENROUTER_API_KEY    ]       │    │
│  │ Base URL:[https://openrouter... ]       │    │
│  └─────────────────────────────────────────┘    │
│                                                  │
│  Tools tab:                                      │
│  ┌─────────────────────────────────────────┐    │
│  │ Available          Selected              │    │
│  │ ┌──────────┐      ┌──────────┐          │    │
│  │ │ http     │  →   │ ✓ bash   │          │    │
│  │ │ json_read│  ←   │ ✓ read   │          │    │
│  │ │ json_writ│      │ ✓ write  │          │    │
│  │ │          │      │ ✓ edit   │          │    │
│  │ │          │      │ ✓ think  │          │    │
│  │ └──────────┘      └──────────┘          │    │
│  └─────────────────────────────────────────┘    │
│                                                  │
│  Prompt tab:                                     │
│  ┌─────────────────────────────────────────┐    │
│  │ # System Prompt                         │    │
│  │                                         │    │
│  │ You are a software engineering agent.   │    │
│  │ ...                                     │    │
│  │ (Monaco/CodeMirror editor)              │    │
│  └─────────────────────────────────────────┘    │
│                                                  │
└─────────────────────────────────────────────────┘
```

### 3. Chat Interface (`/sessions/{id}`)

Similar layout to TUI but in browser:

```
┌─────────────────────────────────────────────────┐
│  swe_agent - Session #abc123     [Stop] [Clear] │
├─────────────────────────────────────────────────┤
│                                                  │
│  ┌─ You ─────────────────────┐  │ [Status][Log]│
│  │ Fix the auth bug           │  │              │
│  └────────────────────────────┘  │ [tool_start] │
│                                   │  bash        │
│  ── Assistant ──────────────────  │ [tool_done]  │
│  I'll analyze the auth module.    │  bash OK     │
│  Found the issue in `auth.py`:   │              │
│  ```python                        │ [subagent]   │
│  if token is None:  # was missing │  explore     │
│  ```                              │  (3 turns)   │
│  ────────────────────────────────│              │
│                                   │              │
├───────────────────────────────────┤              │
│ KohakUwUing...                    │              │
├───────────────────────────────────┤              │
│ Type a message...          [Send] │              │
└─────────────────────────────────────────────────┘
```

### 4. Export/Import

- Export: downloads `.zip` containing config.yaml + prompts/ + metadata.json
- Import: upload `.zip`, creates new agent from contents
- Supports sharing agents between users/instances

---

## Frontend Store (Pinia)

```javascript
// stores/agents.js

/** @typedef {{ id: string, name: string, description: string, config: object, status: string }} Agent */

export const useAgentStore = defineStore('agents', {
  state: () => ({
    /** @type {Agent[]} */
    agents: [],
    /** @type {Agent|null} */
    current: null,
    loading: false,
  }),

  actions: {
    async fetchAgents() {
      this.loading = true
      const { data } = await api.get('/api/agents')
      this.agents = data
      this.loading = false
    },

    async createAgent(payload) {
      const { data } = await api.post('/api/agents', payload)
      this.agents.push(data)
      return data
    },

    async updateAgent(id, payload) {
      const { data } = await api.put(`/api/agents/${id}`, payload)
      const idx = this.agents.findIndex(a => a.id === id)
      if (idx >= 0) this.agents[idx] = data
    },

    async deleteAgent(id) {
      await api.delete(`/api/agents/${id}`)
      this.agents = this.agents.filter(a => a.id !== id)
    },
  },
})
```

```javascript
// stores/chat.js

export const useChatStore = defineStore('chat', {
  state: () => ({
    /** @type {{ role: string, content: string, timestamp: string }[]} */
    messages: [],
    /** @type {{ type: string, detail: string }[]} */
    activities: [],
    /** @type {WebSocket|null} */
    ws: null,
    connected: false,
    processing: false,
  }),

  actions: {
    connect(sessionId) {
      const url = `ws://${location.host}/api/sessions/${sessionId}/chat`
      this.ws = new WebSocket(url)

      this.ws.onmessage = (event) => {
        const msg = JSON.parse(event.data)

        switch (msg.type) {
          case 'assistant_start':
            this.processing = true
            this.messages.push({ role: 'assistant', content: '', timestamp: new Date().toISOString() })
            break

          case 'text':
            // Append to current assistant message
            const last = this.messages[this.messages.length - 1]
            if (last && last.role === 'assistant') {
              last.content += msg.content
            }
            break

          case 'assistant_end':
            this.processing = false
            break

          case 'activity':
            this.activities.push({
              type: msg.activity_type,
              detail: msg.detail,
              timestamp: new Date().toISOString(),
            })
            break

          case 'error':
            this.messages.push({ role: 'error', content: msg.content, timestamp: new Date().toISOString() })
            break
        }
      }

      this.ws.onopen = () => { this.connected = true }
      this.ws.onclose = () => { this.connected = false; this.processing = false }
    },

    send(text) {
      if (!this.ws || !this.connected) return
      this.messages.push({ role: 'user', content: text, timestamp: new Date().toISOString() })
      this.ws.send(JSON.stringify({ type: 'input', content: text }))
    },

    disconnect() {
      if (this.ws) {
        this.ws.send(JSON.stringify({ type: 'stop' }))
        this.ws.close()
      }
    },
  },
})
```

---

## Project Structure

```
web/
├── backend/
│   ├── __init__.py
│   ├── app.py                 # FastAPI app + CORS + lifespan
│   ├── db.py                  # SQLite via aiosqlite
│   ├── models.py              # Pydantic request/response models
│   ├── api/
│   │   ├── agents.py          # Agent CRUD endpoints
│   │   ├── sessions.py        # Session management endpoints
│   │   ├── chat.py            # WebSocket chat handler
│   │   ├── export.py          # Export/import endpoints
│   │   └── builtins.py        # Builtins reference endpoints
│   ├── services/
│   │   ├── agent_manager.py   # Agent lifecycle (start/stop/state)
│   │   ├── ws_io.py           # WebSocketInput + WebSocketOutput
│   │   └── export.py          # Zip export/import logic
│   └── database/
│       ├── migrations.py      # Schema creation
│       └── queries.py         # DB access layer
│
├── frontend/
│   ├── index.html
│   ├── vite.config.js
│   ├── package.json
│   ├── uno.config.js
│   ├── src/
│   │   ├── main.js
│   │   ├── App.vue
│   │   ├── api/
│   │   │   └── index.js       # Axios/fetch wrapper
│   │   ├── stores/
│   │   │   ├── agents.js      # Agent CRUD store
│   │   │   ├── chat.js        # Chat + WebSocket store
│   │   │   └── ui.js          # UI state (sidebar, theme)
│   │   ├── views/
│   │   │   ├── Dashboard.vue  # Agent list
│   │   │   ├── Builder.vue    # Agent config editor
│   │   │   └── Chat.vue       # Chat interface
│   │   ├── components/
│   │   │   ├── AgentCard.vue
│   │   │   ├── ToolPicker.vue
│   │   │   ├── SubAgentPicker.vue
│   │   │   ├── PromptEditor.vue  # Monaco/CodeMirror
│   │   │   ├── ChatMessage.vue
│   │   │   ├── ActivityLog.vue
│   │   │   └── StatusPanel.vue
│   │   └── composables/
│   │       ├── useWebSocket.js
│   │       └── useMarkdown.js
│   └── public/
│
└── run.py                     # Entry point: uvicorn + serve frontend
```

---

## Key Design Decisions

### 1. No YAML files on disk for web-created agents

Web agents live in SQLite. Config is stored as JSON, system prompt as text.
The `Agent` class already supports `Agent(config)` with a programmatic config.
Export creates YAML files; import reads them.

### 2. WebSocket for chat, not polling

Real-time streaming requires WS. Each session gets one WS connection.
The WS handler creates `WebSocketInput` + `WebSocketOutput` and passes
them to `Agent(config, input_module=ws_input, output_module=ws_output)`.

### 3. Session = one running agent instance

A session maps to a `Session` in the registry (shared channels/scratchpad).
Multiple sessions can run the same agent config (different conversations).
Sessions persist in DB for history; runtime state is in-memory.

### 4. Activity stream via on_activity hook

The `on_activity` hook we just built feeds tool/subagent/command events
to `WebSocketOutput`, which sends them as `{ type: "activity" }` WS messages.
Frontend displays them in the side panel.

### 5. Markdown rendering in browser

Use `markdown-it` + `highlight.js` for rendering assistant output.
The assistant message accumulates via `text` WS events, re-renders
on each chunk (or debounced for performance).

### 6. Agent export as portable zip

The zip contains everything needed to run the agent standalone:
config.yaml + prompts/ + metadata.json. Can be imported into
another KohakuTerrarium instance or run via CLI.

---

## Implementation Phases

### Phase 1: Backend Core
- FastAPI skeleton with CORS
- SQLite schema + aiosqlite
- Agent CRUD endpoints
- Builtins reference endpoints

### Phase 2: WebSocket Chat
- WebSocketInput / WebSocketOutput
- Chat WS endpoint
- Session management (start/stop)
- Message persistence

### Phase 3: Frontend Shell
- Vite + Vue3 + Element Plus setup
- Router (Dashboard, Builder, Chat)
- Pinia stores (agents, chat)
- API client

### Phase 4: Dashboard + Builder
- Agent list with cards
- Tool/SubAgent picker (drag-drop or transfer list)
- Prompt editor (CodeMirror or Monaco)
- Config validation

### Phase 5: Chat Interface
- WebSocket connection
- Message display (markdown rendering)
- Activity side panel
- Processing indicator

### Phase 6: Export/Import
- Zip export endpoint
- Zip import endpoint
- Download/upload UI

---

## Open Questions

1. **Auth**: Multi-user? API keys per user? Or single-user local tool?
2. **Agent persistence**: Keep running agents alive across server restarts?
3. **File access**: Web agents can't access local filesystem. Sandbox? Working dir?
4. **Custom modules**: Can web-created agents use custom tools/inputs/outputs? Or builtins only?
5. **Concurrent sessions**: Limit per agent? Per server?
