<p align="center">
  <h1 align="center">KohakuTerrarium</h1>
  <p align="center"><strong>Build self-contained agents that work alone. Wire them into teams that work together.</strong></p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-KohakuTerrarium--1.0-green" alt="License">
  <img src="https://img.shields.io/badge/version-0.2.0-orange" alt="Version">
</p>

---

KohakuTerrarium is built around one design choice: **vertical coordination (inside an agent) and horizontal coordination (between agents) are different problems, and they should stay separate**.

This is one of the first explicitly stated abstractions for what an "agent framework" actually needs to define: what an agent IS, how it RUNS, how it EXTENDS, and how it DEPLOYS. Most existing tools in the ecosystem (LangChain, DSPy, CrewAI, AutoGen) are useful but operate at different levels — they are LLM app libraries, optimizer/compiler layers, or multi-agent coordination patterns, not full agent frameworks. KohakuTerrarium aims to be the framework layer that those kinds of tools could be built on top of.

- A **creature** is a complete agent with its own LLM controller, tools, sub-agents, memory, triggers, input, and output. Even a standalone creature is already a multi-agent system — the controller delegates to sub-agents (explore, plan, worker, critic), the same frontier architecture used by systems like Claude Code.
- A **terrarium** is a **pure wiring layer** that connects creatures through channels, manages lifecycle, and exposes observability. It has no LLM, no reasoning, no intelligence — it is infrastructure, not another hidden planner or meta-agent.
- The same creature config can run **standalone** or inside a terrarium **unchanged**.
- **Five module types** (input, output, tool, trigger, sub-agent) form the extensibility primitive. Any functionality — RAG, monitoring, external integrations — can be composed from these modules. The framework doesn't need to ship every feature because the module system makes everything buildable.

That separation is the project's core idea, and it drives the runtime, the TUI, the web dashboard, the API, and the session system.

This abstraction is empirically validated: frontier agent systems including Claude Code, Codex CLI, OpenCode, and even real-time applications like Neuro-sama can all be expressed within the creature/module architecture. The abstraction holds; specialized runtimes handle domain-specific concerns like latency.

## Why KohakuTerrarium Is Different

<table>
  <tr>
    <td valign="top" width="50%">
      <strong>Inside a creature</strong><br>
      Vertical coordination<br>
      One controller delegates to tools and sub-agents.
    </td>
    <td valign="top" width="50%">
      <strong>Between creatures</strong><br>
      Horizontal coordination<br>
      Independent creatures communicate explicitly through channels.
    </td>
  </tr>
</table>

This gives you a cleaner split than frameworks that blur everything into one orchestration layer:

- **Reusable creatures**: build once, run solo or in teams
- **Opaque team members**: terrariums do not inspect creature internals
- **Explicit communication**: creatures collaborate via named channels, not hidden routing magic
- **Persistent by default**: sessions save rich runtime state, not just chat history
- **One runtime, many surfaces**: CLI, TUI, HTTP API, and web UI sit on the same underlying system
- **Shareable configs**: package and install creature / terrarium configs from Git or local sources

## Key Capabilities

Beyond the creature / terrarium philosophy, KohakuTerrarium already has a strong practical runtime surface:

- **Frontier-style built-in working set**: the default `general` creature ships with file, shell, search, JSON, HTTP, channel, trigger, and introspection tools, plus built-in sub-agents for exploration, planning, implementation, review, summarization, and research.
- **Non-blocking execution and compaction flow**: tools start immediately during LLM streaming, background jobs do not block the agent loop, and compaction / resume are built into the runtime instead of bolted on afterward.
- **Session history as operational memory**: `.kohakutr` session files persist conversations, events, jobs, tool metadata, sub-agent state, scratchpad state, channel history, and resumable triggers in a structured store rather than a flat transcript.

## Architecture at a Glance

### Terrarium view

```text
  +---------+       +---------------------------+
  |  User   |<----->|        Root Agent         |
  +---------+       |  (terrarium tools, TUI)   |
                    +---------------------------+
                          |               ^
            sends tasks   |               |  observes results
                          v               |
                    +---------------------------+
                    |     Terrarium Layer       |
                    |   (pure wiring, no LLM)   |
                    ├-------┬----------┬--------┤
                    |  swe  | reviewer |  ....  |
                    +-------┴----------┴--------+
```

### Creature view

