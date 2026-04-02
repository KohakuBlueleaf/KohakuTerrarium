<p align="center">
  <h1 align="center">KohakuTerrarium</h1>
  <p align="center">Build agents that work alone. Compose them into teams that work together.</p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-Apache--2.0-green" alt="License">
</p>

---

KohakuTerrarium is a Python framework for building AI agents and multi-agent teams. It ships with ready-to-use agents, a web dashboard, and persistent sessions, so you can start working immediately, resume where you left off, or build your own.

**What makes it different:** two levels of composition that solve different problems.

- **Creature** (single agent): self-contained with its own LLM, tools, sub-agents, and memory. Handles task decomposition internally. Works standalone.
- **Terrarium** (multi-agent team): wires multiple creatures together via channels. Pure routing, no intelligence. Creatures don't know they're in a terrarium.

Build agents individually. Test them standalone. Place them in a terrarium to collaborate. The same creature config works in both contexts.

## Quick Start

```bash
git clone https://github.com/Kohaku-Lab/KohakuTerrarium.git
cd KohakuTerrarium
uv pip install -e .

# Authenticate with ChatGPT (uses your Plus/Pro subscription)
kt login codex

# Run a coding assistant
kt run examples/agent-apps/swe_agent

# Run with TUI
kt run examples/agent-apps/swe_agent_tui

# Run a multi-agent team
kt terrarium run terrariums/swe_team/

# Resume a previous session
kt resume .kohaku/sessions/swe_agent_*.kt
```

**Other providers:** Set `OPENROUTER_API_KEY` and override `controller.model` / `controller.base_url` in your creature config to use any OpenAI-compatible API.

## Why Two Levels?

Most multi-agent frameworks force a choice: hierarchical (one boss, many workers) or peer-to-peer (everyone equal). Both break down at scale.

```
    Vertical (inside a creature)       Horizontal (between creatures)

         Controller                  swe  <-------->  reviewer
         /       \                     |                  |
    sub-agent  sub-agent            channels           channels
                                       |                  |
    Hierarchical delegation         researcher <---> creative
    for task decomposition
                                   Peer collaboration
                                   for multi-role teams
```

**Vertical** handles task decomposition within one agent. The controller delegates to sub-agents (explore, plan, worker, critic). This is internal and invisible to the outside.

**Horizontal** handles collaboration between independent agents. Creatures communicate through named channels (queue for point-to-point, broadcast for group). This is the terrarium layer.

The boundary is clean: a creature does not know it is in a terrarium.

## Pre-Built Creatures

Every creature inherits from `general` and adds domain expertise. Create your own agent in 5 lines of YAML.

| Creature | Domain | What It Adds |
|----------|--------|-------------|
| **general** | Foundation | 18 tools, 6 sub-agents, core personality |
| **swe** | Software engineering | Coding workflow, git safety, test validation |
| **reviewer** | Code review | Severity levels, structured findings, verdict |
| **ops** | Infrastructure | CI/CD, deployment, monitoring, rollback planning |
| **researcher** | Research | Source evaluation, citations, multi-source methodology |
| **creative** | Writing | Two-mode operation (workshop vs. writing), craft principles |
| **root** | Orchestration | 8 terrarium management tools, delegation workflow |

```yaml
# Your agent in 3 lines: inherit everything, override what you need
name: my_agent
base_config: creatures/swe
controller:
  model: gpt-5.4
  auth_mode: codex-oauth
  tool_format: native
```

Tools extend, prompts concatenate, scalars override. See the [Creatures Guide](docs/guide/creatures.md).

## Terrarium: Multi-Agent Teams

A terrarium config wires creatures together with channels. No creature config changes needed.

