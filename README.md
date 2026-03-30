# KohakuTerrarium

**A universal agent framework with peer-to-peer multi-agent orchestration.**

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green)

---

KohakuTerrarium is a Python framework for building any kind of agent: coding assistants, conversational AI, monitoring drones, multi-agent teams. It provides **two levels of agent composition**:

1. **Creature** - a self-contained agent with its own LLM, tools, sub-agents, and memory. Handles task decomposition internally via hierarchical sub-agents.
2. **Terrarium** - a runtime that wires multiple standalone creatures together via channels for peer-to-peer collaboration. No creature is special. The terrarium is pure wiring, not intelligence.

Build agents individually, test them standalone, then place them in a terrarium to collaborate.

## Key Features

### Agent Framework (Creature)
- **Any agent type** - SWE agents, chatbots, autonomous monitors, multi-agent coordinators
- **Async-first execution** - tools start during LLM streaming, run in parallel via `asyncio`
- **Nested sub-agents** - full agents with their own LLM, tools, and lifecycle
- **Native + custom tool calling** - OpenAI function calling API, or configurable text formats (bracket, XML)
- **YAML-driven config** - define agents declaratively, minimal code required
- **16 built-in tools** - bash, read, write, edit, glob, grep, http, think, scratchpad, and more
- **10 built-in sub-agents** - explore, plan, worker, critic, summarize, research, coordinator, and more
- **Trigger system** - timers, channel events for autonomous operation

### Multi-Agent Orchestration (Terrarium)
- **Peer-to-peer channels** - queue (point-to-point) and broadcast (all subscribers) channel types
- **Zero-modification wiring** - standalone creatures work in a terrarium without config changes
- **Trigger-based receiving** - channel messages arrive automatically as events, no polling
- **Explicit sending** - creatures decide what to communicate via `send_message`
- **Topology-aware prompts** - system prompt auto-injects channel info with descriptions
- **Lifecycle management** - start, stop, monitor all creatures from one runtime

## Architecture

### Creature (Single Agent)

```
Input ---------+
               +----> Controller (LLM) <----> Tools (parallel, non-blocking)
Trigger -------+           |            <----> Sub-Agents (nested LLMs)
                           |
                     +-----+------+
                     |            |
                  Output      Channels ----> Other Agents
```

| System | Role |
|--------|------|
| **Input** | User requests, chat messages, ASR streams, TUI, or none (trigger-only) |
| **Trigger** | Timers, channel events for autonomous operation |
| **Controller** | LLM orchestrator that dispatches tasks and makes decisions |
| **Tool Calling** | Background parallel execution of tools and sub-agents |
| **Output** | Streaming to stdout, files, TTS, APIs, webhooks |

### Terrarium (Multi-Agent)

```
+-------------+     +-------------------+     +-----------------+
|  Creatures  |     |  Terrarium Layer  |     | Human Interface |
|  (opaque)   |<--->|  (wiring)         |<--->| (pluggable)     |
|             |     |                   |     |                 |
| - architect |     | - channel system  |     | - CLI           |
| - swe_agent |     | - trigger wiring  |     | - API           |
| - reviewer  |     | - lifecycle mgmt  |     | - Web UI        |
| - any other |     | - prompt injection|     | - none (auto)   |
+-------------+     +-------------------+     +-----------------+
```

Two channel types support any topology:

```
Queue (point-to-point):          Broadcast (group chat):

  A --[tasks]--> B               A --+
  B --[results]--> A              B --+--> [discussion] --> all subscribers
                                  C --+

Pipeline:                        Hub-and-spoke:

  research --> plan --> implement     architect --[tasks]--> worker_1
      ^                    |         architect --[tasks]--> worker_2
      +----[feedback]------+         worker_* --[results]--> architect
```

| Concept | Role |
|---------|------|
| **Creature** | Opaque, self-contained agent (microservice analogy) |
| **Queue channel** | Point-to-point: one consumer per message (task dispatch, pipelines) |
| **Broadcast channel** | Group chat: all subscribers see every message (shared awareness) |
| **Terrarium** | Pure wiring: channels, triggers, lifecycle. No intelligence |
| **Human Interface** | CLI, API, or Web UI. Pluggable, optional |

## Quick Start

### Run a Single Agent

```bash
git clone https://github.com/KohakuBlueLeaf/KohakuTerrarium.git
cd KohakuTerrarium
uv pip install -e .

export OPENROUTER_API_KEY=your_key_here

# Run the SWE agent
python -m kohakuterrarium run agents/swe_agent

# Run the SWE agent (TUI mode)
python -m kohakuterrarium run agents/swe_agent_tui
```

### Run a Terrarium

```bash
# Run the novel writer terrarium (3 creatures collaborating)
python -m kohakuterrarium terrarium run agents/novel_terrarium/

# With channel observation (see messages flow between creatures)
python -m kohakuterrarium terrarium run agents/novel_terrarium/ --observe ideas outline draft

# Show terrarium info
python -m kohakuterrarium terrarium info agents/novel_terrarium/
```

### Start the HTTP API

```bash
# Start the API server
python apps/api/main.py
# Open http://localhost:8000/docs for API documentation
```

### Programmatic Usage

```python
import asyncio
from kohakuterrarium.core.agent import Agent

async def main():
    agent = Agent.from_path("agents/swe_agent")
    await agent.run()  # Interactive CLI loop

asyncio.run(main())
```

### Programmatic Terrarium

```python
import asyncio
from kohakuterrarium.terrarium import TerrariumRuntime, load_terrarium_config

async def main():
    config = load_terrarium_config("agents/novel_terrarium")
    runtime = TerrariumRuntime(config)
    await runtime.run()  # All creatures run concurrently

asyncio.run(main())
```