```text
    List, Create, Delete  +------------------+
                    +-----|   Tools System   |
      +---------+   |     +------------------+
      |  Input  |   |          ^        |
      +---------+   V          |        v
        |   +---------+   +------------------+   +------------+
        +-->| Trigger |-->|    Controller    |-->| Sub Agents |
User input  | System  |   |    (Main LLM)    |<--| with tools |
            +---------+   +------------------+   +------------+
                ^             |          |
                |             v          v
                |         +--------+  +------+
                +---------|Channels|  |Output|
                 Receive  +--------+  +------+
                             |  ^
                             v  |
                          +------------------+
                          | Other Creatures  |
                          +------------------+
```

### Naming
- **Terrarium**: a contained world with two levels of meaning. For the creator, it is the world you build agents in. For the creatures, it is the world they live in — any agent architecture can inhabit this framework, and the terrarium layer mimics a small ecosystem where creatures interact through shared environment rather than direct control.
- **Creature**: something that *lives* in an environment, not just an API endpoint. The naming reinforces that KT thinks about agents as inhabitants of a world.

## Quick Start

```bash
# Install
git clone https://github.com/Kohaku-Lab/KohakuTerrarium.git
cd KohakuTerrarium
pip install -e .

# Install the default packaged creatures / terrariums
kt install https://github.com/Kohaku-Lab/kohaku-creatures.git

# Authenticate for the bundled SWE configs (uses ChatGPT subscription via Codex OAuth)
kt login codex

# Run a single creature
kt run @kohaku-creatures/creatures/swe

# Run a multi-agent terrarium (full TUI with tabs)
kt terrarium run @kohaku-creatures/terrariums/swe_team
```

The framework is not limited to Codex OAuth. It also supports OpenRouter, OpenAI, Anthropic, and Google Gemini APIs.

## Model Management

KohakuTerrarium ships with 50+ LLM presets covering OpenAI, Anthropic Claude, Google Gemini, Qwen, and others. Short aliases like `claude`, `gemini`, `gpt5` make switching easy.

```bash
# Authenticate with any supported provider
kt login codex          # ChatGPT subscription (OAuth)
kt login openrouter     # OpenRouter API key
kt login openai         # OpenAI API key
kt login anthropic      # Anthropic API key
kt login gemini         # Google Gemini API key

# Browse and set a default
kt model list
kt model default claude-sonnet-4.6

# Override per-run
kt run @kohaku-creatures/creatures/swe --llm gemini
```

Agent configs reference profiles by name:

```yaml
controller:
  llm: gpt-5.4          # profile name (recommended)
  temperature: 0.7       # inline overrides still work
```

Resolution order: `--llm` CLI flag, then config `llm` field, then default model, then inline fallback. API keys are stored in `~/.kohakuterrarium/api_keys.yaml`; profiles and the default model are stored in `~/.kohakuterrarium/llm_profiles.yaml`.

## Programmatic Usage

KohakuTerrarium is not only a CLI / TUI application. It is also a Python framework you can embed inside your own scripts, services, and backends.

### Use an agent inside your own script

```python
import asyncio

from kohakuterrarium.core.agent import Agent


async def main() -> None:
    agent = Agent.from_path("creatures/general")
    agent.set_output_handler(lambda text: print(text), replace_default=True)

    await agent.start()
    try:
        await agent.inject_input("Summarize what this framework is for.")
    finally:
        await agent.stop()


asyncio.run(main())
```

Use this style when you want to embed one creature inside an existing application and drive it directly from Python.

### Start and control a terrarium programmatically

```python
import asyncio

from kohakuterrarium.core.channel import ChannelMessage
from kohakuterrarium.terrarium.config import load_terrarium_config
from kohakuterrarium.terrarium.runtime import TerrariumRuntime


async def main() -> None:
    config = load_terrarium_config("terrariums/swe_team")
    runtime = TerrariumRuntime(config)

    await runtime.start()
    try:
        tasks = runtime.environment.shared_channels.get("tasks")
        if tasks is not None:
            await tasks.send(ChannelMessage(
                sender="user",
                content="Review the pagination logic for edge cases.",
            ))

        print(runtime.get_status())
        await runtime.run()
    finally:
        await runtime.stop()


asyncio.run(main())
```

Use this when you want the terrarium runtime as part of a Python workflow, automation script, or custom application loop.

### Build your own backend on top of `KohakuManager`

