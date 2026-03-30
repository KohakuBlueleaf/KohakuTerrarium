# Terrarium Architecture

## Two-Level Composition

Agent systems need two fundamentally different coordination mechanisms:

1. **Vertical (creature-internal)**: A main controller delegates to sub-agents for task decomposition. Hierarchical, tightly coupled, shared context, limited authority. This is the standard "main-sub agent" pattern handled by the existing Agent/SubAgent system.

2. **Horizontal (terrarium-level)**: Independent agents collaborate as peers. Flat, loosely coupled, opaque boundaries, explicit messaging. No agent is privileged.

Most multi-agent frameworks fail because they use one mechanism for both. KohakuTerrarium separates them cleanly:

- **Creature** = a self-contained agent with its own controller, sub-agents, tools, and memory. Handles the vertical.
- **Terrarium** = the environment where multiple creatures are placed together and wired up via channels. Handles the horizontal.

The boundary is clean: **a creature does not know it is in a terrarium.**

### Software Architecture Analogy

| Agent Concept | Software Analogy | Role |
|---------------|-----------------|------|
| Creature | Microservice | Self-contained, private internals, well-defined external interface |
| Terrarium | Service mesh | Routing, lifecycle, observability - no business logic |
| Sub-agents | Internal components | Private to the creature, invisible from outside |
| Channels | Message queues | Explicit, typed communication between creatures |

## Architecture Diagram

```
+-------------+     +-------------------+     +-----------------+
|  Creatures  |     |  Terrarium Layer  |     | Human Interface |
|  (opaque)   |<--->|  (wiring)         |<--->| (pluggable)     |
|             |     |                   |     |                 |
| - architect |     | - channel system  |     | - CLI           |
| - swe_agent |     | - trigger wiring  |     | - MCP server    |
| - reviewer  |     | - lifecycle mgmt  |     | - Web UI        |
| - any other |     | - prompt injection|     | - none (auto)   |
|             |     | - API layer       |     |                 |
|             |     | - observer        |     |                 |
|             |     | - output log      |     |                 |
+-------------+     +-------------------+     +-----------------+
```

## Runtime Components

### TerrariumConfig (`terrarium/config.py`)

Loads and validates terrarium YAML configuration. The config parser:

- Finds `terrarium.yaml` or `terrarium.yml` in the given path
- Resolves creature `config` paths relative to the terrarium config directory
- Parses channel declarations (name, type, description)
- Produces a `TerrariumConfig` containing `CreatureConfig` and `ChannelConfig` lists

Key data classes:

```python
@dataclass
class TerrariumConfig:
    name: str
    creatures: list[CreatureConfig]
    channels: list[ChannelConfig]

@dataclass
class CreatureConfig:
    name: str
    config_path: str              # Resolved absolute path to agent config folder
    listen_channels: list[str]
    send_channels: list[str]
    output_log: bool = False
    output_log_size: int = 100

@dataclass
class ChannelConfig:
    name: str
    channel_type: str = "queue"   # "queue" or "broadcast"
    description: str = ""
```

### TerrariumRuntime (`terrarium/runtime.py`)

The runtime orchestrator. It performs the following on `start()`:

1. **Create shared session** - All creatures share one `Session` with a single `ChannelRegistry`, so channels are visible across creatures.
2. **Pre-create declared channels** - Each channel from the config is created in the shared registry with the correct type and description.
3. **Build creatures** - For each creature:
   - Load the standalone agent config via `load_agent_config()`
   - Point the agent at the shared session key
   - Override input to `NoneInput` (creatures receive work via channel triggers, not stdin)
   - Inject `ChannelTrigger` instances for each listen channel
   - Inject channel topology into the system prompt
4. **Start all creature agents** - Call `agent.start()` on each creature.

On `run()`, each creature runs its event loop as a concurrent `asyncio.Task`. The runtime waits for all tasks to finish (or handles cancellation).

### CreatureHandle (`terrarium/creature.py`)

A lightweight wrapper around an `Agent` instance that tracks terrarium metadata:

