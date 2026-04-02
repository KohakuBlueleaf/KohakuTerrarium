# KohakuTerrarium

A universal agent framework for building any type of fully self-driven agent system.

## Project Overview

KohakuTerrarium is a Python framework that enables building any kind of agent system - from SWE agents like Claude Code to conversational bots like Neuro-sama to autonomous monitoring systems. The name "Terrarium" reflects how the framework allows you to build different self-contained agent ecosystems.

## Code Conventions

### File Organization
- Source code: `src/kohakuterrarium/`
- Creature templates: `creatures/`
- Terrarium templates: `terrariums/`
- Examples: `examples/` (agent-apps, terrariums, code)
- Documentation: `docs/`
- Ideas/discussions: `ideas/`
- Max lines per file: 600 (hard max: 1000)
- Highly modularized - one responsibility per module

### Import Rules
1. No imports inside functions (except for cycle import or bad init avoidance)
2. Import grouping order:
   - Built-in modules
   - Third-party packages
   - KohakuTerrarium modules
3. Import ordering within groups:
   - `import` statements before `from` imports
   - Shorter paths before longer paths (by dot count)
   - Alphabetical order (a-z)

### Python Style
- Target: Python 3.10+ (may use 3.11/3.12 features, can disable 3.10 later)
- Use modern type hints: `list`, `tuple`, `dict`, `X | None` (NOT `List`, `Tuple`, `Dict`, `Optional`, `Union`)
- Prefer `match-case` over deeply nested `if-elif-else`
- Full asyncio throughout (mark sync modules as "require blocking" or "can be to_thread")
- Practical dependencies allowed (pydantic, httpx, rich, etc.)

### Development Setup
- Use `uv pip install -e .` for editable install
- **Never use `sys.path.insert` hacks** in examples or tests - always rely on proper package install
- Examples and tests should import from `kohakuterrarium.*` directly

### Logging (No print!)
- **Avoid naive `print()` in library code** - use structured logging
- Use custom logger based on `logging` module (NOT loguru)
- Format: `[HH:MM:SS] [module.name] [LEVEL] message`
- Color coding: DEBUG=gray, INFO=green, WARNING=yellow, ERROR=red
- **Avoid reserved LogRecord attributes** in extra kwargs: `name`, `msg`, `args`, `levelname`, `levelno`, `pathname`, `filename`, `module`, `lineno`, `funcName`, `created`, `msecs`, `relativeCreated`, `thread`, `threadName`, `process`, `processName`, `message`
- Exception: Test suites (`tests/`) can use simpler output

## Core Architecture Concepts (CRITICAL)

### Creature vs Terrarium vs Root Agent

**Creature**: A self-contained agent. Has its own LLM, tools, sub-agents, memory, I/O.
Works standalone. Does NOT know it is in a terrarium. Sub-agents inside a creature
are VERTICAL hierarchy (internal delegation, invisible to outside).

**Terrarium**: Pure wiring layer. NO LLM, NO intelligence, NO decision-making.
Loads standalone creature configs (unchanged), creates channels between them,
injects ChannelTriggers, manages lifecycle. That's ALL it does.

**Root Agent**: A creature that sits OUTSIDE the terrarium. Has terrarium management
tools (create, stop, send, observe, hot-plug). The user talks to root; root orchestrates
the terrarium from above. Root is NEVER a peer of terrarium creatures.

```
User <-> Root Agent (creature with terrarium tools)
              |
              v  (creates, manages, observes via tools)
         +-----------+
         | Terrarium |  <-- pure wiring, no intelligence
         +-----------+
         | swe | reviewer | ... |  <-- opaque creatures
```

**Two composition levels (never mix them):**
- VERTICAL (inside creature): controller -> sub-agents (private, hierarchical)
- HORIZONTAL (terrarium): creature <-> creature via channels (peer, opaque)

### Terrarium Config: Optional Root

```yaml
terrarium:
  root:                    # Optional: root agent sits OUTSIDE
    config: creatures/root
    interface: tui
  creatures: [...]         # These run INSIDE the terrarium
  channels: [...]
```

When root is present, it is force-given all terrarium tools and bound to this
terrarium's runtime. It is the user-facing interface.

## Architecture Overview

