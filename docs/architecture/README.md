# Architecture Overview

This section describes how KohakuTerrarium works internally. For what the key abstractions are and why they exist, see [Concepts](../concept/README.md).

## System Diagram

```
                    +---------------+
                    |  Input Module |
                    | (CLI,TUI,etc) |
                    +-------+-------+
                            | TriggerEvent
                            v
    +-----------------------------------------------+
    |                    Agent                       |
    |  +-------------------------------------------+ |
    |  |              Controller                   | |
    |  |  +-------------+    +-----------------+   | |
    |  |  | Conversation |<-- |  LLM Provider  |   | |
    |  |  +-------------+    +--------+--------+   | |
    |  |                              | Stream     | |
    |  |                              v            | |
    |  |                     +--------------+      | |
    |  |                     | StreamParser |      | |
    |  |                     +------+-------+      | |
    |  +----------------------------|--------------+ |
    |                               | ParseEvents    |
    |      +------------------------+----------+     |
    |      |                        |          |     |
    |      v                        v          v     |
    | +----------+          +----------+ +--------+  |
    | | Executor |          | SubAgent | | Output |  |
    | | (tools)  |          | Manager  | | Router |  |
    | +----+-----+          +----+-----+ +---+----+  |
    |      |                     |           |       |
    |      | JobResult           | Result    |       |
    |      +----------+----------+           v       |
    |                 |               +-----------+  |
    |                 v               |  Named    |  |
    |          +----------+           |  Outputs  |  |
    |          | JobStore |           +-----------+  |
    |          +----------+                          |
    +------------------------------------------------+
```

## Four Layers

KohakuTerrarium is organized into four layers:

| Layer | Location | Purpose | Docs |
|-------|----------|---------|------|
| **Agent Framework** | `src/kohakuterrarium/core/`, `modules/`, `parsing/`, `prompt/`, `builtins/` | Single-agent runtime: controller, tools, sub-agents, parsing, prompts | [Framework Internals](framework.md) |
| **Session Persistence** | `src/kohakuterrarium/session/` | Store everything, resume anytime: SessionStore (.kohakutr files), SessionOutput, resume | [Execution Model](execution-model.md) |
| **Terrarium Runtime** | `src/kohakuterrarium/terrarium/` | Multi-agent orchestration: config, wiring, lifecycle, observer, hot-plug | [Terrarium Runtime](terrarium-runtime.md) |
| **Serving Layer** | `src/kohakuterrarium/serving/` | Transport-agnostic API: KohakuManager, AgentSession, event streaming | [Serving Layer](serving.md) |

The HTTP API (`apps/api/`) and web frontend (`apps/web/`) are application layers built on top of the serving layer.

## Design Principles

1. **Controller as orchestrator** - the controller dispatches tasks, it does not produce long output itself. Heavy work goes to tools and sub-agents.

2. **Non-blocking tool execution** - tools start immediately when detected during LLM streaming, not queued until the response ends. Multiple tools run in parallel.

3. **Unified event model** - everything flows through `TriggerEvent`: user input, timer triggers, tool completions, sub-agent output, channel messages.

4. **Creature opacity** - a terrarium never inspects or modifies creature internals. Communication is always explicit via channels.

5. **Configuration-driven** - agents are defined declaratively in YAML. Custom behavior comes from pluggable modules.
