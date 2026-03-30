# Serving Layer

The serving layer (`src/kohakuterrarium/serving/`) provides a transport-agnostic Python API for hosting and managing agents and terrariums. It sits between the core framework and any interface layer (HTTP API, CLI, Web UI, Gradio).

## Key Difference: Serving vs HTTP API

| Layer | Location | Purpose |
|-------|----------|---------|
| **Serving** | `src/kohakuterrarium/serving/` | Python API for runtime management. Part of the core package. |
| **HTTP API** | `apps/api/` | FastAPI application that exposes the serving layer over REST + WebSocket. An application, not part of the library. |

The serving layer is the single source of truth for all runtime operations. The HTTP API (and any future interface) delegates to it.

## KohakuManager

`KohakuManager` is the central service manager. All runtime operations go through it.

```python
from kohakuterrarium.serving import KohakuManager

manager = KohakuManager()
```

### Standalone Agent Operations

```python
# Create and start an agent from a config path
agent_id = await manager.create_agent(config_path="agents/swe_agent")

# Get status
status = manager.get_agent_status(agent_id)
# {"agent_id": "agent_abc123", "name": "swe_agent", "running": True, "tools": [...], ...}

# Stream a chat response
async for chunk in manager.chat(agent_id, "Fix the bug in main.py"):
    print(chunk, end="")

# List all agents
agents = manager.list_agents()

# Stop
await manager.stop_agent(agent_id)
```

### Terrarium Operations

```python
# Create and start a terrarium
tid = await manager.create_terrarium(config_path="agents/novel_terrarium")

# Get status (creatures, channels, running state)
status = manager.get_terrarium_status(tid)

# Send a message to a channel
msg_id = await manager.send_to_channel(tid, "ideas", "Write about space", sender="human")

# Hot-plug: add a creature at runtime
from kohakuterrarium.terrarium.config import CreatureConfig

config = CreatureConfig(
    name="editor",
    config_path="agents/editor_agent",
    listen_channels=["draft"],
    send_channels=["feedback"],
)
await manager.add_creature(tid, config)

# Hot-plug: add a channel and wire it
await manager.add_channel(tid, "alerts", "broadcast", "System alerts")
await manager.wire_channel(tid, "editor", "alerts", "listen")

# Stream channel events (transport-agnostic async iterator)
async for event in manager.stream_channel_events(tid, channels=["ideas"]):
    print(f"[{event.channel}] {event.sender}: {event.content}")

# Stop
await manager.stop_terrarium(tid)

# Shutdown everything
await manager.shutdown()
```

## AgentSession

`AgentSession` wraps an `Agent` with streaming chat. It manages the output queue so callers get an async iterator of text chunks.

```python
from kohakuterrarium.serving import AgentSession

# Create from config path (starts the agent automatically)
session = await AgentSession.from_path("agents/swe_agent")

# Stream chat
async for chunk in session.chat("What files are in this directory?"):
    print(chunk, end="")

# Check status
status = session.get_status()

# Stop
await session.stop()
```

### How Streaming Works

When `chat(message)` is called:

1. Any stale output in the queue is cleared
2. `agent.inject_input(message)` runs as a background task
3. Output chunks arrive via the agent's output handler callback
4. The caller yields chunks as they arrive
5. After injection completes, remaining output is drained

## Event Types

The serving layer defines two transport-agnostic event dataclasses:

### `ChannelEvent`

Represents a channel message observed in a terrarium.

| Field | Type | Description |
|-------|------|-------------|
| `terrarium_id` | `str` | Which terrarium |
| `channel` | `str` | Channel name |
| `sender` | `str` | Who sent it |
| `content` | `str` | Message body |
| `message_id` | `str` | Unique ID |
| `timestamp` | `datetime` | When created |
| `metadata` | `dict` | Extra data |

### `OutputEvent`

Represents an agent output event (text chunk, tool activity).

| Field | Type | Description |
|-------|------|-------------|
| `agent_id` | `str` | Which agent |
| `event_type` | `str` | `"text"`, `"tool_start"`, `"tool_done"`, `"tool_error"`, etc. |
| `content` | `str` | Event content |
| `timestamp` | `datetime` | When created |
| `metadata` | `dict` | Extra data |
