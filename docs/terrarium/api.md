# API Reference

This document covers the three main interfaces for programmatic interaction with a running terrarium: `TerrariumAPI` for operations, `ChannelObserver` for monitoring channel traffic, and `OutputLogCapture` for creature output history.

All three are accessed through the `TerrariumRuntime` instance. See [Architecture](architecture.md) for how these layers fit together and [Setup Guide](setup.md) for usage walkthroughs.

## TerrariumAPI

`TerrariumAPI` (`terrarium/api.py`) wraps the runtime with convenience methods for channels, creatures, and lifecycle management. Access it via the `runtime.api` property (lazily created on first access).

```python
from kohakuterrarium.terrarium import TerrariumRuntime, load_terrarium_config

config = load_terrarium_config("agents/my_terrarium/")
runtime = TerrariumRuntime(config)
await runtime.start()

api = runtime.api
```

### Channel Operations

#### `list_channels() -> list[dict[str, str]]`

Returns all channels with name, type, and description.

```python
channels = await api.list_channels()
# [
#     {"name": "findings", "type": "queue", "description": "Research findings"},
#     {"name": "team_chat", "type": "broadcast", "description": "Status updates"},
# ]
```

Returns an empty list if the terrarium has not been started.

#### `channel_info(name) -> dict[str, Any] | None`

Returns detailed info for a single channel, including queue size and subscriber count (broadcast only).

```python
info = await api.channel_info("team_chat")
# {
#     "name": "team_chat",
#     "type": "broadcast",
#     "description": "Status updates",
#     "qsize": 0,
#     "subscriber_count": 3,
# }
```

Returns `None` if the channel does not exist.

#### `send_to_channel(name, content, sender, metadata) -> str`

Injects a message into a channel. Works for both queue and broadcast channels. Returns the generated `message_id`.

```python
msg_id = await api.send_to_channel(
    "findings",
    "Here are the results of the external analysis.",
    sender="human",
    metadata={"source": "manual"},
)
# "msg_a1b2c3d4e5f6"
```

Parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | required | Target channel name |
| `content` | `str` | required | Message body |
| `sender` | `str` | `"human"` | Sender identifier shown to receiving creatures |
| `metadata` | `dict[str, Any] \| None` | `None` | Arbitrary key-value metadata attached to the message |

Raises `ValueError` if the terrarium is not running or the channel is not found. The error message includes a list of available channels.

If a `ChannelObserver` exists on the runtime, the message is automatically recorded in the observer.

### Creature Operations

#### `list_creatures() -> list[dict[str, Any]]`

Returns all creatures with their name, running status, and channel assignments.

```python
creatures = await api.list_creatures()
# [
#     {
#         "name": "researcher",
#         "running": True,
#         "listen_channels": [],
#         "send_channels": ["findings"],
#     },
#     {
#         "name": "summarizer",
#         "running": True,
#         "listen_channels": ["findings"],
#         "send_channels": [],
#     },
# ]
```

#### `get_creature_status(name) -> dict[str, Any] | None`

Returns detailed status for one creature. Returns `None` if the creature does not exist.

```python
status = await api.get_creature_status("researcher")
# {"name": "researcher", "running": True, "listen_channels": [], "send_channels": ["findings"]}
```

#### `stop_creature(name) -> bool`

Stops a specific creature by cancelling its task and calling `agent.stop()`. Returns `True` on success, `False` if the creature is not found.

```python
stopped = await api.stop_creature("researcher")
```

#### `start_creature(name) -> bool`

Restarts a stopped creature. Calls `agent.start()` and creates a new run task. Returns `True` on success (or if already running), `False` if not found.

```python
started = await api.start_creature("researcher")
```

### Terrarium Operations

#### `get_status() -> dict[str, Any]`

