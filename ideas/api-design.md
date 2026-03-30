# Core Service API Design

## Principle

The core library provides a **service API** for hosting and managing agents and terrariums. It handles all runtime operations: creation, lifecycle, interaction, observation, hot-plug.

Everything above (Web UI, TUI, Gradio, CLI, Claude Code) is an **application** that consumes this API. The API has no knowledge of HTTP, WebSocket, HTML, or any specific transport.

```
+------------------+  +------------------+  +------------------+
|   Web App        |  |   Gradio App     |  |   TUI / CLI      |
|   (FastAPI+Vue)  |  |   (minimal)      |  |   (terminal)     |
+--------+---------+  +--------+---------+  +--------+---------+
         |                     |                     |
         v                     v                     v
+--------------------------------------------------------+
|              KohakuManager (core lib API)               |
|                                                         |
|  Standalone agents:  create, stop, chat, status, list   |
|  Terrariums:         create, stop, hot-plug, observe    |
|  Event streams:      async iterators (transport-agnostic)|
+--------------------------------------------------------+
         |                     |
         v                     v
+-------------------+  +-------------------+
|  Agent instances  |  | TerrariumRuntime  |
|  (LLM, tools,    |  | (creatures,       |
|   sub-agents)     |  |  channels, wiring)|
+-------------------+  +-------------------+
```

## API Surface

### `KohakuManager`

Single entry point for all runtime operations.

```python
class KohakuManager:
    """Unified service manager for agents and terrariums.

    All runtime operations go through here. Transport-agnostic.
    Used by any interface: CLI, TUI, Web, Gradio, MCP, etc.
    """

    # === Standalone Agent Serving ===

    async def create_agent(
        self,
        config_path: str | None = None,
        config: AgentConfig | None = None,
    ) -> str:
        """Create and start a standalone agent. Returns agent_id."""

    async def stop_agent(self, agent_id: str) -> None:
        """Stop and cleanup an agent."""

    async def chat(
        self, agent_id: str, message: str
    ) -> AsyncIterator[str]:
        """Send a message and stream the response. Async iterator of text chunks."""

    def get_agent_status(self, agent_id: str) -> dict:
        """Get agent status (running, tools, subagents, turn count)."""

    def list_agents(self) -> list[dict]:
        """List all running agents with basic status."""

    # === Terrarium Serving ===

    async def create_terrarium(
        self,
        config_path: str | None = None,
        config: TerrariumConfig | None = None,
    ) -> str:
        """Create and start a terrarium. Returns terrarium_id."""

    async def stop_terrarium(self, terrarium_id: str) -> None:
        """Stop all creatures and cleanup."""

    def get_terrarium(self, terrarium_id: str) -> TerrariumRuntime:
        """Get the runtime instance (for direct API access)."""

    def get_terrarium_status(self, terrarium_id: str) -> dict:
        """Get terrarium status (creatures, channels, running state)."""

    def list_terrariums(self) -> list[dict]:
        """List all running terrariums."""

    # === Terrarium Hot-Plug (delegates to runtime) ===

    async def add_creature(
        self, terrarium_id: str, config: CreatureConfig
    ) -> str:
        """Add a creature to a running terrarium."""

    async def remove_creature(
        self, terrarium_id: str, name: str
    ) -> bool:
        """Remove a creature from a running terrarium."""

    async def add_channel(
        self, terrarium_id: str, name: str,
        channel_type: str = "queue", description: str = "",
    ) -> None:
        """Add a channel to a running terrarium."""

    async def wire_channel(
        self, terrarium_id: str, creature: str,
        channel: str, direction: str,
    ) -> None:
        """Wire a creature to a channel (listen or send)."""

    async def send_to_channel(
        self, terrarium_id: str, channel: str,
        content: str, sender: str = "human",
    ) -> str:
        """Send a message to a terrarium channel. Returns message_id."""

    # === Event Streams (async iterators) ===

    async def stream_channel_events(
        self, terrarium_id: str,
        channels: list[str] | None = None,
    ) -> AsyncIterator[ChannelEvent]:
        """Stream channel messages from a terrarium.

        If channels is None, stream all channels.
        Async iterator - consumer pulls at their own pace.
        """

    async def stream_agent_output(
        self, agent_id: str,
    ) -> AsyncIterator[OutputEvent]:
        """Stream an agent's output (text, tool activity)."""
```

### `AgentSession`

Manages a standalone agent's chat lifecycle:

```python
class AgentSession:
    """A running standalone agent with chat interface."""

    agent_id: str
    agent: Agent

    async def chat(self, message: str) -> AsyncIterator[str]:
        """Inject input and stream the response."""

    def get_status(self) -> dict:
        """Get agent status."""
```

### Event Types

```python
@dataclass
class ChannelEvent:
    """A channel message event."""
    terrarium_id: str
    channel: str
    sender: str
    content: str
    message_id: str
    timestamp: datetime

@dataclass
class OutputEvent:
    """An agent output event."""
    agent_id: str
    event_type: str  # "text", "tool_start", "tool_done", "tool_error"
    content: str
    timestamp: datetime
```

## Module Structure

```
src/kohakuterrarium/serving/
  __init__.py           # Exports KohakuManager, AgentSession, event types
  manager.py            # KohakuManager (~200 lines)
  agent_session.py      # AgentSession (~100 lines)
  events.py             # ChannelEvent, OutputEvent (~40 lines)
```

Small, focused files. Total ~350 lines.

## What Applications Do

Applications bridge the core API to a specific transport/UI:

| App | Transport | What it adds |
|-----|-----------|-------------|
| CLI | Terminal stdin/stdout | Argument parsing, formatted output |
| TUI | Terminal (textual) | Rich terminal UI, keybindings |
| Gradio | HTTP (auto-generated) | Quick chat UI, status panels |
| Web (FastAPI) | HTTP + WebSocket | REST endpoints, WS streams, CORS |
| Web (Vue) | Browser | Visual topology, channel stream, chat |

Each app is a thin wrapper:

```python
# Gradio app (~100 lines)
manager = KohakuManager()
agent_id = await manager.create_agent("agents/swe_agent")

async def chat_fn(message, history):
    async for chunk in manager.chat(agent_id, message):
        yield chunk

gr.ChatInterface(chat_fn).launch()
```

```python
# FastAPI app (~50 lines per route file)
manager = KohakuManager()

@app.post("/api/terrariums")
async def create_terrarium(req: CreateRequest):
    tid = await manager.create_terrarium(config_path=req.path)
    return {"id": tid}

@app.websocket("/ws/terrariums/{tid}/channels")
async def channel_stream(ws: WebSocket, tid: str):
    await ws.accept()
    async for event in manager.stream_channel_events(tid):
        await ws.send_json(event.to_dict())
```

## Implementation Order

1. Event types (`events.py`) - dataclasses, no dependencies
2. AgentSession (`agent_session.py`) - wraps Agent with chat streaming
3. KohakuManager (`manager.py`) - unified entry point
4. Update existing CLI to use KohakuManager
5. Gradio app (quick win, proves the API works)