```python
@dataclass
class CreatureHandle:
    name: str
    agent: Agent
    config: CreatureConfig
    listen_channels: list[str]
    send_channels: list[str]

    @property
    def is_running(self) -> bool: ...
```

## Communication Model

### Explicit Messaging

Communication between creatures is always **explicit**. The creature's LLM decides what to send via the `send_message` tool. The terrarium never silently pipes creature output into channels. This preserves the opacity principle - internal reasoning stays private.

### Receiving Messages

The terrarium appends `ChannelTrigger` instances to each creature's trigger list for its listen channels. When a message arrives on a channel, the trigger creates a `TriggerEvent(type=CHANNEL_MESSAGE)` - the same event system used for all other triggers (timers, user input, idle detection). The creature processes the event through its normal controller loop.

### Sending Messages

The creature calls the `send_message` tool explicitly, specifying the target channel and message content. See [Channel System](channels.md) for tool details.

### Flow

```
Creature A                    Channel                    Creature B
    |                            |                           |
    |-- send_message(ch, msg) -->|                           |
    |                            |-- ChannelTrigger fires -->|
    |                            |                           |
    |                            |   TriggerEvent(           |
    |                            |     type=CHANNEL_MESSAGE, |
    |                            |     content=msg,          |
    |                            |     context={sender: A})  |
    |                            |                           |
    |                            |          B processes event|
    |                            |          via controller   |
```

## System Prompt Injection

The runtime builds a "Terrarium Channels" section and appends it to each creature's system prompt. This section lists only the channels relevant to that creature:

- Channels the creature listens on
- Channels the creature can send to
- All broadcast channels (visible to everyone)

Each channel entry includes its type, the creature's role (listen/send), and the channel description. The section also includes usage hints for `send_message` and a note that listen channel messages arrive automatically.

Example injected prompt section:

```
## Terrarium Channels

You are part of a multi-agent team. Use channels to communicate with other agents.

- `feedback` [queue] (listen) - Feedback from writer back to brainstorm
- `ideas` [queue] (send) - Raw ideas from brainstorm to planner
- `team_chat` [broadcast] (send) - Team-wide status updates

Send messages with: `[/send_message]@@channel=<name>\nYour message[send_message/]`
Messages on your listen channels arrive automatically as events.
```

## Lifecycle Management

### Startup

1. `TerrariumRuntime.start()` initializes the shared session, channels, and creatures.
2. `TerrariumRuntime.run()` fires each creature's `startup_trigger` (if configured) and runs all creature event loops as concurrent tasks.

### Running

Each creature runs its own event loop (`_run_creature`), which:
- Waits for input events (from triggers, including channel triggers)
- Processes each event through the agent's controller
- Continues until the agent stops (termination conditions, exit request, or cancellation)

### Shutdown

`TerrariumRuntime.stop()`:
1. Cancels all running creature tasks
2. Waits for cancellation with `asyncio.gather(..., return_exceptions=True)`
3. Calls `agent.stop()` on each creature
4. Logs any errors during shutdown

### Status Monitoring

`TerrariumRuntime.get_status()` returns a dict with:

```python
{
    "name": "novel_writer",
    "running": True,
    "creatures": {
        "brainstorm": {
            "running": True,
            "listen_channels": ["feedback"],
            "send_channels": ["ideas", "team_chat"],
        },
        # ...
    },
    "channels": [
        {"name": "ideas", "type": "queue", "description": "..."},
        # ...
    ],
}
```

## Coordination Topologies

Different wiring topologies emerge from channel configuration:

### Pipeline

```
brainstorm --ideas(queue)--> planner --outline(queue)--> writer
```

### Hub-and-Spoke

```
architect <--tasks(queue)----> swe_agent_1
          <--tasks(queue)----> swe_agent_2
          <--review_req(queue)--> reviewer
```

### Group Chat

```
agent_a <--discussion(broadcast)--> agent_b <--discussion(broadcast)--> agent_c
```

### Hybrid

