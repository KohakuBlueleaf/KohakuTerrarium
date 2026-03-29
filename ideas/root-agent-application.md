# The Root Agent: KohakuTerrarium as an Application

## The Vision

The final form of KohakuTerrarium is not a framework you code against. It is an **application** with a single interface:

```
User <-> Root Agent <-> Terrarium Layer
```

The user talks to one agent. That agent builds, configures, runs, and manages terrariums. The user never writes YAML. The user never learns channel topology. They just say what they want done.

## How It Works

```
+------------------+
|   Human (WebUI   |
|   or TUI or CLI) |
+--------+---------+
         |
         v
+--------+---------+
|   Root Agent     |  <-- Single LLM-powered agent
|   (orchestrator) |      Has tools to manage the terrarium layer
+--------+---------+
         |
         v
+--------+-------------------------------------------+
|              Terrarium Layer                        |
|                                                     |
|  Channels    Creatures    Lifecycle    Config        |
|                                                     |
|  [brainstorm] --[ideas]--> [planner] --[outline]--> |
|  [reviewer]  <--[reviews]-- [writer]                |
+-----------------------------------------------------+
```

The root agent is a creature itself, but a special one: it has tools that manipulate the terrarium layer. It can:

1. **Create creatures** on the fly ("I need a researcher for this task")
2. **Wire channels** ("connect the researcher to the planner via a findings channel")
3. **Start/stop creatures** ("the reviewer found issues, restart the writer")
4. **Inject messages** ("tell the brainstorm agent to focus on sci-fi themes")
5. **Observe** ("what did the planner produce?")
6. **Adjust configs** ("increase the writer's temperature, it's too formulaic")

## Root Agent Tools

```python
# Terrarium management tools available to the root agent:

terrarium_create(config_yaml: str) -> str
    # Create and start a terrarium from inline YAML config
    # Returns terrarium_id

terrarium_status(terrarium_id: str) -> dict
    # Get full status: creatures, channels, progress

creature_create(terrarium_id: str, name: str, config: dict) -> None
    # Hot-add a new creature to a running terrarium
    # Creates agent, wires channels, injects triggers, starts

creature_stop(terrarium_id: str, name: str) -> None
    # Stop a creature (graceful)

creature_restart(terrarium_id: str, name: str, config_override: dict) -> None
    # Stop + reconfigure + restart a creature

channel_create(terrarium_id: str, name: str, channel_type: str, description: str) -> None
    # Hot-add a channel to a running terrarium

channel_wire(terrarium_id: str, creature: str, channel: str, direction: str) -> None
    # Connect a creature to a channel (listen or send)
    # Injects ChannelTrigger if direction is "listen"

channel_send(terrarium_id: str, channel: str, message: str) -> str
    # Inject a message into a channel

channel_read(terrarium_id: str, channel: str, last_n: int) -> list
    # Read recent messages from a channel

creature_log(terrarium_id: str, name: str, last_n: int) -> str
    # Read a creature's output log

terrarium_stop(terrarium_id: str) -> None
    # Stop everything
```

## Example Interaction

```
User: I want to write a novel about a detective in a cyberpunk city.

Root Agent: (thinks) I'll create a terrarium with three specialized agents.

[calls terrarium_create with brainstorm + planner + writer config]
[calls channel_send to inject the seed prompt]

Root Agent: I've set up a writing team. The brainstorm agent is generating
ideas now. I'll monitor their progress.

[calls terrarium_status to check]

Root Agent: The brainstorm agent produced a concept called "Neon Shadows".
The planner is breaking it into 5 chapters. Want me to adjust anything
before the writer starts?

User: Make it darker. More noir. And the detective should be an AI.

Root Agent: Got it. I'll send that direction to the team.

[calls channel_send to team_chat with style guidance]
[calls creature_restart on brainstorm with updated prompt]

Root Agent: Updated. The brainstorm is reworking with noir tone and AI detective.
The planner will pick up the revised concept automatically.

User: Actually, add a critic agent that reviews each chapter before the next one starts.

Root Agent: Adding a critic to the pipeline.

[calls creature_create for "critic"]
[calls channel_create for "review"]
[calls channel_wire: writer -> review (send), critic -> review (listen)]
[calls channel_wire: critic -> outline (send, to feed back to writer)]

Root Agent: Done. The pipeline is now: brainstorm -> planner -> writer -> critic -> writer.
The critic will review each chapter and send feedback before the writer continues.
```

## Hot-Plug Architecture

For the root agent to work, the terrarium layer needs hot-plug support:

### Hot-Add Creature
1. Load creature config
2. Create Agent instance with shared session
3. Inject ChannelTriggers for listen channels
4. Inject channel topology into system prompt
5. Start the agent
6. Add to runtime's creature registry

