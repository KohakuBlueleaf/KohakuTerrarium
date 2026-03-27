# core/ -- Runtime and Orchestration

The core module contains the runtime engine that powers every KohakuTerrarium agent.
All components communicate through a unified `TriggerEvent` model.

## Modules

### Agent (`agent.py`, `agent_init.py`, `agent_handlers.py`)

Top-level orchestrator that wires all subsystems together. Split across three files
to stay under the line limit:

- **`agent.py`** -- `Agent` class with public API (`from_path()`, `run()`, `inject_input()`)
- **`agent_init.py`** -- `AgentInitMixin` initializes LLM, registry, executor, input, output, triggers, sub-agents
- **`agent_handlers.py`** -- `AgentHandlersMixin` processes events, executes tools, manages background jobs

### Controller (`controller.py`)

Main LLM conversation loop. Receives `TriggerEvent`s, maintains conversation
context, runs the LLM, and parses output into tool calls, sub-agent dispatches,
commands, and text. Supports multimodal content (text + images).

Key class: `ControllerConfig` (model, temperature, ephemeral mode, context limits).

### Executor (`executor.py`)

Background tool runner. Starts tools via `asyncio.create_task()` during LLM
streaming so they run in parallel. Tracks jobs and produces completion events.

### Events (`events.py`)

Unified event model. `TriggerEvent` is the single event type that flows through
the entire system -- inputs, triggers, tool completions, and sub-agent outputs
all produce `TriggerEvent`s. Supports stackable batching and multimodal content.

Common event types: `user_input`, `timer`, `tool_complete`, `subagent_output`,
`monitor`, `error`.

### Channel (`channel.py`)

Named async pub/sub channels for cross-component communication. Components send
and receive `ChannelMessage`s through a `ChannelRegistry` without direct coupling.
Used by `send_message`/`wait_channel` tools and `ChannelTrigger`.

### Session (`session.py`)

Keyed shared state registry. A `Session` holds all session-scoped objects for one
agent (or a group of cooperating agents): channels, scratchpad, TUI state, and
user-provided extras. Functions: `get_session(key)`, `set_session()`, `remove_session()`.
Agents with the same `session_key` in config share a single Session instance.

The legacy `get_channel_registry()` and `get_scratchpad()` singletons now route
through the default session for backward compatibility.

### Scratchpad (`scratchpad.py`)

Session-scoped key-value working memory. Unlike file-based memory (cross-session,
agent-managed), the scratchpad is cleared on restart, framework-managed, structured,
and cheap (no LLM needed to read/write).

### Termination (`termination.py`)

Configurable stop conditions for the agent loop. Supports: `max_turns`,
`max_tokens`, `max_duration`, `idle_timeout`, and `keywords` (stop on output
keyword). Any triggered condition stops the agent.

### Config (`config.py`)

Loads and validates agent configuration from YAML, JSON, or TOML files.
Supports environment variable interpolation (`${VAR:default}`). Produces
`AgentConfig` with typed sub-configs for input, tools, triggers, sub-agents,
output, and termination.

### Constants (`constants.py`)

Framework-wide magic numbers: tool result truncation limits, status preview
lengths, and sub-agent output caps.

### Supporting Files

| File | Purpose |
|------|---------|
| `conversation.py` | Context management and compaction |
| `job.py` | Job status tracking (`JobStore`, `JobResult`, `JobState`) |
| `loader.py` | Dynamic module loading (custom tools, inputs, outputs) |
| `registry.py` | Module registration (`Registry` for tools and sub-agents) |