Mix any of the above. Topology is determined entirely by the channel configuration, not by code changes.

## API Layer

The `TerrariumAPI` class (`terrarium/api.py`) wraps `TerrariumRuntime` with convenient methods for external interaction. It is accessed via the `runtime.api` property, which lazily creates the instance on first use.

The API provides three groups of operations:

- **Channel operations** - `list_channels()`, `channel_info(name)`, `send_to_channel(name, content, sender, metadata)`. These allow external code (scripts, web servers, CLI tools) to inspect and inject messages into the running terrarium.
- **Creature operations** - `list_creatures()`, `get_creature_status(name)`, `stop_creature(name)`, `start_creature(name)`. These support runtime lifecycle management of individual creatures.
- **Terrarium operations** - `get_status()`, `is_running`. High-level status queries.

The API integrates with the observer: when `send_to_channel()` is called, the message is recorded in the observer automatically, ensuring queue channel traffic is visible even though queue channels cannot be observed non-destructively.

See [API Reference](api.md) for full method signatures and examples.

## Observer Pattern

The `ChannelObserver` class (`terrarium/observer.py`) provides non-destructive visibility into channel traffic. It is accessed via the `runtime.observer` property (lazily created after the terrarium is started).

Observation works differently depending on channel type:

- **Broadcast channels** - The observer subscribes as a silent participant using a dedicated subscriber ID (`_observer_<channel_name>`). A background `asyncio.Task` loops on the subscription, recording every message without consuming it from other subscribers.
- **Queue channels** - Queue messages are consumed on receive, so non-destructive peeking is not possible. Instead, the `TerrariumAPI.send_to_channel()` method calls `observer.record()` after each send, capturing API-injected messages. Messages sent by creatures via the `send_message` tool are not captured by the observer unless the channel is broadcast.

The observer supports:

- **Callbacks** - `on_message(callback)` registers a function called for every observed message. The CLI uses this to print live channel traffic when `--observe` is passed.
- **History retrieval** - `get_messages(channel, last_n)` returns recent `ObservedMessage` entries, optionally filtered by channel name.
- **Bounded memory** - The history buffer is capped at `max_history` (default 1000) entries.

## Output Log Capture

The `OutputLogCapture` class (`terrarium/output_log.py`) is a tee wrapper that intercepts a creature's output and records it into a ring buffer.

When a creature has `output_log: true` in the terrarium config, the runtime wraps its default output module with `OutputLogCapture` during creature setup. All output flows to the original module unchanged, and a copy is stored in a `deque` of `LogEntry` objects.

Three entry types are captured:

| Entry type | Source | Description |
|------------|--------|-------------|
| `text` | `write()` calls | Complete text blocks from the output module |
| `stream_flush` | `flush()` after streaming | Accumulated `write_stream()` chunks, flushed as one entry |
| `activity` | `on_activity()` calls | Tool start/done/error notifications with `activity_type` metadata |

Log access methods:

- `get_entries(last_n, entry_type)` - Get recent entries, optionally filtered by type
- `get_text(last_n)` - Get recent text output concatenated (excludes activity entries)
- `entry_count` - Current number of entries in the buffer
- `clear()` - Empty the buffer

The ring buffer size is controlled by `output_log_size` in the terrarium config (default 100). See [Configuration Reference](configuration.md) for the config fields. See [API Reference](api.md) for programmatic access patterns.

## Hot-Plug

The terrarium supports runtime modification of its topology. Creatures, channels, and triggers can be added or removed without stopping and restarting the entire system.

### What Can Be Modified at Runtime

| Component | Add | Remove | Notes |
|-----------|-----|--------|-------|
| Trigger (agent-level) | Yes | Yes | Starts/stops immediately |
| System prompt (agent-level) | Append or replace | N/A | Takes effect on next LLM call |
| Creature (terrarium-level) | Yes | Yes | Full wiring before first trigger |
| Channel (terrarium-level) | Yes | N/A | Available immediately after creation |
| Channel wiring | Yes | N/A | Adds trigger or send permission |

