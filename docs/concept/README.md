# Concepts

KohakuTerrarium builds on one core insight: **agent systems need two different coordination mechanisms**, and mixing them causes problems.

```
                         KohakuTerrarium
                               |
              +----------------+----------------+
              |                                 |
         Creature                          Terrarium
    (vertical hierarchy)              (horizontal peers)
              |                                 |
    Controller delegates              Channels connect
    to sub-agents for                 independent creatures
    task decomposition                for collaboration
```

**Creatures** handle the vertical: one controller orchestrating sub-agents and tools to decompose a task. This is hierarchical, tightly coupled, with shared context.

**Terrariums** handle the horizontal: independent creatures communicating through channels as peers. This is flat, loosely coupled, with opaque boundaries.

A creature built for standalone use works identically in a terrarium. It does not know it is in one.

## The Five Concepts

### [Creature](creature.md) - The Self-Contained Agent

A creature is a complete agent: LLM controller, tools, sub-agents, memory. It receives input, thinks, acts, and produces output. Every creature is built from five systems: input, triggers, controller, tools, and output.

Think of it as a microservice: private internals, well-defined interface.

### [Terrarium](terrarium.md) - The Wiring Layer

A terrarium places creatures in a shared environment and connects them through channels. It has no intelligence of its own. It just moves messages.

Think of it as a service mesh: routing, lifecycle, observability, but no business logic.

### [Channels](channels.md) - The Communication Primitive

Two types of named message conduits:
- **Queue** (SubAgentChannel): one consumer per message. For task dispatch, pipelines, request-response.
- **Broadcast** (AgentChannel): all subscribers receive every message. For group chat, shared awareness.

Channels are the only way creatures communicate. Communication is always explicit via `send_message`.

### [Environment-Session](environment.md) - The Isolation Boundary

Two-level isolation for safe multi-user operation:
- **Environment**: shared state per terrarium (inter-creature channels)
- **Session**: private state per creature (scratchpad, sub-agent channels)

Two users running the same terrarium get separate environments. Two creatures in the same terrarium share channels but not scratchpads.

### [Tool Formats](tool-formats.md) - How LLMs Call Tools

Three ways for an LLM to invoke tools:
- **Native**: the LLM API's built-in function calling (most reliable)
- **Bracket**: `[/tool]content[tool/]` text format
- **XML**: `<tool>content</tool>` text format

Configurable per agent. Native is recommended for models that support it.

## How They Compose

```
User Request
     |
     v
+--------------------+     +------------------------+
|    Terrarium       |     |   Environment          |
|    (wiring)        |     |   (isolation)           |
|                    |     |                         |
|  brainstorm -------+-queue--> planner              |
|       |            |     |       |                 |
|       +--broadcast-+-all-+       +--queue--> writer|
|                    |     |                         |
+--------------------+     +------------------------+
     |                              |
     v                              v
  Each creature                  Each creature
  is a full agent:               has private:
  - LLM controller               - Session
  - Tools (native/bracket/xml)    - Scratchpad
  - Sub-agents                    - Sub-agent channels
  - Memory
```

For implementation details, see [Architecture](../architecture/README.md). For API usage, see [API Reference](../api-reference/README.md).