### Programmatic Control

```python
async def main():
    agent = Agent.from_path("agents/swe_agent")
    await agent.start()

    await agent.inject_input("Create a hello world script")
    agent.set_output_handler(lambda text: print(f"AI: {text}"))

    print(agent.tools)       # ['bash', 'read', 'write', ...]
    print(agent.subagents)   # ['explore', 'plan', 'worker', ...]

    await agent.stop()
```

Agents can also be embedded in web servers (FastAPI, etc.) - see [Configuration Reference](docs/guides/configuration.md) for details.

## Built-in Tools (16)

| Tool | Description | Tool | Description |
|------|-------------|------|-------------|
| `bash` | Execute shell commands | `think` | Extended reasoning step |
| `python` | Run Python scripts | `scratchpad` | Session key-value memory |
| `read` | Read file contents | `send_message` | Send to named channel |
| `write` | Create/overwrite files | `wait_channel` | Wait for channel message |
| `edit` | Search-replace in files | `http` | Make HTTP requests |
| `glob` | Find files by pattern | `ask_user` | Prompt user for input |
| `grep` | Regex search in files | `json_read` | Query JSON files |
| `tree` | Directory structure | `json_write` | Modify JSON files |

## Built-in Sub-Agents (10)

| Sub-Agent | Purpose | Sub-Agent | Purpose |
|-----------|---------|-----------|---------|
| `explore` | Search codebase (read-only) | `coordinator` | Multi-agent via channels |
| `plan` | Create implementation plans | `memory_read` | Retrieve from memory |
| `worker` | Implement changes (read-write) | `memory_write` | Store to memory |
| `critic` | Review and critique | `response` | Generate user responses |
| `summarize` | Condense long content | `research` | Web + file research |

## Examples

### Terrariums (Multi-Agent)

| Terrarium | Topology | Creatures |
|-----------|----------|-----------|
| [novel_terrarium](agents/novel_terrarium/) | Pipeline with feedback | brainstorm, planner, writer |

### Novel Writer Terrarium

Three creatures collaborate via queue channels (pipeline) + one broadcast channel (team awareness):

```
brainstorm --[ideas q]--> planner --[outline q]--> writer --[draft q]-->
     ^                                               |
     +------------------[feedback q]-----------------+
                    [team_chat broadcast] --> all
```

```bash
# Run it
python -m kohakuterrarium terrarium run agents/novel_terrarium/ --observe ideas outline

# See the config
python -m kohakuterrarium terrarium info agents/novel_terrarium/
```

Output: 4 chapters + compiled `novel.md` in the working directory.

### Agents (Single)

| Agent | Pattern |
|-------|---------|
| [swe_agent](agents/swe_agent/) | SWE coding assistant with native tool calling |
| [swe_agent_tui](agents/swe_agent_tui/) | SWE assistant with TUI interface |
| [planner_agent](agents/planner_agent/) | Plan-execute-reflect loop |
| [monitor_agent](agents/monitor_agent/) | Trigger-driven autonomous agent |

## Configuration

### Agent Config

```yaml
name: my_agent
controller:
  model: "google/gemini-3-flash-preview"
  api_key_env: OPENROUTER_API_KEY
  base_url: https://openrouter.ai/api/v1
  tool_format: native    # native, bracket, xml, or custom dict

system_prompt_file: prompts/system.md

input:
  type: cli       # cli, tui, whisper, none (trigger-only), custom

tools:
  - name: bash
    type: builtin
  - name: read
    type: builtin

subagents:
  - name: explore
    type: builtin
```

### Terrarium Config

```yaml
terrarium:
  name: my_team
  creatures:
    - name: researcher
      config: ./creatures/researcher/
      channels:
        listen: [tasks, team_chat]
        can_send: [findings, team_chat]
    - name: writer
      config: ./creatures/writer/
      channels:
        listen: [findings, team_chat]
        can_send: [draft, team_chat]
  channels:
    tasks:      { type: queue, description: "Research tasks" }
    findings:   { type: queue, description: "Research results" }
    draft:      { type: queue, description: "Written output" }
    team_chat:  { type: broadcast, description: "Shared awareness" }
```

## Project Structure

```
src/kohakuterrarium/
  core/        # Agent, controller, executor, events, channels, environment, session
  modules/     # Protocols: input, trigger, tool, output, subagent
  terrarium/   # Multi-agent runtime: config, lifecycle, hot-plug, observer
  serving/     # Service layer: KohakuManager, AgentSession, event streaming
  builtins/    # 16 tools, 10 sub-agents, CLI/TUI/Whisper/None, stdout/TUI/TTS
  parsing/     # Stream parser (bracket, XML, native tool calling)
  prompt/      # System prompt aggregation + Jinja2 templating
  llm/         # LLM providers (OpenAI/OpenRouter) + native tool calling
  testing/     # ScriptedLLM, OutputRecorder, TestAgentBuilder
  utils/       # Structured colored logging

agents/        # Example agents and terrariums
docs/          # Architecture, guides, terrarium docs
apps/
  api/         # FastAPI HTTP API (REST + WebSocket)
```

## Documentation

- [Architecture Overview](docs/architecture.md)
- [Terrarium Guide](docs/terrarium/index.md)
- [Terrarium Architecture](docs/terrarium/architecture.md)
- [Terrarium Channels](docs/terrarium/channels.md)
- [Terrarium API Reference](docs/terrarium/api.md)
- [Serving Layer](docs/terrarium/serving.md)
- [Configuration Reference](docs/guides/configuration.md)
- [Testing Infrastructure](docs/testing.md)
- [Code Conventions](CLAUDE.md)

## License

Apache-2.0
