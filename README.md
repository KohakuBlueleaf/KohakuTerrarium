# KohakuTerrarium

**A universal agent framework and ready-to-use agent application.**

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green)

---

KohakuTerrarium is both a **framework** for building any kind of agent system and an **application** that ships with pre-built agents and multi-agent teams ready to use out of the box.

## Two Levels of Composition

1. **Creature** -- a self-contained agent with its own LLM, tools, sub-agents, and memory. Handles task decomposition internally via hierarchical sub-agents.
2. **Terrarium** -- a runtime that wires multiple creatures together via channels for peer-to-peer collaboration. Pure wiring, no intelligence. Creatures don't know they're in a terrarium.

Build agents individually, test them standalone, then place them in a terrarium to collaborate.

## Philosophy

- **Framework + Application**: not just a library to build agents, but a product with powerful defaults. `kt run` gives you a capable agent immediately.
- **Creature inheritance**: 6 pre-built creature templates (general, swe, reviewer, ops, researcher, root). Extend any of them with a 5-line YAML config.
- **Terrarium-oriented design**: the multi-agent team is the primary visual metaphor. UI, TUI, and API are all designed around terrarium visibility -- topology graphs, channel streams, creature status.
- **Progressive disclosure**: one-line tool descriptions always visible, full documentation loaded on demand via the `info` tool, runtime hints in tool responses.
- **The root agent bridge**: a root agent with terrarium management tools lets users control multi-agent teams through natural language. No YAML required for end users.

## Pre-Built Creatures

All creatures inherit from `general` and add domain-specific behavior:

| Creature | Domain | Key Additions |
|----------|--------|---------------|
| **general** | Foundation | 16 tools, 6 sub-agents, core personality |
| **swe** | Software engineering | Coding workflow, git safety, validation |
| **reviewer** | Code review | Severity levels, structured findings, verdict |
| **ops** | Infrastructure | CI/CD, deployment, monitoring, cloud |
| **researcher** | Research | Source evaluation, citations, methodology |
| **root** | Orchestration | 7 terrarium management tools, delegation |

### Creature Inheritance

```yaml
# A complete agent in 5 lines
name: my_agent
base_config: creatures/swe
controller:
  model: "google/gemini-3-flash-preview"
  api_key_env: OPENROUTER_API_KEY
  base_url: https://openrouter.ai/api/v1
  tool_format: native
input: { type: cli }
output: { type: stdout, controller_direct: true }
```

Tools extend, prompts concatenate, scalars override. See [Creatures Guide](docs/guide/creatures.md).

## Pre-Built Terrariums

| Terrarium | Creatures | Topology |
|-----------|-----------|----------|
| **swe_team** | swe + reviewer | Task -> implement -> review -> feedback loop |

Terrariums support an optional `root:` field. When set, a root agent sits OUTSIDE the terrarium and manages it via tools. The user talks to root; root orchestrates the team.

## Quick Start

```bash
git clone https://github.com/KohakuBlueLeaf/KohakuTerrarium.git
cd KohakuTerrarium
uv pip install -e .
export OPENROUTER_API_KEY=your_key_here
```

### Run a Single Agent

```bash
kt run examples/agent-apps/swe_agent
kt run examples/agent-apps/swe_agent_tui  # TUI mode
```

### Run a Terrarium

```bash
kt terrarium run terrariums/swe_team/
kt terrarium run terrariums/swe_team/ --observe tasks review results

# TUI variant (example)
kt terrarium run examples/terrariums/swe_team_managed_tui/
```

### Programmatic Usage

```python
import asyncio
from kohakuterrarium.core.agent import Agent

async def main() -> None:
    agent = Agent.from_path("examples/agent-apps/swe_agent")
    await agent.run()

asyncio.run(main())
```

```python
from kohakuterrarium.terrarium.config import load_terrarium_config
from kohakuterrarium.terrarium.runtime import TerrariumRuntime

async def main() -> None:
    config = load_terrarium_config("terrariums/swe_team")
    runtime = TerrariumRuntime(config)
    await runtime.run()

asyncio.run(main())
```