```yaml
terrarium:
  name: swe_team

  root:
    base_config: creatures/root
    controller:
      model: gpt-5.4
      auth_mode: codex-oauth
      tool_format: native

  creatures:
    - name: swe
      base_config: creatures/swe
      channels:
        listen: [tasks, feedback, team_chat]
        can_send: [review, team_chat]

    - name: reviewer
      base_config: creatures/reviewer
      channels:
        listen: [review, team_chat]
        can_send: [feedback, results, team_chat]

  channels:
    tasks:      { type: queue, description: "Task assignments" }
    review:     { type: queue, description: "Code for review" }
    feedback:   { type: queue, description: "Review feedback" }
    results:    { type: queue, description: "Approved results" }
    team_chat:  { type: broadcast, description: "Team coordination" }
```

Every creature automatically gets a direct channel named after it. The root agent sits **outside** the terrarium, managing it via tools. The user talks to root; root orchestrates the team.

## The Root Agent Pattern

```
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

The root agent delegates work, watches for results, and reports back. It never does the work itself. Background tools (`terrarium_observe`) set up persistent channel subscriptions that fire as trigger events when messages arrive. The agent stays idle between events.

## Architecture

```

    List, Create, Delete  +------------------+
                    +-----|   Tools System   |
      +---------+   |     +------------------+
      |  Input  |   |          ^        |
      +---------+   V          |        v
        |   +---------+   +------------------+   +------------+
        +-->| Trigger |-->|    Controller    |-->| Sub Agents |
User input  | System  |   |    (Main LLM)    |<--| with tools |
            +---------+   +------------------+   +------------+
                ^             |          ^
                |             v          |
                |         +--------+  +------+
                +---------|Channels|  |Output|
                 Receive  +--------+  +------+
                             |  ^
                             v  |
                          +------------------+
                          | Other Creatures  |
                          +------------------+
```


Three concurrent event sources drive every agent:

| Source | How it works |
|--------|-------------|
| **Input loop** | Blocks on user input, fires `_process_event` |
| **Trigger tasks** | Timer, channel message, or custom triggers fire `_process_event` directly |
| **Background tools** | Executor callback fires `_process_event` when done |

A processing lock serializes all three. Direct tools return results in the same turn. Background tools return a placeholder and deliver results as trigger events later.

## Session Persistence & Resume

Every session can be saved to a `.kt` file (SQLite via KohakuVault) and resumed later.

```bash
# Start with session recording
kt run examples/agent-apps/swe_agent --session

# Resume right where you left off
kt resume .kohaku/sessions/swe_agent_*.kt

# Inspect a session
python scripts/inspect_session.py session.kt --all
python scripts/inspect_session.py session.kt --search "auth bug"
```

What gets saved: conversation history (with full tool_calls metadata), event log, scratchpad state, token usage, sub-agent conversations, channel messages. Everything stored as native Python objects via msgpack, no JSON serialization layer.

## Web Dashboard

A Vue 3 web frontend for managing agents and terrariums in real-time.

```bash
# Start API server
cd KohakuTerrarium && python -m apps.api.main