### Timing Guarantees

When a creature is added at runtime via `runtime.add_creature()`, the runtime performs the same wiring steps as during initial startup:

1. Load the agent config from the creature's `config_path`.
2. Create the `Agent` instance with the shared session.
3. Inject `ChannelTrigger` instances for each listen channel.
4. Inject channel topology into the system prompt.
5. Start the agent.

The creature is fully wired before its first trigger fires. There is no window where a partially-configured creature could receive a message.

Similarly, `agent.add_trigger()` calls `trigger.start()` before creating the background task, so the trigger is fully initialized before it begins listening.

### Session Sharing

Hot-added creatures share the same `Session` (and therefore the same `ChannelRegistry`) as creatures that were present at startup. This means:

- Hot-added creatures can immediately send to and receive from any existing channel.
- Channels created via `runtime.add_channel()` are visible to all creatures, both existing and future.
- There is no separate session for hot-added components.

### Agent-Level vs Terrarium-Level

Agent-level hot-plug methods (`add_trigger`, `remove_trigger`, `update_system_prompt`, `get_system_prompt`) operate on a single agent. They do not require a terrarium and can be used with standalone agents.

Terrarium-level methods (`add_creature`, `remove_creature`, `add_channel`, `wire_channel`) coordinate across multiple agents and handle the wiring that the terrarium runtime normally performs at startup.

See [API Reference](api.md#hot-plug-api) for method signatures and code examples.

## Environment-Session System

The Environment-Session model provides two-level isolation for multi-session support.

### Hierarchy

```
Environment (env_id)
├── shared_channels: ChannelRegistry    (inter-creature channels)
├── _context: dict[str, Any]            (module-registered shared state)
│
├── Session "agent_a"
│   ├── channels: ChannelRegistry       (private channels)
│   ├── scratchpad: Scratchpad          (private working memory)
│   └── extra: dict                     (custom state)
│
├── Session "agent_b"
│   ├── channels: ChannelRegistry       (private channels)
│   ├── scratchpad: Scratchpad          (private working memory)
│   └── extra: dict                     (custom state)
│
└── ... more sessions
```

### Two-Level Isolation

**Environment** holds resources shared across all creatures in a terrarium (or all agents in a user request). This includes the shared channel registry (for inter-creature communication) and module-registered state (database connections, API clients, etc.). One Environment corresponds to one terrarium instance.

**Session** holds private state for a single creature. Each creature gets its own Session with an independent `ChannelRegistry`, `Scratchpad`, and extensible `extra` dict. Sessions are created lazily via `environment.get_session(key)`.

The separation ensures that:

- Creatures cannot accidentally read each other's scratchpads
- Private channels (sub-agent communication within a creature) are invisible to other creatures
- Shared channels (inter-creature communication) are managed at the environment level
- Module state can be scoped to either environment or session as appropriate

### Channel Resolution

When the terrarium runtime resolves channels, it follows a **private first, shared second** order:

1. Check the creature's session-private `ChannelRegistry`
2. Check the environment's `shared_channels` registry
3. If neither has the channel, create it in the appropriate registry

This means a creature's internal sub-agent channels (private) take precedence over terrarium-level channels (shared). If a creature and the terrarium both declare a channel named `"inbox"`, they are distinct objects and do not conflict.

### Shared State Registration

Modules can store and retrieve environment-level shared state without coupling to specific data structures:

```python
# Register shared state (e.g., in a custom tool's setup)
environment.register("db_pool", connection_pool)
environment.register("rate_limiter", limiter)

# Retrieve from anywhere with environment access
pool = environment.get("db_pool")
```

This avoids passing extra constructor arguments through the entire stack.

## What the Terrarium Does NOT Do

- It does **not** replace creature I/O modules. Creatures keep their original input/output.
- It does **not** touch creature internals. Sub-agents inside a creature are invisible.
- It does **not** contain intelligence. No LLM, no decision-making. Pure wiring.
- It does **not** enforce protocols. Creatures and their tools handle task structure.
