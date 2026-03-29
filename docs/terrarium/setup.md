# Terrarium Setup Guide

This guide walks through creating a multi-agent terrarium from scratch: prerequisites, environment setup, creating creatures, wiring channels, and running the result.

## Prerequisites

- Python 3.10+
- KohakuTerrarium installed in editable mode
- An LLM provider API key (OpenRouter recommended)

### Install

```bash
git clone <repository-url>
cd KohakuTerrarium
uv pip install -e .
```

### Environment Setup

Create a `.env` file at the project root:

```bash
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_MODEL=google/gemini-3-flash-preview
```

The `OPENROUTER_MODEL` variable is optional - creature configs specify defaults via the `${VAR:default}` syntax.

## Creating Your First Terrarium

This walkthrough creates a two-creature terrarium: a researcher that gathers information and a summarizer that condenses it.

### Step 1: Directory Structure

Create the terrarium folder:

```
agents/my_terrarium/
  terrarium.yaml
  run.py
  creatures/
    researcher/
      config.yaml
      prompts/
        system.md
    summarizer/
      config.yaml
      prompts/
        system.md
```

### Step 2: Create Creature Configs

Each creature is a standalone agent with its own `config.yaml` and system prompt. Creatures work independently - the terrarium adds channel wiring on top.

**Researcher creature** (`creatures/researcher/config.yaml`):

```yaml
name: researcher
version: "1.0"

controller:
  model: "${OPENROUTER_MODEL:google/gemini-3-flash-preview}"
  temperature: 0.7
  max_tokens: 8192
  api_key_env: OPENROUTER_API_KEY
  base_url: https://openrouter.ai/api/v1

system_prompt_file: prompts/system.md

input:
  type: none

output:
  type: stdout

tools:
  - name: send_message
    type: builtin
  - name: wait_channel
    type: builtin
  - name: think
    type: builtin

termination:
  max_turns: 10
  keywords: ["RESEARCH_COMPLETE"]

startup_trigger:
  prompt: "Begin your research task. Use think to gather your thoughts, then send findings to the 'findings' channel."
```

**Researcher system prompt** (`creatures/researcher/prompts/system.md`):

```markdown
# Researcher Agent

You are a research agent. Your job is to analyze a topic in depth and send your findings to other agents.

## Workflow

1. Use `think` to brainstorm key aspects of the topic
2. Organize your findings into a structured format
3. Send your findings to the `findings` channel via `send_message`
4. Output RESEARCH_COMPLETE when done
```

**Summarizer creature** (`creatures/summarizer/config.yaml`):

```yaml
name: summarizer
version: "1.0"

controller:
  model: "${OPENROUTER_MODEL:google/gemini-3-flash-preview}"
  temperature: 0.3
  max_tokens: 4096
  api_key_env: OPENROUTER_API_KEY
  base_url: https://openrouter.ai/api/v1

system_prompt_file: prompts/system.md

input:
  type: none

output:
  type: stdout

tools:
  - name: send_message
    type: builtin
  - name: think
    type: builtin
  - name: write
    type: builtin

termination:
  max_turns: 10
  keywords: ["SUMMARY_COMPLETE"]
```

**Summarizer system prompt** (`creatures/summarizer/prompts/system.md`):

```markdown
# Summarizer Agent

You are a summarization agent. When you receive research findings, distill them into a clear, concise summary.

## Workflow

1. Read the incoming findings carefully
2. Use `think` to identify key points
3. Write a structured summary to `summary.md` using the `write` tool
4. Output SUMMARY_COMPLETE when done
```

### Step 3: Create the Terrarium Config

The terrarium config (`terrarium.yaml`) wires the creatures together:

```yaml
terrarium:
  name: research_pipeline

  creatures:
    - name: researcher
      config: ./creatures/researcher/
      channels:
        can_send: [findings]

    - name: summarizer
      config: ./creatures/summarizer/
      channels:
        listen: [findings]

  channels:
    findings:
      type: queue
      description: "Research findings from researcher to summarizer"
```

Key decisions in this config:
- **researcher** can send to `findings` but does not listen on any channel. It starts via `startup_trigger`.
- **summarizer** listens on `findings`. The runtime injects a `ChannelTrigger` for this channel, so the summarizer wakes up when findings arrive.
- The `findings` channel is a queue (point-to-point). One message goes to one receiver.

### Step 4: Create the Runner Script

The runner script (`run.py`) loads the config and starts the runtime:

```python
"""Run the research pipeline terrarium."""

import asyncio
import os

from dotenv import load_dotenv

from kohakuterrarium.terrarium import TerrariumRuntime, load_terrarium_config


async def main() -> None:
    # Load environment
    project_root = os.path.join(os.path.dirname(__file__), "..", "..")
    load_dotenv(os.path.join(project_root, ".env"))

    # Set output directory
    output_dir = os.path.join(project_root, "example_output", "research_pipeline")
    os.makedirs(output_dir, exist_ok=True)
    os.chdir(output_dir)

    # Load and run terrarium
    config = load_terrarium_config(os.path.dirname(__file__))

    print(f"=== Terrarium: {config.name} ===")
    print(f"Creatures: {[c.name for c in config.creatures]}")
    print(f"Channels: {[c.name for c in config.channels]}")
    print()

    runtime = TerrariumRuntime(config)
    await runtime.run()


if __name__ == "__main__":
    asyncio.run(main())
```

### Step 5: Run

**Using the CLI** (recommended):

```bash
# Run from the terrarium directory
python -m kohakuterrarium terrarium run agents/my_terrarium/

# Inspect the config before running
python -m kohakuterrarium terrarium info agents/my_terrarium/
```

