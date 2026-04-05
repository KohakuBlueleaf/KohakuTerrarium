# Concepts

Conceptual foundations and architecture internals: what the abstractions are, how they relate, and how the system works under the hood.

- [Overview](overview.md) — five major systems, event model, composition levels
- [Agents](agents.md) — creature lifecycle, controller as orchestrator, sub-agents
- [Terrariums](terrariums.md) — pure wiring layer, root agent, horizontal composition
- [Channels](channels.md) — queue/broadcast types, channel triggers, on_send callbacks
- [Execution Model](execution.md) — event sources, processing loop, tool modes
- [Prompt System](prompts.md) — system prompt aggregation, skill modes, topology injection
- [Serving Layer](serving.md) — KohakuManager, unified WebSocket, session recording
- [Environment-Session](environment.md) — isolation, shared state, session lifecycle
- [Tool Formats](tool-formats.md) — call syntax, parsing, format configuration
