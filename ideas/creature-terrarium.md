# Terrarium: Multi-Agent Orchestration for KohakuTerrarium

## Core Insight: Two Levels of Agent Composition

Agent systems need two fundamentally different coordination mechanisms:

1. **Vertical (Creature-internal)**: A main controller delegates to sub-agents for task decomposition. Hierarchical, tightly coupled, shared context, limited authority. The standard "main-sub agent" pattern.

2. **Horizontal (Terrarium-level)**: Independent agents collaborate as peers. Flat, loosely coupled, opaque boundaries, explicit messaging. No agent is privileged.

Most multi-agent frameworks fail because they use **one mechanism for both**. Either everything is hierarchical (sub-agents can't truly collaborate) or everything is peer-to-peer (task decomposition becomes awkward).

KohakuTerrarium separates them cleanly:
- **Creature** = a self-contained agent with its own controller, sub-agents, tools, memory. Handles the vertical.
- **Terrarium** = the environment where multiple creatures are placed together and wired up via channels. Handles the horizontal.

The boundary is clean: **a creature doesn't know it's in a terrarium.**

### Software Architecture Analogy

| Agent Concept | Software Analogy | Role |
|---------------|-----------------|------|
| Creature | Microservice | Self-contained, private internals, well-defined external interface |
| Terrarium | Service mesh | Routing, lifecycle, observability — no business logic |
| Sub-agents | Internal components | Private to the creature, invisible from outside |
| Channels | Message queues | Explicit, typed communication between creatures |

## What Is a Creature?

A creature is a fully self-contained, opaque agent. It has its own LLM, tools, sub-agents, memory, whatever. You don't know or care what's inside.

- A `discord_bot` is a creature.
- An `swe_agent` is a creature.
- A `code_reviewer` is a creature.

Creatures are built and tested **standalone**. They work independently. They have their own input module, output module, triggers, and tools.

## What Is a Terrarium?

The Terrarium is **not** an agent. It's the runtime environment that:

1. **Loads** standalone creature configs (unchanged from their solo use)
2. **Wires channels** — named async message queues connecting creatures
3. **Adds triggers** — appends ChannelTriggers to creatures so they receive channel messages
4. **Ensures tools** — registers `send_message`/`wait_channel` tools on creatures
5. **Injects topology** — adds channel awareness to creature system prompts
6. **Manages lifecycle** — starts, monitors, stops creatures
7. **Provides interface** — for humans or agent CLIs to observe and interact

### What the Terrarium Does NOT Do

- It does NOT replace creature I/O modules. Creatures keep their original input/output.
- It does NOT touch creature internals. Sub-agents inside a creature are invisible.
- It does NOT contain intelligence. No LLM, no decision-making. Pure wiring.
- It does NOT enforce protocols. Creatures and their tools handle task structure.

## Communication Model

### Channel-Based, Explicit Messaging

Creatures communicate through **named channels**. Communication is always **explicit** — the creature's LLM decides what to send via the `send_message` tool. The terrarium never silently pipes creature output into channels.

**Receiving**: The terrarium adds `ChannelTrigger`(s) to the creature's triggers list. When a message arrives on a channel, it creates a `TriggerEvent(type=CHANNEL_MESSAGE)` — the same event system used for all other triggers (timers, user input, etc.).

**Sending**: The creature calls `send_message` tool explicitly. The LLM decides what to communicate, preserving the opacity principle — the terrarium doesn't leak internal reasoning.

### Two Channel Types

| Type | Class | Semantics | Use Case |
|------|-------|-----------|----------|
| **Queue** | `SubAgentChannel` | One consumer per message | Task dispatch, request-response, pipelines |
| **Broadcast** | `AgentChannel` | All subscribers get every message | Group chat, shared awareness, events |

### Channel Messages

Every message has:
- `sender` — which creature sent it
- `content` — text or structured data
- `message_id` — unique, auto-generated
- `reply_to` — optional, for threading
- `channel` — set automatically by the channel
- `metadata` — arbitrary key-value pairs
- `timestamp` — when it was sent

## Coordination Topologies

Different wiring topologies emerge from channel configuration:

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

### Pipeline
```
researcher --findings(queue)--> planner --plan(queue)--> implementer --code(queue)--> reviewer
```

### Hybrid
Mix any of the above. Topology is just channel config.

## Terrarium Configuration

```yaml
terrarium:
  name: swe_team

  creatures:
    - name: architect
      config: ./creatures/architect/
      channels:
        listen: [reviews, escalations]     # ChannelTriggers added
        can_send: [tasks]                  # documented in system prompt

    - name: backend_dev
      config: ./creatures/swe_agent/
      channels:
        listen: [tasks]
        can_send: [results]

    - name: frontend_dev
      config: ./creatures/swe_agent/       # same creature type, different instance
      channels:
        listen: [tasks]
        can_send: [results]

    - name: reviewer
      config: ./creatures/reviewer/
      channels:
        listen: [results]
        can_send: [reviews]

  channels:
    tasks:       { type: queue }
    results:     { type: queue }
    reviews:     { type: queue }
    escalations: { type: queue }
    team_chat:   { type: broadcast }       # optional group awareness

  interface:
    type: cli                              # or: web, mcp, none
    observe: [tasks, results, reviews]
    inject_to: [tasks, escalations]
```

## Output Log (Optional Observability)

Creature output (LLM reasoning, tool usage) can optionally be captured into a read-only log that other creatures or the interface can query. This is **not** channel communication — it's observability.

```yaml
creatures:
  - name: backend_dev
    output_log: true          # allow others to read my transcript
    output_log_size: 100      # keep last 100 entries
```

Other creatures can read logs via a `read_agent_log` tool if available. This gives the architect visibility into what the backend_dev is doing without requiring explicit status reports.

**Note**: This relaxes the "opaque" principle for observability. It's opt-in per creature.

## The Human Interface (Separate Concern)

The human doesn't talk to creatures directly. The human talks to the **Terrarium** through whatever interface layer is configured.

### Interface Requirements

The interface must serve three audiences:

| Audience | Interaction | Needs |
|----------|------------|-------|
| Human directly | CLI commands, Web UI | Visual channel traffic, creature status, message injection |
| Coding agent CLI (Claude Code, Codex, OpenCode) | Programmatic tool calls | Machine-readable responses, structured API |
| Web browser | Dashboard | Real-time updates, channel viewer, creature inspector |

### Core API

All interfaces share one API:

```
# Channel operations
list_channels() → channel info
read_channel(name, last_n) → messages
send_to_channel(name, content) → message_id

# Creature operations
list_creatures() → creature status
start_creature(name) / stop_creature(name)
get_creature_log(name, last_n) → log entries

# Terrarium operations
get_status() → overall state
pause_all() / resume_all()
```

### Interface Options

- **CLI**: `terrarium status`, `terrarium send tasks "Fix the bug"`, `terrarium channel read results`
- **MCP Server**: Expose as MCP tools for Claude Code / agent CLI integration
- **Web UI**: Real-time dashboard with channel stream, creature cards, command input
- **None**: Fully autonomous, run to completion or escalation

The human interface is pluggable and orthogonal to the Terrarium itself.

## Structured Protocols (Not Terrarium Concerns)

Task lifecycle, artifacts, quality gates are **not** Terrarium concerns:

| Concern | Where It Lives |
|---------|---------------|
| Task state machine | Shared tool available to creatures |
| Structured artifacts | Channel schemas (optional message validation) |
| Quality gates | Tool constraints within specific creatures |
| Dependency ordering | Logic inside the architect creature |
| Git worktree isolation | Tool available to worker creatures |

The Terrarium doesn't enforce protocols. Creatures and their tools do. The Terrarium just moves messages.

## Summary

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

- **All creatures are opaque and equal.** No creature is privileged.
- **Communication is explicit.** Creatures choose what to send via `send_message`.
- **The Terrarium is pure wiring.** Channels, triggers, lifecycle. No intelligence.
- **The human interface is pluggable.** CLI, MCP, Web, or nothing.
- **Two-level composition.** Vertical (creature internals) + horizontal (terrarium wiring).