### HTTP API

```bash
python apps/api/main.py
# 18 REST + 2 WebSocket endpoints at http://localhost:8000/docs
```

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

### Terrarium (Multi-Agent)

```
Queue (point-to-point):          Broadcast (group chat):

  A --[tasks]--> B               A --+
  B --[results]--> A              B --+--> [team_chat] --> all
                                  C --+
```

## Built-in Tools (23)

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
| `info` | Load tool/sub-agent docs | `terrarium_create` | Create and start a terrarium |
| `terrarium_status` | List/inspect terrariums | `terrarium_stop` | Stop a terrarium |
| `terrarium_send` | Send to terrarium channel | `terrarium_observe` | Read channel messages |
| `creature_start` | Hot-add creature | `creature_stop` | Remove creature |

## Built-in Sub-Agents (10)

| Sub-Agent | Purpose | Sub-Agent | Purpose |
|-----------|---------|-----------|---------|
| `explore` | Search codebase (read-only) | `coordinator` | Multi-agent via channels |
| `plan` | Create implementation plans | `memory_read` | Retrieve from memory |
| `worker` | Implement changes (read-write) | `memory_write` | Store to memory |
| `critic` | Review and critique | `response` | Generate user responses |
| `summarize` | Condense long content | `research` | Web + file research |

## Configuration

### Agent Config

```yaml
name: my_agent
base_config: creatures/swe          # Inherit from a creature
controller:
  model: "google/gemini-3-flash-preview"
  api_key_env: OPENROUTER_API_KEY
  base_url: https://openrouter.ai/api/v1
  tool_format: native                # native, bracket, xml
system_prompt_file: prompts/system.md
input: { type: cli }
tools:
  - { name: bash, type: builtin }
  - { name: my_tool, type: custom, module: ./tools/my_tool.py, class: MyTool }
```

### Terrarium Config

```yaml
terrarium:
  name: my_team
  creatures:
    - name: researcher
      config: ../../creatures/researcher
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
  core/        # Agent, controller, executor, events, channels, sessions
  modules/     # Protocols: input, trigger, tool, output, subagent
  terrarium/   # Multi-agent runtime: config, lifecycle, hot-plug, observer
  serving/     # KohakuManager, AgentSession, event streaming
  builtins/    # 23 tools, 10 sub-agents, CLI/TUI/Whisper inputs, stdout/TUI outputs
  parsing/     # Stream parser (bracket, XML, native tool calling)
  prompt/      # System prompt aggregation + Jinja2 templating
  llm/         # LLM providers (OpenAI/OpenRouter/Codex OAuth)
  testing/     # ScriptedLLM, OutputRecorder, TestAgentBuilder
  utils/       # Structured colored logging

creatures/     # Pre-built creature templates (general, swe, reviewer, ops, researcher, root)
terrariums/    # Pre-built terrarium templates (swe_team, swe_team_managed)
examples/      # Example agent apps, terrariums, and code samples
apps/api/      # FastAPI HTTP API (REST + WebSocket)
docs/          # Guide, concepts, architecture, API reference
```

## Documentation

**Guide** (using the framework):
- [Getting Started](docs/guide/getting-started.md)
- [Configuration Reference](docs/guide/configuration.md)
- [Creatures](docs/guide/creatures.md)
- [Example Agents](docs/guide/example-agents.md)

**Concepts**:
- [Creatures and Agents](docs/concept/creature.md)
- [Terrarium](docs/concept/terrarium.md)
- [Channels](docs/concept/channels.md)
- [Environment-Session](docs/concept/environment.md)
- [Tool Formats](docs/concept/tool-formats.md)

**Reference**:
- [Python API](docs/api-reference/python.md)
- [HTTP API](docs/api-reference/http.md)
- [CLI](docs/api-reference/cli.md)

**Contributing**:
- [Testing](docs/develop/testing.md)
- [Code Conventions](CLAUDE.md)

## License

Apache-2.0
