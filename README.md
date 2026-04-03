<p align="center">
  <h1 align="center">KohakuTerrarium</h1>
  <p align="center">Build agents that work alone. Compose them into teams that work together.</p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-KohakuTerrarium--1.0-green" alt="License">
  <img src="https://img.shields.io/badge/version-0.2.0-orange" alt="Version">
</p>

---

KohakuTerrarium is a Python framework for building AI agents and multi-agent teams, with persistent sessions, a full-screen TUI, a web dashboard, and a package system for sharing agent configs.

**Two levels of composition:**

- **Creature** (single agent): self-contained with its own LLM, tools, sub-agents, and memory. Works standalone.
- **Terrarium** (multi-agent team): wires creatures together via channels. Pure routing, no intelligence. Creatures don't know they're in a terrarium.

Build agents individually. Test them standalone. Place them in a terrarium to collaborate. The same creature config works in both contexts.

## Quick Start

```bash
# Install
git clone https://github.com/Kohaku-Lab/KohakuTerrarium.git
cd KohakuTerrarium
pip install -e .

# Install default creatures
kt install https://github.com/Kohaku-Lab/kohaku-creatures.git

# Authenticate (uses ChatGPT subscription)
kt login codex

# Run a single agent
kt run @kohaku-creatures/creatures/swe

# Run a multi-agent team (full TUI with tabs)
kt terrarium run @kohaku-creatures/terrariums/swe_team
```

## Features

### Session Persistence

Every session is automatically saved to `~/.kohakuterrarium/sessions/`. Resume anytime:

```bash
kt resume                    # list recent, pick interactively
kt resume --last             # most recent session
kt resume swe_team           # prefix match
```

What gets saved: conversation history (with full tool_calls metadata), event log, scratchpad state, token usage, sub-agent conversations, channel messages, resumable triggers.

### TUI (Terminal UI)

Full-screen Textual app with:

- **Terrarium tabs**: root agent, each creature, each channel (same as web frontend)
- **Accordion tools**: collapsible blocks showing tool name, args, output
- **Right panel**: running tasks (live), scratchpad viewer, session info, terrarium overview
- **Escape to interrupt**: cancels LLM generation, agent stays alive
- **Sub-agent nesting**: tool lines inside sub-agent accordion
- **Gemstone colors**: iolite, taaffeite, aquamarine, amber, sapphire

### Web Dashboard

Vue 3 frontend with real-time streaming:

```bash
pip install -e ".[web]"
python -m apps.api.main        # API on :8001
cd apps/web && npm run dev     # Frontend on :5173
```

Features: topology graph, multi-tab chat, tool accordion, running tasks panel, session resume, channel message feed, token tracking, dark/light mode.

### Package System

Share and install creature/terrarium configs:

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

### Default Creatures (kohaku-creatures)

| Creature | Description |
|----------|-------------|
| `general` | Base: 19 tools, 6 sub-agents, core personality |
| `swe` | Software engineering (coding workflow, git safety) |
| `reviewer` | Code review (severity levels, structured feedback) |
| `ops` | Infrastructure and operations |
| `researcher` | Research and analysis |
| `creative` | Creative writing |
| `root` | Terrarium management and task delegation |

Terrarium: `swe_team` (root orchestrates, swe implements, reviewer approves)

### Tools

**19 general tools**: bash, python, read, write, edit, glob, grep, tree, think, scratchpad, send_message, wait_channel, http, ask_user, json_read, json_write, info, list_triggers, stop_task

**8 terrarium tools** (root agent): terrarium_create, terrarium_status, terrarium_stop, terrarium_send, terrarium_observe, terrarium_history, creature_start, creature_stop, creature_interrupt

### Interrupt System

- **TUI**: Escape key interrupts current LLM generation
- **Web**: Stop button (red) or Escape key
- **API**: `POST /api/agents/{id}/interrupt` or `POST /api/terrariums/{id}/creatures/{name}/interrupt`
- **Tools**: `stop_task` cancels background tools/sub-agents by job ID
- **Root agent**: `creature_interrupt` tool interrupts a creature's processing

### API

REST + WebSocket endpoints for managing agents and terrariums:

| Category | Endpoints |
|----------|-----------|
| Agents | create, list, get, stop, interrupt, history, jobs, chat, stop task |
| Terrariums | create, list, get, stop, channels, creatures, history, chat |
| Creatures | list, add, remove, interrupt, wire, jobs, stop task |
| Sessions | list, resume, delete |
| WebSocket | `/ws/terrariums/{id}`, `/ws/creatures/{id}` |

## CLI Reference

| Command | Description |
|---------|-------------|
| `kt run <path>` | Run a single agent |
| `kt terrarium run <path>` | Run a multi-agent team with TUI |
| `kt resume [session]` | Resume a session (interactive picker if no arg) |
| `kt install <source> [-e]` | Install creature/terrarium package |
| `kt uninstall <name>` | Remove a package |
| `kt list` | Show installed packages and agents |
| `kt edit <@pkg/path>` | Edit a config in $EDITOR |
| `kt login codex` | Authenticate with ChatGPT |
| `kt logs [session]` | View session events |
| `kt info <path>` | Show agent config details |

## Architecture

```
User <-> Root Agent (creature with terrarium tools)
              |
              v  (creates, manages, observes via tools)
         +-----------+
         | Terrarium |  <-- pure wiring, no intelligence
         +-----------+
         | swe | reviewer | ... |  <-- opaque creatures
```

**Vertical** (inside creature): controller delegates to sub-agents (private, hierarchical)
**Horizontal** (terrarium): creatures communicate via channels (peer, opaque)

## Project Structure

```
src/kohakuterrarium/
  core/           # Agent, controller, executor, events, session
  terrarium/      # Multi-agent runtime, config, hot-plug
  builtins/       # Tools, sub-agents, inputs, outputs, TUI
  session/        # Session persistence (.kohakutr files)
  serving/        # HTTP API serving layer
  modules/        # Plugin protocols (input, output, tool, trigger)
  llm/            # LLM providers (OpenAI, Codex OAuth)
  packages.py     # Package manager (kt install)

apps/
  api/            # FastAPI HTTP + WebSocket server
  web/            # Vue 3 frontend

kohaku-creatures/ # Default creatures + terrariums (submodule)
```

## License

[KohakuTerrarium License 1.0](LICENSE): based on Apache-2.0 with naming and attribution requirements.

- Derivative works must include "Kohaku" or "Terrarium" in their name
- Must provide visible attribution with link to this project

Copyright 2024-2026 Shih-Ying Yeh (KohakuBlueLeaf) and contributors