### Key Design Principle: Controller as Orchestrator

**The controller's role is to dispatch tasks, not to do heavy work itself.**

- Controller outputs should be SHORT: tool calls, sub-agent dispatches, status updates
- Long outputs (user-facing content) should come from **output sub-agents**
- This keeps controller lightweight, fast, and focused on decision-making

### Five Major Systems
1. **Input** - Explicit input that triggers the agent (user request, ASR, group chat message)
2. **Trigger** - Automatic system that triggers agent (timers, events, conditions, composites)
3. **Controller** - Main LLM that **orchestrates** - dispatches tasks, makes decisions
4. **Tool Calling** - Background execution of tools/sub-agents (non-blocking)
5. **Output** - Final output routing (stdout, file, TTS stream, API)

### Unified Event Model

Everything flows through `TriggerEvent` (defined in `core/events.py`):
- Input completion → TriggerEvent
- Timer/condition triggers → TriggerEvent
- Tool completion → TriggerEvent
- Sub-agent output → TriggerEvent

Stackable events can be batched when occurring simultaneously.

### Key Concepts
- **Sub-agents**: Nested agents with own controller + tools
  - Default: output to parent controller only
  - **Output sub-agent**: `output_to: external` - can stream directly to user
  - **Interactive sub-agent**: `interactive: true` - stays alive, receives context updates
- **Skills**: Procedural knowledge ("how to do something")
- **Tools**: Executable functions with documentation ("how to call, what happens")
- **First-citizen memory**: Folder with txt/md files, read-write (some can be protected)

### Tool Execution Modes
1. **Direct/Blocking**: Complete all jobs, return results
2. **Background**: Periodic status updates, context refresh
3. **Stateful**: Multi-turn interaction (like Python generators with yield)

## Configuration Format

- **JSON/YAML/TOML**: Overall setup (controller, input, trigger, tools, output modules)
- **Markdown**: System prompts with Jinja-like templating
- **Call syntax**: Configurable format (short, easy to parse, state-machine friendly)

## Project Structure

```
src/kohakuterrarium/
├── core/                    # Core abstractions and runtime
│   ├── agent.py             # Agent class - orchestrates everything
│   ├── controller.py        # Controller - LLM conversation loop + event queue
│   ├── conversation.py      # Context management, compaction
│   ├── executor.py          # Background job runner
│   ├── job.py               # Job status tracking
│   ├── events.py            # TriggerEvent + related event types
│   ├── config.py            # Config loading
│   └── registry.py          # Module registration
│
├── bootstrap/               # Agent initialization factories
│   ├── llm.py              # LLM provider creation
│   ├── tools.py            # Tool loading and registration
│   ├── io.py               # Input/output module creation
│   ├── subagents.py        # Sub-agent config loading
│   └── triggers.py         # Trigger module creation
│
├── builtins/                # Built-in implementations
│   ├── tool_catalog.py     # Global builtin tool lookup (leaf module, deferred loaders)
│   ├── subagent_catalog.py # Global builtin sub-agent lookup (leaf module)
│   ├── tools/              # 18 general + 8 terrarium tool classes
│   ├── inputs/             # cli, whisper, none
│   ├── outputs/            # stdout, tts
│   └── subagents/          # Sub-agent configs
│
├── modules/                 # Plugin API for devs
│   ├── input/               # Produces TriggerEvent(type="user_input")
│   ├── trigger/             # Produces TriggerEvent(type=...)
│   ├── tool/                # On complete → TriggerEvent(type="tool_complete")
│   ├── output/              # State machine router + output modules
│   └── subagent/            # Sub-agent lifecycle management
│
├── session/                 # Session persistence (KohakuVault-backed)
│   ├── store.py             # SessionStore - 9 tables in one .kohakutr file
│   ├── output.py            # SessionOutput - captures events via OutputModule
│   └── resume.py            # Resume agent/terrarium from .kohakutr file
│
├── serving/                 # HTTP API serving layer
│   ├── manager.py           # KohakuManager - agent/terrarium lifecycle
│   └── agent_session.py     # AgentSession - streaming chat wrapper
│
├── terrarium/               # Multi-agent runtime
│   ├── runtime.py           # TerrariumRuntime - lifecycle orchestration
│   ├── factory.py           # Creature/root agent construction
│   ├── persistence.py       # Session store attachment + resume helpers
│   ├── tool_registration.py # Deferred terrarium tool loading
│   ├── config.py            # Terrarium config loading + topology prompt
│   └── hotplug.py           # Add/remove creatures and channels at runtime
│
├── parsing/                 # Stream parsing (state machine)
├── commands/                # Framework commands (##read##, ##info##)
├── llm/                     # LLM abstraction (OpenAI, OpenRouter, Codex OAuth)
├── prompt/                  # Prompt loading and templating
└── utils/                   # Shared utilities

apps/
├── api/                     # FastAPI HTTP API (18 REST + 4 WebSocket)
│   └── events.py           # Shared event log + StreamOutput (used by REST + WS)
└── web/                     # Vue 3 frontend (Vite + Element Plus + Vue Flow)
```