### Hot-Remove Creature
1. Set creature's `_running = False`
2. Cancel creature's trigger tasks
3. Stop the agent
4. Unsubscribe from broadcast channels
5. Remove from runtime's creature registry

### Hot-Add Channel
1. Create channel in shared ChannelRegistry (queue or broadcast)
2. Update topology prompts for affected creatures (if needed)

### Hot-Wire Channel
1. Create ChannelTrigger for the creature
2. Start the trigger
3. Add to creature's trigger list
4. Optionally update the creature's system prompt

### Config Hot-Reload
1. Stop creature
2. Reload config from file or dict
3. Rebuild agent with new config
4. Re-inject triggers and topology
5. Restart

## The Root Agent's Own Config

```yaml
name: kohaku_root
version: "1.0"

controller:
  model: "${ROOT_MODEL:anthropic/claude-sonnet-4-20250514}"
  tool_format: native

system_prompt_file: prompts/root_system.md

tools:
  - name: terrarium_create
    type: builtin
  - name: terrarium_status
    type: builtin
  - name: creature_create
    type: builtin
  - name: creature_stop
    type: builtin
  - name: creature_restart
    type: builtin
  - name: channel_create
    type: builtin
  - name: channel_wire
    type: builtin
  - name: channel_send
    type: builtin
  - name: channel_read
    type: builtin
  - name: creature_log
    type: builtin
  - name: terrarium_stop
    type: builtin
  - name: think
    type: builtin
```

The root agent's system prompt would explain:
- What terrariums are and how they work
- Available creature templates (brainstorm, planner, writer, critic, researcher, etc.)
- Common topologies (pipeline, hub-and-spoke, group chat)
- When to add/remove/restart creatures
- How to interpret creature logs and channel messages
- When to intervene vs let creatures work

## The Application

The final "KohakuTerrarium" application is:

```
kohaku-app/
  backend/
    main.py           FastAPI app
    root_agent.py     Root agent with terrarium management tools
    manager.py        TerrariumManager (multiple terrariums)
    ws_handler.py     WebSocket for streaming
  frontend/
    pages/
      index.vue       Main chat interface with root agent
      terrarium.vue   Terrarium viewer (auto-opens when terrarium created)
```

The UI is a **chat interface** with the root agent, plus a **terrarium viewer** that opens when the agent creates a terrarium. The user chats naturally, the root agent manages everything.

```
+----------------------------------------------------------+
|  KohakuTerrarium                                    [v1] |
+----------------------------------------------------------+
|                        |                                  |
|   Chat with Root Agent |   Terrarium Viewer (live)        |
|                        |                                  |
|   You: Write a novel   |   [brainstorm] -> [planner]      |
|   about time travel    |        |              |          |
|                        |        v              v          |
|   Root: Setting up a   |   [ideas]        [outline]      |
|   writing team...      |        |              |          |
|                        |        v              v          |
|   Root: Team ready.    |   [planner]      [writer]       |
|   Brainstorm is        |                                  |
|   generating ideas.    |   [ideas] brainstorm: "The       |
|                        |   Clock Mender" - a story...     |
|   You: Make it darker  |   [outline] planner: Ch1...      |
|                        |                                  |
|   Root: Updating style |   [Status: writer RUNNING 2/4]   |
|   guidance...          |                                  |
+------------------------+----------------------------------+
```

## Implementation Order

1. **Hot-plug API on TerrariumRuntime** - creature_add, creature_remove, channel_add, channel_wire
2. **Root agent tools** - wrap hot-plug API as tool functions
3. **Root agent prompt** - teach it about terrariums, creatures, topologies
4. **HTTP API + WebSocket** - REST endpoints + streaming
5. **Vue frontend** - chat interface + terrarium viewer
6. **Creature template library** - pre-built creature configs the root agent can use

## The Key Insight

The root agent makes KohakuTerrarium accessible to non-technical users. They don't configure YAML. They don't understand channels. They just talk to an agent that happens to be able to summon and coordinate other agents.

The terrarium layer becomes an **internal implementation detail** that the root agent manages. The user interface is just a conversation.

But for power users, the terrarium viewer is always there: you can see what the root agent built, observe the channel traffic, inject messages yourself, and take manual control when needed.

## Open Questions

1. **Root agent model**: Should it be a strong model (Claude Sonnet/Opus, GPT-4) even if creatures use cheaper models? The root agent needs strategic thinking.

2. **Creature templates**: Pre-built configs for common roles (brainstorm, planner, writer, critic, researcher, debugger, reviewer). Should these be built into the framework or user-managed?

3. **Cost control**: The root agent creates creatures that make LLM calls. How to prevent runaway costs? Budget system on the terrarium? Root agent tracks total spend?

4. **Persistence**: Should the root agent remember past terrariums? "Last time you wrote a novel, you used this topology. Want to reuse it?"

5. **Multi-user**: Can multiple users share a terrarium? Each user has their own root agent, but they observe the same terrarium?
