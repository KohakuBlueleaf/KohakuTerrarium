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
| Terrarium | Service mesh | Routing, lifecycle, observability -- no business logic |
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

1. **Create shared session** -- All creatures share one `Session` with a single `ChannelRegistry`, so channels are visible across creatures.
2. **Pre-create declared channels** -- Each channel from the config is created in the shared registry with the correct type and description.
3. **Build creatures** -- For each creature:
   - Load the standalone agent config via `load_agent_config()`
   - Point the agent at the shared session key
   - Override input to `NoneInput` (creatures receive work via channel triggers, not stdin)
   - Inject `ChannelTrigger` instances for each listen channel
   - Inject channel topology into the system prompt
4. **Start all creature agents** -- Call `agent.start()` on each creature.

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

Communication between creatures is always **explicit**. The creature's LLM decides what to send via the `send_message` tool. The terrarium never silently pipes creature output into channels. This preserves the opacity principle -- internal reasoning stays private.

### Receiving Messages

The terrarium appends `ChannelTrigger` instances to each creature's trigger list for its listen channels. When a message arrives on a channel, the trigger creates a `TriggerEvent(type=CHANNEL_MESSAGE)` -- the same event system used for all other triggers (timers, user input, idle detection). The creature processes the event through its normal controller loop.

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

- `feedback` [queue] (listen) -- Feedback from writer back to brainstorm
- `ideas` [queue] (send) -- Raw ideas from brainstorm to planner
- `team_chat` [broadcast] (send) -- Team-wide status updates

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

## What the Terrarium Does NOT Do

- It does **not** replace creature I/O modules. Creatures keep their original input/output.
- It does **not** touch creature internals. Sub-agents inside a creature are invisible.
- It does **not** contain intelligence. No LLM, no decision-making. Pure wiring.
- It does **not** enforce protocols. Creatures and their tools handle task structure.