## Prompt System Design (CRITICAL - MUST FOLLOW)

### System Prompt Aggregation

The system prompt is built by `prompt/aggregator.py` which combines:
1. **Base prompt from system.md** - Agent personality/guidelines ONLY
2. **Auto-generated tool list** - Name + one-line description for each tool
3. **Framework hints** - Tool call syntax, ##info##, ##read## commands

### What Goes Where

| Content | Location | Example |
|---------|----------|---------|
| Agent personality/role | `system.md` | "You are a SWE agent" |
| Agent-specific guidelines | `system.md` | "Use tools immediately" |
| Tool list (name + desc) | AUTO-GENERATED | `- bash: Execute shell commands` |
| Tool call syntax | `aggregator.py` hints | `##tool##...##tool##` |
| Full tool documentation | `builtin_skills/` | Loaded via `##info##` |

### NEVER Do These

1. **NEVER put tool list in system.md** - It's auto-aggregated
2. **NEVER put tool call syntax in system.md** - It's in framework hints
3. **NEVER put full tool docs in system prompt** - Use `##info##` command
4. **NEVER hardcode tool descriptions** - They come from tool classes

### On-Demand Documentation

Full tool/sub-agent documentation is loaded ONLY when requested:
- Controller uses `##info tool_name##` to get full docs
- Docs come from: agent folder override → builtin_skills → tool.get_full_documentation()

## Tool Execution Design (CRITICAL - MUST FOLLOW)

### Async Non-Blocking Execution

Tool execution follows this flow:
1. **During LLM streaming**: When `##tool##` block detected, start tool immediately via `asyncio.create_task()`
2. **Don't block streaming**: LLM continues outputting while tools run in background
3. **Parallel execution**: Multiple tools run simultaneously
4. **After streaming ends**: Wait for all direct tools with `asyncio.gather()`
5. **Batch results**: Combine all results into single event for controller

### NEVER Do These

1. **NEVER queue tools until LLM finishes** - Start immediately when detected
2. **NEVER execute tools sequentially** - Run in parallel with gather()
3. **NEVER block LLM output for tool execution** - They run concurrently

### Tool Execution Modes

From specification:
- **Direct/Blocking**: All jobs complete before returning (default for SWE agent)
- **Background**: Periodic status updates, context refresh
- **Stateful**: Multi-turn interaction (sub-agents)

## Current Focus

Core framework complete. Current work areas:
1. **Session persistence** - `.kohakutr` files via KohakuVault, full event recording, resume (`kt resume`)
2. **Web dashboard** - Vue 3 frontend with real-time terrarium UI, topology graph, multi-agent chat
3. **Context compaction** - Non-blocking compact with RAG memory (planned, see `plans/compact-design.md`)
4. **Memory system** - KohakuVault-backed searchable memory with FTS5 + vector search (planned)

## Session System

Sessions store everything in a `.kohakutr` file (SQLite via KohakuVault):
- Conversation snapshots (raw message dicts via msgpack, preserves tool_calls)
- Append-only event log (every text chunk, tool call, trigger, token usage)
- Sub-agent conversation capture (saved before destruction)
- Channel message history
- Scratchpad state

Resume rebuilds the agent from config and injects the saved conversation.

Key files: `src/kohakuterrarium/session/store.py`, `session/output.py`, `session/resume.py`