# Start frontend dev server
cd apps/web && npm install && npm run dev
```

Features: terrarium topology graph, multi-tab chat (root + creatures + channels), real-time streaming, sub-agent tool activity, channel message feed, token usage tracking, dark/light mode with gemstone color theme.

## Built-in Tools

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
| `info` | Load tool/sub-agent docs | `list_triggers` | Show active triggers |

**Terrarium tools** (root agent): `terrarium_create`, `terrarium_status`, `terrarium_stop`, `terrarium_send`, `terrarium_observe`, `terrarium_history`, `creature_start`, `creature_stop`

## Built-in Sub-Agents

| Sub-Agent | Purpose | Sub-Agent | Purpose |
|-----------|---------|-----------|---------|
| `explore` | Search codebase (read-only) | `coordinator` | Multi-agent via channels |
| `plan` | Create implementation plans | `memory_read` | Retrieve from memory |
| `worker` | Implement changes (read-write) | `memory_write` | Store to memory |
| `critic` | Review and critique | `response` | Generate user responses |
| `summarize` | Condense long content | `research` | Web + file research |

## Interfaces

| Interface | Description |
|-----------|-------------|
| **CLI** | `kt run`, `kt resume`, `kt terrarium run`, `kt login codex` |
| **TUI** | Full terminal UI with inline tool display and status panel |
| **HTTP API** | FastAPI with 18 REST + 4 WebSocket endpoints |
| **Web Dashboard** | Vue 3 real-time UI with topology graph and multi-agent chat |
| **Python API** | `Agent.from_path()`, `TerrariumRuntime`, `SessionStore` |

## Key Features

- **Any LLM provider**: OpenAI, OpenRouter, Codex OAuth (ChatGPT subscription). Any OpenAI-compatible API.
- **Native tool calling**: OpenAI function calling API with automatic format-aware prompts. Also supports bracket and XML formats.
- **Config inheritance**: `base_config` field merges tools, concatenates prompts, overrides scalars. Multi-level inheritance supported.
- **Session persistence**: `.kt` files store full conversation history, tool calls, sub-agent internals, channel messages. Resume anytime.
- **Trigger system**: Timer, channel, context, and custom triggers. Tools can set up persistent triggers at runtime via TriggerManager.
- **Background tools**: Tools declaring BACKGROUND mode run asynchronously. Results delivered as trigger events. Agent stays responsive.
- **Hot-plug**: Add/remove creatures and channels to running terrariums.
- **Token tracking**: Per-LLM-call usage tracking from API responses, displayed in web UI per creature.
- **TUI**: Full terminal UI with inline tool display, status panel, and KohakUwU animation.
- **HTTP API**: FastAPI with 18 REST + 4 WebSocket endpoints. Unified WebSocket per terrarium.
- **Web frontend**: Vue 3 dashboard with topology graph, real-time streaming, gemstone theme.

## Project Structure

```
creatures/     Pre-built creature templates (general, swe, reviewer, ops, researcher, creative, root)
terrariums/    Pre-built terrarium templates (swe_team)
examples/      Example agent apps and terrariums
apps/api/      FastAPI HTTP API (REST + WebSocket)
apps/web/      Vue 3 web frontend (Vite + Element Plus + UnoCSS + Vue Flow)
docs/          Guide, concepts, architecture, API reference
scripts/       Utility scripts (inspect_session.py, dep_graph.py)

src/kohakuterrarium/
  core/        Agent, controller, executor, trigger_manager, events, sessions
  bootstrap/   Agent initialization factories (llm, tools, io, subagents, triggers)
  modules/     Protocols: input, trigger, tool, output, subagent
  terrarium/   Multi-agent runtime: config, factory, persistence, hot-plug, observer
  serving/     KohakuManager, AgentSession, event streaming
  session/     SessionStore (KohakuVault), resume, persistent event recording
  builtins/    Tool/subagent catalogs, tools, sub-agents, inputs, outputs
  parsing/     Stream parser (bracket, XML, native tool calling)
  prompt/      System prompt aggregation + Jinja2 templating
  llm/         LLM providers (OpenAI/OpenRouter/Codex OAuth)
```

## Documentation

**Guide** (build with the framework):
[Getting Started](docs/guide/getting-started.md) |
[Configuration](docs/guide/configuration.md) |
[Creatures](docs/guide/creatures.md) |
[Examples](docs/guide/example-agents.md)

**Concepts**:
[Creatures](docs/concept/creature.md) |
[Terrarium](docs/concept/terrarium.md) |
[Channels](docs/concept/channels.md) |
[Environment](docs/concept/environment.md) |
[Tool Formats](docs/concept/tool-formats.md)

**Reference**:
[Python API](docs/api-reference/python.md) |
[HTTP API](docs/api-reference/http.md) |
[CLI](docs/api-reference/cli.md)

**Architecture**:
[Framework](docs/architecture/framework.md) |
[Execution Model](docs/architecture/execution-model.md) |
[Terrarium Runtime](docs/architecture/terrarium-runtime.md) |
[Serving Layer](docs/architecture/serving.md)

## License

Apache-2.0