**Using the runner script**:

```bash
python agents/my_terrarium/run.py
```

## Wiring Channels

### Basic Patterns

**One-way pipeline:**

```yaml
creatures:
  - name: producer
    channels:
      can_send: [data]
  - name: consumer
    channels:
      listen: [data]

channels:
  data: { type: queue }
```

**Bidirectional (request-response):**

```yaml
creatures:
  - name: requester
    channels:
      can_send: [requests]
      listen: [responses]
  - name: responder
    channels:
      listen: [requests]
      can_send: [responses]

channels:
  requests:  { type: queue }
  responses: { type: queue }
```

**Group discussion:**

```yaml
creatures:
  - name: agent_a
    channels:
      listen: [discussion]
      can_send: [discussion]
  - name: agent_b
    channels:
      listen: [discussion]
      can_send: [discussion]
  - name: agent_c
    channels:
      listen: [discussion]
      can_send: [discussion]

channels:
  discussion: { type: broadcast, description: "Open group discussion" }
```

### Channel Tool Registration

Creatures that participate in channel communication need the `send_message` and/or `wait_channel` tools in their agent config:

```yaml
tools:
  - name: send_message
    type: builtin
  - name: wait_channel
    type: builtin
```

The terrarium runtime does not auto-register these tools. They must be listed in the creature's own `config.yaml`.

## CLI Usage

The built-in CLI provides two terrarium commands.

### `terrarium run`

Launches a terrarium from a config path:

```bash
python -m kohakuterrarium terrarium run agents/my_terrarium/
```

Options:

| Flag | Description |
|------|-------------|
| `--log-level` | Logging verbosity: `DEBUG`, `INFO` (default), `WARNING`, `ERROR` |
| `--observe` | Space-separated list of channel names to observe. Prints messages as they flow. |

Example with observation:

```bash
python -m kohakuterrarium terrarium run agents/my_terrarium/ --observe findings --log-level DEBUG
```

When `--observe` is used, the CLI creates a `ChannelObserver` that prints each message with a timestamp, channel name, sender, and content preview. For broadcast channels, the observer subscribes silently. For queue channels, only API-injected messages are visible (see [Architecture - Observer Pattern](architecture.md#observer-pattern)).

### `terrarium info`

Displays terrarium configuration without running it:

```bash
python -m kohakuterrarium terrarium info agents/my_terrarium/
```

Output includes creature names, config paths, channel assignments, output log settings, and all declared channels with their types and descriptions.

## Programmatic API Usage

The `TerrariumAPI` is available on any running runtime via `runtime.api`. It provides methods for channel operations, creature lifecycle, and status queries.

### Basic API usage

```python
from kohakuterrarium.terrarium import TerrariumRuntime, load_terrarium_config

config = load_terrarium_config("agents/my_terrarium/")
runtime = TerrariumRuntime(config)
await runtime.start()

api = runtime.api

# List channels
channels = await api.list_channels()
# [{"name": "findings", "type": "queue", "description": "..."}]

# Send a message into a channel
msg_id = await api.send_to_channel("findings", "New data arrived", sender="human")

# List creatures and their status
creatures = await api.list_creatures()
for c in creatures:
    print(f"{c['name']}: running={c['running']}")

# Stop a specific creature
await api.stop_creature("researcher")

# Restart it
await api.start_creature("researcher")

# Full terrarium status
status = api.get_status()
```

See [API Reference](api.md) for the complete method list.

### Channel observation

```python
observer = runtime.observer

# Subscribe to a broadcast channel
await observer.observe("team_chat")

# Register a callback for live messages
def on_msg(msg):
    print(f"[{msg.channel}] {msg.sender}: {msg.content}")

observer.on_message(on_msg)

# Retrieve recent history
messages = observer.get_messages(channel="team_chat", last_n=10)

# Clean up when done
await observer.stop()
```

### Output log access

Enable output logging per-creature in `terrarium.yaml`:

```yaml
creatures:
  - name: researcher
    config: ./creatures/researcher/
    output_log: true
    output_log_size: 200
    channels:
      can_send: [findings]
```

Then access the log at runtime:

```python
handle = runtime._creatures["researcher"]

# Get recent log entries
entries = handle.get_log_entries(last_n=10)
for entry in entries:
    print(f"[{entry.timestamp}] ({entry.entry_type}) {entry.preview()}")

# Get concatenated text output
text = handle.get_log_text(last_n=5)
print(text)
```

## Monitoring

### Programmatic Status

The runtime exposes a `get_status()` method for monitoring:

```python
runtime = TerrariumRuntime(config)
await runtime.start()

# Check status
status = runtime.get_status()
print(f"Running: {status['running']}")
print(f"Creatures: {list(status['creatures'].keys())}")
for name, info in status['creatures'].items():
    print(f"  {name}: running={info['running']}")
```

### Output

By default, creature output goes to stdout (their configured output module). Each creature streams its LLM responses as they are generated, interleaved on the terminal.

## Startup Triggers

Creatures that need to begin work immediately (without waiting for a channel message) should configure a `startup_trigger` in their agent config:

```yaml
startup_trigger:
  prompt: "Begin your task. Research the topic and send findings to the 'findings' channel."
```

The runtime fires each creature's startup trigger after all creatures are started, so channels are available from the beginning.

## Termination

Each creature defines its own termination conditions in its agent config:

```yaml
termination:
  max_turns: 15
  keywords: ["TASK_COMPLETE"]
```

When all creatures have terminated (or are cancelled), the terrarium runtime exits. The runtime also handles `KeyboardInterrupt` and `asyncio.CancelledError` for clean shutdown.
