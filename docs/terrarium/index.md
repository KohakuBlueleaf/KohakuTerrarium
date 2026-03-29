# Terrarium: Multi-Agent Orchestration

## What Is a Terrarium?

A Terrarium is the multi-agent orchestration layer in KohakuTerrarium. It takes standalone agents ("creatures"), places them in a shared environment, and wires them together through named channels. The terrarium itself contains no intelligence - it is pure wiring: channels, triggers, lifecycle management, and prompt injection.

Each creature is a fully self-contained agent with its own LLM, tools, sub-agents, and memory. Creatures are built and tested independently. The terrarium adds the horizontal coordination layer that lets them collaborate without modifying their internals.

## Key Concepts

| Concept | Role |
|---------|------|
| **Creature** | A standalone agent placed into the terrarium. Opaque - the terrarium does not inspect or modify its internals. |
| **Channel** | A named async message conduit connecting creatures. Two types: queue (point-to-point) and broadcast (all subscribers). |
| **Trigger** | A `ChannelTrigger` injected into a creature so it reacts when messages arrive on its listen channels. |
| **Topology** | The channel wiring between creatures. Emerges from configuration, not code. Supports pipeline, hub-and-spoke, group chat, and hybrid patterns. |
| **API** | `TerrariumAPI` provides programmatic access to channels, creatures, and runtime status. See [API Reference](api.md). |
| **Observer** | `ChannelObserver` watches channel traffic non-destructively. Broadcast channels are subscribed silently; queue messages are recorded via the API. |
| **Output Log** | `OutputLogCapture` wraps a creature's output module and records everything into a ring buffer for later retrieval. Enabled per-creature in config. |
| **CLI** | Built-in commands (`terrarium run`, `terrarium info`) for running and inspecting terrariums from the terminal. |

## Quick Start: Running the Novel Writer Example

The included `novel_terrarium` example demonstrates a three-creature pipeline that collaborates to write a short story: brainstorm generates ideas, planner creates chapter outlines, and writer produces prose.

### Prerequisites

```bash
# Install the framework (editable mode)
uv pip install -e .

# Set up environment variables
cp .env.example .env
# Edit .env to add your OpenRouter API key:
#   OPENROUTER_API_KEY=sk-or-...
```

### Run with the CLI

The quickest way to launch a terrarium is the built-in CLI:

```bash
# Run the terrarium
python -m kohakuterrarium terrarium run agents/novel_terrarium/

# Run with channel observation (prints messages as they flow)
python -m kohakuterrarium terrarium run agents/novel_terrarium/ --observe team_chat ideas

# Inspect terrarium config without running
python -m kohakuterrarium terrarium info agents/novel_terrarium/
```

### Run with a script

Alternatively, use the runner script directly:

```bash
python agents/novel_terrarium/run.py
```

This loads `agents/novel_terrarium/terrarium.yaml`, creates three creatures with a shared channel registry, and runs them concurrently. Output appears on stdout as each creature streams its LLM responses.

### What Happens

1. **brainstorm** starts via its `startup_trigger`, generates story ideas using the `think` tool, and sends its chosen concept to the `ideas` channel.
2. **planner** receives the concept (via a `ChannelTrigger` on `ideas`), breaks it into chapter outlines, and sends each outline to the `outline` channel.
3. **writer** receives outlines (via a `ChannelTrigger` on `outline`), writes prose for each chapter, and saves the result to files.
4. A `feedback` channel and `team_chat` broadcast channel are available for coordination and status updates.

### Terrarium Config (abbreviated)

```yaml
terrarium:
  name: novel_writer

  creatures:
    - name: brainstorm
      config: ./creatures/brainstorm/
      channels:
        listen: [feedback]
        can_send: [ideas, team_chat]

    - name: planner
      config: ./creatures/planner/
      channels:
        listen: [ideas]
        can_send: [outline, team_chat]

    - name: writer
      config: ./creatures/writer/
      channels:
        listen: [outline]
        can_send: [draft, feedback, team_chat]

  channels:
    ideas:      { type: queue, description: "Raw ideas from brainstorm to planner" }
    outline:    { type: queue, description: "Chapter outlines from planner to writer" }
    draft:      { type: queue, description: "Written chapters for review" }
    feedback:   { type: queue, description: "Feedback from writer back to brainstorm" }
    team_chat:  { type: broadcast, description: "Team-wide status updates" }
```

## Documentation

- [Architecture](architecture.md) - Two-level composition, runtime components, communication model
- [Configuration Reference](configuration.md) - Full YAML format, all fields, environment variables
- [Channel System](channels.md) - Channel types, tools, triggers, prompt awareness
- [Setup Guide](setup.md) - Step-by-step guide to creating your own terrarium
- [API Reference](api.md) - TerrariumAPI, ChannelObserver, OutputLogCapture