```python
import asyncio

from kohakuterrarium.serving.manager import KohakuManager


async def main() -> None:
    manager = KohakuManager(session_dir="./sessions")

    agent_id = await manager.agent_create(config_path="creatures/general")
    try:
        async for chunk in manager.agent_chat(agent_id, "What tools do you have?"):
            print(chunk, end="")
    finally:
        await manager.agent_stop(agent_id)


asyncio.run(main())
```

`KohakuManager` is the transport-agnostic serving layer behind the HTTP API. Use it if you want to design your own API server, worker process, or UI on top of the framework.

For more detail, see `docs/api-reference/python.md` and the examples in `examples/code/`.

## Core Concepts

### Creature

A creature is a standalone agent: its own controller, tools, sub-agents, memory, triggers, and I/O. You can run it directly with `kt run <path>`.

A creature is not a simple ReAct loop. It is a multi-agent system internally: the controller orchestrates, sub-agents execute specialized tasks in parallel, results feed back into the controller's decision-making. This is the same architecture as frontier systems like Claude Code.

### Terrarium

A terrarium connects creatures through shared channels, injects the wiring they need, and manages lifecycle and observability. It does **not** add another reasoning layer.

Think of it as a service mesh: routing, lifecycle, observability, but no business logic. Or think of it as a contained world — creatures live in it, interact through shared channels, but each creature is autonomous.

### Root Agent

A terrarium can optionally define a **root agent** that sits **outside** the terrarium and manages it through terrarium tools such as `terrarium_send`, `terrarium_observe`, `terrarium_status`, and the creature control tools.

### Channels

Channels are how creatures communicate:

- **Queue**: one consumer per message
- **Broadcast**: all subscribers receive every message

Sending is explicit via `send_message`; receiving happens through injected channel triggers.

### Modules

Everything extensible in KohakuTerrarium fits into one of five protocol-based module types:

| Module | What It Does | Example Custom Use |
|--------|-------------|-------------------|
| **Input** | Receives external events | Discord listener, webhook, voice input |
| **Output** | Delivers agent output | Discord sender, TTS, file writer |
| **Tool** | Executes actions | RAG retrieval, API calls, database queries |
| **Trigger** | Generates automatic events | Timer, channel watcher, condition monitor |
| **Sub-agent** | Delegated task execution | Any specialized reasoning task |

This is the extensibility mechanism. RAG is a custom input/trigger plus a tool. Monitoring is a trigger plus an output module. External integrations are tools plus triggers. The framework doesn't need to ship every feature because the module system makes everything composable.

### Sessions and Isolation

- **Environment**: shared terrarium state, especially shared channels
- **Session**: private creature state, including scratchpad and sub-agent state

That keeps team communication shared while creature internals stay private.

## Session Persistence

Every session is automatically saved to `~/.kohakuterrarium/sessions/` unless disabled.

Resume anytime:

```bash
kt resume                    # list recent, pick interactively
kt resume --last             # most recent session
kt resume swe_team           # prefix match
```

Session files use the `.kohakutr` format and contain far more than a plain transcript — they capture operational state:

- conversation history
- full tool call metadata
- append-only event log
- scratchpad state
- token usage
- sub-agent conversations
- channel messages
- job records
- resumable triggers
- config and topology metadata

Sessions are also searchable. The `search_memory` tool gives agents keyword and semantic search over their own history, and the CLI exposes the same capability:

```bash
kt search my_session "how did we fix the auth bug"    # hybrid (FTS + vector)
kt search my_session "database error" --mode fts      # keyword only
kt embedding my_session                               # build vector index
```

## Runtime Surfaces

### TUI (Terminal UI)

Full-screen Textual app with:

- **Terrarium tabs**: root agent, each creature, each channel
- **Accordion tools**: collapsible blocks showing tool name, args, and output
- **Right panel**: running tasks, scratchpad viewer, session info, terrarium overview
- **Escape to interrupt**: cancels current LLM generation while keeping the agent alive
- **Sub-agent nesting**: tool lines appear inside sub-agent accordion blocks
- **Shared model with web UI**: the TUI and web dashboard present the same runtime concepts

### Web Dashboard

Vue 3 frontend with real-time streaming:

```bash
pip install -e ".[web]"
python -m kohakuterrarium.api.main        # API on :8001
npm run dev --prefix src/kohakuterrarium-frontend     # Frontend on :5173
```

Features:

- topology graph
- multi-tab chat
- tool accordion
- running tasks panel
- session resume
- channel message feed
- token tracking
- dark / light mode

### Interrupt System

Interruption exists across all interfaces:

- **TUI**: `Escape`
- **Web**: stop button or `Escape`
- **API**: `POST /api/agents/{id}/interrupt` or `POST /api/terrariums/{id}/creatures/{name}/interrupt`
- **Tools**: `stop_task` cancels a background tool or sub-agent by job ID
- **Root agent**: `creature_interrupt` interrupts a creature without stopping it

## Package System

Share and install creature / terrarium configs:

```bash
# Install from git
kt install https://github.com/someone/cool-creatures.git

# Install local (editable, for development)
kt install ./my-creatures -e

# List installed packages
kt list

# Run from a package
kt run @cool-creatures/creatures/my-agent
kt terrarium run @cool-creatures/terrariums/my-team

# Edit a config
kt edit @kohaku-creatures/creatures/general
```

Packages use `@package-name/path` references for cross-package inheritance:

```yaml
# config.yaml
base_config: "@kohaku-creatures/creatures/swe"
```

A package typically looks like this:

```text
my-package/
  kohaku.yaml
  creatures/
    my-agent/
      config.yaml
      prompts/
  terrariums/
    my-team/
      terrarium.yaml
```

## Default Creatures and Terrariums

The repository includes default configs under `creatures/` and `terrariums/`, and the same defaults are also distributed as the installable `kohaku-creatures` package.

### Creatures

| Creature | Description |
|----------|-------------|
| `general` | Base creature with 21 built-in tools, 6 built-in sub-agents, and the core prompt / workflow style |
| `swe` | Software engineering specialist with coding workflow and git safety rules |
| `reviewer` | Code review specialist with structured severity-based feedback |
| `ops` | Infrastructure and operations specialist |
| `researcher` | Research and analysis specialist |
| `creative` | Creative writing specialist |
| `root` | Terrarium orchestration and delegation specialist |

### Terrarium

| Terrarium | Description |
|-----------|-------------|
| `swe_team` | A software engineering team with a root orchestrator, an implementing `swe` creature, and a `reviewer` creature |

`swe_team` is wired roughly like this:

```text
tasks -> swe -> review -> reviewer -> feedback / results
              \______________________________/
                     team_chat (broadcast)
```

## Built-in Tools and Sub-Agents

### General built-in tools

The default `general` creature ships with 21 built-in tools:

| Tool | Description |
|------|-------------|
| `bash` | Execute shell commands when no dedicated structured tool is a better fit |
| `python` | Execute Python code and return its output |
| `read` | Read file contents safely before editing |
| `write` | Create or overwrite files |
| `edit` | Modify files via search/replace or unified diff |
| `glob` | Find files by glob pattern |
| `grep` | Search file contents with regex patterns |
| `tree` | Show directory structure as a tree |
| `think` | Record an explicit reasoning step that stays in context |
| `scratchpad` | Read and write session-scoped working memory |
| `search_memory` | Search session history with keyword or semantic matching |
| `info` | Load full documentation for a tool or sub-agent |
| `ask_user` | Ask the user a question mid-execution |
| `http` | Make HTTP requests to APIs and web pages |
| `json_read` | Read and query JSON files |
| `json_write` | Modify JSON files at specific paths |
| `send_message` | Send a message to a named channel |
| `wait_channel` | Wait for a message on a named channel |
| `stop_task` | Cancel a running background tool or sub-agent by job ID |
| `list_triggers` | Inspect active triggers on the current agent |
| `create_trigger` | Create timer, scheduler, or channel triggers dynamically |

### Terrarium management tools

The root agent is force-given the terrarium management surface for operating a team:

| Tool | Description |
|------|-------------|
| `terrarium_create` | Create and start a terrarium from a config path |
| `terrarium_status` | Inspect a running terrarium or list running terrariums |
| `terrarium_stop` | Stop a running terrarium and all its creatures |
| `terrarium_send` | Send a message into a terrarium channel |
| `terrarium_observe` | Subscribe to a terrarium channel and receive messages as future events |
| `terrarium_history` | Read recent terrarium channel history |
| `creature_start` | Hot-add a creature to a running terrarium |
| `creature_stop` | Stop and remove a creature from a running terrarium |
| `creature_interrupt` | Interrupt a creature's current processing without removing it |

### Built-in sub-agents

The default `general` creature also includes 6 built-in sub-agents:

| Sub-agent | Description |
|-----------|-------------|
| `explore` | Search and explore the codebase in read-only mode |
| `plan` | Create implementation plans and design decisions |
| `worker` | Implement code changes, fix bugs, and refactor |
| `critic` | Review and critique code, plans, or outputs |
| `summarize` | Condense long content into concise summaries |
| `research` | Perform deeper research using files and web access |

## API

KohakuTerrarium includes a FastAPI application plus WebSocket endpoints for managing standalone agents and terrariums.

### REST surface

| Category | Endpoints |
|----------|-----------|
| Agents | create, list, get, stop, interrupt, history, jobs, chat, stop task |
| Terrariums | create, list, get, stop, channels, add channel, history, chat |
| Creatures | list, add, remove, interrupt, wire, jobs, stop task |
| Channels | list, send |
| Sessions | list, resume, delete |
| Config Discovery | `/api/configs/creatures`, `/api/configs/terrariums` |

### WebSocket surface

| Endpoint | Purpose |
|----------|---------|
| `/ws/terrariums/{id}` | Unified terrarium event stream: root, creatures, and channels |
| `/ws/creatures/{id}` | Unified standalone creature event stream |
| `/ws/terrariums/{id}/channels` | Channel-focused WebSocket stream |
| `/ws/agents/{id}/chat` | Standalone agent chat stream |

The HTTP API and web dashboard are application layers built on top of the serving layer in `src/kohakuterrarium/serving/`.

## CLI Reference

| Command | Description |
|---------|-------------|
| `kt run <path> [--llm profile] [--mode cli\|tui]` | Run a single creature / agent |
| `kt terrarium run <path>` | Run a multi-agent terrarium with TUI |
| `kt terrarium info <path>` | Show terrarium config details |
| `kt resume [session] [--last]` | Resume a session (interactive picker if no arg) |
| `kt login <provider>` | Authenticate (codex, openrouter, openai, anthropic, gemini) |
| `kt model list` | Show available LLM profiles and presets |
| `kt model default <name>` | Set the default model |
| `kt model show <name>` | Show details for a profile |
| `kt search <session> <query>` | Search session memory (keyword / semantic) |
| `kt embedding <session>` | Build embedding index for a session |
| `kt install <source> [-e]` | Install a creature / terrarium package |
| `kt uninstall <name>` | Remove a package |
| `kt list` | Show installed packages and agents |
| `kt edit <@pkg/path>` | Edit a config in `$EDITOR` |
| `kt info <path>` | Show agent config details |

## Project Structure

```text
src/kohakuterrarium/
  core/           # Agent runtime, controller, executor, events, environment
  terrarium/      # Multi-agent runtime, config loading, hot-plug, topology wiring
  builtins/       # Built-in tools, sub-agents, I/O modules, TUI, slash commands
  builtin_skills/ # Markdown skill manifests for on-demand tool/subagent docs
  session/        # Session persistence (.kohakutr files), memory search, embeddings
  serving/        # Transport-agnostic service manager and event streaming
  api/            # FastAPI HTTP + WebSocket server (REST routes, WS handlers)
  modules/        # Plugin protocols: input, output, tool, trigger, user_command
  llm/            # LLM providers, profiles (50+ presets), API key management
  parsing/        # Tool-call parsing and stream handling
  prompt/         # Prompt assembly, aggregation, plugins, skill loading
  testing/        # Test infrastructure (ScriptedLLM, OutputRecorder, TestAgentBuilder)
  packages.py     # Package manager for kt install / resolve

src/kohakuterrarium-frontend/  # Vue 3 web frontend (Vite + Element Plus + Pinia)

kohaku-creatures/ # Installable package form of the default configs
examples/         # Example agent apps, terrariums, and code samples
docs/             # Concepts, architecture, guides, API reference
```

## Documentation Map

If you want more detail after the README:

- `docs/guide/getting-started.md` — installation, authentication, first agent
- `docs/guide/configuration.md` — creature and terrarium YAML reference
- `docs/concepts/overview.md` — core abstractions and why the split exists
- `docs/concepts/agents.md` — agent framework internals and execution model
- `docs/api-reference/http.md` — HTTP and WebSocket API reference
- `docs/api-reference/cli.md` — CLI reference

## License

[KohakuTerrarium License 1.0](LICENSE): based on Apache-2.0 with naming and attribution requirements.

- Derivative works must include `Kohaku` or `Terrarium` in their name
- Derivative works must provide visible attribution with a link to this project

Copyright 2024-2026 Shih-Ying Yeh (KohakuBlueLeaf) and contributors