Returns the full terrarium status dict (delegates to `runtime.get_status()`). See [Architecture - Status Monitoring](architecture.md#status-monitoring) for the format.

```python
status = api.get_status()
# {"name": "research_pipeline", "running": True, "creatures": {...}, "channels": [...]}
```

#### `is_running -> bool`

Property that returns whether the terrarium runtime is currently running.

```python
if api.is_running:
    print("Terrarium is active")
```

## ChannelObserver

`ChannelObserver` (`terrarium/observer.py`) provides non-destructive visibility into channel traffic. Access it via `runtime.observer` (lazily created; requires the terrarium to be started).

```python
observer = runtime.observer
```

### How observation works

- **Broadcast channels** - The observer subscribes as a silent participant with subscriber ID `_observer_<channel_name>`. A background task receives copies of every message.
- **Queue channels** - Non-destructive peeking is not possible for queues. Queue messages are only recorded when sent via `TerrariumAPI.send_to_channel()`, which calls `observer.record()` internally.

### `observe(channel_name) -> None`

Start observing a channel. For broadcast channels, this subscribes and starts a background receive loop. For queue channels, this is a no-op (messages are recorded via the API layer).

```python
await observer.observe("team_chat")
await observer.observe("findings")
```

Calling `observe()` on an already-observed channel is safe and does nothing.

### `on_message(callback) -> None`

Register a callback that fires for every observed message. The callback receives an `ObservedMessage` object.

```python
def print_msg(msg):
    print(f"[{msg.timestamp:%H:%M:%S}] [{msg.channel}] {msg.sender}: {msg.content}")

observer.on_message(print_msg)
```

Multiple callbacks can be registered. They are called synchronously in registration order. Exceptions in callbacks are caught and logged.

### `record(channel_name, msg) -> None`

Manually record a `ChannelMessage`. This is called internally by `TerrariumAPI.send_to_channel()` for queue channels. You typically do not call this directly.

```python
observer.record("findings", channel_message)
```

### `get_messages(channel, last_n) -> list[ObservedMessage]`

Retrieve recent observed messages, optionally filtered by channel name.

```python
# All recent messages
recent = observer.get_messages(last_n=20)

# Messages from a specific channel
chat_msgs = observer.get_messages(channel="team_chat", last_n=10)
```

Parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `channel` | `str \| None` | `None` | Filter by channel name. `None` returns all channels. |
| `last_n` | `int` | `20` | Maximum number of messages to return |

### `stop() -> None`

Stop all observation loops and clean up broadcast subscriptions. Call this before shutting down the terrarium.

```python
await observer.stop()
```

### ObservedMessage

Each observed message is an `ObservedMessage` dataclass:

```python
@dataclass
class ObservedMessage:
    channel: str              # Channel the message was observed on
    sender: str               # Creature or entity that sent the message
    content: str              # Message body (stringified if originally a dict)
    message_id: str           # Unique message ID (msg_xxxxxxxxxxxx)
    timestamp: datetime       # When the message was created
    metadata: dict[str, Any]  # Arbitrary metadata from the original message
```

### Configuration

The observer keeps a bounded history buffer. The `max_history` parameter controls the cap (default 1000):

```python
from kohakuterrarium.terrarium.observer import ChannelObserver

observer = ChannelObserver(session, max_history=500)
```

## OutputLogCapture

`OutputLogCapture` (`terrarium/output_log.py`) is a tee wrapper that records a creature's output into a ring buffer. It implements the full `OutputModule` protocol, so it can be swapped in transparently.

### Enabling output logs

Set `output_log: true` on a creature in the terrarium config:

```yaml
creatures:
  - name: researcher
    config: ./creatures/researcher/
    output_log: true
    output_log_size: 200
    channels:
      can_send: [findings]
```

The runtime wraps the creature's default output module during setup. All output continues to flow to the original module; the capture layer is invisible to the creature.

### Accessing the log

The log is available through the `CreatureHandle`:

```python
handle = runtime._creatures["researcher"]

# Via convenience methods on CreatureHandle
entries = handle.get_log_entries(last_n=10)
text = handle.get_log_text(last_n=5)

# Or directly via the OutputLogCapture instance
capture = handle.output_log
if capture is not None:
    entries = capture.get_entries(last_n=10, entry_type="text")
    full_text = capture.get_text(last_n=5)
    print(f"Log has {capture.entry_count} entries")
```

### `get_entries(last_n, entry_type) -> list[LogEntry]`

Get recent log entries, optionally filtered by entry type.

```python
# All entries
all_entries = capture.get_entries(last_n=20)

# Only text entries
text_entries = capture.get_entries(last_n=10, entry_type="text")

# Only activity entries
activities = capture.get_entries(last_n=10, entry_type="activity")
```

### `get_text(last_n) -> str`

Get recent text output concatenated into a single string. Includes both `text` and `stream_flush` entries but excludes `activity` entries.

```python
output = capture.get_text(last_n=5)
print(output)
```

### `clear() -> None`

Empty the log buffer and discard any pending stream data.

```python
capture.clear()
```

### `entry_count -> int`

Property returning the current number of entries in the ring buffer.

### LogEntry

Each log entry is a `LogEntry` dataclass:

```python
@dataclass
class LogEntry:
    timestamp: datetime           # When the entry was recorded
    content: str                  # The captured content
    entry_type: str = "text"      # "text", "stream_flush", or "activity"
    metadata: dict[str, Any]      # Extra data (e.g. activity_type for activity entries)
```

The `preview(max_len)` method returns a truncated version of the content:

```python
entry.preview(80)  # "First 80 characters of content..."
```

### Entry types

| Type | Source | When recorded |
|------|--------|---------------|
| `text` | `write()` | A complete text block is written to output |
| `stream_flush` | `flush()` | Accumulated streaming chunks are flushed as one entry |
| `activity` | `on_activity()` | Tool start/done/error notifications. The `activity_type` is stored in `metadata["activity_type"]`. |

### Ring buffer behavior

The buffer is a `collections.deque` with a fixed `maxlen`. When full, the oldest entries are discarded automatically. The size is set by `output_log_size` in the terrarium config (default 100).

## Hot-Plug API

Add or remove creatures, channels, and triggers at runtime without restarting the terrarium. The hot-plug API operates at two levels: individual agents and the terrarium runtime.

### Agent-Level

These methods are on the `Agent` class and can be called while the agent is running.

#### `agent.add_trigger(trigger) -> None`

Add and start a trigger on a running agent. The trigger begins listening and firing events immediately.

```python
from kohakuterrarium.modules.trigger.channel import ChannelTrigger

trigger = ChannelTrigger(
    channel_name="alerts",
    subscriber_id="my_agent",
    session=agent.session,
)
await agent.add_trigger(trigger)
```

The trigger is appended to `agent._triggers` and a background task is created to run its event loop.

#### `agent.remove_trigger(trigger) -> None`

Stop and remove a trigger from a running agent. The trigger's background task is cancelled and the trigger is stopped.

```python
await agent.remove_trigger(trigger)
# trigger.is_running is now False
```

If the trigger is not found in the agent's trigger list, this is a no-op.

#### `agent.update_system_prompt(content, replace=False) -> None`

Update the system prompt of a running agent. By default, new content is appended. Pass `replace=True` to replace the entire prompt.

```python
# Append a new section
agent.update_system_prompt("## New Instructions\nAlways respond in JSON.")

# Replace the whole prompt
agent.update_system_prompt("You are a JSON-only agent.", replace=True)
```

The change takes effect on the next LLM call. Previous conversation history is not affected.

#### `agent.get_system_prompt() -> str`

Read the current system prompt text.

```python
current = agent.get_system_prompt()
print(len(current), "characters")
```

### Terrarium-Level

These methods are on the `TerrariumRuntime` class and operate on the running terrarium.

#### `runtime.add_creature(config) -> None`

Add and start a new creature in the running terrarium. The creature is fully wired (channels, triggers, system prompt injection) before its agent starts.

```python
from kohakuterrarium.terrarium.config import CreatureConfig

new_creature = CreatureConfig(
    name="reviewer",
    config_path="agents/swe_agent",
    listen_channels=["review_requests"],
    send_channels=["review_results"],
)
await runtime.add_creature(new_creature)
```

Raises `RuntimeError` if the terrarium is not running or a creature with the same name already exists.

#### `runtime.remove_creature(name) -> bool`

Stop and remove a creature from the running terrarium. Returns `True` if the creature was found and removed, `False` if no creature with that name exists.

```python
removed = await runtime.remove_creature("reviewer")
if removed:
    print("Reviewer removed")
```

The creature's agent is stopped and its entry is removed from the runtime's creature registry.

#### `runtime.add_channel(name, type, description) -> None`

Create a new channel in the shared session's channel registry.

```python
await runtime.add_channel("alerts", "broadcast", "System-wide alerts")
```

The channel is immediately available for wiring and message passing. Existing creatures are not automatically connected to it; use `wire_channel` to set up connections.

#### `runtime.wire_channel(creature, channel, direction) -> None`

Connect a creature to a channel. The `direction` parameter controls the connection type:

- `"listen"` - adds a `ChannelTrigger` to the creature so it receives messages from the channel.
- `"send"` - adds the channel to the creature's `send_channels` list so it can send messages.

```python
# Make the reviewer listen for review requests
await runtime.wire_channel("reviewer", "review_requests", "listen")

# Let the reviewer send results
await runtime.wire_channel("reviewer", "review_results", "send")
```

Raises `ValueError` (or `KeyError`) if the creature does not exist.

## HTTP API (`apps/api/`)

The HTTP API is a FastAPI application that exposes the `KohakuManager` (from `serving/`) over REST and WebSocket. It is an application layer, not part of the core library. It lives in `apps/api/` and depends on `kohakuterrarium.serving`.

### Starting the Server

```bash
python apps/api/main.py
# Server runs on http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

The server uses uvicorn with auto-reload enabled by default. On shutdown, the lifespan handler calls `manager.shutdown()` to stop all running agents and terrariums.

### REST Endpoints

#### Terrariums

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/terrariums` | Create and start a terrarium from a config path |
| `GET` | `/api/terrariums` | List all running terrariums |
| `GET` | `/api/terrariums/{id}` | Get status of a specific terrarium |
| `DELETE` | `/api/terrariums/{id}` | Stop and cleanup a terrarium |
| `POST` | `/api/terrariums/{id}/channels` | Add a channel to a running terrarium |

#### Creatures

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/terrariums/{id}/creatures` | List creatures in a terrarium |
| `POST` | `/api/terrariums/{id}/creatures` | Add a creature (hot-plug) |
| `DELETE` | `/api/terrariums/{id}/creatures/{name}` | Remove a creature |
| `POST` | `/api/terrariums/{id}/creatures/{name}/wire` | Wire creature to a channel |

#### Channels

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/terrariums/{id}/channels` | List all channels |
| `POST` | `/api/terrariums/{id}/channels/{name}/send` | Send a message to a channel |

#### Standalone Agents

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/agents` | Create and start a standalone agent |
| `GET` | `/api/agents` | List all running agents |
| `GET` | `/api/agents/{id}` | Get agent status |
| `DELETE` | `/api/agents/{id}` | Stop an agent |
| `POST` | `/api/agents/{id}/chat` | Non-streaming chat (returns full response) |

### WebSocket Streams

#### `ws://host/ws/terrariums/{id}/channels`

Streams all channel messages from a terrarium in real-time. Each message is a JSON object:

```json
{
    "type": "channel_message",
    "channel": "ideas",
    "sender": "brainstorm",
    "content": "Here is a new idea...",
    "message_id": "msg_a1b2c3d4e5f6",
    "timestamp": "2026-03-30T14:22:01.123456"
}
```

#### `ws://host/ws/agents/{id}/chat`

Bidirectional streaming chat with a standalone agent. Send a JSON message:

```json
{"message": "Create a hello world script"}
```

Receive streaming chunks:

```json
{"type": "text", "content": "I'll create"}
{"type": "text", "content": " the script..."}
{"type": "done"}
```

### Architecture Note

The HTTP API is a thin transport layer over the `serving` module. All business logic lives in `KohakuManager` and `AgentSession`, which are transport-agnostic. See [Serving Layer](serving.md) for the Python API that the HTTP layer delegates to.
